"""Perfil do eleitorado (TSE) e Censo 2022 (IBGE) × voto por bairro: estatística, fontes e API — offline."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient

import votos_por_local_votacao as v
from apuracao import bairros as br
from apuracao import perfil as pf
from apuracao.web.app import create_app
from conftest import BAIRRO_A, BAIRRO_B, CAND, download_sem_rede, escrever_bairros


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    download_sem_rede(monkeypatch)  # 2026 e tudo o que faltar no cache vira 404, sem ir ao TSE/IBGE


@pytest.fixture()
def perfil(tse_cache: Path, monkeypatch: pytest.MonkeyPatch) -> pf.PerfilVoto:
    escrever_bairros(tse_cache)
    comp = br.ComparacaoBairros(br.Bairros("RJ", tse_cache))
    monkeypatch.setattr(comp, "siglas", lambda ano: {55: "PSD", 22: "PL"})
    return pf.PerfilVoto(comp)


# --------------------------------------------------------------------------- estatística
def test_correlacao_reta_perfeita() -> None:
    x = np.arange(1, 11, dtype=float)
    e = pf.correlacao(x, 2 * x + 1)
    assert e["pearson"] == pytest.approx(1) and e["spearman"] == pytest.approx(1)
    assert (e["b"], e["a"], e["r2"]) == (pytest.approx(2), pytest.approx(1), pytest.approx(1))
    assert e["p"] == 0 and e["ic95"] is None  # |r| = 1: sem intervalo


def test_correlacao_confere_com_numpy_e_pandas() -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(size=300)
    y = 0.4 * x + rng.normal(size=300)
    e = pf.correlacao(x, y)
    assert e["pearson"] == pytest.approx(np.corrcoef(x, y)[0, 1])
    import pandas as pd
    assert e["spearman"] == pytest.approx(pd.Series(x).rank().corr(pd.Series(y).rank()))
    assert e["b"] == pytest.approx(np.polyfit(x, y, 1)[0])
    assert e["ic95"][0] < e["pearson"] < e["ic95"][1]
    # Spearman é invariante a transformação monotônica; Pearson não
    e2 = pf.correlacao(np.exp(x), y)
    assert e2["spearman"] == pytest.approx(e["spearman"]) and e2["pearson"] != pytest.approx(e["pearson"])


def test_p_valor_de_fisher() -> None:
    # r = 0,5 com n = 28: z = atanh(0,5)·√25 = 2,7465 → p bilateral = 0,0060
    assert pf._p_fisher(0.5, 28) == pytest.approx(math.erfc(math.atanh(0.5) * 5 / math.sqrt(2)))
    assert pf._p_fisher(0.5, 28) == pytest.approx(0.00602, abs=1e-4)
    assert pf._p_fisher(0.5, 3) is None


def test_correlacao_ponderada() -> None:
    rng = np.random.default_rng(1)
    x, y = rng.normal(size=50), rng.normal(size=50)
    igual = pf.correlacao(x, y, np.full(50, 3.0))
    assert igual["pearson"] == pytest.approx(pf.correlacao(x, y)["pearson"]) and igual["n_efetivo"] == pytest.approx(50)
    w = np.r_[np.full(5, 100.0), np.ones(45)]
    pond = pf.correlacao(x, y, w)
    assert pond["n_efetivo"] < 20  # poucos bairros grandes dominam: IC mais largo
    assert pond["ic95"][1] - pond["ic95"][0] > igual["ic95"][1] - igual["ic95"][0]


def test_correlacao_sem_dado_suficiente() -> None:
    assert pf.correlacao([1, 2, 3, 4], [1, 2, 3, 5])["pearson"] is None  # n < 5
    assert pf.correlacao([1, 1, 1, 1, 1], [1, 2, 3, 4, 5])["pearson"] is None  # X sem variação


# --------------------------------------------------------------------------- fontes
def test_censo_por_bairro(tse_cache: Path) -> None:
    c = {r["CD_BAIRRO"]: r for r in pf.censo_por_bairro("RJ", tse_cache).iter_rows(named=True)}
    assert set(c) == {BAIRRO_A, BAIRRO_B}  # só a UF pedida
    a, b = c[BAIRRO_A], c[BAIRRO_B]
    assert (a["renda_media"], a["renda_mediana"], a["densidade"], a["moradores_domicilio"]) == (8000.5, 6000, 5000, 2.5)
    assert a["pct_pretos_pardos"] == pytest.approx(40)  # (100 pretos + 300 pardos) / 1000
    assert b["densidade"] == 10000 and b["pct_pretos_pardos"] is None  # "X" = sigilo do IBGE
    # sexo e idade dos moradores (rodada 48); sigilo numa faixa → só essa faixa sem dado
    assert (a["pct_mulheres_censo"], a["pct_0_14_censo"], a["pct_15_24_censo"], a["pct_60_mais_censo"]) == (55, 15, 10, 25)
    assert b["pct_0_14_censo"] is None and b["pct_15_24_censo"] == 20 and b["pct_mulheres_censo"] == 50
    assert (tse_cache / "ibge_censo2022" / "censo_bairros_RJ.parquet").exists()
    # cache gravado antes de um indicador novo é refeito
    antigo = pl.read_parquet(tse_cache / "ibge_censo2022" / "censo_bairros_RJ.parquet").drop("pct_60_mais_censo")
    antigo.write_parquet(tse_cache / "ibge_censo2022" / "censo_bairros_RJ.parquet")
    assert "pct_60_mais_censo" in pf.censo_por_bairro("RJ", tse_cache).columns


def test_perfil_por_bairro(perfil: pf.PerfilVoto) -> None:
    p = {r["CD_BAIRRO"]: r for r in perfil.perfil(2024).iter_rows(named=True)}
    a, b = p[BAIRRO_A], p[BAIRRO_B]  # Niterói fica fora de qualquer bairro
    assert set(p) == {BAIRRO_A, BAIRRO_B} and (a["ELEITORES"], b["ELEITORES"]) == (180, 110)
    assert a["pct_superior"] == pytest.approx(100 * 100 / 180) and b["pct_sem_fundamental"] == pytest.approx(100 * 100 / 110)
    assert a["pct_16_24"] == pytest.approx(100 * 30 / 180) and b["pct_60_mais"] == pytest.approx(100 * 20 / 110)
    assert a["pct_mulheres"] == pytest.approx(100 * 130 / 180)


def test_perfil_2026_com_coluna_renomeada(tse_cache: Path) -> None:
    lf = pf.load_perfil(2026, "RJ", tse_cache)  # em 2026 a contagem se chama QT_ELEITORES
    assert lf.select(pl.col("QT_ELEITORES_PERFIL").sum()).collect().item() == 180


# --------------------------------------------------------------------------- voto
def test_ausencia_de_candidatura_nao_e_zero() -> None:
    vb = pl.DataFrame({"CD_BAIRRO": ["3304557001", "3304557001", "3303302001"], "NR_VOTAVEL": [22222, 55555, 22222],
                       "QT_VOTOS": [10, 5, 7], "NM_VOTAVEL": ["B", "F", "B"]})
    municipal = pf.voto_por_bairro(vb, pf.Alvo(2024, 13, partido=55))
    assert municipal["CD_BAIRRO"].to_list() == ["3304557001"]  # o 55 não concorreu no outro município
    estadual = pf.voto_por_bairro(vb, pf.Alvo(2022, 7, partido=55)).sort("CD_BAIRRO")
    assert estadual["VOTO"].to_list() == [0.0, pytest.approx(100 * 5 / 15)]  # candidatura estadual: 0% é dado real
    with pytest.raises(ValueError):
        pf.Alvo(2024, 13, numero=1, partido=2)
    with pytest.raises(ValueError):
        pf.Alvo(2024, 99, numero=1)


def test_dispersao_e_transferencia(perfil: pf.PerfilVoto) -> None:
    y = pf.Alvo(2024, 13, numero=CAND)
    d = perfil.dispersao(y, "pct_superior", min_validos=0)
    pts = {r["CD_BAIRRO"]: r for r in d["pontos"].iter_rows(named=True)}
    assert pts[BAIRRO_A]["X"] == pytest.approx(100 * 100 / 180) and pts[BAIRRO_A]["Y"] == pytest.approx(100 * 13 / 138)
    assert pts[BAIRRO_B]["Y"] == pytest.approx(100 * 16 / 51) and pts[BAIRRO_B]["BAIRRO"] == "Lapa Sintética — Rio de Janeiro"
    assert d["estatistica"]["pearson"] is None and d["acima"].is_empty()  # 2 bairros não bastam
    assert d["rotulo_y"] == f"% dos válidos — nº {CAND} FULANA DE TAL (Vereador 2024)"
    assert d["rotulo_x"] == "% com superior completo"
    assert perfil.dispersao(y, "pct_superior", min_validos=100)["pontos"]["CD_BAIRRO"].to_list() == [BAIRRO_A]
    assert perfil.dispersao(y, "renda_media", min_validos=0, municipio=3303302)["pontos"].is_empty()
    t = perfil.dispersao(y, pf.Alvo(2024, 13, partido=55), min_validos=0)  # transferência (aqui, mesmo ano)
    tx = dict(t["pontos"].select("CD_BAIRRO", "X").iter_rows())
    assert tx[BAIRRO_A] == pytest.approx(100 * 18 / 138) and t["rotulo_x"].startswith("% dos válidos — partido 55 PSD")
    censo = perfil.dispersao(y, "pct_pretos_pardos", min_validos=0)
    assert censo["pontos"]["CD_BAIRRO"].to_list() == [BAIRRO_A]  # B sob sigilo: fora
    with pytest.raises(ValueError):
        perfil.dispersao(y, "signo")


def test_correlacoes_listam_todos_os_indicadores(perfil: pf.PerfilVoto) -> None:
    c = perfil.correlacoes(pf.Alvo(2024, 13, numero=CAND), min_validos=0)
    assert {e["indicador"] for e in c} == set(pf.INDICADORES_TSE) | set(pf.INDICADORES_CENSO)
    assert all(e["fonte"].startswith(("TSE", "IBGE")) for e in c)


# --------------------------------------------------------------------------- API
@pytest.fixture()
def site(tse_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    escrever_bairros(tse_cache)
    (tse_cache / "malhas" / "municipios_RJ.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    monkeypatch.setattr(br.ComparacaoBairros, "siglas", lambda self, ano: {55: "PSD"})
    return TestClient(create_app(tmp_path / "dados", "RJ", tse_cache))


def test_api_perfil(site: TestClient) -> None:
    info = site.get("/api/perfil/info").json()
    assert info["anos"] == {"2024": [13]} and set(info["indicadores"]) >= {"pct_superior", "renda_media"}
    assert info["municipios"] == [{"CD_MUN": 3304557, "NM_MUN": "Rio de Janeiro", "BAIRROS": 2}]
    assert site.get("/api/perfil/candidatos?ano=2024&cargo=13").json()[0] == {"NUMERO": 22222, "NOME": "BELTRANO",
                                                                            "VOTOS": 155}
    assert site.get("/api/perfil/partidos?ano=2024&cargo=13").json()[0]["PARTIDO"] == 22
    base = f"ano=2024&cargo=13&numero={CAND}&min_validos=0"
    d = site.get(f"/api/perfil/dispersao?{base}&x=pct_superior").json()
    assert len(d["pontos"]) == 2 and d["estatistica"]["n"] == 2 and d["pontos"][0]["RESIDUO"] is None
    t = site.get(f"/api/perfil/dispersao?{base}&x=voto&x_ano=2024&x_cargo=13&x_numero={CAND}").json()
    assert all(p["X"] == p["Y"] for p in t["pontos"])  # o mesmo voto nos dois eixos
    c = site.get(f"/api/perfil/correlacoes?{base}").json()
    assert c["rotulo_y"].startswith("% dos válidos") and len(c["correlacoes"]) == len(pf.INDICADORES_TSE) + len(pf.INDICADORES_CENSO)
    assert site.get(f"/api/perfil/dispersao?{base}&x=voto").status_code == 400          # falta a outra eleição
    assert site.get(f"/api/perfil/dispersao?{base}&x=signo").status_code == 400
    assert site.get("/api/perfil/dispersao?ano=2024&cargo=13&x=pct_superior").status_code == 400  # sem alvo
    assert site.get("/api/perfil/dispersao?ano=2026&cargo=3&numero=22&x=pct_superior").status_code == 404


def test_pedidos_paralelos_nao_colidem_na_conversao(perfil: pf.PerfilVoto) -> None:
    """A página pede dispersão e correlações juntas; com o cache frio, as duas convertiam o mesmo ZIP."""
    from concurrent.futures import ThreadPoolExecutor

    y = pf.Alvo(2024, 13, numero=CAND)
    with ThreadPoolExecutor(6) as ex:
        feitos = [ex.submit(perfil.dispersao, y, k, 0) for k in ("pct_superior", "pct_mulheres", "renda_media")] + [
            ex.submit(perfil.correlacoes, y, 0) for _ in range(3)]
        resultados = [f.result() for f in feitos]  # sem exceção
    assert all(len(r) == len(pf.INDICADORES_TSE) + len(pf.INDICADORES_CENSO) for r in resultados[3:])


def test_numero_municipal_e_de_uma_pessoa_por_municipio(perfil: pf.PerfilVoto, monkeypatch: pytest.MonkeyPatch) -> None:
    vb = pl.DataFrame({"CD_BAIRRO": ["3304557001", "3303302001"], "NR_VOTAVEL": [22, 22], "QT_VOTOS": [10, 7],
                       "NM_VOTAVEL": ["FULANO (RIO)", "CICLANO (NITERÓI)"]})
    monkeypatch.setattr(perfil.b, "votos", lambda ano, cargo, turno: vb)
    todos = perfil.candidatos(2024, 11).row(0, named=True)
    assert (todos["NUMERO"], todos["VOTOS"]) == (22, 17) and todos["NOME"].startswith("2 candidatos diferentes")
    assert perfil.candidatos(2024, 11, municipio=3304557)["NOME"].to_list() == ["FULANO (RIO)"]
    alvo = pf.Alvo(2024, 11, numero=22)
    assert "2 candidatos diferentes" in perfil.rotulo(alvo) and "FULANO (RIO)" in perfil.rotulo(alvo, 3304557)
