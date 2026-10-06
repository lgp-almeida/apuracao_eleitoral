"""Comparação entre UFs: abstenção, brancos/nulos e transferência 1º → 2º turno lado a lado (TODO 20).

    python comparar_ufs.py                                   # 27 UFs, 2026 (oficial) × 2022 (histórico)
    python comparar_ufs.py --ufs RJ SP MG --cargo governador --saida saidas/ufs.xlsx --grafico saidas/abstencao.png

Lê as pastas no formato do coletor (`dados_2026/oficial[_t2]_<UF>`, `historico_2022_t<turno>_<UF>`); o 2º turno de
2026 entra sozinho quando as pastas `oficial_t2_<UF>` existirem. Sem rede. Ver apuracao/entre_ufs.py.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import polars as pl

from apuracao import entre_ufs as eu
from apuracao import ufs as uu

CARGOS = {"presidente": 1, "governador": 3}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Comparação entre UFs: abstenção, brancos/nulos e transferência 1º → 2º turno.")
    p.add_argument("--dados", default="dados_2026", help="diretório com as pastas das UFs")
    p.add_argument("--ambiente", default="oficial", help="pastas da eleição atual (<ambiente>[_t2]_<UF>)")
    p.add_argument("--ano-ref", type=int, default=2022, help="eleição de referência (historico_<ano>_t<turno>_<UF>)")
    p.add_argument("--ufs", nargs="+", default=["todas"])
    p.add_argument("--cargo", nargs="+", choices=list(CARGOS), default=list(CARGOS))
    p.add_argument("--sem-transferencia", action="store_true", help="só abstenção e brancos/nulos (mais rápido)")
    p.add_argument("--saida", help="planilha .xlsx (participação, variação, transferência)")
    p.add_argument("--grafico", help="PNG da abstenção por UF (Presidente, 1º turno), referência × atual")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    try:
        ufs = uu.lista(a.ufs)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    cargos = [CARGOS[c] for c in a.cargo]
    eleicoes = eu.eleicoes_padrao(Path(a.dados), a.ambiente, a.ano_ref)
    atual, ref = eleicoes[0].rotulo, eleicoes[1].rotulo
    part = eu.participacao(eleicoes, ufs, cargos)
    if part.is_empty():
        print("erro: nenhuma pasta com dados para as UFs pedidas", file=sys.stderr)
        return 1
    var = eu.variacao(part, atual, ref)
    transf = pl.DataFrame(schema=eu.SCHEMA_TRANSF) if a.sem_transferencia else eu.transferencias(eleicoes, ufs, cargos)
    with pl.Config(tbl_rows=60, tbl_cols=14, tbl_width_chars=220, float_precision=2, fmt_str_lengths=30):
        for cargo in cargos:
            for turno in (1, 2):
                d = var.filter((pl.col("CARGO") == cargo) & (pl.col("TURNO") == turno))
                if not d.is_empty():
                    print(f"\n{eu.CARGOS[cargo]}, {turno}º turno — {atual} × {ref} (p.p.), da maior alta da abstenção:")
                    print(d.drop("CARGO", "TURNO"))
        if not transf.is_empty():
            print("\nTransferência 1º → 2º turno por UF (municípios como unidades; leitura frágil):")
            print(transf.select("ELEICAO", "CARGO", "UF", "MUNICIPIOS", "FINALISTA_A", "ELIM_PARA_A", "FINALISTA_B",
                                "ELIM_PARA_B", "ELIM_PARA_ABSTENCAO", "ABSTENCAO_EXTRA_PP", "CELULAS_NO_LIMITE", "NOTA"))
    if a.saida:
        print(f"\nplanilha: {eu.para_planilha(part, var, transf, Path(a.saida))}")
    if a.grafico:
        g = eu.grafico(var, 1 if 1 in cargos else cargos[0], 1, Path(a.grafico), atual, ref)
        print(f"gráfico: {g}" if g else "gráfico: sem dados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
