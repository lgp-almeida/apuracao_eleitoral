"""Orquestrador de várias UFs (`baixar_ufs.py` / `apuracao/lote_ufs.py`, rodada 39) — offline, com o TSE falso."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import baixar_ufs
import votos_por_local_votacao as v
from apuracao import lote_ufs as lt
from apuracao.divulgacao.cliente import BloqueioTSE
from conftest import FakeTSE


def _final(fake: FakeTSE) -> FakeTSE:
    """Apuração encerrada: os arquivos da UF com totalização final (100% das seções)."""
    for eleicao in (21270, 21272):
        fake.avancar_uf(eleicao, "23:00:00", 100.0, 1.0)
    return fake


def _lote(tmp_path: Path, fake: FakeTSE, ufs: list[str], **kw) -> lt.Lote:
    cfg = lt.Config(ufs=ufs, etapas=kw.pop("etapas", ("divulgacao",)), ambiente="simulado", raiz=tmp_path,
                    cache=tmp_path / "cache", max_rps=1e9, pausa_ciclos=0, **kw)
    return lt.Lote(cfg, sessao=fake)


def test_divulgacao_completa_e_retomada(tmp_path: Path, fake_tse: FakeTSE) -> None:
    lote = _lote(tmp_path, _final(fake_tse), ["RJ"])
    estado = lote.executar()
    rj = estado["RJ"]["divulgacao_t1"]
    assert rj["situacao"] == lt.OK and "simulado_RJ" in rj["detalhe"]
    assert lt.divulgacao_completa(tmp_path / "simulado_RJ")
    assert json.loads((tmp_path / lt.ARQUIVO_ESTADO).read_text())["RJ"]["divulgacao_t1"]["situacao"] == lt.OK
    pedidos = len(fake_tse.pedidos)
    _lote(tmp_path, fake_tse, ["RJ"]).executar()  # já feita: nenhum acesso ao TSE
    assert len(fake_tse.pedidos) == pedidos
    _lote(tmp_path, fake_tse, ["RJ"], refazer=True).executar()  # --refazer: coleta de novo
    assert len(fake_tse.pedidos) > pedidos


def test_uma_uf_com_problema_nao_para_as_outras(tmp_path: Path, fake_tse: FakeTSE,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    clientes = []
    original = lt.ClienteDivulgacao

    def espiao(*a, **kw):
        clientes.append(kw["limitador"])
        return original(*a, **kw)

    monkeypatch.setattr(lt, "ClienteDivulgacao", espiao)
    vistos = []
    estado = _lote(tmp_path, _final(fake_tse), ["AC", "RJ"], max_ciclos=2).executar(
        lambda chave, uf, r: vistos.append((uf, r.situacao)))
    assert estado["AC"]["divulgacao_t1"]["situacao"] in (lt.INCOMPLETO, lt.ERRO)  # o TSE falso só tem o RJ
    assert estado["RJ"]["divulgacao_t1"]["situacao"] == lt.OK and [u for u, _ in vistos] == ["AC", "RJ"]
    assert len(clientes) == 2 and clientes[0] is clientes[1]  # UM limite de acessos para todas as UFs


def test_bloqueio_do_tse_suspende_a_divulgacao(tmp_path: Path, fake_tse: FakeTSE,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = []

    def bloqueado(self):
        chamadas.append(self.uf)
        raise BloqueioTSE("403 em sequência")

    monkeypatch.setattr(lt.Coletor, "ciclo", bloqueado)
    estado = _lote(tmp_path, fake_tse, ["AC", "RJ", "SP"]).executar()
    assert chamadas == ["ac"]  # depois do bloqueio, nenhuma outra UF acessa o TSE
    assert {estado[u]["divulgacao_t1"]["situacao"] for u in ("AC", "RJ", "SP")} == {lt.PENDENTE}


def test_historico_e_erro_inesperado(tmp_path: Path, fake_tse: FakeTSE, monkeypatch: pytest.MonkeyPatch) -> None:
    from apuracao import historico as h

    chamadas = []

    def importar(ano, uf, turno, cache, destino, fonte=None):
        chamadas.append((uf, turno, destino.name))
        if uf == "AC":
            raise RuntimeError("defeito")
        if turno == 2:
            raise v.TseDataError(f"sem totais para {uf} {ano}, 2º turno")
        (destino / "ultimo").mkdir(parents=True)
        (destino / "ultimo" / "totais.parquet").touch()
        (destino / "status.json").write_text(json.dumps({"ano": ano, "uf": uf, "fontes": ["votacao_candidato_munzona"]}))
        return {"candidatos": 10, "municipios": 2}

    monkeypatch.setattr(h, "importar", importar)
    estado = _lote(tmp_path, fake_tse, ["AC", "RR"], etapas=("historico",), turnos=(1, 2)).executar()
    assert estado["AC"]["historico_2022_t1"]["situacao"] == lt.ERRO and "defeito" in estado["AC"]["historico_2022_t1"]["detalhe"]
    assert estado["RR"]["historico_2022_t1"]["situacao"] == lt.OK and "munzona" in estado["RR"]["historico_2022_t1"]["detalhe"]
    assert estado["RR"]["historico_2022_t2"]["situacao"] == lt.NAO_SE_APLICA
    assert ("RR", 1, "historico_2022_t1_RR") in chamadas
    n = len(chamadas)
    _lote(tmp_path, fake_tse, ["RR"], etapas=("historico",), turnos=(1, 2)).executar()
    assert len(chamadas) == n  # RR: feito e "não se aplica" não são refeitos


def test_so_plano_nao_acessa_nada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(lt.Lote, "executar", lambda *a, **k: pytest.fail("não podia executar"))
    assert baixar_ufs.main(["--ufs", "AC", "rr", "--etapas", "divulgacao", "historico", "--so-plano",
                            "--raiz", str(tmp_path)]) == 0
    saida = capsys.readouterr().out
    assert "2 UF(s), 4 tarefas, 4 a fazer" in saida and "historico_2022_t1" in saida and "AC RR" in saida
    assert baixar_ufs.main(["--ufs", "XX", "--so-plano"]) == 2
    assert lt.resumo({"AC": {"x": {"situacao": "ok"}}}, ["AC", "RR"]).to_dicts() == [
        {"UF": "AC", "x": "ok"}, {"UF": "RR", "x": "—"}]


def test_microdados_provisorio_aguarda_e_oficial_fica_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rodada 40: importado com totais reconstruídos (provisório) segue "aguardando" e é refeito; com os
    oficiais (e o resto do FINAL) fica OK e deixa de ser repetido."""
    import preparar_2026 as p26
    from apuracao import ibge
    from apuracao import microdados as md
    from apuracao.ufs import dir_uf
    from test_microdados import CDN, OFICIAL, PROVISORIO, publicar

    importados: list[str] = []

    def importar(a, totais_de, turno, memo=None):
        importados.append(totais_de)
        destino = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "status.json").write_text(json.dumps({"ano": a.ano, "totais_de": totais_de}))
        return True
    monkeypatch.setattr(p26, "importar", importar)
    monkeypatch.setattr(md, "turnos", lambda *a: {1})  # os ZIPs falsos não têm NR_TURNO: só o 1º turno
    monkeypatch.setattr(p26, "transferencia", lambda a: None)
    monkeypatch.setattr(md, "converter", lambda *a: [])
    monkeypatch.setattr(ibge, "preparar", lambda *a, **k: [])
    cdn = CDN()

    def rodar() -> dict:
        cfg = lt.Config(ufs=["RJ"], etapas=("microdados",), raiz=tmp_path, cache=tmp_path / "cache")
        return lt.Lote(cfg, sessao=cdn).executar()["RJ"]["microdados_2026"]

    assert rodar()["situacao"] == lt.AGUARDANDO and importados == []
    publicar(cdn, PROVISORIO)
    e = rodar()
    assert e["situacao"] == lt.AGUARDANDO and "PROVISÓRIOS" in e["detalhe"] and importados == ["secoes"]
    publicar(cdn, OFICIAL)
    e = rodar()
    assert e["situacao"] == lt.OK and importados == ["secoes", "munzona"]
    heads = cdn.heads
    assert rodar()["situacao"] == lt.OK and cdn.heads == heads  # completo: pulado, sem acessar a CDN
