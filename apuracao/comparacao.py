"""Comparação por município entre duas eleições no formato do coletor (ex.: 2022 × 2026).

Entradas: os diretórios `ultimo/` de duas fontes — o importador histórico
(apuracao/historico.py) e/ou o coletor em tempo real — com as tabelas `totais`,
`candidatos`, `partidos` e `municipios`. A chave é o código TSE do município; o
código IBGE vem da tabela de municípios (para o mapa).

Métricas (A = ano de referência, B = ano atual; DIF = B − A):
  totais     abstenção, comparecimento, brancos, nulos, brancos+nulos → pontos percentuais
             eleitorado → variação percentual
  partido    % dos votos válidos do partido (nominais + legenda nos proporcionais) → p.p.
  candidato  % dos válidos de um candidato em A × outro (ou o mesmo) em B → p.p.

Senador: em 2022 havia 1 vaga e em 2026 há 2 (cada eleitor vota duas vezes); os
percentuais continuam sobre os válidos de cada ano, mas não são diretamente equivalentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

PROPORCIONAIS = (6, 7, 8)
METRICAS_TOTAIS = {
    "abstencao": ("PCT_ABSTENCAO", "Abstenção (%)", "pp"),
    "comparecimento": ("PCT_COMPARECIMENTO", "Comparecimento (%)", "pp"),
    "brancos": ("PCT_BRANCOS", "Brancos (%)", "pp"),
    "nulos": ("PCT_NULOS", "Nulos (%)", "pp"),
    "brancos_nulos": (None, "Brancos + nulos (%)", "pp"),
    "eleitorado": ("ELEITORADO", "Eleitorado", "var_pct"),
}
CHAVE = ["ABRANGENCIA", "CD_MUNICIPIO"]


@dataclass
class Fonte:
    """Tabelas de uma eleição (o `ultimo/` do coletor ou do importador) e o ano."""

    ano: int
    totais: pl.DataFrame
    candidatos: pl.DataFrame
    partidos: pl.DataFrame
    municipios: pl.DataFrame


def _valor_totais(f: Fonte, cargo: int, metrica: str) -> pl.DataFrame:
    col = METRICAS_TOTAIS[metrica][0]
    expr = (pl.col("PCT_BRANCOS") + pl.col("PCT_NULOS")) if col is None else pl.col(col)
    return (f.totais.filter((pl.col("CARGO") == cargo) & pl.col("ABRANGENCIA").is_in(["uf", "mun"]))
            .select(CHAVE + [expr.cast(pl.Float64).alias("VALOR")]))


def _votos_partido(f: Fonte, cargo: int) -> pl.DataFrame:
    """Votos por (abrangência, município, partido)."""
    if cargo in PROPORCIONAIS:
        src = f.partidos.filter(pl.col("CARGO") == cargo).select(CHAVE + ["PARTIDO", pl.col("VOTOS_TOTAL").alias("V")])
    else:
        src = f.candidatos.filter(pl.col("CARGO") == cargo).select(CHAVE + ["PARTIDO", pl.col("VOTOS").alias("V")])
    return src.filter(pl.col("ABRANGENCIA").is_in(["uf", "mun"])).group_by(CHAVE + ["PARTIDO"]).agg(pl.col("V").sum())


def _pct_partido(f: Fonte, cargo: int, partido: str) -> pl.DataFrame:
    validos = f.totais.filter(pl.col("CARGO") == cargo).select(CHAVE + ["VALIDOS"])
    v = _votos_partido(f, cargo).filter(pl.col("PARTIDO") == partido)
    return (validos.join(v, on=CHAVE, how="left", nulls_equal=True)
            .filter(pl.col("ABRANGENCIA").is_in(["uf", "mun"]))
            .select(CHAVE + [pl.when(pl.col("VALIDOS") > 0).then(100 * pl.col("V").fill_null(0) / pl.col("VALIDOS"))
                             .otherwise(None).alias("VALOR")]))


def _pct_candidato(f: Fonte, cargo: int, numero: int) -> pl.DataFrame:
    base = f.totais.filter((pl.col("CARGO") == cargo) & pl.col("ABRANGENCIA").is_in(["uf", "mun"])).select(CHAVE)
    c = f.candidatos.filter((pl.col("CARGO") == cargo) & (pl.col("NUMERO") == numero)).select(
        CHAVE + [pl.col("PCT_VALIDOS").alias("VALOR")])
    return base.join(c, on=CHAVE, how="left", nulls_equal=True).with_columns(pl.col("VALOR").fill_null(0.0))


def comparar(a: Fonte, b: Fonte, cargo: int, metrica: str, partido: str | None = None,
             numero_a: int | None = None, numero_b: int | None = None) -> pl.DataFrame:
    """Uma linha por abrangência (uf e municípios) com VALOR_A, VALOR_B e DIF."""
    if metrica in METRICAS_TOTAIS:
        va, vb = _valor_totais(a, cargo, metrica), _valor_totais(b, cargo, metrica)
        var_pct = METRICAS_TOTAIS[metrica][2] == "var_pct"
    elif metrica == "partido":
        if not partido:
            raise ValueError("informe o partido")
        va, vb, var_pct = _pct_partido(a, cargo, partido), _pct_partido(b, cargo, partido), False
    elif metrica == "candidato":
        if numero_a is None or numero_b is None:
            raise ValueError("informe o número do candidato em cada ano")
        va, vb, var_pct = _pct_candidato(a, cargo, numero_a), _pct_candidato(b, cargo, numero_b), False
    else:
        raise ValueError(f"métrica desconhecida: {metrica}")
    dif = ((pl.col("VALOR_B") - pl.col("VALOR_A")) / pl.col("VALOR_A") * 100) if var_pct else (
        pl.col("VALOR_B") - pl.col("VALOR_A"))
    nomes = pl.concat([b.municipios, a.municipios], how="diagonal_relaxed").unique(subset=["CD_MUNICIPIO"], keep="first")
    return (
        va.rename({"VALOR": "VALOR_A"}).join(vb.rename({"VALOR": "VALOR_B"}), on=CHAVE, how="full",
                                              coalesce=True, nulls_equal=True)
        .rechunk()
        .with_columns(pl.when(pl.col("VALOR_A").is_not_null() & pl.col("VALOR_B").is_not_null()
                              & ((pl.col("VALOR_A") != 0) | pl.lit(not var_pct)))
                      .then(dif).otherwise(None).alias("DIF"))
        .join(nomes.select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO"), on="CD_MUNICIPIO", how="left")
        .sort("ABRANGENCIA", "NM_MUNICIPIO", descending=[True, False])
    )


def partidos_disponiveis(a: Fonte, b: Fonte, cargo: int) -> pl.DataFrame:
    """Partidos do cargo na UF em cada ano (votos), para o seletor; os presentes nos dois vêm primeiro."""
    def uf(f: Fonte, sufixo: str) -> pl.DataFrame:
        return (_votos_partido(f, cargo).filter(pl.col("ABRANGENCIA") == "uf")
                .select("PARTIDO", pl.col("V").alias(f"VOTOS_{sufixo}")))
    return (uf(a, "A").join(uf(b, "B"), on="PARTIDO", how="full", coalesce=True)
            .with_columns((pl.col("VOTOS_A").is_not_null() & pl.col("VOTOS_B").is_not_null()).alias("NOS_DOIS"))
            .sort(["NOS_DOIS", "VOTOS_B", "VOTOS_A"], descending=True, nulls_last=True))


def carregar_fonte(diretorio: Path, ano_padrao: int) -> Fonte:
    """Lê <diretorio>/ultimo/*.parquet; o ano vem do status.json (importador histórico) ou do padrão."""
    import json

    from apuracao.divulgacao import modelo as m

    schemas = {"totais": m.TOTAIS_SCHEMA, "candidatos": m.CANDIDATOS_SCHEMA, "partidos": m.PARTIDOS_SCHEMA,
               "municipios": m.MUNICIPIOS_SCHEMA}
    tabs = {n: (pl.read_parquet(p) if (p := diretorio / "ultimo" / f"{n}.parquet").exists() else pl.DataFrame(schema=s))
            for n, s in schemas.items()}
    st = diretorio / "status.json"
    ano = (json.loads(st.read_text()).get("ano") if st.exists() else None) or ano_padrao
    return Fonte(ano=ano, **tabs)
