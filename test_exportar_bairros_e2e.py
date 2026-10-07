"""Downloads (mapa PNG/SVG/JPEG, gráficos SVG/PNG) e mapa por bairro no navegador (marca e2e)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page  # noqa: E402

from conftest import CAND, abrir, endereco  # noqa: E402

pytestmark = pytest.mark.e2e
MAGICOS = {"png": b"\x89PNG", "jpeg": b"\xff\xd8\xff", "svg": b"<?xml"}


def baixar(pg: Page, seletor: str) -> tuple[str, bytes]:
    with pg.expect_download() as info:
        pg.click(seletor)
    d = info.value
    return d.suggested_filename, Path(d.path()).read_bytes()


def esperar_mapa(pg: Page, qual: str = "mapa", camada: str = "municipios") -> None:
    pg.wait_for_function(f"() => __apuracao.estado.{qual} && __apuracao.estado.{qual}._export && __apuracao.estado.{qual}._export.camada === '{camada}'",
                         timeout=20_000)


# --------------------------------------------------------------------------- downloads
@pytest.mark.parametrize("formato", ["png", "svg", "jpeg"])
def test_baixar_mapa(pagina: Page, site: dict, formato: str) -> None:
    abrir(pagina, site, "#mapas?cargo=3&metrica=abstencao_pct")
    esperar_mapa(pagina)
    nome, conteudo = baixar(pagina, f".baixar-mapa[data-mapa=mapa][data-formato={formato}]")
    assert nome.endswith(f".{formato}") and conteudo.startswith(MAGICOS[formato])
    if formato == "svg":
        texto = conteudo.decode()
        assert "Abstenção (%)" in texto and "Governador — RJ" in texto  # título e subtítulo no arquivo


def test_baixar_mapa_da_comparacao(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?cargo=3&metrica=abstencao")
    esperar_mapa(pagina, "compMapa")
    nome, conteudo = baixar(pagina, ".baixar-mapa[data-mapa=compMapa][data-formato=jpeg]")
    assert nome.endswith(".jpeg") and conteudo.startswith(MAGICOS["jpeg"])


def test_baixar_grafico_de_serie(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    gov = pagina.locator(".cartao", has=pagina.locator("h2", has_text="Governador"))
    gov.locator("svg.serie").wait_for()
    nome, svg = baixar(pagina, ".cartao:has(h2:has-text('Governador')) .baixar-serie button:has-text('SVG')")
    texto = svg.decode()
    assert nome.endswith(".svg") and texto.startswith("<svg") and texto.count("<polyline") == 3
    assert 'class="guia"' not in texto  # a camada de interação não vai para o arquivo
    nome, png = baixar(pagina, ".cartao:has(h2:has-text('Governador')) .baixar-serie button:has-text('PNG')")
    assert nome.endswith(".png") and png.startswith(MAGICOS["png"])


# --------------------------------------------------------------------------- bairros
def test_mapa_por_bairro(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"#mapas?detalhe=bairros&ano_bairros=2024&cargo=13&metrica=pct_candidato&numero={CAND}")
    esperar_mapa(pagina, camada="bairros")
    assert pagina.input_value("#mapa-detalhe") == "bairros" and pagina.input_value("#mapa-ano") == "2024"
    assert pagina.input_value("#mapa-cargo") == "13"
    assert pagina.locator("#mapa-cargo option").all_inner_texts() == ["Vereador"]  # cargos do ano escolhido
    assert pagina.is_hidden("#linha-tempo")                                       # microdados: sem linha do tempo
    assert pagina.evaluate("document.querySelector('#mapa-metrica option[value=secoes_totalizadas_pct]').disabled")
    assert not pagina.evaluate("document.querySelector('#mapa-metrica option[value=nulos_pct]').disabled")
    assert not pagina.evaluate("document.querySelector('#mapa-metrica option[value=abstencao_pct]').disabled")
    assert "2 de 2 bairros" in pagina.inner_text("#bairros-nota")
    assert f"nº {CAND}" in pagina.inner_text("#mapa-legenda h4")
    assert pagina.evaluate("__apuracao.estado.mapa._camada.getLayers().length") == 2
    assert pagina.evaluate("!!__apuracao.estado.mapa._contornos")                            # municípios por cima
    aba, q = endereco(pagina)
    assert q["detalhe"] == "bairros" and q["ano_bairros"] == "2024" and "momento" not in q

    nome, conteudo = baixar(pagina, ".baixar-mapa[data-mapa=mapa][data-formato=svg]")
    assert conteudo.startswith(MAGICOS["svg"]) and f"nº {CAND}" in conteudo.decode()


def test_voltar_para_municipios(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?cargo=3&metrica=vencedor")                     # governador, por município
    esperar_mapa(pagina, camada="municipios")
    pagina.select_option("#mapa-detalhe", "bairros")
    esperar_mapa(pagina, camada="bairros")
    pagina.select_option("#mapa-detalhe", "municipios")
    esperar_mapa(pagina, camada="municipios")
    assert pagina.input_value("#mapa-cargo") == "3"  # volta ao cargo que estava antes dos bairros
    assert pagina.is_hidden("#mapa-l-ano") and pagina.is_visible("#linha-tempo")
    assert not pagina.evaluate("!!__apuracao.estado.mapa._contornos")
    aba, q = endereco(pagina)
    assert "detalhe" not in q and "ano_bairros" not in q


def test_bairros_sem_microdados(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?detalhe=bairros&ano_bairros=2026&cargo=3&metrica=vencedor")
    pagina.wait_for_function("() => document.getElementById('mapa-legenda').textContent.includes('sem microdados')",
                             timeout=20_000)
    assert pagina.evaluate("__apuracao.estado.mapa._export") is None  # nada desenhado, nada para baixar


# --------------------------------------------------------------------------- comparação por bairro
def test_comparacao_por_bairro_eleitorado(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?detalhe=bairros&ano_a=2024&cargo_a=13&ano_b=2026&cargo_b=13&metrica=eleitorado")
    esperar_mapa(pagina, "compMapa", "bairros")
    assert pagina.input_value("#comp-detalhe") == "bairros" and pagina.is_hidden("#comp-l-cargo")
    assert (pagina.input_value("#comp-ano-a"), pagina.input_value("#comp-ano-b")) == ("2024", "2026")
    assert not pagina.evaluate("[...document.querySelectorAll('#comp-metrica option')].some((o) => o.disabled)")
    linhas = pagina.locator("#comp-tabela tbody tr td:first-child").all_inner_texts()
    assert len(linhas) == 2 and all(t.endswith("— Rio de Janeiro") for t in linhas)
    assert pagina.inner_text("#comp-titulo-tabela").startswith("Por bairro")
    assert "Cadastro de eleitorado 2024 × 2026" in pagina.inner_text("#comp-bairros-nota")
    assert pagina.evaluate("!!__apuracao.estado.compMapa._contornos")
    aba, q = endereco(pagina)
    assert (q["detalhe"], q["ano_a"], q["ano_b"], q["metrica"]) == ("bairros", "2024", "2026", "eleitorado")
    nome, conteudo = baixar(pagina, ".baixar-mapa[data-mapa=compMapa][data-formato=svg]")
    assert "Cadastro de eleitorado 2024 × 2026" in conteudo.decode()  # subtítulo certo no arquivo


def test_comparacao_por_bairro_partido(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?detalhe=bairros&ano_a=2024&cargo_a=13&ano_b=2024&cargo_b=13"
                        "&metrica=partido&partido=55")
    esperar_mapa(pagina, "compMapa", "bairros")
    assert pagina.input_value("#comp-partido") == "55"
    assert pagina.locator("#comp-partido option:checked").inner_text().startswith("55 PSD")
    assert "0,00 p.p." in pagina.inner_text("#comp-fichas")  # mesmo ano dos dois lados: diferença zero


def test_comparacao_bairro_sem_microdados_e_volta(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?detalhe=bairros&ano_a=2024&cargo_a=13&ano_b=2026&cargo_b=3&metrica=brancos_nulos")
    pagina.wait_for_function("() => document.getElementById('comp-legenda').textContent.includes('indisponíveis')",
                             timeout=20_000)
    assert pagina.evaluate("__apuracao.estado.compMapa._export") is None and pagina.locator("#comp-fichas .ficha").count() == 0
    pagina.select_option("#comp-detalhe", "municipios")
    esperar_mapa(pagina, "compMapa", "municipios")
    assert pagina.is_visible("#comp-l-cargo") and pagina.is_hidden("#comp-ano-a")
    assert not pagina.evaluate("[...document.querySelectorAll('#comp-metrica option')].some((o) => o.disabled)")
    aba, q = endereco(pagina)
    assert "detalhe" not in q


# --------------------------------------------------------------------------- participação por bairro
def test_abstencao_por_bairro_no_mapa(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?detalhe=bairros&ano_bairros=2024&cargo=13&metrica=abstencao_pct")
    esperar_mapa(pagina, camada="bairros")
    assert pagina.input_value("#mapa-metrica") == "abstencao_pct" and pagina.is_disabled("#mapa-numero")
    assert "Abstenção (%) — 2024" in pagina.inner_text("#mapa-legenda h4")
    assert pagina.evaluate("__apuracao.estado.mapa._camada.getLayers().length") == 2
    aba, q = endereco(pagina)
    assert (q["detalhe"], q["metrica"]) == ("bairros", "abstencao_pct")


def test_comparecimento_por_bairro_na_comparacao(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?detalhe=bairros&ano_a=2024&cargo_a=13&ano_b=2024&cargo_b=13&metrica=comparecimento")
    esperar_mapa(pagina, "compMapa", "bairros")
    assert pagina.input_value("#comp-metrica") == "comparecimento"
    fichas = pagina.inner_text("#comp-fichas")
    assert "77,37" in fichas and "0,00 p.p." in fichas  # 1.060 de 1.370 aptos na área dos bairros
    assert len(pagina.locator("#comp-tabela tbody tr").all()) == 2


# --------------------------------------------------------------------------- brancos e nulos separados
def test_brancos_e_nulos_por_bairro(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?detalhe=bairros&ano_bairros=2024&cargo=13&metrica=nulos_pct")
    esperar_mapa(pagina, camada="bairros")
    assert pagina.input_value("#mapa-metrica") == "nulos_pct"
    assert "Nulos (%) — 2024" in pagina.inner_text("#mapa-legenda h4")
    aba, q = endereco(pagina)
    assert q["metrica"] == "nulos_pct"

    abrir(pagina, site, "#comparacao?detalhe=bairros&ano_a=2024&cargo_a=13&ano_b=2024&cargo_b=13&metrica=brancos")
    esperar_mapa(pagina, "compMapa", "bairros")
    assert pagina.input_value("#comp-metrica") == "brancos"
    assert "3,35" in pagina.inner_text("#comp-fichas")  # 7 brancos em 209 votos na área dos bairros
