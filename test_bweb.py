"""Boletim de Urna (bweb) como terceira fonte dos totais e votos por partido reconstruídos (rodada 55) — offline.

BU sintético nos cabeçalhos REAIS de 2022 e 2026 (45 colunas; nomes que mudam entre os anos), a regra de
decisão por turno, a descoberta no CKAN e o SHA-512. Os goldens com os arquivos reais do RJ 2022 (marca
`dados`) só rodam com o cache local.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import polars as pl
import pytest
import requests

import votos_por_local_votacao as v
from apuracao import bweb
from apuracao import historico as h
from apuracao import microdados as md

RIO, NIT = 60011, 58653
CAB_2026 = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO", "CD_PLEITO", "DT_PLEITO",
            "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
            "NR_LOCAL_VOTACAO", "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA", "NR_PARTIDO", "SG_PARTIDO", "NM_PARTIDO",
            "DT_BU_RECEBIDO", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "CD_TIPO_URNA", "DS_TIPO_URNA",
            "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_URNA_EFETIVADA",
            "CD_CARGA_1_URNA_EFETIVADA", "CD_CARGA_2_URNA_EFETIVADA", "CD_FLASHCARD_URNA_EFETIVADA",
            "DT_CARGA_URNA_EFETIVADA", "DS_CARGO_PERGUNTA_SECAO", "DS_SECOES_AGREGADAS", "DT_ABERTURA",
            "DT_ENCERRAMENTO", "QT_ELEI_BIOM_SEM_HABILITACAO", "DT_EMISSAO_BU", "NR_JUNTA_APURADORA",
            "NR_TURMA_APURADORA"]
# 2022: os mesmos 45 campos, dois com outro nome
CAB_2022 = [{"DS_SECOES_AGREGADAS": "DS_AGREGADAS", "QT_ELEI_BIOM_SEM_HABILITACAO": "QT_ELEITORES_BIOMETRIA_NH"}.get(c, c)
            for c in CAB_2026]
CARGOS = {1: "Presidente", 3: "Governador", 7: "Deputado Estadual"}
TIPOS = {"Nominal": 1, "Branco": 2, "Nulo": 3, "Legenda": 4}

# seções: (uf, município, zona, seção, aptos, comparecimento, agregadas, tipo de urna)
SECOES = {
    ("RJ", RIO, 4, 1): (100, 80, "2 / 3", (1, "Apurada")),
    ("RJ", RIO, 5, 10): (50, 40, None, (2, "Contingência")),
    ("RJ", NIT, 71, 7): (30, 24, None, (1, "Apurada")),
    ("ZZ", 99999, 1, 1): (10, 9, None, (1, "Apurada")),
}
# votos: (seção, cargo, tipo, votável, votos)
VOTOS = [
    (("RJ", RIO, 4, 1), 3, "Nominal", 22, 40), (("RJ", RIO, 4, 1), 3, "Nominal", 40, 30),
    (("RJ", RIO, 4, 1), 3, "Branco", 95, 5), (("RJ", RIO, 4, 1), 3, "Nulo", 96, 5),
    (("RJ", RIO, 5, 10), 3, "Nominal", 22, 20), (("RJ", RIO, 5, 10), 3, "Nominal", 40, 15),
    (("RJ", RIO, 5, 10), 3, "Branco", 95, 3), (("RJ", RIO, 5, 10), 3, "Nulo", 96, 2),
    (("RJ", NIT, 71, 7), 3, "Nominal", 22, 10), (("RJ", NIT, 71, 7), 3, "Nominal", 40, 10),
    (("RJ", NIT, 71, 7), 3, "Branco", 95, 2), (("RJ", NIT, 71, 7), 3, "Nulo", 96, 2),
    (("RJ", RIO, 4, 1), 7, "Nominal", 55123, 30),   # Válido
    (("RJ", RIO, 4, 1), 7, "Nominal", 55456, 20),   # Anulado sub judice
    (("RJ", RIO, 4, 1), 7, "Nominal", 77777, 5),    # fora do candidato_munzona → nulo técnico
    (("RJ", RIO, 4, 1), 7, "Legenda", 55, 10),      # partido com candidato válido → legenda válida
    (("RJ", RIO, 4, 1), 7, "Legenda", 90, 5),       # partido sem candidato no cargo → nulo técnico
    (("RJ", RIO, 4, 1), 7, "Branco", 95, 5), (("RJ", RIO, 4, 1), 7, "Nulo", 96, 5),
    (("RJ", RIO, 4, 1), 1, "Nominal", 13, 50), (("RJ", RIO, 4, 1), 1, "Nominal", 22, 25),
    (("RJ", RIO, 4, 1), 1, "Branco", 95, 3), (("RJ", RIO, 4, 1), 1, "Nulo", 96, 2),
    (("ZZ", 99999, 1, 1), 1, "Nominal", 13, 5), (("ZZ", 99999, 1, 1), 1, "Nominal", 22, 4),
]
# destinação (candidato_munzona): (turno, uf, cargo, número, partido, destinação)
DESTINACAO = [(1, "RJ", 3, 22, 22, "Válido"), (1, "RJ", 3, 40, 40, "Válido"), (1, "RJ", 7, 55123, 55, "Válido"),
              (1, "RJ", 7, 55456, 55, "Anulado sub judice"), (1, "RJ", 1, 13, 13, "Válido"),
              (1, "RJ", 1, 22, 22, "Válido")]


def _linhas_bu(uf: str, ano: int, turno: int, votos: list[tuple] = VOTOS) -> list[dict[str, str]]:
    hora = "04/10/2026 18:46:02" if ano == 2022 else "2026-10-04 18:46:02"
    saida = []
    for secao, cargo, tipo, votavel, q in votos:
        if secao[0] != uf:
            continue
        aptos, comp, agregadas, (cd_urna, ds_urna) = SECOES[secao]
        saida.append({
            "ANO_ELEICAO": str(ano), "CD_TIPO_ELEICAO": "0", "NM_TIPO_ELEICAO": "Eleição Ordinária",
            "NR_TURNO": str(turno), "CD_ELEICAO": "545" if cargo == 1 else "546", "SG_UF": secao[0],
            "CD_MUNICIPIO": str(secao[1]), "NM_MUNICIPIO": "RIO DE JANEIRO", "NR_ZONA": str(secao[2]),
            "NR_SECAO": str(secao[3]), "NR_LOCAL_VOTACAO": "1015", "CD_CARGO_PERGUNTA": str(cargo),
            "DS_CARGO_PERGUNTA": CARGOS[cargo], "NR_PARTIDO": "-1" if tipo in ("Branco", "Nulo") else str(votavel)[:2],
            "SG_PARTIDO": "#NULO#", "DT_BU_RECEBIDO": hora, "QT_APTOS": str(aptos), "QT_COMPARECIMENTO": str(comp),
            "QT_ABSTENCOES": str(aptos - comp), "CD_TIPO_URNA": str(cd_urna), "DS_TIPO_URNA": ds_urna,
            "CD_TIPO_VOTAVEL": str(TIPOS[tipo]), "DS_TIPO_VOTAVEL": tipo, "NR_VOTAVEL": str(votavel),
            "NM_VOTAVEL": tipo.upper(), "QT_VOTOS": str(q), "DS_SECOES_AGREGADAS": agregadas or "#NULO#",
            "NR_JUNTA_APURADORA": "-1", "NR_TURMA_APURADORA": "-1"})
    return saida


def _zip_bu(destino: Path, linhas: list[dict[str, str]], cabecalho: list[str] = CAB_2026) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    renomear = dict(zip(CAB_2026, cabecalho))
    linhas = [{renomear.get(k, k): val for k, val in r.items()} for r in linhas]
    texto = "\n".join(";".join(f'"{r.get(c, "")}"' for c in cabecalho) for r in [dict(zip(cabecalho, cabecalho)), *linhas])
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(destino.with_suffix(".csv").name, (texto + "\n").encode("latin-1"))
        z.writestr("_leiame-boletimurnaweb.pdf", b"%PDF")
    return destino


def _no_cache(cache: Path, ano: int, turno: int, uf: str, linhas=None, cabecalho=CAB_2026,
              carimbo: str = "051020261403") -> Path:
    """Um BU no cache como `bweb.baixar` deixaria: ZIP + proveniência com o SHA conferido."""
    zp = _zip_bu(bweb.pasta(cache, ano) / f"bweb_{turno}t_{uf}_{carimbo}.zip",
                 _linhas_bu(uf, ano, turno) if linhas is None else linhas, cabecalho)
    sha = hashlib.sha512(zp.read_bytes()).hexdigest()
    zp.with_suffix(".proveniencia.json").write_text(json.dumps({"sha512": sha, "sha512_publicado": sha}))
    return zp


def _dest(rows: list[tuple] = DESTINACAO) -> pl.DataFrame:
    return pl.DataFrame([{"NR_TURNO": t, "SG_UF": uf, "CD_CARGO": c, "NUMERO": n, "NR_PARTIDO": p, "CD_ELEICAO": 546,
                          "DESTINACAO_TSE": d, "SITUACAO_TSE": None} for t, uf, c, n, p, d in rows],
                        schema=h._DESTINACAO_VAZIA)


# --------------------------------------------------------------------------
# Tradução (contrato com os loaders atuais)
# --------------------------------------------------------------------------
def test_esquemas_iguais_aos_das_fontes_atuais() -> None:
    assert list(bweb.ESQUEMA_VOTOS) == v.SECTION_VOTES_REQUIRED + v.SECTION_VOTES_OPTIONAL
    assert list(bweb.ESQUEMA_DETALHE)[:12] == v.SECTION_DETAILS_REQUIRED + v.SECTION_DETAILS_OPTIONAL
    for esquema in (bweb.ESQUEMA_VOTOS, bweb.ESQUEMA_DETALHE):  # inteiros do núcleo = Int64, o resto texto
        for c, t in esquema.items():
            assert t == (pl.Int64 if c in v.INT_COLUMNS or c.startswith("QT_") or c == "CD_ELEICAO" else pl.String), c


@pytest.mark.parametrize("cabecalho", [CAB_2026, CAB_2022], ids=["layout 2026", "layout 2022"])
def test_traducao_do_bu(tmp_path: Path, cabecalho: list[str]) -> None:
    zp = _no_cache(tmp_path, 2026, 1, "RJ", cabecalho=cabecalho)
    bu = bweb.ler(zp, "RJ")
    votos = bweb.votos_por_secao(bu)
    assert dict(votos.collect_schema()) == bweb.ESQUEMA_VOTOS
    vs = votos.collect()
    assert set(vs.filter(pl.col("DS_CARGO") == "GOVERNADOR")["NR_VOTAVEL"]) == {22, 40, 95, 96}
    assert vs["QT_VOTOS"].sum() == sum(q for s, *_, q in VOTOS if s[0] == "RJ")
    det = bweb.detalhe_por_secao(bu)
    assert dict(det.schema) == bweb.ESQUEMA_DETALHE
    gov = det.filter(pl.col("CD_CARGO") == 3).sort("NR_SECAO")
    # aptos UMA vez por seção × cargo (o BU repete em cada votável), agregadas contadas, hora no formato do detalhe
    assert gov["QT_APTOS"].to_list() == [100, 30, 50] and gov["QT_SECOES_AGREGADAS"].to_list() == [2, 0, 0]
    assert gov["DT_PRIM_TOT_PARCIAL_HOR_TSE"].unique().to_list() == ["04/10/2026 18:46:02"]
    r = bweb.verificar(bu)
    assert r["secoes"] == 3 and r["por_tipo_de_urna"] == {"1 Apurada": 2, "2 Contingência": 1}
    assert r["secoes_com_agregadas"] == 1 and r["chaves_duplicadas"] == 0


def test_aptos_diferentes_na_mesma_secao_e_votavel_repetido_sao_recusados(tmp_path: Path) -> None:
    linhas = _linhas_bu("RJ", 2026, 1)
    linhas[1]["QT_APTOS"] = "101"  # mesma seção × cargo de linhas[0]
    with pytest.raises(v.TseDataError, match="aptos"):
        bweb.detalhe_por_secao(bweb.ler(_zip_bu(tmp_path / "a" / "bweb_1t_RJ_051020261403.zip", linhas), "RJ"))
    duplicado = _linhas_bu("RJ", 2026, 1)
    duplicado.append(dict(duplicado[0]))  # urna substituída?
    with pytest.raises(v.TseDataError, match="repetido"):
        bweb.verificar(bweb.ler(_zip_bu(tmp_path / "b" / "bweb_1t_RJ_051020261403.zip", duplicado), "RJ"))


def test_tipo_de_votavel_desconhecido_para_a_traducao(tmp_path: Path) -> None:
    linhas = _linhas_bu("RJ", 2026, 1)
    linhas[0]["DS_TIPO_VOTAVEL"] = "Anulado em apuração separada"
    with pytest.raises(v.TseDataError, match="tipo de votável"):
        bweb.votos_por_secao(bweb.ler(_zip_bu(tmp_path / "bweb_1t_RJ_051020261403.zip", linhas), "RJ"))


def test_totais_do_bu_pela_mesma_classificacao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BU → `detalhe_de_secoes` sem regra nova: nominal válido, sub judice, nulo técnico (número fora da
    destinação e legenda de partido sem candidato), seções com as agregadas."""
    _no_cache(tmp_path, 2026, 1, "RJ")
    d = h.load_detalhe_bweb(2026, 1, "RJ", tmp_path, destinacao=_dest())
    dep = d.filter((pl.col("CD_CARGO") == 7) & (pl.col("NR_ZONA") == 4)).row(0, named=True)
    assert (dep["QT_VOTOS_NOMINAIS_VALIDOS"], dep["QT_TOTAL_VOTOS_LEG_VALIDOS"], dep["QT_TOTAL_VOTOS_ANUL_SUBJUD"]) == (30, 10, 20)
    assert (dep["QT_VOTOS_NULOS_TECNICOS"], dep["QT_VOTOS_NULOS"], dep["QT_VOTOS_BRANCOS"]) == (5 + 5, 5, 5)
    assert (dep["QT_APTOS"], dep["QT_TOTAL_SECOES"], dep["QT_VOTOS"], dep["CD_ELEICAO"]) == (100, 3, 80, 546)
    gov = d.filter(pl.col("CD_CARGO") == 3).sort("NR_ZONA")
    assert gov["QT_TOTAL_VOTOS_VALIDOS"].to_list() == [70, 35, 20] and gov["QT_TOTAL_SECOES"].to_list() == [3, 1, 1]
    # sem a destinação do turno (2º turno antes do candidato_munzona): nominais e legenda contam como válidos
    sem = h.load_detalhe_bweb(2026, 1, "RJ", tmp_path, destinacao=pl.DataFrame(schema=h._DESTINACAO_VAZIA))
    dep = sem.filter((pl.col("CD_CARGO") == 7)).row(0, named=True)
    assert (dep["QT_VOTOS_NOMINAIS_VALIDOS"], dep["QT_TOTAL_VOTOS_LEG_VALIDOS"]) == (55, 15)
    assert dep["CD_ELEICAO"] == 546  # o código vem do BU quando a destinação falta


def test_brasil_exige_todos_os_bus(tmp_path: Path) -> None:
    _no_cache(tmp_path, 2026, 1, "RJ")
    _no_cache(tmp_path, 2026, 1, "ZZ")
    with pytest.raises(v.TseDataError, match="fora do cache: AC"):
        h.load_votos_bweb(2026, 1, "RJ", tmp_path, brasil=True)
    uf, nacional = h.load_votos_bweb(2026, 1, "RJ", tmp_path)  # sem brasil: o "nacional" é só a UF
    assert set(nacional.collect()["SG_UF"]) == {"RJ"} and uf.collect()["SG_UF"].unique().to_list() == ["RJ"]


def test_importar_pelo_bu_tira_o_brasil(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_historico import _cand
    _no_cache(tmp_path, 2026, 1, "RJ")
    monkeypatch.setattr(h, "load_candidatos", lambda ano, cache: _cand())
    monkeypatch.setattr(h, "destinacao_oficial", lambda ano, cache: _dest())
    monkeypatch.setattr(h, "load_candidatos_zona", lambda ano, uf, cache: (_ for _ in ()).throw(v.TseDataError("x")))
    monkeypatch.setattr(h, "municipios_tse_ibge", lambda uf, cache: pl.DataFrame(
        {"UF": ["RJ"], "CD_MUNICIPIO": [RIO], "CD_MUNICIPIO_IBGE": [3304557], "NM_MUNICIPIO": ["RIO DE JANEIRO"],
         "CAPITAL": [True], "ZONAS": ["4,5"]}))
    h.importar(2026, "RJ", 1, tmp_path, tmp_path / "r", totais_de="bweb")
    st = json.loads((tmp_path / "r" / "status.json").read_text())
    assert st["totais_de"] == "bweb" and "(BU)" in st["ambiente"] and "Boletim de Urna" in st["totais"]
    assert any("abrangência Brasil" in a for a in st["avisos"]) and st["partidos_de"] is None
    assert any(f.startswith("bweb_1t_RJ_") for f in st["fontes"])
    tot = pl.read_parquet(tmp_path / "r" / "ultimo" / "totais.parquet")
    assert "br" not in tot["ABRANGENCIA"].to_list()
    gov = tot.filter((pl.col("CARGO") == 3) & (pl.col("ABRANGENCIA") == "uf")).row(0, named=True)
    assert (gov["VALIDOS"], gov["ELEITORADO"], gov["SECOES_TOTAL"]) == (125, 180, 5)
    with pytest.raises(ValueError, match="bweb"):
        h.importar(2026, "RJ", 1, tmp_path, tmp_path / "x", fonte="secao", totais_de="bweb")


# --------------------------------------------------------------------------
# votacao_partido_munzona reconstruído
# --------------------------------------------------------------------------
def _candidatos_zona(rows: list[tuple]) -> pl.DataFrame:
    """(município, zona, cargo, número, partido, votos, destinação)."""
    return pl.DataFrame([{"NR_TURNO": 1, "SG_UF": "RJ", "CD_MUNICIPIO": m, "CD_CARGO": c, "NR_ZONA": z,
                          "NM_MUNICIPIO": "RIO DE JANEIRO", "QT_VOTOS_NOMINAIS": q, "NR_CANDIDATO": n, "NR_PARTIDO": p,
                          "CD_ELEICAO": 546, "NM_TIPO_DESTINACAO_VOTOS": d, "DS_SIT_TOT_TURNO": None,
                          "SG_PARTIDO": "PSD", "NR_FEDERACAO": None, "DS_COMPOSICAO_FEDERACAO": None,
                          "DS_CARGO": "Deputado Estadual", "TP_AGREMIACAO": "Partido isolado", "NM_PARTIDO": None,
                          "NM_FEDERACAO": None, "SG_FEDERACAO": None, "SQ_COLIGACAO": 1, "NM_COLIGACAO": None,
                          "DS_COMPOSICAO_COLIGACAO": None} for m, z, c, n, p, q, d in rows])


def test_partidos_munzona_pela_destinacao(tmp_path: Path) -> None:
    cand = _candidatos_zona([(RIO, 4, 7, 55123, 55, 30, "Válido"), (RIO, 4, 7, 55456, 55, 20, "Anulado sub judice"),
                             (RIO, 4, 7, 55999, 55, 7, "Válido (legenda)"), (RIO, 4, 7, 55888, 55, 4, "Anulado"),
                             (RIO, 5, 7, 55123, 55, 0, "Válido")])  # zona sem voto: linha zerada, como o oficial
    _no_cache(tmp_path, 2026, 1, "RJ")
    leg = h.legenda_por_zona(h.load_votos_bweb(2026, 1, "RJ", tmp_path)[0])
    p = h.partidos_munzona(cand, leg, _dest(), 2026)
    assert dict(p.schema) == h.ESQUEMA_PARTIDO_MUNZONA
    assert p.select("CD_MUNICIPIO", "NR_ZONA", "NR_PARTIDO").rows() == [(RIO, 4, 55), (RIO, 5, 55)]  # 90: nulo técnico
    z4 = p.row(0, named=True)
    assert (z4["QT_VOTOS_NOMINAIS_VALIDOS"], z4["QT_VOTOS_NOM_CONVR_LEG_VALIDOS"], z4["QT_VOTOS_LEGENDA_VALIDOS"]) == (30, 7, 10)
    assert (z4["QT_TOTAL_VOTOS_LEG_VALIDOS"], z4["QT_VOTOS_NOMINAIS_ANUL_SUBJUD"], z4["QT_VOTOS_NOMINAIS_ANULADOS"]) == (17, 20, 4)
    assert z4["ST_VOTO_EM_TRANSITO"] is None and z4["SG_PARTIDO"] == "PSD" and z4["CD_TIPO_ELEICAO"] == 2
    assert p.row(1, named=True)["QT_TOTAL_VOTOS_LEG_VALIDOS"] == 0


def test_cadeiras_aceitam_os_partidos_reconstruidos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from apuracao import cadeiras as cd

    cand = _candidatos_zona([(RIO, 4, 7, 55123, 55, 300, "Válido"), (RIO, 4, 7, 44111, 44, 100, "Válido")])
    leg = pl.DataFrame({"NR_TURNO": [1], "SG_UF": ["RJ"], "CD_MUNICIPIO": [RIO], "NR_ZONA": [4], "CD_CARGO": [7],
                        "NR_VOTAVEL": [44], "QT_VOTOS": [50]})
    p = h.partidos_munzona(cand, leg, _dest([(1, "RJ", 7, 55123, 55, "Válido"), (1, "RJ", 7, 44111, 44, "Válido")]), 2026)
    pedidos: list[str] = []
    monkeypatch.setattr(v, "download", lambda spec, cache, *a: pedidos.append(spec.name) or tmp_path / "c.zip")
    monkeypatch.setattr(cd, "_ler_uf", lambda zp, uf, cols: cand.with_columns(
        pl.lit(2).alias("CD_TIPO_ELEICAO"), pl.col("NR_CANDIDATO").alias("SQ_CANDIDATO"),
        pl.col("NR_CANDIDATO").cast(pl.String).alias("NM_URNA_CANDIDATO"), pl.col("QT_VOTOS_NOMINAIS").alias(
            "QT_VOTOS_NOMINAIS_VALIDOS"), pl.lit("ELEITO").alias("DS_SIT_TOT_TURNO")).select(
        pl.col(cols).cast(pl.String)))
    agr, _, _, validos = cd.entrada_munzona(2026, "RJ", 7, tmp_path, partidos=p)
    assert pedidos == ["votacao_candidato_munzona_2026"]  # o oficial por partido NÃO é pedido
    assert validos == 450 and dict(agr.select("AGREMIACAO", "VOTOS").iter_rows()) == {"PSD": 450}


# --------------------------------------------------------------------------
# Regra de decisão por turno
# --------------------------------------------------------------------------
@pytest.mark.parametrize("com, turnos, bu, esperado", [
    (set(), {}, False, []),
    ({"candidatos"}, {}, True, ["bweb"]),
    ({"candidatos"}, {}, False, []),                                       # sem BU conferido
    (set(md.BASE_IMPORTAR | md.TOTAIS_DE_SECOES), {"votos": {1}, "detalhe_secao": {1}}, True, ["bweb"]),  # turno 2
    (set(md.BASE_IMPORTAR | md.TOTAIS_DE_SECOES), {"votos": {1, 2}, "detalhe_secao": {1, 2}}, True, ["secoes", "bweb"]),
    (set(md.BASE_IMPORTAR | md.TOTAIS_DE_SECOES) - {"candidato_munzona"}, {"votos": {2}, "detalhe_secao": {2}}, True, ["bweb"]),
    (set(md.BASE_IMPORTAR | md.TOTAIS_OFICIAIS | md.TOTAIS_DE_SECOES),
     {"votos": {2}, "detalhe_secao": {2}, "detalhe_munzona": {2}}, False, ["munzona", "secoes"]),
    (set(md.BASE_IMPORTAR | md.TOTAIS_OFICIAIS), {"detalhe_munzona": {1}}, False, []),  # oficial só do 1º turno
], ids=["nada", "so-bu", "bu-nao-conferido", "secoes-sem-o-turno", "secoes", "sem-destinacao", "oficial", "oficial-sem-o-turno"])
def test_niveis_do_turno_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, com, turnos, bu, esperado) -> None:
    monkeypatch.setattr(md, "turnos", lambda cache, ano, uf, chave: turnos.get(chave, set()))
    monkeypatch.setattr(bweb, "no_cache", lambda cache, ano, turno, uf: tmp_path if bu else None)
    assert md.niveis_disponiveis(tmp_path, 2026, "RJ", 2, com) == esperado


def test_politica_fixa_nunca_cai_para_outro_nivel() -> None:
    assert md.escolher_nivel(["secoes", "bweb"]) == "secoes"
    assert md.escolher_nivel([]) is None
    assert md.escolher_nivel(["munzona", "secoes", "bweb"], "bweb") == "bweb"
    with pytest.raises(md.PoliticaIndisponivel, match="munzona"):
        md.escolher_nivel(["secoes", "bweb"], "oficial")
    with pytest.raises(ValueError, match="política"):
        md.escolher_nivel(["secoes"], "melhor")


def test_atualizar_sobe_de_nivel_e_nunca_rebaixa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    import preparar_2026 as p26
    from apuracao.ufs import dir_uf

    importados: list[tuple[int, str]] = []

    def importar(a, totais_de, turno, memo=None):
        importados.append((turno, totais_de))
        d = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf)
        d.mkdir(parents=True, exist_ok=True)
        (d / "status.json").write_text(json.dumps({"ano": a.ano, "totais_de": totais_de}))
        return True
    disponivel: dict[int, list[str]] = {1: ["secoes", "bweb"], 2: ["bweb"]}
    monkeypatch.setattr(p26, "importar", importar)
    monkeypatch.setattr(md, "no_cache", lambda *a: set())
    monkeypatch.setattr(md, "niveis_disponiveis", lambda cache, ano, uf, turno, com=None: disponivel[turno])
    a = argparse.Namespace(ano=2026, uf="RJ", cache_dir=tmp_path, raiz=tmp_path / "d", saidas=tmp_path / "s",
                           politica_totais="auto", bweb_brasil=False)
    assert p26.atualizar(a) == {1: "secoes", 2: "bweb"} and importados == [(1, "secoes"), (2, "bweb")]
    importados.clear()
    disponivel[1] = ["bweb"]               # as seções somem do cache: não volta para o BU
    assert p26.atualizar(a) == {1: "secoes", 2: "bweb"} and importados == []
    assert p26.atualizar(a, {md.BWEB}) == {1: "secoes", 2: "bweb"} and importados == [(2, "bweb")]  # BU novo
    importados.clear()
    disponivel[2] = ["munzona", "bweb"]    # o oficial do 2º turno chega
    assert p26.atualizar(a)[2] == "munzona" and importados == [(2, "munzona")]
    importados.clear()
    a.politica_totais = "oficial"          # fixa e indisponível no 1º turno: erro registrado, nada importado
    assert p26.atualizar(a) == {1: "secoes", 2: "munzona"} and importados == []


# --------------------------------------------------------------------------
# CKAN, download e SHA-512
# --------------------------------------------------------------------------
class Sessao:
    """CKAN + CDN falsos: url → (status, corpo, Last-Modified)."""

    def __init__(self, recursos: list[str] | None = None, fora: bool = False) -> None:
        self.recursos, self.fora, self.arquivos = recursos or [], fora, {}
        self.pedidos: list[str] = []

    def _resp(self, url, **kw):
        from test_microdados import Resp
        self.pedidos.append(url)
        if self.fora:
            raise requests.ConnectionError("fora do ar")
        if url == bweb.CKAN:
            corpo = {"success": True, "result": {"resources": [{"url": u} for u in self.recursos]}}
            r = Resp(200, json.dumps(corpo).encode())
            r.json = lambda: corpo
            return r
        if url in self.arquivos:
            r = Resp(200, self.arquivos[url], "Mon, 05 Oct 2026 16:00:00 GMT")
            r.text = self.arquivos[url].decode("latin-1")
            return r
        return Resp(404)

    get = head = _resp


BASE_BU = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb"


def test_descobrir_escolhe_o_carimbo_mais_novo() -> None:
    s = Sessao([f"{BASE_BU}/bweb_1t_RJ_051020261403.zip", f"{BASE_BU}/bweb_1t_RJ_061020260900.zip",
                f"{BASE_BU}/bweb_1t_RJ_061020260900.zip.sha512", f"{BASE_BU}/bweb_2t_RJ_271020261000.zip",
                f"{BASE_BU}/bweb_1t_SP_051020261403.zip", "https://outra/coisa.pdf"])
    r = bweb.descobrir(2026, 1, "RJ", s)
    assert r.nome == "bweb_1t_RJ_061020260900.zip" and r.turno == 1 and r.carimbo.day == 6
    assert bweb.descobrir(2026, 2, "rj", s).nome == "bweb_2t_RJ_271020261000.zip"
    assert bweb.descobrir(2026, 2, "SP", s) is None
    assert bweb.descobrir(2026, 1, "RJ", Sessao(fora=True)) is None  # CKAN fora do ar: só aviso


def test_baixar_confere_o_sha512_e_troca_a_versao(tmp_path: Path) -> None:
    origem = _zip_bu(tmp_path / "origem" / "x.zip", _linhas_bu("RJ", 2026, 1)).read_bytes()
    s = Sessao([f"{BASE_BU}/bweb_1t_RJ_051020261403.zip"])
    url = f"{BASE_BU}/bweb_1t_RJ_051020261403.zip"
    s.arquivos[url] = origem
    s.arquivos[url + ".sha512"] = b"0" * 128 + b"  bweb_1t_RJ_051020261403.zip\n"  # divergente
    cache = tmp_path / "cache"
    with pytest.raises(v.TseDataError, match="SHA-512"):
        bweb.baixar(bweb.descobrir(2026, 1, "RJ", s), cache, s)
    assert bweb.no_cache(cache, 2026, 1, "RJ") is None and not list(bweb.pasta(cache, 2026).glob("*.zip"))
    s.arquivos[url + ".sha512"] = hashlib.sha512(origem).hexdigest().encode() + b"  bweb_1t_RJ_051020261403.zip\n"
    zp = bweb.baixar(bweb.descobrir(2026, 1, "RJ", s), cache, s)
    assert bweb.no_cache(cache, 2026, 1, "RJ") == zp
    n = len(s.pedidos)
    bweb.baixar(bweb.descobrir(2026, 1, "RJ", s), cache, s)  # já conferido: nada baixado
    assert [p for p in s.pedidos[n:] if p != bweb.CKAN] == []
    # versão nova (carimbo maior): a anterior e o Parquet dela saem
    bweb.ler(zp, "RJ")
    url2 = f"{BASE_BU}/bweb_1t_RJ_061020260900.zip"
    s.recursos.append(url2)
    s.arquivos[url2] = origem
    s.arquivos[url2 + ".sha512"] = s.arquivos[url + ".sha512"]
    novo = bweb.baixar(bweb.descobrir(2026, 1, "RJ", s), cache, s)
    assert sorted(p.name for p in bweb.pasta(cache, 2026).iterdir()) == [
        "bweb_1t_RJ_061020260900.proveniencia.json", "bweb_1t_RJ_061020260900.zip"]
    assert bweb.no_cache(cache, 2026, 1, "RJ") == novo


def test_bu_so_com_cabecalho_ou_sha_nao_conferido_nao_vale(tmp_path: Path) -> None:
    _no_cache(tmp_path, 2026, 1, "RJ", linhas=[])
    assert bweb.no_cache(tmp_path, 2026, 1, "RJ") is None  # só cabeçalho = não publicado
    zp = _no_cache(tmp_path, 2026, 2, "RJ")
    zp.with_suffix(".proveniencia.json").write_text(json.dumps({"sha512": "a", "sha512_publicado": "b"}))
    assert bweb.no_cache(tmp_path, 2026, 2, "RJ") is None


# --------------------------------------------------------------------------
# Goldens com os arquivos reais (RJ 2022): só com o cache local
# --------------------------------------------------------------------------
CACHE_REAL = Path("cache_tse")


def _golden_disponivel() -> bool:
    return all(bweb.no_cache(CACHE_REAL, 2022, t, "RJ") for t in (1, 2)) and all(
        (CACHE_REAL / f"{n}_2022.zip").exists() for n in ("detalhe_votacao_munzona", "votacao_partido_munzona",
                                                          "votacao_candidato_munzona", "consulta_cand"))


dados_rj_2022 = pytest.mark.skipif(not _golden_disponivel(), reason="BUs/microdados do RJ 2022 fora do cache")


@pytest.mark.dados
@dados_rj_2022
@pytest.mark.parametrize("turno", [1, 2])
def test_golden_totais_do_bu_iguais_ao_oficial_2022(turno: int) -> None:
    cols = ["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_TOTAL_SECOES", "QT_VOTOS", "QT_TOTAL_VOTOS_VALIDOS",
            "QT_VOTOS_NOMINAIS_VALIDOS", "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_BRANCOS", "QT_TOTAL_VOTOS_NULOS",
            "QT_VOTOS_NULOS_TECNICOS", "QT_TOTAL_VOTOS_ANULADOS", "QT_TOTAL_VOTOS_ANUL_SUBJUD"]
    k = ["NR_TURNO", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO"]
    of = (h.load_detalhe(2022, CACHE_REAL)
          .filter((pl.col("SG_UF") == "RJ") & (pl.col("CD_TIPO_ELEICAO") == "2") & (pl.col("NR_TURNO") == str(turno)))
          .select([pl.col(c).cast(pl.Int64) for c in k + cols]).group_by(k).agg(pl.all().sum()))
    bu = h.load_detalhe_bweb(2022, turno, "RJ", CACHE_REAL).filter(pl.col("SG_UF") == "RJ").select(k + cols)
    assert of.height == bu.height == {1: 915, 2: 183}[turno]
    j = of.join(bu, on=k, how="full", coalesce=True, suffix="_BU")
    assert all(j.filter(pl.col(c) != pl.col(f"{c}_BU")).is_empty() for c in cols)


@pytest.mark.dados
@dados_rj_2022
def test_golden_partidos_reconstruidos_iguais_ao_oficial_2022() -> None:
    import io
    with zipfile.ZipFile(CACHE_REAL / "votacao_partido_munzona_2022.zip") as z:  # o _BRASIL tem todas as UFs e o Presidente
        membro = next(n for n in z.namelist() if n.endswith("_BRASIL.csv"))
        of = pl.read_csv(io.BytesIO(z.read(membro).decode("latin-1").encode()), separator=";", infer_schema=False,
                         null_values=["#NULO#"])
    k, q = h._CHAVE_PARTIDO, h.QT_PARTIDO_MUNZONA
    of = (of.filter((pl.col("SG_UF") == "RJ") & (pl.col("CD_TIPO_ELEICAO") == "2"))
          .with_columns([pl.col(c).cast(pl.Int64) for c in k if c != "SG_UF"] + [pl.col(c).cast(pl.Int64) for c in q])
          .group_by(k).agg([pl.col(c).sum() for c in q]))  # soma o voto em trânsito (a reconstrução não separa)
    cand = h.load_candidatos_zona(2022, "RJ", CACHE_REAL)
    dest = h.destinacao_oficial(2022, CACHE_REAL)
    for votos in (h.load_votos(2022, "RJ", CACHE_REAL)[0],
                  pl.concat([h.load_votos_bweb(2022, t, "RJ", CACHE_REAL)[0] for t in (1, 2)])):
        r = h.partidos_munzona(cand, h.legenda_por_zona(votos), dest, 2022)
        j = of.join(r.select(k + q), on=k, how="full", coalesce=True, suffix="_R")
        assert of.height == r.height == 16836
        assert all(j.filter(pl.col(c).fill_null(-1) != pl.col(f"{c}_R").fill_null(-1)).is_empty() for c in q)
