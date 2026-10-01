"""Endereços das abas do site (#mapas?…, #candidato?…, #comparacao?…) num navegador de verdade.

Usa as fixtures `site`/`pagina` do conftest.py: o site numa porta livre com dados do TSE falso
(várias totalizações, para a linha do tempo) e uma referência 2022 sintética, no Chrome
instalado via Playwright (`channel="chrome"`), sem internet.

Rodar só estes:   pytest -q -m e2e        Pular:   pytest -q -m "not e2e"
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page  # noqa: E402

from conftest import E2E_T, abrir, endereco, esperar_endereco  # noqa: E402
from test_historico import NIT, RIO  # noqa: E402

pytestmark = pytest.mark.e2e
T1 = E2E_T[0]


# --------------------------------------------------------------------------- mapas
def test_mapa_link_abre_momento_e_regrava(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#mapas?cargo=3&metrica=secoes_totalizadas_pct&momento=2026-09-29T17:20:00")
    pagina.wait_for_function("() => document.getElementById('lt-rotulo').textContent.includes('totalização')")
    assert pagina.input_value("#mapa-cargo") == "3"
    assert pagina.input_value("#mapa-metrica") == "secoes_totalizadas_pct"
    assert "totalização 2 de 4" in pagina.inner_text("#lt-rotulo")  # última até 17h20 = 17h10
    pagina.wait_for_function("() => document.querySelector('#mapa-legenda h4')?.textContent.includes('às')")
    esperar_endereco(pagina, f"h.includes('momento={T1}')")  # regravado com a hora exata da totalização

    pagina.eval_on_selector("#lt-range", "e => { e.value = e.max; e.dispatchEvent(new Event('input')); }")
    esperar_endereco(pagina, "!h.includes('momento=')")  # no mais recente o link acompanha a apuração
    pagina.check("#mapa-locais")
    esperar_endereco(pagina, "h.includes('locais=1')")
    aba, q = endereco(pagina)
    assert aba == "mapas" and q == {"cargo": "3", "metrica": "secoes_totalizadas_pct", "locais": "1"}

    pagina.click("button[data-aba=painel]")
    esperar_endereco(pagina, "h === '#painel'")


def test_mapa_candidato_no_endereco(pagina: Page, site: dict) -> None:
    n = site["numero"]
    abrir(pagina, site, f"#mapas?cargo=3&metrica=votos_candidato&numero={n}")
    pagina.wait_for_function("() => document.querySelector('#mapa-legenda h4')")
    assert pagina.input_value("#mapa-numero") == str(n) and not pagina.is_disabled("#mapa-numero")
    aba, q = endereco(pagina)
    assert q["metrica"] == "votos_candidato" and q["numero"] == str(n)

    pagina.select_option("#mapa-metrica", "pct_candidato")  # troca pelo formulário: o endereço acompanha
    pagina.fill("#mapa-numero", "59")
    pagina.click("#form-mapa button[type=submit]")
    esperar_endereco(pagina, "h.includes('metrica=pct_candidato') && h.includes('numero=59')")


# --------------------------------------------------------------------------- candidato
def test_candidato_link_completo(pagina: Page, site: dict) -> None:
    n = site["numero"]
    abrir(pagina, site, f"#candidato?cargo=3&numero={n}&municipio={RIO}&ordem=NM_MUNICIPIO-asc")
    pagina.wait_for_selector("#cand-resultado table tbody tr")
    assert pagina.input_value("#evol-mun") == str(RIO)
    assert pagina.inner_text("#cand-resultado tbody tr:first-child td:first-child") == "NITERÓI"  # ordem alfabética

    pagina.click("#cand-resultado th:has-text('Votos')")
    esperar_endereco(pagina, "h.includes('ordem=VOTOS-desc')")
    pagina.select_option("#evol-mun", str(NIT))
    esperar_endereco(pagina, f"h.includes('municipio={NIT}')")
    aba, q = endereco(pagina)
    assert aba == "candidato" and q == {"cargo": "3", "numero": str(n), "municipio": str(NIT), "ordem": "VOTOS-desc"}


def test_candidato_formato_antigo(pagina: Page, site: dict) -> None:
    abrir(pagina, site, f"#candidato/3/{site['numero']}/{NIT}")
    pagina.wait_for_function(f"() => document.getElementById('evol-mun')?.value === '{NIT}'")
    esperar_endereco(pagina, f"h.startsWith('#candidato?') && h.includes('municipio={NIT}')")  # vira o formato novo


def test_planilha_no_endereco(pagina: Page, site: dict) -> None:
    n = site["numero"]
    abrir(pagina, site, f"#candidato?cargo=3&numero={n}&pl=1&pl_ano=2022&pl_cargo=deputado%20estadual"
                        "&pl_numero=13713&pl_municipio=Niter%C3%B3i&pl_comparar=2024")
    pagina.wait_for_function("() => document.getElementById('caixa-planilha').open "
                             "&& document.getElementById('pl-numero').value === '13713'")
    assert pagina.input_value("#pl-ano") == "2022" and pagina.input_value("#pl-cargo") == "deputado estadual"
    assert pagina.input_value("#pl-municipio") == "Niterói" and pagina.input_value("#pl-comparar") == "2024"
    assert pagina.input_value("#cand-numero") == str(n)  # a consulta é a do candidato; a planilha, a do link

    pagina.select_option("#pl-ano", "2024")
    esperar_endereco(pagina, "h.includes('pl_ano=2024')")
    pagina.click("#caixa-planilha summary")  # fecha o bloco: os campos pl_* saem do endereço
    esperar_endereco(pagina, "!h.includes('pl=1') && !h.includes('pl_')")


def test_planilha_sem_consulta(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#candidato?pl=1&pl_ano=2024&pl_cargo=vereador")
    pagina.wait_for_function("() => document.getElementById('caixa-planilha').open")
    assert pagina.input_value("#pl-cargo") == "vereador"
    assert pagina.get_attribute("button[data-aba=candidato]", "aria-selected") == "true"


# --------------------------------------------------------------------------- comparação
def test_comparacao_partido(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#comparacao?cargo=3&metrica=partido&partido=PL&ordem=NM_MUNICIPIO-asc")
    pagina.wait_for_selector("#comp-tabela tbody tr")
    assert pagina.input_value("#comp-cargo") == "3" and pagina.input_value("#comp-metrica") == "partido"
    assert pagina.input_value("#comp-partido") == "PL"
    assert pagina.inner_text("#comp-tabela tbody tr:first-child td:first-child") == "NITERÓI"
    assert "PL" in pagina.inner_text("#comp-fichas")

    pagina.click("#comp-tabela th:has-text('Diferença')")
    esperar_endereco(pagina, "h.includes('ordem=DIF-desc')")
    aba, q = endereco(pagina)
    assert aba == "comparacao" and q == {"cargo": "3", "metrica": "partido", "partido": "PL", "ordem": "DIF-desc"}


def test_comparacao_candidatos_e_valores_invalidos(pagina: Page, site: dict) -> None:
    n = site["numero"]
    abrir(pagina, site, f"#comparacao?cargo=3&metrica=candidato&numero_a=22&numero_b={n}")
    pagina.wait_for_function("() => document.getElementById('comp-fichas').textContent.includes('nº 22')")
    assert pagina.input_value("#comp-num-a") == "22" and pagina.is_visible("#comp-num-b")

    abrir(pagina, site, "#comparacao?cargo=99&metrica=inventada")  # valores desconhecidos: ignorados
    pagina.reload()
    pagina.wait_for_selector("#comp-tabela tbody tr")
    assert pagina.input_value("#comp-cargo") == "3" and pagina.input_value("#comp-metrica") == "abstencao"


# --------------------------------------------------------------------------- copiar link
@pytest.mark.parametrize("hash_,botao", [
    ("#mapas?cargo=3&metrica=vencedor", "#copiar-link"),
    ("#comparacao?cargo=3&metrica=abstencao", "#comp-copiar"),
])
def test_copiar_link(pagina: Page, site: dict, hash_: str, botao: str) -> None:
    abrir(pagina, site, hash_)
    aba = hash_[1:].split("?")[0]
    pagina.wait_for_function(f"() => location.hash.startsWith('#{aba}?') && "
                             "document.querySelector('.legenda h4')")
    pagina.click(botao)
    copiado = pagina.evaluate("navigator.clipboard.readText()")
    assert copiado == site["url"] + pagina.evaluate("location.hash")
