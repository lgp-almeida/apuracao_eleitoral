"""Locais e seções de um bairro (`apuracao/locais_bairro.py` + `locais_por_bairro.py`), no cadastro sintético."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

import locais_por_bairro as cli
from apuracao import bairros as br
from apuracao import eleitorado as el
from apuracao import locais_bairro as lb
from conftest import escrever_bairros


@pytest.fixture
def secoes_2026(tse_cache: Path) -> pl.DataFrame:
    return el.load_sections(2026, "RJ", tse_cache)


def test_cadastro_ignora_acento_e_caixa_e_inclui_agregada(secoes_2026: pl.DataFrame) -> None:
    locais = lb.locais_do_bairro(secoes_2026, "centro")
    # Pedro II (Rio, "Centro"), Escola X (Rio, "CENTRO") e o Pedro II de Niterói: o bairro-texto se repete entre municípios
    assert locais.select("NM_MUNICIPIO", "NR_LOCAL_VOTACAO").rows() == [
        ("NITERÓI", 1015), ("RIO DE JANEIRO", 1015), ("RIO DE JANEIRO", 1023)]
    tab = lb.secoes_dos_locais(secoes_2026, locais.filter(pl.col("NM_MUNICIPIO") == "RIO DE JANEIRO"))
    assert tab.select("NR_LOCAL_VOTACAO", "NR_SECAO", "TIPO_SECAO", "NR_SECAO_PRINCIPAL").rows() == [
        (1015, 10, "PRINCIPAL", None), (1015, 11, "PRINCIPAL", None), (1015, 12, "PRINCIPAL", None),
        (1015, 13, "AGREGADA", 12), (1023, 20, "PRINCIPAL", None)]
    assert tab["QT_ELEITOR_SECAO"].sum() == 310 + 290 + 260 + 95 + 150


def test_exato_por_padrao_e_contem_sob_pedido(secoes_2026: pl.DataFrame) -> None:
    assert lb.locais_do_bairro(secoes_2026, "LAP").is_empty()
    assert lb.locais_do_bairro(secoes_2026, "LAP", contem=True)["NR_LOCAL_VOTACAO"].to_list() == [1040]
    assert lb.sugestoes(secoes_2026, "lap") == ["LAPA"]


def test_fonte_ibge_usa_a_coordenada_e_nao_o_texto(tse_cache: Path, secoes_2026: pl.DataFrame) -> None:
    escrever_bairros(tse_cache)
    geo = br.malha("RJ", tse_cache)
    # a Escola X de 2026 diz "CENTRO" no cadastro, mas a coordenada cai na Lapa Sintética da malha;
    # a Creche Nova não tem coordenada e fica de fora
    lapa = lb.locais_do_bairro(secoes_2026, "Lapa Sintetica", fonte="ibge", geo=geo)
    assert lapa.select("NR_LOCAL_VOTACAO", "BAIRRO").rows() == [(1023, "Lapa Sintética")]
    assert lb.locais_do_bairro(secoes_2026, "Centro Sintético", fonte="ibge", geo=geo)["NR_LOCAL_VOTACAO"].to_list() == [1015]


def test_fonte_ibge_sem_malha_falha(secoes_2026: pl.DataFrame) -> None:
    with pytest.raises(ValueError, match="malha"):
        lb.locais_do_bairro(secoes_2026, "Centro", fonte="ibge")


def test_cli_imprime_e_grava_csv(tse_cache: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    saida = tmp_path / "out" / "centro.csv"
    rc = cli.main(["CENTRO", "--ano", "2026", "--municipio", "Rio de Janeiro", "--cache-dir", str(tse_cache),
                   "--saida", str(saida)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Zona 4 · Local 1015 — COLEGIO PEDRO II" in out
    assert "Seções: 10, 11, 12, 13 (agregada à 12)" in out
    assert "4 seções, 955 eleitores" in out
    assert "Total: 2 locais, 5 seções, 1.105 eleitores" in out
    assert "NITERÓI" not in out
    assert pl.read_csv(saida, separator=";").height == 5


def test_cli_sem_resultado_sugere_e_devolve_1(tse_cache: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert cli.main(["Lap", "--ano", "2026", "--cache-dir", str(tse_cache)]) == 1
    assert "LAPA" in caplog.text
