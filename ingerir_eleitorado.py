"""Ingere o eleitorado por local de votação no cache (ZIP -> Parquet por UF).

Usa o ZIP já presente em --cache-dir (registrando a proveniência de arquivo colocado
manualmente) ou o baixa da CDN do TSE.

Com --atualizar, consulta a CDN (um HEAD) e, se o TSE regerou o arquivo, guarda a versão do
cache no acervo (cache_tse/versoes/eleitorado_local_votacao_<ano>/<carimbo>/), baixa a nova e
apaga os Parquet derivados (refeitos aqui, para as UFs pedidas, ou no próximo uso). --versoes
lista as versões guardadas.

    python ingerir_eleitorado.py --ano 2026 --uf RJ
    python ingerir_eleitorado.py --ano 2024 --uf RJ SP --relatorio-geo
    python ingerir_eleitorado.py --ano 2026 --atualizar --uf todas
    python ingerir_eleitorado.py --ano 2026 --versoes
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

import votos_por_local_votacao as v
from apuracao import eleitorado as el
from apuracao import ufs as uf_mod
from apuracao import versoes as vs

logger = logging.getLogger("ingerir_eleitorado")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingerir eleitorado por local de votação (TSE) no cache.")
    p.add_argument("--ano", type=int, required=True)
    p.add_argument("--uf", nargs="+",
                   help="siglas (ex.: RJ SP) ou 'todas'; obrigatório, exceto com --atualizar ou --versoes")
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--atualizar", action="store_true",
                   help="baixar a versão nova do TSE, se houver, guardando a do cache no acervo de versões")
    p.add_argument("--forcar", action="store_true", help="com --atualizar: baixar mesmo sem Last-Modified mais novo")
    p.add_argument("--versoes", action="store_true", help="listar as versões guardadas do cadastro do ano e sair")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE ao baixar")
    p.add_argument("--relatorio-geo", action="store_true", help="qualidade das coordenadas por local")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def imprimir_versoes(cache: Path, nome_zip: str) -> None:
    versoes = vs.listar(cache, nome_zip)
    if not versoes:
        print(f"Nenhuma versão de {nome_zip} guardada em {vs.acervo(cache, nome_zip)}")
        return
    prov = vs.proveniencia_no_cache(cache, nome_zip)
    print(f"Versões de {nome_zip} em {vs.acervo(cache, nome_zip)}:")
    for x in versoes:
        marca = "  ← no cache" if x.sha512 == prov.get("sha512") else ""
        print(f"  {x.descricao()}  {x.bytes / 1e6:.1f} MB  SHA-512 {x.sha512[:16]}…{marca}")


def imprimir_atualizacao(a: vs.Atualizacao, ano: int) -> None:
    print(f"\nCadastro de eleitorado {ano}: {a.situacao}")
    if a.anterior is not None and a.anterior.sha512 != a.atual.sha512:
        print(f"  anterior: {a.anterior.descricao()}\n            guardada em {a.anterior.pasta}")
    print(f"  no cache: {a.atual.descricao()}\n            guardada em {a.atual.pasta}")
    if a.derivados_apagados:
        print(f"  {len(a.derivados_apagados)} Parquet derivados da versão anterior apagados (refeitos ao usar)")


def _ufs(pedidas: list[str]) -> list[str]:
    """"todas" → as 27 UFs; senão, as siglas pedidas em maiúsculas (sem validar: "BR"/"ZZ" também valem)."""
    return uf_mod.lista(pedidas) if [u.lower() for u in pedidas] == ["todas"] else [u.upper() for u in pedidas]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.uf and not (args.atualizar or args.versoes):
        parser.error("informe --uf (ou use --atualizar / --versoes)")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cache = Path(args.cache_dir)
    try:
        lista = _ufs(args.uf or [])
        spec = v.electorate_spec(args.ano, lista[0] if lista else uf_mod.UF_LEGADA)
        if args.versoes:
            imprimir_versoes(cache, spec.zip_name)
            return 0
        if args.atualizar:
            imprimir_atualizacao(vs.atualizar(spec, cache, forcar=args.forcar), args.ano)
        for uf in lista:
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
