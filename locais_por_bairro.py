"""Lista os locais de votação de um bairro e as seções eleitorais de cada local.

Lê o cadastro de eleitorado do TSE (cache em --cache-dir; baixa se faltar). O bairro é,
por padrão, o texto NM_BAIRRO do cadastro; com --fonte ibge, o bairro da malha do IBGE
(Censo 2022) que contém a coordenada do local. Nomes comparados sem acento, caixa ou
pontuação. Seções agregadas aparecem com a seção principal entre parênteses.

    python locais_por_bairro.py Tijuca --municipio "Rio de Janeiro"
    python locais_por_bairro.py tijuca --contem --uf RJ --ano 2024
    python locais_por_bairro.py Icaraí --municipio Niterói --fonte ibge --saida saidas/icarai.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import bairros as br
from apuracao import eleitorado as el
from apuracao import locais_bairro as lb

logger = logging.getLogger("locais_por_bairro")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Locais de votação de um bairro e as seções de cada local.")
    p.add_argument("bairro", help="nome do bairro (sem diferença de acento, caixa ou pontuação)")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--ano", type=int, default=2026, help="ano do cadastro de eleitorado (padrão 2026)")
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--municipio", help="restringe a um município (o mesmo nome de bairro existe em vários)")
    p.add_argument("--contem", action="store_true", help="aceita bairros cujo nome CONTÉM o texto dado")
    p.add_argument("--fonte", choices=lb.FONTES, default="cadastro",
                   help="cadastro = bairro-texto do TSE; ibge = malha de bairros do Censo 2022 (pela coordenada)")
    p.add_argument("--saida", help="grava as seções em CSV (;) em vez de só imprimir")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE ao baixar")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _rotulo_secao(r: dict) -> str:
    return str(r["NR_SECAO"]) if r["TIPO_SECAO"] == "PRINCIPAL" else f"{r['NR_SECAO']} (agregada à {r['NR_SECAO_PRINCIPAL']})"


def imprimir(locais: pl.DataFrame, secoes: pl.DataFrame) -> None:
    por_local = secoes.partition_by(v.LOCAL_KEY, as_dict=True, maintain_order=True)
    municipio = None
    for loc in locais.iter_rows(named=True):
        if loc["NM_MUNICIPIO"] != municipio:
            municipio = loc["NM_MUNICIPIO"]
            print(f"\n== {municipio} ==")
        chave = tuple(loc[k] for k in v.LOCAL_KEY)
        linhas = por_local[chave].iter_rows(named=True)
        print(f"\nZona {loc['NR_ZONA']} · Local {loc['NR_LOCAL_VOTACAO']} — {loc['NM_LOCAL_VOTACAO']}")
        print(f"  {loc['DS_ENDERECO'] or 's/ endereço'} — {loc['BAIRRO']}")
        print(f"  {loc['N_SECOES']} seções, {_milhar(loc['QT_ELEITORES'])} eleitores")
        print(f"  Seções: {', '.join(_rotulo_secao(r) for r in linhas)}")
    print(f"\nTotal: {locais.height} locais, {secoes.height} seções, "
          f"{_milhar(int(secoes['QT_ELEITOR_SECAO'].sum()))} eleitores")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cache = Path(args.cache_dir)
    try:
        secoes = el.load_sections(args.ano, args.uf, cache, args.sha512, args.turno)
        muni = v.resolve_municipality(secoes.lazy(), args.municipio)
        secoes = el.filter_area(secoes, muni)
        geo = br.malha(args.uf, cache) if args.fonte == "ibge" else None
        locais = lb.locais_do_bairro(secoes, args.bairro, args.fonte, args.contem, geo)
        if locais.is_empty():
            parecidos = lb.sugestoes(secoes, args.bairro, args.fonte, geo)
            logger.error("nenhum local no bairro '%s' (cadastro %s, %s%s). Parecidos: %s", args.bairro, args.ano,
                         args.uf, f", {args.municipio}" if args.municipio else "", parecidos or "nenhum")
            return 1
        tabela = lb.secoes_dos_locais(secoes, locais)
        imprimir(locais, tabela)
        if args.saida:
            destino = Path(args.saida)
            destino.parent.mkdir(parents=True, exist_ok=True)
            tabela.write_csv(destino, separator=";")
            print(f"Seções gravadas em {destino}")
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
