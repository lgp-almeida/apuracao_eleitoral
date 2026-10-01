"""Modo TV e "O que mudou" no painel (rodada 33), no Chrome."""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import abrir

pytestmark = pytest.mark.e2e


def test_modo_tv(pagina, site) -> None:
    abrir(pagina, site, "#painel?tv=1")
    pagina.wait_for_selector("#cartoes .cartao")
    pagina.wait_for_function("() => document.body.classList.contains('modo-tv')")
    assert pagina.locator("#cartoes .cartao:visible").count() == 1
    assert pagina.locator(".abas").is_hidden() and pagina.locator("#tv-barra").is_visible()
    primeiro = pagina.locator("#cartoes .cartao.tv-atual h2").inner_text()
    pagina.keyboard.press("ArrowRight")
    assert pagina.locator("#cartoes .cartao.tv-atual h2").inner_text() != primeiro
    assert "(2 de" in pagina.inner_text("#tv-barra")
    pagina.keyboard.press(" ")
    assert "pausado" in pagina.inner_text("#tv-barra")
    pagina.evaluate("() => atualizarPainel()")                       # o redesenho de 60 s mantém o cargo
    pagina.wait_for_function("() => document.querySelectorAll('#cartoes .cartao.tv-atual').length === 1")
    pagina.keyboard.press("Escape")
    pagina.wait_for_function("() => !document.body.classList.contains('modo-tv')")
    assert "tv=1" not in pagina.evaluate("location.hash") and pagina.locator(".abas").is_visible()
    assert pagina.locator("#cartoes .cartao:visible").count() > 1


def test_o_que_mudou_no_painel(pagina, site) -> None:
    pasta = site["app"].state.consultas.dados.diretorio / "boletins"
    pasta.mkdir(exist_ok=True)
    # boletim anterior "inventado": governador a 5% e outro líder -> a página mostra a diferença
    foto = {"titulo": "Boletim das 18h", "gerado_em": "2026-10-04T18:00:05", "cargos": {
        "3-RJ": {"ds": "Governador — RJ", "pct": 5.0, "final": False,
                 "lider": {"numero": 1, "nome": "OUTRO", "pct": 1.0}, "leitura": None}}}
    (pasta / "boletim_2026-10-04_18h00.json").write_text(json.dumps(foto))
    try:
        abrir(pagina, site, "#painel")
        pagina.locator("#mudancas:not([hidden])").wait_for()
        assert "desde o boletim das 18h" in pagina.inner_text("#mudancas-titulo")
        lista = pagina.inner_text("#mudancas-lista")
        assert "Governador — RJ" in lista and "5,00% →" in lista and "novo líder" in lista
    finally:
        shutil.rmtree(pasta)
