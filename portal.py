"""Portal da apuração: uma página com os links dos sites que estão no ar nesta máquina.

    python portal.py                     # http://localhost:8100 — procura sites nas portas 8000–8099
    python portal.py --porta 8090 --faixa 8000-8050

A cada acesso, pergunta GET /api/status a cada porta da faixa (nesta máquina, em paralelo, 0,5 s de
limite) e lista só os sites da apuração que responderem (site_apuracao.py, ensaio_apuracao.py), com
ambiente, turno, % apurado e a última coleta. A página se atualiza sozinha a cada 30 s.
Os links usam o endereço pelo qual o portal foi aberto (de outro computador, se os sites estiverem na rede).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger("portal")
TIMEOUT_S = 0.5


def sondar(porta: int, host: str = "127.0.0.1", timeout: float = TIMEOUT_S) -> dict[str, Any] | None:
    """Resumo do site da apuração na porta, ou None (nada escutando, outro serviço, erro)."""
    try:
        r = requests.get(f"http://{host}:{porta}/api/status", timeout=timeout)
        st = r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(st, dict) or "coletor" not in st or "progresso" not in st:
        return None
    col = st.get("coletor") or {}
    thread = st.get("thread_coletor") or {}
    ano = col.get("ano")
    ambiente = col.get("ambiente") or "?"
    if thread.get("ensaio"):
        tipo = "ensaio"
    elif ano:
        tipo = "histórico"
    else:
        tipo = "oficial" if ambiente == "oficial" else "teste"
    if col.get("erro"):
        situacao = "erro"
    elif thread.get("ativo"):
        situacao = "coletando"
    elif ano:
        situacao = "resultado importado"
    else:
        situacao = "só leitura"
    return {
        "porta": porta, "titulo": f"Apuração {ano or 2026} — {st.get('uf', '?')}", "tipo": tipo,
        "ambiente": ambiente, "ano": ano, "turno": col.get("turno", 1), "dados": st.get("dados"),
        "situacao": situacao, "erro": col.get("erro"),
        "ultima_coleta": col.get("ultimo_ciclo_fim") or col.get("ultimo_ciclo_inicio"),
        "progresso": _progresso(st.get("progresso") or []),
    }


def _progresso(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uma linha por abrangência (a UF tem duas eleições, federal e estadual): o menor % e final só se todas."""
    por: dict[str, dict[str, Any]] = {}
    for p in linhas:
        nome = "Brasil" if p.get("ABRANGENCIA") == "br" else str(p.get("UF"))
        pct, final = p.get("PCT_SECOES_TOTALIZADAS"), bool(p.get("TOTALIZACAO_FINAL"))
        if nome not in por:
            por[nome] = {"abrangencia": nome, "pct": pct, "final": final}
        else:
            atual = por[nome]
            atual["pct"] = pct if atual["pct"] is None else (atual["pct"] if pct is None else min(atual["pct"], pct))
            atual["final"] = atual["final"] and final
    return list(por.values())


def servicos(portas: list[int], host: str = "127.0.0.1") -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=32) as ex:
        return [s for s in ex.map(lambda p: sondar(p, host), portas) if s]


def vigias(pasta: Path) -> dict[int, dict[str, Any]]:
    """Estado gravado pelo vigia de processo (vigiar_site.py), por porta."""
    saida: dict[int, dict[str, Any]] = {}
    for arq in pasta.glob("porta_*.json") if pasta.exists() else []:
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
            saida[int(d["porta"])] = d
        except (OSError, ValueError, KeyError):
            continue
    return saida


def create_app(portas: list[int], pasta_vigia: Path = Path("dados_2026/vigia")) -> FastAPI:
    app = FastAPI(title="Portal da apuração", docs_url=None, redoc_url=None)
    vistos: dict[int, dict[str, Any]] = {}  # sites já vistos no ar: se sumirem, aparecem "fora do ar"

    @app.get("/api/servicos")
    def api_servicos() -> list[dict[str, Any]]:
        no_ar = {s["porta"]: s for s in servicos(portas)}
        vg = vigias(pasta_vigia)
        agora = datetime.now().isoformat(timespec="seconds")
        for porta, s in no_ar.items():
            vistos[porta] = {**s, "visto_em": agora}
        saida = []
        for porta in sorted(set(no_ar) | set(vistos) | {p for p, d in vg.items() if d.get("estado") != "encerrado"}):
            if porta in no_ar:
                s = dict(no_ar[porta])
            else:  # sumiu (ou o vigia diz que está caído): fica na lista, marcado
                antes = vistos.get(porta, {})
                s = {"porta": porta, "titulo": antes.get("titulo", f"Porta {porta}"), "tipo": antes.get("tipo", "?"),
                     "ambiente": antes.get("ambiente"), "turno": antes.get("turno", 1), "dados": antes.get("dados"),
                     "situacao": "fora do ar", "erro": None, "ultima_coleta": antes.get("ultima_coleta"),
                     "progresso": [], "ano": antes.get("ano"), "fora_do_ar_desde": antes.get("visto_em")}
            if porta in vg:
                d = vg[porta]
                ult = (d.get("eventos") or [{}])[-1]
                s["vigia"] = {"estado": d.get("estado"), "reinicios": d.get("reinicios", 0),
                              "ultimo_evento": ult.get("detalhe"), "hora": ult.get("hora")}
            saida.append(s)
        return saida

    @app.get("/", response_class=HTMLResponse)
    def pagina(request: Request) -> str:
        return PAGINA

    return app


PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portal da apuração</title>
<style>
:root{--fundo:#f9f9f7;--sup:#fcfcfb;--tinta:#0b0b0b;--tinta2:#52514e;--borda:rgba(11,11,11,.12);--link:#1c5cab;
--oficial:#006300;--erro:#d03b3b;--ok:#0ca30c;--aviso:#fab219}
@media (prefers-color-scheme:dark){:root{--fundo:#0d0d0d;--sup:#1a1a19;--tinta:#fff;--tinta2:#c3c2b7;
--borda:rgba(255,255,255,.12);--link:#86b6ef;--oficial:#0ca30c}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--tinta);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}h1{font-size:1.4rem;margin:.2rem 0}
.nota{color:var(--tinta2);font-size:.85rem}
.grade{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:14px;margin-top:14px}
a.cartao{display:block;background:var(--sup);border:1px solid var(--borda);border-radius:10px;padding:14px 16px;
color:inherit;text-decoration:none}
a.cartao:hover,a.cartao:focus{border-color:var(--link);outline:none}
.cartao h2{font-size:1.1rem;margin:0 0 4px;color:var(--link)}
.selo{display:inline-block;font-size:.75rem;padding:1px 8px;border-radius:999px;border:1px solid var(--tinta2);
color:var(--tinta2);margin-right:6px}
.selo.oficial{border-color:var(--oficial);color:var(--oficial);font-weight:700}
.sit::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:var(--tinta2)}
.sit.coletando::before{background:var(--ok)}.sit.erro::before{background:var(--erro)}
.linha{margin-top:6px;font-size:.9rem}.erro{color:var(--erro);font-size:.85rem;margin-top:6px}
.vazio{background:var(--sup);border:1px dashed var(--borda);border-radius:10px;padding:18px;margin-top:14px}
</style></head>
<body><main>
<h1>Portal da apuração</h1>
<p class="nota">Sites da apuração no ar nesta máquina. Atualiza sozinho a cada 30 s. <span id="hora"></span></p>
<div id="lista" class="grade" aria-live="polite"></div>
</main>
<script>
"use strict";
function el(tag, cls, texto) { const n = document.createElement(tag); if (cls) n.className = cls;
  if (texto !== undefined) n.textContent = texto; return n; }
const pct = (v) => v === null || v === undefined ? "—" : v.toFixed(2).replace(".", ",") + "%";
const hora = (iso) => iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";
async function atualizar() {
  const lista = document.getElementById("lista");
  let servicos;
  try { servicos = await (await fetch("api/servicos", { cache: "no-store" })).json(); }
  catch (e) { lista.replaceChildren(el("div", "vazio", "Portal sem resposta: " + e.message)); return; }
  document.getElementById("hora").textContent = "Verificado às " + new Date().toLocaleTimeString("pt-BR") + ".";
  if (!servicos.length) {
    lista.replaceChildren(el("div", "vazio", "Nenhum site da apuração no ar. Suba um com: python site_apuracao.py --ambiente oficial --coletar"));
    return;
  }
  lista.replaceChildren(...servicos.map((s) => {
    const a = el("a", "cartao");
    a.href = location.protocol + "//" + location.hostname + ":" + s.porta + "/";
    a.append(el("h2", null, s.titulo));
    const selos = el("div");
    const selo = el("span", "selo" + (s.tipo === "oficial" ? " oficial" : ""),
      s.tipo === "oficial" ? "OFICIAL" : s.tipo === "teste" ? "teste: " + s.ambiente : s.tipo);
    selos.append(selo, el("span", "selo", s.turno + "º turno"), el("span", "selo", "porta " + s.porta));
    a.append(selos, el("div", "linha sit " + (s.situacao === "fora do ar" ? "erro" : s.situacao.split(" ")[0]),
      s.situacao + (s.fora_do_ar_desde ? " (visto no ar às " + hora(s.fora_do_ar_desde) + ")" : "")));
    for (const p of s.progresso) {
      a.append(el("div", "linha", p.abrangencia + ": " + pct(p.pct) + " das seções" + (p.final ? " — final" : "")));
    }
    a.append(el("div", "linha nota", (s.ano ? "Importado em " : "Última coleta: ") + hora(s.ultima_coleta)));
    if (s.dados) a.append(el("div", "nota", s.dados));
    if (s.erro) a.append(el("div", "erro", "⚠ " + s.erro));
    if (s.vigia) a.append(el("div", s.vigia.reinicios ? "erro" : "nota",
      "Vigia: " + (s.vigia.reinicios ? "reiniciado " + s.vigia.reinicios + " vez(es); último: " + s.vigia.ultimo_evento
        + " (" + hora(s.vigia.hora) + ")" : "sem reinícios")));
    return a;
  }));
}
atualizar();
setInterval(atualizar, 30000);
</script>
</body></html>
"""


def _faixa(texto: str) -> list[int]:
    try:
        ini, fim = (int(x) for x in texto.split("-"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"use INICIO-FIM (ex.: 8000-8099), não {texto!r}") from None
    if not (1 <= ini <= fim <= 65535) or fim - ini > 1000:
        raise argparse.ArgumentTypeError("faixa inválida (no máximo 1.000 portas)")
    return list(range(ini, fim + 1))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Portal com os links dos sites da apuração no ar.")
    p.add_argument("--porta", type=int, default=8100, help="padrão 8100: fora da faixa procurada (a 8080 costuma estar ocupada)")
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 para abrir de outra máquina da rede")
    p.add_argument("--vigia", default="dados_2026/vigia", help="pasta do estado do vigia de processo")
    p.add_argument("--faixa", type=_faixa, default=_faixa("8000-8099"), help="portas procuradas (padrão 8000-8099)")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    portas = [p for p in a.faixa if p != a.porta]
    print(f"\nPortal da apuração: http://localhost:{a.porta}/  (procura sites nas portas {portas[0]}–{portas[-1]}; "
          "Ctrl+C encerra)\n", flush=True)
    uvicorn.run(create_app(portas, Path(a.vigia)), host=a.host, port=a.porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
