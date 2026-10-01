"""Painel, gráficos e mapas num navegador de verdade (Chrome via Playwright; marca e2e).

Usa o site da fixture `site` (conftest.py): TSE falso com 4 totalizações do cargo de
governador (UF e municípios), referência 2022 sintética e um candidato com nome em HTML.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page  # noqa: E402

from conftest import NOME_COM_HTML, abrir, endereco  # noqa: E402

pytestmark = pytest.mark.e2e


def cartao(pg: Page, titulo: str):
    return pg.locator(".cartao", has=pg.locator("h2", has_text=titulo))


def cores(pg: Page, *variaveis: str) -> set[str]:
    return set(pg.evaluate("vs => vs.map(v => getComputedStyle(document.documentElement).getPropertyValue(v).trim())",
                           list(variaveis)))


def preenchimentos(pg: Page, mapa: str) -> list[str]:
    """Cor de preenchimento de cada município desenhado no mapa Leaflet (`estado.mapa`, `estado.compMapa`)."""
    pg.wait_for_function(f"() => estado.{mapa} && estado.{mapa}._camada")
    return pg.evaluate(f"estado.{mapa}._camada.getLayers().map(l => l.options.fillColor)")


# --------------------------------------------------------------------------- painel
def test_painel_cartoes(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    pagina.wait_for_function("() => document.querySelectorAll('.cartao').length === 6")
    assert pagina.locator(".cartao h2").all_inner_texts() == [
        "Presidente — BRASIL", "Presidente — RJ", "Governador — RJ", "Senador — RJ",
        "Deputado Federal — RJ", "Deputado Estadual — RJ"]
    gov = cartao(pagina, "Governador")
    texto = gov.inner_text()
    for trecho in ("Eleitorado 13.319.487", "Comparecimento", "Abstenção", "Válidos", "Brancos", "Nulos",
                   "Anulados sub judice", "totalização 29/09/2026"):
        assert trecho in texto, trecho
    assert gov.locator("[role=progressbar]").count() == 1
    assert gov.locator(".lista .item").count() == 11  # todos os candidatos a governador
    assert "2 vagas" in cartao(pagina, "Senador").inner_text()
    dep = cartao(pagina, "Deputado Estadual")
    assert dep.get_by_role("heading", name="Partidos (nominais + legenda)", exact=True).count() == 1
    assert dep.locator(".lista").nth(1).locator(".item").count() > 0
    assert "Anulado sub judice" in gov.inner_text()  # destinação exibida ao lado da situação


def test_painel_mostra_html_como_texto(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    pagina.wait_for_function("() => document.querySelectorAll('.cartao').length === 6")
    assert pagina.query_selector("#injetado") is None  # o nome não virou elemento
    assert NOME_COM_HTML in cartao(pagina, "Governador").inner_text()


def test_painel_serie_temporal(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#painel")
    gov = cartao(pagina, "Governador")
    gov.locator("svg.serie").wait_for()
    assert gov.locator("svg.serie polyline").count() == 3            # 3 mais votados
    rotulos = gov.locator("svg.serie text.rotulo").all_text_contents()  # texto SVG: sem inner_text
    assert len(rotulos) == 3 and all(r.endswith("%") for r in rotulos)  # valor na ponta de cada linha
    assert gov.locator(".legenda-linha").last.locator("span.amostra").count() == 3
    # presidente: a eleição federal não avançou → um ponto só, aviso no lugar do gráfico
    assert "A série aparece a partir da 2ª totalização" in cartao(pagina, "Presidente — BRASIL").inner_text()

    dica = gov.locator(".dica")
    assert dica.is_hidden()
    gov.locator("svg.serie rect").hover()
    dica.wait_for(state="visible")
    assert "das seções" in dica.inner_text() and dica.locator("div").count() == 3
    pagina.mouse.move(0, 0)
    dica.wait_for(state="hidden")


# --------------------------------------------------------------------------- candidato
def test_evolucao_do_candidato(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"#candidato?cargo=3&numero={site['numero']}&municipio=60011")
    graf = pagina.locator("#evol-grafico svg.serie")
    graf.wait_for()
    assert graf.locator("polyline").count() == 2  # município e estado
    legenda = pagina.locator("#evol-grafico .legenda-linha").inner_text()
    assert "RIO DE JANEIRO" in legenda and "RJ" in legenda
    graf.locator("rect").hover()
    dica = pagina.locator("#evol-grafico .dica")
    dica.wait_for(state="visible")
    assert "votos" in dica.inner_text() and "das seções" in dica.inner_text()


# --------------------------------------------------------------------------- mapas
def test_mapa_mais_votado_cores_categoricas(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?cargo=3&metrica=vencedor")
    fills = preenchimentos(pagina, "mapa")
    assert len(fills) == 3
    permitidas = cores(pagina, "--serie-1", "--serie-2", "--serie-3", "--outros", "--sem-dado")
    assert set(fills) <= permitidas  # no máximo 3 cores categóricas + "Outros"
    itens = pagina.locator("#mapa-legenda div").all_inner_texts()
    assert itens[-2:] == ["Outros", "sem dado"] and len(itens) == 5


def test_mapa_sequencial_e_dica(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?cargo=3&metrica=abstencao_pct")
    fills = preenchimentos(pagina, "mapa")
    assert set(fills) <= cores(pagina, "--mapa-1", "--mapa-2", "--mapa-3", "--mapa-4", "--mapa-5", "--sem-dado")
    assert "sem dado" in pagina.locator("#mapa-legenda").inner_text()
    # amarelo = menos, vermelho = mais: a 1ª faixa da legenda é a mais clara (rodada 31, pedido do usuário)
    faixas = pagina.evaluate("""() => [...document.querySelectorAll('#mapa-legenda div')]
        .map(d => getComputedStyle(d.firstElementChild || d).backgroundColor)""")
    assert faixas[0] == "rgb(254, 217, 118)" and faixas[0] != faixas[-2]
    # passar o mouse sobre um município mostra a dica com o nome
    ponto = pagina.evaluate("""() => {
        const l = estado.mapa._camada.getLayers()[0];
        const v = l.getLatLngs()[0];  // centroide do polígono (o centro do retângulo envolvente pode cair na borda)
        const c = L.latLng(v.reduce((a, x) => a + x.lat, 0) / v.length, v.reduce((a, x) => a + x.lng, 0) / v.length);
        const p = estado.mapa.latLngToContainerPoint(c);
        const r = document.getElementById('mapa').getBoundingClientRect();
        return {x: r.left + p.x, y: r.top + p.y}; }""")
    # o Leaflet ignora o mouse enquanto anima o zoom do enquadramento inicial: espera o mapa parar
    pagina.wait_for_function("() => !estado.mapa._animatingZoom")
    for tentativa in range(20):
        pagina.mouse.move(ponto["x"] - 3, ponto["y"] - 3)
        pagina.mouse.move(ponto["x"], ponto["y"], steps=3)
        if pagina.locator(".leaflet-tooltip").count():
            break
        pagina.wait_for_timeout(150)
    pagina.locator(".leaflet-tooltip").wait_for(state="visible")
    assert "%" in pagina.locator(".leaflet-tooltip").inner_text()


def test_linha_do_tempo_reproduz_ate_o_fim(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?cargo=3&metrica=secoes_totalizadas_pct&momento=2026-09-29T16:00:00")
    rotulo = pagina.locator("#lt-rotulo")
    pagina.wait_for_function("() => document.getElementById('lt-rotulo').textContent.includes('totalização 1 de')")
    pagina.click("#lt-play")
    assert pagina.inner_text("#lt-play") == "⏸"
    pagina.wait_for_function("() => document.getElementById('lt-rotulo').textContent.includes('mais recente')"
                             " && document.getElementById('lt-play').textContent === '▶'", timeout=15_000)
    assert "totalização 4 de 4" in rotulo.inner_text()
    aba, q = endereco(pagina)
    assert "momento" not in q  # terminou no mais recente


# --------------------------------------------------------------------------- comparação
def test_comparacao_mapa_divergente(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?cargo=3&metrica=abstencao")
    fills = preenchimentos(pagina, "compMapa")
    divergente = cores(pagina, "--div-n3", "--div-n2", "--div-n1", "--div-0", "--div-p1", "--div-p2", "--div-p3",
                       "--sem-dado")
    assert set(fills) <= divergente
    legenda = pagina.locator("#comp-legenda").inner_text()
    for trecho in ("aumento maior que", "variação menor que ±", "redução maior que", "sem dado", "2026 − 2022"):
        assert trecho in legenda, trecho
    assert pagina.locator("#comp-fichas .ficha").count() == 3


# --------------------------------------------------------------------------- tema
@pytest.mark.parametrize("esquema,fundo", [("light", "rgb(249, 249, 247)"), ("dark", "rgb(13, 13, 13)")])
def test_modo_claro_e_escuro(nova_pagina, site: dict, esquema: str, fundo: str) -> None:
    pg = nova_pagina(color_scheme=esquema)
    abrir(pg, site, "#painel")
    pg.wait_for_function("() => document.querySelectorAll('.cartao').length === 6")
    assert pg.evaluate("getComputedStyle(document.body).backgroundColor") == fundo
    # as barras usam a cor da série do próprio tema (passos diferentes no escuro)
    esperado = {"light": "rgb(42, 120, 214)", "dark": "rgb(57, 135, 229)"}[esquema]
    assert pg.evaluate("getComputedStyle(document.querySelector('.progresso > div')).backgroundColor") == esperado


def test_mapa_de_intensidade_nao_inverte_no_tema_escuro(nova_pagina, site: dict) -> None:
    """Pedido do usuário: no escuro, menos votos também é amarelo e mais votos é vermelho (antes a rampa azul invertia)."""
    pg = nova_pagina(color_scheme="dark", viewport={"width": 1200, "height": 900})
    abrir(pg, site, "#mapas?cargo=3&metrica=abstencao_pct")
    preenchimentos(pg, "mapa")
    assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--mapa-1').trim()") == "#fed976"
    assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--mapa-5').trim()") == "#bd0026"
