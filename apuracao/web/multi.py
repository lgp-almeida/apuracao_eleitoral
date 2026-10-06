"""Site com várias UFs (rodada 39): o app de cada UF (`create_app`) montado em `/<uf>/`.

A página usa só caminhos relativos (`api/...`, `geo/...`), então, aberta em `/sp/`, fala com `/sp/api/...`
sem saber que há outras UFs. A raiz acrescenta:
  GET /           → a UF padrão
  GET /<uf>       → /<uf>/
  GET /ufs.json   UFs com dados (nome, ambiente, % das seções totalizadas na UF), para o seletor do cabeçalho
UFs sem dados (`ufs.tem_dados`) não são montadas e aparecem em `ufs.json` como indisponíveis.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse

from apuracao import ufs as uf_mod


@dataclass
class EntradaUF:
    uf: str
    dados: Path
    referencia: Path | None = None


def create_multi_app(entradas: list[EntradaUF], uf_padrao: str, fabrica: Callable[[EntradaUF], FastAPI]) -> FastAPI:
    """`fabrica(entrada)` cria o app de uma UF (em `site_apuracao.py`, `create_app` com as opções do site)."""
    raiz = FastAPI(title="Apuração 2026 — UFs", docs_url=None, redoc_url=None)
    montadas = {e.uf: e for e in entradas if uf_mod.tem_dados(e.dados)}
    if not montadas:
        raise ValueError("nenhuma das UFs pedidas tem dados (rode baixar_ufs.py --etapas divulgacao)")
    padrao = uf_padrao.upper() if uf_padrao.upper() in montadas else next(iter(montadas))

    @raiz.get("/ufs.json")
    def lista_ufs() -> JSONResponse:
        saida = [_resumo(e.uf, e.dados if e.uf in montadas else None) for e in entradas]
        return JSONResponse({"padrao": padrao, "ufs": saida}, headers={"Cache-Control": "no-cache"})

    @raiz.get("/")
    def inicio() -> RedirectResponse:
        return RedirectResponse(f"/{padrao.lower()}/")

    @raiz.get("/{uf}")
    def sem_barra(uf: str) -> RedirectResponse:
        if uf.upper() not in montadas:
            return RedirectResponse(f"/{padrao.lower()}/")
        return RedirectResponse(f"/{uf.lower()}/")

    for uf, e in montadas.items():
        raiz.mount(f"/{uf.lower()}", fabrica(e), name=f"uf_{uf.lower()}")
    raiz.state.montadas = montadas
    return raiz


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
