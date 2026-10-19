"""Lista os locais de votação de um bairro e as seções eleitorais de cada local.

Lê o cadastro de eleitorado do TSE (cache em --cache-dir; baixa se faltar), no turno pedido
(--turno, padrão 1). O bairro é, por padrão, o texto NM_BAIRRO do cadastro; com --fonte ibge, o
bairro da malha do IBGE (Censo 2022) que contém a coordenada do local. Nomes comparados sem
acento, caixa ou pontuação. Seções agregadas aparecem com a seção principal entre parênteses.

O TSE regera o cadastro no mesmo endereço: atualize antes com
`python ingerir_eleitorado.py --ano 2026 --atualizar`. A versão usada (carimbo, geração do TSE,
SHA-512) vai para a aba Consulta e para o nome da planilha e fica guardada no acervo
(cache_tse/versoes/); --versao refaz a lista com uma versão guardada.

Imprime a lista e grava a planilha .xlsx (abas Locais, Seções e Consulta), por padrão em
saidas/<UF>/locais_bairro_<bairro>_<ano>_t<turno>[_ibge]_<carimbo>.xlsx.

    python locais_por_bairro.py Tijuca --municipio "Rio de Janeiro"
    python locais_por_bairro.py Rocinha --municipio "Rio de Janeiro" --fonte ibge --turno 2
    python locais_por_bairro.py tijuca --contem --uf RJ --ano 2024
    python locais_por_bairro.py Icaraí --municipio Niterói --fonte ibge --saida saidas/icarai.xlsx
    python locais_por_bairro.py Gávea --municipio "Rio de Janeiro" --versao 2026-10-06
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
from apuracao import versoes as vs

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
    p.add_argument("--versao", help="carimbo (ou começo dele) de uma versão guardada do cadastro; padrão: a do cache")
    p.add_argument("--saida", type=Path,
                   help="planilha .xlsx; padrão saidas/<UF>/locais_bairro_<bairro>_<ano>_t<turno>[_ibge]_<carimbo>.xlsx")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE ao baixar")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def destino_padrao(uf: str, bairro: str, ano: int, turno: int, versao: vs.Versao, fonte: str = "cadastro") -> Path:
    """Um arquivo por bairro, ano, turno, fonte e versão do cadastro: uma lista não grava por cima da outra."""
    nome = f"locais_bairro_{el.compact(bairro).lower()}_{ano}_t{turno}{'_ibge' if fonte == 'ibge' else ''}"
    return Path("saidas") / uf / f"{nome}_{versao.carimbo}.xlsx"


def imprimir(locais: pl.DataFrame, secoes: pl.DataFrame) -> None:
    municipio = None
    for loc in lb.tabela_locais(locais, secoes).iter_rows(named=True):
        if loc["NM_MUNICIPIO"] != municipio:
            municipio = loc["NM_MUNICIPIO"]
            print(f"\n== {municipio} ==")
        print(f"\nZona {loc['NR_ZONA']} · Local {loc['NR_LOCAL_VOTACAO']} — {loc['NM_LOCAL_VOTACAO']}")
        print(f"  {loc['DS_ENDERECO'] or 's/ endereço'} — {loc['BAIRRO']}")
        print(f"  {loc['N_SECOES']} seções, {_milhar(loc['QT_ELEITORES'])} eleitores")
        print(f"  Seções: {loc['SECOES']}")
    print(f"\nTotal: {locais.height} locais, {secoes.height} seções, "
          f"{_milhar(int(secoes['QT_ELEITOR_SECAO'].sum()))} eleitores")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cache = Path(args.cache_dir)
    try:
        spec = v.electorate_spec(args.ano, args.uf)
        if args.versao:
            versao = vs.escolher(cache, spec.zip_name, args.versao)
            fonte_cadastro = versao.pasta  # a pasta da versão tem o layout do cache
        else:
            v.download(spec, cache, args.sha512)
            el.ensure_local_provenance(spec, cache)
            versao, fonte_cadastro = vs.em_uso(cache, spec.zip_name), cache
        secoes = el.load_sections(args.ano, args.uf, fonte_cadastro, args.sha512, args.turno)
        if secoes.is_empty():
            raise v.TseDataError(f"o cadastro de eleitorado de {args.ano} não tem linhas do {args.turno}º turno "
                                 f"para {args.uf}")
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
        print(f"Cadastro de eleitorado {args.ano}, {args.turno}º turno — versão {versao.descricao()}")
        imprimir(locais, tabela)
        consulta = {"bairro": args.bairro, "fonte": args.fonte, "nome exato": not args.contem, "UF": args.uf,
                    "município": args.municipio or "todos", "cadastro de eleitorado": args.ano, "turno": args.turno,
                    **versao.para_consulta()}
        destino = lb.para_planilha(
            locais, tabela, consulta,
            args.saida or destino_padrao(args.uf, args.bairro, args.ano, args.turno, versao, args.fonte))
        print(f"Planilha gravada em {destino}")
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
