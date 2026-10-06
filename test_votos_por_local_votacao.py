"""Validação com dados sintéticos no layout do TSE (latin-1, ';', aspas).

Roda offline: os ZIP falsos são colocados no cache, então nada é baixado.
    pytest -q test_votos_por_local_votacao.py
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import polars as pl
import pytest

import votos_por_local_votacao as v

VS_HEADER = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "NR_TURNO", "SG_UF", "SG_UE", "NM_UE",
    "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "DS_CARGO",
    "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO", "SQ_CANDIDATO",
    "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO",
]
EL_HEADER = [
    "DT_GERACAO", "AA_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
    "NR_SECAO", "NR_SECAO_PRINCIPAL", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO",
    "NM_BAIRRO", "NR_CEP", "NR_LATITUDE", "NR_LONGITUDE", "QT_ELEITOR_SECAO",
]

RIO, NIT = (60011, "RIO DE JANEIRO"), (58653, "NITERÓI")
PEDRO_II = (4, 1015, "COLÉGIO PEDRO II - UNIDADE CENTRO", "AV. MARECHAL FLORIANO, 80")
ESCOLA_X = (4, 1023, "ESCOLA MUNICIPAL JOÃO BARBALHO", "RUA DO LAVRADIO, 12")
NIT_LOC = (71, 1015, "COLÉGIO PEDRO II - NITERÓI", "RUA X, 1")  # mesmo nº de local, outra zona!

# (muni, local, secao, cargo, votavel, nome, votos)
DEP_EST = "DEPUTADO ESTADUAL"
VOTES = [
    (RIO, PEDRO_II, 10, DEP_EST, 13713, "FULANA DE TAL", 5),
    (RIO, PEDRO_II, 10, DEP_EST, 22222, "BELTRANO", 40),
    (RIO, PEDRO_II, 10, DEP_EST, 13, "PT", 3),
    (RIO, PEDRO_II, 10, DEP_EST, 95, "VOTO BRANCO", 7),
    (RIO, PEDRO_II, 10, DEP_EST, 96, "VOTO NULO", 9),
    # seção 11: candidato NÃO tem linha (0 voto) -> tem de aparecer com 0
    (RIO, PEDRO_II, 11, DEP_EST, 22222, "BELTRANO", 30),
    (RIO, PEDRO_II, 11, DEP_EST, 96, "VOTO NULO", 4),
    # seção 12 é principal; a 13 foi agregada a ela (não aparece na votação)
    (RIO, PEDRO_II, 12, DEP_EST, 13713, "FULANA DE TAL", 8),
    (RIO, PEDRO_II, 12, DEP_EST, 22222, "BELTRANO", 50),
    (RIO, PEDRO_II, 12, DEP_EST, 13, "PT", 2),
    # outro cargo no mesmo local: não pode contaminar
    (RIO, PEDRO_II, 10, "DEPUTADO FEDERAL", 1371, "OUTRO", 99),
    (RIO, ESCOLA_X, 20, DEP_EST, 13713, "FULANA DE TAL", 11),
    (RIO, ESCOLA_X, 20, DEP_EST, 22222, "BELTRANO", 20),
    (NIT, NIT_LOC, 30, DEP_EST, 13713, "FULANA DE TAL", 100),
    (NIT, NIT_LOC, 30, DEP_EST, 45, "PSDB", 10),
]
ELECTORATE = [  # (muni, local, secao, principal, eleitores, lat, lon, bairro, uf)
    (RIO, PEDRO_II, 10, -1, 300, "-22,9035", "-43,1790", "CENTRO", "RJ"),
    (RIO, PEDRO_II, 11, -1, 280, "-22,9035", "-43,1790", "CENTRO", "RJ"),
    (RIO, PEDRO_II, 12, -1, 250, "-22,9035", "-43,1790", "CENTRO", "RJ"),
    (RIO, PEDRO_II, 13, 12, 90, "-22,9035", "-43,1790", "CENTRO", "RJ"),
    (RIO, ESCOLA_X, 20, -1, 200, "-1", "-1", "LAPA", "RJ"),
    (NIT, NIT_LOC, 30, -1, 310, "-22,89", "-43,12", "CENTRO", "RJ"),
    ((1, "SAO PAULO"), (1, 1, "X", "Y"), 1, -1, 999, "0", "0", "SÉ", "SP"),
]


def _write_zip(path: Path, member: str, header: list[str], rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, buf.getvalue().encode("latin-1"))
        zf.writestr("leiame.pdf", b"%PDF-fake")


@pytest.fixture()
def cache(tmp_path: Path) -> Path:
    rows = []
    for (cd, nm), (z, loc, nml, end), sec, cargo, nr, nome, q in VOTES:
        rows.append(["29/09/2026", "00:00:00", 2022, 1, "RJ", "RJ", "RIO DE JANEIRO", cd, nm, z, sec,
                     7, cargo, nr, nome, q, loc, "#NULO#" if nr < 100 else 190000000001, nml, end])
    _write_zip(tmp_path / "votacao_secao_2022_RJ.zip", "votacao_secao_2022_RJ.csv", VS_HEADER, rows)

    erows = []
    for (cd, nm), (z, loc, nml, end), sec, princ, qt, lat, lon, bairro, uf in ELECTORATE:
        erows.append(["29/09/2026", 2022, 1, uf, cd, nm, z, sec, princ, loc, nml, end, bairro,
                      "20000000", lat, lon, qt])
    _write_zip(tmp_path / "eleitorado_local_votacao_2022.zip", "eleitorado_local_votacao_2022.csv",
               EL_HEADER, erows)
    return tmp_path


def _votes(cache: Path) -> pl.LazyFrame:
    return v.load_section_votes(2022, "RJ", DEP_EST, cache, False)


def test_latin1_and_municipality_resolution(cache: Path) -> None:
    votes = _votes(cache)
    assert v.resolve_municipality(votes, "niteroi") == 58653  # sem acento
    assert "NITERÓI" in votes.select("NM_MUNICIPIO").collect()["NM_MUNICIPIO"].to_list()


def test_section_tally_includes_zero_and_splits_vote_types(cache: Path) -> None:
    df = v.tally_by_section(_votes(cache), 1, "deputado estadual", 13713, 4, 1015, 60011)
    by_sec = {r["NR_SECAO"]: r for r in df.iter_rows(named=True)}
    assert set(by_sec) == {10, 11, 12}
    assert by_sec[11]["VOTOS_CANDIDATO"] == 0
    s10 = by_sec[10]
    assert (s10["VOTOS_CANDIDATO"], s10["VOTOS_NOMINAIS"], s10["VOTOS_LEGENDA"]) == (5, 45, 3)
    assert (s10["VOTOS_BRANCOS"], s10["VOTOS_NULOS"], s10["VOTOS_VALIDOS"]) == (7, 9, 48)
    assert s10["VOTOS_APURADOS"] == 64  # Dep. Federal (99) não entra
    assert s10["PCT_VALIDOS"] == pytest.approx(100 * 5 / 48, abs=1e-3)


def test_local_key_is_zone_scoped(cache: Path) -> None:
    # local 1015 existe na zona 4 (Rio) e 71 (Niterói): não pode somar os dois
    df = v.tally_by_section(_votes(cache), 1, DEP_EST, 13713, 4, 1015, None)
    assert df["VOTOS_CANDIDATO"].sum() == 13


def test_total_row(cache: Path) -> None:
    df = v.add_total_row(v.tally_by_section(_votes(cache), 1, DEP_EST, 13713, 4, 1015, None))
    tot = df.filter(pl.col("SECAO") == "TOTAL DO LOCAL").row(0, named=True)
    assert tot["VOTOS_CANDIDATO"] == 13 and tot["VOTOS_VALIDOS"] == 48 + 30 + 60


def test_aggregated_sections_and_electorate(cache: Path) -> None:
    elect = v.electorate_by_section(v.load_electorate(2022, "RJ", cache, False), 1)
    assert elect.filter(pl.col("NR_SECAO") == 1).is_empty()  # SP filtrado
    df = v.enrich_sections(v.tally_by_section(_votes(cache), 1, DEP_EST, 13713, 4, 1015, None), elect)
    s12 = df.filter(pl.col("NR_SECAO") == 12).row(0, named=True)
    assert s12["SECOES_AGREGADAS"] == "13" and s12["QT_ELEITORES_EFETIVOS"] == 340


def test_by_place_with_coordinates(cache: Path) -> None:
    votes = _votes(cache)
    elect = v.electorate_by_section(v.load_electorate(2022, "RJ", cache, False), 1)
    df = v.enrich_places(v.tally_by_place(votes, 1, DEP_EST, 13713, 60011), votes, elect, 1, DEP_EST)
    assert df.height == 2 and df["VOTOS_CANDIDATO"].to_list() == [13, 11]
    pedro = df.filter(pl.col("NR_LOCAL_VOTACAO") == 1015).row(0, named=True)
    assert pedro["NR_LATITUDE"] == pytest.approx(-22.9035) and pedro["QT_ELEITORES"] == 920
    escola = df.filter(pl.col("NR_LOCAL_VOTACAO") == 1023).row(0, named=True)
    assert escola["NR_LATITUDE"] is None  # -1 do TSE vira nulo


def test_search_and_cli(cache: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out.csv"
    rc = v.main(["secoes", "--uf", "RJ", "--cargo", "Deputado Estadual", "--candidato", "13713",
                 "--municipio", "Rio de Janeiro", "--busca", "pedro ii", "--com-eleitorado",
                 "--cache-dir", str(cache), "--saida", str(out)])
    assert rc == 0 and out.exists()
    assert "FULANA DE TAL" in capsys.readouterr().out
    assert v.main(["secoes", "--uf", "RJ", "--cargo", DEP_EST, "--candidato", "99999",
                   "--zona", "4", "--local", "1015", "--cache-dir", str(cache)]) == 1


class _Resposta404:
    status_code = 404

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("url, cita_tse", [
    (f"{v.CDN_BASE}/votacao_secao/votacao_secao_2030_RJ.zip", True),
    ("https://geoftp.ibge.gov.br/bairros/shp/UF/DF_bairros_CD2022.zip", False),
])
def test_download_404_so_atribui_ao_tse_o_que_e_do_tse(tmp_path, monkeypatch, url, cita_tse):
    monkeypatch.setattr(v.requests, "get", lambda *a, **k: _Resposta404())
    with pytest.raises(v.TseDataError) as exc:
        v.download(v.DatasetSpec("x", url, "RJ"), tmp_path)
    assert url in str(exc.value)
    assert ("TSE" in str(exc.value)) is cita_tse
