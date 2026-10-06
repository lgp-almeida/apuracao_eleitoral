"""Perfil × voto por LOCAL de votação (setores censitários) e regressão múltipla — offline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient

from apuracao import bairros as br
from apuracao import perfil as pf
from apuracao import perfil_local as pfl
from apuracao.web.app import create_app
from conftest import CAND, download_sem_rede, escrever_bairros, escrever_setores

PEDRO, ESCOLA_X, CIEP, NITEROI = "3304557000401015", "3304557000401023", "3304557000401031", "3303302007101015"


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    download_sem_rede(monkeypatch)


@pytest.fixture()
def cache(tse_cache: Path) -> Path:
    escrever_bairros(tse_cache)
    escrever_setores(tse_cache)
    return tse_cache


# --------------------------------------------------------------------------- malha de setores
def test_setor_sem_municipio_sai_da_malha() -> None:
    import geopandas as gpd
    from shapely.geometry import box

    g = gpd.GeoDataFrame({"CD_SETOR": ["430000100000000", "431490205000001"], "CD_MUN": [None, "4314902"]},
                         geometry=[box(-53, -33, -52, -32), box(-51.3, -30.1, -51.2, -30.0)], crs="EPSG:4674")
    geo = pfl._pontos(g)  # a 1ª linha é como a Lagoa Mirim na malha do RS: sem CD_MUN
    assert geo["CD_SETOR"].to_list() == ["431490205000001"] and geo["CD_MUN"].to_list() == [4314902]
    assert -51.3 < geo["LON"][0] < -51.2 and -30.1 < geo["LAT"][0] < -30.0


# --------------------------------------------------------------------------- regressão múltipla
def test_regressao_recupera_os_efeitos() -> None:
    rng = np.random.default_rng(3)
    x1, x2 = rng.normal(10, 2, 200), rng.normal(50, 5, 200)
    y = 3 + 2 * x1 - 1 * x2  # sem ruído
    r = pf.regressao_multipla(y, {"a": x1, "b": x2})
    c = {k["indicador"]: k for k in r["coeficientes"]}
    # efeito por +1 desvio-padrão = coeficiente × dp do indicador
    assert c["a"]["efeito_pp_por_dp"] == pytest.approx(2 * x1.std()) and c["b"]["efeito_pp_por_dp"] == pytest.approx(-x2.std())
    assert r["r2"] == pytest.approx(1) and c["a"]["vif"] == pytest.approx(1, abs=0.1)


def test_colinearidade_aparece_no_vif() -> None:
    rng = np.random.default_rng(4)
    x1 = rng.normal(size=100)
    x2 = x1 + rng.normal(scale=0.1, size=100)  # quase o mesmo indicador
    y = x1 + rng.normal(size=100)
    r = pf.regressao_multipla(y, {"a": x1, "b": x2})
    assert all(k["vif"] > 50 for k in r["coeficientes"])


def test_regressao_com_dados_insuficientes() -> None:
    with pytest.raises(ValueError):
        pf.regressao_multipla([1, 2, 3], {"a": [1, 2, 3], "b": [3, 1, 2]})  # 3 unidades, 2 indicadores
    with pytest.raises(ValueError):
        pf.regressao_multipla(np.arange(10), {"a": np.ones(10)})  # sem variação


# --------------------------------------------------------------------------- setores → locais
def test_locais_com_unidade_que_comeca_pelo_municipio(cache: Path) -> None:
    loc = pfl.locais(2024, "RJ", cache)
    assert set(loc["UNIDADE"]) == {PEDRO, ESCOLA_X, CIEP, NITEROI}  # SP fora (outra UF)
    assert loc.filter(pl.col("UNIDADE") == NITEROI)["CD_MUN"][0] == 3303302


@pytest.mark.parametrize("metodo,esperado", [
    ("contem", {PEDRO: 1, ESCOLA_X: 1, CIEP: 1, NITEROI: 1}),
    ("raio", {PEDRO: 1, ESCOLA_X: 1, CIEP: 1, NITEROI: 1}),       # o setor rural está a ~13 km
    ("influencia", {PEDRO: 1, ESCOLA_X: 1, CIEP: 1, NITEROI: 2}),  # o rural vai para o local do mesmo município
    ("raio+contem", {PEDRO: 1, ESCOLA_X: 1, CIEP: 1, NITEROI: 1}),
])
def test_metodos_de_ligacao(cache: Path, metodo: str, esperado: dict[str, int]) -> None:
    lig = pfl.ligar("RJ", cache, pfl.locais(2024, "RJ", cache), metodo)
    assert dict(lig.group_by("UNIDADE").len().iter_rows()) == esperado


def test_raio_mais_contem_cobre_quem_nao_tem_setor_no_raio(cache: Path) -> None:
    loc = pfl.locais(2024, "RJ", cache)
    lig = pfl.ligar("RJ", cache, loc, "raio+contem", raio_m=10)  # raio minúsculo: ninguém no raio…
    assert set(lig["UNIDADE"]) == set(loc["UNIDADE"])             # …e o "contém" cobre todos


def test_agregar_indicadores_do_censo(cache: Path) -> None:
    st = pfl.setores("RJ", cache)
    ag = {r["UNIDADE"]: r for r in pfl.agregar(st, pfl.ligar("RJ", cache, pfl.locais(2024, "RJ", cache), "influencia"))
          .iter_rows(named=True)}
    p = ag[PEDRO]
    assert (p["renda_media"], p["renda_mediana"], p["densidade"], p["moradores_domicilio"]) == (8000, 6000, 25000, 2.5)
    assert p["pct_pretos_pardos"] == pytest.approx(40) and p["pct_favela"] == 0
    assert ag[ESCOLA_X]["pct_favela"] == 100 and ag[ESCOLA_X]["pct_pretos_pardos"] == pytest.approx(80)
    assert ag[CIEP]["pct_pretos_pardos"] is None  # sigilo: sem cor, nunca zero
    n = ag[NITEROI]  # urbano + rural: renda ponderada pelos responsáveis, densidade = moradores ÷ área somados
    assert n["pct_pretos_pardos"] == pytest.approx(100 * (50 + 150) / 500)  # rural com sigilo parcial fica fora
    assert n["renda_media"] == pytest.approx((5000 * 180 + 900 * 15) / 195) and n["densidade"] == pytest.approx(550 / 5.04)


# --------------------------------------------------------------------------- perfil × voto por local
@pytest.fixture()
def pv(cache: Path, monkeypatch: pytest.MonkeyPatch) -> pfl.PerfilVotoLocal:
    comp = br.ComparacaoBairros(br.Bairros("RJ", cache))
    monkeypatch.setattr(comp, "siglas", lambda ano: {55: "PSD"})
    return pfl.PerfilVotoLocal(comp)


def test_perfil_do_tse_por_local(pv: pfl.PerfilVotoLocal) -> None:
    p = {r["CD_BAIRRO"]: r for r in pv.perfil(2024).iter_rows(named=True)}
    assert p[PEDRO]["pct_superior"] == pytest.approx(100 * 100 / 180) and p[ESCOLA_X]["pct_sem_fundamental"] == 100
    assert p[NITEROI]["pct_superior"] == 100


def test_dispersao_e_regressao_por_local(pv: pfl.PerfilVotoLocal) -> None:
    y = pf.Alvo(2024, 13, numero=CAND)
    d = pv.dispersao(y, "renda_media", min_validos=0)
    pts = {r["CD_BAIRRO"]: r for r in d["pontos"].iter_rows(named=True)}
    assert set(pts) == {PEDRO, ESCOLA_X, CIEP, NITEROI}
    assert pts[PEDRO]["Y"] == pytest.approx(100 * 13 / 138) and pts[PEDRO]["X"] == 8000
    assert pts[PEDRO]["BAIRRO"] == "COLÉGIO PEDRO II — Rio de Janeiro"
    r = pv.regressao(y, ["pct_superior"], min_validos=0)
    assert r["n"] == 4 and r["unidade"] == "local" and r["coeficientes"][0]["rotulo"] == "% com superior completo"
    with pytest.raises(ValueError):
        pv.regressao(y, ["pct_superior", "renda_media"], min_validos=0)  # 4 locais não bastam para 2 indicadores
    assert "pct_favela" in pv.indicadores() and "pct_favela" not in pf.PerfilVoto.indicadores()
    assert {r["CD_MUN"] for r in pv.municipios().iter_rows(named=True)} == {3304557, 3303302}


# --------------------------------------------------------------------------- API
@pytest.fixture()
def site(cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    (cache / "malhas" / "municipios_RJ.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    monkeypatch.setattr(br.ComparacaoBairros, "siglas", lambda self, ano: {55: "PSD"})
    return TestClient(create_app(tmp_path / "dados", "RJ", cache))


def test_api_por_local(site: TestClient) -> None:
    info = site.get("/api/perfil/info?unidade=local").json()
    assert info["unidade"] == "local" and "pct_favela" in info["indicadores"] and len(info["municipios"]) == 2
    base = f"ano=2024&cargo=13&numero={CAND}&min_validos=0&unidade=local"
    d = site.get(f"/api/perfil/dispersao?{base}&x=pct_favela").json()
    assert len(d["pontos"]) == 4
    assert len(site.get(f"/api/perfil/correlacoes?{base}").json()["correlacoes"]) == 11
    r = site.get(f"/api/perfil/regressao?{base}&indicadores=pct_superior").json()
    assert r["n"] == 4 and r["coeficientes"][0]["indicador"] == "pct_superior"
    assert site.get(f"/api/perfil/regressao?{base}&indicadores=pct_superior,renda_media").status_code == 400
    assert site.get(f"/api/perfil/dispersao?{base.replace('local', 'setor')}&x=pct_superior").status_code == 400
    assert site.get("/api/perfil/info").json()["unidade"] == "bairro"  # padrão continua bairro


# --------------------------------------------------------------------------- mapa por local (rodada 32)
def test_mapa_por_local_tres_camadas(pv: pfl.PerfilVotoLocal) -> None:
    from apuracao import mapa_locais as ml
    d = ml.pontos(pv, 2024, "voto", cargo=13, metrica="pct_candidato", numero=CAND)
    pts = {p["u"]: p for p in d["itens"]}
    assert d["tipo"] == "sequencial" and set(pts) == {PEDRO, ESCOLA_X, CIEP, NITEROI}
    assert pts[PEDRO]["valor"] == pytest.approx(100 * 13 / 138) and pts[PEDRO]["eleitores"] > 0
    assert pts[PEDRO]["nome"] == "COLÉGIO PEDRO II" and pts[PEDRO]["lat"] and pts[PEDRO]["lon"]
    # o mesmo valor que a dispersão do Perfil × voto (a fonte é a mesma)
    disp = {r["CD_BAIRRO"]: r["Y"] for r in pv.dispersao(pf.Alvo(2024, 13, numero=CAND), "renda_media", 0)["pontos"].iter_rows(named=True)}
    assert all(pts[u]["valor"] == pytest.approx(y) for u, y in disp.items())
    so_rio = ml.pontos(pv, 2024, "voto", cargo=13, metrica="pct_candidato", numero=CAND, municipio=3304557)
    assert {p["u"] for p in so_rio["itens"]} == {PEDRO, ESCOLA_X, CIEP} and so_rio["cobertura"]["locais"] == 3
    venc = ml.pontos(pv, 2024, "voto", cargo=13, metrica="vencedor")
    assert venc["tipo"] == "categorico" and venc["categorias"] and all(p.get("rotulo") for p in venc["itens"])

    perfil = ml.pontos(pv, 2024, "perfil", indicador="renda_media")
    assert {p["u"]: p["valor"] for p in perfil["itens"]}[PEDRO] == 8000 and perfil["unidade"] == ""
    assert ml.pontos(pv, 2024, "perfil", indicador="pct_superior")["unidade"] == "%"

    res = ml.pontos(pv, 2024, "residuo", cargo=13, numero=CAND, indicador="renda_media", min_validos=0)
    assert res["tipo"] == "divergente" and res["unidade"] == "p.p." and res["estatistica"]["n"] == 4
    est = res["estatistica"]
    for p in res["itens"]:  # resíduo = voto − (a + b·indicador)
        assert p["valor"] == pytest.approx(p["voto"] - (est["a"] + est["b"] * p["indicador"]))
    assert sum(p["valor"] for p in res["itens"]) == pytest.approx(0, abs=1e-9)

    with pytest.raises(ValueError):
        ml.pontos(pv, 2024, "setor")
    with pytest.raises(ValueError):
        ml.pontos(pv, 2024, "residuo", cargo=13, indicador="renda_media")   # sem número
    with pytest.raises(ValueError):
        ml.pontos(pv, 2024, "voto", cargo=13, metrica="secoes_totalizadas_pct")


def test_numero_de_dois_digitos_em_proporcional_e_partido() -> None:
    from apuracao import mapa_locais as ml
    assert ml.alvo(2022, 7, 1, 22).partido == 22 and ml.alvo(2022, 7, 1, 22).numero is None
    assert ml.alvo(2022, 7, 1, 2212).numero == 2212 and ml.alvo(2022, 3, 1, 22).numero == 22


def test_api_mapa_por_local_e_exportacao(site: TestClient) -> None:
    d = site.get(f"/api/mapa/locais?ano=2024&camada=voto&cargo=13&metrica=pct_candidato&numero={CAND}").json()
    assert len(d["itens"]) == 4 and d["rotulo"].startswith("% dos válidos do candidato")
    assert site.get("/api/mapa/locais?ano=2024&camada=setor").status_code == 400
    assert site.get("/api/mapa/locais?ano=2030&camada=perfil&indicador=pct_superior").status_code == 404
    cores = {p["u"]: "#fd8d3c" for p in d["itens"]}
    r = site.post("/api/exportar/mapa", json={"formato": "svg", "camada": "locais", "ano": 2024, "titulo": "Locais",
                                               "cores": cores, "legenda": [["#fd8d3c", "faixa"]]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
    assert site.post("/api/exportar/mapa", json={"formato": "png", "camada": "locais", "titulo": "t",
                                                 "cores": {}, "legenda": []}).status_code == 400    # sem ano
