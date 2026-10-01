"""Aba "1º → 2º turno" no Chrome: barras, legenda, dica, aviso de leitura frágil, endereço e celular."""

from __future__ import annotations

import pytest

from apuracao import transferencia as tr
from conftest import abrir
from test_transferencia import sintetico

pytestmark = pytest.mark.e2e


@pytest.fixture()
def calculo_sintetico(monkeypatch: pytest.MonkeyPatch):
    secoes, votos, nomes = sintetico(locais_por_zona=30)

    def calcular(ano, uf, cargo, nivel, cache, municipio=None, n_boot=200):
        if municipio == 1:   # área sem unidades suficientes: o erro chega à página
            raise tr.v.TseDataError("poucas unidades (2) para 5 categorias do 1º turno")
        if nivel == "municipio":  # o sintético tem 2 municípios: seções no formato do nível município
            u = tr.montar_unidades(secoes, votos, nomes, "secao", max_eliminados=0, descricao="sintético, por município")
            u.nivel = "municipio"
        else:
            u = tr.montar_unidades(secoes, votos, nomes, nivel, descricao=f"sintético, por {nivel}")
        return tr.analisar(u, n_boot=5)

    monkeypatch.setattr(tr, "calcular", calcular)


def test_aba_transferencia(pagina, site, calculo_sintetico) -> None:
    abrir(pagina, site, "#transferencia?fonte=microdados&ano=2024&cargo=11&nivel=local")
    pagina.wait_for_selector("#tf-resultado .tf-linha")
    linhas = pagina.locator("#tf-resultado .tf-linha")
    assert linhas.count() == 7                                     # A, B, 2 eliminados, outros, branco/nulo, abstenção
    assert pagina.locator(".tf-legenda span").all_inner_texts() == ["ANA (P1)", "BIA (P2)", "Branco/nulo", "Abstenção"]
    seg = linhas.nth(2).locator(".tf-barra div").first
    assert "CAIO (P3) → ANA (P1)" in seg.get_attribute("title") and "IC 95%" in seg.get_attribute("title")
    assert "CAIO (P3)" in linhas.nth(2).locator(".tf-barra").get_attribute("aria-label")
    assert pagina.locator("#tf-resultado .aviso").count() == 0     # local: sem aviso de leitura frágil
    assert "Erro fora da amostra" in pagina.inner_text("#tf-resultado .fichas")
    assert "nivel=local" in pagina.evaluate("location.hash")
    pagina.select_option("#tf-nivel", "municipio")
    pagina.click("#form-tf button[type=submit]")
    pagina.wait_for_function("() => location.hash.includes('nivel=municipio')")
    pagina.locator("#tf-resultado .aviso", has_text="Leitura frágil").wait_for()
    assert pagina.locator("#tf-resultado .tf-linha").count() == 5   # municípios: eliminados num grupo só
    pagina.evaluate("() => { const o = document.createElement('option'); o.value = '1'; o.textContent = 'X';"
                    " document.getElementById('tf-municipio').append(o); document.getElementById('tf-municipio').value = '1'; }")
    pagina.click("#form-tf button[type=submit]")
    pagina.wait_for_function("() => document.getElementById('tf-msg').textContent.includes('poucas unidades')")
    assert pagina.locator("#tf-resultado .tf-linha").count() == 0   # não fica o resultado anterior na tela


def test_aba_transferencia_no_celular(nova_pagina, site, calculo_sintetico) -> None:
    pg = nova_pagina(viewport={"width": 390, "height": 800})
    abrir(pg, site, "#transferencia?fonte=microdados&ano=2024&cargo=11&nivel=secao")
    pg.wait_for_selector("#tf-resultado .tf-linha")
    pg.evaluate("document.querySelector('#tf-resultado details').open = true")
    assert pg.evaluate("document.documentElement.scrollWidth") <= 390
