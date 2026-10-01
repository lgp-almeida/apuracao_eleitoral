"""Projeção das cadeiras de deputado (consolidados × em disputa): σ calibrado, simulação e API — offline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from apuracao import cadeiras as cd
from apuracao import projecao_cadeiras as pc
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import FakeTSE
from test_cadeiras import AGREMIACOES, CANDIDATOS


def test_sigma_calibrado_diminui_com_a_apuracao() -> None:
    sa = [pc.sigma(p)[0] for p in (5, 15, 45, 75, 95)]
    sc = [pc.sigma(p)[1] for p in (5, 15, 45, 75, 95)]
    assert sa == sorted(sa, reverse=True) and sc == sorted(sc, reverse=True)
    assert all(c > a for a, c in zip(sa, sc))  # candidato erra mais que agremiação
    assert pc.sigma(100) == (0.0, 0.0)


@pytest.mark.parametrize("freq,eleito,esperado", [(0.99, True, "consolidado"), (0.95, True, "consolidado"),
                                                  (0.6, True, "em disputa (dentro)"), (0.3, False, "em disputa (fora)"),
                                                  (0.01, False, "fora")])
def test_status(freq: float, eleito: bool, esperado: str) -> None:
    assert pc.status(freq, eleito) == esperado


def _dois_municipios(fracao_m2: float) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """O cenário à mão de test_cadeiras (10 vagas, 1.000 válidos) repartido em 2 municípios iguais; o 2º
    com `fracao_m2` do eleitorado apurado (votos na mesma proporção)."""
    mun = pl.DataFrame({"CD_MUNICIPIO": [1, 2], "ELEITORADO": [1000, 1000],
                        "APURADO": [1000, int(1000 * fracao_m2)], "VALIDOS": [500, int(500 * fracao_m2)]})
    va = pl.concat([AGREMIACOES.select("AGREMIACAO", (pl.col("VOTOS") / 2).alias("VOTOS")).with_columns(pl.lit(m).alias("CD_MUNICIPIO"))
                    for m in (1, 2)]).with_columns(
        pl.when(pl.col("CD_MUNICIPIO") == 2).then(pl.col("VOTOS") * fracao_m2).otherwise(pl.col("VOTOS")).alias("VOTOS"))
    vc = pl.concat([CANDIDATOS.filter(pl.col("VALIDO")).select("NUMERO", (pl.col("VOTOS") / 2).alias("VOTOS"))
                    .with_columns(pl.lit(m).alias("CD_MUNICIPIO")) for m in (1, 2)]).with_columns(
        pl.when(pl.col("CD_MUNICIPIO") == 2).then(pl.col("VOTOS") * fracao_m2).otherwise(pl.col("VOTOS")).alias("VOTOS"))
    return mun, va, vc, CANDIDATOS.select("AGREMIACAO", "NUMERO", "NOME", "VALIDO", "DESEMPATE")


def test_apuracao_completa_consolida_todos_os_eleitos() -> None:
    mun, va, vc, info = _dois_municipios(1.0)
    p = pc.projetar_cadeiras(mun, va, vc, info, vagas=10, n_sim=50)
    assert p.pct_apurado == 100 and p.base.qe == 100
    ag = {r["AGREMIACAO"]: (r["VAGAS"], r["VAGAS_MIN"], r["VAGAS_MAX"]) for r in p.agremiacoes.iter_rows(named=True)}
    assert ag == {"A": (4, 4, 4), "B": (2, 2, 2), "C": (3, 3, 3), "D": (1, 1, 1), "E": (0, 0, 0)}  # sem incerteza
    st = dict(zip(p.candidatos["NOME"], p.candidatos["STATUS"]))
    assert {n for n, s in st.items() if s == "consolidado"} == {"A1", "A2", "A3", "A5", "B1", "C1", "C2", "D1", "C3", "B2"}


def test_apuracao_parcial_separa_consolidados_da_disputa() -> None:
    mun, va, vc, info = _dois_municipios(0.4)  # 70% do eleitorado apurado
    p = pc.projetar_cadeiras(mun, va, vc, info, vagas=10, n_sim=300)
    assert p.pct_apurado == pytest.approx(70)
    st = dict(zip(p.candidatos["NOME"], p.candidatos["STATUS"]))
    freq = dict(zip(p.candidatos["NOME"], p.candidatos["FREQ_ELEITO"]))
    assert st["A1"] == st["B1"] == "consolidado"  # 200 e 240 votos: longe de qualquer corte
    assert st["A5"] != "consolidado" and st["A4"].startswith("em disputa")  # empate 15 × 15: moeda
    assert 0.2 < freq["A5"] < 0.8 and freq["A1"] == 1.0
    assert st["C4"] == "fora"  # sub judice nunca entra
    a = p.agremiacoes.filter(pl.col("AGREMIACAO") == "A").row(0, named=True)
    assert a["VAGAS_MIN"] <= a["VAGAS"] <= a["VAGAS_MAX"]
    # a mesma semente dá o mesmo resultado (o painel não "pisca" entre atualizações sem dado novo)
    p2 = pc.projetar_cadeiras(mun, va, vc, info, vagas=10, n_sim=300)
    assert p2.candidatos["FREQ_ELEITO"].to_list() == p.candidatos["FREQ_ELEITO"].to_list()


def test_votos_por_secao_da_apuracao_de_2022() -> None:
    import votos_por_local_votacao as v
    votos = pl.LazyFrame({"NR_TURNO": [1] * 5, "DS_CARGO": ["DEPUTADO ESTADUAL"] * 5, "CD_MUNICIPIO": [1] * 5,
                          "NR_ZONA": [1] * 5, "NR_SECAO": [1, 1, 1, 2, 2], "NR_VOTAVEL": [11111, 11, 22222, 99999, 95],
                          "QT_VOTOS": [10, 3, 7, 50, 4]})
    info = pl.DataFrame({"AGREMIACAO": ["P11", "P22", "P99"], "NUMERO": [11111, 22222, 99999],
                         "NOME": ["X", "Y", "Z"], "VALIDO": [True, True, False]})
    agr, cand = pc.votos_secao_deputado(votos, info, "deputado estadual")
    assert dict(zip(agr["AGREMIACAO"], agr["VOTOS"])) == {"P11": 13, "P22": 7}  # legenda 11 → P11; 99999 anulado; 95 fora
    assert set(cand["NUMERO"]) == {11111, 22222}
    secoes = pl.DataFrame({"CD_MUNICIPIO": [1, 1], "NR_ZONA": [1, 1], "NR_SECAO": [1, 2], "APTOS": [100, 100],
                           "T": [datetime(2022, 10, 2, 18), datetime(2022, 10, 2, 19)]})
    mun, va, vc = pc.estado_em(secoes, agr, cand, datetime(2022, 10, 2, 18, 30))
    assert mun.row(0, named=True)["VALIDOS"] == 20 and mun.row(0, named=True)["APURADO"] == 100  # válidos com legenda
    assert v is not None


# --------------------------------------------------------------------------- API
@pytest.fixture()
def site(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> TestClient:
    dados = tmp_path / "dados"
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados)
    col.ciclo()
    fake_tse.avancar_uf(21272, "19:00:00", 40.0, 1.0)  # deputados a 40% das seções na UF
    col.ciclo()
    return TestClient(create_app(dados, "RJ", tse_cache))


def test_api_projecao_de_cadeiras(site: TestClient) -> None:
    r = site.get("/api/cadeiras?cargo=7").json()
    p = r["projecao"]
    assert p["ativa"] and p["simulacoes"] == pc.N_SIM and p["limiar"] == pc.LIMIAR
    assert p["consolidados"] + p["em_disputa_dentro"] == r["vagas"] - r["vagas_nao_preenchidas"]
    assert all(a["VAGAS_MIN"] <= a["VAGAS"] <= a["VAGAS_MAX"] for a in p["agremiacoes"])
    assert {c["STATUS"] for c in p["candidatos"]} <= {"consolidado", "em disputa (dentro)", "em disputa (fora)"}
    card = next(c for c in site.get("/api/painel").json()["cartoes"] if c["cargo"] == 7)
    assert card["cadeiras"]["projecao"]["consolidados"] == p["consolidados"] and "candidatos" not in card["cadeiras"]["projecao"]
    k = site.get(f"/api/candidato?cargo=7&numero={p['candidatos'][0]['NUMERO']}").json()["cadeira"]
    assert k["projecao"]["status"] == p["candidatos"][0]["STATUS"]


# --------------------------------------------------------------------------- dados reais (regressão)
CACHE_REAL = Path(__file__).parent / "cache_tse"


@pytest.mark.skipif(not (CACHE_REAL / "votacao_candidato_munzona_2022.zip").exists()
                    or not (CACHE_REAL / "detalhe_votacao_secao_2022.zip").exists(),
                    reason="microdados de 2022 fora do cache")
def test_apuracao_real_do_rj_2022_a_metade() -> None:
    """Dep. Estadual RJ 2022 com 50% apurado: nenhum consolidado errado e faixas cobrindo as cadeiras oficiais."""
    import votos_por_local_votacao as v
    from apuracao import projecao as pj
    agr, cand, vagas, validos = cd.entrada_munzona(2022, "RJ", 7, CACHE_REAL)
    oficiais = set(cand.filter(pl.col("SITUACAO_TSE").str.starts_with("ELEITO"))["NUMERO"])
    of_vagas = dict(cd.distribuir(agr, cand, vagas, validos).agremiacoes.select("AGREMIACAO", "VAGAS").iter_rows())
    secoes = pj.secoes_com_hora(2022, "RJ", 7, 1, CACHE_REAL)
    va_s, vc_s = pc.votos_secao_deputado(v.load_section_votes(2022, "RJ", "deputado estadual", CACHE_REAL, False),
                                         cand, "DEPUTADO ESTADUAL")
    (_, t), = pc.momentos(secoes, [50])
    p = pc.projetar_cadeiras(*pc.estado_em(secoes, va_s, vc_s, t),
                             cand.select("AGREMIACAO", "NUMERO", "NOME", "VALIDO").with_columns(pl.lit(None, pl.Int64).alias("DESEMPATE")),
                             vagas)
    consolidados = set(p.candidatos.filter(pl.col("STATUS") == "consolidado")["NUMERO"])
    assert len(consolidados) >= 40 and consolidados <= oficiais
    cobre = [r["VAGAS_MIN"] <= of_vagas.get(r["AGREMIACAO"], 0) <= r["VAGAS_MAX"] for r in p.agremiacoes.iter_rows(named=True)]
    assert all(cobre)


def test_mesma_semente_mesmo_resultado_em_qualquer_ordem() -> None:
    """A ordem de entrada (um group_by sem ordem, por exemplo) não pode mudar as simulações."""
    mun, va, vc, info = _dois_municipios(0.4)
    a = pc.projetar_cadeiras(mun, va, vc, info, vagas=10, n_sim=200)
    b = pc.projetar_cadeiras(mun, va.reverse(), vc.reverse(), info.reverse(), vagas=10, n_sim=200)
    fa = dict(zip(a.candidatos["NUMERO"], a.candidatos["FREQ_ELEITO"]))
    fb = dict(zip(b.candidatos["NUMERO"], b.candidatos["FREQ_ELEITO"]))
    assert fa == fb


def test_tabela_sigma_calibrada_a_partir_dos_erros() -> None:
    erros = pl.DataFrame({"PCT": [5.0, 5.0, 5.0, 5.0, 15.0, 15.0, 15.0, 15.0],
                          "TIPO": ["agremiacao", "agremiacao", "candidato", "candidato"] * 2,
                          "LOG_ERRO": [0.1, 0.3, 0.2, 0.6, 0.0, 0.4, 0.1, 0.2]})
    tab = pc.calibrar_tabela_sigma(erros, faixas=[10, 20, 30])
    # até 10%: desvios 0,141 e 0,283; 10–20%: agremiação 0,283 fica limitada a 0,141 (nunca cresce),
    # candidato 0,071; 20–30% sem dados herda a faixa anterior
    assert tab == [(10, 0.141, 0.283), (20, 0.141, 0.071), (30, 0.141, 0.071)]
    assert pc.sigma(15, tab) == (0.141, 0.071)
    with pytest.raises(ValueError):
        pc.calibrar_tabela_sigma(erros.filter(pl.col("PCT") > 10), faixas=[10, 20])
