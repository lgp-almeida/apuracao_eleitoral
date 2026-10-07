"""Abstenção × mudança de local (rodada 56) — offline, seções sintéticas com os números calculados à mão."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import polars as pl
import pytest

from apuracao import abstencao_locais as al

RIO, NIT = 60011, 58653


def _sec(rows: list[tuple]) -> pl.DataFrame:
    """(município, zona, seção, nº local, nome, endereço, lat, lon, aptos, abstenções)."""
    return pl.DataFrame([{"CD_MUNICIPIO": m, "NR_ZONA": z, "NR_SECAO": s, "NM_MUNICIPIO": "RIO", "NR_LOCAL_VOTACAO": n,
                          "NM_LOCAL_VOTACAO": nome, "DS_ENDERECO": end, "NM_BAIRRO": None, "NR_LATITUDE": lat,
                          "NR_LONGITUDE": lon, "APTOS": ap, "COMPARECIMENTO": ap - ab, "ABSTENCOES": ab,
                          "APTOS_GOV": ap, "COMPARECIMENTO_GOV": ap - ab, "ABSTENCOES_GOV": ab}
                         for m, z, s, n, nome, end, lat, lon, ap, ab in rows])


# 2022 e 2026: zona 1 com duas seções que ficam (controle), uma que mudou de prédio (nº reaproveitado!), uma
# renumerada no mesmo prédio, uma que mudou de nº e de prédio a 1 km, uma extinta e uma nova
A = _sec([(RIO, 1, 1, 10, "ESCOLA MUNICIPAL ALFA", "RUA A, 1", -22.90, -43.20, 100, 20),
          (RIO, 1, 2, 10, "ESCOLA MUNICIPAL ALFA", "RUA A, 1", -22.90, -43.20, 300, 60),
          (RIO, 1, 3, 20, "SOPRECAM", "AV B, 2", -22.91, -43.21, 200, 40),
          (RIO, 1, 4, 30, "COLEGIO ESTADUAL EDUARDO BREDERODES", "RUA C, 3", -22.92, -43.22, 100, 20),
          (RIO, 1, 5, 40, "CIEP 100 GAMA", "RUA D, 4", -22.93, -43.23, 100, 30),
          (RIO, 1, 6, 50, "IGREJA", "RUA E, 5", -22.94, -43.24, 50, 10)])
B = _sec([(RIO, 1, 1, 10, "E.M. ALFA", "RUA A, 1", -22.90, -43.20, 100, 22),            # mesmo endereço: MANTEVE
          (RIO, 1, 2, 10, "ESCOLA MUNICIPAL ALFA", "RUA A 1", -22.90, -43.20, 300, 69),  # mesmo nome: MANTEVE
          (RIO, 1, 3, 20, "COLEGIO OBJETIVO CAMBOINHAS", "RUA X, 9", -22.91, -43.21, 200, 50),  # mesmo nº e ponto: MUDOU
          (RIO, 1, 4, 31, "ESCOLA ESTADUAL EDUARDO BREDERODES", "RUA C 3 FUNDOS", -22.9201, -43.2201, 100, 25),
          (RIO, 1, 5, 41, "PUC RIO EDIFICIO CARDEAL", "RUA P, 7", -22.93, -43.2203 + 0.0097, 100, 40),
          (RIO, 1, 7, 60, "NOVA", "RUA N, 1", -22.95, -43.25, 80, 10)])


def test_similaridade_ignora_palavras_genericas() -> None:
    assert al.similaridade("COLEGIO ESTADUAL EDUARDO BREDERODES", "ESCOLA ESTADUAL EDUARDO BREDERODES") == 1.0
    assert al.similaridade("QUADRA POLIESPORTIVA CIEP 275", "CIEP 275 LENINE CORTES FALANTE") == pytest.approx(1 / 3)
    assert al.similaridade("ESCOLA MUNICIPAL", "COLEGIO ESTADUAL") == 0.0  # só palavras genéricas


def test_classificacao_pelo_lugar_e_nao_pelo_numero() -> None:
    c = al.classificar(A, B, 2022, 2026)
    classe = dict(c.select("NR_SECAO", "CLASSE").iter_rows())
    assert classe == {1: al.MANTEVE, 2: al.MANTEVE, 3: al.MUDOU, 4: al.RENUMERADO, 5: al.MUDOU, 6: al.FORA, 7: al.FORA}
    s3 = c.filter(pl.col("NR_SECAO") == 3).row(0, named=True)
    assert s3["DISTANCIA_M"] == 0 and s3["FAIXA_DISTANCIA"] == "até 150 m"  # o TSE repetiu o ponto: outro prédio
    assert c.filter(pl.col("NR_SECAO") == 5)["FAIXA_DISTANCIA"].item() == "0,5–2 km"
    motivos = dict(c.filter(pl.col("CLASSE") == al.FORA).select("NR_SECAO", "MOTIVO_FORA").iter_rows())
    assert motivos == {6: "seção sem voto em 2026 (extinta ou agregada)", 7: "seção nova em 2026"}


def test_excesso_dentro_da_zona() -> None:
    s = al.excesso(al.classificar(A, B, 2022, 2026), 2022, 2026)
    # controle da zona: seções 1 (20%→22%, +2) e 2 (20%→23%, +3), ponderadas por 100 e 300 aptos → +2,75 p.p.
    assert s["DELTA_CONTROLE_ZONA_PP"].drop_nulls().unique().to_list() == [pytest.approx(2.75)]
    s3 = s.filter(pl.col("NR_SECAO") == 3).row(0, named=True)  # 20% → 25%: +5 − 2,75
    assert s3["EXCESSO_PP"] == pytest.approx(2.25) and s3["ELEITORES_A_MAIS_ABSTENDO"] == pytest.approx(4.5)
    s5 = s.filter(pl.col("NR_SECAO") == 5).row(0, named=True)  # 30% → 40%: +10 − 2,75
    assert s5["EXCESSO_PP"] == pytest.approx(7.25)
    assert s.filter(pl.col("NR_SECAO") == 4)["EXCESSO_PP"].item() is None  # renumerado: fora do efeito
    g = al.agregar(s, [], 2022, 2026).row(0, named=True)  # (4,5 + 7,25) / 300 aptos
    assert g["SECOES"] == 2 and g["EXCESSO_PP"] == pytest.approx(100 * 11.75 / 300)
    assert g["ABST_PCT_2022"] == pytest.approx(100 * 70 / 300) and g["ABST_PCT_2026"] == pytest.approx(100 * 90 / 300)


def _votos(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame([{"CD_MUNICIPIO": RIO, "NR_ZONA": 1, "NR_SECAO": s, "CD_CARGO": c, "NR_VOTAVEL": n, "QT_VOTOS": q}
                         for s, c, n, q in rows])


CAND_B = pl.DataFrame({"CD_CARGO": [1, 1, 1], "NUMERO": [13, 22, 55], "NOME": ["LULA", "FLAVIO", "CAIADO"],
                       "PARTIDO": ["PT", "PL", "PSD"]})
CAND_A = pl.DataFrame({"CD_CARGO": [1, 1], "NUMERO": [13, 22], "NOME": ["LULA", "BOLSONARO"], "PARTIDO": ["PT", "PL"]})
VOTOS_B = _votos([(1, 1, 13, 40), (1, 1, 22, 38), (2, 1, 13, 100), (2, 1, 22, 131),
                  (3, 1, 13, 100), (3, 1, 22, 40), (3, 1, 96, 10),     # seção 3: 150 votos
                  (5, 1, 13, 10), (5, 1, 22, 40), (5, 1, 55, 10)])      # seção 5: 60 votos
VOTOS_A = _votos([(1, 1, 13, 40), (1, 1, 22, 40), (2, 1, 13, 120), (2, 1, 22, 120),
                  (3, 1, 13, 100), (3, 1, 22, 60), (5, 1, 13, 30), (5, 1, 22, 40)])


def test_votos_perdidos_e_margem() -> None:
    s = al.excesso(al.classificar(A, B, 2022, 2026), 2022, 2026)
    p = al.votos_perdidos(s, VOTOS_B, CAND_B, 2026)
    perdido = dict(p.select("NUMERO", "VOTOS_PERDIDOS_EST").iter_rows())
    # seção 3: 4,5 eleitores × (100, 40, 10)/150; seção 5: 7,25 × (10, 40, 10)/60
    assert perdido[13] == pytest.approx(4.5 * 100 / 150 + 7.25 * 10 / 60)
    assert perdido[22] == pytest.approx(4.5 * 40 / 150 + 7.25 * 40 / 60)
    assert perdido[96] == pytest.approx(4.5 * 10 / 150)
    assert p.filter(pl.col("NUMERO") == 96)["LEITURA"].item() is None and p.filter(pl.col("NUMERO") == 96)["NOME"].item() == "Nulos"
    m = al.efeito_na_margem(p).row(0, named=True)  # o mais votado (Lula, 250) × o 2º (Flávio, 249)
    assert (m["CANDIDATO_A"], m["CANDIDATO_B"]) == ("LULA (PT)", "FLAVIO (PL)")
    assert m["EFEITO_NA_MARGEM_EST"] == pytest.approx(perdido[22] - perdido[13])
    soma = p.filter(pl.col("LEITURA").is_not_null())["PERDA_ALEM_DA_PROPORCIONAL"].sum()
    assert soma == pytest.approx(0, abs=1e-9)  # o que um perde além da parte, outro perde aquém


def test_partidos_ligados_pela_entidade_e_sem_par() -> None:
    s = al.excesso(al.classificar(A, B, 2022, 2026), 2022, 2026)
    d = al.desempenho_partidos(s, VOTOS_A, VOTOS_B, CAND_A, CAND_B, 2022, 2026)
    pt_ = d.filter(pl.col("PARTIDO") == "PT").row(0, named=True)
    # MUDOU = seções 3 e 5 (300 aptos nos dois anos): PT 130/300 em 2022, 110/300 em 2026
    assert pt_["PCT_ELEITORADO_MUDOU_2022"] == pytest.approx(100 * 130 / 300)
    assert pt_["PCT_ELEITORADO_MUDOU_2026"] == pytest.approx(100 * 110 / 300)
    # controle (seções 1 e 2): Δ PT = 40→40 (0) e 120→100 (−6,67 p.p.), ponderados 100 e 300 → −5
    assert pt_["DELTA_CONTROLE_ZONA_PP"] == pytest.approx(-5.0)
    assert pt_["DELTA_MUDOU_PP"] == pytest.approx(100 * (110 - 130) / 300)  # 0 e −20 p.p. em 200 e 100 aptos
    assert pt_["DIF_EM_DIF_PP"] == pytest.approx(pt_["DELTA_MUDOU_PP"] + 5.0)
    psd = d.filter(pl.col("PARTIDO") == "PSD").row(0, named=True)  # sem candidato em 2022: sem dado, não 0
    assert psd["PARTIDO_EM_2022"] is None and psd["DIF_EM_DIF_PP"] is None and psd["PCT_ELEITORADO_MUDOU_2026"] > 0


def test_planilha(tmp_path: Path) -> None:
    r = al.montar(A, B, VOTOS_A, VOTOS_B, CAND_A, CAND_B, "RJ", 2022, 2026)
    assert r.notas[0].startswith("FORA: 2 seções")
    destino = al.escrever(r, tmp_path / "x" / "abst.xlsx")
    wb = openpyxl.load_workbook(destino)
    assert wb.sheetnames == ["LEIA-ME", "Resumo", "Seções", "Locais que mudaram", "Zonas", "Municípios", "Candidatos",
                             "Margem", "Partidos"]
    secoes = wb["Seções"]
    cab = [c.value for c in secoes[1]]
    assert secoes.max_row == 1 + 7 and "CLASSE" in cab and "EXCESSO_PP" in cab
    formatos = [str(f.formula) for regra in secoes.conditional_formatting for f in regra.rules]
    assert any(al.MUDOU in f for f in formatos) and any(al.RENUMERADO in f for f in formatos)
    assert wb["Locais que mudaram"].max_row == 1 + 2


def test_cli_rejeita_saida_com_varias_ufs(capsys) -> None:
    import abstencao_mudanca_local as cli
    assert cli.main(["--uf", "RJ", "SP", "--saida", "x.xlsx"]) == 2
    assert cli.main(["--uf", "XX"]) == 2
