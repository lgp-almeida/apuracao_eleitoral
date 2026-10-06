"""Comparação entre UFs (apuracao/entre_ufs.py e comparar_ufs.py) sobre pastas sintéticas no formato do coletor."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

import comparar_ufs
from apuracao import entre_ufs as eu

# 1º turno: 22, 13 e 12 (eliminado); 2º turno: 22 e 13. Linhas: 22, 13, 12, branco/nulo, abstenção.
MATRIZ = np.array([[0.95, 0.00, 0.01, 0.04],
                   [0.00, 0.95, 0.01, 0.04],
                   [0.30, 0.50, 0.05, 0.15],
                   [0.05, 0.05, 0.80, 0.10],
                   [0.03, 0.03, 0.02, 0.92]])


def _gravar(pasta: Path, uf: str, turno: int, muns: list[tuple[int, int, np.ndarray]], cargo: int = 1) -> None:
    """muns: (código, eleitorado, votos por categoria [cand..., branco/nulo, abstenção])."""
    numeros = [22, 13, 12] if turno == 1 else [22, 13]
    tot, cand = [], []
    for cd, el, q in [*muns, (None, sum(m[1] for m in muns), sum(m[2] for m in muns))]:
        bn, abst = int(q[-2]), int(q[-1])
        tot.append({"ABRANGENCIA": "uf" if cd is None else "mun", "UF": uf, "CD_MUNICIPIO": cd, "CARGO": cargo,
                    "TURNO": turno, "ELEITORADO": el, "COMPARECIMENTO": el - abst, "ABSTENCAO": abst,
                    "VOTOS_TOTAL": el - abst, "BRANCOS": bn // 2, "NULOS": bn - bn // 2, "PCT_SECOES_TOTALIZADAS": 100.0})
        cand += [{"ABRANGENCIA": "uf" if cd is None else "mun", "UF": uf, "CD_MUNICIPIO": cd, "CARGO": cargo,
                  "NUMERO": n, "VOTOS": int(x), "NOME_URNA": f"C{n}", "PARTIDO": f"P{n}"} for n, x in zip(numeros, q)]
    (pasta / "ultimo").mkdir(parents=True)
    pl.DataFrame(tot).write_parquet(pasta / "ultimo" / "totais.parquet")
    pl.DataFrame(cand).write_parquet(pasta / "ultimo" / "candidatos.parquet")
    pl.DataFrame({"CD_MUNICIPIO": [m[0] for m in muns], "NM_MUNICIPIO": [f"M{m[0]}" for m in muns]}).write_parquet(
        pasta / "ultimo" / "municipios.parquet")


def _uf(dados: Path, base1: str, base2: str | None, uf: str, n_muns: int, abst: float, semente: int) -> None:
    rng = np.random.default_rng(semente)
    m1, m2 = [], []
    for i in range(n_muns):
        el = int(rng.integers(5_000, 50_000))
        x = rng.dirichlet([6, 5, 1.5, 1, 1])
        x[-1] = abst + rng.normal(0, 0.01)
        x[:-1] *= (1 - x[-1]) / x[:-1].sum()
        m1.append((1000 + i, el, np.round(el * x)))
        m2.append((1000 + i, el, np.round(el * (x @ MATRIZ))))
    _gravar(dados / f"{base1}_{uf}", uf, 1, m1)
    if base2:
        _gravar(dados / f"{base2}_{uf}", uf, 2, m2)


@pytest.fixture()
def dados(tmp_path: Path) -> Path:
    for base1, base2, abst in (("oficial", None, 0.22), ("historico_2022_t1", "historico_2022_t2", 0.20)):
        _uf(tmp_path, base1, base2, "SP", 60, abst, 1)
        _uf(tmp_path, base1, base2, "DF", 1, abst, 2)       # 1 município: sem como estimar a transferência
    _uf(tmp_path, "oficial", None, "MG", 30, 0.25, 3)      # só 2026, sem 2º turno
    return tmp_path


def test_participacao_e_variacao(dados: Path) -> None:
    el = eu.eleicoes_padrao(dados)
    part = eu.participacao(el, ["SP", "DF", "MG", "RJ"], [1])
    assert set(part["UF"]) == {"SP", "DF", "MG"}               # RJ sem pasta: sem linha, não erro
    assert set(part.filter(pl.col("TURNO") == 2)["ELEICAO"]) == {"2022"}   # 2º turno de 2026 ainda não existe
    sp = part.filter((pl.col("UF") == "SP") & (pl.col("ELEICAO") == "2026") & (pl.col("TURNO") == 1)).row(0, named=True)
    assert 20 < sp["ABSTENCAO_PCT"] < 24 and sp["PCT_APURADO"] == 100
    var = eu.variacao(part, "2026", "2022")
    assert set(var["UF"]) == {"SP", "DF"}                     # MG não tem a referência
    r = var.filter((pl.col("UF") == "SP") & (pl.col("TURNO") == 1)).row(0, named=True)
    assert r["ABSTENCAO_VAR_PP"] == pytest.approx(r["ABSTENCAO_PCT_2026"] - r["ABSTENCAO_PCT_2022"])
    assert 1 < r["ABSTENCAO_VAR_PP"] < 3


def test_transferencia_por_uf(dados: Path) -> None:
    t = eu.transferencias(eu.eleicoes_padrao(dados), ["SP", "DF", "MG"], [1])
    assert t.select("ELEICAO", "UF").rows() == [("2022", "DF"), ("2022", "SP")]   # só onde há 2º turno
    df = t.filter(pl.col("UF") == "DF").row(0, named=True)
    assert df["NOTA"] and "poucas unidades" in df["NOTA"]
    sp = t.filter(pl.col("UF") == "SP").row(0, named=True)
    assert sp["NOTA"] is None and sp["MUNICIPIOS"] == 60 and sp["FINALISTA_A"] == "C22 (P22)"
    assert sp["ELIM_PARA_A"] == pytest.approx(30, abs=4) and sp["ELIM_PARA_B"] == pytest.approx(50, abs=4)
    assert sp["A_FICOU"] == pytest.approx(95, abs=3)


def test_cli_grava_planilha_e_grafico(dados: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    xlsx, png = tmp_path / "s" / "ufs.xlsx", tmp_path / "s" / "abst.png"
    rc = comparar_ufs.main(["--dados", str(dados), "--ufs", "SP", "DF", "MG", "--cargo", "presidente",
                            "--saida", str(xlsx), "--grafico", str(png)])
    assert rc == 0 and xlsx.stat().st_size > 0 and png.stat().st_size > 0
    assert "Transferência 1º → 2º turno" in capsys.readouterr().out
    assert comparar_ufs.main(["--dados", str(tmp_path / "vazio")]) == 1
    assert comparar_ufs.main(["--ufs", "XX"]) == 1
