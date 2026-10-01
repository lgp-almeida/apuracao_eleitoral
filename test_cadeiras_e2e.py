"""Cadeiras no navegador (marca e2e): cartões de deputado do painel e aba Candidato.

No site de testes a apuração de deputados está em andamento (80% das seções na UF), então o painel
mostra as cadeiras sobre os votos PROJETADOS (consolidados × em disputa)."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page  # noqa: E402

from conftest import abrir  # noqa: E402

pytestmark = pytest.mark.e2e


def cartao(pg: Page, cargo: str):
    return pg.locator(".cartao", has=pg.locator("h2", has_text=cargo))


def test_cadeiras_projetadas_no_painel(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    dep = cartao(pagina, "Deputado Estadual")
    dep.locator(".cad-lista").wait_for(timeout=20_000)
    assert dep.get_by_role("heading", name="Cadeiras projetadas — 80 vagas").count() == 1
    assert "eleitos consolidados" in dep.locator(".proj-situacao").inner_text()
    assert dep.locator(".cad-item").count() >= 1 and dep.locator(".cad-faixa").count() >= 1
    # o recorte do simulado nos testes é truncado: a salvaguarda avisa que os votos não somam os válidos
    assert "não somam os válidos" in dep.locator(".aviso").inner_text()
    dep.locator("details summary", has_text="consolidados").click()
    dep.locator(".cad-eleitos tbody tr").first.wait_for(timeout=20_000)
    assert dep.locator(".cad-eleitos thead th").all_inner_texts()[-1] == "Sim."
    assert cartao(pagina, "Governador").locator(".cad-lista").count() == 0  # só nos proporcionais


def test_projecao_de_cadeira_na_aba_candidato(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    cartao(pagina, "Deputado Estadual").locator(".cad-lista").wait_for(timeout=20_000)
    numero = pagina.evaluate("fetch('api/cadeiras?cargo=7').then(r => r.json()).then(d => d.projecao.candidatos[0].NUMERO)")
    abrir(pagina, site, f"#candidato?cargo=7&numero={numero}")
    ficha = pagina.locator(".ficha", has=pagina.locator(".rot", has_text="Projeção de cadeira"))
    ficha.wait_for(timeout=20_000)
    texto = ficha.locator(".val").inner_text()
    assert texto.startswith(("Consolidado", "Em disputa")) and "das simulações" in texto
