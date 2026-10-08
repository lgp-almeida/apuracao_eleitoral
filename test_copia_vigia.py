"""Cópia de segurança (apuracao/copia.py) e vigia de processo (apuracao/vigia_site.py) — offline."""

from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from apuracao.copia import Copiador
from apuracao.vigia_site import VigiaSite, porta_do_comando


class Relogio:
    def __init__(self, t: str) -> None:
        self.t = datetime.fromisoformat(t)

    def __call__(self) -> datetime:
        return self.t


def _dados(raiz: Path, pct: float = 40.0, final: bool = False) -> Path:
    d = raiz / "dados"
    (d / "ultimo").mkdir(parents=True, exist_ok=True)
    pl.DataFrame([{"ABRANGENCIA": "uf", "UF": "RJ", "CARGO": 3, "PCT_SECOES_TOTALIZADAS": pct,
                   "TOTALIZACAO_FINAL": final}]).write_parquet(d / "ultimo" / "totais.parquet")
    (d / "status.json").write_text("{}")
    (d / "boletins").mkdir(exist_ok=True)
    (d / "boletins" / "boletim_ultimo.html").write_text("<p>b</p>")
    return d


def _parcial(d: Path, nome: str) -> None:
    alvo = d / "raw" / "21272" / "rj-c0003-e021272-u" / nome
    alvo.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(alvo, "wt") as fh:
        fh.write(json.dumps({"parcial": nome}))


# --------------------------------------------------------------------------- cópia de segurança
def test_copia_da_hora_espelha_todas_as_parciais(tmp_path: Path) -> None:
    d = _dados(tmp_path)
    _parcial(d, "20261004_190000_1_a.json.gz")
    relogio = Relogio("2026-10-04T19:37:00")
    c = Copiador(d, tmp_path / "copia", agora=relogio)
    r = c.verificar()
    assert r["nome"] == "2026-10-04_19h00" and r["raw_novos"] == 1
    inst = tmp_path / "copia" / "instantaneos" / "2026-10-04_19h00"
    assert (inst / "ultimo" / "totais.parquet").exists() and (inst / "boletins" / "boletim_ultimo.html").exists()
    assert not (inst / "raw").exists()                         # raw/ fica no espelho, sem duplicar por hora
    assert c.verificar() is None                               # mesma hora: nada
    _parcial(d, "20261004_194500_2_b.json.gz")                 # nova parcial do TSE
    c._ultimo_espelho = 0                                      # já passou o intervalo do espelho
    c.verificar()
    assert len(list((tmp_path / "copia" / "raw").rglob("*.json.gz"))) == 2   # espelhada sem esperar a hora
    relogio.t = datetime.fromisoformat("2026-10-04T20:01:00")
    assert c.verificar()["nome"] == "2026-10-04_20h00"
    registro = json.loads((tmp_path / "copia" / "copias.json").read_text())
    assert [x["nome"] for x in registro] == ["2026-10-04_19h00", "2026-10-04_20h00"]


def test_copia_espelha_raw_brasil(tmp_path: Path) -> None:
    """Os brutos do presidente nas outras UFs (raw_brasil/) também vão para o espelho, não para a hora."""
    d = _dados(tmp_path)
    alvo = d / "raw_brasil" / "21270" / "sp-c0001-e021270-u" / "20261004_190000_1_a.json.gz"
    alvo.parent.mkdir(parents=True)
    with gzip.open(alvo, "wt") as fh:
        fh.write("{}")
    c = Copiador(d, tmp_path / "copia", agora=Relogio("2026-10-04T19:37:00"))
    assert c.verificar()["raw_novos"] == 1
    assert (tmp_path / "copia" / "raw_brasil" / alvo.relative_to(d / "raw_brasil")).exists()
    assert not (tmp_path / "copia" / "instantaneos" / "2026-10-04_19h00" / "raw_brasil").exists()


def test_copia_final_e_poda(tmp_path: Path) -> None:
    d = _dados(tmp_path)
    c = Copiador(d, tmp_path / "copia", manter=2, agora=Relogio("2026-10-04T18:00:00"))
    for h in ("18", "19", "20", "21"):
        c.agora = Relogio(f"2026-10-04T{h}:05:00")
        c.verificar()
    c.copiar("manual_2026-10-04_21h30")
    nomes = sorted(p.name for p in (tmp_path / "copia" / "instantaneos").iterdir())
    assert nomes == ["2026-10-04_20h00", "2026-10-04_21h00", "manual_2026-10-04_21h30"]   # a manual não é podada
    _dados(tmp_path, 100.0, final=True)
    assert c.verificar()["nome"] == "final" and c.verificar() is None
    assert (tmp_path / "copia" / "instantaneos" / "final").exists()



def test_parcial_depois_do_final_e_espelhada_e_refaz_o_final(tmp_path: Path) -> None:
    """Rodada 70 (TODO 28): o TSE publica depois do final (EA20 regerado, retotalização) — antes, nunca copiado."""
    d = _dados(tmp_path, 100.0, final=True)
    _parcial(d, "antes.json.gz")
    copia = tmp_path / "copia"
    c = Copiador(d, copia, espelho_min=0, agora=Relogio("2026-10-05T00:20:00"))
    assert c.verificar()["nome"] == "final"
    assert c.verificar() is None                                   # nada novo: o final não é refeito
    _parcial(d, "depois.json.gz")
    (d / "status.json").write_text('{"depois": true}')
    r = c.verificar()
    assert r is not None and r["nome"] == "final" and r["raw_novos"] == 0  # o espelho veio antes do instantâneo
    assert (copia / "raw" / "21272" / "rj-c0003-e021272-u" / "depois.json.gz").exists()
    assert json.loads((copia / "instantaneos" / "final" / "status.json").read_text()) == {"depois": True}
    assert [x["nome"] for x in json.loads((copia / "copias.json").read_text())] == ["final", "final"]


def test_espelho_respeita_o_intervalo_e_encerrar_nao_espera(tmp_path: Path) -> None:
    d = _dados(tmp_path, 100.0, final=True)
    c = Copiador(d, tmp_path / "copia", espelho_min=5, agora=Relogio("2026-10-05T00:20:00"))
    c.verificar()
    _parcial(d, "tardia.json.gz")
    assert c.verificar() is None                                   # menos de 5 min desde o espelho
    assert not (tmp_path / "copia" / "raw").exists() or not list((tmp_path / "copia" / "raw").rglob("tardia*"))
    assert c.encerrar()["nome"] == "final"                         # fim do ensaio: espelha já
    assert list((tmp_path / "copia" / "raw").rglob("tardia.json.gz"))

def test_sem_dados_nao_copia_e_destino_dentro_dos_dados_e_recusado(tmp_path: Path) -> None:
    d = tmp_path / "dados"
    d.mkdir()
    assert Copiador(d, tmp_path / "copia").verificar() is None
    _dados(tmp_path, pct=0.0)
    assert Copiador(d, tmp_path / "copia").verificar() is None  # antes da apuração
    with pytest.raises(ValueError, match="dentro"):
        Copiador(d, d / "copias")


def test_erro_na_copia_nao_derruba_o_laco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    c = Copiador(_dados(tmp_path), tmp_path / "copia")
    parar, n = threading.Event(), []

    def falha():
        n.append(1)
        if len(n) == 3:
            parar.set()
        raise OSError("disco da cópia desconectado")

    monkeypatch.setattr(c, "verificar", falha)
    c.executar(parar, verificar_s=0.01)
    assert len(n) == 3


def test_cli_copiar_dados(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    import copiar_dados
    d = _dados(tmp_path)
    _parcial(d, "x.json.gz")
    assert copiar_dados.main(["--dados", str(d), "--destino", str(tmp_path / "c")]) == 0
    assert "1 parciais novas" in capsys.readouterr().out
    assert copiar_dados.main(["--dados", str(d), "--destino", str(d / "c")]) == 1


# --------------------------------------------------------------------------- vigia de processo
DORME = [sys.executable, "-c", "import time; time.sleep(60)"]


def test_porta_do_comando() -> None:
    assert porta_do_comando(["python", "site_apuracao.py", "--porta", "8022"]) == 8022
    assert porta_do_comando(["python", "site_apuracao.py", "--porta=8023"]) == 8023
    assert porta_do_comando(["python", "site_apuracao.py"]) == 8000


def test_vigia_reinicia_processo_que_termina(tmp_path: Path) -> None:
    v = VigiaSite([sys.executable, "-c", "import sys; sys.exit(3)", "--abrir"], 9999, tmp_path, espera_inicial_s=0,
                  sondar=lambda p: True)
    v.iniciar()
    v.proc.wait(10)
    v.passo()
    assert len(v.reinicios) == 1 and "--abrir" not in v.proc.args          # não reabre o Chrome a cada queda
    estado = json.loads((tmp_path / "porta_9999.json").read_text())
    assert estado["reinicios"] == 1 and any("código 3" in e["detalhe"] for e in estado["eventos"])
    assert "reinicio" in (tmp_path / "porta_9999.log").read_text()
    v.matar()


def test_vigia_reinicia_site_sem_resposta(tmp_path: Path) -> None:
    respostas = iter([True, False, False, False])
    v = VigiaSite(DORME, 9998, tmp_path, falhas_max=2, espera_inicial_s=0, sondar=lambda p: next(respostas))
    v.iniciar()
    pid = v.proc.pid
    v.passo()                                  # respondendo
    assert v.estado == "no ar" and not v.reinicios
    v.passo()                                  # 1ª falha: tolera
    assert v.proc.pid == pid and v.falhas == 1
    v.passo()                                  # 2ª falha: mata e sobe de novo
    assert v.proc.pid != pid and len(v.reinicios) == 1
    v.matar()


def test_vigia_tolera_o_inicio_lento(tmp_path: Path) -> None:
    v = VigiaSite(DORME, 9997, tmp_path, falhas_max=1, espera_inicial_s=60, sondar=lambda p: False)
    v.iniciar()
    v.passo()
    assert not v.reinicios and v.falhas == 0   # ainda na espera inicial (o 1º ciclo do coletor demora)
    v.matar()
    assert v.proc.poll() is not None


def test_portal_mostra_o_vigia_e_quem_caiu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    import portal
    (tmp_path / "porta_8000.json").write_text(json.dumps({"porta": 8000, "estado": "no ar", "reinicios": 2,
        "eventos": [{"hora": "2026-10-04T20:00:00", "tipo": "reinicio", "detalhe": "sem resposta"}]}))
    no_ar = {"estado": [{"porta": 8000, "titulo": "Apuração 2026 — RJ", "tipo": "oficial", "situacao": "coletando",
                         "progresso": [], "turno": 1}]}
    monkeypatch.setattr(portal, "servicos", lambda portas, host="127.0.0.1": no_ar["estado"])
    app = TestClient(portal.create_app([8000], tmp_path))
    s = app.get("/api/servicos").json()
    assert s[0]["vigia"]["reinicios"] == 2 and s[0]["situacao"] == "coletando"
    no_ar["estado"] = []                                        # o site caiu
    s = app.get("/api/servicos").json()
    assert s[0]["situacao"] == "fora do ar" and s[0]["titulo"] == "Apuração 2026 — RJ" and s[0]["fora_do_ar_desde"]
