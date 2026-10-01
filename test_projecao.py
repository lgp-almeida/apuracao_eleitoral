"""Projeção do resultado final: método, margem calibrada, leitura, apuração reconstituída e API — offline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from apuracao import projecao as pj
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import FakeTSE

# M1: metade apurada, A com 75%; M2: 10% apurado, A com 25%; M3: nada apurado
MUN = pl.DataFrame({"CD_MUNICIPIO": [1, 2, 3], "ELEITORADO": [100, 300, 100], "APURADO": [50, 30, 0],
                    "VALIDOS": [40, 24, 0]})
VOTOS = pl.DataFrame({"CD_MUNICIPIO": [1, 1, 2, 2], "NUMERO": [10, 20, 10, 20], "VOTOS": [30, 10, 6, 18]})


def test_projecao_calculada_a_mao() -> None:
    p = pj.projetar(MUN, VOTOS)
    # válidos por eleitor apurado = 64/80 = 0,8 → finais: M1 80, M2 240, M3 100 × 0,8 = 80 → 400
    assert p.pct_apurado == pytest.approx(16) and p.validos_atuais == 64 and p.validos_projetados == pytest.approx(400)
    c = {r["NUMERO"]: r for r in p.candidatos.iter_rows(named=True)}
    # A: M1 30 + 0,75 × 40 = 60; M2 6 + 0,25 × 216 = 60; M3 (participação no estado, 36/64) × 80 = 45 → 165
    assert c[10]["VOTOS_PROJ"] == pytest.approx(165) and c[10]["PCT_PROJ"] == pytest.approx(41.25)
    assert c[10]["PCT_ATUAL"] == pytest.approx(100 * 36 / 64)  # o parcial (56,25%) exagera A: M1 apurou antes
    assert c[20]["PCT_PROJ"] == pytest.approx(58.75) and p.candidatos["NUMERO"][0] == 20
    assert p.margem_pp == pj.margem(16) and c[10]["MIN"] == pytest.approx(41.25 - pj.margem(16))
    assert p.municipios_sem_apuracao == 1
    assert p.municipios["CD_MUNICIPIO"].to_list() == [2, 3, 1]  # onde faltam mais válidos: M2 (216), M3 (80), M1 (40)


def test_apuracao_completa_projeta_o_proprio_resultado() -> None:
    mun = MUN.with_columns(pl.col("ELEITORADO").alias("APURADO"), pl.Series("VALIDOS", [80, 240, 80]))
    votos = pl.DataFrame({"CD_MUNICIPIO": [1, 2, 3], "NUMERO": [10, 10, 20], "VOTOS": [80, 120, 80]})
    p = pj.projetar(mun, votos.vstack(pl.DataFrame({"CD_MUNICIPIO": [2], "NUMERO": [20], "VOTOS": [120]})))
    assert p.margem_pp == 0 and p.pct_apurado == 100
    assert all(abs(r["PCT_PROJ"] - r["PCT_ATUAL"]) < 1e-9 for r in p.candidatos.iter_rows(named=True))


@pytest.mark.parametrize("pct,faixa", [(0, None), (5, 0), (10, 0), (20, 1), (55, 5), (99.9, -1), (100, None)])
def test_margem_por_faixa(pct: float, faixa: int | None) -> None:
    """A faixa (limite superior inclusivo) escolhe a margem; os VALORES ficam em test_calibracao.py."""
    esperado = None if pct == 0 else 0.0 if pct == 100 else pj.MARGEM_PP[faixa][1]
    assert pj.margem(pct) == esperado
    assert pj.margem(pct, [(50, 9.0), (100, 1.0)]) == (None if pct == 0 else 0.0 if pct == 100
                                                       else 9.0 if pct <= 50 else 1.0)  # tabela proposta


def _proj(pcts: list[tuple[int, float]], margem: float) -> pj.Projecao:
    c = pl.DataFrame({"NUMERO": [n for n, _ in pcts], "PCT_PROJ": [x for _, x in pcts]}).with_columns(
        (pl.col("PCT_PROJ") - margem).alias("MIN"), (pl.col("PCT_PROJ") + margem).alias("MAX"))
    return pj.Projecao(50, 1, 1, margem, c, pl.DataFrame(), 0)


def test_leitura_da_projecao() -> None:
    assert pj.situacao(_proj([(1, 53), (2, 40)], 2), objetivo="maioria").startswith("vitória no 1º turno projetada")
    assert pj.situacao(_proj([(1, 51), (2, 40)], 2), objetivo="maioria").startswith("indefinido")
    assert pj.situacao(_proj([(1, 45), (2, 40)], 2), objetivo="maioria").startswith("2º turno projetado")
    assert pj.situacao(_proj([(1, 45), (2, 40)], 0), objetivo="maioria") == "2º turno confirmado"
    assert pj.situacao(_proj([(1, 30), (2, 29), (3, 20)], 2), 2, "vagas").startswith("eleitos (projeção)")
    assert pj.situacao(_proj([(1, 30), (2, 22), (3, 20)], 2), 2, "vagas").startswith("indefinido: o 2º e o 3º")
    assert pj.situacao(_proj([(1, 30), (2, 29)], 2), 1, "lideranca").startswith("indefinido: o 1º e o 2º")
    assert pj.situacao(_proj([(1, 30), (2, 20)], 0), 1, "lideranca") == "mais votado no estado confirmado"


def test_apuracao_reconstituida_pela_hora_das_secoes() -> None:
    h = lambda m: datetime(2022, 10, 2, 18, m)  # noqa: E731
    secoes = pl.DataFrame({"CD_MUNICIPIO": [1, 1, 2, 2], "NR_ZONA": [1, 1, 2, 2], "NR_SECAO": [1, 2, 1, 2],
                           "APTOS": [100, 100, 100, 100], "T": [h(0), h(30), h(10), h(40)]})
    votos = pl.DataFrame({"CD_MUNICIPIO": [1, 1, 1, 2, 2], "NR_ZONA": [1, 1, 1, 2, 2], "NR_SECAO": [1, 1, 2, 1, 2],
                          "NUMERO": [10, 20, 10, 20, 20], "VOTOS": [60, 20, 70, 50, 60]})
    mun, vt = pj.estado_em(secoes, votos, h(15))  # 1ª seção de cada município
    assert dict(zip(mun["CD_MUNICIPIO"], mun["APURADO"])) == {1: 100, 2: 100}
    assert dict(zip(mun["CD_MUNICIPIO"], mun["ELEITORADO"])) == {1: 200, 2: 200}
    b = pj.backtest(secoes, votos, pontos=[25, 50, 100], top=2)
    assert set(b["PCT_ALVO"]) == {25, 50, 100}
    fim = b.filter(pl.col("PCT_ALVO") == 100)
    assert fim["ERRO_PROJECAO"].max() == pytest.approx(0) and fim["ERRO_PARCIAL"].max() == pytest.approx(0)
    meio = b.filter(pl.col("PCT_ALVO") == 50)  # com uma seção de cada município a projeção acerta aqui
    assert meio["ERRO_PROJECAO"].max() < meio["ERRO_PARCIAL"].max() + 1e-9


def test_calibracao_nao_cresce_com_a_apuracao() -> None:
    erros = pl.DataFrame({"PCT_APURADO": [5, 15, 15, 55, 95], "ERRO_PROJECAO": [3.0, 1.0, 4.0, 2.0, 0.1]})
    m = dict(pj.calibrar(erros, faixas=[10, 20, 60, 100], quantil=1.0))
    assert m == {10: 3.0, 20: 3.0, 60: 2.0, 100: 0.1}  # a faixa 10–20 (4,0) é limitada pela anterior


# --------------------------------------------------------------------------- API
@pytest.fixture()
def site(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> TestClient:
    dados = tmp_path / "dados"
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados)
    col.ciclo()
    fake_tse.avancar_uf(21272, "19:00:00", 40.0, 1.1)  # governador a 40% no estado
    col.ciclo()
    return TestClient(create_app(dados, "RJ", tse_cache))


def test_api_projecao(site: TestClient) -> None:
    r = site.get("/api/projecao?cargo=3").json()
    assert 0 < r["pct_apurado"] <= 100 and r["candidatos"] and r["situacao"]
    assert sum(1 for _ in r["faltam"]) <= 15 and "metodo" in r
    k = r["candidatos"][0]
    assert k["MIN"] <= k["PCT_PROJ"] <= k["MAX"] and k["NOME_URNA"]
    assert site.get("/api/projecao?cargo=7").status_code == 400
    card = next(c for c in site.get("/api/painel").json()["cartoes"] if c["cargo"] == 3)
    assert ("projecao" in card) == (0 < card["totais"]["PCT_SECOES_TOTALIZADAS"] < 100)


# --------------------------------------------------------------------------- dados reais (regressão)
CACHE_REAL = Path(__file__).parent / "cache_tse"


@pytest.mark.skipif(not (CACHE_REAL / "detalhe_votacao_secao_2022.zip").exists()
                    or not (CACHE_REAL / "votacao_secao_2022_RJ.zip").exists(),
                    reason="microdados de 2022 fora do cache")
def test_apuracao_real_do_rj_2022_dentro_da_margem() -> None:
    import votos_por_local_votacao as v
    votes = v.load_section_votes(2022, "RJ", "governador", CACHE_REAL, False)
    secoes = pj.secoes_com_hora(2022, "RJ", 3, 1, CACHE_REAL)
    b = pj.backtest(secoes, pj.votos_por_secao(votes, "RJ", "GOVERNADOR", 1))
    dentro = b.with_columns(pl.col("PCT_APURADO").map_elements(pj.margem, return_dtype=pl.Float64).alias("M")) \
              .select((pl.col("ERRO_PROJECAO") <= pl.col("M") + 1e-9).mean()).item()
    assert dentro >= 0.95  # Governador RJ 2022: a margem calibrada cobre as projeções
    tardio = b.filter(pl.col("PCT_ALVO") >= 50)
    assert tardio["ERRO_PROJECAO"].mean() < tardio["ERRO_PARCIAL"].mean()  # da metade em diante, melhor que o parcial


def test_cedo_demais_para_ler_a_projecao() -> None:
    """Com uma fração ínfima apurada (achado no ensaio geral) a leitura não pode anunciar vitória."""
    p = _proj([(1, 83.6), (2, 10.0)], 8.07)
    p.pct_apurado = 0.4
    assert pj.situacao(p, objetivo="maioria").startswith("cedo demais: 0,4% do eleitorado apurado")
