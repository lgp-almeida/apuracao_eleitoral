"""Projeção do resultado final no painel (marca e2e)."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page  # noqa: E402

from conftest import abrir  # noqa: E402

pytestmark = pytest.mark.e2e


def test_projecao_no_cartao_do_governador(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    gov = pagina.locator(".cartao", has=pagina.locator("h2", has_text="Governador"))
    gov.locator(".proj-lista").wait_for(timeout=20_000)  # o site de testes para o governador em 80%
    sub = gov.locator(".proj-lista").locator("xpath=preceding-sibling::div[contains(@class,'sub')][1]").inner_text()
    assert "do eleitorado apurado" in sub and "margem ±" in sub
    assert gov.locator(".proj-situacao").inner_text()
    itens = gov.locator(".proj-item")
    assert itens.count() >= 2 and itens.first.locator(".proj-ponto").count() == 1
    assert gov.locator(".proj-50").count() == itens.count()  # linha dos 50%: governador decide por maioria
    assert gov.locator(".lista .item").count() == 11  # a lista de candidatos continua intacta
    gov.locator("details summary", has_text="Onde faltam votos").click()
    # nos recortes do simulado os municípios já vêm com todo o eleitorado apurado: a tabela sai vazia
    gov.locator(".cad-eleitos table thead").wait_for(timeout=20_000)

