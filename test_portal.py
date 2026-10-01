"""Portal (portal.py): lista só os sites da apuração que respondem — offline."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import portal
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import FakeTSE


class Resposta:
    def __init__(self, dados=None, ok=True, texto=False):
        self.ok, self._dados, self._texto = ok, dados, texto

    def json(self):
        if self._texto:
            raise ValueError("não é JSON")
        return self._dados


@pytest.fixture()
def rede(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dados = tmp_path / "dados"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados).ciclo()
    site = TestClient(create_app(dados, "RJ", tse_cache, {"ativo": True, "intervalo_s": 60}))
    respostas = {8001: lambda: Resposta(site.get("/api/status").json()),           # site da apuração
                 8002: lambda: Resposta({"status": "ok"}),                           # outro serviço com JSON
                 8003: lambda: Resposta(texto=True),                                 # página HTML
                 8004: lambda: Resposta(ok=False)}                                   # 404

    def get(url, timeout):
        porta = int(url.split(":")[2].split("/")[0])
        if porta not in respostas:
            raise requests.ConnectionError("nada escutando")
        return respostas[porta]()

    monkeypatch.setattr(portal.requests, "get", get)
    return dados


def test_so_os_sites_da_apuracao(rede) -> None:
    s = portal.servicos(list(range(8000, 8006)))
    assert [x["porta"] for x in s] == [8001]
    x = s[0]
    assert x["titulo"] == "Apuração 2026 — RJ" and x["tipo"] == "teste" and x["situacao"] == "coletando"
    assert x["dados"] == str(rede)
    # a UF tem duas eleições (federal e estadual): uma linha por abrangência
    nomes = [p["abrangencia"] for p in x["progresso"]]
    assert len(nomes) == len(set(nomes))


def test_progresso_junta_as_eleicoes_da_uf() -> None:
    linhas = [{"ABRANGENCIA": "uf", "UF": "RJ", "PCT_SECOES_TOTALIZADAS": 80.0, "TOTALIZACAO_FINAL": False},
              {"ABRANGENCIA": "uf", "UF": "RJ", "PCT_SECOES_TOTALIZADAS": 100.0, "TOTALIZACAO_FINAL": True},
              {"ABRANGENCIA": "br", "UF": "BR", "PCT_SECOES_TOTALIZADAS": 50.0, "TOTALIZACAO_FINAL": False}]
    assert portal._progresso(linhas) == [{"abrangencia": "RJ", "pct": 80.0, "final": False},
                                         {"abrangencia": "Brasil", "pct": 50.0, "final": False}]


def test_pagina_e_api(rede) -> None:
    app = TestClient(portal.create_app([8000, 8001, 8002]))
    assert [x["porta"] for x in app.get("/api/servicos").json()] == [8001]
    html = app.get("/").text
    assert "Portal da apuração" in html and "<script src" not in html and "<link" not in html  # autônomo
    assert "textContent" in html and "innerHTML" not in html                                  # texto sem HTML


def test_faixa_de_portas() -> None:
    assert portal._faixa("8000-8002") == [8000, 8001, 8002]
    with pytest.raises(portal.argparse.ArgumentTypeError):
        portal._faixa("9000-8000")
