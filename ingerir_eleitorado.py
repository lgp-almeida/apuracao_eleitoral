"""Ingere o eleitorado por local de votação no cache (ZIP -> Parquet por UF).

Usa o ZIP já presente em --cache-dir (registrando a proveniência de arquivo colocado
manualmente) ou o baixa da CDN do TSE.

    python ingerir_eleitorado.py --ano 2026 --uf RJ
    python ingerir_eleitorado.py --ano 2024 --uf RJ SP --relatorio-geo
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

import votos_por_local_votacao as v
from apuracao import eleitorado as el

logger = logging.getLogger("ingerir_eleitorado")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingerir eleitorado por local de votação (TSE) no cache.")
    p.add_argument("--ano", type=int, required=True)
    p.add_argument("--uf", nargs="+", required=True, type=str.upper)
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE ao baixar")
    p.add_argument("--relatorio-geo", action="store_true", help="qualidade das coordenadas por local")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cache = Path(args.cache_dir)
    try:
        for uf in args.uf:
            sections = el.load_sections(args.ano, uf, cache, args.sha512, args.turno)
            print(f"\nEleitorado {args.ano} — {uf} ({args.turno}º turno)")
            for k, val in el.summary(sections).items():
                print(f"  {k:<26}{val:>14,}")
            if args.relatorio_geo:
                print("  coordenadas por local:")
                for k, val in el.geo_report(el.places(sections), uf).items():
                    print(f"    {k:<46}{val:>10,}")
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
