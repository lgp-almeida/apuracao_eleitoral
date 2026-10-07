"""Catálogo de contagens do universo do Censo 2022 por setor (apuracao.censo, rodada 49) — offline."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from apuracao import bairros as br
from apuracao import censo as cs
from apuracao import ibge
from apuracao import perfil as pf
from apuracao import perfil_local as pfl
from conftest import BAIRRO_A, BAIRRO_B, download_sem_rede, escrever_bairros, escrever_setores

PEDRO, ESCOLA_X, CIEP, NITEROI = "3304557000401015", "3304557000401023", "3304557000401031", "3303302007101015"


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    download_sem_rede(monkeypatch)


def test_catalogo_aponta_para_fontes_do_ibge() -> None:
    assert set(cs.colunas_por_fonte()) <= set(ibge.POR_CHAVE)
    assert cs.colunas_por_fonte()["setores_alfabetizacao"] == ["V00900", "V00901"]
    assert set(cs.COLUNAS) == {f"{x}_{k}" for k in cs.INDICADORES for x in ("N", "D")}
    assert not set(cs.INDICADORES) & set(pf.INDICADORES_TSE)  # nunca a mesma chave de um indicador do TSE


def test_contagens_com_sigilo_por_indicador() -> None:
    brutos = pl.DataFrame({"CD_SETOR": ["1", "2"], "V00900": ["90", "X"], "V00901": ["10", "5"],
                           "V00001": ["200", "100"], "V00049": ["50", "0"], "V00017": ["X", "20"]})
    c = {r["CD_SETOR"]: r for r in cs.contagens(brutos).iter_rows(named=True)}
    assert (c["1"]["N_pct_alfabetizados"], c["1"]["D_pct_alfabetizados"]) == (90, 100)
    assert c["2"]["N_pct_alfabetizados"] is None and c["2"]["D_pct_alfabetizados"] is None  # "X": fora da conta
    assert (c["2"]["N_pct_apartamentos"], c["2"]["D_pct_apartamentos"]) == (0, 100)  # zero de verdade ≠ sigilo
    assert c["1"]["N_pct_unipessoais"] is None and c["2"]["N_pct_unipessoais"] == 20  # sigilo só no indicador dele
    assert c["1"]["N_pct_rua_pavimentada"] is None  # fonte ausente (entorno): sem dado, nunca zero


def test_taxas_somam_numeradores_e_denominadores() -> None:
    st = pl.DataFrame({"U": ["a", "a", "b", "c"], "N_pct_apartamentos": [10.0, 30.0, None, 0.0],
                       "D_pct_apartamentos": [100.0, 100.0, None, 0.0]})
    t = {r["U"]: r for r in cs.taxas(st, "U").iter_rows(named=True)}
    assert t["a"]["pct_apartamentos"] == 20  # (10 + 30) / (100 + 100), não a média de 10% e 30% por acaso
    assert t["b"]["pct_apartamentos"] is None and t["c"]["pct_apartamentos"] is None  # sem dado / denominador 0


def test_catalogo_por_local(tse_cache: Path) -> None:
    escrever_setores(tse_cache)
    st = pfl.setores("RJ", tse_cache)
    ag = {r["UNIDADE"]: r for r in pfl.agregar(st, pfl.ligar("RJ", tse_cache, pfl.locais(2024, "RJ", tse_cache),
                                                                 "influencia")).iter_rows(named=True)}
    assert ag[PEDRO]["pct_apartamentos"] == pytest.approx(90) and ag[CIEP]["pct_apartamentos"] == pytest.approx(20)
    assert ag[CIEP]["pct_alfabetizados"] is None  # sigilo só na alfabetização do setor do CIEP
    assert ag[NITEROI]["pct_esgoto_rede"] == pytest.approx((60 + 10) / 2)  # urbano + rural, D = 100 cada


def test_catalogo_por_bairro(tse_cache: Path) -> None:
    escrever_bairros(tse_cache)
    escrever_setores(tse_cache)
    pv = pf.PerfilVoto(br.ComparacaoBairros(br.Bairros("RJ", tse_cache)))
    c = {r["CD_BAIRRO"]: r for r in pv.censo().iter_rows(named=True)}
    assert c[BAIRRO_A]["pct_apartamentos"] == pytest.approx(90)
    assert c[BAIRRO_B]["pct_apartamentos"] == pytest.approx((50 + 20) / 2)  # dois setores no bairro B
    assert c[BAIRRO_B]["pct_alfabetizados"] == pytest.approx(50)  # o do CIEP (sigilo) sai só desse indicador
    assert c[BAIRRO_A]["renda_media"] == 8000.5  # os indicadores dos agregados por bairro continuam
    ind = pv.indicadores()
    assert ind["pct_apartamentos"]["fonte"] == "IBGE — Censo 2022 (domicílios)"
    assert ind["pct_alfabetizados"]["fonte"] == "IBGE — Censo 2022 (moradores)"


def test_catalogo_sem_setores_nao_derruba_o_bairro(tse_cache: Path) -> None:
    escrever_bairros(tse_cache)  # sem setores no cache e sem rede: o catálogo fica sem dado, o resto segue
    pv = pf.PerfilVoto(br.ComparacaoBairros(br.Bairros("RJ", tse_cache)))
    c = {r["CD_BAIRRO"]: r for r in pv.censo().iter_rows(named=True)}
    assert c[BAIRRO_A]["renda_media"] == 8000.5 and c[BAIRRO_A]["pct_apartamentos"] is None


def test_leitura_dos_setores_em_streaming(tmp_path: Path) -> None:
    """Só a UF pedida; a chave "setor" (domicílio 2) vira CD_SETOR; coluna ausente fica de fora; sem repetição."""
    import zipfile
    zp = tmp_path / "Agregados_por_setores_caracteristicas_domicilio2_BR_20250417.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("x.csv", '"setor";"V00111";"V00238"\n"330455705000001";"10";"X"\n"350000105000001";"99";"0"\n'
                            '"330455705000002";"20";"1"\n')
    df = pfl._ler_setores_csv(zp, "33", ["CD_SETOR", "V00111", "V00111", "V09999"])
    assert df.columns == ["CD_SETOR", "V00111"] and df["CD_SETOR"].to_list() == ["330455705000001", "330455705000002"]
