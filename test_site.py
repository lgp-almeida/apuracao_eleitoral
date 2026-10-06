"""Site de apuração (FastAPI): rotas sobre os dados gravados pelo coletor — offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import CAND, FakeTSE

IBGE = {"60011": 3304557, "58653": 3303302, "58009": 3304151}


@pytest.fixture()
def site(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> TestClient:
    dados = tmp_path / "dados"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados).ciclo()
    malha = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": str(c)},
         "geometry": {"type": "Polygon", "coordinates": [[[-43, -22], [-43.1, -22], [-43.1, -22.1], [-43, -22]]]}}
        for c in IBGE.values()]}
    (tse_cache / "malhas").mkdir()
    (tse_cache / "malhas" / "municipios_RJ.geojson").write_text(json.dumps(malha))
    return TestClient(create_app(dados, "RJ", tse_cache))


def test_pagina_e_status(site: TestClient) -> None:
    assert "Apuração 2026" in site.get("/").text
    st = site.get("/api/status").json()
    assert st["tem_dados"] and st["coletor"]["ciclo_tse"] == "ele2026"
    assert {(p["ELEICAO"], p["ABRANGENCIA"]) for p in st["progresso"]} == {(21270, "br"), (21270, "uf"), (21272, "uf")}


def test_painel(site: TestClient) -> None:
    cartoes = site.get("/api/painel").json()["cartoes"]
    assert [(c["cargo"], c["abrangencia"]) for c in cartoes] == [
        (1, "BRASIL"), (1, "RJ"), (3, "RJ"), (5, "RJ"), (6, "RJ"), (7, "RJ")]
    gov = cartoes[2]
    assert gov["totais"]["ELEITORADO"] == 13319487 and not gov["proporcional"]
    assert gov["candidatos"][0]["VOTOS"] >= gov["candidatos"][1]["VOTOS"]
    assert "Anulado sub judice" in {c["DESTINACAO"] for c in gov["candidatos"]}
    assert cartoes[3]["totais"]["VAGAS"] == 2
    assert cartoes[5]["proporcional"] and cartoes[5]["partidos"]


def test_presidente_por_uf(site: TestClient, tmp_path: Path) -> None:
    d = site.get("/api/presidente/ufs").json()
    assert [u["uf"] for u in d["ufs"]] == ["RJ", "SP"] and len(d["candidatos"]) == 3
    sp = d["ufs"][1]
    assert sp["cd_ibge"] == 35 and sp["pct_secoes"] == 100
    assert sp["primeiro"]["pct"] >= sp["segundo"]["pct"]
    assert sp["diferenca_pp"] == pytest.approx(sp["primeiro"]["pct"] - sp["segundo"]["pct"], abs=0.01)
    assert set(sp["pct"]) == {str(c["NUMERO"]) for c in d["candidatos"]}
    # hint do mapa: todos os candidatos, em ordem de votos, e os não válidos do TSE
    votos = [c["votos"] for c in sp["candidatos"]]
    assert len(sp["candidatos"]) > 3 and votos == sorted(votos, reverse=True)
    assert sp["candidatos"][0]["numero"] == sp["primeiro"]["numero"]
    import polars as pl
    t = pl.read_parquet(tmp_path / "dados" / "ultimo" / "brasil_totais.parquet").filter(pl.col("UF") == "SP").row(0, named=True)
    for k in ("brancos", "pct_brancos", "nulos", "pct_nulos", "abstencao", "pct_abstencao", "comparecimento"):
        assert sp[k] is not None and sp[k] == t[k.upper()], k


def test_presidente_por_uf_exterior_por_ultimo() -> None:
    import polars as pl
    from apuracao.divulgacao import modelo as m
    from apuracao.web.app import presidente_por_uf
    tot = pl.DataFrame([{"CARGO": 1, "ABRANGENCIA": "uf", "UF": u, "PCT_SECOES_TOTALIZADAS": p, "VALIDOS": v}
                        for u, p, v in (("ZZ", 10.0, 100), ("AC", 0.0, 0), ("BA", 50.0, 300))],
                       schema=m.TOTAIS_SCHEMA)
    cand = pl.DataFrame([{"CARGO": 1, "ABRANGENCIA": "uf", "UF": u, "NUMERO": n, "NOME_URNA": f"C{n}", "VOTOS": v,
                          "PCT_VALIDOS": 100 * v / t if t else 0.0, "SEQ": s}
                         for u, t in (("ZZ", 100), ("AC", 0), ("BA", 300))
                         for n, v, s in ((10, {"ZZ": 30, "AC": 0, "BA": 200}[u], 1),
                                         (20, {"ZZ": 70, "AC": 0, "BA": 100}[u], 2))],
                        schema=m.CANDIDATOS_SCHEMA)
    d = presidente_por_uf(tot, cand)
    assert [u["uf"] for u in d["ufs"]] == ["AC", "BA", "ZZ"] and d["ufs"][2]["nome"] == "Exterior"
    assert d["ufs"][0]["primeiro"] is None and d["ufs"][0]["diferenca_pp"] is None   # AC sem apuração
    assert d["ufs"][1]["primeiro"]["numero"] == 10 and d["ufs"][2]["primeiro"]["numero"] == 20
    assert [c["NUMERO"] for c in d["candidatos"]] == [10, 20]                          # 230 × 170 votos
    assert [c["numero"] for c in d["ufs"][2]["candidatos"]] == [20, 10]                # exterior: 70 × 30


def test_candidato(site: TestClient) -> None:
    lista = site.get("/api/candidatos?cargo=3").json()
    numero = lista[0]["NUMERO"]
    d = site.get(f"/api/candidato?cargo=3&numero={numero}").json()
    assert d["posicao_uf"] == 1 and len(d["municipios"]) == 3
    assert {m["CD_MUNICIPIO_IBGE"] for m in d["municipios"]} == set(IBGE.values())
    assert all(m["POSICAO_MUN"] >= 1 for m in d["municipios"])
    assert site.get("/api/candidato?cargo=3&numero=1").status_code == 404
    pres = site.get(f"/api/candidato?cargo=1&numero={site.get('/api/candidatos?cargo=1').json()[0]['NUMERO']}").json()
    assert "brasil" in pres


def test_mapas(site: TestClient) -> None:
    ab = site.get("/api/mapa?cargo=3&metrica=abstencao_pct").json()
    assert set(ab["itens"]) == {str(c) for c in IBGE.values()} and ab["tipo"] == "sequencial"
    venc = site.get("/api/mapa?cargo=3&metrica=vencedor").json()
    assert venc["tipo"] == "categorico" and venc["categorias"]
    numero = site.get("/api/candidatos?cargo=7").json()[0]["NUMERO"]
    assert site.get(f"/api/mapa?cargo=7&metrica=pct_candidato&numero={numero}").json()["itens"]
    assert site.get("/api/mapa?cargo=7&metrica=pct_candidato").status_code == 400
    assert site.get("/api/mapa?cargo=7&metrica=inventada").status_code == 400


def test_camadas_geograficas(site: TestClient) -> None:
    assert len(site.get("/geo/municipios.geojson").json()["features"]) == 3  # do cache, sem rede
    locais = site.get("/geo/locais.geojson?ano=2026").json()["features"]
    nomes = {f["properties"]["nome"] for f in locais}
    assert "CRECHE NOVA" not in nomes  # sem coordenadas no cadastro
    assert {"COLEGIO PEDRO II", "ESCOLA X RENOVADA"} <= nomes


def test_planilha_pelo_site(site: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    r = site.get(f"/api/planilha?ano=2024&cargo=vereador&numero={CAND}&municipio=Rio de Janeiro")
    assert r.status_code == 200 and r.content[:2] == b"PK"  # xlsx é um zip
    assert site.get(f"/api/planilha?ano=2024&cargo=vereador&numero={CAND}").status_code == 400  # nº ambíguo
    assert not list((tmp_path / "tmp").iterdir())  # nada sobra no temporário, com ou sem erro


def test_site_na_rede_so_atende_consultas_pesadas_da_propria_maquina(tse_cache: Path, tmp_path: Path) -> None:
    """--host 0.0.0.0 não tem senha: quem está na rede vê o painel, mas não dispara downloads de
    centenas de MB nem conversões que disputariam a máquina com o coletor na noite da eleição."""
    from apuracao.web.app import eh_loopback
    app = create_app(tmp_path / "dados", "RJ", tse_cache, pesadas_so_local=True)
    de_fora = TestClient(app, client=("192.168.0.20", 5000))
    assert de_fora.get("/api/status").status_code == 200 and de_fora.get("/").status_code == 200
    for rota in ("/api/planilha?ano=2024&cargo=vereador&numero=1", "/api/perfil/info", "/geo/locais.geojson",
                 "/api/mapa/bairros?ano=2024&cargo=13&metrica=abstencao"):
        assert de_fora.get(rota).status_code == 403, rota
    # a própria máquina passa (rota pesada que responde sem ir à rede: camada inválida = 400, não 403)
    assert TestClient(app, client=("127.0.0.1", 5000)).get("/api/mapa/locais?ano=2024&camada=x").status_code == 400
    assert de_fora.get("/api/mapa/locais?ano=2024&camada=x").status_code == 403
    assert eh_loopback("::1") and eh_loopback("localhost") and not eh_loopback("0.0.0.0")


def test_pagina_sem_cache(site: TestClient) -> None:
    """A página, o JS e o CSS são revalidados a cada carga (senão o navegador mostra a versão antiga do site)."""
    for caminho in ("/", "/app.js", "/style.css"):
        assert site.get(caminho).headers["cache-control"] == "no-cache"


# --------------------------------------------------------------------------
# Site com várias UFs (rodada 39): o app de cada UF montado em /<uf>/
# --------------------------------------------------------------------------
@pytest.fixture()
def multi(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> TestClient:
    import shutil

    from apuracao.web.multi import EntradaUF, create_multi_app

    rj = tmp_path / "oficial_RJ"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), rj).ciclo()
    shutil.copytree(rj, tmp_path / "oficial_AC")  # outra UF: os mesmos arquivos bastam para o roteamento
    entradas = [EntradaUF("RJ", rj), EntradaUF("AC", tmp_path / "oficial_AC"), EntradaUF("SP", tmp_path / "oficial_SP")]
    app = create_multi_app(entradas, "rj", lambda e: create_app(e.dados, e.uf, tse_cache, pesadas_so_local=True))
    return TestClient(app, follow_redirects=False)


def test_multi_ufs_rotas(multi: TestClient) -> None:
    d = multi.get("/ufs.json").json()
    assert d["padrao"] == "RJ" and [(u["uf"], u["disponivel"]) for u in d["ufs"]] == [
        ("RJ", True), ("AC", True), ("SP", False)]
    assert d["ufs"][1]["nome"] == "Acre" and d["ufs"][1]["url"] == "ac/"
    assert multi.get("/").headers["location"] == "/rj/"
    assert multi.get("/ac").headers["location"] == "/ac/"
    assert multi.get("/xx").headers["location"] == "/rj/"  # UF sem dados ou inexistente: a padrão
    assert multi.get("/ac/").status_code == 200 and "seletor-uf" in multi.get("/ac/").text
    assert multi.get("/ac/api/status").json()["uf"] == "AC" and multi.get("/rj/api/status").json()["uf"] == "RJ"
    assert multi.get("/sp/api/status").status_code == 404


def test_multi_ufs_regras_por_rota(multi: TestClient) -> None:
    # as regras de cada app valem para o caminho DENTRO dele (sem o /<uf>): rota pesada só na própria máquina
    # (o TestClient não é loopback) e página sem cache, API sem o cabeçalho
    assert multi.get("/rj/api/planilha?ano=2022&cargo=governador&numero=22").status_code == 403
    assert multi.get("/ac/api/status").status_code == 200
    assert multi.get("/ac/").headers["cache-control"] == "no-cache"
    assert "cache-control" not in multi.get("/ac/api/status").headers


def test_multi_ufs_sem_dados(tmp_path: Path, tse_cache: Path) -> None:
    from apuracao.web.multi import EntradaUF, create_multi_app

    with pytest.raises(ValueError, match="nenhuma"):
        create_multi_app([EntradaUF("SP", tmp_path / "x")], "SP", lambda e: create_app(e.dados, e.uf, tse_cache))


def test_multi_ufs_comeca_vazio_e_monta_uf_nova(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> None:
    """Rodada 43: no 2º turno as pastas começam vazias; o site sobe e monta a UF quando ela ganha dados,
    chamando `ao_montar` (serviços da UF) — sem reiniciar."""
    from apuracao.web.multi import EntradaUF, create_multi_app

    rj = tmp_path / "oficial_t2_RJ"
    montadas: list[str] = []
    app = create_multi_app([EntradaUF("RJ", rj)], "rj", lambda e: create_app(e.dados, e.uf, tse_cache),
                           ao_montar=lambda e, a: montadas.append(e.uf), permitir_vazio=True)
    c = TestClient(app, follow_redirects=False)
    assert c.get("/").status_code == 200 and "Aguardando" in c.get("/").text
    assert c.get("/ufs.json").json()["padrao"] is None and montadas == []
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), rj).ciclo()  # 1º ciclo
    assert c.get("/ufs.json").json()["padrao"] == "RJ" and montadas == ["RJ"]
    assert c.get("/").headers["location"] == "/rj/" and c.get("/rj/api/status").json()["uf"] == "RJ"
    c.get("/ufs.json")
    assert montadas == ["RJ"]  # montada uma vez só


def test_servicos_por_uf(tmp_path: Path) -> None:
    """Uma thread percorre as UFs: cada serviço no seu período; o erro de uma UF não para as outras."""
    from types import SimpleNamespace

    from apuracao.web.multi import EntradaUF
    from apuracao.web.servicos import PERIODOS_S, ServicosUFs

    chamadas: list[tuple[str, str]] = []

    class Falso:
        def __init__(self, uf: str, tipo: str, falha: bool = False) -> None:
            self.uf, self.tipo, self.falha = uf, tipo, falha

        def verificar(self) -> None:
            chamadas.append((self.uf, self.tipo))
            if self.falha:
                raise RuntimeError("disco cheio")

    sv = ServicosUFs(boletim=False, copia=False, alertas=True)
    sv.registrar(EntradaUF("RJ", tmp_path / "rj"), SimpleNamespace(state=SimpleNamespace(vigia=Falso("RJ", "alertas", True))))
    sv.registrar(EntradaUF("SP", tmp_path / "sp"), SimpleNamespace(state=SimpleNamespace(vigia=Falso("SP", "alertas"))))
    sv.itens["SP"]["copia"] = Falso("SP", "copia")
    ultimo: dict[str, float] = {}
    sv.passo(0.0, ultimo)
    assert chamadas == [("RJ", "alertas"), ("SP", "alertas"), ("SP", "copia")]  # o erro do RJ não parou o SP
    chamadas.clear()
    sv.passo(PERIODOS_S["alertas"], ultimo)          # 15 s depois: só os alertas
    assert chamadas == [("RJ", "alertas"), ("SP", "alertas")]
    chamadas.clear()
    sv.passo(PERIODOS_S["copia"], ultimo)            # 60 s: alertas e cópia
    assert ("SP", "copia") in chamadas
    rj = tmp_path / "oficial_RJ"
    rj.mkdir()
    com_copia = ServicosUFs(boletim=False, copia=True, copia_base=rj / "dentro", alertas=False)
    com_copia.registrar(EntradaUF("RJ", rj), SimpleNamespace(state=SimpleNamespace()))
    assert "copia" not in com_copia.itens["RJ"]  # cópia dentro da pasta de dados: recusada, sem derrubar nada
