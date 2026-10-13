"""Locais de votação de um bairro e as seções de cada local (cadastro de eleitorado do TSE).

Duas fontes de bairro:

- "cadastro": o NM_BAIRRO do cadastro do TSE (texto livre, comparado por `compact`);
- "ibge": o bairro da malha do IBGE/Censo 2022 que CONTÉM a coordenada do local
  (`bairros.locais_em_bairros`, o mesmo critério do mapa por bairro). Local sem coordenada fica de fora.

Sem I/O (exceto `para_planilha`): recebe as seções de `eleitorado.load_sections` (e a malha, na fonte "ibge").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

import votos_por_local_votacao as v
from apuracao import bairros as br
from apuracao import eleitorado as el

FONTES = ("cadastro", "ibge")


def _casa(col: str, bairro: str, contem: bool) -> pl.Expr:
    alvo = el.compact(bairro)
    return pl.col(col).str.contains(alvo, literal=True) if contem else pl.col(col) == alvo


def _com_bairro(locais: pl.DataFrame, fonte: str, geo: dict[str, Any] | None) -> pl.DataFrame:
    """Locais com a coluna BAIRRO (o nome na fonte escolhida) e _BAIRRO_BUSCA (compactado)."""
    if fonte == "cadastro":
        return locais.with_columns(pl.col("NM_BAIRRO").alias("BAIRRO"), pl.col("_BAIRRO_N").alias("_BAIRRO_BUSCA"))
    if fonte != "ibge":
        raise ValueError(f"fonte de bairro desconhecida: {fonte!r} (use {', '.join(FONTES)})")
    if geo is None:
        raise ValueError("a fonte 'ibge' precisa da malha de bairros")
    lb = br.locais_em_bairros(locais, geo).select(v.LOCAL_KEY + ["NM_BAIRRO_IBGE"])
    return (locais.join(lb, on=v.LOCAL_KEY, how="inner")
            .with_columns(pl.col("NM_BAIRRO_IBGE").alias("BAIRRO"),
                          el.compact_expr("NM_BAIRRO_IBGE").alias("_BAIRRO_BUSCA")))


def locais_do_bairro(secoes: pl.DataFrame, bairro: str, fonte: str = "cadastro", contem: bool = False,
                     geo: dict[str, Any] | None = None) -> pl.DataFrame:
    """Uma linha por local do bairro (resumo de `eleitorado.places` + BAIRRO), ordenada por município/zona/local.

    `contem`: o nome digitado basta estar contido no do bairro ("tijuca" acha também "Barra da Tijuca").
    """
    locais = _com_bairro(el.places(secoes), fonte, geo)
    return locais.filter(_casa("_BAIRRO_BUSCA", bairro, contem)).sort(["NM_MUNICIPIO"] + v.LOCAL_KEY)


def secoes_dos_locais(secoes: pl.DataFrame, locais: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por seção dos locais dados (agregadas incluídas, com a seção principal)."""
    return (
        secoes.join(locais.select(v.LOCAL_KEY + ["BAIRRO"]), on=v.LOCAL_KEY, how="inner")
        .select("NM_MUNICIPIO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO",
                "BAIRRO", "NR_SECAO",
                pl.when(pl.col("NR_SECAO_PRINCIPAL").is_null()).then(pl.lit("PRINCIPAL"))
                .otherwise(pl.lit("AGREGADA")).alias("TIPO_SECAO"),
                "NR_SECAO_PRINCIPAL", "QT_ELEITOR_SECAO")
        .sort(["NM_MUNICIPIO"] + v.LOCAL_KEY + ["NR_SECAO"])
    )


def sugestoes(secoes: pl.DataFrame, bairro: str, fonte: str = "cadastro", geo: dict[str, Any] | None = None,
              limite: int = 10) -> list[str]:
    """Nomes de bairro (na fonte escolhida) que contêm o texto digitado, ou que ele contém."""
    alvo = el.compact(bairro)
    nomes = (_com_bairro(el.places(secoes), fonte, geo)
             .filter(pl.col("BAIRRO").is_not_null())
             .group_by("_BAIRRO_BUSCA").agg(pl.col("BAIRRO").mode().sort().first(), pl.len().alias("n")))
    hits = nomes.filter(pl.col("_BAIRRO_BUSCA").str.contains(alvo, literal=True)
                        | (pl.lit(alvo).str.contains(pl.col("_BAIRRO_BUSCA"), literal=True)
                           & (pl.col("_BAIRRO_BUSCA").str.len_chars() >= 4)))
    return hits.sort("n", descending=True)["BAIRRO"].head(limite).to_list()


def rotulo_secao() -> pl.Expr:
    """"375" ou "375 (agregada à 109)"."""
    return (pl.when(pl.col("TIPO_SECAO") == "PRINCIPAL").then(pl.col("NR_SECAO").cast(pl.String))
            .otherwise(pl.format("{} (agregada à {})", "NR_SECAO", "NR_SECAO_PRINCIPAL")))


def tabela_locais(locais: pl.DataFrame, secoes: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por local, para a planilha: sem colunas internas e com a lista de seções rotulada."""
    listas = (secoes.with_columns(rotulo_secao().alias("_ROTULO"))
              .group_by(v.LOCAL_KEY, maintain_order=True).agg(pl.col("_ROTULO").str.join(", ").alias("SECOES")))
    return (locais.drop("SECOES").join(listas, on=v.LOCAL_KEY, how="left", maintain_order="left")
            .select("NM_MUNICIPIO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO",
                    "BAIRRO", "NR_LATITUDE", "NR_LONGITUDE", "N_SECOES", "QT_ELEITORES", "SECOES"))


def para_planilha(locais: pl.DataFrame, secoes: pl.DataFrame, consulta: dict[str, Any], destino: Path) -> Path:
    """.xlsx com as abas "Locais" (um por linha), "Seções" (uma por linha) e "Consulta" (parâmetros e totais)."""
    import xlsxwriter

    destino.parent.mkdir(parents=True, exist_ok=True)
    resumo = {**consulta, "locais": locais.height, "seções": secoes.height,
              "eleitores": int(secoes["QT_ELEITOR_SECAO"].sum())}
    abas = {"Locais": tabela_locais(locais, secoes), "Seções": secoes,
            "Consulta": pl.DataFrame({"ITEM": list(resumo), "VALOR": [str(x) for x in resumo.values()]})}
    tmp = destino.with_name(destino.name + ".tmp")
    with xlsxwriter.Workbook(str(tmp)) as wb:
        for nome, df in abas.items():
            df.write_excel(wb, worksheet=nome, autofit=True, freeze_panes=(1, 0))
    tmp.replace(destino)
    return destino
