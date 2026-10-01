"""Eleitorado por local de votação (dataset "eleitorado-<ano>" do TSE), qualquer layout.

Uma linha por seção (principal ou agregada), já filtrada por UF e turno, e o resumo
por local. O eleitorado de um local é a soma de QT_ELEITOR_SECAO de todas as suas
seções, agregadas incluídas: elas não aparecem no arquivo de votação, mas os
eleitores continuam votando naquele local.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

import votos_por_local_votacao as v

logger = logging.getLogger("apuracao.eleitorado")

SECTION_KEY = ["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]

# Retângulos envolventes (lat_min, lat_max, lon_min, lon_max) para validar coordenadas.
BBOX_BRASIL = (-34.0, 5.5, -74.0, -28.5)
BBOX_UF = {"RJ": (-23.40, -20.70, -44.95, -40.90)}


# --------------------------------------------------------------------------
# Proveniência de ZIP colocado manualmente no cache
# --------------------------------------------------------------------------
def ensure_local_provenance(spec: v.DatasetSpec, cache_dir: Path) -> Path | None:
    """Grava `<zip>.proveniencia.json` para um ZIP que não veio do `download()`."""
    target = cache_dir / spec.zip_name
    prov = target.with_suffix(".proveniencia.json")
    if not target.exists() or prov.exists():
        return prov if prov.exists() else None

    sha = hashlib.sha512()
    with target.open("rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            sha.update(block)
    generated = _tse_generation_stamp(target, spec.uf_filter)
    meta = {
        "url": spec.url,
        "origem": "arquivo local (colocado no cache manualmente, não baixado por este código)",
        "registrado_em": datetime.now(timezone.utc).isoformat(),
        "arquivo_modificado_em": datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(),
        "geracao_tse": generated,
        "bytes": target.stat().st_size,
        "sha512": sha.hexdigest(),
    }
    prov.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    logger.info("proveniência registrada: %s", prov.name)
    return prov


def _tse_generation_stamp(zip_path: Path, uf: str) -> str | None:
    """DT_GERACAO + HH_GERACAO da primeira linha de dados do CSV da UF."""
    with zipfile.ZipFile(zip_path) as zf:
        member = v.pick_csv_member(zf, uf)
        with zf.open(member) as raw:
            txt = io.TextIOWrapper(raw, encoding="latin-1")
            header = [c.strip('"') for c in txt.readline().rstrip("\r\n").split(";")]
            first = [c.strip('"') for c in txt.readline().rstrip("\r\n").split(";")]
    row = dict(zip(header, first))
    if "DT_GERACAO" not in row:
        return None
    return f"{row['DT_GERACAO']} {row.get('HH_GERACAO', '')}".strip()


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------
def load_sections(year: int, uf: str, cache_dir: Path, sha: bool = False, turno: int = 1) -> pl.DataFrame:
    """Seções do eleitorado de um ano: uma linha por (município, zona, seção)."""
    spec = v.electorate_spec(year, uf)
    ensure_local_provenance(spec, cache_dir)
    lf = v.load_electorate(year, uf, cache_dir, sha)
    schema = lf.collect_schema()
    if "NR_TURNO" in schema:
        # o 2º turno repete (um subconjunto das) seções do 1º; basta o 1º para o cadastro
        lf = lf.filter(pl.col("NR_TURNO") == turno)
    df = lf.unique(subset=SECTION_KEY, keep="first", maintain_order=True).collect()
    for col, dtype in (("NR_LOCAL_VOTACAO_ORIGINAL", pl.Int64), ("NR_SECAO_PRINCIPAL", pl.Int64),
                       ("DS_SITU_LOCAL_VOTACAO", pl.String),
                       ("DS_TIPO_LOCAL", pl.String), ("DS_TIPO_SECAO_AGREGADA", pl.String),
                       ("NM_BAIRRO", pl.String), ("DS_ENDERECO", pl.String),
                       ("NR_LATITUDE", pl.Float64), ("NR_LONGITUDE", pl.Float64)):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=dtype).alias(col))
    return df.with_columns(
        pl.col("QT_ELEITOR_SECAO").fill_null(0),
        (pl.col("NR_LOCAL_VOTACAO_ORIGINAL").is_not_null()
         & (pl.col("NR_LOCAL_VOTACAO_ORIGINAL") != pl.col("NR_LOCAL_VOTACAO"))).alias("REMANEJADA"),
    )


def filter_area(df: pl.DataFrame, muni: int | None) -> pl.DataFrame:
    return df if muni is None else df.filter(pl.col("CD_MUNICIPIO") == muni)


# --------------------------------------------------------------------------
# Resumo por local
# --------------------------------------------------------------------------
def compact(value: str | None) -> str:
    """Chave de comparação: só letras e dígitos, sem acento ("R. X, 12" == "R X 12")."""
    return re.sub(r"[^A-Z0-9]", "", v.normalize_text(value))


def compact_expr(col: str) -> pl.Expr:
    return pl.col(col).map_elements(compact, return_dtype=pl.String)


def _mode(col: str) -> pl.Expr:
    """Valor mais frequente (não nulo) no grupo; empate resolvido pela ordem alfabética."""
    return pl.col(col).drop_nulls().mode().sort().first()


def places(sections: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por local (CD_MUNICIPIO, NR_ZONA, NR_LOCAL_VOTACAO)."""
    return (
        sections.group_by(v.LOCAL_KEY)
        .agg(
            pl.col("NM_MUNICIPIO").first(),
            _mode("NM_LOCAL_VOTACAO").alias("NM_LOCAL_VOTACAO"),
            _mode("DS_ENDERECO").alias("DS_ENDERECO"),
            _mode("NM_BAIRRO").alias("NM_BAIRRO"),
            pl.col("NR_LATITUDE").drop_nulls().first(),
            pl.col("NR_LONGITUDE").drop_nulls().first(),
            pl.col("QT_ELEITOR_SECAO").sum().alias("QT_ELEITORES"),
            pl.len().alias("N_SECOES"),
            pl.col("NR_SECAO").sort().cast(pl.String).str.join(",").alias("SECOES"),
            pl.col("NR_SECAO").filter(pl.col("NR_SECAO_PRINCIPAL").is_null())
            .sort().cast(pl.String).str.join(",").alias("SECOES_INSTALADAS"),
            (pl.col("DS_SITU_LOCAL_VOTACAO") == "BLOQUEADO").any().alias("BLOQUEADO"),
            (pl.col("DS_TIPO_LOCAL").str.to_uppercase().str.starts_with("TEMPOR")).any().alias("TEMPORARIO"),
            pl.col("REMANEJADA").sum().alias("N_REMANEJADAS"),
        )
        .with_columns(
            compact_expr("NM_LOCAL_VOTACAO").alias("_NOME_N"),
            compact_expr("DS_ENDERECO").alias("_END_N"),
            compact_expr("NM_BAIRRO").alias("_BAIRRO_N"),
        )
        .sort(v.LOCAL_KEY)
    )


def summary(sections: pl.DataFrame) -> dict[str, int]:
    pl_ = places(sections)
    return {
        "secoes": sections.height,
        "secoes_agregadas": sections.filter(pl.col("NR_SECAO_PRINCIPAL").is_not_null()).height,
        "secoes_remanejadas": int(sections["REMANEJADA"].sum()),
        "secoes_local_bloqueado": sections.filter(pl.col("DS_SITU_LOCAL_VOTACAO") == "BLOQUEADO").height,
        "eleitores": int(sections["QT_ELEITOR_SECAO"].sum()),
        "municipios": sections["CD_MUNICIPIO"].n_unique(),
        "zonas": sections.select("CD_MUNICIPIO", "NR_ZONA").unique().height,
        "locais": pl_.height,
        "locais_sem_coordenada": pl_.filter(pl.col("NR_LATITUDE").is_null()).height,
        "bairros_distintos": pl_["_BAIRRO_N"].n_unique(),
    }


# --------------------------------------------------------------------------
# Coordenadas
# --------------------------------------------------------------------------
def haversine_m(lat1: pl.Expr, lon1: pl.Expr, lat2: pl.Expr, lon2: pl.Expr) -> pl.Expr:
    """Distância em metros entre dois pontos (graus decimais)."""
    r = 6_371_000.0
    p1, p2 = lat1.radians(), lat2.radians()
    dphi, dlmb = (lat2 - lat1).radians(), (lon2 - lon1).radians()
    a = (dphi / 2).sin().pow(2) + p1.cos() * p2.cos() * (dlmb / 2).sin().pow(2)
    return 2 * r * a.sqrt().arcsin()


def inside_bbox(uf: str) -> pl.Expr:
    lat_min, lat_max, lon_min, lon_max = BBOX_UF.get(uf, BBOX_BRASIL)
    return pl.col("NR_LATITUDE").is_between(lat_min, lat_max) & pl.col("NR_LONGITUDE").is_between(lon_min, lon_max)


def geo_report(pl_: pl.DataFrame, uf: str) -> dict[str, float | int]:
    """Qualidade das coordenadas por local, para decidir se dá para mapear por ponto."""
    n = pl_.height
    with_coord = pl_.filter(pl.col("NR_LATITUDE").is_not_null() & pl.col("NR_LONGITUDE").is_not_null())
    inside = with_coord.filter(inside_bbox(uf)).height
    dup = (
        with_coord.group_by("NR_LATITUDE", "NR_LONGITUDE")
        .agg(pl.col("_END_N").n_unique().alias("n_end"), pl.len().alias("n"))
        .filter(pl.col("n_end") > 1)
    )
    return {
        "locais": n,
        "com_coordenada": with_coord.height,
        "pct_com_coordenada": round(100 * with_coord.height / n, 2) if n else math.nan,
        "dentro_do_retangulo_da_uf": inside,
        "fora_do_retangulo_da_uf": with_coord.height - inside,
        "pontos_compartilhados_por_enderecos_distintos": dup.height,
        "locais_nesses_pontos": int(dup["n"].sum()) if dup.height else 0,
    }
