"""Comparação dos locais de votação entre dois cadastros de eleitorado (ano-base × 2026).

O ano-base é, por padrão, o ano do resultado analisado (ex.: votos de 2022 comparados
com o cadastro de 2022 e o de 2026), e pode ser escolhido na CLI (--comparar-com).
Nomes de colunas, status e inconsistências trazem os dois anos (ex.: MUDANCA_2022_2026,
DESATIVADO_EM_2026, VALOR_2022).

Dois níveis:
  * seção  (CD_MUNICIPIO, NR_ZONA, NR_SECAO): em que local estava e em que local está;
  * local  (CD_MUNICIPIO, NR_ZONA, NR_LOCAL_VOTACAO): nome, endereço, coordenadas,
    seções que saíram/entraram.

NR_LOCAL_VOTACAO só é único dentro da zona; nomes e endereços são comparados por
`compact()` (só letras e dígitos, sem acento).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import polars as pl

import votos_por_local_votacao as v
from apuracao.eleitorado import SECTION_KEY, compact, haversine_m, inside_bbox

NEW_YEAR = 2026
MOVE_THRESHOLD_M = 150.0
ELECTORATE_JUMP_PCT = 50.0
COORD_JUMP_M = 5_000.0

MANTIDO = "MANTIDO"


def change_col(old: int, new: int = NEW_YEAR) -> str:
    return f"MUDANCA_{old}_{new}"


def desativado(new: int = NEW_YEAR) -> str:
    return f"DESATIVADO_EM_{new}"


def novo(new: int = NEW_YEAR) -> str:
    return f"NOVO_EM_{new}"


def inconsistency_columns(old: int, new: int = NEW_YEAR) -> list[str]:
    return ["TIPO", "CHAVE", f"VALOR_{old}", f"VALOR_{new}", "DETALHE"]


def _key(df: pl.DataFrame) -> pl.Expr:
    return pl.format("mun {} zona {} local {}", *[pl.col(c) for c in v.LOCAL_KEY])


# --------------------------------------------------------------------------
# Seções
# --------------------------------------------------------------------------
def compare_sections(sec_old: pl.DataFrame, sec_new: pl.DataFrame, old: int, new: int = NEW_YEAR) -> pl.DataFrame:
    """Uma linha por seção existente em algum dos anos, com o local em cada um."""
    lo, ln = f"LOCAL_{old}", f"LOCAL_{new}"
    a = sec_old.select(SECTION_KEY + [pl.col("NR_LOCAL_VOTACAO").alias(lo),
                                      pl.col("NM_LOCAL_VOTACAO").alias(f"NM_LOCAL_{old}")])
    b = sec_new.select(SECTION_KEY + [pl.col("NR_LOCAL_VOTACAO").alias(ln),
                                      pl.col("NM_LOCAL_VOTACAO").alias(f"NM_LOCAL_{new}"),
                                      "REMANEJADA", "NR_LOCAL_VOTACAO_ORIGINAL"])
    df = a.join(b, on=SECTION_KEY, how="full", coalesce=True).rechunk()
    status = (
        pl.when(pl.col(ln).is_null()).then(pl.lit(f"SECAO_EXTINTA_EM_{new}"))
        .when(pl.col(lo).is_null()).then(pl.lit(f"SECAO_NOVA_EM_{new}"))
        .when(pl.col(lo) != pl.col(ln)).then(pl.lit("MUDOU_DE_LOCAL"))
        .otherwise(pl.lit(MANTIDO))
    )
    return df.with_columns(
        status.alias("STATUS_SECAO"),
        pl.col("REMANEJADA").fill_null(False),
    ).sort(SECTION_KEY)


# --------------------------------------------------------------------------
# Locais
# --------------------------------------------------------------------------
_PLACE_COLS = ["NM_LOCAL_VOTACAO", "DS_ENDERECO", "NM_BAIRRO", "NR_LATITUDE", "NR_LONGITUDE",
               "QT_ELEITORES", "N_SECOES", "SECOES", "_NOME_N", "_END_N", "_BAIRRO_N"]


def compare_places(pl_old: pl.DataFrame, pl_new: pl.DataFrame, sections: pl.DataFrame,
                   old: int, new: int = NEW_YEAR) -> pl.DataFrame:
    """Uma linha por local existente em algum dos anos, com a lista de mudanças."""
    o, n = f"_{old}", f"_{new}"
    a = pl_old.select(v.LOCAL_KEY + ["NM_MUNICIPIO"] + [pl.col(c).alias(c + o) for c in _PLACE_COLS])
    b = pl_new.select(
        v.LOCAL_KEY + [pl.col("NM_MUNICIPIO").alias("_MUN_NEW")]
        + [pl.col(c).alias(c + n) for c in _PLACE_COLS]
        + ["BLOQUEADO", "TEMPORARIO", "N_REMANEJADAS"]
    )
    df = a.join(b, on=v.LOCAL_KEY, how="full", coalesce=True).rechunk().with_columns(
        pl.coalesce("NM_MUNICIPIO", "_MUN_NEW").alias("NM_MUNICIPIO")
    ).drop("_MUN_NEW")

    moved_out = _section_flow(sections, f"LOCAL{o}", f"LOCAL{n}", "SECOES_SAIRAM", outgoing=True)
    moved_in = _section_flow(sections, f"LOCAL{n}", f"LOCAL{o}", "SECOES_ENTRARAM", outgoing=False)
    df = (
        df.join(moved_out, on=v.LOCAL_KEY, how="left")
        .join(moved_in, on=v.LOCAL_KEY, how="left")
        .with_columns(
            haversine_m(pl.col("NR_LATITUDE" + o), pl.col("NR_LONGITUDE" + o),
                        pl.col("NR_LATITUDE" + n), pl.col("NR_LONGITUDE" + n)).round(0).alias("DISTANCIA_M"),
        )
    )

    only_old = pl.col("N_SECOES" + n).is_null()
    only_new = pl.col("N_SECOES" + o).is_null()
    both = ~only_old & ~only_new
    flags = [
        pl.when(only_old).then(pl.lit(desativado(new))),
        pl.when(only_new).then(pl.lit(novo(new))),
        pl.when(both & (pl.col("_NOME_N" + o) != pl.col("_NOME_N" + n))).then(pl.lit("RENOMEADO")),
        pl.when(both & (pl.col("_END_N" + o) != pl.col("_END_N" + n))).then(pl.lit("ENDERECO_ALTERADO")),
        pl.when(pl.col("DISTANCIA_M") > MOVE_THRESHOLD_M).then(pl.lit("DESLOCADO")),
        pl.when(both & pl.col("SECOES_SAIRAM").is_not_null()).then(pl.lit("SECOES_SAIRAM")),
        pl.when(both & pl.col("SECOES_ENTRARAM").is_not_null()).then(pl.lit("SECOES_ENTRARAM")),
        pl.when(pl.col("N_REMANEJADAS").fill_null(0) > 0).then(pl.lit(f"REMANEJAMENTO_{new}")),
        pl.when(pl.col("TEMPORARIO").fill_null(False)).then(pl.lit(f"TEMPORARIO_{new}")),
    ]
    col = change_col(old, new)
    mudanca = pl.concat_list(flags).list.drop_nulls().list.join(", ")
    return (
        df.with_columns(mudanca.alias(col))
        .with_columns(
            pl.when(pl.col(col) == "").then(pl.lit(MANTIDO)).otherwise(pl.col(col)).alias(col),
            pl.when(pl.col("BLOQUEADO").fill_null(False)).then(pl.lit("BLOQUEADO")).otherwise(
                pl.when(only_old).then(None).otherwise(pl.lit("ATIVO"))
            ).alias(f"SITUACAO_LOCAL{n}"),
            pl.when(only_old).then(None).otherwise(
                pl.format("{} — {}", pl.col("NM_LOCAL_VOTACAO" + n), pl.col("DS_ENDERECO" + n))
            ).alias(f"LOCAL{n}"),
        )
        .sort(v.LOCAL_KEY)
    )


def _section_flow(sections: pl.DataFrame, side: str, other: str, name: str, outgoing: bool) -> pl.DataFrame:
    """Seções que saíram do local (outgoing) ou entraram nele, com o local do outro ano."""
    moved = sections.filter(
        pl.col(side).is_not_null() & pl.col(other).is_not_null() & (pl.col(side) != pl.col(other))
    )
    arrow = pl.format("{}→local {}" if outgoing else "{}←local {}", pl.col("NR_SECAO"), pl.col(other))
    return (
        moved.with_columns(arrow.alias("_d"))
        .group_by(["CD_MUNICIPIO", "NR_ZONA", pl.col(side).alias("NR_LOCAL_VOTACAO")])
        .agg(pl.col("_d").sort().str.join("; ").alias(name))
    )


# --------------------------------------------------------------------------
# Inconsistências
# --------------------------------------------------------------------------
def inconsistencies(cmp: pl.DataFrame, pl_old: pl.DataFrame, pl_new: pl.DataFrame, uf: str,
                    old: int, new: int = NEW_YEAR) -> pl.DataFrame:
    """Problemas de cadastro entre os dois anos (não são mudanças legítimas)."""
    o, n = f"_{old}", f"_{new}"
    vo, vn = f"VALOR_{old}", f"VALOR_{new}"
    parts: list[pl.DataFrame] = []
    key = _key(cmp)

    for year, pl_, other in ((old, pl_old, vn), (new, pl_new, vo)):
        k = _key(pl_)
        no_coord = pl_.filter(pl.col("NR_LATITUDE").is_null() | pl.col("NR_LONGITUDE").is_null())
        parts.append(_rows(no_coord, "COORDENADA_AUSENTE", k, year, pl.col("NM_LOCAL_VOTACAO"),
                           pl.lit(f"lat/lon ausente ou -1 no cadastro de {year}"), other))
        outside = pl_.filter(pl.col("NR_LATITUDE").is_not_null() & ~inside_bbox(uf))
        parts.append(_rows(outside, "COORDENADA_FORA_DA_UF", k, year,
                           pl.format("{}, {}", pl.col("NR_LATITUDE"), pl.col("NR_LONGITUDE")),
                           pl.format("{} fora do retângulo de {}", pl.col("NM_LOCAL_VOTACAO"), pl.lit(uf)), other))
        shared = (
            pl_.filter(pl.col("NR_LATITUDE").is_not_null())
            .with_columns(pl.col("_END_N").n_unique().over("NR_LATITUDE", "NR_LONGITUDE").alias("_n"),
                          pl.len().over("NR_LATITUDE", "NR_LONGITUDE").alias("_locais"))
            .filter(pl.col("_n") > 1)
        )
        parts.append(_rows(shared, "COORDENADA_COMPARTILHADA", k, year,
                           pl.format("{}, {}", pl.col("NR_LATITUDE"), pl.col("NR_LONGITUDE")),
                           pl.format("{} locais com endereços diferentes no mesmo ponto; este: {}",
                                     pl.col("_locais"), pl.col("DS_ENDERECO")), other))

    both = cmp.filter(pl.col("N_SECOES" + o).is_not_null() & pl.col("N_SECOES" + n).is_not_null())
    bairro = both.filter(pl.col("_BAIRRO_N" + o) != pl.col("_BAIRRO_N" + n))
    parts.append(bairro.select(pl.lit("BAIRRO_DIVERGENTE").alias("TIPO"), key.alias("CHAVE"),
                               pl.col("NM_BAIRRO" + o).alias(vo), pl.col("NM_BAIRRO" + n).alias(vn),
                               pl.col("NM_LOCAL_VOTACAO" + n).alias("DETALHE")))

    var = both.with_columns(
        (100 * (pl.col("QT_ELEITORES" + n) - pl.col("QT_ELEITORES" + o)) / pl.col("QT_ELEITORES" + o)).alias("_v")
    ).filter(pl.col("_v").abs() > ELECTORATE_JUMP_PCT)
    parts.append(var.select(pl.lit("VARIACAO_ELEITORADO").alias("TIPO"), key.alias("CHAVE"),
                            pl.col("QT_ELEITORES" + o).cast(pl.String).alias(vo),
                            pl.col("QT_ELEITORES" + n).cast(pl.String).alias(vn),
                            pl.format("{}% — {}", pl.col("_v").round(1), pl.col("NM_LOCAL_VOTACAO" + n)).alias("DETALHE")))

    jump = both.filter(pl.col("DISTANCIA_M") > COORD_JUMP_M)
    parts.append(jump.select(pl.lit("COORDENADA_SALTO_5KM").alias("TIPO"), key.alias("CHAVE"),
                             pl.format("{}, {}", pl.col("NR_LATITUDE" + o), pl.col("NR_LONGITUDE" + o)).alias(vo),
                             pl.format("{}, {}", pl.col("NR_LATITUDE" + n), pl.col("NR_LONGITUDE" + n)).alias(vn),
                             pl.format("{} m com a mesma chave — provável erro de geocodificação; {}",
                                       pl.col("DISTANCIA_M"), pl.col("NM_LOCAL_VOTACAO" + n)).alias("DETALHE")))

    parts.append(_renumbering(cmp, old, new))
    parts.append(_zones(pl_old, pl_new, old, new))
    cols = inconsistency_columns(old, new)
    return pl.concat([p.select(cols).cast(pl.String) for p in parts], how="vertical").sort("TIPO", "CHAVE")


def _rows(df: pl.DataFrame, tipo: str, key: pl.Expr, year: int, value: pl.Expr, detail: pl.Expr,
          other: str) -> pl.DataFrame:
    return df.select(pl.lit(tipo).alias("TIPO"), key.alias("CHAVE"), value.cast(pl.String).alias(f"VALOR_{year}"),
                     pl.lit(None, dtype=pl.String).alias(other), detail.alias("DETALHE"))


def _renumbering(cmp: pl.DataFrame, old: int, new: int) -> pl.DataFrame:
    """Local desativado e local novo com o mesmo nome no mesmo município: provável renumeração."""
    col = change_col(old, new)
    gone = cmp.filter(pl.col(col).str.starts_with(desativado(new))).select(
        "CD_MUNICIPIO", pl.col(f"_NOME_N_{old}").alias("_NOME"), pl.col("NR_ZONA").alias("ZO"),
        pl.col("NR_LOCAL_VOTACAO").alias("LO"), pl.col(f"NM_LOCAL_VOTACAO_{old}").alias("NOME"))
    fresh = cmp.filter(pl.col(col).str.starts_with(novo(new))).select(
        "CD_MUNICIPIO", pl.col(f"_NOME_N_{new}").alias("_NOME"), pl.col("NR_ZONA").alias("ZN"),
        pl.col("NR_LOCAL_VOTACAO").alias("LN"))
    hits = gone.join(fresh, on=["CD_MUNICIPIO", "_NOME"], how="inner")
    return hits.select(
        pl.lit("RENUMERACAO_PROVAVEL").alias("TIPO"),
        pl.format("mun {} {}", pl.col("CD_MUNICIPIO"), pl.col("NOME")).alias("CHAVE"),
        pl.format("zona {} local {}", pl.col("ZO"), pl.col("LO")).alias(f"VALOR_{old}"),
        pl.format("zona {} local {}", pl.col("ZN"), pl.col("LN")).alias(f"VALOR_{new}"),
        pl.lit("mesmo nome, chave diferente: tratado como desativado + novo").alias("DETALHE"),
    )


def _zones(pl_old: pl.DataFrame, pl_new: pl.DataFrame, old: int, new: int) -> pl.DataFrame:
    z_old = pl_old.group_by("CD_MUNICIPIO", "NR_ZONA").agg(pl.col("QT_ELEITORES").sum().alias("EO"))
    z_new = pl_new.group_by("CD_MUNICIPIO", "NR_ZONA").agg(pl.col("QT_ELEITORES").sum().alias("EN"))
    z = z_old.join(z_new, on=["CD_MUNICIPIO", "NR_ZONA"], how="full", coalesce=True).rechunk().filter(
        pl.col("EO").is_null() | pl.col("EN").is_null()
    )
    return z.select(
        pl.lit("ZONA_EM_UM_SO_ANO").alias("TIPO"),
        pl.format("mun {} zona {}", pl.col("CD_MUNICIPIO"), pl.col("NR_ZONA")).alias("CHAVE"),
        pl.col("EO").cast(pl.String).alias(f"VALOR_{old}"), pl.col("EN").cast(pl.String).alias(f"VALOR_{new}"),
        pl.lit("eleitorado da zona; nulo = zona inexistente no ano").alias("DETALHE"),
    )


def missing_from_register(vote_places: pl.DataFrame, register: pl.DataFrame, year: int,
                          old: int, new: int = NEW_YEAR) -> pl.DataFrame:
    """Locais que receberam votos mas não constam do cadastro de eleitorado do mesmo ano."""
    miss = vote_places.join(register.select(v.LOCAL_KEY), on=v.LOCAL_KEY, how="anti")
    none = pl.lit(None, dtype=pl.String)
    return miss.select(
        pl.lit("LOCAL_SEM_CADASTRO").alias("TIPO"), _key(miss).alias("CHAVE"),
        none.alias(f"VALOR_{old}"), none.alias(f"VALOR_{new}"),
        pl.format("{} — há votos em {} mas o local não está no eleitorado de {}",
                  pl.col("NM_LOCAL_VOTACAO"), pl.lit(year), pl.lit(year)).alias("DETALHE"),
    ).cast(pl.String)


# --------------------------------------------------------------------------
# Conferência com a lista de locais do TRE-RJ (JSON sem nº do local)
# --------------------------------------------------------------------------
def load_tre_places(path: Path) -> pl.DataFrame:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return pl.DataFrame(
        {
            "NR_ZONA": [int(r["ZONA_ELEITORAL"]) for r in rows],
            "NM_LOCAL_TRE": [r["NOME_LOCAL"] for r in rows],
            "_MUN_N": [v.normalize_text(r["MUNICIPIO_LOCAL"]) for r in rows],
            "_NOME_N": [compact(r["NOME_LOCAL"]) for r in rows],
            "SECOES_TRE": [_sorted_sections(re.findall(r"\d+", r["SECOES_INSTALADAS"] or "")) for r in rows],
        },
        schema_overrides={"NR_ZONA": pl.Int64},
    )


def _sorted_sections(numbers: list[str]) -> str:
    return ",".join(str(n) for n in sorted({int(x) for x in numbers}))


def compare_with_tre(pl_new: pl.DataFrame, tre: pl.DataFrame, old: int, new: int = NEW_YEAR) -> pl.DataFrame:
    """Confere o cadastro 2026 com a lista de locais publicada pelo TRE.

    O TRE não traz o nº do local e junta num só item os locais do TSE que têm o mesmo
    nome na mesma zona (mesmo prédio, números de local diferentes). Por isso o casamento
    é por (município, zona, nome compacto) e compara a UNIÃO das seções — todas, as
    agregadas inclusive, como o TRE lista. `old` só define o nome da coluna VALOR_<old>.
    """
    ours = (
        pl_new.with_columns(
            pl.col("NM_MUNICIPIO").map_elements(v.normalize_text, return_dtype=pl.String).alias("_MUN_N")
        )
        .group_by("_MUN_N", "NR_ZONA", "_NOME_N")
        .agg(
            pl.col("CD_MUNICIPIO").first(),
            pl.col("NM_LOCAL_VOTACAO").first(),
            pl.col("NR_LOCAL_VOTACAO").sort().cast(pl.String).str.join(",").alias("LOCAIS"),
            pl.col("SECOES").str.join(","),
        )
        .with_columns(pl.col("SECOES").map_elements(lambda s: _sorted_sections(s.split(",")),
                                                    return_dtype=pl.String))
    )
    tre = (
        tre.filter(pl.col("_MUN_N").is_in(ours["_MUN_N"].unique().to_list()))
        .group_by("_MUN_N", "NR_ZONA", "_NOME_N")  # o TRE também repete o mesmo local em itens separados
        .agg(pl.col("NM_LOCAL_TRE").first(), pl.col("SECOES_TRE").str.join(","))
        .with_columns(pl.col("SECOES_TRE").map_elements(lambda s: _sorted_sections(s.split(",")),
                                                        return_dtype=pl.String))
    )
    # rechunk: pl.format sobre o full join fragmentado dispara panic no Polars 1.44
    j = ours.join(tre, on=["_MUN_N", "NR_ZONA", "_NOME_N"], how="full", coalesce=True).rechunk()
    key = pl.format("mun {} zona {} local {}", pl.col("CD_MUNICIPIO"), pl.col("NR_ZONA"), pl.col("LOCAIS"))
    only_ours = j.filter(pl.col("NM_LOCAL_TRE").is_null())
    only_tre = j.filter(pl.col("LOCAIS").is_null())
    both = j.filter(pl.col("NM_LOCAL_TRE").is_not_null() & pl.col("LOCAIS").is_not_null()
                    & (pl.col("SECOES") != pl.col("SECOES_TRE")))
    none = pl.lit(None, dtype=pl.String)
    vo, vn = f"VALOR_{old}", f"VALOR_{new}"
    out = [
        only_ours.select(pl.lit(f"LOCAL_{new}_AUSENTE_NA_LISTA_TRE").alias("TIPO"), key.alias("CHAVE"),
                         none.alias(vo), pl.col("NM_LOCAL_VOTACAO").alias(vn),
                         pl.lit("nome não encontrado na lista do TRE para a mesma zona (pode ser só grafia)").alias("DETALHE")),
        only_tre.select(pl.lit(f"LOCAL_TRE_AUSENTE_NO_CADASTRO_{new}").alias("TIPO"),
                        pl.format("{} zona {}", pl.col("_MUN_N"), pl.col("NR_ZONA")).alias("CHAVE"),
                        none.alias(vo), pl.col("NM_LOCAL_TRE").alias(vn),
                        pl.format("seções na lista do TRE: {}", pl.col("SECOES_TRE")).alias("DETALHE")),
        both.select(pl.lit("SECOES_DIVERGEM_DA_LISTA_TRE").alias("TIPO"), key.alias("CHAVE"),
                    none.alias(vo), pl.col("SECOES").alias(vn),
                    pl.format("{} — lista do TRE: {}", pl.col("NM_LOCAL_VOTACAO"), pl.col("SECOES_TRE")).alias("DETALHE")),
    ]
    return pl.concat([o.cast(pl.String) for o in out], how="vertical")
