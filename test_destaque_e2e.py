"""Destaque de partidos/federações nas listas de eleitos projetados e botão de salvar (rodada 31), no Chrome."""

from __future__ import annotations

import json
from urllib.request import urlopen

import pytest

from conftest import abrir

pytestmark = pytest.mark.e2e


def _eleitos(site: dict, cargo: int = 7) -> list[dict]:
    """A lista que o cartão mostra: a da projeção (a partir de 30% apurado) ou a dos eleitos da apuração atual."""
    with urlopen(f"{site['url']}api/cadeiras?cargo={cargo}") as r:
        d = json.load(r)
    return d["projecao"]["candidatos"] if (d.get("projecao") or {}).get("ativa") else d["eleitos"]


DESTACAR_NO_ENDERECO = "() => new URLSearchParams(location.hash.split('?')[1] || '').get('destacar')"


def test_destaque_nas_listas_de_eleitos(pagina, site) -> None:
    eleitos = _eleitos(site)
    alvo = eleitos[0]["PARTIDO"]
    n = sum(e["PARTIDO"] == alvo or e["AGREMIACAO"] == alvo for e in eleitos)
    abrir(pagina, site, "#painel?" + pagina.evaluate("a => new URLSearchParams({destacar: a}).toString()", alvo))
    pagina.wait_for_selector("#cartoes .cartao")
    pagina.locator("#destaque:not([hidden])").wait_for()
    cartao = pagina.locator(".cartao", has_text="Deputado Estadual")
    lista = cartao.locator("details:has(.cad-eleitos) > summary")
    lista.click()
    cartao.locator(".cad-eleitos tr.destaque").first.wait_for()
    assert cartao.locator(".cad-eleitos tr.destaque").count() == n
    assert cartao.locator(".cad-eleitos tr.destaque td").first.inner_text().startswith("★")   # não só a cor
    assert f"{n} destacado" in lista.inner_text()
    assert cartao.locator(".cad-item.destaque").count() >= 1
    href = cartao.locator("a.botao-salvar").get_attribute("href")
    assert href.startswith("api/cadeiras/planilha?cargo=7") and pagina.evaluate(
        "h => new URLSearchParams(h.split('?')[1]).get('destacar')", href) == alvo
    # o redesenho de 60 s mantém o destaque e a lista aberta
    pagina.evaluate("() => __apuracao.atualizarPainel()")
    cartao.locator(".cad-eleitos tr.destaque").first.wait_for()
    assert cartao.locator(".cad-eleitos tr.destaque").count() == n
    # desmarcar pela caixa: some o destaque, o endereço e o link de salvar acompanham
    pagina.locator("#destaque summary").click()
    pagina.locator(f"#destaque-opcoes input[value='{alvo}']").first.uncheck()
    pagina.wait_for_function(f"() => ({DESTACAR_NO_ENDERECO})() === null")
    assert "destacar" not in cartao.locator("a.botao-salvar").get_attribute("href")


def test_escolha_fica_no_navegador(nova_pagina, site) -> None:
    alvo = _eleitos(site)[0]["PARTIDO"]
    pg = nova_pagina(viewport={"width": 1200, "height": 900})
    abrir(pg, site, "#painel")
    pg.wait_for_selector("#destaque:not([hidden])")
    pg.locator("#destaque summary").click()
    pg.locator(f"#destaque-opcoes input[value='{alvo}']").first.check()
    pg.wait_for_function(f"a => ({DESTACAR_NO_ENDERECO})() === a", arg=alvo)
    pg.goto(site["url"] + "#painel")
    pg.reload()
    pg.wait_for_selector("#destaque:not([hidden])")
    assert pg.evaluate("[...__apuracao.abas.painel.estado.destacar]") == [alvo]
    assert pg.locator(f"#destaque-opcoes input[value='{alvo}']").first.is_checked()
