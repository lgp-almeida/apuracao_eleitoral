"""A página não lança erro de JavaScript em nenhuma aba (rodada 67: todo o código da página em módulos TypeScript).

Percorre as seis abas pelo endereço e pelos botões, abre os blocos que carregam sob demanda e falha com qualquer
`pageerror` ou `console.error` — exceto recurso que não carregou (fundo do OpenStreetMap sem internet, /ufs.json
ausente no site de uma UF), que o navegador registra sozinho.

Rodar só estes:   pytest -q -m e2e test_console_e2e.py
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from conftest import abrir  # noqa: E402

pytestmark = pytest.mark.e2e

IGNORAR = ("Failed to load resource",)


def test_nenhum_erro_de_javascript_nas_abas(nova_pagina, site) -> None:
    pg = nova_pagina(viewport={"width": 1400, "height": 1000})
    erros: list[str] = []
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.on("console", lambda m: erros.append(f"console: {m.text}")
          if m.type == "error" and not any(i in m.text for i in IGNORAR) else None)

    abrir(pg, site, "#painel")
    pg.wait_for_selector("#cartoes .cartao")
    pg.locator("#cartoes details summary").first.click()  # projeção ("onde faltam votos") ou lista de eleitos
    abrir(pg, site, f"#candidato?cargo=3&numero={site['numero']}&hist=1&pl=1")
    pg.wait_for_selector("#cand-resultado table tbody tr")
    pg.wait_for_selector("#hist-resultado .fichas, #hist-resultado .aviso")
    abrir(pg, site, "#mapas?cargo=3&metrica=vencedor&locais=1")
    pg.wait_for_selector("#mapa-legenda h4")
    abrir(pg, site, "#comparacao?cargo=3&metrica=abstencao&banc=1&var=1")
    pg.wait_for_selector("#aba-comparacao .legenda h4")
    for aba in ("perfil", "transferencia", "painel"):
        pg.click(f"button[data-aba={aba}]")
        pg.wait_for_function(f"() => !document.getElementById('aba-{aba}').hidden")
    pg.wait_for_timeout(1500)  # pedidos que ainda estavam a caminho
    assert erros == []
