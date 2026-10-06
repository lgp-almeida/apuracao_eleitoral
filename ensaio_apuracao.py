"""Ensaio geral da noite da eleição: a apuração real de 2022 (RJ) tocada de novo, acelerada.

Sobe, num só processo, o "servidor do TSE" do ensaio (JSON gerado da apuração de 2022 seção a seção),
o COLETOR de verdade (com o limite de 20 req/s), o SITE de verdade e usuários simultâneos consultando
as rotas do site. No fim, confere o resultado com o oficial e grava um relatório.

    python ensaio_apuracao.py                          # 7 h de apuração em ~14 min (velocidade 30)
    python ensaio_apuracao.py --velocidade 120 --carga 8
    python ensaio_apuracao.py --inicio 19:30 --manter  # começa às 19h30 de 2022 e deixa o site no ar ao fim
    python ensaio_apuracao.py --uf ES --turno 2        # 2º turno de 2022 (Governador e Presidente) de outra UF

Abra http://localhost:8040 durante o ensaio. Os dados ficam em dados_2026/ensaio_2022/ (apagados
a cada novo ensaio, a menos que use --continuar).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
import statistics
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import requests
import uvicorn

from apuracao import ensaio as en
from apuracao.boletim import Boletineiro
from apuracao.copia import Copiador
from apuracao.divulgacao.cliente import ClienteDivulgacao
from apuracao.divulgacao.coletor import Coletor
from apuracao.ufs import dir_uf
from apuracao.web.app import create_app

logger = logging.getLogger("ensaio")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ensaio geral: apuração de 2022 (RJ, ou outra UF/turno) acelerada, com coletor, site e carga.")
    p.add_argument("--velocidade", type=float, default=30.0, help="quantas vezes mais rápido que a noite real")
    p.add_argument("--inicio", help="hora de 2022 em que o ensaio começa (HH:MM; padrão: 5 min antes da 1ª seção)")
    p.add_argument("--intervalo", type=float, default=15.0, help="segundos (reais) entre ciclos do coletor")
    p.add_argument("--max-rps", type=float, default=20.0, help="limite de requisições do coletor (o mesmo da noite)")
    p.add_argument("--atraso-ea20", type=float, default=3.0,
                   help="minutos (de 2022) entre o anúncio da totalização (EA15) e o resultado (EA20), como o TSE "
                        "em 04/10/2026 (padrão 3; 0 = juntos)")
    p.add_argument("--carga", type=int, default=4, help="usuários simultâneos consultando o site")
    p.add_argument("--boletim-min", type=int, default=60, help="minutos (da hora de 2022) entre boletins")
    p.add_argument("--interesse", nargs="+", default=["7:13713"], metavar="CARGO:NUMERO",
                   help="deputados acompanhados pelos alertas (padrão: 7:13713)")
    p.add_argument("--porta", type=int, default=8040)
    p.add_argument("--uf", default="RJ", type=str.upper, help="UF reconstituída (precisa do votacao_secao_2022_<UF>)")
    p.add_argument("--turno", type=int, choices=[1, 2], default=1,
                   help="2: o 2º turno de 2022 (Governador, se a UF teve, e Presidente) pelo caminho de 2º turno do coletor")
    p.add_argument("--dados", help="padrão: dados_2026/ensaio_2022 (RJ, 1º turno) ou dados_2026/ensaio_2022_<UF>_t<turno>")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--continuar", action="store_true", help="não apagar os dados de um ensaio anterior")
    p.add_argument("--manter", action="store_true", help="deixar o site no ar ao fim (Ctrl+C encerra)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


# --------------------------------------------------------------------------
# Usuários simultâneos
# --------------------------------------------------------------------------
class Carga:
    """Usuários que consultam rotas do site em sequência aleatória e anotam status e latência."""

    ROTAS = ["api/status", "api/painel", "api/projecao?cargo=3", "api/projecao?cargo=5", "api/cadeiras?cargo=7",
             "api/cadeiras?cargo=6", "api/candidato?cargo=7&numero={dep}", "api/candidato/serie?cargo=3&numero=22",
             "api/mapa?cargo=3&metrica=vencedor", "api/mapa?cargo=7&metrica=pct_candidato&numero={dep}",
             "api/mapa/momentos?cargo=3", "api/candidatos?cargo=7"]

    def __init__(self, base: str, usuarios: int, semente: int = 4) -> None:
        self.base, self.usuarios = base, usuarios
        self.parar = threading.Event()
        self.medidas: list[tuple[str, int, float]] = []
        self._trava = threading.Lock()
        self._rng = random.Random(semente)
        self.deputados = [22022, 50007, 44123, 15016, 22222]

    def _usuario(self) -> None:
        sessao = requests.Session()
        while not self.parar.is_set():
            rota = self._rng.choice(self.ROTAS)
            url = self.base + rota.format(dep=self._rng.choice(self.deputados))
            t0 = time.perf_counter()
            try:
                st = sessao.get(url, timeout=60).status_code
            except requests.RequestException:
                st = -1
            with self._trava:
                self.medidas.append((rota.split("?")[0] + ("?" + rota.split("?")[1].split("&")[0] if "?" in rota else ""),
                                     st, time.perf_counter() - t0))
            self.parar.wait(self._rng.uniform(0.2, 1.0))

    def iniciar(self) -> None:
        for i in range(self.usuarios):
            threading.Thread(target=self._usuario, name=f"usuario-{i}", daemon=True).start()

    def resumo(self) -> list[dict[str, Any]]:
        por_rota: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for rota, st, dt in self.medidas:
            por_rota[rota].append((st, dt))
        linhas = []
        for rota, xs in sorted(por_rota.items()):
            lat = sorted(dt for _, dt in xs)
            linhas.append({"rota": rota, "pedidos": len(xs), "erros_5xx_ou_rede": sum(1 for s, _ in xs if s >= 500 or s < 0),
                           "404": sum(1 for s, _ in xs if s == 404), "outros_4xx": sum(1 for s, _ in xs if 400 <= s < 500 and s != 404),
                           "p50_ms": round(1000 * statistics.median(lat)), "p95_ms": round(1000 * lat[int(0.95 * (len(lat) - 1))]),
                           "max_ms": round(1000 * lat[-1])})
        return linhas


# --------------------------------------------------------------------------
# Conferência final com o resultado oficial
# --------------------------------------------------------------------------
def conferir(base: str, rec: en.Reconstituicao) -> list[dict[str, Any]]:
    """O que o site mostra ao fim do ensaio × resultado oficial de 2022 da UF e do turno (o importado em
    dados_2026/historico_2022_t<turno>[_<UF>]): válidos, apuração final, cadeiras (1º turno) e eleitos."""
    pasta = dir_uf(Path(f"dados_2026/historico_2022_t{rec.turno}"), rec.uf) / "ultimo"
    oficial = pasta / "totais.parquet"
    checks: list[dict[str, Any]] = []
    painel = requests.get(base + "api/painel", timeout=120).json()
    ref = pl.read_parquet(oficial).filter(pl.col("ABRANGENCIA") == "uf") if oficial.exists() else None
    cand_of = (pl.read_parquet(pasta / "candidatos.parquet").filter(pl.col("ABRANGENCIA") == "uf")
               if (pasta / "candidatos.parquet").exists() else None)
    for c in painel["cartoes"]:
        if c["abrangencia"] == "BRASIL":
            continue
        t = c["totais"]
        if ref is not None:
            o = ref.filter(pl.col("CARGO") == c["cargo"])
            if not o.is_empty():
                ov = o["VALIDOS"][0]
                dif = abs((t["VALIDOS"] or 0) - ov) / ov
                checks.append({"verificacao": f"válidos de {c['ds_cargo']} (site × oficial)", "site": t["VALIDOS"],
                               "oficial": int(ov), "ok": dif < 0.001, "detalhe": f"diferença {100 * dif:.3f}%"})
        checks.append({"verificacao": f"{c['ds_cargo']}: apuração 100% e final", "site": t["PCT_SECOES_TOTALIZADAS"],
                       "oficial": 100, "ok": t["PCT_SECOES_TOTALIZADAS"] == 100 and bool(t["TOTALIZACAO_FINAL"]), "detalhe": ""})
    for cargo in (6, 7) if rec.turno == 1 else ():
        if cargo not in rec.cargos or cand_of is None:
            continue
        vagas = cand_of.filter((pl.col("CARGO") == cargo) & pl.col("SITUACAO").str.starts_with("Eleito")).height
        r = requests.get(base + f"api/cadeiras?cargo={cargo}", timeout=120).json()
        conf = r.get("conferencia_tse", {})
        checks.append({"verificacao": f"cadeiras {cargo} (projeção do site × eleitos oficiais)",
                       "site": conf.get("coincidentes"), "oficial": vagas,
                       "ok": conf.get("coincidentes") == vagas, "detalhe": f"divergências {conf.get('divergencias')}"})
    for c in painel["cartoes"]:  # majoritários: quem o site dá como eleito (ou no 2º turno) × o oficial
        if c["abrangencia"] == "BRASIL" or c["cargo"] not in (1, 3, 5) or cand_of is None:
            continue
        site = sorted(x["NOME_URNA"] for x in c["candidatos"] if x.get("ELEITO"))
        of = sorted(cand_of.filter((pl.col("CARGO") == c["cargo"]) & pl.col("ELEITO"))["NOME_URNA"].to_list())
        if c["cargo"] == 1:  # presidente: a situação é a nacional e o painel da UF mostra a dela (só confere a regra)
            continue
        checks.append({"verificacao": f"{c['ds_cargo']}: eleitos no {rec.turno}º turno", "site": ", ".join(site),
                       "oficial": ", ".join(of), "ok": site == of, "detalhe": ""})
    return checks


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for ruidoso in ("apuracao.divulgacao", "apuracao.web", "votos_local"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    destino = Path(a.dados) if a.dados else Path(
        "dados_2026/ensaio_2022" if (a.uf, a.turno) == ("RJ", 1) else f"dados_2026/ensaio_2022_{a.uf}_t{a.turno}")
    copias = Path(f"{destino}_copias")  # cópia de segurança do ensaio (na noite: --copia-dir, outro disco)
    if destino.exists() and not a.continuar:
        shutil.rmtree(destino)
        shutil.rmtree(copias, ignore_errors=True)
    t0 = time.time()
    rec = en.carregar_2022(Path(a.cache_dir), a.uf, turno=a.turno)
    inicio = rec.inicio
    if a.inicio:
        h, mnt = map(int, a.inicio.split(":"))
        inicio = rec.inicio.replace(hour=h, minute=mnt)
    # o relógio passa do fim de 2022 pelo atraso do EA20: a última totalização anunciada só é publicada
    # depois (sem isso o ensaio acabava com o último EA20 na versão anterior)
    fim = rec.fim + timedelta(minutes=a.atraso_ea20)
    relogio = en.Relogio(inicio, fim, a.velocidade)
    duracao = (fim - inicio).total_seconds() / a.velocidade
    logger.info("reconstituição de 2022 carregada em %.1f s: %s → %s em ~%.1f min reais", time.time() - t0,
                f"{inicio:%H:%M}", f"{fim:%H:%M}", duracao / 60)

    muns = dir_uf(Path("dados_2026/historico_2022_t1"), a.uf) / "ultimo" / "municipios.parquet"  # os da UF, com nome
    sessao = en.SessaoEnsaio(en.Gerador(rec, relogio, a.atraso_ea20), pl.read_parquet(muns) if muns.exists() else None)
    cliente = ClienteDivulgacao("simulado", sessao=sessao, max_rps=a.max_rps)
    cliente.ambiente = "ensaio 2022"  # só o rótulo (status.json e selo do site); os caminhos são os do simulado
    coletor = Coletor(cliente, destino, a.uf, a.turno)
    status: dict[str, Any] = {"ativo": True, "intervalo_s": a.intervalo, "ensaio": True}
    interesse = tuple(tuple(int(x) for x in i.split(":")) for i in a.interesse)
    app = create_app(destino, a.uf, Path(a.cache_dir), status, None,
                     interesse=interesse if (a.uf, a.turno) == ("RJ", 1) else ())
    vigia = app.state.vigia
    vigia.agora = relogio.agora  # "sem avanço" e a hora dos alertas no relógio de 2022 (coleta parada: relógio real)
    # boletins no relógio do ensaio (hora de 2022): um por hora cheia e o final
    boletineiro = Boletineiro(app.state.consultas, destino / "boletins", a.boletim_min, agora=relogio.agora)
    boletins: list[dict[str, Any]] = []
    alertas: list[dict[str, Any]] = []
    copiador = Copiador(destino, copias, a.uf, a.boletim_min, agora=relogio.agora)
    copiadas: list[dict[str, Any]] = []
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=a.porta, log_level="warning"))
    threading.Thread(target=servidor.run, name="site", daemon=True).start()
    base = f"http://127.0.0.1:{a.porta}/"
    print(f"\nENSAIO GERAL — abra {base}  (2022 às {relogio.agora():%H:%M}, velocidade {a.velocidade:g}×)\n", flush=True)

    ciclos: list[dict[str, Any]] = []
    projecoes: list[dict[str, Any]] = []
    carga = Carga(base, a.carga)
    carga_iniciada = False
    try:
        while True:
            hora = relogio.agora()
            c0 = time.time()
            try:
                r = coletor.ciclo()
                ciclos.append({"hora_2022": f"{hora:%H:%M}", "duracao_s": round(time.time() - c0, 1),
                               "pedidos": r.arquivos_pedidos, "novos": r.arquivos_novos, "304": r.arquivos_304,
                               "404": r.arquivos_404, "antigos": r.arquivos_antigos, "erro": None})
            except Exception as exc:  # o ensaio existe para achar isto: anota e segue
                logger.exception("ciclo do coletor falhou")
                ciclos.append({"hora_2022": f"{hora:%H:%M}", "duracao_s": round(time.time() - c0, 1), "erro": repr(exc)})
            ult = ciclos[-1]
            logger.info("2022 %s · ciclo %.1fs · %s arquivos novos%s", ult["hora_2022"], ult["duracao_s"],
                        ult.get("novos"), f" · ERRO {ult['erro']}" if ult["erro"] else "")
            try:
                for al_ in vigia.verificar():
                    alertas.append({"hora_2022": al_["momento"][11:16], "nivel": al_["nivel"], "titulo": al_["titulo"],
                                    "detalhe": al_["detalhe"]})
            except Exception as exc:  # anotado: o ensaio existe para achar isto
                logger.exception("verificação de alertas falhou")
                alertas.append({"hora_2022": ult["hora_2022"], "nivel": "ERRO", "titulo": repr(exc), "detalhe": ""})
            try:
                if r_copia := copiador.verificar():
                    copiadas.append({"hora_2022": ult["hora_2022"], "nome": r_copia["nome"],
                                     "raw_novos": r_copia["raw_novos"], "segundos": r_copia["segundos"]})
            except Exception as exc:
                logger.exception("cópia de segurança falhou")
                copiadas.append({"hora_2022": ult["hora_2022"], "nome": "ERRO", "raw_novos": 0, "segundos": repr(exc)})
            b0 = time.time()
            try:
                feitos = boletineiro.verificar()
                if feitos:
                    boletins.append({"hora_2022": ult["hora_2022"], "arquivo": feitos[0].name,
                                     "duracao_s": round(time.time() - b0, 1), "erro": None})
            except Exception as exc:  # anotado como o ciclo: o ensaio existe para achar isto
                logger.exception("boletim falhou")
                boletins.append({"hora_2022": ult["hora_2022"], "arquivo": None,
                                 "duracao_s": round(time.time() - b0, 1), "erro": repr(exc)})
            if not carga_iniciada:
                carga.iniciar()
                carga_iniciada = True
            try:
                p = requests.get(base + f"api/projecao?cargo={3 if 3 in rec.cargos else 1}", timeout=60)
                if p.ok:
                    d = p.json()
                    k = d["candidatos"][0]
                    arred = lambda x: None if x is None else round(x, 2)  # noqa: E731 (sem votos ainda: nulo)
                    projecoes.append({"hora_2022": ult["hora_2022"], "pct_apurado": arred(d["pct_apurado"]),
                                      "lider": k["NOME_URNA"], "parcial": arred(k["PCT_ATUAL"]),
                                      "projecao": arred(k["PCT_PROJ"]), "margem": d["margem_pp"], "situacao": d["situacao"]})
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                logger.warning("leitura da projeção falhou: %s", exc)
            if relogio.terminou and ult.get("erro") is None and ciclos[-1]["hora_2022"] == f"{fim:%H:%M}":
                break
            time.sleep(max(0.0, a.intervalo - (time.time() - c0)))
        time.sleep(3)
        try:  # a totalização final pode ter chegado no último ciclo
            if r_copia := copiador.verificar():
                copiadas.append({"hora_2022": ult["hora_2022"], "nome": r_copia["nome"],
                                 "raw_novos": r_copia["raw_novos"], "segundos": r_copia["segundos"]})
        except Exception as exc:
            logger.exception("cópia final falhou")
        try:
            if feitos := boletineiro.verificar():
                boletins.append({"hora_2022": ult["hora_2022"], "arquivo": feitos[0].name, "duracao_s": None,
                                 "erro": None})
        except Exception as exc:
            logger.exception("boletim final falhou")
            boletins.append({"hora_2022": ult["hora_2022"], "arquivo": None, "duracao_s": None, "erro": repr(exc)})
    except KeyboardInterrupt:
        print("\nensaio interrompido")
    carga.parar.set()
    checks = conferir(base, rec) if relogio.terminou else []
    rotas = carga.resumo()
    if relogio.terminou:
        graves = [x for x in alertas if x["nivel"] in ("critico", "ERRO")]
        checks.append({"verificacao": "nenhum alerta crítico (coleta normal)", "site": len(graves), "oficial": 0,
                       "ok": not graves, "detalhe": "; ".join(x["titulo"] for x in graves)[:120]})
        if 3 in rec.cargos:  # houve governador eleito neste turno (no RJ de 2022, no 1º)
            gov = [x for x in alertas if x["titulo"].startswith("Governador: vitória")]
            checks.append({"verificacao": "alerta de leitura do Governador (vitória)", "site": len(gov),
                           "oficial": ">= 1", "ok": bool(gov), "detalhe": gov[0]["hora_2022"] if gov else ""})
        n_raw = len(list((destino / "raw").rglob("*.json.gz")))
        n_copia = len(list((copias / "raw").rglob("*.json.gz")))
        tem_copia = (copias / "instantaneos" / "final").exists() and n_copia == n_raw
        checks.append({"verificacao": "cópia final com todas as parciais do TSE", "site": n_copia, "oficial": n_raw,
                       "ok": tem_copia, "detalhe": f"{len(copiadas)} cópias"})
        final_html = destino / "boletins" / "boletim_final.html"
        diz = final_html.exists() and "O que mudou desde" in final_html.read_text(encoding="utf-8")
        checks.append({"verificacao": "boletim final diz o que mudou", "site": diz, "oficial": True, "ok": diz,
                       "detalhe": ""})
        tem_final = (destino / "boletins" / "boletim_final.html").exists()
        checks.append({"verificacao": "boletim final gravado", "site": tem_final, "oficial": True, "ok": tem_final,
                       "detalhe": f"{len(boletins)} boletins"})
    relatorio = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "velocidade": a.velocidade,
                 "max_rps": a.max_rps, "usuarios": a.carga, "duracao_real_min": round((time.time() - t0) / 60, 1),
                 "ciclos": ciclos, "projecao_governador": projecoes, "boletins": boletins, "alertas": alertas, "copias": copiadas, "rotas": rotas, "conferencia": checks,
                 "pedidos_ao_tse_falso": len(sessao.pedidos)}
    (destino / "relatorio_ensaio.json").write_text(json.dumps(relatorio, indent=2, ensure_ascii=False))
    _imprimir(relatorio)
    ok = all(c["ok"] for c in checks) and not any(c["erro"] for c in ciclos) \
        and not any(r["erros_5xx_ou_rede"] for r in rotas) and not any(b["erro"] for b in boletins)
    print(f"\nRESULTADO DO ENSAIO: {'OK' if ok else 'PROBLEMAS — ver acima'}  (relatório em {destino / 'relatorio_ensaio.json'})")
    if a.manter:
        print(f"site no ar em {base} (Ctrl+C encerra)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    servidor.should_exit = True
    return 0 if ok else 1


def _imprimir(r: dict[str, Any]) -> None:
    with pl.Config(tbl_rows=60, tbl_cols=12, tbl_width_chars=160, fmt_str_lengths=60):
        print("\nCICLOS DO COLETOR"); print(pl.DataFrame(r["ciclos"]))
        if r["projecao_governador"]:
            print("\nPROJEÇÃO DO GOVERNADOR AO LONGO DO ENSAIO"); print(pl.DataFrame(r["projecao_governador"]))
        if r["alertas"]:
            print("\nALERTAS"); print(pl.DataFrame(r["alertas"]).drop("detalhe"))
        if r.get("copias"):
            print("\nCÓPIAS DE SEGURANÇA"); print(pl.DataFrame(r["copias"]))
        if r["boletins"]:
            print("\nBOLETINS"); print(pl.DataFrame(r["boletins"]))
        if r["rotas"]:
            print("\nCONSULTAS AO SITE (usuários simultâneos)"); print(pl.DataFrame(r["rotas"]))
        if r["conferencia"]:
            print("\nCONFERÊNCIA COM O RESULTADO OFICIAL DE 2022"); print(pl.DataFrame(r["conferencia"]))


if __name__ == "__main__":
    sys.exit(main())
