"""Boletim da apuração (HTML de um arquivo + planilha, a cada hora e no fim) — offline, TSE falso."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from apuracao.boletim import Boletineiro, montar, para_html
from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor
from apuracao.web.app import create_app
from conftest import NOME_COM_HTML, FakeTSE


class Relogio:
    def __init__(self, t: str) -> None:
        self.t = datetime.fromisoformat(t)

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture()
def apuracao(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path):
    """Governador a 40% no estado (em andamento); os recortes do TSE falso vêm com totalização final."""
    fake_tse._doc("rj-c0003-e021272-u.json")["carg"][0]["agr"][-1]["par"][0]["cand"][0]["nmu"] = NOME_COM_HTML
    dados = tmp_path / "dados"
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados)
    col.ciclo()
    app = create_app(dados, "RJ", tse_cache)
    relogio = Relogio("2026-10-04T19:37:12")
    return {"app": app, "coletor": col, "fake": fake_tse, "dados": dados, "relogio": relogio,
            "boletineiro": Boletineiro(app.state.consultas, dados / "boletins", agora=relogio)}


def test_um_boletim_por_hora_cheia_enquanto_a_apuracao_anda(apuracao) -> None:
    b, relogio = apuracao["boletineiro"], apuracao["relogio"]
    apuracao["fake"].avancar_uf(21272, "19:00:00", 40.0, 1.1)
    apuracao["coletor"].ciclo()
    assert b.situacao() == "andamento"

    feitos = b.verificar()
    assert [p.name for p in feitos] == ["boletim_2026-10-04_19h00.html", "boletim_2026-10-04_19h00.xlsx"]
    assert (b.destino / "boletim_ultimo.html").read_bytes() == feitos[0].read_bytes()
    assert b.verificar() == []                      # mesma hora: nada de novo
    relogio.t = datetime.fromisoformat("2026-10-04T19:59:59")
    assert b.verificar() == []
    relogio.t = datetime.fromisoformat("2026-10-04T20:00:05")
    assert [p.name for p in b.verificar()][0] == "boletim_2026-10-04_20h00.html"
    # reiniciar o processo não repete o boletim: os arquivos gravados são a memória
    de_novo = Boletineiro(apuracao["app"].state.consultas, b.destino, agora=relogio)
    assert de_novo.verificar() == []
    assert not list(b.destino.glob(".*"))           # nenhum temporário esquecido

    texto = feitos[0].read_text(encoding="utf-8")
    assert "<title>Boletim das 19h — Apuração RJ</title>" in texto
    assert "Projeção (" in texto and "margem ±" in texto          # governador em andamento: projeção
    assert NOME_COM_HTML not in texto and "&lt;b id=&quot;injetado&quot;&gt;" in texto
    assert not re.search(r"<script|<link|src=|https?://(?!resultados\.tse)", texto)  # autônomo


def test_boletim_tem_os_mesmos_numeros_do_site(apuracao) -> None:
    apuracao["fake"].avancar_uf(21272, "19:00:00", 40.0, 1.1)
    apuracao["coletor"].ciclo()
    b = apuracao["boletineiro"]
    xlsx = b.verificar()[1]
    site = TestClient(apuracao["app"])
    painel = {(c["cargo"], c["abrangencia"]): c for c in site.get("/api/painel").json()["cartoes"]}
    wb = openpyxl.load_workbook(xlsx)
    assert {"Resumo", "Cargos", "Governador RJ", "Dep. Estadual RJ cadeiras", "Dep. Estadual RJ eleitos"} <= set(wb.sheetnames)

    gov = wb["Governador RJ"]
    cab = [c.value for c in gov[1]]
    linhas = [dict(zip(cab, (c.value for c in r))) for r in gov.iter_rows(min_row=2)]
    esperado = painel[(3, "RJ")]["candidatos"]
    assert [(r["Número"], r["Votos"]) for r in linhas] == [(k["NUMERO"], k["VOTOS"]) for k in esperado]
    proj = site.get("/api/projecao?cargo=3").json()["candidatos"][0]
    lider = next(r for r in linhas if r["Número"] == proj["NUMERO"])
    assert lider["Projeção"] == pytest.approx(proj["PCT_PROJ"] / 100)

    cad = site.get("/api/cadeiras?cargo=7").json()
    ws = wb["Dep. Estadual RJ cadeiras"]
    cab = [c.value for c in ws[1]]
    vagas = sum(dict(zip(cab, (c.value for c in r)))["Vagas (apuração atual)"] or 0 for r in ws.iter_rows(min_row=2))
    assert vagas == cad["vagas"] - cad["vagas_nao_preenchidas"]
    assert wb["Dep. Estadual RJ eleitos"].max_row - 1 == len(cad["eleitos"])


def test_boletim_final_uma_vez_quando_tudo_termina(apuracao) -> None:
    b = apuracao["boletineiro"]
    assert b.situacao() == "final"                  # os recortes do TSE falso já vêm totalizados
    feitos = b.verificar()
    assert [p.name for p in feitos] == ["boletim_final.html", "boletim_final.xlsx"]
    assert b.verificar() == []
    apuracao["relogio"].t = datetime.fromisoformat("2026-10-04T23:00:00")
    assert b.verificar() == []                      # depois do final não há boletim de hora
    texto = feitos[0].read_text(encoding="utf-8")
    assert "Boletim final" in texto and "totalização final" in texto and "Projeção (" not in texto


def test_sem_votos_nao_gera_boletim(tmp_path: Path, tse_cache: Path) -> None:
    app = create_app(tmp_path / "vazio", "RJ", tse_cache)
    b = Boletineiro(app.state.consultas, tmp_path / "vazio" / "boletins")
    assert b.situacao() == "sem dados" and b.verificar() == []
    html = para_html(montar(app.state.consultas, datetime(2026, 10, 4, 17), "Boletim das 17h"))
    assert "Ainda não há votos apurados" in html


@pytest.mark.parametrize("intervalo, hora, nome", [(60, "19:37", "19h00"), (30, "19:37", "19h30"),
                                                   (15, "00:14", "00h00"), (120, "19:37", "18h00")])
def test_horario_do_boletim(apuracao, intervalo: int, hora: str, nome: str) -> None:
    b = Boletineiro(apuracao["app"].state.consultas, apuracao["dados"] / "b", intervalo,
                    agora=Relogio(f"2026-10-04T{hora}:00"))
    apuracao["fake"].avancar_uf(21272, "19:00:00", 40.0, 1.1)
    apuracao["coletor"].ciclo()
    assert b.verificar()[0].name == f"boletim_2026-10-04_{nome}.html"


def test_erro_no_boletim_nao_derruba_o_laco(apuracao, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    b = apuracao["boletineiro"]
    chamadas = []

    def falha() -> list[Path]:
        chamadas.append(1)
        if len(chamadas) == 3:
            parar.set()
        raise RuntimeError("disco cheio")

    parar = threading.Event()
    monkeypatch.setattr(b, "verificar", falha)
    b.executar(parar, verificar_s=0.01)
    assert len(chamadas) == 3


def test_cli_gera_boletim_agora(apuracao, tse_cache: Path, capsys: pytest.CaptureFixture) -> None:
    import gerar_boletim

    saida = apuracao["dados"] / "fora_de_hora"
    assert gerar_boletim.main(["--dados", str(apuracao["dados"]), "--saida", str(saida),
                               "--cache-dir", str(tse_cache)]) == 0
    assert (saida / "boletim_final.html").exists() and (saida / "boletim_final.xlsx").exists()
    assert gerar_boletim.main(["--dados", str(apuracao["dados"] / "nada")]) == 1


def test_final_nao_espera_o_presidente_no_brasil(fake_tse: FakeTSE, tse_cache: Path, tmp_path: Path) -> None:
    """Achado do ensaio: o RJ terminou às 00h19 de 2022 e o Brasil ficou em 99,94% (exterior)."""
    br = fake_tse._docs["br-c0001-e021270-u.json"]
    br["tf"], br["s"]["pst"], br["s"]["pstn"] = "n", "99,94", "99,94"
    dados = tmp_path / "dados"
    Coletor(ClienteDivulgacao("simulado", sessao=fake_tse, limitador=LimitadorTaxa(1e9)), dados).ciclo()
    app = create_app(dados, "RJ", tse_cache)
    b = Boletineiro(app.state.consultas, dados / "boletins", agora=Relogio("2026-10-05T00:25:00"))
    assert b.situacao() == "final"
    texto = b.verificar()[0].read_text(encoding="utf-8")
    assert "Boletim final" in texto and "99,94% das seções" in texto   # o Brasil aparece com o % que tem


def test_boletim_destaca_partidos(apuracao, tse_cache: Path) -> None:
    """Rodada 31: `--destacar` marca ★ nas listas de eleitos do HTML e "Sim" na planilha."""
    site = TestClient(apuracao["app"])
    eleitos = site.get("/api/cadeiras?cargo=7").json()["eleitos"]
    alvo = eleitos[0]["PARTIDO"]
    b = Boletineiro(apuracao["app"].state.consultas, apuracao["dados"] / "bd", agora=apuracao["relogio"],
                    destacar=[alvo, '<i>x</i>'])
    html_, xlsx = b.gerar("boletim_teste", "Boletim de teste")
    texto = html_.read_text(encoding="utf-8")
    n = sum(e["PARTIDO"] == alvo for e in eleitos)
    assert texto.count("<tr class=destaque>") >= n and "★ Destaque nas listas de eleitos" in texto
    assert "<i>x</i>" not in texto and "&lt;i&gt;x&lt;/i&gt;" in texto          # sigla vinda de fora: escapada
    ws = openpyxl.load_workbook(xlsx)["Dep. Estadual RJ eleitos"]
    cab = [c.value for c in ws[1]]
    marcados = [row[cab.index("Partido")].value for row in ws.iter_rows(min_row=2) if row[cab.index("Destacado")].value == "Sim"]
    assert len(marcados) == n and set(marcados) == {alvo}


# --------------------------------------------------------------------------- o que mudou (rodada 33)
def _foto(pct, lider, leitura, vagas, eleitos, consolidados=None, final=False):
    return {"titulo": "Boletim das 19h", "gerado_em": "2026-10-04T19:00:05", "cargos": {
        "3-RJ": {"ds": "Governador — RJ", "pct": pct, "final": final, "lider": lider, "leitura": leitura},
        "7-RJ": {"ds": "Deputado Estadual — RJ", "pct": pct, "final": final, "vagas": vagas, "eleitos": eleitos,
                 "consolidados": consolidados}}}


def test_mudancas_entre_duas_fotografias() -> None:
    from apuracao.boletim import mudancas
    ant = _foto(40.0, {"numero": 22, "nome": "A", "pct": 48.0}, "indefinido", {"PL": 11, "PT": 8},
                {"1": "X (PL)", "2": "Y (PT)"}, {"1": "X (PL)"})
    atual = _foto(80.0, {"numero": 40, "nome": "B", "pct": 50.2}, "vitória no 1º turno projetada",
                  {"PL": 12, "PT": 7, "PSOL": 1}, {"1": "X (PL)", "3": "Z (PSOL)"}, {"1": "X (PL)", "3": "Z (PSOL)"})
    textos = [(m["cargo"], m["tipo"], m["texto"]) for m in mudancas(ant, atual)]
    # mesmo avanço em dois cargos: uma linha só
    assert ("Governador, Deputado Estadual — RJ", "apuracao", "apuração: 40,00% → 80,00% das seções") in textos
    assert ("Governador — RJ", "lider", "novo líder: B (50,20%); antes A") in textos
    assert ("Governador — RJ", "leitura", "projeção: vitória no 1º turno projetada (antes: indefinido)") in textos
    assert ("Deputado Estadual — RJ", "cadeiras", "cadeiras: PL 11 → 12; PT 8 → 7; PSOL 0 → 1") in textos
    assert ("Deputado Estadual — RJ", "eleitos", "entraram entre os eleitos: Z (PSOL)") in textos
    assert ("Deputado Estadual — RJ", "eleitos", "saíram dos eleitos: Y (PT)") in textos
    assert ("Deputado Estadual — RJ", "consolidados", "1 novo(s) consolidado(s): Z (PSOL)") in textos
    assert mudancas(ant, ant) == []
    final = _foto(100.0, {"numero": 40, "nome": "B", "pct": 50.2}, None, {"PL": 12}, {"1": "X (PL)"}, final=True)
    assert ("Governador, Deputado Estadual — RJ", "apuracao", "totalização final") in [(m["cargo"], m["tipo"], m["texto"])
                                                                     for m in mudancas(atual, final)]


def test_boletim_seguinte_diz_o_que_mudou(apuracao) -> None:
    b, relogio = apuracao["boletineiro"], apuracao["relogio"]
    apuracao["fake"].avancar_uf(21272, "19:00:00", 40.0, 1.1)
    apuracao["coletor"].ciclo()
    html1 = b.verificar()[0]
    assert (b.destino / "boletim_2026-10-04_19h00.json").exists() and "O que mudou" not in html1.read_text()
    site = TestClient(apuracao["app"])
    assert site.get("/api/mudancas").json()["mudancas"] == []                 # nada mudou desde o boletim
    apuracao["fake"].avancar_uf(21272, "19:50:00", 80.0, 1.3)
    apuracao["coletor"].ciclo()
    agora = site.get("/api/mudancas").json()                                  # o painel já vê a mudança
    assert agora["anterior"]["titulo"] == "Boletim das 19h"
    assert any("40,00% → 80,00%" in m["texto"] for m in agora["mudancas"])
    relogio.t = datetime.fromisoformat("2026-10-04T20:00:10")
    html2, xlsx2 = b.verificar()
    texto = html2.read_text(encoding="utf-8")
    assert "O que mudou desde o boletim das 19h" in texto and "40,00% → 80,00%" in texto
    assert "Mudanças" in openpyxl.load_workbook(xlsx2).sheetnames
