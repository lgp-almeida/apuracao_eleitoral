"""Divulgação em tempo real (TSE 2026): parse, caminhos, cliente e coletor incremental — offline.

Os JSON em tests/fixtures/divulgacao são recortes reais do ambiente de simulado do TSE
(29/09/2026; nomes de candidatos fictícios do próprio TSE, inclusive com aspas e símbolos).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from apuracao.divulgacao import modelo as m
from apuracao.divulgacao.cliente import ClienteDivulgacao, DivulgacaoIndisponivel, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from conftest import DIVULGACAO_FIXTURES, FakeTSE


def _fx(nome: str) -> dict:
    return json.loads((DIVULGACAO_FIXTURES / nome).read_text(encoding="utf-8"))


def _cliente(fake: FakeTSE) -> ClienteDivulgacao:
    return ClienteDivulgacao("simulado", sessao=fake, limitador=LimitadorTaxa(1e9))


# ---------------------------------------------------------------- modelo
def test_config_eleicoes_e_cargos() -> None:
    cfg = m.parse_config(_fx("ele-c.json"))
    assert cfg.ciclo == "ele2026" and cfg.pleito == 17801
    assert cfg.por_cargo(7).codigo == 21272 and cfg.por_cargo(1).codigo == 21270
    assert cfg.por_cargo(3, turno=2).codigo == 21273
    assert cfg.por_cargo(7).cargo(7).proporcional and not cfg.por_cargo(3).cargo(3).proporcional


def test_municipios_trazem_codigo_ibge() -> None:
    mun = m.parse_municipios(_fx("mun-e021272-cm.json"))
    rio = mun.filter(pl.col("CD_MUNICIPIO") == 60011).row(0, named=True)
    assert rio["CD_MUNICIPIO_IBGE"] == 3304557 and rio["CAPITAL"] and rio["UF"] == "RJ"


def test_resultado_governador_uf() -> None:
    r = m.parse_resultado(_fx("rj-c0003-e021272-u.json"), "rj")
    t = r.totais.row(0, named=True)
    assert (t["ABRANGENCIA"], t["UF"], t["CD_MUNICIPIO"]) == ("uf", "RJ", None)
    assert (t["SECOES_TOTALIZADAS"], t["ELEITORADO"], t["VALIDOS"]) == (38926, 13319487, 7824970)
    assert t["PCT_ABSTENCAO"] == pytest.approx(14.863019875)  # campo de alta precisão (pan)
    assert t["DT_TOTALIZACAO"] == datetime(2026, 9, 29, 16, 37, 51) and t["TOTALIZACAO_FINAL"]
    primeiro = r.candidatos.sort("SEQ").row(0, named=True)
    assert primeiro["SITUACAO"] == "2º turno" and primeiro["VICES"]
    # os votos dos candidatos incluem os anulados sub judice (candidatura sub judice)
    assert r.candidatos["VOTOS"].sum() == t["VALIDOS"] + t["ANULADOS_SUB_JUDICE"]
    assert set(r.candidatos["DESTINACAO"]) == {"Válido", "Anulado sub judice"}


def test_senado_duas_vagas_e_proporcional() -> None:
    s = m.parse_resultado(_fx("rj-c0005-e021272-u.json"), "rj")
    assert s.totais["VAGAS"].item() == 2 and s.candidatos["ELEITO"].sum() == 2
    d = m.parse_resultado(_fx("rj60011-c0007-e021272-u.json"), "rj")
    t = d.totais.row(0, named=True)
    assert (t["ABRANGENCIA"], t["CD_MUNICIPIO"], t["VAGAS"]) == ("mun", 60011, 80)
    assert d.partidos["VOTOS_LEGENDA"].sum() > 0


def test_nomes_com_caracteres_especiais_sao_preservados() -> None:
    br = m.parse_resultado(_fx("br-c0001-e021270-u.json"), "br")
    assert br.totais["ABRANGENCIA"].item() == "br"
    assert any('"TSE"' in n for n in br.candidatos["NOME_URNA"].to_list())


# ---------------------------------------------------------------- cliente
def test_caminhos_montados_pelos_modelos_do_ele_c() -> None:
    cfg = m.parse_config(_fx("ele-c.json"))
    c = ClienteDivulgacao("simulado")
    assert c.caminho_resultado(cfg, 21272, "RJ", 7, 60011) == "ele2026/21272/dados/rj/rj60011-c0007-e021272-u.json"
    assert c.caminho_acompanhamento(cfg, 21270, "br") == "ele2026/21270/dados/br/br-e021270-ab.json"
    assert c.caminho_municipios(cfg, 21272) == "ele2026/21272/config/mun-e021272-cm.json"
    assert c.url("x.json") == "https://resultados-sim.tse.jus.br/simulado/simulado2026/x.json"


def test_cliente_etag_304_e_404_memorizado(fake_tse: FakeTSE) -> None:
    c = _cliente(fake_tse)
    r1 = c.get_json("ele2026/21272/dados/rj/rj-c0003-e021272-u.json")
    r2 = c.get_json("ele2026/21272/dados/rj/rj-c0003-e021272-u.json")
    assert r1.mudou and not r2.mudou and r2.dados == r1.dados
    assert c.get_json("nao/existe.json") is None
    assert c.get_json("nao/existe.json") is None
    assert c.estatisticas["404"] == 1 and c.estatisticas["404_evitado"] == 1  # não repete o 404
    c.novo_ciclo()
    assert c.get_json("nao/existe.json") is None and c.estatisticas["404"] == 2


def test_cliente_pagina_html_vira_indisponivel(fake_tse: FakeTSE) -> None:
    fake_tse.html = True
    with pytest.raises(DivulgacaoIndisponivel):
        _cliente(fake_tse).get_json("comum/config/ele-c.json")


def test_limitador_de_taxa() -> None:
    agora = [0.0]
    esperas: list[float] = []
    lim = LimitadorTaxa(20, relogio=lambda: agora[0], dormir=lambda s: (esperas.append(s), agora.__setitem__(0, agora[0] + s)))
    for _ in range(3):
        lim.aguardar()
    assert esperas == pytest.approx([0.05, 0.05])


# ---------------------------------------------------------------- coletor
def test_coletor_primeiro_ciclo_e_incremental(fake_tse: FakeTSE, tmp_path: Path) -> None:
    col = Coletor(_cliente(fake_tse), tmp_path)
    r1 = col.ciclo()
    # estadual: uf + 3 municípios × 4 cargos; federal: br + uf + 3 municípios × presidente
    assert (r1.abrangencias_alteradas, r1.arquivos_novos, r1.arquivos_404) == (9, 21, 0)
    tot = pl.read_parquet(tmp_path / "ultimo" / "totais.parquet")
    assert tot.height == 21 and set(tot["CARGO"]) == {1, 3, 5, 6, 7}
    assert tot.filter((pl.col("CARGO") == 3) & (pl.col("ABRANGENCIA") == "uf"))["ELEITORADO"].item() == 13319487
    assert pl.read_parquet(tmp_path / "ultimo" / "municipios.parquet").height == 3
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["erro"] is None and status["ciclo_tse"] == "ele2026"
    brutos = list((tmp_path / "raw").rglob("*.json.gz"))
    assert len(brutos) == 21 + 3  # EA20 + 3 acompanhamentos

    r2 = col.ciclo()  # nada mudou no TSE: só os 3 acompanhamentos, respondidos com 304
    assert (r2.abrangencias_alteradas, r2.arquivos_pedidos) == (0, 0)
    assert r2.estatisticas.get("304") == 3

    fake_tse.totalizar(21272, 60011)  # nova totalização no Rio (eleição estadual)
    r3 = col.ciclo()
    assert (r3.abrangencias_alteradas, r3.arquivos_pedidos) == (1, 4)  # 4 cargos do Rio
    assert pl.read_parquet(tmp_path / "historico_totais.parquet").height == 21


def test_coletor_segundo_turno_so_governador_e_presidente(fake_tse: FakeTSE, tmp_path: Path) -> None:
    col = Coletor(_cliente(fake_tse), tmp_path, turno=2)
    col.preparar()
    assert col._eleicoes == {21273: (3,), 21271: (1,)}


def test_coletor_ambiente_indisponivel(fake_tse: FakeTSE, tmp_path: Path) -> None:
    fake_tse.html = True
    col = Coletor(_cliente(fake_tse), tmp_path)
    col.executar(intervalo=0, max_ciclos=1)
    assert "não disponível" in json.loads((tmp_path / "status.json").read_text())["erro"]


def test_segundo_turno_nao_grava_por_cima_do_primeiro() -> None:
    from apuracao.divulgacao.coletor import destino_padrao
    assert destino_padrao("oficial") == Path("dados_2026/oficial")
    assert destino_padrao("oficial", turno=2) == Path("dados_2026/oficial_t2")


# ---------------------------------------------------------------- robustez na noite (rodada 27)
RIO_GOV = "rj60011-c0003-e021272-u.json"


def _hora_rio_governador(destino: Path) -> str:
    tot = pl.read_parquet(destino / "ultimo" / "totais.parquet")
    return f'{tot.filter((pl.col("CARGO") == 3) & (pl.col("CD_MUNICIPIO") == 60011))["DT_TOTALIZACAO"].item():%H:%M:%S}'


@pytest.mark.parametrize("falha", ["rede", 500, 404, 200])  # 200 = HTML no lugar do JSON
def test_arquivo_que_falhou_e_pedido_de_novo_no_ciclo_seguinte(fake_tse: FakeTSE, tmp_path: Path, falha) -> None:
    """A totalização FINAL de um município acontece uma vez só: se o arquivo dela falhar, o coletor
    não pode dar a abrangência por vista, senão o município fica parado no parcial a noite toda."""
    col = Coletor(_cliente(fake_tse), tmp_path)
    col.ciclo()
    fake_tse.avancar_municipio(21272, 60011, "23:59:59", 100, {})
    fake_tse.falhas[RIO_GOV] = falha
    r2 = col.ciclo()  # a falha de um arquivo não derruba o ciclo inteiro (os outros 3 cargos: 304)
    assert (r2.arquivos_pedidos, r2.arquivos_304) == (4, 3) and _hora_rio_governador(tmp_path) != "23:59:59"
    r3 = col.ciclo()  # a abrangência é pedida de novo inteira; o que não mudou volta como 304
    assert (r3.arquivos_pedidos, r3.arquivos_novos, r3.arquivos_304) == (4, 1, 3)
    assert _hora_rio_governador(tmp_path) == "23:59:59"
    assert col.ciclo().arquivos_pedidos == 0  # e depois disso a abrangência está em dia


def test_404_persistente_desiste_depois_de_algumas_tentativas(fake_tse: FakeTSE, tmp_path: Path) -> None:
    """Vários 404 podem bloquear o IP: um arquivo que não existe não é pedido para sempre."""
    col = Coletor(_cliente(fake_tse), tmp_path)
    col.ciclo()
    fake_tse.avancar_municipio(21272, 60011, "23:59:59", 100, {})
    pedidos = []
    for _ in range(6):
        fake_tse.falhas[RIO_GOV] = 404
        pedidos.append(col.ciclo().arquivos_pedidos)
    assert pedidos == [4, 4, 4, 0, 0, 0]  # TENTATIVAS_404 = 3


def test_bloqueio_no_meio_do_ciclo_nao_perde_o_que_ja_veio(fake_tse: FakeTSE, tmp_path: Path) -> None:
    """Arquivos baixados antes do 403 ficam no cache de ETag do cliente: no ciclo seguinte vêm
    como 304, e o coletor ainda assim tem de usá-los (não os tinha guardado)."""
    from apuracao.divulgacao.cliente import BloqueioTSE
    col = Coletor(_cliente(fake_tse), tmp_path, downloads_simultaneos=1)
    fake_tse.falhas["rj60011-c0005-e021272-u.json"] = 403
    with pytest.raises(BloqueioTSE):
        col.ciclo()
    r = col.ciclo()
    assert r.estatisticas.get("304", 0) > 0 and r.arquivos_novos == 21
    assert pl.read_parquet(tmp_path / "ultimo" / "totais.parquet").height == 21


def test_erro_inesperado_nao_mata_o_laco(fake_tse: FakeTSE, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    col = Coletor(_cliente(fake_tse), tmp_path)
    original, chamadas = col.ciclo, []

    def ciclo_com_defeito():
        chamadas.append(1)
        if len(chamadas) == 1:
            raise KeyError("tpabr")  # ex.: JSON do TSE com estrutura inesperada
        return original()

    monkeypatch.setattr(col, "ciclo", ciclo_com_defeito)
    col.executar(intervalo=0, max_ciclos=2)
    assert len(chamadas) == 2
    assert json.loads((tmp_path / "status.json").read_text())["erro"] is None  # o 2º ciclo deu certo
