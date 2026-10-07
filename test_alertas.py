"""Alertas da noite (apuracao/alertas.py): condições, eventos, persistência e API — offline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient

import votos_por_local_votacao as v
from apuracao.alertas import Vigia
from apuracao.divulgacao import modelo as m
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import FakeTSE

UTC0 = datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc)   # 19h00 em Brasília


class Relogio:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def avancar(self, **kw: float) -> None:
        self.t += timedelta(**kw)


class FakeDados:
    def __init__(self) -> None:
        self.st: dict[str, Any] = {"ultimo_ciclo_fim": UTC0.isoformat(), "erro": None, "tipo_erro": None}
        self.linhas: list[dict[str, Any]] = []
        self.cand = pl.DataFrame([{"ABRANGENCIA": "uf", "UF": "RJ", "CARGO": 7, "NUMERO": 13713, "NOME_URNA": "FULANO"}])

    def cargo(self, cargo: int, pct: float, dt: datetime, final: bool = False) -> None:
        self.linhas = [r for r in self.linhas if r["CARGO"] != cargo] + [
            {"ABRANGENCIA": "uf", "UF": "RJ", "CARGO": cargo, "DS_CARGO": {3: "Governador", 7: "Deputado Estadual"}[cargo],
             "PCT_SECOES_TOTALIZADAS": pct, "TOTALIZACAO_FINAL": final, "DT_TOTALIZACAO": dt}]

    def status(self) -> dict[str, Any]:
        return self.st

    def tabela(self, nome: str) -> pl.DataFrame:
        if nome == "candidatos":
            return self.cand
        return pl.DataFrame(self.linhas, schema={k: m.TOTAIS_SCHEMA[k] for k in (
            "ABRANGENCIA", "UF", "CARGO", "DS_CARGO", "PCT_SECOES_TOTALIZADAS", "TOTALIZACAO_FINAL", "DT_TOTALIZACAO")})


@pytest.fixture()
def cenario(tmp_path: Path):
    dados = FakeDados()
    brasilia, utc = Relogio(datetime(2026, 10, 4, 19, 0)), Relogio(UTC0)
    leitura = {"situacao": "cedo demais: 1,0% do eleitorado apurado"}
    cadeiras: dict[str, Any] = {"final": False, "projecao": None}

    def projecao(cargo: int) -> dict[str, Any]:
        return {"situacao": leitura["situacao"], "pct_apurado": 42.5, "margem_pp": leitura.get("margem", 4.0),
                "candidatos": [{"NOME_URNA": "CASTRO", "PARTIDO": "PL", "PCT_PROJ": 55.1, "MIN": 51.2, "MAX": 59.0}]}

    def cad(cargo: int) -> dict[str, Any]:
        if cargo not in (6, 7, 8):
            raise ValueError("não proporcional")
        return cadeiras

    consultas = SimpleNamespace(dados=dados, uf="RJ", projecao=projecao, cadeiras=cad)
    dados.cargo(3, 10.0, datetime(2026, 10, 4, 18, 58))
    novo = lambda **kw: Vigia(consultas, tmp_path / "alertas.json", agora=brasilia, relogio_utc=utc, **kw)  # noqa: E731
    return SimpleNamespace(dados=dados, brasilia=brasilia, utc=utc, leitura=leitura, cadeiras=cadeiras,
                           vigia=novo(), novo=novo, arquivo=tmp_path / "alertas.json")


def chaves(alertas: list[dict[str, Any]]) -> list[str]:
    return [a["chave"] for a in alertas]


def test_coleta_parada_avisa_uma_vez_e_depois_resolve(cenario) -> None:
    v_ = cenario.vigia
    assert v_.verificar() == []
    cenario.utc.avancar(minutes=9)
    assert v_.verificar() == []                              # dentro de 10 min: normal
    cenario.utc.avancar(minutes=2)
    (a,) = v_.verificar()
    assert a["chave"] == "coletor:parado" and a["nivel"] == "critico" and "11 min" in a["titulo"]
    assert "19:00" in a["detalhe"]                           # hora de Brasília do último ciclo
    cenario.utc.avancar(minutes=5)
    assert v_.verificar() == []                              # não repete
    assert v_.lista()["ativos"][0]["titulo"] == "Coleta parada há 16 min"   # o texto acompanha
    cenario.dados.st["ultimo_ciclo_fim"] = cenario.utc.t.isoformat()
    (r,) = v_.verificar()
    assert r["chave"] == "coletor:parado:resolvido" and r["nivel"] == "ok" and not v_.lista()["ativos"]


def test_depois_da_totalizacao_final_coleta_parada_nao_e_alerta(cenario) -> None:
    cenario.dados.cargo(3, 100.0, datetime(2026, 10, 4, 23, 50), final=True)
    cenario.utc.avancar(hours=3)
    assert "coletor:parado" not in chaves(cenario.vigia.verificar())


def test_bloqueio_do_tse_e_critico_e_a_pausa_nao_vira_coleta_parada(cenario) -> None:
    cenario.dados.st.update(erro="TSE bloqueou (HTTP 403)", tipo_erro="bloqueio", pausa_s=660)
    (a,) = cenario.vigia.verificar()
    assert a["chave"] == "coletor:bloqueio" and a["nivel"] == "critico" and "11 min" in a["detalhe"]
    cenario.utc.avancar(minutes=15)                          # dentro de 10 min + a pausa de 11
    assert cenario.vigia.verificar() == []
    cenario.utc.avancar(minutes=7)
    assert chaves(cenario.vigia.verificar()) == ["coletor:parado"]


def test_falha_de_rede_isolada_nao_avisa_mas_persistente_sim(cenario) -> None:
    cenario.dados.st.update(erro="falha de rede: timeout", tipo_erro="rede")
    assert cenario.vigia.verificar() == []
    cenario.utc.avancar(seconds=60)
    cenario.dados.st.update(erro=None, tipo_erro=None, ultimo_ciclo_fim=cenario.utc.t.isoformat())
    assert cenario.vigia.verificar() == []                   # resolveu no ciclo seguinte: nenhum alerta
    cenario.dados.st.update(erro="falha de rede: timeout", tipo_erro="rede")
    assert cenario.vigia.verificar() == []
    cenario.utc.avancar(seconds=160)
    cenario.dados.st["ultimo_ciclo_fim"] = cenario.utc.t.isoformat()
    (a,) = cenario.vigia.verificar()
    assert a["chave"] == "coletor:erro:rede" and a["nivel"] == "aviso"


def test_divulgacao_indisponivel_avisa_na_hora(cenario) -> None:
    cenario.dados.st.update(erro="nenhuma eleição do 1º turno no ele-c.json", tipo_erro="indisponivel")
    (a,) = cenario.vigia.verificar()
    assert a["titulo"] == "Divulgação do TSE indisponível" and "5 min" in a["detalhe"]


def test_apuracao_sem_avanco(cenario) -> None:
    cenario.brasilia.t = datetime(2026, 10, 4, 19, 17)
    assert cenario.vigia.verificar() == []                   # 19 min desde a última totalização
    cenario.brasilia.t = datetime(2026, 10, 4, 19, 20)
    (a,) = cenario.vigia.verificar()
    assert a["chave"] == "apuracao:estagnada" and "22 min" in a["titulo"]
    assert "18:58" in a["detalhe"] and "10,00%" in a["detalhe"]
    cenario.dados.cargo(3, 12.0, datetime(2026, 10, 4, 19, 19))
    assert chaves(cenario.vigia.verificar()) == ["apuracao:estagnada:resolvido"]


def test_cauda_da_apuracao_nao_e_travamento(cenario) -> None:
    """Achado do ensaio: 2022 ficou em 99,99% das 23h33 às 00h07 — normal, não é para alarmar."""
    cenario.dados.cargo(3, 99.99, datetime(2026, 10, 4, 23, 33))
    cenario.brasilia.t = datetime(2026, 10, 4, 23, 58)
    assert cenario.vigia.verificar() == []
    cenario.dados.cargo(7, 97.0, datetime(2026, 10, 4, 23, 30))   # outro cargo ainda longe do fim: avisa
    assert chaves(cenario.vigia.verificar()) == ["apuracao:estagnada"]


def test_resultado_final_nao_e_chamado_de_projecao(cenario) -> None:
    cenario.leitura["situacao"] = "vitória no 1º turno projetada (acima de 50% mesmo na margem)"
    cenario.vigia.verificar()
    cenario.leitura["situacao"] = "vitória no 1º turno confirmada (acima de 50% mesmo na margem)"
    cenario.leitura["margem"] = 0
    (a,) = cenario.vigia.verificar()
    assert a["detalhe"].startswith("Antes: vitória no 1º turno projetada") and "CASTRO (PL) com 55,1% dos válidos." in a["detalhe"]
    assert "projeção de" not in a["detalhe"]


def test_sem_avanco_nao_e_avisado_quando_a_causa_e_a_coleta(cenario) -> None:
    cenario.brasilia.t = datetime(2026, 10, 4, 19, 40)
    cenario.utc.avancar(minutes=40)
    assert chaves(cenario.vigia.verificar()) == ["coletor:parado"]


def test_antes_da_apuracao_nada_esta_parado(cenario) -> None:
    cenario.dados.cargo(3, 0.0, datetime(2026, 10, 4, 8, 0))
    cenario.brasilia.t = datetime(2026, 10, 4, 16, 50)
    assert cenario.vigia.verificar() == []


def test_leitura_da_projecao_mudando(cenario) -> None:
    v_ = cenario.vigia
    assert v_.verificar() == []                               # "cedo demais" não é notícia
    cenario.leitura["situacao"] = "indefinido: o líder está a menos de uma margem dos 50%"
    assert v_.verificar() == []                               # de "cedo demais" para "indefinido": silêncio
    assert v_.verificar() == []
    cenario.leitura["situacao"] = "vitória no 1º turno projetada (acima de 50% mesmo na margem)"
    (a,) = v_.verificar()
    assert a["chave"] == "leitura:3" and a["nivel"] == "noticia"
    assert a["titulo"] == "Governador: vitória no 1º turno projetada (acima de 50% mesmo na margem)"
    assert a["detalhe"] == ("Antes: indefinido. Líder: CASTRO (PL), projeção de 55,1% (de 51,2% a 59,0%). "
                            "42,5% do eleitorado apurado.")


def test_de_cedo_demais_direto_para_uma_leitura_definida_e_noticia(cenario) -> None:
    assert cenario.vigia.verificar() == []
    cenario.leitura["situacao"] = "2º turno projetado (ninguém chega a 50% mesmo na margem)"
    assert cenario.vigia.verificar()[0]["titulo"].startswith("Governador: 2º turno projetado")


def test_leitura_definida_logo_no_inicio_da_apuracao_e_noticia(cenario) -> None:
    """Ensaio AM 2º turno (07/10/2026): antes de qualquer seção nada é lido; no ciclo seguinte a projeção já
    diz "vitória projetada". Antes, essa era a 1ª observação e não saía alerta."""
    cenario.dados.cargo(3, 0.0, datetime(2026, 10, 4, 17, 0))
    cenario.brasilia.t = datetime(2026, 10, 4, 17, 5)
    assert cenario.vigia.verificar() == []
    cenario.dados.cargo(3, 8.0, datetime(2026, 10, 4, 17, 20))
    cenario.brasilia.t = datetime(2026, 10, 4, 17, 21)
    cenario.leitura["situacao"] = "vitória projetada (acima de 50% mesmo na margem)"
    (a,) = cenario.vigia.verificar()
    assert a["titulo"] == "Governador: vitória projetada (acima de 50% mesmo na margem)"
    assert a["detalhe"].startswith("Antes: sem apuração.")
    # um site que sobe no meio da apuração, sem alertas.json, continua sem alertar a 1ª leitura
    cenario.arquivo.unlink()
    assert cenario.novo().verificar() == []


def test_deputado_de_interesse(cenario) -> None:
    v_ = cenario.novo(interesse=[(7, 13713)])
    cenario.dados.cargo(7, 20.0, datetime(2026, 10, 4, 18, 58))
    assert v_.verificar() == [] and v_.lista()["interesse"] == [
        {"cargo": 7, "numero": 13713, "nome": "13713 FULANO", "situacao": None}]   # antes de 30%: sem situação
    proj = {"ativa": True, "simulacoes": 300, "pct_apurado": 35.0,
            "candidatos": [{"NUMERO": 13713, "STATUS": "em disputa (dentro)", "FREQ_ELEITO": 0.8, "VOTOS_PROJ": 41234.4}]}
    cenario.cadeiras["projecao"] = proj
    assert v_.verificar() == []                               # 1ª situação: em silêncio
    proj["candidatos"][0].update(STATUS="consolidado", FREQ_ELEITO=0.97)
    (a,) = v_.verificar()
    assert a["titulo"] == "13713 FULANO: consolidado"
    assert a["detalhe"] == ("Antes: em disputa, dentro das vagas. Eleito em 97% das 300 simulações; "
                            "41.234 votos projetados com 35,0% apurado.")
    proj["candidatos"] = []
    assert v_.verificar()[0]["titulo"] == "13713 FULANO: fora da disputa"
    cenario.cadeiras.update(final=True, eleitos=[{"NUMERO": 13713, "SITUACAO_PROJETADA": "Eleito por média",
                                                  "VOTOS": 45001}])
    a = v_.verificar()[0]
    assert (a["titulo"], a["detalhe"]) == ("13713 FULANO: eleito",
                                           "Antes: fora da disputa. Eleito por média, 45.001 votos.")


def test_interesse_so_de_deputado(cenario) -> None:
    with pytest.raises(ValueError, match="deputado"):
        cenario.vigia.definir_interesse(3, 22, True)
    cenario.vigia.definir_interesse(7, 13713, True)
    cenario.vigia.definir_interesse(7, 13713, True)            # repetido não duplica
    assert [(i["cargo"], i["numero"]) for i in cenario.vigia.lista()["interesse"]] == [(7, 13713)]
    cenario.vigia.definir_interesse(7, 13713, False)
    assert cenario.vigia.lista()["interesse"] == []


def test_reiniciar_nao_repete_nem_perde(cenario) -> None:
    cenario.leitura["situacao"] = "indefinido: o líder está a menos de uma margem dos 50%"
    cenario.utc.avancar(minutes=12)
    assert chaves(cenario.vigia.verificar()) == ["coletor:parado"]
    de_novo = cenario.novo()                                   # site reiniciado: lê alertas.json
    assert de_novo.verificar() == []                           # a condição e a leitura já eram conhecidas
    assert de_novo.lista(desde=0)["ultimo_id"] == 1 and len(de_novo.lista()["ativos"]) == 1
    cenario.leitura["situacao"] = "2º turno projetado (ninguém chega a 50% mesmo na margem)"
    assert de_novo.verificar()[0]["id"] == 2
    assert [a["id"] for a in de_novo.lista(desde=1)["alertas"]] == [2]


def test_alertas_json_corrompido_nao_impede_o_site(cenario) -> None:
    cenario.arquivo.write_text("{ não é json")
    assert cenario.novo().lista()["ultimo_id"] == 0


def test_eleicao_passada_nao_tem_alertas(cenario) -> None:
    cenario.dados.st["ano"] = 2022
    cenario.utc.avancar(days=300)
    assert cenario.vigia.verificar() == [] and not cenario.arquivo.exists()


def test_erro_na_verificacao_nao_derruba_o_laco(cenario, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    parar, chamadas = threading.Event(), []

    def falha() -> None:
        chamadas.append(1)
        if len(chamadas) == 3:
            parar.set()
        raise v.TseDataError("parquet sendo gravado")

    monkeypatch.setattr(cenario.vigia, "verificar", falha)
    cenario.vigia.executar(parar, verificar_s=0.01)
    assert len(chamadas) == 3


# --------------------------------------------------------------------------- API (TSE falso)
def test_api_de_alertas(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> None:
    dados = tmp_path / "dados"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados).ciclo()
    status = json.loads((dados / "status.json").read_text())
    status.update(erro="TSE bloqueou (HTTP 429)", tipo_erro="bloqueio", pausa_s=660)
    (dados / "status.json").write_text(json.dumps(status))
    app = create_app(dados, "RJ", tse_cache, interesse=((7, 13713),))
    site = TestClient(app)
    assert site.get("/api/alertas").json()["alertas"] == []
    app.state.vigia.verificar()
    r = site.get("/api/alertas").json()
    assert [a["chave"] for a in r["alertas"]] == ["coletor:bloqueio"] and r["ativos"][0]["nivel"] == "critico"
    assert site.get(f"/api/alertas?desde={r['ultimo_id']}").json()["alertas"] == []
    assert [i["numero"] for i in r["interesse"]] == [13713]

    assert site.post("/api/alertas/interesse", json={"cargo": 3, "numero": 22}).status_code == 400
    r = site.post("/api/alertas/interesse", json={"cargo": 7, "numero": 13713, "acompanhar": False}).json()
    assert r["interesse"] == []
    # na rede, só a própria máquina muda os candidatos de interesse (ler os alertas é livre)
    exposto = create_app(dados, "RJ", tse_cache, pesadas_so_local=True)
    fora = TestClient(exposto, client=("192.168.0.20", 5000))
    assert fora.get("/api/alertas").status_code == 200
    assert fora.post("/api/alertas/interesse", json={"cargo": 7, "numero": 1}).status_code == 403
