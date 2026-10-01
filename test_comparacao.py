"""Comparação por município entre duas eleições (2022 importado × coletor 2026) — offline."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from apuracao import comparacao as cp
from apuracao import historico as h
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import FakeTSE
from test_historico import NIT, RIO, VOTOS_BR, VOTOS_UF, _cand, _detalhe, _votos

IBGE_RIO, IBGE_NIT = 3304557, 3303302


@pytest.fixture()
def dirs(fake_tse: FakeTSE, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """(2022 importado dos microdados sintéticos, 2026 coletado do TSE falso)."""
    monkeypatch.setattr(h, "load_detalhe", lambda ano, cache: _detalhe())
    monkeypatch.setattr(h, "load_candidatos", lambda ano, cache: _cand())
    monkeypatch.setattr(h, "load_votos", lambda ano, uf, cache: (_votos(VOTOS_UF), _votos(VOTOS_BR)))
    monkeypatch.setattr(h, "municipios_tse_ibge", lambda uf, cache: pl.DataFrame(
        {"UF": ["RJ", "RJ"], "CD_MUNICIPIO": [RIO, NIT], "CD_MUNICIPIO_IBGE": [IBGE_RIO, IBGE_NIT],
         "NM_MUNICIPIO": ["RIO DE JANEIRO", "NITERÓI"], "CAPITAL": [True, False], "ZONAS": ["4,5", "71"]}))
    a = tmp_path / "historico_2022_t1"
    h.importar(2022, "RJ", 1, tmp_path, a)
    b = tmp_path / "simulado"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), b).ciclo()
    return a, b


def test_comparar_totais(dirs: tuple[Path, Path]) -> None:
    a, b = cp.carregar_fonte(dirs[0], 0), cp.carregar_fonte(dirs[1], 2026)
    assert (a.ano, b.ano) == (2022, 2026)
    d = cp.comparar(a, b, 3, "abstencao")
    uf = d.filter(pl.col("ABRANGENCIA") == "uf").row(0, named=True)
    assert uf["VALOR_A"] == pytest.approx(20.0)  # 2022 sintético: 360 de 1800
    assert uf["DIF"] == pytest.approx(uf["VALOR_B"] - uf["VALOR_A"])
    rio = d.filter(pl.col("CD_MUNICIPIO") == RIO).row(0, named=True)
    assert rio["CD_MUNICIPIO_IBGE"] == IBGE_RIO and rio["DIF"] is not None
    quissama = d.filter(pl.col("CD_MUNICIPIO") == 58009).row(0, named=True)  # só existe em 2026 nos dados
    assert quissama["VALOR_A"] is None and quissama["DIF"] is None and quissama["NM_MUNICIPIO"] == "QUISSAMÃ"
    ele = cp.comparar(a, b, 3, "eleitorado").filter(pl.col("ABRANGENCIA") == "uf").row(0, named=True)
    assert ele["DIF"] == pytest.approx(100 * (ele["VALOR_B"] - 1800) / 1800)  # variação %


def test_comparar_partido_e_candidato(dirs: tuple[Path, Path]) -> None:
    a, b = cp.carregar_fonte(dirs[0], 0), cp.carregar_fonte(dirs[1], 2026)
    ps = cp.partidos_disponiveis(a, b, 3)
    assert {"PL", "PSB"} <= set(ps["PARTIDO"]) and not ps.filter(pl.col("PARTIDO") == "PL")["NOS_DOIS"].item()
    pl_rio = cp.comparar(a, b, 3, "partido", partido="PL").filter(pl.col("CD_MUNICIPIO") == RIO).row(0, named=True)
    assert pl_rio["VALOR_A"] == pytest.approx(100 * 700 / 1050) and pl_rio["VALOR_B"] == 0.0  # ausente em 2026 = 0%
    cand = cp.comparar(a, b, 3, "candidato", numero_a=22, numero_b=66).filter(pl.col("ABRANGENCIA") == "uf").row(0, named=True)
    assert cand["VALOR_A"] == pytest.approx(60.0) and cand["VALOR_B"] > 0
    with pytest.raises(ValueError):
        cp.comparar(a, b, 3, "partido")


def test_api_comparacao(dirs: tuple[Path, Path], tmp_path: Path) -> None:
    site = TestClient(create_app(dirs[1], "RJ", tmp_path, referencia=dirs[0]))
    info = site.get("/api/comparacao/info").json()
    assert info["disponivel"] and (info["ano_a"], info["ano_b"]) == (2022, 2026) and 3 in info["cargos"]
    d = site.get("/api/comparacao?cargo=3&metrica=abstencao").json()
    assert d["unidade"] == "pp" and d["uf"]["VALOR_A"] == pytest.approx(20.0)
    assert set(d["itens"]) == {str(IBGE_RIO), str(IBGE_NIT), "3304151"}
    assert site.get("/api/comparacao?cargo=3&metrica=partido").status_code == 400
    assert site.get("/api/comparacao/partidos?cargo=7").status_code == 200
    sem_ref = TestClient(create_app(dirs[1], "RJ", tmp_path))
    assert not sem_ref.get("/api/comparacao/info").json()["disponivel"]
    assert sem_ref.get("/api/comparacao?cargo=3&metrica=abstencao").status_code == 404
