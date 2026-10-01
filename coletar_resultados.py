"""Coleta os resultados da divulgação do TSE (2026) e guarda os snapshots localmente.

    python coletar_resultados.py --ambiente simulado --uma-vez
    python coletar_resultados.py --ambiente oficial --intervalo 60      # noite da eleição

Coleta todos os cargos da UF (UF e cada município) e o Presidente (Brasil, UF e
municípios). Só baixa de novo o que mudou desde o ciclo anterior. Dados em
dados_2026/<ambiente>/ (ver apuracao/divulgacao/coletor.py). Ctrl+C encerra.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

from apuracao.divulgacao.cliente import AMBIENTES, BloqueioTSE, ClienteDivulgacao, DivulgacaoIndisponivel
from apuracao.divulgacao.coletor import Coletor, destino_padrao, tipo_do_erro

logger = logging.getLogger("coletar_resultados")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Coleta dos resultados em tempo real do TSE (2026).")
    p.add_argument("--ambiente", choices=sorted(AMBIENTES), default="simulado")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--intervalo", type=float, default=60.0, help="segundos entre ciclos")
    p.add_argument("--max-rps", type=float, default=20.0, help="requisições por segundo (TSE: máx. 100)")
    p.add_argument("--destino", help="diretório de dados (padrão: dados_2026/<ambiente>; no 2º turno, <ambiente>_t2)")
    p.add_argument("--sem-presidente-br", action="store_true", help="não baixar o arquivo nacional do presidente")
    p.add_argument("--uma-vez", action="store_true", help="um único ciclo e sai")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    destino = Path(args.destino) if args.destino else destino_padrao(args.ambiente, turno=args.turno)
    coletor = Coletor(ClienteDivulgacao(args.ambiente, max_rps=args.max_rps), destino, args.uf, args.turno,
                      presidente_br=not args.sem_presidente_br)
    if not args.uma_vez:
        try:
            coletor.executar(args.intervalo)
        except KeyboardInterrupt:
            logger.info("encerrado")
        return 0
    try:
        r = coletor.ciclo()
    except (DivulgacaoIndisponivel, BloqueioTSE, requests.RequestException) as exc:
        logger.error("%s", exc)
        coletor._registrar_erro(str(exc), tipo_do_erro(exc))
        return 1
    print(f"\n{args.ambiente} — {args.uf}, {args.turno}º turno: {r.abrangencias_alteradas} abrangências, "
          f"{r.arquivos_pedidos} arquivos pedidos ({r.arquivos_novos} novos, {r.arquivos_304} sem mudança, "
          f"{r.arquivos_404} ausentes) em {(r.fim - r.inicio).total_seconds():.1f}s")
    print(f"requisições HTTP: {dict(r.estatisticas)}\ndados: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
