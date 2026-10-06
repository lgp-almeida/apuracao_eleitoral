"""Migração de votos entre duas eleições (ex.: 2022 → 2026), por local de votação (inferência ecológica).

    python migracao_votos.py --ano-a 2022 --ano-b 2026 --uf RJ --cargo presidente
    python migracao_votos.py --cargo governador --municipio "Niterói" --saida saidas/migracao.xlsx

Unidade = local presente nos dois cadastros; categorias = candidatos com ≥ 1% dos válidos (até 5), Outros,
branco/nulo e abstenção. Ver apuracao/migracao.py (método e ressalvas) e docs/RODADA_46_*.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import votos_por_local_votacao as v
from apuracao import migracao as mg
from apuracao import transferencia as tr
from transferencia_turnos import imprimir

CARGOS = {nome: cod for cod, nome in mg.NOMES_CARGO.items()}


def _cargo(texto: str) -> int:
    t = texto.strip().lower()
    if t.isdigit() and int(t) in mg.NOMES_CARGO:
        return int(t)
    if t not in CARGOS:
        raise argparse.ArgumentTypeError(f"cargo: {', '.join(CARGOS)}")
    return CARGOS[t]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Migração de votos entre duas eleições, por local de votação.")
    p.add_argument("--ano-a", type=int, default=2022, help="eleição de origem (padrão 2022)")
    p.add_argument("--ano-b", type=int, default=2026, help="eleição de destino (padrão 2026)")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--cargo", type=_cargo, default=1, help="presidente ou governador")
    p.add_argument("--municipio", help="restringe a um município (nome ou código TSE)")
    p.add_argument("--bootstrap", type=int, default=100, help="replicações do bootstrap (0 = sem intervalo)")
    p.add_argument("--saida", help="planilha .xlsx (matriz, validação e uma linha por local)")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    cache = Path(a.cache_dir)
    try:
        municipio = None
        if a.municipio:
            votos = v.load_section_votes(a.ano_b, a.uf, mg.NOMES_CARGO[a.cargo], cache, False)
            municipio = int(a.municipio) if a.municipio.isdigit() else v.resolve_municipality(votos, a.municipio)
        res = mg.calcular(a.ano_a, a.ano_b, a.uf, a.cargo, cache, municipio, a.bootstrap)
    except (v.TseDataError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    r = tr.resumo(res)
    imprimir(r, (str(a.ano_a), str(a.ano_b)))
    if a.saida:
        Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
        tr.para_planilha(r, res.por_unidade, Path(a.saida), (str(a.ano_a), str(a.ano_b)))
        print(f"\nplanilha: {a.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
