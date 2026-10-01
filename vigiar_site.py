"""Vigia de processo: roda o site (ou o coletor) e o reinicia se ele cair ou parar de responder.

    python vigiar_site.py -- python site_apuracao.py --ambiente oficial --coletar --abrir
    python vigiar_site.py --intervalo 30 --falhas 3 -- python site_apuracao.py --ambiente oficial --coletar

Tudo depois de `--` é o comando vigiado. A porta verificada é a do `--porta` do comando (padrão 8000).
Eventos: `dados_2026/vigia/porta_<N>.log`; estado (lido pelo portal): `dados_2026/vigia/porta_<N>.json`.
Ctrl+C encerra o vigia e o site.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from apuracao.vigia_site import PASTA_PADRAO, VigiaSite


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reinicia o site da apuração se ele cair ou parar de responder.")
    p.add_argument("--intervalo", type=float, default=30.0, help="segundos entre verificações (padrão 30)")
    p.add_argument("--falhas", type=int, default=3, help="verificações sem resposta antes de reiniciar (padrão 3)")
    p.add_argument("--espera-inicial", type=float, default=90.0,
                   help="segundos de tolerância depois de subir (o 1º ciclo do coletor demora; padrão 90)")
    p.add_argument("--porta", type=int, help="porta a verificar (padrão: a do --porta do comando, ou 8000)")
    p.add_argument("--pasta", default=str(PASTA_PADRAO), help="pasta do log e do estado (lida pelo portal)")
    p.add_argument("comando", nargs=argparse.REMAINDER, help="-- comando a vigiar")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    comando = a.comando[1:] if a.comando[:1] == ["--"] else a.comando
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    try:
        vigia = VigiaSite(comando, a.porta, Path(a.pasta), a.intervalo, a.falhas, a.espera_inicial)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    parar = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    try:
        vigia.executar(parar)
    except KeyboardInterrupt:
        parar.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
