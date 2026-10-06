"""Importação de resultado histórico (microdados) no formato do site — offline, dados sintéticos."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

import votos_por_local_votacao as v
from apuracao import historico as h
from apuracao.web.app import create_app

RIO, NIT, SP = 60011, 58653, 71072

# detalhe_votacao_munzona: (turno, eleição, uf, município, zona, cargo, aptos, comparec., válidos, nominais,
#                           legenda, brancos, nulos, seções)
DETALHE = [
    (1, 546, "RJ", RIO, 4, 3, 1000, 800, 700, 700, 0, 50, 50, 3),
    (1, 546, "RJ", RIO, 5, 3, 500, 400, 350, 350, 0, 25, 25, 2),
    (1, 546, "RJ", NIT, 71, 3, 300, 240, 200, 200, 0, 20, 20, 1),
    (1, 546, "RJ", RIO, 4, 7, 1000, 800, 740, 700, 40, 30, 30, 3),
    (1, 544, "RJ", RIO, 4, 1, 1000, 800, 760, 760, 0, 20, 20, 3),
    (1, 544, "SP", SP, 1, 1, 2000, 1500, 1400, 1400, 0, 50, 50, 5),
    (1, 544, "ZZ", 99999, 1, 1, 100, 50, 45, 45, 0, 3, 2, 1),
    (2, 545, "RJ", RIO, 4, 1, 1000, 790, 770, 770, 0, 10, 10, 3),
    (2, 545, "SP", SP, 1, 1, 2000, 1490, 1450, 1450, 0, 20, 20, 5),
]
DET_COLS = ["NR_TURNO", "CD_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO", "QT_APTOS", "QT_COMPARECIMENTO",
            "QT_TOTAL_VOTOS_VALIDOS", "QT_VOTOS_NOMINAIS_VALIDOS", "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_BRANCOS",
            "QT_TOTAL_VOTOS_NULOS", "QT_TOTAL_SECOES"]

# consulta_cand: (turno, uf, cargo, número, nome, partido, nº partido, candidatura, situação)
CAND = [
    (1, "RJ", 3, 22, "CASTRO", "PL", 22, "INAPTO", "ELEITO"),     # inapto HOJE, eleito em 2022
    (1, "RJ", 3, 40, "FREIXO", "PSB", 40, "APTO", "NÃO ELEITO"),
    (1, "RJ", 3, 40, "FREIXO (substituído)", "PSB", 40, "INAPTO", None),  # nº repetido: fica o APTO
    (1, "RJ", 7, 55123, "FULANA", "PSD", 55, "APTO", "ELEITO POR QP"),
    (1, "RJ", 7, 55456, "BELTRANO", "PSD", 55, "APTO", "SUPLENTE"),
    (1, "BR", 1, 13, "LULA", "PT", 13, "APTO", "2º TURNO"),
    (1, "BR", 1, 22, "BOLSONARO", "PL", 22, "APTO", "2º TURNO"),
    (2, "BR", 1, 13, "LULA", "PT", 13, "APTO", "ELEITO"),
    (2, "BR", 1, 22, "BOLSONARO", "PL", 22, "APTO", "NÃO ELEITO"),
]
# votação por seção: (turno, uf, município, cargo, votável, votos)
VOTOS_UF = [
    (1, "RJ", RIO, 3, 22, 700), (1, "RJ", RIO, 3, 40, 350), (1, "RJ", NIT, 3, 22, 50), (1, "RJ", NIT, 3, 40, 150),
    (1, "RJ", RIO, 3, 95, 75), (1, "RJ", RIO, 3, 96, 75),
    (1, "RJ", RIO, 7, 55123, 500), (1, "RJ", RIO, 7, 55456, 200), (1, "RJ", RIO, 7, 55, 40), (1, "RJ", RIO, 7, 96, 30),
]
VOTOS_BR = [
    (1, "RJ", RIO, 1, 13, 300), (1, "RJ", RIO, 1, 22, 460), (1, "SP", SP, 1, 13, 800), (1, "SP", SP, 1, 22, 600),
    (1, "ZZ", 99999, 1, 13, 20), (1, "ZZ", 99999, 1, 22, 25),
    (2, "RJ", RIO, 1, 13, 330), (2, "RJ", RIO, 1, 22, 440), (2, "SP", SP, 1, 13, 800), (2, "SP", SP, 1, 22, 650),
]


def _detalhe() -> pl.DataFrame:
    df = pl.DataFrame([[str(x) for x in r] for r in DETALHE], schema=DET_COLS, orient="row")
    return df.with_columns(
        (pl.col("QT_APTOS").cast(pl.Int64) - pl.col("QT_COMPARECIMENTO").cast(pl.Int64)).cast(pl.String).alias("QT_ABSTENCOES"),
        pl.col("QT_COMPARECIMENTO").alias("QT_VOTOS"), pl.lit("0").alias("QT_TOTAL_VOTOS_ANULADOS"),
        pl.lit("0").alias("QT_TOTAL_VOTOS_ANUL_SUBJUD"),
        pl.when(pl.col("CD_CARGO") == "1").then(pl.lit("Presidente")).when(pl.col("CD_CARGO") == "3")
        .then(pl.lit("Governador")).otherwise(pl.lit("Deputado Estadual")).alias("DS_CARGO"),
        pl.lit("02/10/2022").alias("DT_ULTIMA_TOTALIZACAO"), pl.lit("20:00:00").alias("HH_ULTIMA_TOTALIZACAO"),
    )


def _cand() -> pl.DataFrame:
    rows = [{"NR_TURNO": str(t), "SG_UF": uf, "CD_CARGO": str(c), "NR_CANDIDATO": str(n), "NM_URNA_CANDIDATO": nm,
             "NM_CANDIDATO": nm, "SQ_CANDIDATO": str(i), "SG_PARTIDO": sg, "NR_PARTIDO": str(np_),
             "SG_FEDERACAO": None, "NM_FEDERACAO": None, "NM_COLIGACAO": "PARTIDO ISOLADO",
             "DS_COMPOSICAO_COLIGACAO": sg, "DS_SITUACAO_CANDIDATURA": apto, "DS_SIT_TOT_TURNO": sit,
             "DT_GERACAO": "29/09/2026"}
            for i, (t, uf, c, n, nm, sg, np_, apto, sit) in enumerate(CAND)]
    return pl.DataFrame(rows, schema={k: pl.String for k in rows[0]})


def _votos(rows: list[tuple]) -> pl.LazyFrame:
    return pl.DataFrame(rows, schema=["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "CD_CARGO", "NR_VOTAVEL", "QT_VOTOS"],
                        orient="row").lazy()


def _tabelas(turno: int) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    tot = h.totais(_detalhe(), "RJ", turno)
    cand, part = h.candidatos_e_partidos(_votos(VOTOS_UF), _votos(VOTOS_BR), _cand(), tot, "RJ", turno)
    return h.vagas(tot, cand), cand, part


def _row(df: pl.DataFrame, **kw: object) -> dict:
    cond = pl.lit(True)
    for k, val in kw.items():
        cond &= pl.col(k).is_null() if val is None else pl.col(k) == val
    return df.filter(cond).row(0, named=True)


def test_totais_por_abrangencia() -> None:
    tot, _, _ = _tabelas(1)
    gov_uf = _row(tot, CARGO=3, ABRANGENCIA="uf")
    assert (gov_uf["ELEITORADO"], gov_uf["VALIDOS"], gov_uf["SECOES_TOTAL"]) == (1800, 1250, 6)
    assert gov_uf["PCT_ABSTENCAO"] == pytest.approx(100 * 360 / 1800)
    assert _row(tot, CARGO=3, ABRANGENCIA="mun", CD_MUNICIPIO=RIO)["VALIDOS"] == 1050  # zonas somadas
    pres_br = _row(tot, CARGO=1, ABRANGENCIA="br")
    assert pres_br["VALIDOS"] == 760 + 1400 + 45 and pres_br["ELEICAO"] == 544  # Brasil inclui SP e exterior
    assert tot.filter(pl.col("UF") == "SP").is_empty()  # municípios de outras UFs não entram
    assert gov_uf["TOTALIZACAO_FINAL"] and gov_uf["PCT_SECOES_TOTALIZADAS"] == 100.0


def test_candidatos_situacao_e_destinacao() -> None:
    _, cand, _ = _tabelas(1)
    castro = _row(cand, CARGO=3, ABRANGENCIA="uf", NUMERO=22)
    assert castro["VOTOS"] == 750 and castro["PCT_VALIDOS"] == pytest.approx(60.0) and castro["SEQ"] == 1
    assert castro["SITUACAO"] == "Eleito" and castro["ELEITO"]
    assert castro["DESTINACAO"] == "candidatura INAPTO no cadastro de 29/09/2026"  # não vira "anulado"
    assert _row(cand, CARGO=3, ABRANGENCIA="uf", NUMERO=40)["NOME_URNA"] == "FREIXO"  # APTO vence o duplicado
    assert _row(cand, CARGO=7, ABRANGENCIA="uf", NUMERO=55123)["SITUACAO"] == "Eleito por QP"
    lula = _row(cand, CARGO=1, ABRANGENCIA="br", NUMERO=13)
    assert lula["VOTOS"] == 1120 and lula["SITUACAO"] == "2º turno" and lula["ELEITO"]
    assert cand.filter(pl.col("NUMERO").is_in([95, 96, 55])).is_empty()  # brancos, nulos e legenda fora


def test_partidos_vagas_e_segundo_turno() -> None:
    tot, _, part = _tabelas(1)
    psd = _row(part, CARGO=7, ABRANGENCIA="uf", NR_PARTIDO=55)
    assert (psd["VOTOS_NOMINAIS"], psd["VOTOS_LEGENDA"], psd["VOTOS_TOTAL"], psd["PARTIDO"]) == (700, 40, 740, "PSD")
    assert psd["VAGAS_AGREMIACAO"] == 1 and psd["ELEICAO"] == 546
    assert _row(tot, CARGO=7, ABRANGENCIA="uf")["VAGAS"] == 1 and _row(tot, CARGO=3, ABRANGENCIA="uf")["VAGAS"] == 1
    tot2, cand2, part2 = _tabelas(2)
    assert set(tot2["CARGO"]) == {1} and part2.is_empty()
    assert _row(cand2, CARGO=1, ABRANGENCIA="br", NUMERO=13)["SITUACAO"] == "Eleito"


def test_importar_e_abrir_no_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "load_detalhe", lambda ano, cache: _detalhe())
    monkeypatch.setattr(h, "load_candidatos", lambda ano, cache: _cand())
    monkeypatch.setattr(h, "load_votos", lambda ano, uf, cache: (_votos(VOTOS_UF), _votos(VOTOS_BR)))
    monkeypatch.setattr(h, "fonte_padrao", lambda ano, uf, cache: "secao")  # os votos acima são da fonte "secao"
    monkeypatch.setattr(h, "municipios_tse_ibge", lambda uf, cache: pl.DataFrame(
        {"UF": ["RJ", "RJ"], "CD_MUNICIPIO": [RIO, NIT], "CD_MUNICIPIO_IBGE": [3304557, 3303302],
         "NM_MUNICIPIO": ["RIO DE JANEIRO", "NITERÓI"], "CAPITAL": [True, False], "ZONAS": ["4,5", "71"]}))
    destino = tmp_path / "historico_2022_t1"
    n = h.importar(2022, "RJ", 1, tmp_path, destino)
    assert n["municipios"] == 2 and n["candidatos"] > 0
    st = json.loads((destino / "status.json").read_text())
    assert st["ano"] == 2022 and st["erro"] is None

    site = TestClient(create_app(destino, "RJ", tmp_path))
    assert site.get("/api/status").json()["coletor"]["ano"] == 2022
    cartoes = {(c["cargo"], c["abrangencia"]) for c in site.get("/api/painel").json()["cartoes"]}
    assert cartoes == {(1, "BRASIL"), (1, "RJ"), (3, "RJ"), (7, "RJ")}
    mapa = site.get("/api/mapa?cargo=3&metrica=vencedor").json()
    assert mapa["itens"]["3304557"]["valor"] == 22 and mapa["itens"]["3303302"]["valor"] == 40


# --------------------------------------------------------------------------
# Fonte "munzona" (rodada 39): os arquivos nacionais por município e zona dão o mesmo resultado
# --------------------------------------------------------------------------
def _zip_tse(destino: Path, membro: str, cab: list[str], linhas: list[list]) -> None:
    import zipfile

    texto = "\n".join(";".join(f'"{x}"' for x in r) for r in [cab, *linhas]) + "\n"
    with zipfile.ZipFile(destino, "w") as z:
        z.writestr(membro, texto.encode("latin-1"))


def _munzona(cache: Path) -> None:
    """VOTOS_UF + VOTOS_BR no layout dos arquivos por município e zona (cada voto dividido em duas zonas, para
    conferir a soma), com uma eleição suplementar (CD_TIPO_ELEICAO 1) que tem de ser ignorada."""
    cab_c = ["CD_TIPO_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO", "NR_CANDIDATO",
             "QT_VOTOS_NOMINAIS", "NR_PARTIDO", "CD_ELEICAO", "NM_TIPO_DESTINACAO_VOTOS", "DS_SIT_TOT_TURNO"]
    # situação NA TOTALIZAÇÃO (a do consulta_cand sintético; Castro: INAPTO no cadastro, mas Válido/ELEITO aqui)
    sit = {(t, c, n): st for t, _, c, n, _, _, _, apto, st in CAND if st and apto == "APTO" or n == 22 and c == 3}
    cab_p = ["CD_TIPO_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO", "NR_PARTIDO",
             "QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_LEGENDA_ANUL_SUBJUD", "QT_VOTOS_LEGENDA_ANULADOS"]
    cand, part = [], []
    for t, uf, mun, cargo, votavel, q in VOTOS_UF + VOTOS_BR:
        if votavel in h.ESPECIAIS:
            continue
        if cargo in h.PROPORCIONAIS and votavel < 100:  # legenda: válidos + anulados
            part.append([2, t, uf, mun, 1, cargo, votavel, q - 10, 0, 10])
        else:
            extra = [votavel if votavel < 100 else votavel // 1000, 546 if cargo != 1 else 544 + t - 1, "Válido",
                     sit.get((t, cargo, votavel), "NÃO ELEITO")]
            cand += [[2, t, uf, mun, 1, cargo, votavel, q // 2, *extra], [2, t, uf, mun, 2, cargo, votavel, q - q // 2, *extra]]
    cand.append([1, 1, "RJ", RIO, 1, 3, 22, 99999, 22, 999, "Válido", "ELEITO"])  # suplementar: fora
    _zip_tse(cache / "votacao_candidato_munzona_2022.zip", "votacao_candidato_munzona_2022_BRASIL.csv", cab_c, cand)
    _zip_tse(cache / "votacao_partido_munzona_2022.zip", "votacao_partido_munzona_2022_BRASIL.csv", cab_p, part)


@pytest.fixture()
def sem_microdados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h, "load_detalhe", lambda ano, cache: _detalhe())
    monkeypatch.setattr(h, "load_candidatos", lambda ano, cache: _cand())
    monkeypatch.setattr(h, "municipios_tse_ibge", lambda uf, cache: pl.DataFrame(
        {"UF": ["RJ"], "CD_MUNICIPIO": [RIO], "CD_MUNICIPIO_IBGE": [3304557], "NM_MUNICIPIO": ["RIO DE JANEIRO"],
         "CAPITAL": [True], "ZONAS": ["4,5"]}))


@pytest.mark.parametrize("turno", [1, 2])
def test_fonte_munzona_igual_a_secao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sem_microdados: None,
                                     turno: int) -> None:
    _munzona(tmp_path)
    monkeypatch.setattr(h, "load_votos", lambda ano, uf, cache: (_votos(VOTOS_UF), _votos(VOTOS_BR)))
    assert h.fonte_padrao(2022, "RJ", tmp_path) == "munzona"  # sem o votacao_secao da UF no cache
    h.importar(2022, "RJ", turno, tmp_path, tmp_path / "s", fonte="secao")
    h.importar(2022, "RJ", turno, tmp_path, tmp_path / "m")
    for tab, chave in (("candidatos", ["CARGO", "ABRANGENCIA", "CD_MUNICIPIO", "NUMERO"]),
                       ("partidos", ["CARGO", "ABRANGENCIA", "CD_MUNICIPIO", "NR_PARTIDO"]), ("totais", ["CARGO", "ABRANGENCIA", "CD_MUNICIPIO"])):
        a, b = (pl.read_parquet(tmp_path / d / "ultimo" / f"{tab}.parquet").sort(chave, nulls_last=True) for d in "sm")
        assert a.drop("SEQ", strict=False).equals(b.drop("SEQ", strict=False)), tab
    fontes = json.loads((tmp_path / "m" / "status.json").read_text())["fontes"]
    assert "votacao_candidato_munzona_2022" in fontes and not any(f.startswith("votacao_secao") for f in fontes)
    br = pl.read_parquet(tmp_path / "m" / "ultimo" / "candidatos.parquet").filter(
        (pl.col("ABRANGENCIA") == "br") & (pl.col("NUMERO") == 13))
    assert br["VOTOS"].item() == (1120 if turno == 1 else 1130)  # Brasil = todas as UFs + exterior
    if turno == 1:  # destinação e situação da TOTALIZAÇÃO (candidato_munzona), não as do consulta_cand regerado
        castro = pl.read_parquet(tmp_path / "m" / "ultimo" / "candidatos.parquet").filter(
            (pl.col("ABRANGENCIA") == "uf") & (pl.col("CARGO") == 3) & (pl.col("NUMERO") == 22)).row(0, named=True)
        assert (castro["DESTINACAO"], castro["SITUACAO"], castro["ELEITO"]) == ("Válido", "Eleito", True)


def test_fonte_padrao_e_invalida(tmp_path: Path, sem_microdados: None) -> None:
    (tmp_path / "votacao_secao_2022_RJ.zip").touch()
    assert h.fonte_padrao(2022, "rj", tmp_path) == "secao" and h.fonte_padrao(2022, "SP", tmp_path) == "munzona"
    with pytest.raises(ValueError, match="fonte"):
        h.importar(2022, "RJ", 1, tmp_path, tmp_path / "x", fonte="outra")


def test_municipios_cache_sem_a_uf_e_refeito(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache gerado do EA12 de uma eleição municipal não tem o DF: é refeito uma vez (rodada 39)."""
    cols = {"UF": ["RJ"], "CD_MUNICIPIO": [RIO], "CD_MUNICIPIO_IBGE": [3304557], "NM_MUNICIPIO": ["RIO DE JANEIRO"],
            "CAPITAL": [True], "ZONAS": ["4"]}
    pl.DataFrame(cols).write_parquet(tmp_path / h.MUNICIPIOS_CACHE)
    feitos = []

    def baixar(path: Path) -> None:
        feitos.append(path)
        pl.DataFrame({k: v + ([{"UF": "DF", "CD_MUNICIPIO": 97012, "CD_MUNICIPIO_IBGE": 5300108,
                                "NM_MUNICIPIO": "BRASÍLIA", "CAPITAL": True, "ZONAS": "1"}[k]])
                      for k, v in cols.items()}).write_parquet(path)

    monkeypatch.setattr(h, "_baixar_municipios", baixar)
    assert h.municipios_tse_ibge("RJ", tmp_path).height == 1 and not feitos  # UF no cache: sem rede
    assert h.municipios_tse_ibge("df", tmp_path)["NM_MUNICIPIO"].to_list() == ["BRASÍLIA"] and len(feitos) == 1


# --------------------------------------------------------------------------
# Totais reconstruídos das seções (rodada 40): enquanto o TSE não publica o detalhe_votacao_munzona
# --------------------------------------------------------------------------
def _dest(linhas: list[tuple]) -> pl.DataFrame:
    """(turno, uf, cargo, número, nº partido, destinação) → o formato de `destinacao_oficial`."""
    return pl.DataFrame(linhas, schema=["NR_TURNO", "SG_UF", "CD_CARGO", "NUMERO", "NR_PARTIDO", "DESTINACAO_TSE"],
                        orient="row").with_columns(pl.lit(546).alias("CD_ELEICAO"), pl.lit("ELEITO").alias("SITUACAO_TSE"))


def _secoes(votos: list[tuple], detalhe: list[tuple]) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """votos: (turno, uf, mun, zona, seção, cargo, votável, qtd); detalhe: (turno, uf, mun, zona, seção, cargo,
    aptos, comparecimento, hora de entrada na totalização)."""
    vs = pl.DataFrame(votos, schema=["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO",
                                     "NR_VOTAVEL", "QT_VOTOS"], orient="row")
    det = pl.DataFrame(detalhe, schema=["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO",
                                        "QT_APTOS", "QT_COMPARECIMENTO", "DT_PRIM_TOT_PARCIAL_HOR_TSE"], orient="row")
    det = det.with_columns((pl.col("QT_APTOS") - pl.col("QT_COMPARECIMENTO")).alias("QT_ABSTENCOES"),
                           pl.lit("Deputado Estadual").alias("DS_CARGO"))
    return vs.lazy(), det.lazy()


def test_detalhe_de_secoes_categorias() -> None:
    """Cada regra da reconstrução (iguais ao oficial nas 732 zonas × cargo do RJ 2022)."""
    votos, det = _secoes(
        [(1, "RJ", RIO, 4, 1, 7, 55123, 100),   # destinação Válido → nominal válido
         (1, "RJ", RIO, 4, 2, 7, 55123, 50),
         (1, "RJ", RIO, 4, 1, 7, 55789, 10),    # Anulado
         (1, "RJ", RIO, 4, 1, 7, 55999, 5),     # Anulado sub judice
         (1, "RJ", RIO, 4, 1, 7, 66111, 7),     # fora do candidato_munzona (negado antes da eleição) → nulo técnico
         (1, "RJ", RIO, 4, 1, 7, 55, 20),       # legenda de partido com candidato → válida
         (1, "RJ", RIO, 4, 2, 7, 77, 3),        # legenda de partido SEM candidato no cargo → nulo técnico
         (1, "RJ", RIO, 4, 1, 7, 95, 4), (1, "RJ", RIO, 4, 1, 7, 96, 6), (1, "RJ", RIO, 4, 2, 7, 97, 2),
         (1, "SP", SP, 1, 1, 1, 13, 30)],       # presidente: destinação nacional (a linha está no RJ)
        [(1, "RJ", RIO, 4, 1, 7, 300, 200, "31/10/2022 23:59:00"),
         (1, "RJ", RIO, 4, 2, 7, 100, 50, "01/11/2022 00:10:00"),   # virada do mês: a hora é a MAIOR data
         (1, "SP", SP, 1, 1, 1, 40, 30, "02/10/2022 18:00:00")])
    dest = _dest([(1, "RJ", 7, 55123, 55, "Válido"), (1, "RJ", 7, 55789, 55, "Anulado"),
                  (1, "RJ", 7, 55999, 55, "Anulado sub judice"), (1, "RJ", 1, 13, 13, "Válido")])
    d = h.detalhe_de_secoes(votos, det, dest)
    rj = d.filter(pl.col("SG_UF") == "RJ").row(0, named=True)
    assert (rj["QT_VOTOS_NOMINAIS_VALIDOS"], rj["QT_TOTAL_VOTOS_LEG_VALIDOS"], rj["QT_TOTAL_VOTOS_VALIDOS"]) == (150, 20, 170)
    assert (rj["QT_TOTAL_VOTOS_ANULADOS"], rj["QT_TOTAL_VOTOS_ANUL_SUBJUD"]) == (10, 5)
    assert (rj["QT_VOTOS_NULOS"], rj["QT_VOTOS_NULOS_TECNICOS"], rj["QT_TOTAL_VOTOS_NULOS"]) == (6, 10, 16)
    assert (rj["QT_VOTOS_BRANCOS"], rj["QT_VOTOS_ANULADOS_APU_SEP"], rj["QT_VOTOS"]) == (4, 2, 207)
    assert (rj["QT_APTOS"], rj["QT_COMPARECIMENTO"], rj["QT_ABSTENCOES"], rj["QT_TOTAL_SECOES"]) == (400, 250, 150, 2)
    assert (rj["DT_ULTIMA_TOTALIZACAO"], rj["HH_ULTIMA_TOTALIZACAO"], rj["CD_ELEICAO"]) == ("01/11/2022", "00:10:00", 546)
    sp = d.filter(pl.col("SG_UF") == "SP").row(0, named=True)
    assert sp["QT_TOTAL_VOTOS_VALIDOS"] == 30 and sp["QT_VOTOS_NULOS_TECNICOS"] == 0


def test_importar_com_totais_reconstruidos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sem_microdados: None) -> None:
    """Os totais reconstruídos alimentam as mesmas tabelas; o status.json marca o resultado como provisório."""
    votos, det = _secoes([(1, "RJ", RIO, 4, 1, 3, 22, 700), (1, "RJ", RIO, 4, 1, 3, 40, 300), (1, "RJ", RIO, 4, 1, 3, 96, 20)],
                         [(1, "RJ", RIO, 4, 1, 3, 1200, 1020, "02/10/2022 19:00:00")])
    dest = _dest([(1, "RJ", 3, 22, 22, "Válido"), (1, "RJ", 3, 40, 40, "Válido")])
    monkeypatch.setattr(h, "load_detalhe_secoes", lambda ano, uf, cache: h.detalhe_de_secoes(votos, det, dest))
    monkeypatch.setattr(h, "destinacao_oficial", lambda ano, cache: dest)
    monkeypatch.setattr(h, "load_votos", lambda ano, uf, cache: (_votos(VOTOS_UF), _votos(VOTOS_BR)))
    h.importar(2022, "RJ", 1, tmp_path, tmp_path / "r", totais_de="secoes")
    st = json.loads((tmp_path / "r" / "status.json").read_text())
    assert st["totais_de"] == "secoes" and "provisório" in st["totais"] and "totais provisórios" in st["ambiente"]
    assert "detalhe_votacao_munzona_2022" not in st["fontes"] and "detalhe_votacao_secao_2022" in st["fontes"]
    gov = pl.read_parquet(tmp_path / "r" / "ultimo" / "totais.parquet").filter(
        (pl.col("CARGO") == 3) & (pl.col("ABRANGENCIA") == "uf")).row(0, named=True)
    assert (gov["VALIDOS"], gov["NULOS"], gov["ELEITORADO"], gov["ABSTENCAO"]) == (1000, 20, 1200, 180)
    with pytest.raises(ValueError, match="secao"):
        h.importar(2022, "RJ", 1, tmp_path, tmp_path / "x", fonte="munzona", totais_de="secoes")
    with pytest.raises(ValueError, match="totais"):
        h.importar(2022, "RJ", 1, tmp_path, tmp_path / "x", totais_de="outro")


def test_conferir_totais() -> None:
    base = pl.DataFrame({"CARGO": [3, 3], "ABRANGENCIA": ["uf", "mun"], "UF": ["RJ", "RJ"], "CD_MUNICIPIO": [None, RIO],
                         "VALIDOS": [1000, 600], "NULOS": [20, 10]})
    oficial = base.with_columns(pl.when(pl.col("ABRANGENCIA") == "mun").then(pl.col("NULOS") + 2)
                                .otherwise(pl.col("NULOS")).alias("NULOS"))
    d = h.conferir_totais(base, oficial)
    assert d.height == 1 and d.row(0, named=True)["DIF_NULOS"] == 2 and d.row(0, named=True)["DIF_VALIDOS"] == 0
    assert h.conferir_totais(base, base).is_empty()


def test_destinacao_so_do_cache(tmp_path: Path) -> None:
    with pytest.raises(v.TseDataError, match="cache"):
        h.destinacao_oficial(2026, tmp_path)  # sem o ZIP: erro claro, nada de rede


def test_cadeiras_sem_partido_munzona_nao_repetem_o_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                            sem_microdados: None) -> None:
    """Eleição importada sem o votacao_partido_munzona (2026 antes da publicação): as cadeiras caem para o
    `ultimo/` e a falha fica memorizada (antes, cada pedido de cadeiras repetia o 404 na CDN)."""
    from apuracao import cadeiras as cd
    monkeypatch.setattr(h, "load_votos", lambda ano, uf, cache: (_votos(VOTOS_UF), _votos(VOTOS_BR)))
    monkeypatch.setattr(h, "fonte_padrao", lambda ano, uf, cache: "secao")
    destino = tmp_path / "historico_2022_t1"
    h.importar(2022, "RJ", 1, tmp_path, destino)
    tentativas = []

    def falha(*a, **k):
        tentativas.append(a)
        raise v.TseDataError("404 em votacao_partido_munzona_2022.zip")
    monkeypatch.setattr(cd, "entrada_munzona", falha)
    site = TestClient(create_app(destino, "RJ", tmp_path))
    for _ in range(3):
        r = site.get("/api/cadeiras?cargo=7")
        assert r.status_code == 200 and r.json()["fonte"] == "divulgação do TSE"
    assert len(tentativas) == 1


def test_cargo_sem_destinacao_publicada_conta_como_valido() -> None:
    """Presidente 2026 em 06/10: o candidato_munzona ainda sem nenhuma linha do cargo. Não é nulo técnico."""
    votos, det = _secoes([(1, "RJ", RIO, 4, 1, 1, 13, 40), (1, "RJ", RIO, 4, 1, 1, 22, 50), (1, "RJ", RIO, 4, 1, 1, 96, 5),
                          (1, "RJ", RIO, 4, 1, 3, 22, 30), (1, "RJ", RIO, 4, 1, 3, 99, 7)],
                         [(1, "RJ", RIO, 4, 1, 1, 100, 95, "02/10/2022 19:00:00"),
                          (1, "RJ", RIO, 4, 1, 3, 100, 37, "02/10/2022 19:00:00")])
    dest = _dest([(1, "RJ", 3, 22, 22, "Válido")])  # só governador publicado
    d = h.detalhe_de_secoes(votos, det, dest)
    pres = d.filter(pl.col("CD_CARGO") == 1).row(0, named=True)
    gov = d.filter(pl.col("CD_CARGO") == 3).row(0, named=True)
    assert (pres["QT_TOTAL_VOTOS_VALIDOS"], pres["QT_VOTOS_NULOS_TECNICOS"], pres["QT_TOTAL_VOTOS_NULOS"]) == (90, 0, 5)
    assert (gov["QT_TOTAL_VOTOS_VALIDOS"], gov["QT_VOTOS_NULOS_TECNICOS"]) == (30, 7)  # governador: regra normal
    assert h.cargos_sem_destinacao(dest, "RJ", 1, [1, 3]) == [1] and h.cargos_sem_destinacao(None, "RJ", 1, [3]) == [3]


def test_partido_soma_so_nominais_validos() -> None:
    """Voto em candidato anulado não é do partido (com a destinação oficial); sem ela, como antes: todos."""
    tot = h.totais(_detalhe(), "RJ", 1)
    dest = _dest([(1, "RJ", 7, 55123, 55, "Válido"), (1, "RJ", 7, 55456, 55, "Anulado")])
    _, part = h.candidatos_e_partidos(_votos(VOTOS_UF), _votos(VOTOS_BR), _cand(), tot, "RJ", 1, dest)
    _, sem = h.candidatos_e_partidos(_votos(VOTOS_UF), _votos(VOTOS_BR), _cand(), tot, "RJ", 1)
    uf = lambda p: p.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("NR_PARTIDO") == 55)).row(0, named=True)  # noqa: E731
    assert (uf(part)["VOTOS_NOMINAIS"], uf(part)["VOTOS_LEGENDA"], uf(part)["VOTOS_TOTAL"]) == (500, 40, 540)
    assert uf(sem)["VOTOS_NOMINAIS"] == 700


def test_agremiacao_da_federacao_e_formato_2026() -> None:
    """Rodada 41: federação sozinha tinha AGREMIACAO = "FEDERAÇÃO" (genérico); o cadastro de 2026 traz "13-PT/…"."""
    c = _cand().with_columns(
        pl.when(pl.col("NR_CANDIDATO").is_in(["55123", "55456"])).then(pl.lit("FEDERAÇÃO"))
        .otherwise(pl.col("NM_COLIGACAO")).alias("NM_COLIGACAO"),
        pl.when(pl.col("NR_CANDIDATO").is_in(["55123", "55456"])).then(pl.lit("55-PSD/10-REPUBLICANOS"))
        .otherwise(pl.col("SG_FEDERACAO")).alias("SG_FEDERACAO"))
    cad = h.cadastro(c, "RJ", 1).filter(pl.col("CARGO") == 7)
    assert set(cad["FEDERACAO"]) == {"PSD/REPUBLICANOS"} and set(cad["AGREMIACAO"]) == {"PSD/REPUBLICANOS"}
    gov = h.cadastro(_cand(), "RJ", 1).filter((pl.col("CARGO") == 3) & (pl.col("NUMERO") == 40)).row(0, named=True)
    assert gov["AGREMIACAO"] == "PSB"  # partido isolado: a sigla
