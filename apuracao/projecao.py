"""Projeção do resultado final durante a apuração (cargos majoritários, por UF).

Por que projetar: os municípios apuram em ritmos diferentes. Com 60% apurado, o percentual parcial do
estado está puxado por quem apurou primeiro (em 2022 no RJ, o interior veio antes da capital).

Método (tudo por município, com o que o TSE publica em tempo real):
- fração apurada do município = eleitorado das seções totalizadas ÷ eleitorado do município
  (`est`/`te` do JSON; no coletor, COMPARECIMENTO + ABSTENCAO ÷ ELEITORADO);
- válidos finais esperados do município = válidos atuais ÷ fração apurada; município ainda sem
  seção apurada: eleitorado × (válidos por eleitor já apurado no estado);
- votos restantes de cada candidato no município = restantes × a participação dele ali até agora;
  no município ainda sem seção, a participação do candidato no estado até agora;
- projeção = votos atuais + votos restantes, somados no estado.

Margem: EMPÍRICA, calibrada reconstituindo a apuração real de 2022 seção a seção (hora da 1ª
totalização de cada seção, `detalhe_votacao_secao`): Presidente nas 27 UFs (1º e 2º turno) e
Governador/Senador no RJ — 58 apurações, 4 candidatos, 20 momentos (`validar_projecao.py`).
Em 2022 a projeção errou em média ~40% menos que o parcial a partir de 30% apurado. Para cada faixa de % do eleitorado apurado, `MARGEM_PP` é o percentil 95
do erro absoluto da projeção frente ao resultado final (ver `backtest` e a rodada 21). Não é
intervalo de confiança estatístico: é "em 2022, 95% das projeções nesta fase erraram menos que isto".
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

import votos_por_local_votacao as v

ESPECIAIS = (95, 96, 97)
# (limite superior da faixa de % do eleitorado apurado, margem em p.p.) — gerado por `calibrar`; a faixa final
# vale até 100%. Uma tabela por turno (rodada 44): no 2º turno (2 candidatos) a projeção erra MAIS no meio da
# apuração (p95 a 40%: 2,98 × 2,11 p.p.), e a margem única cobria só 94,5% dele.
#   1º turno: 2022 + 2026 reconstituídos seção a seção (Presidente nas 27 UFs; Governador e Senador no RJ e no ES)
#   2º turno: 2022 (Presidente nas 27 UFs; Governador no ES)
MARGEM_PP: list[tuple[float, float]] = [
    (10, 7.02), (20, 4.72), (30, 3.51), (40, 2.76), (50, 2.11), (60, 1.78), (70, 1.4), (80, 1.08),
    (90, 0.78), (100, 0.42),
]
MARGEM_PP_2T: list[tuple[float, float]] = [
    (10, 8.82), (20, 4.24), (30, 3.76), (40, 3.33), (50, 2.98), (60, 2.07), (70, 1.55), (80, 1.17),
    (90, 0.7), (100, 0.35),
]


PCT_MINIMO_LEITURA = 2.0  # a calibração começa em 2% apurado: antes disso a leitura seria chute


def margem(pct_apurado: float, tabela: list[tuple[float, float]] | None = None, turno: int = 1) -> float | None:
    """Margem calibrada (p.p.) para o % do eleitorado já apurado; None antes de haver apuração.
    `tabela`: outra calibração (para validar uma proposta antes de adotá-la); padrão a do `turno`."""
    tabela = tabela or (MARGEM_PP_2T if turno == 2 else MARGEM_PP)
    if pct_apurado <= 0:
        return None
    if pct_apurado >= 100:
        return 0.0
    i = bisect.bisect_left([lim for lim, _ in tabela], pct_apurado)
    return tabela[min(i, len(tabela) - 1)][1]


def cobertura(erros: pl.DataFrame, tabela: list[tuple[float, float]] | None = None) -> float:
    """Fração das projeções do backtest com erro dentro da margem (≈ 0,95 na calibração)."""
    m = erros["PCT_APURADO"].map_elements(lambda p: margem(p, tabela), return_dtype=pl.Float64)
    return float((erros["ERRO_PROJECAO"] <= m + 1e-9).mean())


def formatar_tabela(nome: str, tabela: list[tuple]) -> str:
    """A tabela como código Python, pronta para colar no módulo."""
    itens = ", ".join("(" + ", ".join(f"{x:g}" if isinstance(x, (int, float)) else str(x) for x in t) + ")"
                      for t in tabela)
    return f"{nome} = [{itens}]"


@dataclass
class Projecao:
    pct_apurado: float                  # % do eleitorado do estado nas seções já totalizadas
    validos_atuais: int
    validos_projetados: float
    margem_pp: float | None
    candidatos: pl.DataFrame            # NUMERO, VOTOS, PCT_ATUAL, VOTOS_PROJ, PCT_PROJ, MIN, MAX
    municipios: pl.DataFrame            # CD_MUNICIPIO, PCT_APURADO, VALIDOS, VALIDOS_RESTANTES
    municipios_sem_apuracao: int


def projetar(mun: pl.DataFrame, votos: pl.DataFrame, turno: int = 1) -> Projecao:
    """`mun`: CD_MUNICIPIO, ELEITORADO, APURADO (eleitorado das seções totalizadas), VALIDOS.
    `votos`: CD_MUNICIPIO, NUMERO, VOTOS (votos atuais de cada candidato no município).

    No que falta de cada município vale a participação do candidato ali até agora. Testado contra
    misturá-la com a do estado pesando pela fração apurada (linear ou raiz): em 2022 as misturas
    erraram mais em todas as faixas (rodada 21)."""
    m = mun.select("CD_MUNICIPIO", pl.col("ELEITORADO").fill_null(0).cast(pl.Float64),
                   pl.col("APURADO").fill_null(0).cast(pl.Float64), pl.col("VALIDOS").fill_null(0).cast(pl.Float64))
    apurado, eleitorado = m["APURADO"].sum(), m["ELEITORADO"].sum()
    validos_atuais = m["VALIDOS"].sum()
    por_eleitor = validos_atuais / apurado if apurado else 0.0  # válidos por eleitor já apurado (estado)
    m = m.with_columns(
        pl.when(pl.col("APURADO") > 0).then(pl.col("VALIDOS") * pl.col("ELEITORADO") / pl.col("APURADO"))
        .otherwise(pl.col("ELEITORADO") * por_eleitor).alias("VALIDOS_FINAIS"),
    ).with_columns((pl.col("VALIDOS_FINAIS") - pl.col("VALIDOS")).clip(lower_bound=0).alias("VALIDOS_RESTANTES"))

    vt = votos.select("CD_MUNICIPIO", "NUMERO", pl.col("VOTOS").fill_null(0).cast(pl.Float64))
    total_cand = vt.group_by("NUMERO").agg(pl.col("VOTOS").sum().alias("VOTOS_UF"))
    share_uf = total_cand.with_columns((pl.col("VOTOS_UF") / validos_atuais if validos_atuais else pl.lit(0.0))
                                       .alias("SHARE_UF"))
    # participação no município (onde já há apuração) ou no estado (onde ainda não há)
    grade = m.select("CD_MUNICIPIO", "VALIDOS", "VALIDOS_RESTANTES").join(share_uf.select("NUMERO", "SHARE_UF"),
                                                                        how="cross")
    grade = grade.join(vt, on=["CD_MUNICIPIO", "NUMERO"], how="left").with_columns(pl.col("VOTOS").fill_null(0.0))
    grade = grade.with_columns(
        pl.when(pl.col("VALIDOS") > 0).then(pl.col("VOTOS") / pl.col("VALIDOS")).otherwise(pl.col("SHARE_UF"))
        .alias("SHARE"))
    proj = grade.group_by("NUMERO").agg(
        pl.col("VOTOS").sum(), (pl.col("VOTOS") + pl.col("SHARE") * pl.col("VALIDOS_RESTANTES")).sum().alias("VOTOS_PROJ"))
    validos_proj = float(m["VALIDOS_FINAIS"].sum())
    pct_ap = 100 * apurado / eleitorado if eleitorado else 0.0
    mg = margem(pct_ap, turno=turno)
    cand = proj.with_columns(
        (100 * pl.col("VOTOS") / validos_atuais if validos_atuais else pl.lit(None, pl.Float64)).alias("PCT_ATUAL"),
        (100 * pl.col("VOTOS_PROJ") / validos_proj if validos_proj else pl.lit(None, pl.Float64)).alias("PCT_PROJ"),
    ).with_columns(
        (pl.col("PCT_PROJ") - (mg or 0)).clip(lower_bound=0).alias("MIN"),
        (pl.col("PCT_PROJ") + (mg or 0)).clip(upper_bound=100).alias("MAX"),
    ).sort("VOTOS_PROJ", descending=True)
    municipios = m.select("CD_MUNICIPIO", (100 * pl.col("APURADO") / pl.col("ELEITORADO")).fill_nan(0).alias("PCT_APURADO"),
                          "VALIDOS", "VALIDOS_RESTANTES").sort("VALIDOS_RESTANTES", descending=True)
    return Projecao(pct_ap, int(validos_atuais), validos_proj, mg, cand, municipios,
                    int((m["APURADO"] == 0).sum()))


def situacao(p: Projecao, vagas: int = 1, objetivo: str = "maioria", turno: int = 1) -> str:
    """Leitura da projeção com a margem calibrada: definido × indefinido (sem probabilidades).
    `objetivo`: "maioria" (Governador: > 50% dos válidos decide no 1º turno), "vagas" (Senador: os
    `vagas` primeiros) ou "lideranca" (Presidente na UF: quem vence no estado; o turno é nacional).
    No 2º turno (rodada 44) não há "vitória no 1º turno" nem "2º turno projetado": quem passa de 50% vence."""
    c = p.candidatos
    if p.margem_pp is None or c.is_empty():
        return "sem apuração"
    if p.pct_apurado < PCT_MINIMO_LEITURA:
        return (f"cedo demais: {p.pct_apurado:.1f}% do eleitorado apurado (a margem foi medida a partir de "
                f"{PCT_MINIMO_LEITURA:g}%)").replace(".", ",")
    final = p.margem_pp == 0
    if objetivo == "lideranca":
        if c.height == 1 or c.row(0, named=True)["MIN"] > c.row(1, named=True)["MAX"]:
            return f"mais votado no estado {'confirmado' if final else 'definido (fora do alcance do 2º mesmo na margem)'}"
        return "indefinido: o 1º e o 2º no estado estão a menos de uma margem"
    if objetivo == "maioria":
        lider = c.row(0, named=True)
        no_turno = " no 1º turno" if turno == 1 else ""
        if lider["MIN"] > 50:
            return f"vitória{no_turno} {'confirmada' if final else 'projetada'} (acima de 50% mesmo na margem)"
        if turno == 2:
            return "indefinido: o líder está a menos de uma margem dos 50%"
        if lider["MAX"] < 50:
            return "2º turno " + ("confirmado" if final else "projetado (ninguém chega a 50% mesmo na margem)")
        return "indefinido: o líder está a menos de uma margem dos 50%"
    if c.height <= vagas:
        return "definido"
    ultimo, proximo = c.row(vagas - 1, named=True), c.row(vagas, named=True)
    quem = "o 1º está" if vagas == 1 else f"os {vagas} primeiros estão"
    if ultimo["MIN"] > proximo["MAX"]:
        return f"{'eleito' if vagas == 1 else 'eleitos'}{'' if final else ' (projeção)'}: {quem} fora do alcance do {vagas + 1}º"
    return f"indefinido: o {vagas}º e o {vagas + 1}º estão a menos de uma margem"


# --------------------------------------------------------------------------
# Entrada do tempo real
# --------------------------------------------------------------------------
def entrada_divulgacao(totais: pl.DataFrame, candidatos: pl.DataFrame, cargo: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(municípios, votos) a partir do `ultimo/` do coletor (abrangência município)."""
    t = totais.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
    mun = t.select("CD_MUNICIPIO", "ELEITORADO",
                   (pl.col("COMPARECIMENTO").fill_null(0) + pl.col("ABSTENCAO").fill_null(0)).alias("APURADO"), "VALIDOS")
    votos = candidatos.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun")).select(
        "CD_MUNICIPIO", "NUMERO", "VOTOS")
    return mun, votos


# --------------------------------------------------------------------------
# Apuração de 2022 reconstituída (para validar e calibrar)
# --------------------------------------------------------------------------
def detalhe_nacional(ano: int, cache: Path) -> pl.LazyFrame:
    """Detalhe por seção de TODAS as UFs (CSV _BRASIL), para calibrar com Presidente nas 27 UFs."""
    spec = v.DatasetSpec(f"detalhe_votacao_secao_{ano}",
                         f"{v.CDN_BASE}/detalhe_votacao_secao/detalhe_votacao_secao_{ano}.zip", v.NATIONAL,
                         member="_BRASIL.csv")
    pq = v.zip_to_parquet(v.download(spec, cache), spec, v.SECTION_DETAILS_REQUIRED + v.SECTION_DETAILS_OPTIONAL,
                          v.SECTION_DETAILS_REQUIRED, cache)
    return pl.scan_parquet(pq)


def secoes_com_hora(ano: int, uf: str, cargo: int, turno: int, cache: Path,
                    detalhe: pl.LazyFrame | None = None) -> pl.DataFrame:
    """Uma linha por seção: CD_MUNICIPIO, NR_ZONA, NR_SECAO, APTOS, T (hora da 1ª totalização)."""
    det = v.load_section_details(ano, uf, cache) if detalhe is None else detalhe.filter(pl.col("SG_UF") == uf.upper())
    return (det.filter((pl.col("NR_TURNO") == turno) & (pl.col("CD_CARGO") == cargo))
            .select("CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", pl.col("QT_APTOS").alias("APTOS"),
                    pl.col("DT_PRIM_TOT_PARCIAL_HOR_TSE").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M:%S", strict=False)
                    .alias("T"))
            .collect())


def votos_por_secao(votes: pl.LazyFrame, uf: str, cargo_nome: str, turno: int) -> pl.DataFrame:
    """Votos válidos (nominais) por seção e candidato: CD_MUNICIPIO, NR_ZONA, NR_SECAO, NUMERO, VOTOS."""
    return (votes.filter((pl.col("NR_TURNO") == turno) & (pl.col("SG_UF") == uf.upper()) & v.office_filter(cargo_nome)
                         & ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS))
            .group_by("CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum())
            .rename({"NR_VOTAVEL": "NUMERO", "QT_VOTOS": "VOTOS"}).collect())


def estado_em(secoes: pl.DataFrame, votos: pl.DataFrame, t: Any) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(municípios, votos) como o tempo real teria mostrado na hora `t` (seções com T ≤ t)."""
    chave = ["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
    feitas = secoes.filter(pl.col("T") <= t)
    ele = secoes.group_by("CD_MUNICIPIO").agg(pl.col("APTOS").sum().alias("ELEITORADO"))
    vf = votos.join(feitas.select(chave), on=chave, how="inner")
    val = vf.group_by("CD_MUNICIPIO").agg(pl.col("VOTOS").sum().alias("VALIDOS"))
    mun = (ele.join(feitas.group_by("CD_MUNICIPIO").agg(pl.col("APTOS").sum().alias("APURADO")), on="CD_MUNICIPIO",
                    how="left")
           .join(val, on="CD_MUNICIPIO", how="left").with_columns(pl.col("APURADO", "VALIDOS").fill_null(0)))
    return mun, vf.group_by("CD_MUNICIPIO", "NUMERO").agg(pl.col("VOTOS").sum())


def backtest(secoes: pl.DataFrame, votos: pl.DataFrame, pontos: list[float] | None = None,
             top: int = 4) -> pl.DataFrame:
    """Para cada ponto (% do eleitorado apurado), o erro do parcial e da projeção frente ao final,
    para os `top` candidatos finais. Colunas: PCT_ALVO, PCT_APURADO, NUMERO, FINAL, PARCIAL, PROJECAO."""
    pontos = pontos or [2, 5] + list(range(10, 100, 5))
    final = votos.group_by("NUMERO").agg(pl.col("VOTOS").sum())
    final = final.with_columns((100 * pl.col("VOTOS") / pl.col("VOTOS").sum()).alias("FINAL")).sort(
        "FINAL", descending=True).head(top)
    ordem = secoes.drop_nulls("T").sort("T").with_columns(
        (100 * pl.col("APTOS").cum_sum() / secoes["APTOS"].sum()).alias("ACUM"))
    linhas = []
    for alvo in pontos:
        chegou = ordem.filter(pl.col("ACUM") >= alvo)
        if chegou.is_empty():
            continue
        t = chegou["T"][0]
        p = projetar(*estado_em(secoes, votos, t))
        j = final.join(p.candidatos.select("NUMERO", "PCT_ATUAL", "PCT_PROJ"), on="NUMERO", how="left")
        for r in j.iter_rows(named=True):
            linhas.append({"PCT_ALVO": alvo, "PCT_APURADO": p.pct_apurado, "HORA": t, "NUMERO": r["NUMERO"],
                           "FINAL": r["FINAL"], "PARCIAL": r["PCT_ATUAL"], "PROJECAO": r["PCT_PROJ"]})
    return pl.DataFrame(linhas).with_columns((pl.col("PARCIAL") - pl.col("FINAL")).abs().alias("ERRO_PARCIAL"),
                                             (pl.col("PROJECAO") - pl.col("FINAL")).abs().alias("ERRO_PROJECAO"))


def calibrar(erros: pl.DataFrame, faixas: list[float] | None = None, quantil: float = 0.95) -> list[tuple[float, float]]:
    """`MARGEM_PP` a partir dos erros do backtest: percentil do erro da projeção por faixa de % apurado,
    forçado a não crescer com a apuração (uma faixa mais adiantada nunca tem margem maior)."""
    faixas = faixas or [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    saida, anterior, piso = [], float("inf"), 0.0
    for lim in faixas:
        lo = saida[-1][0] if saida else 0
        e = erros.filter((pl.col("PCT_APURADO") > lo) & (pl.col("PCT_APURADO") <= lim))["ERRO_PROJECAO"]
        q = float(e.quantile(quantil)) if e.len() else anterior
        q = min(q, anterior)
        saida.append((lim, round(max(q, piso), 2)))
        anterior = q
    return saida
