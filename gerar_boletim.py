"""Boletim da apuração para a equipe: HTML de um arquivo + planilha (ver apuracao/boletim.py).

    python gerar_boletim.py --ambiente oficial                 # um boletim agora, da situação atual
    python gerar_boletim.py --ambiente oficial --vigiar        # a cada hora cheia e no fim (Ctrl+C encerra)
    python gerar_boletim.py --dados dados_2026/historico_2022_t1

O site com --coletar já grava os boletins sozinho; use este comando quando o coletor roda à parte ou
para um boletim fora de hora. Os arquivos ficam em <dados>/boletins/ (boletim_ultimo.* = o mais recente).
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from apuracao.boletim import Boletineiro
from apuracao.divulgacao.cliente import AMBIENTES
from apuracao.divulgacao.coletor import destino_padrao
from apuracao.ufs import dir_uf
from apuracao.web.app import create_app


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Boletim da apuração (HTML + planilha).")
    p.add_argument("--ambiente", choices=sorted(AMBIENTES), default="simulado")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--dados", help="diretório de dados (padrão: dados_2026/<ambiente>[_t2]_<UF>; no RJ, a pasta antiga)")
    p.add_argument("--saida", help="diretório dos boletins (padrão: <dados>/boletins)")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--destacar", nargs="+", default=[], metavar="SIGLA",
                   help='partidos/federações com ★ nas listas de eleitos, ex.: PL "PT/PC do B/PV"')
    p.add_argument("--vigiar", action="store_true", help="gerar a cada intervalo e no fim, até Ctrl+C")
    p.add_argument("--intervalo-min", type=int, default=60, help="minutos entre boletins com --vigiar")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    dados = Path(a.dados) if a.dados else dir_uf(destino_padrao(a.ambiente, turno=a.turno), a.uf)
    if not (dados / "ultimo").exists():
        print(f"sem dados do coletor em {dados}", file=sys.stderr)
        return 1
    app = create_app(dados, a.uf, Path(a.cache_dir))
    b = Boletineiro(app.state.consultas, Path(a.saida) if a.saida else dados / "boletins", a.intervalo_min,
                    destacar=a.destacar)
    if a.vigiar:
        parar = threading.Event()
        try:
            b.executar(parar)
        except KeyboardInterrupt:
            parar.set()
        return 0
    sit = b.situacao()
    if sit == "sem dados":
        print("ainda não há votos apurados; nenhum boletim gerado", file=sys.stderr)
        return 1
    agora = b.agora()
    final = sit == "final"
    arquivos = b.gerar("boletim_final" if final else f"boletim_{agora:%Y-%m-%d_%Hh%M}",
                       "Boletim final" if final else f"Boletim das {agora:%Hh%M}", final=final)
    print("\n".join(str(p) for p in arquivos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
