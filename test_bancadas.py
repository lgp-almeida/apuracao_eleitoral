"""Bancadas de deputado × eleição anterior (TODO 15, rodada 45) — offline."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from apuracao import bancadas as bc
from apuracao import comparacao as cp
from apuracao.web.app import create_app

COLS = ["CARGO", "NUMERO", "NOME_URNA", "NOME", "PARTIDO", "NR_PARTIDO", "VOTOS", "SITUACAO"]


def _fonte(ano: int, linhas: list[tuple]) -> cp.Fonte:
    c = pl.DataFrame(linhas, schema=COLS, orient="row").with_columns(
        pl.lit("uf").alias("ABRANGENCIA"), pl.lit("RJ").alias("UF"), pl.lit(None, pl.Int64).alias("CD_MUNICIPIO"),
        pl.lit(None, pl.String).alias("FEDERACAO"))
    vazio = pl.DataFrame()
    return cp.Fonte(ano=ano, totais=vazio, candidatos=c, partidos=vazio, municipios=vazio)


@pytest.fixture()
def fontes() -> tuple[cp.Fonte, cp.Fonte]:
    ref = _fonte(2022, [
        (7, 22111, "ANA", "Ana Reeleita", "PL", 22, 900, "Eleito por QP"),
        (7, 14000, "BIA", "Bia do PTB", "PTB", 14, 500, "Eleito por média"),     # PTB → PRD em 2026
        (7, 51000, "CAU", "Cau Patriota", "PATRIOTA", 51, 400, "Eleito por QP"),  # PATRIOTA → PRD
        (7, 13000, "DUDA", "Duda Saiu", "PT", 13, 300, "Eleito por QP"),          # não concorreu em 2026
        (6, 1300, "EVA", "Eva Federal", "PT", 13, 800, "Eleito por QP"),          # vira estadual em 2026
        (7, 55000, "FÁBIO", "Fabio Tentou", "PSD", 55, 100, "Suplente"),         # não se elegeu em 2022
    ])
    atual = _fonte(2026, [
        (7, 22222, "ANA", "ANA REELEITA", "PL", 22, 950, "Eleito por QP"),        # reeleita (nº mudou)
        (7, 25000, "BIA", "BIA DO PTB", "PRD", 25, 600, "Eleito por QP"),         # reeleita, agora no PRD
        (7, 13111, "EVA", "EVA FEDERAL", "PT", 13, 700, "Eleito por QP"),         # eleita antes para federal
        (7, 55555, "FÁBIO", "FABIO TENTOU", "PSD", 55, 650, "Eleito por média"),  # já tinha concorrido
        (7, 14123, "GIL", "Gil Missao", "MISSÃO", 14, 640, "Eleito por média"),   # novato no 14 reaproveitado
        (7, 51111, "CAU", "CAU PATRIOTA", "PRD", 25, 90, "Suplente"),             # concorreu e não se elegeu
    ])
    return atual, ref


def test_partidos_pela_entidade(fontes) -> None:
    b = bc.bancadas(*fontes, "RJ", 7)
    p = {r["PARTIDO"]: r for r in b.partidos.iter_rows(named=True)}
    assert (p["PRD"]["ELEITOS_ANTES"], p["PRD"]["ELEITOS_AGORA"], p["PRD"]["ANTES_COMO"]) == (2, 1, "PTB + PATRIOTA")
    assert (p["MISSÃO"]["ELEITOS_ANTES"], p["MISSÃO"]["ANTES_COMO"]) == (0, None)  # o 14 não herda o PTB
    assert p["PT"]["ELEITOS_ANTES"] == 1 and p["PT"]["VARIACAO"] == 0
    assert b.partidos["ELEITOS_ANTES"].sum() == 4 and b.partidos["ELEITOS_AGORA"].sum() == 5


def test_trajetorias_e_quem_saiu(fontes) -> None:
    b = bc.bancadas(*fontes, "RJ", 7)
    t = dict(b.eleitos.select("NOME_URNA", "TRAJETORIA").iter_rows())
    assert t == {"ANA": "reeleito", "BIA": "reeleito", "EVA": "eleito antes para outro cargo",
                 "FÁBIO": "já concorreu, sem se eleger", "GIL": "novato"}
    assert b.eleitos.filter(pl.col("NOME_URNA") == "EVA")["DETALHE"][0] == "Deputado Federal"
    s = dict(b.sairam.select("NOME_URNA", "DESTINO").iter_rows())
    assert s == {"DUDA": "não concorreu", "CAU": "concorreu de novo e não se elegeu: Suplente"}
    assert b.resumo["reeleito"] == 2 and b.resumo["nao_reeleitos"] == 2
    with pytest.raises(ValueError):
        bc.bancadas(*fontes, "RJ", 3)
    assert bc.planilha(b, "RJ")[:2] == b"PK"


def test_api(fontes, tmp_path: Path) -> None:
    def gravar(f: cp.Fonte, d: Path) -> Path:
        (d / "ultimo").mkdir(parents=True)
        f.candidatos.write_parquet(d / "ultimo" / "candidatos.parquet")
        pl.DataFrame({"CARGO": [7], "ABRANGENCIA": ["uf"], "UF": ["RJ"], "CD_MUNICIPIO": [None]},
                     schema_overrides={"CD_MUNICIPIO": pl.Int64}).write_parquet(d / "ultimo" / "totais.parquet")
        (d / "status.json").write_text(json.dumps({"ano": f.ano}))
        return d
    atual, ref = fontes
    site = TestClient(create_app(gravar(atual, tmp_path / "a"), "RJ", tmp_path, referencia=gravar(ref, tmp_path / "r")))
    d = site.get("/api/bancadas?cargo=7").json()
    assert (d["ano"], d["ano_ref"], d["resumo"]["novato"]) == (2026, 2022, 1) and len(d["eleitos"]) == 5
    r = site.get("/api/bancadas/planilha?cargo=7")
    assert r.status_code == 200 and r.content[:2] == b"PK" and "bancadas_7_RJ_2026x2022" in r.headers["content-disposition"]
    assert site.get("/api/bancadas?cargo=3").status_code == 400
    assert TestClient(create_app(tmp_path / "a", "RJ", tmp_path)).get("/api/bancadas?cargo=7").status_code == 404
