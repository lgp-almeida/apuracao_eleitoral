"""Conferência tempo real × importado (TODO 16, rodada 45) — offline, com o TSE falso."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import polars as pl
import pytest

import conferir_resultado as cli
from apuracao import conferencia as cf
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from conftest import FakeTSE


@pytest.fixture()
def pastas(fake_tse: FakeTSE, tmp_path: Path) -> tuple[Path, Path]:
    noite = tmp_path / "oficial"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), noite).ciclo()
    importado = tmp_path / "historico_2026_t1"
    shutil.copytree(noite, importado)
    return noite, importado


def _mexer(pasta: Path, tabela: str, filtro: pl.Expr, coluna: str, valor: object) -> None:
    arq = pasta / "ultimo" / f"{tabela}.parquet"
    df = pl.read_parquet(arq)
    df.with_columns(pl.when(filtro).then(pl.lit(valor)).otherwise(pl.col(coluna)).alias(coluna)).write_parquet(arq)


def test_iguais(pastas: tuple[Path, Path]) -> None:
    c = cf.conferir(*pastas, "RJ")
    assert c.ok and c.totais.is_empty() and c.candidatos.is_empty() and c.so_num_lado.is_empty()


def test_diferencas_em_totais_candidatos_e_avisos(pastas: tuple[Path, Path]) -> None:
    noite, importado = pastas
    uf3 = (pl.col("CARGO") == 3) & (pl.col("ABRANGENCIA") == "uf")
    _mexer(importado, "totais", uf3, "NULOS", 999_999)
    cand = pl.read_parquet(importado / "ultimo" / "candidatos.parquet").filter(uf3).sort("VOTOS", descending=True)
    numero = cand["NUMERO"][0]
    _mexer(importado, "candidatos", uf3 & (pl.col("NUMERO") == numero), "VOTOS", int(cand["VOTOS"][0]) + 7)
    (importado / "status.json").write_text(json.dumps({"totais_de": "secoes", "totais": "reconstruídos",
                                                       "avisos": ["destinação do Presidente ainda não publicada"]}))
    c = cf.conferir(noite, importado, "RJ")
    assert not c.ok
    t = c.totais.row(0, named=True)
    assert (t["CARGO"], t["ABRANGENCIA"], t["COLUNA"], t["IMPORTADO"]) == (3, "uf", "NULOS", 999_999)
    d = c.candidatos.row(0, named=True)
    assert d["NUMERO"] == numero and d["VOTOS_IMPORTADO"] - d["VOTOS"] == 7
    assert any("PROVISÓRIOS" in a for a in c.avisos) and any("Presidente" in a for a in c.avisos)


def test_cli(pastas: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    noite, importado = pastas
    saida = tmp_path / "c.xlsx"
    assert cli.main(["--noite", str(noite), "--importado", str(importado), "--saida", str(saida)]) == 0
    assert "TUDO IGUAL" in capsys.readouterr().out and saida.stat().st_size > 0
    assert cli.main(["--noite", str(tmp_path / "nada"), "--importado", str(importado)]) == 2
