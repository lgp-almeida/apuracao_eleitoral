"""Site com várias UFs (rodada 39): o app de cada UF (`create_app`) montado em `/<uf>/`.

A página usa só caminhos relativos (`api/...`, `geo/...`), então, aberta em `/sp/`, fala com `/sp/api/...`
sem saber que há outras UFs. A raiz acrescenta:
  GET /           → a UF padrão
  GET /<uf>       → /<uf>/
  GET /ufs.json   UFs com dados (nome, ambiente, % das seções totalizadas na UF), para o seletor do cabeçalho
UFs sem dados (`ufs.tem_dados`) não são montadas e aparecem em `ufs.json` como indisponíveis. A UF que GANHA
dados depois (o coletor do 2º turno começa com as pastas vazias) é montada na próxima consulta a `/ufs.json`,
`/`, `/<uf>` ou em `raiz.state.atualizar()`, sem reiniciar o site (rodada 43).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from apuracao import ufs as uf_mod


@dataclass
class EntradaUF:
    uf: str
    dados: Path
    referencia: Path | None = None


def create_multi_app(entradas: list[EntradaUF], uf_padrao: str, fabrica: Callable[[EntradaUF], FastAPI],
                     ao_montar: Callable[[EntradaUF, FastAPI], None] | None = None,
                     permitir_vazio: bool = False) -> FastAPI:
    """`fabrica(entrada)` cria o app de uma UF (em `site_apuracao.py`, `create_app` com as opções do site);
    `ao_montar(entrada, app)` é chamado a cada UF montada (serviços por UF: boletim, cópia, alertas).
    `permitir_vazio`: o site sobe mesmo sem nenhuma UF com dados (noite com --coletar: a 1ª coleta cria as pastas)."""
    raiz = FastAPI(title="Apuração 2026 — UFs", docs_url=None, redoc_url=None)
    montadas: dict[str, EntradaUF] = {}
    apps: dict[str, FastAPI] = {}
    trava = threading.Lock()
    pedida = uf_padrao.upper()

    def atualizar() -> list[str]:
        """Monta as UFs que passaram a ter dados; devolve as recém-montadas."""
        novas = []
        with trava:
            for e in entradas:
                if e.uf not in montadas and uf_mod.tem_dados(e.dados):
                    app = fabrica(e)
                    raiz.mount(f"/{e.uf.lower()}", app, name=f"uf_{e.uf.lower()}")
                    montadas[e.uf], apps[e.uf] = e, app
                    novas.append(e.uf)
        for uf in novas:
            if ao_montar is not None:
                ao_montar(montadas[uf], apps[uf])
        return novas

    def padrao() -> str | None:
        return pedida if pedida in montadas else next(iter(montadas), None)

    atualizar()
    if not montadas and not permitir_vazio:
        raise ValueError("nenhuma das UFs pedidas tem dados (rode baixar_ufs.py --etapas divulgacao)")

    @raiz.get("/ufs.json")
    def lista_ufs() -> JSONResponse:
        atualizar()
        saida = [_resumo(e.uf, e.dados if e.uf in montadas else None) for e in entradas]
        return JSONResponse({"padrao": padrao(), "ufs": saida}, headers={"Cache-Control": "no-cache"})

    @raiz.get("/", response_model=None)
    def inicio() -> RedirectResponse | HTMLResponse:
        atualizar()
        p_ = padrao()
        if p_ is None:
            return HTMLResponse(AGUARDANDO, headers={"Cache-Control": "no-cache"})
        return RedirectResponse(f"/{p_.lower()}/")

    @raiz.get("/{uf}", response_model=None)
    def sem_barra(uf: str) -> RedirectResponse | HTMLResponse:
        atualizar()
        if uf.upper() in montadas:
            return RedirectResponse(f"/{uf.lower()}/")
        return inicio()

    raiz.state.montadas, raiz.state.apps, raiz.state.atualizar = montadas, apps, atualizar
    return raiz


# página enquanto nenhuma UF tem dados (o coletor ainda não terminou o 1º ciclo): recarrega sozinha
AGUARDANDO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15"><title>Apuração 2026</title></head>
<body style="font-family: system-ui, sans-serif; padding: 2rem">
<h1>Apuração 2026</h1><p>Aguardando os primeiros dados do TSE. A página recarrega a cada 15 segundos.</p>
</body></html>"""


def _resumo(uf: str, dados: Path | None) -> dict[str, Any]:
    base = {"uf": uf, "nome": uf_mod.UFS.get(uf, uf), "url": f"{uf.lower()}/", "disponivel": dados is not None}
    if dados is None:
        return base
    try:
        t = pl.read_parquet(dados / "ultimo" / "totais.parquet", columns=["ABRANGENCIA", "PCT_SECOES_TOTALIZADAS"])
        pct = t.filter(pl.col("ABRANGENCIA") == "uf")["PCT_SECOES_TOTALIZADAS"].max()
    except (OSError, pl.exceptions.PolarsError):
        pct = None
    return {**base, "pct_secoes": pct}
