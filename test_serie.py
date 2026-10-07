"""Série temporal da apuração (coletor → historico_serie.parquet → painel) — offline."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from fastapi.testclient import TestClient

from apuracao.divulgacao import serie as sr
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import FakeTSE


def _coletar_em_passos(fake: FakeTSE, destino: Path) -> Coletor:
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake, limitador=LimitadorTaxa(1e9)), destino)
    col.ciclo()
    fake.avancar_uf(21272, "18:00:00", 40.0, 1.5)
    col.ciclo()
    fake.avancar_uf(21272, "19:00:00", 80.0, 1.2)
    col.ciclo()
    return col


def test_coletor_grava_serie(fake_tse: FakeTSE, tmp_path: Path) -> None:
    _coletar_em_passos(fake_tse, tmp_path)
    s = pl.read_parquet(tmp_path / sr.ARQUIVO)
    gov = s.filter((pl.col("CARGO") == 3) & (pl.col("ABRANGENCIA") == "uf"))
    assert gov["DT_TOTALIZACAO"].n_unique() == 3 and set(gov["TIPO"]) == {"candidato"}
    assert set(s.filter(pl.col("CARGO") == 7)["TIPO"]) == {"partido"}  # proporcionais: por partido
    assert s.filter(pl.col("ABRANGENCIA") == "mun").is_empty()           # só UF e Brasil
    g = sr.para_grafico(s, 3, "uf", "RJ")
    assert [p["pct_secoes"] for p in g["pontos"]] == [100.0, 40.0, 80.0]  # ordem = hora, não % seções
    assert len(g["series"]) == 3 and all(len(x["valores"]) == 3 for x in g["series"])
    assert sr.para_grafico(s, 1, "br", "RJ")["pontos"]  # presidente no Brasil (1 ponto: eleição federal parada)


def test_reconstruir_a_partir_dos_brutos(fake_tse: FakeTSE, tmp_path: Path) -> None:
    _coletar_em_passos(fake_tse, tmp_path)
    original = pl.read_parquet(tmp_path / sr.ARQUIVO)
    assert sr.reconstruir(tmp_path) > 0
    refeita = pl.read_parquet(tmp_path / sr.ARQUIVO)
    chave = ["CARGO", "ABRANGENCIA", "DT_TOTALIZACAO", "CHAVE"]
    assert refeita.select(chave).sort(chave).equals(original.select(chave).sort(chave))


def test_painel_traz_serie(fake_tse: FakeTSE, tmp_path: Path) -> None:
    _coletar_em_passos(fake_tse, tmp_path)
    cartoes = {(c["cargo"], c["abrangencia"]): c for c in TestClient(create_app(tmp_path, "RJ", tmp_path))
               .get("/api/painel").json()["cartoes"]}
    assert len(cartoes[(3, "RJ")]["serie"]["pontos"]) == 3 and cartoes[(7, "RJ")]["serie"]["tipo"] == "partido"
    vazio = TestClient(create_app(tmp_path / "nada", "RJ", tmp_path)).get("/api/painel").json()
    assert vazio["cartoes"] == []


# ---------------------------------------------------------------- série por candidato e município
def _numero_governador(fake: FakeTSE) -> int:
    doc = fake._doc("rj60011-c0003-e021272-u.json")
    return int(doc["carg"][0]["agr"][0]["par"][0]["cand"][0]["n"])


def test_serie_por_municipio(fake_tse: FakeTSE, tmp_path: Path) -> None:
    n = _numero_governador(fake_tse)
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), tmp_path)
    col.ciclo()
    fake_tse.avancar_municipio(21272, 60011, "18:00:00", 50.0, {n: 0})     # candidato sem voto nesse momento
    col.ciclo()
    fake_tse.avancar_municipio(21272, 60011, "19:00:00", 90.0, {n: 1234})
    col.ciclo()
    assert len(list((tmp_path / sr.CANDIDATOS_DIR).glob("*.parquet"))) == 3  # um bloco por ciclo com mudança
    rio, uf = sr.serie_candidato(tmp_path, 3, n, [("mun", 60011), ("uf", None)])
    assert [p["pct_secoes"] for p in rio["pontos"]] == [100.0, 50.0, 90.0]
    assert [p["votos"] for p in rio["pontos"]][1:] == [0, 1234]  # ausente = 0 voto (linha de referência)
    assert len(uf["pontos"]) == 1                                   # a UF não mudou
    assert sr.serie_candidato(tmp_path, 3, 999, [("mun", 60011)])[0]["pontos"][0]["votos"] == 0

    antes = {(p["dt"], p["votos"]) for p in rio["pontos"]}
    sr.reconstruir_candidatos(tmp_path)
    assert {(p["dt"], p["votos"]) for p in sr.serie_candidato(tmp_path, 3, n, [("mun", 60011)])[0]["pontos"]} == antes

    site = TestClient(create_app(tmp_path, "RJ", tmp_path))
    d = site.get(f"/api/candidato/serie?cargo=3&numero={n}&municipio=60011").json()
    assert [s["abrangencia"] for s in d["series"]] == ["mun", "uf"] and len(d["series"][0]["pontos"]) == 3
    pres = site.get("/api/candidato/serie?cargo=1&numero=13").json()
    assert [s["abrangencia"] for s in pres["series"]] == ["uf", "br"]
    assert TestClient(create_app(tmp_path / "nada", "RJ", tmp_path)).get(
        "/api/candidato/serie?cargo=3&numero=1").json() == {"series": []}


# ---------------------------------------------------------------- mapa num momento da apuração
def test_mapa_no_momento(fake_tse: FakeTSE, tmp_path: Path) -> None:
    from datetime import datetime

    n = _numero_governador(fake_tse)
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), tmp_path)
    col.ciclo()
    fake_tse.avancar_municipio(21272, 60011, "18:00:00", 50.0, {n: 0})
    col.ciclo()
    fake_tse.avancar_municipio(21272, 60011, "19:00:00", 90.0, {n: 1234})
    col.ciclo()
    hist = pl.read_parquet(tmp_path / "historico_totais.parquet")
    momentos = sr.momentos(hist, 3)
    assert momentos[-2:] == [datetime(2026, 9, 29, 18), datetime(2026, 9, 29, 19)]

    as18 = sr.totais_ate(hist, 3, datetime(2026, 9, 29, 18, 30))
    assert as18.filter(pl.col("CD_MUNICIPIO") == 60011)["PCT_SECOES_TOTALIZADAS"].item() == 50.0
    assert as18.height == 3                                    # os outros municípios: última totalização anterior
    assert sr.totais_ate(hist, 3, datetime(2026, 9, 29, 8)).is_empty()  # antes de qualquer totalização
    c18 = sr.candidatos_ate(tmp_path, 3, datetime(2026, 9, 29, 18, 30), n)
    assert c18.filter(pl.col("CD_MUNICIPIO") == 60011)["VOTOS"].item() == 0
    c19 = sr.candidatos_ate(tmp_path, 3, datetime(2026, 9, 29, 19, 30), n)
    assert c19.filter(pl.col("CD_MUNICIPIO") == 60011)["VOTOS"].item() == 1234
    todos = sr.candidatos_ate(tmp_path, 3, datetime(2026, 9, 29, 18, 30))
    assert n not in todos.filter(pl.col("CD_MUNICIPIO") == 60011)["NUMERO"].to_list()

    site = TestClient(create_app(tmp_path, "RJ", tmp_path))
    ms = site.get("/api/mapa/momentos?cargo=3").json()["momentos"]
    assert ms[-1] == "2026-09-29T19:00:00"
    rio_ibge = str(fake_tse._doc("mun-e021272-cm.json")["abr"][0]["mu"][2]["cdi"])  # Rio de Janeiro
    q = f"/api/mapa?cargo=3&metrica=votos_candidato&numero={n}&momento=2026-09-29T18:30:00"
    d = site.get(q).json()
    assert d["momento"] == "2026-09-29T18:30:00" and d["itens"][rio_ibge]["valor"] == 0
    agora = site.get(f"/api/mapa?cargo=3&metrica=votos_candidato&numero={n}").json()
    assert agora["momento"] is None and agora["itens"][rio_ibge]["valor"] == 1234
    venc = site.get("/api/mapa?cargo=3&metrica=vencedor&momento=2026-09-29T18:30:00").json()
    assert venc["itens"][rio_ibge]["valor"] != n and venc["itens"][rio_ibge]["rotulo"]
    secoes = site.get("/api/mapa?cargo=3&metrica=secoes_totalizadas_pct&momento=2026-09-29T18:30:00").json()
    assert secoes["itens"][rio_ibge]["valor"] == 50.0
    assert site.get("/api/mapa?cargo=3&metrica=abstencao_pct&momento=ontem").status_code == 400
    # com fuso (ex.: link montado à mão em UTC): vira a hora de Brasília, a do TSE, em vez de erro 500
    utc = site.get(f"/api/mapa?cargo=3&metrica=votos_candidato&numero={n}&momento=2026-09-29T21:30:00%2B00:00")
    assert utc.status_code == 200 and utc.json()["momento"] == "2026-09-29T18:30:00"


def test_serie_por_municipio_ignora_linha_sem_hora(fake_tse: FakeTSE, tmp_path: Path) -> None:
    """Abrangência publicada antes de totalizar vem com a data vazia: a série descarta o ponto em vez de quebrar
    a rota (/api/candidato/serie, AttributeError em 07/10/2026 com os dados da noite de 4/10)."""
    n = _numero_governador(fake_tse)
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), tmp_path)
    col.ciclo()
    pasta = tmp_path / sr.CANDIDATOS_DIR
    bloco = pl.read_parquet(next(pasta.glob("*.parquet")))
    bloco.with_columns(pl.lit(None, bloco.schema["DT_TOTALIZACAO"]).alias("DT_TOTALIZACAO")).write_parquet(
        pasta / "sem_hora.parquet")
    (rio,) = sr.serie_candidato(tmp_path, 3, n, [("mun", 60011)])
    assert len(rio["pontos"]) == 1 and rio["pontos"][0]["dt"]
    site = TestClient(create_app(tmp_path, "RJ", tmp_path))
    assert site.get(f"/api/candidato/serie?cargo=3&numero={n}&municipio=60011").status_code == 200
