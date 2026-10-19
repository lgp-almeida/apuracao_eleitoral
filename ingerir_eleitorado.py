"""Ingere o eleitorado por local de votação no cache (ZIP -> Parquet por UF).

Usa o ZIP já presente em --cache-dir (registrando a proveniência de arquivo colocado
manualmente) ou o baixa da CDN do TSE.

Com --atualizar, consulta a CDN (um HEAD) e, se o TSE regerou o arquivo, guarda a versão do
cache no acervo (cache_tse/versoes/eleitorado_local_votacao_<ano>/<carimbo>/), baixa a nova e
apaga os Parquet derivados (refeitos aqui, para as UFs pedidas, ou no próximo uso). --versoes
lista as versões guardadas.

Com --diferencas, diz o que mudou entre duas versões guardadas (`apuracao/diferencas_cadastro.py`):
células alteradas no CSV do TSE, linhas criadas e extintas, seções em local temporário e a
situação de cada seção entre os turnos em cada versão. Sem versões, as duas mais recentes; com
uma, ela e a do cache. Grava a planilha em saidas/<UF>/diferencas_cadastro_<ano>_<antes>_<depois>.xlsx
(saidas/BR/ sem --uf).

    python ingerir_eleitorado.py --ano 2026 --uf RJ
    python ingerir_eleitorado.py --ano 2024 --uf RJ SP --relatorio-geo
    python ingerir_eleitorado.py --ano 2026 --atualizar --uf todas
    python ingerir_eleitorado.py --ano 2026 --versoes
    python ingerir_eleitorado.py --ano 2026 --atualizar --diferencas
    python ingerir_eleitorado.py --ano 2026 --diferencas 2026-10-15 2026-10-17 --uf RJ
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import diferencas_cadastro as dc
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
    p.add_argument("--diferencas", nargs="*", metavar="VERSAO",
                   help="o que mudou entre duas versões guardadas (carimbo ou começo dele): a de antes e a de depois "
                        "(padrão: a do cache); sem nenhuma, as duas mais recentes. UFs: --uf (padrão: todas)")
    p.add_argument("--limite", type=int, default=30, help="com --diferencas: alterações por local impressas (padrão 30)")
    p.add_argument("--saida", type=Path, help="com --diferencas: planilha .xlsx; padrão "
                                              "saidas/<UF>/diferencas_cadastro_<ano>_<antes>_<depois>.xlsx")
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


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _curto(texto: str | None, n: int = 70) -> str:
    texto = "" if texto is None else texto
    return texto if len(texto) <= n else texto[:n - 1] + "…"


def versoes_comparadas(cache: Path, spec: v.DatasetSpec, pedidas: list[str]) -> tuple[vs.Versao, vs.Versao]:
    """As versões de antes e de depois de --diferencas: as pedidas; com uma só, ela e a do cache; sem nenhuma, as
    duas mais recentes guardadas (a do cache é guardada antes, se ainda não estiver).

    Raises:
        TseDataError: versão não guardada, menos de duas versões, cadastro fora do cache ou as duas iguais.
    """
    nome = spec.zip_name
    no_cache = None
    if len(pedidas) < 2 and (cache / nome).is_file():
        el.ensure_local_provenance(spec, cache)
        no_cache = vs.em_uso(cache, nome)
    if not pedidas:
        guardadas = vs.listar(cache, nome)
        if len(guardadas) < 2:
            raise v.TseDataError(f"--diferencas sem versões compara as duas mais recentes, mas há "
                                 f"{len(guardadas)} guardada(s) em {vs.acervo(cache, nome)}")
        antes, depois = guardadas[-2:]
    else:
        antes = vs.escolher(cache, nome, pedidas[0])
        if len(pedidas) == 2:
            depois = vs.escolher(cache, nome, pedidas[1])
        elif no_cache is None:
            raise v.TseDataError(f"{nome} não está em {cache}: informe também a versão de depois")
        else:
            depois = no_cache
    if antes.sha512 == depois.sha512:
        raise v.TseDataError(f"as duas versões são a mesma ({antes.carimbo})")
    return antes, depois


def destino_diferencas(ufs: list[str], ano: int, antes: vs.Versao, depois: vs.Versao) -> Path:
    return (Path("saidas") / uf_mod.rotulo(ufs)
            / f"diferencas_cadastro_{ano}_{antes.carimbo}_{depois.carimbo}.xlsx")


def _turnos(versao: vs.Versao, ano: int, ufs: list[str]) -> dc.Turnos:
    """As seções da versão nos dois turnos (a pasta da versão tem o layout do cache: os Parquet ficam nela)."""
    return dc.turnos(*[pl.concat([el.load_sections(ano, uf, versao.pasta, False, turno) for uf in ufs],
                                 how="vertical_relaxed") for turno in (1, 2)])


def imprimir_diferencas(d: dc.Diferencas, antes: dc.Turnos, depois: dc.Turnos, por_uf: pl.DataFrame,
                        m: pl.DataFrame | None, versoes: tuple[vs.Versao, vs.Versao], ufs: list[str], ano: int,
                        limite: int) -> None:
    rotulo = ", ".join(ufs) if len(ufs) <= 5 else f"{len(ufs)} UFs"
    print(f"\nCadastro de eleitorado {ano} — o que mudou entre duas versões ({rotulo})")
    print(f"  antes:  {versoes[0].descricao()}\n  depois: {versoes[1].descricao()}")
    linhas_alteradas = d.celulas.select(dc.CHAVE).n_unique()
    print(f"\nLinhas (seção × turno): {_milhar(d.linhas_antes)} → {_milhar(d.linhas_depois)} · "
          f"{_milhar(d.criadas.height)} criadas · {_milhar(d.extintas.height)} extintas")
    print(f"Células alteradas: {_milhar(d.celulas.height)}, em {_milhar(linhas_alteradas)} linhas "
          f"({' e '.join(dc.IGNORAR)} não contam)")
    if d.colunas_novas or d.colunas_removidas:
        print(f"Colunas novas: {', '.join(d.colunas_novas) or 'nenhuma'} · "
              f"removidas: {', '.join(d.colunas_removidas) or 'nenhuma'} (não comparadas)")
    if d.celulas.height:
        print(f"\n{'Coluna':<32}{'1º turno':>10}{'2º turno':>10}")
        for r in dc.resumo_colunas(d).iter_rows(named=True):
            print(f"{r['COLUNA']:<32}{_milhar(r['LINHAS_1T']):>10}{_milhar(r['LINHAS_2T']):>10}")
    mexeu = por_uf.filter((pl.col("LINHAS_ALTERADAS") + pl.col("CRIADAS") + pl.col("EXTINTAS") > 0)
                          | (pl.col("TEMPORARIAS_2T_ANTES") != pl.col("TEMPORARIAS_2T_DEPOIS")))
    if mexeu.height:
        print(f"\n{'UF':<5}{'Linhas alteradas':>17}{'Criadas':>9}{'Extintas':>10}{'Temporárias no 2º turno':>26}")
        for r in mexeu.iter_rows(named=True):
            temp = f"{_milhar(r['TEMPORARIAS_2T_ANTES'])} → {_milhar(r['TEMPORARIAS_2T_DEPOIS'])}"
            print(f"{r['SG_UF']:<5}{_milhar(r['LINHAS_ALTERADAS']):>17}{_milhar(r['CRIADAS']):>9}"
                  f"{_milhar(r['EXTINTAS']):>10}{temp:>26}")
    soma = {c: int(por_uf[c].sum()) for c in por_uf.columns if c.startswith("TEMPORARIAS")}
    print(f"\nSeções em local temporário (onde vota ≠ local cadastrado): 1º turno "
          f"{_milhar(soma['TEMPORARIAS_1T_ANTES'])} → {_milhar(soma['TEMPORARIAS_1T_DEPOIS'])} · 2º turno "
          f"{_milhar(soma['TEMPORARIAS_2T_ANTES'])} → {_milhar(soma['TEMPORARIAS_2T_DEPOIS'])}")
    if m is None:
        sem = [n for n, t in (("antes", antes), ("depois", depois)) if t.comparacao is None]
        print(f"\nSituação entre os turnos: a versão de {' e a de '.join(sem)} não tem linhas do 2º turno")
    else:
        print(f"\n{'Situação entre os turnos':<26}{'antes (seções / eleitores)':>28}{'depois':>22}")
        for r in dc.situacoes(antes, depois).iter_rows(named=True):
            a = f"{_milhar(r['SECOES_ANTES'])} / {_milhar(r['ELEITORES_ANTES'])}"
            b = f"{_milhar(r['SECOES_DEPOIS'])} / {_milhar(r['ELEITORES_DEPOIS'])}"
            print(f"{r['SITUACAO']:<26}{a:>28}{b:>22}")
        print(f"\nMudaram de situação ou de local no 2º turno: {_milhar(m.height)} seções "
              f"({_milhar(int(m['QT_ELEITOR_SECAO'].sum()))} eleitores)")
        for r in dc.quadro_de_situacoes(m).iter_rows(named=True):
            print(f"  {r['SITUACAO_ANTES']} → {r['SITUACAO_DEPOIS']}: {_milhar(r['SECOES'])} seções, "
                  f"{_milhar(r['ELEITORES'])} eleitores ({r['UFS']})")
    alt = dc.alteracoes(d)
    if alt.height:
        print(f"\nAlterações por local ({_milhar(min(limite, alt.height))} de {_milhar(alt.height)}; "
              "todas na planilha):")
        for r in alt.head(limite).iter_rows(named=True):
            print(f"  {r['SG_UF']} · {r['NM_MUNICIPIO']} · zona {r['NR_ZONA']} · local {r['NR_LOCAL_VOTACAO']} · "
                  f"{r['NR_TURNO']}º turno — {r['COLUNA']}: \"{_curto(r['ANTES'])}\" → \"{_curto(r['DEPOIS'])}\" "
                  f"(seções {_curto(r['SECOES'], 60)})")
    if not (d.celulas.height or d.criadas.height or d.extintas.height):
        print("\nNenhuma diferença no CSV entre as duas versões nas UFs pedidas.")


def diferencas(cache: Path, spec: v.DatasetSpec, pedidas: list[str], ufs: list[str], ano: int, limite: int,
               saida: Path | None) -> Path:
    """--diferencas: compara, imprime e grava a planilha. Devolve o caminho da planilha."""
    versoes = versoes_comparadas(cache, spec, pedidas)
    d = dc.comparar_zips(versoes[0].zip, versoes[1].zip, ufs)
    antes, depois = (_turnos(x, ano, ufs) for x in versoes)
    m = dc.mudancas_de_situacao(antes, depois)
    por_uf = dc.resumo_ufs(d, antes, depois)
    imprimir_diferencas(d, antes, depois, por_uf, m, versoes, ufs, ano, limite)
    consulta = {"cadastro de eleitorado": ano, "UFs": ", ".join(ufs),
                **{f"antes: {k}": x for k, x in versoes[0].para_consulta().items()},
                **{f"depois: {k}": x for k, x in versoes[1].para_consulta().items()},
                "linhas antes": d.linhas_antes, "linhas depois": d.linhas_depois,
                "células alteradas": d.celulas.height, "linhas alteradas": d.celulas.select(dc.CHAVE).n_unique(),
                "linhas criadas": d.criadas.height, "linhas extintas": d.extintas.height,
                "colunas novas": ", ".join(d.colunas_novas), "colunas removidas": ", ".join(d.colunas_removidas),
                "seções em local temporário no 2º turno (antes → depois)":
                    f"{int(por_uf['TEMPORARIAS_2T_ANTES'].sum())} → {int(por_uf['TEMPORARIAS_2T_DEPOIS'].sum())}",
                "seções que mudaram de situação ou de local no 2º turno": "" if m is None else m.height}
    abas = {"Resumo": dc.resumo_colunas(d), "UFs": por_uf, "Alterações": dc.alteracoes(d), "Células": d.celulas,
            "Criadas e extintas": pl.concat([d.criadas.with_columns(pl.lit("CRIADA").alias("MUDANCA")),
                                             d.extintas.with_columns(pl.lit("EXTINTA").alias("MUDANCA"))]),
            "Situações": dc.situacoes(antes, depois),
            "Mudou de situação": m if m is not None else pl.DataFrame({"AVISO": ["uma versão sem 2º turno"]})}
    destino = dc.para_planilha(abas, consulta, saida or destino_diferencas(ufs, ano, *versoes))
    print(f"\nPlanilha gravada em {destino}")
    return destino


def _ufs(pedidas: list[str]) -> list[str]:
    """"todas" → as 27 UFs; senão, as siglas pedidas em maiúsculas (sem validar: "BR"/"ZZ" também valem)."""
    return uf_mod.lista(pedidas) if [u.lower() for u in pedidas] == ["todas"] else [u.upper() for u in pedidas]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.uf and not (args.atualizar or args.versoes or args.diferencas is not None):
        parser.error("informe --uf (ou use --atualizar / --versoes / --diferencas)")
    if args.diferencas is not None and len(args.diferencas) > 2:
        parser.error("--diferencas aceita no máximo duas versões (a de antes e a de depois)")
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
        if args.diferencas is not None:
            diferencas(cache, spec, args.diferencas, lista or uf_mod.lista("todas"), args.ano, args.limite,
                       args.saida)
            return 0
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
