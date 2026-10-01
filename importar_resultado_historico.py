"""Importa o resultado de uma eleição passada (microdados do TSE) para o site de apuração.

    python importar_resultado_historico.py --ano 2022 --uf RJ --turno 1 2
    python site_apuracao.py --dados dados_2026/historico_2022_t1      # abre o 1º turno de 2022

Grava dados_2026/historico_<ano>_t<turno>/ no mesmo formato do coletor em tempo real
(ver apuracao/historico.py). Baixa da CDN do TSE o que faltar no cache.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

import votos_por_local_votacao as v
from apuracao import historico

logger = logging.getLogger("importar_resultado_historico")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Resultado de eleição passada no formato do site de apuração.")
    p.add_argument("--ano", type=int, required=True)
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--turno", type=int, nargs="+", default=[1], choices=[1, 2])
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--raiz", default="dados_2026", help="destino: <raiz>/historico_<ano>_t<turno>")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        for turno in args.turno:
            destino = Path(args.raiz) / f"historico_{args.ano}_t{turno}"
            n = historico.importar(args.ano, args.uf, turno, Path(args.cache_dir), destino)
            print(f"{args.ano} {args.uf} {turno}º turno: {n} -> {destino}")
            print(f"  python site_apuracao.py --dados {destino}")
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
