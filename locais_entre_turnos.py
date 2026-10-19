"""Seções eleitorais que mudam de local de votação entre o 1º e o 2º turno (cadastro de eleitorado do TSE).

O cadastro traz cada seção uma vez por turno, com o local onde ela vota e o local cadastrado (original): a
diferença mostra a seção que vai para um local temporário, a que volta ao local de sempre e a que muda por
outro motivo (situações em `apuracao/locais_turnos.py`). O cadastro diz onde a seção DEVE votar; onde ela
votou sai nos microdados de votação do 2º turno.

O TSE regera o cadastro no mesmo endereço: atualize antes com
`python ingerir_eleitorado.py --ano 2026 --atualizar`. A versão usada (carimbo, geração do TSE, SHA-512) vai
para a aba Consulta e para o nome da planilha e fica guardada no acervo (cache_tse/versoes/); --versao refaz a
comparação com uma versão guardada.

Imprime o resumo e os pares de locais e grava a planilha .xlsx (abas Resumo, Locais, Seções e Consulta), por
padrão em saidas/<UF>/locais_entre_turnos_<ano>_<carimbo>.xlsx (saidas/BR/ com --ufs todas).

    python locais_entre_turnos.py
    python locais_entre_turnos.py --ufs RJ --municipio "Rio de Janeiro"
    python locais_entre_turnos.py --ufs todas --limite 100
    python locais_entre_turnos.py --versao 2026-10-06 --saida saidas/RJ/turnos_06out.xlsx
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import eleitorado as el
from apuracao import locais_turnos as lt
from apuracao import ufs as uf_mod
from apuracao import versoes as vs

logger = logging.getLogger("locais_entre_turnos")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seções que mudam de local de votação entre o 1º e o 2º turno.")
    p.add_argument("--ufs", nargs="+", default=["RJ"], help="siglas (ex.: RJ SP) ou 'todas' (padrão RJ)")
    p.add_argument("--ano", type=int, default=2026, help="ano do cadastro de eleitorado (padrão 2026)")
    p.add_argument("--municipio", help="restringe a um município (só com uma UF)")
    p.add_argument("--versao", help="carimbo (ou começo dele) de uma versão guardada do cadastro; padrão: a do cache")
    p.add_argument("--limite", type=int, default=40, help="pares de locais impressos (padrão 40; todos na planilha)")
    p.add_argument("--saida", type=Path,
                   help="planilha .xlsx; padrão saidas/<UF>/locais_entre_turnos_<ano>_<carimbo>.xlsx")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE ao baixar")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def destino_padrao(ufs: list[str], ano: int, versao: vs.Versao) -> Path:
    return Path("saidas") / uf_mod.rotulo(ufs) / f"locais_entre_turnos_{ano}_{versao.carimbo}.xlsx"


def carregar(ano: int, ufs: list[str], cache: Path, sha: bool, municipio: str | None) -> tuple[pl.DataFrame, ...]:
    """Seções do 1º e do 2º turno das UFs pedidas (e do município, com uma UF).

    Raises:
        TseDataError: o cadastro do ano não tem linhas do 2º turno, ou o município não existe.
    """
    turnos = []
    for turno in (1, 2):
        partes = [el.load_sections(ano, uf, cache, sha, turno) for uf in ufs]
        turnos.append(pl.concat(partes, how="vertical_relaxed"))
    if municipio is not None:
        muni = v.resolve_municipality(turnos[0].lazy(), municipio)
        turnos = [el.filter_area(t, muni) for t in turnos]
    if turnos[1].is_empty():
        raise v.TseDataError(f"o cadastro de eleitorado de {ano} não tem linhas do 2º turno para {', '.join(ufs)}")
    return tuple(turnos)


def imprimir(c: lt.Comparacao, versao: vs.Versao, ufs: list[str], limite: int) -> None:
    print(f"\nCadastro de eleitorado — versão {versao.descricao()}")
    print(f"UFs: {', '.join(ufs) if len(ufs) <= 5 else f'{len(ufs)} UFs'} · {_milhar(c.nos_dois_turnos)} seções "
          f"nos dois turnos · {_milhar(c.so_no_1t)} só no 1º turno")
    print(f"\n{'Situação':<20}{'Seções':>9}{'Eleitores':>12}{'Locais no 2º':>14}")
    for r in lt.resumo(c).iter_rows(named=True):
        print(f"{r['SITUACAO']:<20}{_milhar(r['SECOES']):>9}{_milhar(r['ELEITORES']):>12}"
              f"{_milhar(r['LOCAIS_NO_2T']):>14}")
    muda = c.secoes.filter(pl.col("SITUACAO").is_in(lt.MUDA_DE_LOCAL))
    if muda.is_empty():
        print("\nNenhuma seção muda de local entre os turnos.")
    pares = lt.locais(c)
    municipio = None
    for loc in pares.head(limite).iter_rows(named=True):
        if (loc["SG_UF"], loc["NM_MUNICIPIO"]) != municipio:
            municipio = (loc["SG_UF"], loc["NM_MUNICIPIO"])
            print(f"\n== {loc['NM_MUNICIPIO']} ({loc['SG_UF']}) ==")
        antes = f"{loc['NR_LOCAL_VOTACAO_1T']} {loc['NM_LOCAL_VOTACAO_1T']}" if loc["NR_LOCAL_VOTACAO_1T"] else "—"
        dist = f", {loc['DISTANCIA_M'] / 1000:.1f} km".replace(".", ",") if loc["DISTANCIA_M"] else ""
        print(f"Zona {loc['NR_ZONA']} · {antes} → {loc['NR_LOCAL_VOTACAO_2T']} {loc['NM_LOCAL_VOTACAO_2T']} "
              f"[{loc['SITUACAO']}]")
        if loc["NR_LOCAL_VOTACAO_1T"] and loc["DS_ENDERECO_1T"] != loc["DS_ENDERECO_2T"]:
            print(f"  endereço: {loc['DS_ENDERECO_1T']} → {loc['DS_ENDERECO_2T']}")
        print(f"  seções {loc['SECOES']} ({_milhar(loc['QT_ELEITORES'])} eleitores{dist})")
    if pares.height > limite:
        print(f"\n… e mais {_milhar(pares.height - limite)} pares de locais (todos na planilha)")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        ufs = uf_mod.lista(args.ufs)
    except ValueError as exc:
        parser.error(str(exc))
    if args.municipio and len(ufs) != 1:
        parser.error("--municipio só com uma UF")
    cache = Path(args.cache_dir)
    try:
        nome_zip = v.electorate_spec(args.ano, ufs[0]).zip_name
        if args.versao:
            versao = vs.escolher(cache, nome_zip, args.versao)
            fonte = versao.pasta  # a pasta da versão tem o layout do cache
        else:
            v.download(v.electorate_spec(args.ano, ufs[0]), cache, args.sha512)
            el.ensure_local_provenance(v.electorate_spec(args.ano, ufs[0]), cache)
            versao, fonte = vs.em_uso(cache, nome_zip), cache
        t1, t2 = carregar(args.ano, ufs, fonte, args.sha512, args.municipio)
        c = lt.comparar(t1, t2)
        imprimir(c, versao, ufs, args.limite)
        consulta: dict[str, Any] = {"cadastro de eleitorado": args.ano, "UFs": ", ".join(ufs),
                                    "município": args.municipio or "todos", **versao.para_consulta()}
        destino = lt.para_planilha(c, consulta, args.saida or destino_padrao(ufs, args.ano, versao))
        print(f"\nPlanilha gravada em {destino}")
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
