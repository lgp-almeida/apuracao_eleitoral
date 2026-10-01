"""Alertas na página (Chrome): faixa, aviso, som, título, painel e "Acompanhar" na aba Candidato."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import abrir

pytestmark = pytest.mark.e2e


def test_alerta_aparece_toca_e_resolve(pagina, site) -> None:
    vigia = site["app"].state.vigia
    vigia.estagnada_min = 1e9  # as horas do TSE falso são fictícias: "sem avanço" é testado em test_alertas.py
    abrir(pagina, site)
    pagina.wait_for_function("() => alertas.ultimo !== null")
    pagina.evaluate("() => { window.__sons = []; window.tocar = (n) => window.__sons.push(n); }")
    real = vigia.relogio_utc
    try:
        vigia.relogio_utc = lambda: datetime.now(timezone.utc) + timedelta(days=2)  # coleta parada
        assert [a["chave"] for a in vigia.verificar()] == ["coletor:parado"]
        pagina.evaluate("() => atualizarAlertas()")
        faixa = pagina.locator("#faixa-alertas")
        faixa.wait_for(state="visible")
        assert "Coleta parada" in faixa.inner_text() and "Crítico" in faixa.inner_text()
        assert pagina.locator("#avisos .alerta.critico").count() == 1
        assert pagina.evaluate("() => window.__sons") == ["critico"]
        assert pagina.title().startswith("⚠ (1) ")
        assert pagina.locator("#alertas-contagem").inner_text() == "1"

        pagina.click("#botao-alertas")
        assert pagina.locator("#painel-alertas").is_visible()
        assert "Coleta parada" in pagina.locator("#alertas-historico").inner_text()
        assert pagina.locator("#alertas-contagem").is_hidden()
        assert pagina.locator("#avisos .alerta").count() == 0      # avisos não cobrem o painel
        pagina.keyboard.press("Escape")
        assert pagina.locator("#painel-alertas").is_hidden()
    finally:
        vigia.relogio_utc = real
    assert [a["chave"] for a in vigia.verificar()] == ["coletor:parado:resolvido"]
    pagina.evaluate("() => atualizarAlertas()")
    pagina.locator("#faixa-alertas").wait_for(state="hidden")
    assert "Resolvido" in pagina.locator("#avisos").inner_text()
    assert not pagina.title().startswith("⚠")
    assert pagina.evaluate("() => window.__sons") == ["critico", "ok"]


def test_acompanhar_deputado_pela_aba_candidato(pagina, site) -> None:
    abrir(pagina, site)
    pagina.wait_for_function("() => alertas.ultimo !== null")
    pagina.locator("#cartoes .cartao").first.wait_for()   # carga inicial (tick + abrirPorHash) concluída
    numero = pagina.evaluate("() => api('api/candidatos?cargo=7').then((l) => l[0].NUMERO)")
    pagina.evaluate(f"() => consultarCandidato(7, {numero})")
    botao = pagina.locator("#botao-acompanhar")
    botao.wait_for()
    assert "Acompanhar" in botao.inner_text()
    botao.click()
    pagina.locator("#botao-acompanhar", has_text="Deixar de acompanhar").wait_for()
    assert [i["numero"] for i in site["app"].state.vigia.lista()["interesse"]] == [numero]
    pagina.click("#botao-alertas")
    assert str(numero) in pagina.locator("#alertas-interesse").inner_text()
    pagina.locator("#alertas-interesse button").click()          # "remover"
    pagina.wait_for_function("() => alertas.interesse.length === 0")
    assert site["app"].state.vigia.lista()["interesse"] == []
    pagina.keyboard.press("Escape")
    # governador não tem "Acompanhar" (a leitura da projeção já é avisada para todos)
    pagina.evaluate(f"() => consultarCandidato(3, {site['numero']})")
    pagina.wait_for_function("() => document.querySelector('#cand-resultado .fichas')")
    assert pagina.locator("#botao-acompanhar").count() == 0
