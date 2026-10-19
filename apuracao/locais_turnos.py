"""Local de votação de cada seção no 1º × no 2º turno, pelo cadastro de eleitorado do TSE (rodada 72).

O cadastro (`eleitorado_local_votacao_<ano>`) traz cada seção uma vez por turno (`NR_TURNO`), com o local onde
ela vota e o local ORIGINAL — o cadastrado: quando ele está interditado ou indisponível no dia, o TRE manda a
seção para um local temporário (leiame do TSE). As duas linhas da seção são casadas pela chave UF + município +
zona + seção (o nº do local e o da seção só valem dentro da zona) e cada seção com diferença recebe uma situação:

  VOLTA_AO_ORIGINAL   local temporário no 1º turno; no 2º, de volta ao local cadastrado
  TEMPORARIO_NO_2T    local cadastrado no 1º turno; local temporário no 2º
  OUTRO_TEMPORARIO    local temporário nos dois turnos, em lugares diferentes
  OUTRO_LOCAL         local diferente sem ser pelo local temporário (o cadastro mudou, ou o ano não traz o original)
  OUTRO_PREDIO        mesmo nº de local, mas outro nome E outro endereço: provavelmente outro prédio — confira
  NOME_OU_ENDERECO    mesmo nº de local, só o nome ou só o endereço diferente: o mesmo prédio, texto corrigido
  AGREGACAO           mesmo local; a seção passou a ser agregada a outra, ou deixou de ser
  SO_NO_2T            seção que só existe no 2º turno

O nº do local não identifica o prédio (o TSE reaproveita o nº; RJ, cadastro de 16/10/2026: o local 1279 da zona 156
de Nova Iguaçu é o CIEP 351 na Estrada Santa Bárbara no 1º turno e o Colégio Estadual Barão de Tinguá na Rua Gisela no
2º), e a coordenada também não (o TSE a repete no 2º turno). Por isso vale a regra de `abstencao_locais`, sem a parte
da distância: mesmo prédio = mesmo nome OU mesmo endereço (`compact`: pontuação e acento não contam).

Seção só no 1º turno não é mudança (o município pode não ter 2º turno, como na eleição municipal): entra só na
contagem. O cadastro diz onde a seção DEVE votar; onde ela votou sai nos microdados de votação do 2º turno.

Sem I/O (exceto `para_planilha`): recebe as seções de `eleitorado.load_sections(..., turno=1)` e `(..., turno=2)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from apuracao import eleitorado as el

CHAVE = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
SITUACOES: dict[str, str] = {
    "VOLTA_AO_ORIGINAL": "local temporário no 1º turno; no 2º, de volta ao local cadastrado",
    "TEMPORARIO_NO_2T": "local cadastrado no 1º turno; local temporário no 2º",
    "OUTRO_TEMPORARIO": "local temporário nos dois turnos, em lugares diferentes",
    "OUTRO_LOCAL": "local diferente sem ser pelo local temporário (o cadastro mudou, ou o ano não traz o original)",
    "OUTRO_PREDIO": "mesmo nº de local, mas outro nome e outro endereço: provavelmente outro prédio (confira)",
    "NOME_OU_ENDERECO": "mesmo nº de local, só o nome ou só o endereço diferente (o mesmo prédio)",
    "AGREGACAO": "mesmo local; a seção passou a ser agregada a outra, ou deixou de ser",
    "SO_NO_2T": "seção que só existe no 2º turno",
}
MUDA_DE_LOCAL = ("VOLTA_AO_ORIGINAL", "TEMPORARIO_NO_2T", "OUTRO_TEMPORARIO", "OUTRO_LOCAL", "OUTRO_PREDIO")

# colunas de `eleitorado.load_sections` usadas de cada turno (as ausentes num layout antigo entram nulas)
_DO_TURNO: dict[str, type[pl.DataType]] = {
    "NM_MUNICIPIO": pl.String, "NR_LOCAL_VOTACAO": pl.Int64, "NM_LOCAL_VOTACAO": pl.String,
    "DS_ENDERECO": pl.String, "NM_BAIRRO": pl.String, "NR_LATITUDE": pl.Float64, "NR_LONGITUDE": pl.Float64,
    "NR_LOCAL_VOTACAO_ORIGINAL": pl.Int64, "NM_LOCAL_VOTACAO_ORIGINAL": pl.String,
    "DS_ENDERECO_LOCVT_ORIGINAL": pl.String, "NR_SECAO_PRINCIPAL": pl.Int64, "QT_ELEITOR_SECAO": pl.Int64,
}
_ORIGINAL = ("NR_LOCAL_VOTACAO_ORIGINAL", "NM_LOCAL_VOTACAO_ORIGINAL", "DS_ENDERECO_LOCVT_ORIGINAL")


@dataclass(frozen=True)
class Comparacao:
    """`secoes`: uma linha por seção com diferença entre os turnos (coluna SITUACAO); as contagens são do todo."""

    secoes: pl.DataFrame
    nos_dois_turnos: int
    so_no_1t: int
    eleitores_2t: int


def _do_turno(secoes: pl.DataFrame, sufixo: str) -> pl.DataFrame:
    faltam = [pl.lit(None, dtype=t).alias(c) for c, t in _DO_TURNO.items() if c not in secoes.columns]
    if "SG_UF" not in secoes.columns:
        faltam.append(pl.lit("").alias("SG_UF"))
    return (secoes.with_columns(faltam).select(CHAVE + list(_DO_TURNO))
            .unique(subset=CHAVE, keep="first", maintain_order=True)
            .rename({c: f"{c}_{sufixo}" for c in _DO_TURNO})
            .with_columns(pl.lit(True).alias(f"_EM_{sufixo}")))


def _col(nome: str, turno: str) -> pl.Expr:
    return pl.col(f"{nome}_{turno}")


def _situacao_do_local() -> pl.Expr:
    """Situação pelo nº do local (e pelo local original de cada turno); nula se o nº não mudou."""
    nr1, nr2 = _col("NR_LOCAL_VOTACAO", "1T"), _col("NR_LOCAL_VOTACAO", "2T")
    or1, or2 = _col("NR_LOCAL_VOTACAO_ORIGINAL", "1T"), _col("NR_LOCAL_VOTACAO_ORIGINAL", "2T")
    temp1 = or1.is_not_null() & (or1 != nr1)
    temp2 = or2.is_not_null() & (or2 != nr2)
    em1, em2 = pl.col("_EM_1T").fill_null(False), pl.col("_EM_2T").fill_null(False)
    return (
        pl.when(~em1).then(pl.lit("SO_NO_2T"))
        .when(~em2 | (nr1 == nr2)).then(pl.lit(None, dtype=pl.String))
        .when(temp1 & (nr2 == pl.coalesce(or2, or1))).then(pl.lit("VOLTA_AO_ORIGINAL"))
        .when(temp2 & (nr1 == pl.coalesce(or1, or2))).then(pl.lit("TEMPORARIO_NO_2T"))
        .when(temp1 & temp2).then(pl.lit("OUTRO_TEMPORARIO"))
        .otherwise(pl.lit("OUTRO_LOCAL"))
    )


def _textos_mudaram(df: pl.DataFrame) -> pl.DataFrame:
    """Colunas _NOME e _END: o nome / o endereço do local diferem entre os turnos, por `compact` — calculado só
    nas linhas em que o texto cru difere (o `compact` é Python, linha a linha)."""
    pares = {"_NOME": ("NM_LOCAL_VOTACAO_1T", "NM_LOCAL_VOTACAO_2T"), "_END": ("DS_ENDERECO_1T", "DS_ENDERECO_2T")}
    cru = pl.any_horizontal([pl.col(a).ne_missing(pl.col(b)) for a, b in pares.values()])
    candidatas = df.with_row_index("_I").filter(cru)
    indice = pl.Series("_I", range(df.height), dtype=pl.Int64)
    saida = {}
    for nome, (a, b) in pares.items():
        mudou = candidatas.filter(el.compact_expr(a).fill_null("") != el.compact_expr(b).fill_null(""))["_I"]
        saida[nome] = indice.is_in(mudou.cast(pl.Int64).implode())
    return pl.DataFrame(saida)


def comparar(turno1: pl.DataFrame, turno2: pl.DataFrame) -> Comparacao:
    """Casa as seções dos dois turnos e classifica as que mudaram (ver o topo do módulo).

    Args:
        turno1: seções do 1º turno (`eleitorado.load_sections(..., turno=1)`), de uma ou várias UFs.
        turno2: seções do 2º turno, idem.

    Returns:
        `Comparacao` com as seções que mudaram (ordenadas por UF, município, zona e seção) e as contagens.
    """
    j = (_do_turno(turno1, "1T").join(_do_turno(turno2, "2T"), on=CHAVE, how="full", coalesce=True)
         .rechunk()  # full join + pl.format/expressões dá panic no Polars 1.44 sem consolidar (CLAUDE.md)
         .with_columns(_situacao_do_local().alias("SITUACAO")))
    nos_dois = pl.col("_EM_1T").fill_null(False) & pl.col("_EM_2T").fill_null(False)
    j = j.hstack(_textos_mudaram(j))
    j = j.with_columns(
        pl.when(pl.col("SITUACAO").is_not_null() | ~nos_dois).then(pl.col("SITUACAO"))
        .when(pl.col("_NOME") & pl.col("_END")).then(pl.lit("OUTRO_PREDIO"))
        .when(pl.col("_NOME") | pl.col("_END")).then(pl.lit("NOME_OU_ENDERECO"))
        .when(_col("NR_SECAO_PRINCIPAL", "1T").ne_missing(_col("NR_SECAO_PRINCIPAL", "2T"))).then(pl.lit("AGREGACAO"))
        .otherwise(pl.col("SITUACAO")).alias("SITUACAO"))
    contagens = j.select(nos_dois.sum().alias("dois"), (~pl.col("_EM_2T").fill_null(False)).sum().alias("so1"),
                         _col("QT_ELEITOR_SECAO", "2T").fill_null(0).sum().alias("el2")).row(0)
    original = {c: pl.coalesce(_col(c, "2T"), _col(c, "1T")).alias(c) for c in _ORIGINAL}
    secoes = (
        j.filter(pl.col("SITUACAO").is_not_null())
        .select(
            "SG_UF", pl.coalesce(_col("NM_MUNICIPIO", "2T"), _col("NM_MUNICIPIO", "1T")).alias("NM_MUNICIPIO"),
            "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO",
            pl.when(_col("NR_SECAO_PRINCIPAL", "2T").is_null()).then(pl.lit("PRINCIPAL"))
            .otherwise(pl.lit("AGREGADA")).alias("TIPO_SECAO_2T"),
            _col("NR_SECAO_PRINCIPAL", "1T"), _col("NR_SECAO_PRINCIPAL", "2T"),
            pl.coalesce(_col("QT_ELEITOR_SECAO", "2T"), _col("QT_ELEITOR_SECAO", "1T")).alias("QT_ELEITOR_SECAO"),
            "SITUACAO",
            *[_col(c, t) for t in ("1T", "2T") for c in ("NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO",
                                                          "NM_BAIRRO")],
            *original.values(),
            el.haversine_m(_col("NR_LATITUDE", "1T"), _col("NR_LONGITUDE", "1T"),
                           _col("NR_LATITUDE", "2T"), _col("NR_LONGITUDE", "2T")).round(0).cast(pl.Int64)
            .alias("DISTANCIA_M"),
        )
        .sort(["SG_UF", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"])
    )
    return Comparacao(secoes=secoes, nos_dois_turnos=int(contagens[0]), so_no_1t=int(contagens[1]),
                      eleitores_2t=int(contagens[2]))


def resumo(c: Comparacao) -> pl.DataFrame:
    """Uma linha por situação (todas, com zero onde não houve): seções, eleitores e locais do 2º turno."""
    por = (c.secoes.group_by("SITUACAO")
           .agg(pl.len().alias("SECOES"), pl.col("QT_ELEITOR_SECAO").fill_null(0).sum().alias("ELEITORES"),
                pl.struct("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO_2T").n_unique()
                .alias("LOCAIS_NO_2T")))
    todas = pl.DataFrame({"SITUACAO": list(SITUACOES), "DESCRICAO": list(SITUACOES.values())})
    return (todas.join(por, on="SITUACAO", how="left", maintain_order="left")
            .with_columns(pl.col("SECOES", "LOCAIS_NO_2T").fill_null(0).cast(pl.Int64),
                          pl.col("ELEITORES").fill_null(0).cast(pl.Int64)))


def locais(c: Comparacao) -> pl.DataFrame:
    """Uma linha por par (local no 1º turno → local no 2º turno) e situação, com as seções e os eleitores."""
    chave = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "SITUACAO", "NR_LOCAL_VOTACAO_1T", "NR_LOCAL_VOTACAO_2T"]
    return (
        c.secoes.sort("NR_SECAO")
        .group_by(chave, maintain_order=True)
        .agg(pl.col("NM_MUNICIPIO").first(),
             *[pl.col(f"{n}_{t}").first() for t in ("1T", "2T") for n in ("NM_LOCAL_VOTACAO", "DS_ENDERECO")],
             pl.len().alias("N_SECOES"), pl.col("QT_ELEITOR_SECAO").fill_null(0).sum().alias("QT_ELEITORES"),
             pl.col("NR_SECAO").cast(pl.String).str.join(", ").alias("SECOES"),
             pl.col("DISTANCIA_M").max())
        .select("SG_UF", "NM_MUNICIPIO", "CD_MUNICIPIO", "NR_ZONA", "SITUACAO",
                "NR_LOCAL_VOTACAO_1T", "NM_LOCAL_VOTACAO_1T", "DS_ENDERECO_1T",
                "NR_LOCAL_VOTACAO_2T", "NM_LOCAL_VOTACAO_2T", "DS_ENDERECO_2T",
                "DISTANCIA_M", "N_SECOES", "QT_ELEITORES", "SECOES")
        .sort(["SG_UF", "NM_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO_1T", "NR_LOCAL_VOTACAO_2T"], nulls_last=True)
    )


def para_planilha(c: Comparacao, consulta: dict[str, Any], destino: Path) -> Path:
    """.xlsx com as abas "Resumo" (por situação), "Locais" (pares de locais), "Seções" e "Consulta" (parâmetros,
    a versão do cadastro usada e as contagens). Gravação atômica."""
    import xlsxwriter

    destino.parent.mkdir(parents=True, exist_ok=True)
    itens = {**consulta, "seções nos dois turnos": c.nos_dois_turnos, "seções só no 1º turno": c.so_no_1t,
             "eleitores no 2º turno": c.eleitores_2t, "seções com diferença": c.secoes.height}
    abas = {"Resumo": resumo(c), "Locais": locais(c), "Seções": c.secoes,
            "Consulta": pl.DataFrame({"ITEM": list(itens), "VALOR": [str(x) for x in itens.values()]})}
    tmp = destino.with_name(destino.name + ".tmp")
    with xlsxwriter.Workbook(str(tmp)) as wb:
        for nome, df in abas.items():
            df.write_excel(wb, worksheet=nome, autofit=True, freeze_panes=(1, 0))
    tmp.replace(destino)
    return destino
