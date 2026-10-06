"""Conferência do resultado gravado na noite (tempo real) com o importado dos microdados (TODO 16, rodada 45).

    python conferir_resultado.py                          # RJ, 1º turno de 2026: dados_2026/oficial × historico_2026_t1
    python conferir_resultado.py --uf ES --turno 2        # oficial_t2_ES × historico_2026_t2_ES
    python conferir_resultado.py --noite X --importado Y --saida saidas/conf.xlsx

Compara totais, votos/situação/destinação dos candidatos e os eleitos de deputado; grava a planilha em
saidas/<UF>/conferencia_<ano>_t<turno>.xlsx. Código de saída 0 se tudo bate, 1 se há diferença (os avisos do
importado — totais provisórios, destinação ainda não publicada — explicam as diferenças esperadas).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

from apuracao import conferencia as cf
from apuracao.divulgacao.coletor import destino_padrao
from apuracao.ufs import dir_uf, tem_dados


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Tempo real × microdados importados: totais, candidatos e cadeiras.")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--turno", type=int, choices=[1, 2], default=1)
    p.add_argument("--noite", type=Path, help="pasta do coletor (padrão: dados_2026/oficial[_t2][_UF])")
    p.add_argument("--importado", type=Path, help="pasta importada (padrão: dados_2026/historico_<ano>_t<turno>[_UF])")
    p.add_argument("--saida", type=Path, help="padrão: saidas/<UF>/conferencia_<ano>_t<turno>.xlsx")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    noite = a.noite or dir_uf(destino_padrao("oficial", turno=a.turno), a.uf)
    importado = a.importado or dir_uf(Path(f"dados_2026/historico_{a.ano}_t{a.turno}"), a.uf)
    for nome, pasta in (("noite", noite), ("importado", importado)):
        if not tem_dados(pasta):
            print(f"sem dados em {pasta} ({nome})", file=sys.stderr)
            return 2
    c = cf.conferir(noite, importado, a.uf)
    saida = cf.para_planilha(c, a.saida or Path("saidas") / a.uf / f"conferencia_{a.ano}_t{a.turno}.xlsx")
    with pl.Config(tbl_rows=30, tbl_width_chars=160, fmt_str_lengths=80):
        print(f"{noite} × {importado}")
        print("\ntotais (cargo × coluna com diferença):", c.resumo_totais if c.resumo_totais.height else "iguais")
        print(f"\ncandidatos com votos/situação/destinação diferentes: {c.candidatos.height}")
        if c.candidatos.height:
            print(c.candidatos.group_by("CARGO").len().sort("CARGO"))
        print(f"candidatos com voto só num lado: {c.so_num_lado.height}")
        if c.so_num_lado.height:
            print(c.so_num_lado.group_by("CARGO", "ONDE").agg(pl.len().alias("N")).sort("CARGO", "ONDE"))
        print("\ncadeiras:", c.cadeiras if c.cadeiras.height else "sem deputados")
        for av in c.avisos:
            print("AVISO:", av)
    print(f"\n{'TUDO IGUAL' if c.ok else 'HÁ DIFERENÇAS (ver planilha e avisos)'} — planilha: {saida}")
    return 0 if c.ok else 1


if __name__ == "__main__":
    sys.exit(main())
