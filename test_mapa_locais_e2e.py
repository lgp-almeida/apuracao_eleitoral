"""Mapa por local de votação na aba Mapas (rodada 32), no Chrome: pontos, camadas, endereço e cores."""

from __future__ import annotations

import pytest

from conftest import CAND, abrir

pytestmark = pytest.mark.e2e
BASE = "#mapas?cargo=13&metrica=pct_candidato&detalhe=locais&ano_bairros=2024"


def _pronto(pg) -> None:
    pg.wait_for_function("() => estado.mapa && estado.mapa._export && estado.mapa._export.camada === 'locais'")


def test_pontos_de_voto_com_a_rampa_de_mapas(pagina, site) -> None:
    abrir(pagina, site, f"{BASE}&camada=voto&numero={CAND}")
    _pronto(pagina)
    cores = pagina.evaluate("Object.values(estado.mapa._export.cores)")
    rampa = pagina.evaluate("['--mapa-1','--mapa-2','--mapa-3','--mapa-4','--mapa-5']"
                            ".map(v => getComputedStyle(document.documentElement).getPropertyValue(v).trim())")
    assert len(cores) == 4 and set(cores) <= set(rampa)          # amarelo (menos) -> vermelho (mais)
    assert pagina.locator("#mapa-l-camada").is_visible() and pagina.locator("#mapa-l-locais").is_hidden()
    assert "4 de 4 locais com valor" in pagina.inner_text("#locais-nota")
    assert "Área do ponto" in pagina.inner_text("#mapa-legenda")
    assert "camada=voto" in pagina.evaluate("location.hash")


def test_camada_de_residuo_e_perfil(pagina, site) -> None:
    abrir(pagina, site, f"{BASE}&camada=residuo&indicador=renda_media&numero={CAND}")
    _pronto(pagina)
    assert pagina.locator("#mapa-l-indicador").is_visible() and pagina.locator("#mapa-l-metrica").is_hidden()
    assert pagina.locator("#mapa-numero").is_enabled()
    # o sintético tem poucos votos por local: nenhum passa do mínimo de 50 válidos, e a página explica
    assert "Nenhum local com 50 votos válidos" in pagina.inner_text("#locais-nota")
    # trocar para a camada de perfil: o número sai de cena e o endereço acompanha
    pagina.select_option("#mapa-camada", "perfil")
    pagina.wait_for_function("() => location.hash.includes('camada=perfil')")
    _pronto(pagina)
    assert pagina.locator("#mapa-numero").is_disabled()
    assert "Renda média" in pagina.inner_text("#mapa-legenda")


def test_voltar_para_municipios(pagina, site) -> None:
    abrir(pagina, site, f"{BASE}&camada=voto&numero={CAND}")
    _pronto(pagina)
    pagina.select_option("#mapa-detalhe", "municipios")
    pagina.wait_for_function("() => estado.detalhe === 'municipios' && !location.hash.includes('camada=')")
    assert pagina.locator("#mapa-l-camada").is_hidden() and pagina.locator("#mapa-l-locais").is_visible()


def test_camada_de_variacao(pagina, site) -> None:
    """Rodada 46 (17a): o sintético só tem 2024; a resposta da API vem pronta (rota interceptada) para
    conferir os controles, a legenda divergente com "subiu/caiu" e o endereço."""
    import json
    resposta = {"camada": "variacao", "tipo": "divergente", "unidade": "p.p.", "ano": 2024, "ano_ref": 2020,
                "lados": ["2020", "2024"], "sentido": "variacao",
                "rotulo": "Variação (p.p.) de % dos válidos do PSD — Vereador, 2020 → 2024",
                "cobertura": {"locais": 4, "com_valor": 3},
                "itens": [{"u": f"u{i}", "lat": -22.9 - i / 100, "lon": -43.2, "nome": f"L{i}", "mun": "RIO", "zona": 4,
                           "local": 1000 + i, "eleitores": 300, "valor": d, "antes": 30.0, "depois": 30.0 + d}
                          for i, d in enumerate((-6.0, 0.5, 8.0))]}
    pagina.route("**/api/mapa/locais?*camada=variacao*",
                 lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(resposta)))
    abrir(pagina, site, f"{BASE}&camada=variacao&numero=55")
    _pronto(pagina)
    assert pagina.locator("#mapa-l-metrica").is_visible() and pagina.locator("#mapa-l-indicador").is_hidden()
    assert pagina.locator("#mapa-numero").is_enabled()
    assert pagina.evaluate("document.querySelector('#mapa-metrica option[value=vencedor]').disabled")
    leg = pagina.inner_text("#mapa-legenda")
    assert "subiu mais de" in leg and "caiu mais de" in leg and "estável" in leg
    assert "presentes em 2020 e 2024" in pagina.inner_text("#locais-nota")
    h = pagina.evaluate("location.hash")
    assert "camada=variacao" in h and "numero=55" in h and "indicador=" not in h
    cores = set(pagina.evaluate("Object.values(estado.mapa._export.cores)"))
    div = set(pagina.evaluate("['--div-n3','--div-n2','--div-n1','--div-0','--div-p1','--div-p2','--div-p3']"
                              ".map(v => getComputedStyle(document.documentElement).getPropertyValue(v).trim())"))
    assert len(cores) == 3 and cores <= div


def test_camada_destino_dos_eliminados(pagina, site) -> None:
    """Rodada 47 (17b): a camada pede o 2º turno e a métrica da transferência; resposta interceptada (o sintético
    não tem 2º turno)."""
    import json
    pedidos = []
    resposta = {"camada": "transferencia", "tipo": "divergente", "unidade": "p.p.", "ano": 2024,
                "rotulo": "Abstenção extra no 2º turno (p.p.) — Prefeito 2024, 1º → 2º turno",
                "lados": ["1º turno", "2º turno"], "sentido": "variacao", "finalistas": ["A (X)", "B (Y)"],
                "cobertura": {"locais": 4, "com_valor": 2},
                "itens": [{"u": f"u{i}", "lat": -22.9 - i / 100, "lon": -43.2, "nome": f"L{i}", "mun": "RIO", "zona": 4,
                           "local": 1000 + i, "eleitores": 300, "valor": d, "antes": 20.0, "depois": 20.0 + d}
                          for i, d in enumerate((-2.0, 3.0))]}

    def responder(r):
        pedidos.append(r.request.url)
        r.fulfill(status=200, content_type="application/json", body=json.dumps(resposta))
    pagina.route("**/api/mapa/locais?*camada=transferencia*", responder)
    abrir(pagina, site, f"{BASE}&camada=transferencia&transf=abst_extra")
    _pronto(pagina)
    assert pagina.locator("#mapa-l-transf").is_visible() and pagina.locator("#mapa-l-metrica").is_hidden()
    assert pagina.locator("#mapa-l-indicador").is_hidden() and pagina.locator("#mapa-numero").is_disabled()
    assert "metrica=abst_extra" in pedidos[-1] and "turno=2" in pedidos[-1]
    assert "subiu mais de" in pagina.inner_text("#mapa-legenda")
    assert "estimado por município" in pagina.inner_text("#locais-nota")
    h = pagina.evaluate("location.hash")
    assert "camada=transferencia" in h and "transf=abst_extra" in h and "indicador=" not in h
