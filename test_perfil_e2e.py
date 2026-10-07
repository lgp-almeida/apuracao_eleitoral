"""Aba "Perfil × voto" no navegador (marca e2e): endereço, gráfico de dispersão, correlações e transferência."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page  # noqa: E402

from apuracao import perfil as pf  # noqa: E402
from conftest import CAND, abrir, endereco  # noqa: E402

pytestmark = pytest.mark.e2e
BASE = f"#perfil?ano=2024&turno=1&cargo=13&numero={CAND}&min_validos=0"


def esperar_grafico(pg: Page, pontos: int = 2) -> None:
    pg.wait_for_function(f"() => document.querySelectorAll('#pf-grafico circle.ponto').length === {pontos}",
                         timeout=20_000)


def test_endereco_abre_a_analise(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"{BASE}&x=pct_superior")
    esperar_grafico(pagina)
    assert pagina.is_visible("#aba-perfil") and pagina.input_value("#pf-cargo") == "13"
    assert pagina.input_value("#pf-x") == "pct_superior" and pagina.is_hidden("#pf-x-ano")
    assert "Bairros na análise\n2" in pagina.inner_text("#pf-fichas")
    titulo = pagina.inner_text("#pf-titulo-grafico")
    assert f"nº {CAND} FULANA DE TAL" in titulo and "% com superior completo" in titulo
    linhas = pagina.locator("#pf-correlacoes tbody tr")
    assert linhas.count() == len(pf.INDICADORES_TSE) + len(pf.INDICADORES_CENSO)  # TSE + Censo
    assert pagina.locator("#pf-correlacoes tr.selecionado td").first.inner_text() == "% com superior completo"
    aba, q = endereco(pagina)
    assert aba == "perfil" and (q["numero"], q["x"], q["min_validos"]) == (str(CAND), "pct_superior", "0")


def test_dica_e_clique_na_correlacao(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"{BASE}&x=pct_superior")
    esperar_grafico(pagina)
    ponto = pagina.locator("#pf-grafico circle.ponto").first
    caixa = ponto.bounding_box()
    pagina.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
    dica = pagina.locator("#pf-grafico .dica")
    dica.wait_for(state="visible")
    assert "Sintético — Rio de Janeiro" in dica.inner_text() or "Sintética — Rio de Janeiro" in dica.inner_text()
    assert pagina.locator("#pf-grafico circle.ponto.ativo").count() == 1
    pagina.locator("#pf-correlacoes tbody tr", has_text="Renda média").click()
    pagina.wait_for_function("() => document.getElementById('pf-titulo-grafico').textContent.includes('Renda média')")
    assert "x=renda_media" in pagina.evaluate("location.hash")
    assert "Renda média do responsável" in pagina.inner_text("#pf-titulo-grafico")
    assert "R$" in pagina.inner_text("#pf-acima") or "R$" in pagina.locator("#pf-grafico svg").text_content()


def test_transferencia_entre_eleicoes(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"{BASE}&x=voto&x_ano=2024&x_turno=1&x_cargo=13&x_partido=55")
    esperar_grafico(pagina)
    assert pagina.is_visible("#pf-x-ano") and pagina.is_visible("#pf-x-partido") and pagina.is_hidden("#pf-x-numero")
    assert pagina.input_value("#pf-x-partido") == "55"
    assert "partido 55 PSD" in pagina.inner_text("#pf-titulo-grafico")
    aba, q = endereco(pagina)
    assert (q["x"], q["x_ano"], q["x_partido"]) == ("voto", "2024", "55") and "x_numero" not in q


def test_ano_sem_microdados_mostra_erro(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#perfil?ano=2026&turno=1&cargo=3&numero=22&x=pct_superior")
    pagina.wait_for_function("() => document.getElementById('pf-msg').textContent.includes('Não foi possível')",
                             timeout=20_000)
    assert pagina.locator("#pf-grafico circle").count() == 0 and pagina.locator("#pf-fichas .ficha").count() == 0


def test_aba_abre_com_analise_padrao(nova_pagina, site: dict) -> None:
    pg = nova_pagina()  # página limpa: nada de análise anterior no estado
    abrir(pg, site, "#perfil")
    pg.wait_for_function("() => location.hash.startsWith('#perfil?')", timeout=20_000)
    aba, q = endereco(pg)
    # único ano com microdados no cenário: vereador 2024, o mais votado, contra % com superior completo
    assert (q["ano"], q["cargo"], q["numero"], q["x"]) == ("2024", "13", "22222", "pct_superior")


def test_baixar_grafico_de_dispersao(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"{BASE}&x=pct_superior")
    esperar_grafico(pagina)
    with pagina.expect_download() as info:
        pagina.click("#pf-grafico .baixar-serie button:has-text('SVG')")
    texto = Path(info.value.path()).read_text()
    assert texto.startswith("<svg") and texto.count("<circle") == 2 and "Bairro acima da tendência" in texto


def test_unidade_area_de_ponderacao(pagina: Page, site: dict) -> None:
    """Rodada 49: religião (amostra do Censo) só por área de ponderação; os 4 locais caem em 3 áreas."""
    abrir(pagina, site, f"{BASE}&x=pct_evangelicos&unidade=area")
    pagina.wait_for_function("() => document.querySelectorAll('#pf-grafico circle.ponto').length === 3", timeout=20_000)
    assert pagina.input_value("#pf-unidade") == "area" and pagina.is_visible("#pf-nota-area")
    assert "Áreas na análise\n3" in pagina.inner_text("#pf-fichas")
    assert pagina.locator("#pf-x optgroup[label='IBGE — Censo 2022 (amostra, área de ponderação)'] option").count() > 0
    aba, q = endereco(pagina)
    assert aba == "perfil" and q["unidade"] == "area" and q["x"] == "pct_evangelicos"
    pagina.select_option("#pf-unidade", "local")
    pagina.wait_for_function("() => document.querySelectorAll('#pf-grafico circle.ponto').length === 4", timeout=20_000)
    assert pagina.is_hidden("#pf-nota-area")


def test_unidade_local_de_votacao(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"{BASE}&x=renda_media&unidade=local")
    pagina.wait_for_function("() => document.querySelectorAll('#pf-grafico circle.ponto').length === 4", timeout=20_000)
    assert pagina.input_value("#pf-unidade") == "local"
    assert "Locais na análise\n4" in pagina.inner_text("#pf-fichas")
    assert pagina.locator("#pf-municipio option").first.inner_text() == "Estado inteiro"
    assert "Local acima da tendência" in pagina.inner_text("#pf-grafico")
    # 4 locais não bastam para os 4 indicadores padrão: a regressão explica em vez de quebrar
    pagina.wait_for_function("() => document.getElementById('pf-reg').textContent.includes('indisponível')")
    # com um só indicador marcado ela sai, e o endereço guarda a escolha
    pagina.locator("#pf-reg-ind input:checked").evaluate_all("xs => xs.forEach(x => x.checked = false)")
    pagina.locator("#pf-reg-ind input[value=pct_superior]").check()
    pagina.click("#pf-reg-btn")
    pagina.locator("#pf-reg table").wait_for(timeout=20_000)
    aba, q = endereco(pagina)
    assert q["unidade"] == "local" and q["reg"] == "pct_superior"
    # de volta a bairros: 2 pontos e o endereço sem unidade
    pagina.select_option("#pf-unidade", "bairro")
    pagina.wait_for_function("() => document.querySelectorAll('#pf-grafico circle.ponto').length === 2", timeout=20_000)
    aba, q = endereco(pagina)
    assert "unidade" not in q
