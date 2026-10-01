"""Cópia de segurança dos dados da apuração (ver apuracao/copia.py).

    python copiar_dados.py --dados dados_2026/oficial --destino /mnt/d/apuracao_copias/oficial            # uma cópia agora
    python copiar_dados.py --dados dados_2026/oficial --destino /mnt/d/apuracao_copias/oficial --vigiar   # a noite toda

O site com --coletar já faz a cópia sozinho (--copia-dir); use este comando quando o coletor roda à parte,
para uma cópia fora de hora ou para outro disco.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

from apuracao.copia import Copiador


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cópia de segurança dos dados da apuração.")
    p.add_argument("--dados", required=True, help="pasta de dados do coletor (ex.: dados_2026/oficial)")
    p.add_argument("--destino", required=True, help="pasta da cópia (de preferência em outro disco)")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--vigiar", action="store_true", help="copiar a cada hora e no fim, até Ctrl+C")
    p.add_argument("--intervalo-min", type=int, default=60)
    p.add_argument("--manter", type=int, default=6, help="instantâneos da hora guardados (o final sempre fica)")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    dados = Path(a.dados)
    if not dados.exists():
        print(f"pasta de dados inexistente: {dados}", file=sys.stderr)
        return 1
    try:
        c = Copiador(dados, Path(a.destino), a.uf, a.intervalo_min, a.manter)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    if a.vigiar:
        parar = threading.Event()
        try:
            c.executar(parar)
        except KeyboardInterrupt:
            parar.set()
        return 0
    r = c.copiar(f"manual_{datetime.now():%Y-%m-%d_%Hh%M%S}")
    print(f"cópia em {r['instantaneo']} ({r['raw_novos']} parciais novas em {Path(a.destino) / 'raw'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
