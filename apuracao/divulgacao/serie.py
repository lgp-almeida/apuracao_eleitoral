"""Série temporal da apuração: % dos válidos ao longo da totalização (UF e Brasil).

O coletor acrescenta, a cada totalização nova de uma abrangência UF/BR, uma linha por
candidato (cargos majoritários) ou por partido (proporcionais — são milhares de
candidatos) em <destino>/historico_serie.parquet. O gráfico do painel usa como eixo x
o % de seções totalizadas no momento e como eixo y o % dos válidos.

`reconstruir` refaz a série a partir dos JSON brutos já guardados em raw/ (o coletor
guarda cada versão de cada arquivo), para dados coletados antes desta série existir.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from pathlib import Path
from typing import Any

import polars as pl

from apuracao.divulgacao import modelo as m

logger = logging.getLogger("apuracao.divulgacao")

ARQUIVO = "historico_serie.parquet"
PROPORCIONAIS = (6, 7, 8)
CHAVE_PONTO = ["ELEICAO", "CARGO", "ABRANGENCIA", "UF", "DT_TOTALIZACAO"]
SCHEMA = {
    "ELEICAO": pl.Int64, "CARGO": pl.Int64, "ABRANGENCIA": pl.String, "UF": pl.String,
    "DT_TOTALIZACAO": pl.Datetime, "PCT_SECOES_TOTALIZADAS": pl.Float64, "TIPO": pl.String,
    "CHAVE": pl.String, "NOME": pl.String, "PARTIDO": pl.String, "VOTOS": pl.Int64, "PCT_VALIDOS": pl.Float64,
}
_ARQUIVO_UF = re.compile(r"^(br|[a-z]{2})-c\d{4}-e\d{6}-u$")  # EA20 da UF ou do Brasil (não municipal)


def linhas(totais: pl.DataFrame, candidatos: pl.DataFrame, partidos: pl.DataFrame) -> pl.DataFrame:
    """Linhas da série para as abrangências uf/br presentes nas tabelas."""
    tot = totais.filter(pl.col("ABRANGENCIA").is_in(["uf", "br"])).select(
        ["ELEICAO", "CARGO", "ABRANGENCIA", "UF", "DT_TOTALIZACAO", "PCT_SECOES_TOTALIZADAS", "VALIDOS"])
    chave = ["ELEICAO", "CARGO", "ABRANGENCIA", "UF"]
    cand = (candidatos.filter(pl.col("ABRANGENCIA").is_in(["uf", "br"]) & ~pl.col("CARGO").is_in(PROPORCIONAIS))
            .join(tot, on=chave, how="inner")
            .select(CHAVE_PONTO + ["PCT_SECOES_TOTALIZADAS", pl.lit("candidato").alias("TIPO"),
                                   pl.col("NUMERO").cast(pl.String).alias("CHAVE"), pl.col("NOME_URNA").alias("NOME"),
                                   "PARTIDO", "VOTOS", "PCT_VALIDOS"]))
    part = (partidos.filter(pl.col("ABRANGENCIA").is_in(["uf", "br"]) & pl.col("CARGO").is_in(PROPORCIONAIS))
            .group_by(chave + ["PARTIDO"]).agg(pl.col("VOTOS_TOTAL").sum().alias("VOTOS"))
            .join(tot, on=chave, how="inner")
            .select(CHAVE_PONTO + ["PCT_SECOES_TOTALIZADAS", pl.lit("partido").alias("TIPO"),
                                   pl.col("PARTIDO").alias("CHAVE"), pl.col("PARTIDO").alias("NOME"), "PARTIDO", "VOTOS",
                                   pl.when(pl.col("VALIDOS") > 0).then(100 * pl.col("VOTOS") / pl.col("VALIDOS"))
                                   .otherwise(None).alias("PCT_VALIDOS")]))
    return pl.concat([cand, part], how="diagonal_relaxed").select([pl.col(c).cast(t) for c, t in SCHEMA.items()])


def acrescentar(path: Path, novas: pl.DataFrame) -> None:
    """Junta ao histórico sem duplicar (um ponto = abrangência + hora da totalização)."""
    if novas.is_empty():
        return
    if path.exists():
        novas = pl.concat([pl.read_parquet(path), novas], how="diagonal_relaxed")
    novas = novas.unique(subset=CHAVE_PONTO + ["TIPO", "CHAVE"], keep="first", maintain_order=True)
    tmp = path.with_suffix(".parquet.tmp")
    novas.sort(CHAVE_PONTO).write_parquet(tmp)
    tmp.replace(path)


def reconstruir(destino: Path) -> int:
    """Refaz historico_serie.parquet com todas as versões dos EA20 de UF/BR guardadas em raw/."""
    partes = []
    for gz in sorted((destino / "raw").glob("*/*/*.json.gz")):
        if not _ARQUIVO_UF.match(gz.parent.name):
            continue
        with gzip.open(gz, "rt", encoding="utf-8") as fh:
            dados: dict[str, Any] = json.load(fh)
        uf = gz.parent.name.split("-", 1)[0]
        r = m.parse_resultado(dados, uf)
        partes.append(linhas(r.totais, r.candidatos, r.partidos))
    path = destino / ARQUIVO
    path.unlink(missing_ok=True)
    if partes:
        acrescentar(path, pl.concat(partes))
    logger.info("série reconstruída a partir de %d arquivos brutos", len(partes))
    return len(partes)


def para_grafico(serie: pl.DataFrame, cargo: int, abrangencia: str, uf: str, n: int = 3) -> dict[str, Any] | None:
    """Pontos (hora, % seções) e as `n` séries com mais votos na última totalização."""
    s = serie.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == abrangencia)
                     & ((pl.col("UF") == uf) | (pl.lit(abrangencia) == "br")))
    if s.is_empty():
        return None
    pontos = s.select("DT_TOTALIZACAO", "PCT_SECOES_TOTALIZADAS").unique().sort("DT_TOTALIZACAO")
    ultimo = pontos["DT_TOTALIZACAO"].max()
    top = (s.filter(pl.col("DT_TOTALIZACAO") == ultimo).sort("VOTOS", descending=True).head(n)
           .select("CHAVE", "NOME", "PARTIDO"))
    series = []
    for t in top.iter_rows(named=True):
        vals = pontos.join(s.filter(pl.col("CHAVE") == t["CHAVE"]).select("DT_TOTALIZACAO", "PCT_VALIDOS"),
                           on="DT_TOTALIZACAO", how="left").sort("DT_TOTALIZACAO")["PCT_VALIDOS"].to_list()
        series.append({**t, "valores": vals})
    return {"tipo": s["TIPO"][0], "pontos": [{"dt": d.isoformat() if d else None, "pct_secoes": p}
                                               for d, p in pontos.iter_rows()],
            "series": series}


# --------------------------------------------------------------------------
# Série por candidato em cada abrangência (municípios, UF e Brasil)
# --------------------------------------------------------------------------
# Cada arquivo municipal do TSE lista TODOS os candidatos do cargo (dep. estadual no Rio:
# ~2 mil). Para não regravar um arquivo gigante a cada ciclo, o coletor grava um BLOCO
# novo por ciclo (só os arquivos que mudaram) em historico_candidatos/, com:
#   * uma linha por candidato com voto (VOTOS > 0) na abrangência;
#   * uma linha de referência NUMERO = 0 por totalização (VOTOS = válidos), que diz quando
#     houve totalização — o candidato ausente nesse momento tinha 0 voto ali.
# A consulta de um candidato lê só as linhas dele (filtro empurrado para o Parquet).
CANDIDATOS_DIR = "historico_candidatos"
REFERENCIA = 0
SCHEMA_CAND = {
    "ELEICAO": pl.Int64, "CARGO": pl.Int64, "ABRANGENCIA": pl.String, "UF": pl.String, "CD_MUNICIPIO": pl.Int64,
    "DT_TOTALIZACAO": pl.Datetime, "PCT_SECOES_TOTALIZADAS": pl.Float64, "NUMERO": pl.Int64, "VOTOS": pl.Int64,
    "PCT_VALIDOS": pl.Float64,
}
_ABR = ["ELEICAO", "CARGO", "ABRANGENCIA", "UF", "CD_MUNICIPIO"]


def linhas_candidatos(resultados: list[m.Resultado]) -> pl.DataFrame:
    """Linhas de cada arquivo com os totais DELE: um lote pode ter várias versões da mesma
    abrangência (reconstrução), e juntar só pela abrangência misturaria as versões."""
    partes = []
    for r in resultados:
        tot = r.totais.select(_ABR + ["DT_TOTALIZACAO", "PCT_SECOES_TOTALIZADAS", "VALIDOS"])
        ref = tot.select(_ABR + ["DT_TOTALIZACAO", "PCT_SECOES_TOTALIZADAS", pl.lit(REFERENCIA).alias("NUMERO"),
                                 pl.col("VALIDOS").alias("VOTOS"), pl.lit(None, dtype=pl.Float64).alias("PCT_VALIDOS")])
        cand = (r.candidatos.filter(pl.col("VOTOS") > 0)
                .join(tot.drop("VALIDOS"), on=_ABR, how="inner", nulls_equal=True)
                .select(_ABR + ["DT_TOTALIZACAO", "PCT_SECOES_TOTALIZADAS", "NUMERO", "VOTOS", "PCT_VALIDOS"]))
        partes += [ref, cand]
    if not partes:
        return pl.DataFrame(schema=SCHEMA_CAND)
    return pl.concat(partes, how="diagonal_relaxed").select([pl.col(c).cast(t) for c, t in SCHEMA_CAND.items()])


def gravar_bloco(destino: Path, df: pl.DataFrame, tag: str) -> None:
    if df.is_empty():
        return
    pasta = destino / CANDIDATOS_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{tag}.parquet"
    tmp = alvo.with_suffix(".parquet.tmp")
    df.write_parquet(tmp)
    tmp.replace(alvo)


def reconstruir_candidatos(destino: Path) -> int:
    """Refaz historico_candidatos/ com todas as versões dos EA20 (UF, BR e municípios) de raw/."""
    pasta = destino / CANDIDATOS_DIR
    if pasta.exists():
        for f in pasta.glob("*.parquet"):
            f.unlink()
    arquivos = sorted((destino / "raw").glob("*/*-u/*.json.gz"))
    lote: list[m.Resultado] = []
    for i, gz in enumerate(arquivos):
        with gzip.open(gz, "rt", encoding="utf-8") as fh:
            dados = json.load(fh)
        uf = gz.parent.name[:2]
        lote.append(m.parse_resultado(dados, uf))
        if len(lote) == 200 or i == len(arquivos) - 1:  # blocos de 200 arquivos (memória limitada)
            gravar_bloco(destino, linhas_candidatos(lote), f"reconstrucao_{i:06d}")
            lote = []
    logger.info("série por candidato reconstruída a partir de %d arquivos brutos", len(arquivos))
    return len(arquivos)


def serie_candidato(destino: Path, cargo: int, numero: int, abrangencias: list[tuple[str, int | None]]
                    ) -> list[dict[str, Any]]:
    """Para cada (abrangência, município): pontos no tempo com % de seções, votos e % dos válidos."""
    pasta = destino / CANDIDATOS_DIR
    if not pasta.exists() or not any(pasta.glob("*.parquet")):
        return []
    lf = pl.scan_parquet(pasta / "*.parquet").filter(
        (pl.col("CARGO") == cargo) & pl.col("NUMERO").is_in([REFERENCIA, numero]))
    saida = []
    for abr, mun in abrangencias:
        cond = pl.col("ABRANGENCIA") == abr
        cond &= pl.col("CD_MUNICIPIO").is_null() if mun is None else pl.col("CD_MUNICIPIO") == mun
        # sem hora de totalização (o TSE publica a abrangência com a data vazia antes de começar a totalizar: 790
        # linhas na coleta de 4/10) não há ponto no tempo; quebrava a rota com AttributeError (07/10/2026)
        df = (lf.filter(cond & pl.col("DT_TOTALIZACAO").is_not_null()).collect()
              .unique(subset=["DT_TOTALIZACAO", "NUMERO"], keep="first"))
        ref = df.filter(pl.col("NUMERO") == REFERENCIA).select(
            "DT_TOTALIZACAO", "PCT_SECOES_TOTALIZADAS", pl.col("VOTOS").alias("VALIDOS"))
        c = df.filter(pl.col("NUMERO") == numero).select("DT_TOTALIZACAO", "VOTOS", "PCT_VALIDOS")
        pontos = (ref.join(c, on="DT_TOTALIZACAO", how="left")
                  .with_columns(pl.col("VOTOS").fill_null(0), pl.col("PCT_VALIDOS").fill_null(0.0))
                  .sort("DT_TOTALIZACAO"))
        saida.append({"abrangencia": abr, "municipio": mun,
                      "pontos": [{"dt": r["DT_TOTALIZACAO"].isoformat(), "pct_secoes": r["PCT_SECOES_TOTALIZADAS"],
                                  "votos": r["VOTOS"], "pct": r["PCT_VALIDOS"]} for r in pontos.iter_rows(named=True)]})
    return saida


# --------------------------------------------------------------------------
# Mapa num momento da apuração ("como estava às HH:MM")
# --------------------------------------------------------------------------
# Para cada município vale a ÚLTIMA totalização até o momento pedido; município ainda
# sem totalização fica de fora (o mapa mostra "sem dado").
def momentos(hist_totais: pl.DataFrame, cargo: int) -> list[Any]:
    """Horas das totalizações municipais do cargo, em ordem."""
    return (hist_totais.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
            .select("DT_TOTALIZACAO").unique().drop_nulls().sort("DT_TOTALIZACAO")["DT_TOTALIZACAO"].to_list())


def _ultimo_ate(df: pl.DataFrame, momento: Any) -> pl.DataFrame:
    df = df.filter(pl.col("DT_TOTALIZACAO") <= momento)
    return df.filter(pl.col("DT_TOTALIZACAO") == pl.col("DT_TOTALIZACAO").max().over("CD_MUNICIPIO"))


def totais_ate(hist_totais: pl.DataFrame, cargo: int, momento: Any) -> pl.DataFrame:
    base = hist_totais.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
    return _ultimo_ate(base, momento).unique(subset=["CD_MUNICIPIO"], keep="first")


def candidatos_ate(destino: Path, cargo: int, momento: Any, numero: int | None = None) -> pl.DataFrame:
    """CD_MUNICIPIO, NUMERO, VOTOS, PCT_VALIDOS na última totalização de cada município até o momento.
    Com `numero`, uma linha por município totalizado (0 voto se o candidato não aparecia)."""
    pasta = destino / CANDIDATOS_DIR
    vazio = pl.DataFrame(schema={"CD_MUNICIPIO": pl.Int64, "NUMERO": pl.Int64, "VOTOS": pl.Int64,
                                 "PCT_VALIDOS": pl.Float64})
    if not pasta.exists() or not any(pasta.glob("*.parquet")):
        return vazio
    lf = pl.scan_parquet(pasta / "*.parquet").filter(
        (pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun") & (pl.col("DT_TOTALIZACAO") <= momento))
    if numero is not None:
        lf = lf.filter(pl.col("NUMERO").is_in([REFERENCIA, numero]))
    df = lf.collect().unique(subset=["CD_MUNICIPIO", "DT_TOTALIZACAO", "NUMERO"], keep="first")
    ultimo = _ultimo_ate(df.filter(pl.col("NUMERO") == REFERENCIA), momento).select("CD_MUNICIPIO", "DT_TOTALIZACAO")
    no_momento = df.join(ultimo, on=["CD_MUNICIPIO", "DT_TOTALIZACAO"], how="inner")
    if numero is None:
        return no_momento.filter(pl.col("NUMERO") != REFERENCIA).select(list(vazio.columns))
    cand = no_momento.filter(pl.col("NUMERO") == numero).select("CD_MUNICIPIO", "VOTOS", "PCT_VALIDOS")
    return (ultimo.select("CD_MUNICIPIO").join(cand, on="CD_MUNICIPIO", how="left")
            .with_columns(pl.lit(numero).alias("NUMERO"), pl.col("VOTOS").fill_null(0),
                          pl.col("PCT_VALIDOS").fill_null(0.0))
            .select(list(vazio.columns)))
