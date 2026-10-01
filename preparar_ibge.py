"""Dados do IBGE (malhas e Censo 2022): baixar antes de precisar e manter atualizados (rodada 34).

    python preparar_ibge.py                  # verifica (índices + HEADs), baixa o que falta/mudou e gera os derivados
    python preparar_ibge.py --so-verificar   # só o relatório, sem baixar
    python preparar_ibge.py --vigiar         # repete a cada 24 h
    python preparar_ibge.py --forcar-api     # confere também a malha municipal (API sem HEAD: GET + SHA-512)

Derivados: malhas/bairros_<UF>.geojson, ibge_censo2022/censo_bairros_<UF>.parquet e
ibge_censo2022/censo_setores_<UF>.parquet. Estado da última verificação: <cache>/ibge_estado.json.
Um site no ar guarda as malhas e o Censo na memória: reinicie-o para usar uma versão nova.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import polars as pl
import requests

from apuracao import ibge

logger = logging.getLogger("preparar_ibge")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dados do IBGE: baixar, verificar versões novas e atualizar o cache.")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    p.add_argument("--so-verificar", action="store_true", help="só verificar (nada é baixado)")
    p.add_argument("--forcar-api", action="store_true", help="conferir a malha municipal da API agora")
    p.add_argument("--vigiar", action="store_true", help="repetir a verificação/atualização")
    p.add_argument("--intervalo", type=float, default=86400, help="segundos entre verificações (mínimo 3600)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def imprimir(estados: list[ibge.Estado]) -> None:
    with pl.Config(tbl_rows=20, tbl_width_chars=170, fmt_str_lengths=60):
        print(pl.DataFrame([{"fonte": e.chave, "arquivo": e.local or e.arquivo, "IBGE": e.http,
                             "modificado no IBGE": e.remoto_modificado, "situação": e.situacao, "ação": e.acao}
                            for e in estados]))


def rodada(a: argparse.Namespace, sessao) -> int:
    if a.so_verificar:
        estados = ibge.verificar(a.cache_dir, a.uf, sessao, a.forcar_api)
        ibge.gravar_estado(a.cache_dir, estados)
        imprimir(estados)
        return 0 if all(e.acao != "tentar de novo" for e in estados) else 1
    estados = ibge.atualizar(a.cache_dir, a.uf, sessao, a.forcar_api)
    imprimir(estados)
    falhas = ibge.preparar(a.cache_dir, a.uf, sessao)  # o que ainda falte (ex.: derivado apagado à mão)
    if any(e.acao in ("baixado", "atualizado") for e in estados):
        print("Dados do IBGE atualizados: reinicie os sites no ar para usar a versão nova.")
    for f in falhas:
        print("FALHA:", f)
    return 0 if not falhas and all(e.acao != "tentar de novo" for e in estados) else 1


def main(argv: list[str] | None = None, sessao=requests) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    intervalo = max(a.intervalo, 3600)  # os dados do IBGE mudam em meses, não em minutos
    while True:
        codigo = rodada(a, sessao)
        if not a.vigiar:
            return codigo
        logger.info("próxima verificação em %.1f h", intervalo / 3600)
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
