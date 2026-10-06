"""Análise das parciais da noite (TODO 21, rodada 42) sobre um raw/ sintético — offline."""

from __future__ import annotations

import gzip
import json
import os
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

import analisar_coleta as cli
from apuracao.divulgacao import analise as an

ELE = 6259


def _gravar(raiz: Path, arquivo: str, dados: dict, chegada: str, n: int) -> None:
    pasta = raiz / "raw" / str(ELE) / arquivo
    pasta.mkdir(parents=True, exist_ok=True)
    gz = pasta / f"{dados['dg'].replace('/', '')}_{n:06d}_{n}_{n:010x}.json.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as fh:
        json.dump(dados, fh)
    t = datetime.strptime(chegada, "%d/%m/%Y %H:%M:%S").astimezone(an.BRASILIA).timestamp()
    os.utime(gz, (t, t))


def _ea15(gerado: str, municipios: dict[int, str]) -> dict:
    d, h = gerado.split()
    return {"ele": str(ELE), "dg": d, "hg": h, "abr": [
        {"tpabr": "mun", "cdabr": str(mun), "dt": dt.split()[0], "ht": dt.split()[1], "s": {"pstn": "100"}, "e": {}}
        for mun, dt in municipios.items()]}


def _ea20(gerado: str, dt: str, pct: str = "100") -> dict:
    d, h = gerado.split()
    return {"ele": str(ELE), "dg": d, "hg": h, "dt": dt.split()[0], "ht": dt.split()[1], "s": {"pstn": pct}, "tf": "s"}


@pytest.fixture()
def noite(tmp_path: Path) -> Path:
    """Município 1: anunciado às 20:00; o TSE serve a versão das 19:50 (anterior) e só às 20:03 gera a certa.
    Município 2: anunciado às 20:10; o EA20 certo (gerado 20:10:30) chega de primeira. Uma pausa nossa de 20 min."""
    _gravar(tmp_path, f"rj-e00{ELE}-ab", _ea15("04/10/2026 20:00:10", {1: "04/10/2026 20:00:00"}), "04/10/2026 20:01:00", 1)
    _gravar(tmp_path, f"rj1-c0003-e00{ELE}-u", _ea20("04/10/2026 19:50:00", "04/10/2026 19:49:00"), "04/10/2026 20:01:05", 2)
    _gravar(tmp_path, f"rj1-c0003-e00{ELE}-u", _ea20("04/10/2026 20:03:00", "04/10/2026 20:00:00"), "04/10/2026 20:04:00", 3)
    _gravar(tmp_path, f"rj-e00{ELE}-ab", _ea15("04/10/2026 20:10:10", {1: "04/10/2026 20:00:00", 2: "04/10/2026 20:10:00"}),
            "04/10/2026 20:11:00", 4)
    _gravar(tmp_path, f"rj2-c0003-e00{ELE}-u", _ea20("04/10/2026 20:10:30", "04/10/2026 20:09:00"), "04/10/2026 20:11:20", 5)
    _gravar(tmp_path, f"rj-e00{ELE}-ab", _ea15("04/10/2026 20:31:00", {1: "04/10/2026 20:00:00", 2: "04/10/2026 20:10:00"}),
            "04/10/2026 20:32:00", 6)
    return tmp_path


def test_anuncio_x_publicacao(noite: Path) -> None:
    versoes, anuncios = an.ler(noite)
    assert versoes.height == 6 and an.anuncios_distintos(anuncios).height == 2
    pub = an.publicacao(anuncios, versoes).sort("CD_MUNICIPIO")
    m1, m2 = pub.row(0, named=True), pub.row(1, named=True)
    assert (m1["N_ANTERIORES"], m1["VEIO_ANTERIOR_PRIMEIRO"], m1["ESPERA_MIN"]) == (1, True, pytest.approx(3.0))
    assert m1["ATRASO_TSE_MIN"] == pytest.approx(3.0)                      # gerado 20:03 − anunciado 20:00
    assert (m2["N_ANTERIORES"], m2["ESPERA_MIN"]) == (0, pytest.approx(20 / 60))
    r = an.resumo_publicacao(pub).filter(pl.col("ESCOPO") == "mun")
    assert r["TOTALIZACOES"][0] == 2 and r["ANTERIOR_PRIMEIRO"][0] == 1
    assert an.criterio(pub) == {"anteriores_pela_regra": 1, "anteriores_de_conteudo_diferente": 1,
                                "totalizacoes_com_a_certa": 2, "certas_de_primeira": 1}
    pec = an.peculiaridades(anuncios, pub)
    assert pec.filter(pl.col("O_QUE").str.starts_with("EA20"))["N"].sum() == 1  # rj2: dt 20:09 < anúncio 20:10


def test_atraso_e_pausas(noite: Path) -> None:
    versoes, _ = an.ler(noite)
    at = an.atraso_coleta(versoes).filter(pl.col("TIPO") == "resultado")
    assert at["MAX_MIN"][0] == pytest.approx(11 + 5 / 60, abs=0.01)  # versão anterior: gerada 19:50, chegou 20:01:05
    pa = an.pausas(versoes, minutos=10)
    nossa = pa.filter(pl.col("ORIGEM") == "coleta").row(0, named=True)
    assert nossa["MINUTOS"] == pytest.approx(20.7, abs=0.1) and nossa["TSE_TAMBEM"]  # o TSE também ficou 20 min parado


def test_cli_planilha_e_grafico(noite: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    log = tmp_path / "vigia.log"
    log.write_text("2026-10-04 20:15:00 vigia: reiniciando o site (3 falhas)\noutra linha\n")
    assert cli.main(["--dados", str(noite), "--saida", str(tmp_path / "x.xlsx"), "--grafico", str(tmp_path / "x.png"),
                     "--log", str(log)]) == 0
    saida = capsys.readouterr().out
    assert "anteriores pela regra: 1" in saida and "reiniciando" in saida
    assert (tmp_path / "x.xlsx").stat().st_size > 0 and (tmp_path / "x.png").stat().st_size > 0
    assert cli.main(["--dados", str(tmp_path / "nada")]) == 1
