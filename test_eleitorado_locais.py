"""Eleitorado (ingestão, layout 2024/2026) e comparação de locais 2024 × 2026 — offline."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

import ingerir_eleitorado
from apuracao import eleitorado as el
from apuracao import locais as lc


def _places(cache: Path, year: int, muni: int | None = 60011) -> tuple[pl.DataFrame, pl.DataFrame]:
    sec = el.filter_area(el.load_sections(year, "RJ", cache), muni)
    return sec, el.places(sec)


def _cmp(cache: Path) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    s24, p24 = _places(cache, 2024)
    s26, p26 = _places(cache, 2026)
    sec = lc.compare_sections(s24, s26, 2024)
    return sec, lc.compare_places(p24, p26, sec, 2024), p24, p26


def _status(cmp: pl.DataFrame, local: int) -> set[str]:
    return set(cmp.filter(pl.col("NR_LOCAL_VOTACAO") == local)[lc.change_col(2024)].item().split(", "))


def test_compact_and_haversine() -> None:
    assert el.compact("Av. Marechal Floriano, 80") == el.compact("AV MARECHAL FLORIANO 80")
    d = pl.select(el.haversine_m(pl.lit(-22.0), pl.lit(-43.0), pl.lit(-23.0), pl.lit(-43.0))).item()
    assert d == pytest.approx(111_195, rel=1e-3)


def test_load_sections_both_layouts(tse_cache: Path) -> None:
    s24, p24 = _places(tse_cache, 2024, None)
    assert set(s24["SG_UF"].unique()) == {"RJ"}  # SP filtrado do CSV nacional
    assert s24.filter(pl.col("NR_SECAO") == 10)["QT_ELEITOR_SECAO"].item() == 300  # 2º turno ignorado
    s26, p26 = _places(tse_cache, 2026, None)
    assert p26.filter(pl.col("NR_LOCAL_VOTACAO") == 1015, pl.col("NR_ZONA") == 4)["NR_LATITUDE"].item() == \
        pytest.approx(-22.9035)  # vírgula decimal em 2026
    assert p26.filter(pl.col("NR_LOCAL_VOTACAO") == 1040)["NR_LATITUDE"].item() is None  # -1 -> nulo
    pedro = p24.filter(pl.col("NR_ZONA") == 4, pl.col("NR_LOCAL_VOTACAO") == 1015).row(0, named=True)
    assert pedro["QT_ELEITORES"] == 920 and pedro["N_SECOES"] == 4  # agregada conta no local
    assert pedro["SECOES_INSTALADAS"] == "10,11,12"
    assert s26.filter(pl.col("NR_SECAO") == 22)["REMANEJADA"].item() is True


def test_ingest_cli_registers_provenance(tse_cache: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ingerir_eleitorado.main(["--ano", "2026", "--uf", "RJ", "--cache-dir", str(tse_cache),
                                    "--relatorio-geo"]) == 0
    prov = json.loads((tse_cache / "eleitorado_local_votacao_2026.proveniencia.json").read_text())
    assert prov["geracao_tse"] == "29/09/2026 06:28:09" and len(prov["sha512"]) == 128
    assert (tse_cache / "eleitorado_local_votacao_2026__RJ.parquet").exists()
    out = capsys.readouterr().out
    assert "secoes_remanejadas" in out and "locais_sem_coordenada" in out


def test_section_changes(tse_cache: Path) -> None:
    sec, *_ = _cmp(tse_cache)
    st = dict(zip(sec["NR_SECAO"].to_list(), sec["STATUS_SECAO"].to_list()))
    assert st[10] == st[13] == lc.MANTIDO
    assert st[21] == "MUDOU_DE_LOCAL" and st[30] == "SECAO_EXTINTA_EM_2026" and st[22] == "SECAO_NOVA_EM_2026"


def test_place_changes(tse_cache: Path) -> None:
    _, cmp, *_ = _cmp(tse_cache)
    assert _status(cmp, 1015) == {lc.MANTIDO}  # acento/pontuação/bairro em caixa diferente não contam
    assert {"RENOMEADO", "DESLOCADO", "SECOES_SAIRAM"} <= _status(cmp, 1023)
    assert "ENDERECO_ALTERADO" not in _status(cmp, 1023)
    assert _status(cmp, 1031) == {lc.desativado()}
    assert {lc.novo(), "REMANEJAMENTO_2026"} <= _status(cmp, 1040)
    x = cmp.filter(pl.col("NR_LOCAL_VOTACAO") == 1023).row(0, named=True)
    assert x["DISTANCIA_M"] == pytest.approx(500, abs=5) and x["SECOES_SAIRAM"] == "21→local 1040"


def test_inconsistencies_and_tre(tse_cache: Path) -> None:
    _, cmp, p24, p26 = _cmp(tse_cache)
    inc = lc.inconsistencies(cmp, p24, p26, "RJ", 2024)
    tipos = inc["TIPO"].to_list()
    assert "BAIRRO_DIVERGENTE" in tipos and "VARIACAO_ELEITORADO" in tipos
    assert inc.filter(pl.col("TIPO") == "COORDENADA_AUSENTE")["CHAVE"].to_list() == ["mun 60011 zona 4 local 1040"]
    tre = lc.compare_with_tre(p26, lc.load_tre_places(tse_cache / "consulta_de_locais_de_votacao_2026-09-29.json"),
                              2024)
    by = {t: r for t, r in zip(tre["TIPO"], tre.iter_rows(named=True))}
    assert set(by) == {"SECOES_DIVERGEM_DA_LISTA_TRE", "LOCAL_2026_AUSENTE_NA_LISTA_TRE"}
    assert by["SECOES_DIVERGEM_DA_LISTA_TRE"]["VALOR_2026"] == "20"
    assert by["LOCAL_2026_AUSENTE_NA_LISTA_TRE"]["VALOR_2026"] == "CRECHE NOVA"
