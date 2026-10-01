"""Exportação do mapa (PNG/SVG/JPEG) e mapa por bairro (malha IBGE + microdados) — offline."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

import votos_por_local_votacao as v
from apuracao import bairros as br
from apuracao.web import exportar as ex
from apuracao.web.app import create_app
from conftest import BAIRRO_A, BAIRRO_B, CAND, download_sem_rede, escrever_bairros

MAGICOS = {"png": b"\x89PNG", "jpeg": b"\xff\xd8\xff", "svg": b"<?xml"}


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    download_sem_rede(monkeypatch)  # 2026 (e o que faltar no cache) vira 404 sem tocar no TSE


# --------------------------------------------------------------------------- exportar
def _geo() -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": str(c)},
         "geometry": {"type": "Polygon", "coordinates": [[[-43 - i, -22], [-43.5 - i, -22], [-43.5 - i, -22.5], [-43 - i, -22]]]}}
        for i, c in enumerate((1, 2))]}


@pytest.mark.parametrize("formato", ["png", "svg", "jpeg"])
def test_renderizar_formatos(formato: str) -> None:
    pedido = ex.PedidoMapa(formato=formato, titulo="Título — acentuação ç", cores={"1": "#2a78d6"},
                           legenda=[("#2a78d6", "faixa"), ("#f0efec", "sem dado")], fonte="Fonte: TSE")
    conteudo = ex.renderizar(_geo(), "codarea", pedido)
    assert conteudo.startswith(MAGICOS[formato])
    if formato == "svg":
        texto = conteudo.decode()
        assert "Título — acentuação ç" in texto and "sem dado" in texto  # texto editável, não contornos
        assert "#2a78d6" in texto.lower()                                # a cor da página chega ao arquivo


@pytest.mark.parametrize("campo,valor", [
    ("formato", "gif"), ("cores", {"1": "red; drop"}), ("legenda", [("#fff", "x" * 400)]), ("dpi", 5000),
    ("fundo", "url(javascript:1)"),
])
def test_validacao(campo: str, valor: object) -> None:
    base = dict(formato="png", titulo="t", cores={"1": "#123456"}, legenda=[("#123456", "a")])
    base[campo] = valor
    with pytest.raises(ex.PedidoInvalido):
        ex.renderizar(_geo(), "codarea", ex.PedidoMapa(**base))


# --------------------------------------------------------------------------- bairros (puro)
def _bairros(tse_cache: Path) -> br.Bairros:
    escrever_bairros(tse_cache)
    return br.Bairros("RJ", tse_cache)


def test_locais_caem_no_bairro_certo(tse_cache: Path) -> None:
    b = _bairros(tse_cache)
    lb = b.local_bairro(2024)
    por_local = dict(zip(lb["NR_LOCAL_VOTACAO"].to_list(), lb["CD_BAIRRO"].to_list()))
    assert por_local == {1015: BAIRRO_A, 1023: BAIRRO_B, 1031: BAIRRO_B}  # Niterói fora de qualquer bairro


def test_metricas_por_bairro(tse_cache: Path) -> None:
    b = _bairros(tse_cache)
    vb = b.votos(2024, 13, 1)
    pct = dict(br.metrica(vb, 13, "pct_candidato", CAND).iter_rows())
    # A: candidato 13 de 138 válidos (nominais 13+120 + legenda 5); B: 16 de 51
    assert pct[BAIRRO_A] == pytest.approx(100 * 13 / 138) and pct[BAIRRO_B] == pytest.approx(100 * 16 / 51)
    votos = dict(br.metrica(vb, 13, "votos_candidato", CAND).iter_rows())
    assert (votos[BAIRRO_A], votos[BAIRRO_B]) == (13, 16)
    venc = {r["CD_BAIRRO"]: r for r in br.metrica(vb, 13, "vencedor").iter_rows(named=True)}
    assert venc[BAIRRO_A]["VALOR"] == 22222 and venc[BAIRRO_A]["ROTULO"].startswith("BELTRANO")
    bn = dict(br.metrica(vb, 13, "brancos_nulos_pct").iter_rows())
    assert bn[BAIRRO_A] == pytest.approx(100 * 20 / 158)  # brancos 7 + nulos 13 sobre 158 apurados
    brancos = dict(br.metrica(vb, 13, "brancos_pct").iter_rows())
    nulos = dict(br.metrica(vb, 13, "nulos_pct").iter_rows())
    assert brancos[BAIRRO_A] == pytest.approx(100 * 7 / 158) and nulos[BAIRRO_A] == pytest.approx(100 * 13 / 158)
    assert (brancos[BAIRRO_B], nulos[BAIRRO_B]) == (0, 0)  # bairro sem branco nem nulo: 0%, não "sem dado"
    assert [c["NUMERO"] for c in br.categorias(vb, 13)][:2] == [22222, CAND]
    with pytest.raises(ValueError):
        br.metrica(vb, 13, "abstencao_pct")  # participação não vem dos votos
    assert b.anos_disponiveis() == {2024: [13]}


def test_suplementar_no_mesmo_arquivo_e_descartada(tse_cache: Path) -> None:
    votos = v.load_section_votes(2024, "RJ", "vereador", tse_cache, False)
    cand = votos.filter(pl.col("NR_VOTAVEL") == CAND, pl.col("CD_MUNICIPIO") == 60011).select(pl.col("QT_VOTOS").sum())
    assert cand.collect().item() == 29  # sem os 1.000 da suplementar na seção 10


def test_abstencao_e_comparecimento_por_bairro(tse_cache: Path) -> None:
    b = _bairros(tse_cache)
    pb = {r["CD_BAIRRO"]: r for r in b.participacao(2024, 13, 1).iter_rows(named=True)}
    # CSV _BRASIL, só RJ, sem a suplementar e sem o 2º turno; Niterói fora dos bairros
    assert (pb[BAIRRO_A]["QT_APTOS"], pb[BAIRRO_A]["QT_COMPARECIMENTO"]) == (920, 750)
    assert (pb[BAIRRO_B]["QT_APTOS"], pb[BAIRRO_B]["QT_ABSTENCOES"]) == (450, 140)
    abst = dict(br.metrica_participacao(b.participacao(2024, 13, 1), "abstencao_pct").select("CD_BAIRRO", "VALOR").iter_rows())
    assert abst[BAIRRO_A] == pytest.approx(100 * 170 / 920) and abst[BAIRRO_B] == pytest.approx(100 * 140 / 450)
    t2 = b.participacao(2024, 11, 2)  # 2º turno de prefeito só existe no CSV _BRASIL
    assert t2.row(0, named=True)["QT_APTOS"] == 300
    with pytest.raises(v.TseDataError):
        b.participacao(2024, 3, 1)  # cargo que não houve naquele ano


def test_falha_de_microdados_nao_repete_download(tse_cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    b = _bairros(tse_cache)
    chamadas = []

    def sem_microdados(*args: object) -> None:
        chamadas.append(args)
        raise v.TseDataError("404 no TSE")

    monkeypatch.setattr(v, "load_section_votes", sem_microdados)
    for _ in range(3):
        with pytest.raises(v.TseDataError):
            b.votos(2026, 3, 1)
    assert len(chamadas) == 1  # vários 404 seguidos podem bloquear o IP no TSE


# --------------------------------------------------------------------------- API
@pytest.fixture()
def site(tse_cache: Path, tmp_path: Path) -> TestClient:
    escrever_bairros(tse_cache)
    (tse_cache / "malhas" / "municipios_RJ.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"codarea": "3304557"},
                                                    "geometry": {"type": "Polygon", "coordinates": [[[-43.3, -22.8],
                                                    [-43.1, -22.8], [-43.1, -23.0], [-43.3, -22.8]]]}}]}))
    return TestClient(create_app(tmp_path / "dados", "RJ", tse_cache))


def test_api_bairros(site: TestClient) -> None:
    assert len(site.get("/geo/bairros.geojson").json()["features"]) == 2
    info = site.get("/api/bairros/anos").json()
    assert info["anos"] == {"2024": [13]} and info["cargos"]["13"] == "Vereador"
    d = site.get(f"/api/mapa/bairros?ano=2024&cargo=13&metrica=pct_candidato&numero={CAND}").json()
    assert set(d["itens"]) == {BAIRRO_A, BAIRRO_B} and d["cobertura"]["locais_em_bairro"] == 3
    assert d["itens"][BAIRRO_A]["municipio"] == "Centro Sintético — Rio de Janeiro"
    assert f"nº {CAND}" in d["rotulo"] and d["rotulo"].endswith("2024")
    assert site.get("/api/mapa/bairros?ano=2024&cargo=13&metrica=vencedor").json()["categorias"]
    ab = site.get("/api/mapa/bairros?ano=2024&cargo=13&metrica=abstencao_pct").json()
    assert ab["tipo"] == "sequencial" and ab["itens"][BAIRRO_B]["valor"] == pytest.approx(100 * 140 / 450)
    assert ab["rotulo"] == "Abstenção (%) — 2024"
    assert site.get("/api/mapa/bairros?ano=2024&cargo=13&metrica=comparecimento_pct&numero=1").status_code == 200
    nu = site.get("/api/mapa/bairros?ano=2024&cargo=13&metrica=nulos_pct").json()
    assert nu["rotulo"] == "Nulos (%) — 2024" and nu["itens"][BAIRRO_A]["valor"] == pytest.approx(100 * 13 / 158)
    assert site.get("/api/mapa/bairros?ano=2024&cargo=13&metrica=secoes_totalizadas_pct").status_code == 400
    assert site.get("/api/mapa/bairros?ano=2024&cargo=3&metrica=abstencao_pct").status_code == 404
    assert site.get("/api/mapa/bairros?ano=2024&cargo=99&metrica=vencedor").status_code == 400


def test_api_exportar(site: TestClient) -> None:
    corpo = {"formato": "svg", "camada": "bairros", "nome": "mapa bairros teste", "titulo": "t",
             "cores": {BAIRRO_A: "#2a78d6"}, "legenda": [["#2a78d6", "x"]]}
    r = site.post("/api/exportar/mapa", json=corpo)
    assert r.status_code == 200 and r.content.startswith(b"<?xml")
    assert r.headers["content-disposition"] == 'attachment; filename="mapa_bairros_teste.svg"'
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert site.post("/api/exportar/mapa", json={**corpo, "formato": "bmp"}).status_code == 400
    assert site.post("/api/exportar/mapa", json={**corpo, "camada": "setores"}).status_code == 422
    png = site.post("/api/exportar/mapa", json={**corpo, "formato": "png", "camada": "municipios",
                                                "cores": {"3304557": "#256abf"}})
    assert png.status_code == 200 and png.content.startswith(MAGICOS["png"])


# --------------------------------------------------------------------------- comparação por bairro
@pytest.fixture()
def comp(tse_cache: Path, monkeypatch: pytest.MonkeyPatch) -> br.ComparacaoBairros:
    c = br.ComparacaoBairros(_bairros(tse_cache))
    monkeypatch.setattr(c, "siglas", lambda ano: {55: "PSD", 22: "PL"} if ano == 2024 else {55: "PSD", 22: "PR"})
    return c


def test_numero_do_partido() -> None:
    nums = pl.Series([95, 96, 22, 222, 55555, 13]).to_frame("n").select(br.numero_partido(pl.col("n")))
    assert nums.to_series().to_list() == [None, None, 22, 22, 55, 13]


def test_comparar_eleitorado_entre_cadastros(comp: br.ComparacaoBairros) -> None:
    assert comp.anos_cadastro() == [2024, 2026]
    df, resumo = comp.comparar(2024, 13, 2026, 13, "eleitorado")
    linhas = {r["CD_BAIRRO"]: r for r in df.iter_rows(named=True)}
    # A: local 1015 com 920 → 955; B: 1023 + 1031 (350 + 100) em 2024 → só 1023 (150) em 2026
    assert (linhas[BAIRRO_A]["VALOR_A"], linhas[BAIRRO_A]["VALOR_B"]) == (920, 955)
    assert linhas[BAIRRO_B]["DIF"] == pytest.approx(100 * (150 - 450) / 450)
    assert resumo["VALOR_A"] == 1370 and resumo["DIF"] == pytest.approx(100 * (1105 - 1370) / 1370)


def test_comparar_partido_e_brancos(comp: br.ComparacaoBairros) -> None:
    df, resumo = comp.comparar(2024, 13, 2024, 13, "partido", partido=55)
    linhas = {r["CD_BAIRRO"]: r for r in df.iter_rows(named=True)}
    assert linhas[BAIRRO_A]["VALOR_A"] == pytest.approx(100 * 18 / 138)  # 13 do candidato 55555 + 5 de legenda
    assert linhas[BAIRRO_A]["DIF"] == 0 and resumo["DIF"] == 0
    assert resumo["VALOR_A"] == pytest.approx(100 * (18 + 16) / (138 + 51))  # área = soma, não média
    _, bn = comp.comparar(2024, 13, 2024, 13, "brancos_nulos")
    assert bn["VALOR_A"] == pytest.approx(100 * 20 / (158 + 51))
    _, brancos = comp.comparar(2024, 13, 2024, 13, "brancos")
    df_nulos, nulos = comp.comparar(2024, 13, 2024, 13, "nulos")
    assert brancos["VALOR_A"] == pytest.approx(100 * 7 / 209) and nulos["VALOR_B"] == pytest.approx(100 * 13 / 209)
    assert brancos["VALOR_A"] + nulos["VALOR_A"] == pytest.approx(bn["VALOR_A"])  # as partes somam o todo
    ps = comp.partidos(2024, 13, 2026, 13)  # 2026 sem microdados: partido fica "só 2024"
    pl22 = ps.filter(pl.col("PARTIDO") == 22).row(0, named=True)
    assert (pl22["SIGLA_A"], pl22["SIGLA_B"], pl22["NOS_DOIS"], pl22["VOTOS_B"]) == ("PL", "PR", False, None)
    with pytest.raises(ValueError):
        comp.comparar(2024, 13, 2024, 13, "secoes_totalizadas")


def test_comparar_abstencao_e_comparecimento(comp: br.ComparacaoBairros) -> None:
    df, resumo = comp.comparar(2024, 13, 2024, 13, "abstencao")
    linhas = {r["CD_BAIRRO"]: r for r in df.iter_rows(named=True)}
    assert linhas[BAIRRO_A]["VALOR_A"] == pytest.approx(100 * 170 / 920) and linhas[BAIRRO_A]["DIF"] == 0
    assert resumo["VALOR_A"] == pytest.approx(100 * 310 / 1370)  # área: abstenções / aptos somados
    _, comp_ = comp.comparar(2024, 13, 2024, 13, "comparecimento")
    assert comp_["VALOR_B"] == pytest.approx(100 * 1060 / 1370)
    with pytest.raises(v.TseDataError):
        comp.comparar(2024, 13, 2026, 13, "abstencao")  # 2026: detalhe por seção ainda não publicado


def test_api_comparacao_bairros(site: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(br.ComparacaoBairros, "siglas", lambda self, ano: {55: "PSD"})
    info = site.get("/api/comparacao/bairros/info").json()
    assert info["anos_votos"] == {"2024": [13]} and info["anos_cadastro"] == [2024, 2026]
    d = site.get("/api/comparacao/bairros?ano_a=2024&cargo_a=13&ano_b=2026&cargo_b=13&metrica=eleitorado").json()
    assert d["camada"] == "bairros" and set(d["itens"]) == {BAIRRO_A, BAIRRO_B}
    assert d["municipios"][0]["NM_MUNICIPIO"].endswith("— Rio de Janeiro")
    p = site.get("/api/comparacao/bairros?ano_a=2024&cargo_a=13&ano_b=2024&cargo_b=13&metrica=partido&partido=55").json()
    assert p["rotulo"].endswith("55 PSD") and p["subtitulo"] == "Vereador 2024 × Vereador 2024"
    assert site.get("/api/comparacao/bairros?ano_a=2024&cargo_a=13&ano_b=2026&cargo_b=3&metrica=brancos_nulos"
                    ).status_code == 404  # 2026 sem microdados
    assert site.get("/api/comparacao/bairros?ano_a=2024&cargo_a=13&ano_b=2024&cargo_b=13&metrica=partido"
                    ).status_code == 400
    assert site.get("/api/comparacao/bairros/partidos?ano_a=2024&cargo_a=13&ano_b=2024&cargo_b=13").json()[0]["PARTIDO"]
