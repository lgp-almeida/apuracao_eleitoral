"""Design system no Chrome (fase 5 da refatoração do front-end): régua de apuração, tema forçado, fonte local,
abas pelo teclado e nenhuma aba com rolagem horizontal no celular."""

from __future__ import annotations

import pytest

from conftest import abrir

pytestmark = pytest.mark.e2e

ABAS = ["painel", "candidato", "mapas", "comparacao", "perfil", "transferencia"]


def test_regua_de_apuracao(pagina, site: dict) -> None:
    abrir(pagina, site, "#painel")
    pagina.wait_for_selector("#regua:not([hidden]) .regua-pct")
    pct = pagina.locator("#regua .regua-pct").inner_text()
    assert pct.endswith("%")
    assert pagina.locator("#regua").get_attribute("aria-valuetext").startswith(pct)
    largura = pagina.evaluate("document.querySelector('#regua-trilho > .regua-feito').style.width")
    assert largura.endswith("%") and 0 < float(largura[:-1]) <= 100
    # a régua fica nas outras abas e no modo TV
    pagina.locator("#botao-mapas").click()
    assert pagina.locator("#regua").is_visible()
    abrir(pagina, site, "#painel?tv=1")
    pagina.wait_for_function("() => document.body.classList.contains('modo-tv')")
    assert pagina.locator("#regua").is_visible() and not pagina.locator(".abas").is_visible()


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_tema_forcado_pelo_endereco_vence_o_sistema(nova_pagina, site: dict, esquema: str) -> None:
    oposto, fundo = ("escuro", "rgb(13, 13, 13)") if esquema == "light" else ("claro", "rgb(249, 249, 247)")
    pg = nova_pagina(color_scheme=esquema)
    pg.goto(site["url"] + f"?tema={oposto}#painel")
    pg.wait_for_function("() => document.querySelectorAll('.cartao').length > 0")
    assert pg.evaluate("document.documentElement.dataset.tema") == oposto
    assert pg.evaluate("getComputedStyle(document.body).backgroundColor") == fundo
    assert pg.locator("#tema").input_value() == oposto
    # a paleta dos mapas não muda com o tema (rodada 31)
    assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--mapa-1').trim()") == "#fed976"


def test_seletor_de_tema_grava_a_escolha(nova_pagina, site: dict) -> None:
    pg = nova_pagina(color_scheme="light")
    abrir(pg, site, "#painel")
    pg.wait_for_function("() => document.querySelectorAll('.cartao').length > 0")
    with pg.expect_navigation():
        pg.locator("#tema").select_option("escuro")
    pg.wait_for_function("() => document.querySelectorAll('.cartao').length > 0")
    assert pg.evaluate("document.documentElement.dataset.tema") == "escuro"
    assert pg.evaluate("location.hash").startswith("#painel")  # o estado das abas volta pelo endereço
    pg.locator("#tema").select_option("")
    pg.wait_for_function("() => document.querySelectorAll('.cartao').length > 0")
    assert pg.evaluate("document.documentElement.dataset.tema") is None


def test_fonte_local_e_numeros_tabulares(pagina, site: dict) -> None:
    abrir(pagina, site, "#painel")
    pagina.wait_for_function("() => document.fonts.check('14px \"Public Sans Variable\"')")
    estilo = pagina.evaluate("(() => { const s = getComputedStyle(document.body);"
                             " return [s.fontFamily, s.fontVariantNumeric]; })()")
    assert estilo[0].startswith('"Public Sans Variable"') and estilo[1] == "tabular-nums"


def test_abas_pelo_teclado(pagina, site: dict) -> None:
    abrir(pagina, site, "#painel")
    pagina.wait_for_selector("#botao-painel[aria-selected=true]")
    assert pagina.locator("#botao-painel").get_attribute("aria-controls") == "aba-painel"
    assert pagina.locator("#aba-painel").get_attribute("aria-labelledby") == "botao-painel"
    assert pagina.locator(".abas [role=tab][tabindex='0']").count() == 1
    pagina.locator("#botao-painel").focus()
    pagina.keyboard.press("ArrowRight")
    pagina.wait_for_selector("#aba-candidato:not([hidden])")
    assert pagina.evaluate("document.activeElement.id") == "botao-candidato"
    pagina.keyboard.press("End")
    pagina.wait_for_selector("#aba-transferencia:not([hidden])")
    pagina.keyboard.press("Home")
    pagina.wait_for_selector("#aba-painel:not([hidden])")


def test_celular_sem_rolagem_horizontal(nova_pagina, site: dict) -> None:
    pg = nova_pagina(viewport={"width": 360, "height": 780})
    for aba in ABAS:
        abrir(pg, site, f"#{aba}")
        pg.wait_for_selector(f"#aba-{aba}:not([hidden])")
        pg.wait_for_timeout(300)
        assert pg.evaluate("document.documentElement.scrollWidth") <= 360, aba
