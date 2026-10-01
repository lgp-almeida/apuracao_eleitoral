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
