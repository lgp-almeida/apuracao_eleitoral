"""Ensaio geral: a apuração reconstituída servida no formato do TSE e coletada pelo Coletor real — offline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from apuracao import ensaio as en
from apuracao.divulgacao import modelo as m
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor

RIO, NIT = 60011, 58653
H = lambda h, mi=0: datetime(2022, 10, 2, h, mi)  # noqa: E731
# 4 seções: Rio às 18h e 20h, Niterói às 18h30 e 19h (100 aptos, 80 comparecem em cada)
SECOES = pl.DataFrame({"SG_UF": ["RJ"] * 4, "CD_MUNICIPIO": [RIO, RIO, NIT, NIT],
                       "T": [H(18), H(20), H(18, 30), H(19)], "APTOS": [100] * 4, "COMPARECIMENTO": [80] * 4,
                       "ABSTENCOES": [20] * 4})


def _votos(linhas: list[tuple[int, datetime, int, int]]) -> pl.DataFrame:
    return pl.DataFrame(linhas, schema={"CD_MUNICIPIO": pl.Int64, "T": pl.Datetime, "NR_VOTAVEL": pl.Int64,
                                        "QT_VOTOS": pl.Int64}, orient="row").with_columns(pl.lit("RJ").alias("SG_UF"))


def _cand(linhas: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(linhas, schema=["NUMERO", "NOME_URNA", "NOME", "SQ", "PARTIDO", "NR_PARTIDO", "FEDERACAO",
                                        "VALIDO", "SITUACAO_FINAL"], orient="row")


@pytest.fixture()
def rec() -> en.Reconstituicao:
    gov_v = _votos([(RIO, H(18), 22, 50), (RIO, H(18), 40, 20), (RIO, H(18), 95, 10), (RIO, H(20), 22, 30),
                    (RIO, H(20), 40, 45), (NIT, H(18, 30), 22, 10), (NIT, H(18, 30), 40, 60), (NIT, H(19), 40, 70),
                    (NIT, H(19), 99, 5)])  # 99: candidato anulado
    gov_c = _cand([(22, "CASTRO", "C", 1, "PL", 22, None, True, "Eleito"), (40, "FREIXO", "F", 2, "PSB", 40, None, True, "Não eleito"),
                   (99, "ANULADO", "A", 3, "PX", 99, None, False, "Não eleito")])
    dep_v = _votos([(RIO, H(18), 22111, 40), (RIO, H(18), 22, 5), (RIO, H(18), 50123, 20), (RIO, H(20), 50123, 50),
                    (NIT, H(18, 30), 22111, 30), (NIT, H(19), 50222, 25)])
    dep_c = _cand([(22111, "D1", "D1", 11, "PL", 22, None, True, "Eleito por QP"),
                   (50123, "P1", "P1", 12, "PSOL", 50, "PSOL/REDE", True, "Eleito por média"),
                   (50222, "P2", "P2", 13, "PSOL", 50, "PSOL/REDE", True, "Suplente")])
    cargos = {3: en.DadosCargo(3, en.ELEICAO_ESTADUAL, 1, SECOES, gov_v, gov_c, gov_c.select("NR_PARTIDO", "PARTIDO", "FEDERACAO")),
              7: en.DadosCargo(7, en.ELEICAO_ESTADUAL, 2, SECOES, dep_v, dep_c, dep_c.select("NR_PARTIDO", "PARTIDO", "FEDERACAO"))}
    return en.Reconstituicao("RJ", cargos, H(17, 55), H(20, 1))


def test_relogio_acelerado_e_fixo() -> None:
    r = en.Relogio(H(17), H(18), velocidade=3600)
    assert H(17) <= r.agora() <= H(18)
    r.fixar(H(17, 30))
    assert r.agora() == H(17, 30) and not r.terminou
    r.fixar(H(18))
    assert r.terminou


def test_json_no_formato_do_tse_na_metade(rec: en.Reconstituicao) -> None:
    rel = en.Relogio(rec.inicio, rec.fim)
    g = en.Gerador(rec, rel)
    rel.fixar(H(18, 45))  # Rio: 1 de 2 seções; Niterói: 1 de 2
    r = m.parse_resultado(g.resultado(en.ELEICAO_ESTADUAL, 3, "rj"), "rj")
    t = r.totais.row(0, named=True)
    assert (t["SECOES_TOTALIZADAS"], t["SECOES_TOTAL"], t["ELEITORADO"], t["COMPARECIMENTO"]) == (2, 4, 400, 160)
    assert (t["VALIDOS"], t["BRANCOS"], t["TOTALIZACAO_FINAL"]) == (50 + 20 + 10 + 60, 10, False)
    c = dict(zip(r.candidatos["NOME_URNA"], r.candidatos["VOTOS"]))
    assert c == {"CASTRO": 60, "FREIXO": 80, "ANULADO": 0}
    assert set(r.candidatos["SITUACAO"]) == {""}  # sem situação antes do fim
    dep = m.parse_resultado(g.resultado(en.ELEICAO_ESTADUAL, 7, "rj"), "rj")
    p = {r_["PARTIDO"]: r_ for r_ in dep.partidos.iter_rows(named=True)}
    assert p["PL"]["VOTOS_LEGENDA"] == 5 and p["PL"]["VOTOS_NOMINAIS"] == 70 and p["PSOL"]["FEDERACAO"] == "PSOL/REDE"
    assert dep.totais.row(0, named=True)["QUOCIENTE_ELEITORAL"] == 47  # 95 válidos ÷ 2 vagas = 47,5 → 47 (0,5 desprezado)
    ab = m.parse_acompanhamento(g.acompanhamento(en.ELEICAO_ESTADUAL, "rj"), "rj")
    rio = ab.filter(pl.col("CD_MUNICIPIO") == RIO).row(0, named=True)
    assert rio["DT_TOTALIZACAO"] == H(18) and rio["PCT_SECOES_TOTALIZADAS"] == 50  # hora da última seção apurada
    assert g.resultado(en.ELEICAO_ESTADUAL, 1, "br") is None and g.resultado(en.ELEICAO_FEDERAL, 3, "rj") is None


def test_fim_traz_a_situacao_oficial_e_anulados(rec: en.Reconstituicao) -> None:
    rel = en.Relogio(rec.inicio, rec.fim)
    rel.fixar(rec.fim)
    r = m.parse_resultado(en.Gerador(rec, rel).resultado(en.ELEICAO_ESTADUAL, 3, "rj"), "rj")
    t = r.totais.row(0, named=True)
    assert t["TOTALIZACAO_FINAL"] and t["ANULADOS"] == 5 and t["VALIDOS"] == 285
    # votos de candidato anulado não entram nos votos do partido (nem nos válidos)
    assert r.partidos.filter(pl.col("PARTIDO") == "PX")["VOTOS_NOMINAIS"][0] == 0
    assert r.partidos["VOTOS_TOTAL"].sum() == t["VALIDOS"]
    assert dict(zip(r.candidatos["NOME_URNA"], r.candidatos["SITUACAO"]))["CASTRO"] == "Eleito"
    assert r.candidatos.filter(pl.col("NOME_URNA") == "CASTRO")["ELEITO"][0]


def test_coletor_real_contra_o_ensaio(rec: en.Reconstituicao, tmp_path: Path) -> None:
    rel = en.Relogio(rec.inicio, rec.fim)
    sessao = en.SessaoEnsaio(en.Gerador(rec, rel))
    col = Coletor(ClienteDivulgacao("simulado", sessao=sessao, limitador=LimitadorTaxa(1e9)), tmp_path)
    rel.fixar(H(18, 45))
    r1 = col.ciclo()
    assert r1.arquivos_novos == 6  # governador e deputado: UF + Rio + Niterói
    gov = pl.read_parquet(tmp_path / "ultimo" / "totais.parquet").filter(
        (pl.col("CARGO") == 3) & (pl.col("ABRANGENCIA") == "uf")).row(0, named=True)
    assert gov["PCT_SECOES_TOTALIZADAS"] == 50
    r2 = col.ciclo()  # nada mudou: o acompanhamento diz que ninguém totalizou de novo
    assert r2.arquivos_pedidos == 0
    rel.fixar(H(19, 5))  # só Niterói totalizou de novo (19h)
    r3 = col.ciclo()
    assert r3.abrangencias_alteradas == 2 and r3.arquivos_novos == 4  # UF + Niterói, dois cargos
    rel.fixar(rec.fim)
    col.ciclo()
    fim = pl.read_parquet(tmp_path / "ultimo" / "totais.parquet").filter(pl.col("ABRANGENCIA") == "uf")
    assert fim["TOTALIZACAO_FINAL"].all()
    assert (tmp_path / "historico_serie.parquet").exists()  # a série do painel foi gravada ao longo do ensaio


def test_sessao_responde_como_o_tse(rec: en.Reconstituicao) -> None:
    rel = en.Relogio(rec.inicio, rec.fim)
    rel.fixar(H(18, 45))
    s = en.SessaoEnsaio(en.Gerador(rec, rel))
    assert s.get("x/nada.json").status_code == 404
    r = s.get("x/rj-c0003-e021272-u.json")
    assert r.status_code == 200 and r.headers["ETag"]
    assert s.get("x/rj-c0003-e021272-u.json", {"If-None-Match": r.headers["ETag"]}).status_code == 304  # igual: 304
    rel.fixar(H(19, 5))
    assert s.get("x/rj-c0003-e021272-u.json", {"If-None-Match": r.headers["ETag"]}).status_code == 200  # mudou
    assert s.get("x/ele-c.json").json()["pl"] and s.get("x/mun-e021270-cm.json").status_code == 200


def test_resumo_da_carga() -> None:
    from ensaio_apuracao import Carga
    c = Carga("http://x/", 1)
    c.medidas = [("api/painel", 200, 0.1), ("api/painel", 500, 0.3), ("api/painel", 404, 0.2)]
    (r,) = c.resumo()
    assert (r["pedidos"], r["erros_5xx_ou_rede"], r["404"], r["p50_ms"], r["max_ms"]) == (3, 1, 1, 200, 300)


def test_sessao_serve_a_lista_de_municipios_dada(rec: en.Reconstituicao) -> None:
    """Com a lista do 2022 importado, os municípios têm nome (antes: só os 3 do recorte de teste)."""
    from apuracao.divulgacao import modelo as m
    muns = pl.DataFrame([{"UF": "RJ", "CD_MUNICIPIO": 60011, "CD_MUNICIPIO_IBGE": 3304557, "NM_MUNICIPIO": "RIO DE JANEIRO",
                          "CAPITAL": True, "ZONAS": "4,5"},
                         {"UF": "RJ", "CD_MUNICIPIO": 58190, "CD_MUNICIPIO_IBGE": 3301702, "NM_MUNICIPIO": "DUQUE DE CAXIAS",
                          "CAPITAL": False, "ZONAS": "79"}], schema=m.MUNICIPIOS_SCHEMA)
    s = en.SessaoEnsaio(en.Gerador(rec, en.Relogio(rec.inicio, rec.fim)), muns)
    lido = m.parse_municipios(s.get("x/mun-e021272-cm.json").json())
    assert lido.sort("CD_MUNICIPIO").equals(muns.sort("CD_MUNICIPIO"))


def test_ensaio_com_o_atraso_do_tse(rec: en.Reconstituicao, tmp_path: Path) -> None:
    """Rodada 36: o EA20 sai alguns minutos depois do anúncio no EA15 (como o TSE em 04/10/2026). O coletor
    recebe a versão anterior, NÃO dá a totalização por vista e a busca de novo quando o TSE a publica."""
    from datetime import timedelta
    rel = en.Relogio(rec.inicio, rec.fim)
    sessao = en.SessaoEnsaio(en.Gerador(rec, rel, atraso_ea20_min=3))
    col = Coletor(ClienteDivulgacao("simulado", sessao=sessao, limitador=LimitadorTaxa(1e9)), tmp_path)
    rel.fixar(H(18, 31))
    r1 = col.ciclo()
    assert r1.arquivos_antigos > 0                       # Niterói anunciado às 18h30; o EA20 ainda é de 18h28
    rel.fixar(H(18, 31) + timedelta(seconds=30))
    assert col.ciclo().arquivos_antigos > 0              # ainda não publicado: pede de novo
    rel.fixar(rec.fim + timedelta(minutes=5))            # o TSE publicou tudo
    col.ciclo()
    fim = pl.read_parquet(tmp_path / "ultimo" / "totais.parquet").filter(pl.col("ABRANGENCIA") == "uf")
    assert fim["TOTALIZACAO_FINAL"].all()
    assert col.ciclo().arquivos_pedidos == 0
