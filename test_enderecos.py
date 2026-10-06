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


def test_historico_no_endereco(pagina: Page, site: dict) -> None:
    """Resultado por município × 2022: indicado à mão pelo link (cargo 3, nº 22 do 2022 sintético)."""
    n = site["numero"]
    abrir(pagina, site, f"#candidato?cargo=3&numero={n}&hist=1&hist_cargo=3&hist_numero=22")
    pagina.wait_for_function("() => document.querySelector('#hist-resultado table tbody tr')")
    texto = pagina.inner_text("#hist-resultado")
    assert "indicado à mão" in texto and "Votos 2022" in texto and "Variação dos votos" in texto
    href = pagina.get_attribute("#hist-resultado a.botao-salvar", "href")
    assert href == f"api/candidato/historico/planilha?cargo=3&numero={n}&numero_ref=22&cargo_ref=3"
    r = pagina.request.get(site["url"] + href)
    assert r.ok and r.body()[:2] == b"PK"
    aba, q = endereco(pagina)
    assert aba == "candidato" and (q["hist"], q["hist_cargo"], q["hist_numero"]) == ("1", "3", "22")

    pagina.fill("#hist-numero", "")  # volta à identificação pelo nome civil
    pagina.click("#form-historico button[type=submit]")
    esperar_endereco(pagina, "h.includes('hist=1') && !h.includes('hist_numero')")
    pagina.wait_for_function("() => !document.getElementById('hist-resultado').textContent.includes('indicado')")
    pagina.click("#caixa-historico summary")  # fecha: hist sai do endereço
    esperar_endereco(pagina, "!h.includes('hist')")


def test_historico_nome_com_html(pagina: Page, site: dict) -> None:
    abrir(pagina, site, "#candidato")
    cands = pagina.evaluate("() => fetch('api/candidatos?cargo=3').then((r) => r.json())")
    n = next(c["NUMERO"] for c in cands if "injetado" in c["NOME_URNA"])
    abrir(pagina, site, f"#candidato?cargo=3&numero={n}&hist=1")
    pagina.wait_for_function("() => document.getElementById('hist-resultado').textContent.includes('CANDIDATO HTML')")
    assert "CANDIDATO HTML</b>" in pagina.inner_text("#hist-resultado")  # como texto
    assert pagina.query_selector("#injetado") is None


# --------------------------------------------------------------------------- comparação
def test_bancadas_no_endereco(pagina: Page, site: dict) -> None:
    """Rodada 45: bloco de bancadas aberto pelo endereço, com o cargo; fechar tira do endereço."""
    abrir(pagina, site, "#comparacao?cargo=3&metrica=abstencao&banc=1&banc_cargo=6")
    pagina.wait_for_function("() => document.getElementById('comp-bancadas').open "
                             "&& document.getElementById('banc-resultado').textContent.length > 0 "
                             "&& !document.getElementById('banc-resultado').textContent.includes('Carregando')")
    assert pagina.input_value("#banc-cargo") == "6"
    esperar_endereco(pagina, "h.includes('banc=1') && h.includes('banc_cargo=6')")
    pagina.select_option("#banc-cargo", "7")
    esperar_endereco(pagina, "h.includes('banc_cargo=7')")
    pagina.click("#comp-bancadas summary")
    esperar_endereco(pagina, "!h.includes('banc')")


def test_variacao_partidos_no_endereco(pagina: Page, site: dict) -> None:
    """Bloco "Gráfico da variação por partido": escolha (na ordem do link) e no máximo 3 partidos."""
    abrir(pagina, site, "#comparacao?cargo=3&metrica=abstencao&var=1&var_partidos=PSB,PL&var_ponderar=1")
    pagina.wait_for_function("() => document.querySelectorAll('#var-partidos input').length >= 4")
    assert pagina.evaluate("() => partidosVar()") == ["PSB", "PL"]
    assert pagina.is_checked("#var-ponderar")
    # 2022 sintético × TSE falso: os partidos não se correspondem (ou têm < 3 municípios) — a API explica o motivo
    pagina.wait_for_function("() => /sem correspondente|menos de 3/.test("
                             "document.querySelector('#var-resultado .aviso')?.textContent || '')")
    esperar_endereco(pagina, "h.includes('var_partidos=PSB,PL') && h.includes('var_ponderar=1')")
    pagina.locator("#var-partidos input:not(:checked)").nth(0).check()
    assert pagina.locator("#var-partidos input:disabled").count() == pagina.locator("#var-partidos input").count() - 3
    pagina.click("#comp-variacao summary")  # fecha: var sai do endereço
    esperar_endereco(pagina, "!h.includes('var')")


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


# --------------------------------------------------------------------------- várias UFs (rodada 39)
def test_seletor_de_uf(pagina: Page, site: dict, site_multi: dict) -> None:
    """O seletor só existe no site de várias UFs; trocar de UF mantém a aba e o endereço."""
    abrir(pagina, site, "#painel")
    pagina.wait_for_function("() => document.getElementById('titulo').textContent.includes('RJ')")
    assert pagina.is_hidden("#seletor-uf-rotulo")  # site de uma UF: /ufs.json não existe

    n = site_multi["numero"]
    pagina.goto(site_multi["url"] + f"#candidato?cargo=3&numero={n}")
    pagina.wait_for_url("**/rj/**")  # a raiz leva à UF padrão
    pagina.wait_for_function("() => !document.getElementById('seletor-uf-rotulo').hidden")
    opcoes = pagina.eval_on_selector_all("#seletor-uf option", "os => os.map(o => [o.value, o.disabled])")
    assert opcoes == [["RJ", False], ["AC", False], ["SP", True]] and pagina.input_value("#seletor-uf") == "RJ"
    pagina.select_option("#seletor-uf", "AC")
    pagina.wait_for_url("**/ac/**")
    pagina.wait_for_function("() => document.getElementById('titulo').textContent.includes('AC')")
    assert pagina.input_value("#seletor-uf") == "AC"
    aba, q = endereco(pagina)
    assert aba == "candidato" and q["numero"] == str(n)
