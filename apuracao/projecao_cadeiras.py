"""Projeção das cadeiras de deputado durante a apuração: cadeiras por agremiação e eleitos
"consolidados" × "em disputa".

1. Projeta, por município (mesmo método de `apuracao.projecao`), os votos de cada agremiação e de
   cada candidato.
2. Distribui as cadeiras sobre os votos projetados (`apuracao.cadeiras`).
3. Simula `N_SIM` vezes, perturbando os votos projetados com ruído log-normal do tamanho do erro que a
   projeção teve na apuração real de 2022 (`SIGMA`, por faixa de % apurado; agremiações e candidatos
   em separado). Em cada simulação refaz a distribuição inteira.
4. Eleito "consolidado" = eleito em ≥ `LIMIAR` das simulações; "em disputa" = eleito em parte delas.
   Cadeiras da agremiação: a da projeção e a faixa (percentis 5–95) das simulações.

Calibração e validação: `validar_projecao.py --deputados` (rodada 22). Só RJ 2022, Dep. Federal e
Estadual — é a única eleição com votos por seção no cache; os números são "dentro da amostra".
Antes de `PCT_MINIMO` apurado o painel mostra só a distribuição sobre os votos parciais.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

import numpy as np
import polars as pl

from apuracao import cadeiras as cd
from apuracao import projecao as pj

N_SIM = 300
LIMIAR = 0.95
PCT_MINIMO = 30.0
# (limite superior da faixa de % apurado, σ do log-erro das agremiações, σ do log-erro dos candidatos)
# medidos na apuração real de 2022 (RJ, Dep. Federal e Estadual) — `calibrar_sigma`, rodada 22
SIGMA: list[tuple[float, float, float]] = [
    (10, 0.142, 0.425), (20, 0.130, 0.338), (30, 0.126, 0.289), (40, 0.109, 0.239), (50, 0.086, 0.194),
    (60, 0.072, 0.145), (70, 0.059, 0.131), (80, 0.038, 0.093), (90, 0.022, 0.052), (100, 0.012, 0.025),
]


def sigma(pct_apurado: float, tabela: list[tuple[float, float, float]] | None = None) -> tuple[float, float]:
    """σ (agremiação, candidato) para o % apurado; `tabela` permite validar uma proposta antes de adotá-la."""
    tabela = tabela or SIGMA
    if pct_apurado >= 100:
        return 0.0, 0.0
    i = bisect.bisect_left([lim for lim, _, _ in tabela], max(pct_apurado, 1e-9))
    _, sa, sc = tabela[min(i, len(tabela) - 1)]
    return sa, sc


def calibrar_tabela_sigma(erros: pl.DataFrame, faixas: list[float] | None = None) -> list[tuple[float, float, float]]:
    """`SIGMA` a partir dos log-erros (`calibrar_sigma`, de um ou mais anos): desvio-padrão por faixa de
    % apurado, para agremiações e candidatos, forçado a não crescer com a apuração."""
    faixas = faixas or [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    saida, ant = [], {"agremiacao": float("inf"), "candidato": float("inf")}
    lo = 0.0
    for lim in faixas:
        faixa = erros.filter((pl.col("PCT") > lo) & (pl.col("PCT") <= lim))
        linha = [lim]
        for tipo in ("agremiacao", "candidato"):
            x = faixa.filter(pl.col("TIPO") == tipo)["LOG_ERRO"]
            if x.len() < 2 and ant[tipo] == float("inf"):
                raise ValueError(f"faixa até {lim}% sem erros de {tipo} para calibrar")
            sd = float(x.std()) if x.len() > 1 else ant[tipo]  # faixa vazia herda a anterior
            ant[tipo] = min(sd, ant[tipo])
            linha.append(round(ant[tipo], 3))
        saida.append(tuple(linha))
        lo = lim
    return saida


@dataclass
class ProjecaoCadeiras:
    pct_apurado: float
    base: cd.Distribuicao            # distribuição sobre os votos projetados
    agremiacoes: pl.DataFrame        # base.agremiacoes + VOTOS_ATUAIS, VAGAS_MIN, VAGAS_MAX
    candidatos: pl.DataFrame         # base.candidatos + VOTOS_ATUAIS, FREQ_ELEITO, STATUS
    n_sim: int


def projetar_votos(mun: pl.DataFrame, votos_agr: pl.DataFrame, votos_cand: pl.DataFrame
                   ) -> tuple[pl.DataFrame, pl.DataFrame, float]:
    """(agremiações: AGREMIACAO, VOTOS_ATUAIS, VOTOS_PROJ; candidatos: NUMERO, VOTOS_ATUAIS, VOTOS_PROJ; % apurado).
    `votos_agr`: CD_MUNICIPIO, AGREMIACAO, VOTOS; `votos_cand`: CD_MUNICIPIO, NUMERO, VOTOS."""
    nomes = sorted(votos_agr["AGREMIACAO"].unique().to_list())
    ids = {a: i for i, a in enumerate(nomes)}
    va = votos_agr.with_columns(pl.col("AGREMIACAO").replace_strict(ids, return_dtype=pl.Int64).alias("NUMERO"))
    pa = pj.projetar(mun, va.select("CD_MUNICIPIO", "NUMERO", "VOTOS"))
    agr = pa.candidatos.select(pl.col("NUMERO").replace_strict(dict(enumerate(nomes)), return_dtype=pl.String)
                               .alias("AGREMIACAO"), pl.col("VOTOS").alias("VOTOS_ATUAIS"), "VOTOS_PROJ")
    pc = pj.projetar(mun, votos_cand.select("CD_MUNICIPIO", "NUMERO", "VOTOS"))
    cand = pc.candidatos.select("NUMERO", pl.col("VOTOS").alias("VOTOS_ATUAIS"), "VOTOS_PROJ")
    return agr, cand, pa.pct_apurado


def _filas(cand: pl.DataFrame, votos_col: str) -> dict[str, list[dict]]:
    ordem = cand.filter(pl.col("VALIDO")).with_columns(pl.col("DESEMPATE").fill_null(2**62)) \
        .sort([votos_col, "DESEMPATE", "NUMERO"], descending=[True, False, False])
    fila: dict[str, list[dict]] = {}
    for r in ordem.select("AGREMIACAO", "NUMERO", "NOME", pl.col(votos_col).alias("VOTOS")).iter_rows(named=True):
        fila.setdefault(r["AGREMIACAO"], []).append(r)
    return fila


def simular(agr: pl.DataFrame, cand: pl.DataFrame, vagas: int, sigma_agr: float, sigma_cand: float,
            n: int = N_SIM, semente: int = 2026) -> tuple[dict[int, float], dict[str, np.ndarray]]:
    """(frequência de eleição por nº de candidato, vagas por agremiação em cada simulação).
    `agr`: AGREMIACAO, VOTOS_PROJ; `cand`: AGREMIACAO, NUMERO, NOME, VOTOS_PROJ, VALIDO, DESEMPATE."""
    rng = np.random.default_rng(semente)
    # ordem fixa: o ruído é sorteado por posição, então a ordem de entrada (que pode vir de um
    # group_by sem ordem) não pode mudar o resultado — mesma semente, mesmo resultado
    agr = agr.sort("AGREMIACAO")
    nomes = agr["AGREMIACAO"].to_list()
    va = agr["VOTOS_PROJ"].to_numpy().astype(float)
    ok = cand.filter(pl.col("VALIDO")).sort("NUMERO")
    ag_c, num_c = ok["AGREMIACAO"].to_list(), ok["NUMERO"].to_list()
    nome_c, vc = ok["NOME"].to_list(), ok["VOTOS_PROJ"].to_numpy().astype(float)
    desemp = ok["DESEMPATE"].fill_null(2**62).to_list()
    conta: dict[int, int] = {}
    vagas_sim = {a: np.zeros(n, dtype=int) for a in nomes}
    for k in range(n):
        v_a = va * np.exp(rng.normal(0, sigma_agr, va.size)) if sigma_agr else va
        v_c = vc * np.exp(rng.normal(0, sigma_cand, vc.size)) if sigma_cand else vc
        votos = dict(zip(nomes, v_a))
        qe = cd.quociente_eleitoral(int(round(v_a.sum())), vagas)
        fila: dict[str, list[dict]] = {}
        for i in sorted(range(len(num_c)), key=lambda j: (-v_c[j], desemp[j], num_c[j])):
            fila.setdefault(ag_c[i], []).append({"NUMERO": num_c[i], "NOME": nome_c[i], "VOTOS": v_c[i]})
        for a in fila:
            votos.setdefault(a, 0.0)
        eleitos, lugares, *_ = cd._eleger(votos, fila, vagas, qe)
        for (_, n_) in eleitos:
            conta[n_] = conta.get(n_, 0) + 1
        for a, lug in lugares.items():
            if a in vagas_sim:
                vagas_sim[a][k] = lug
    return {n_: c / n for n_, c in conta.items()}, vagas_sim


def status(freq: float, eleito: bool) -> str:
    if eleito and freq >= LIMIAR:
        return "consolidado"
    if eleito:
        return "em disputa (dentro)"
    if freq >= 1 - LIMIAR:
        return "em disputa (fora)"
    return "fora"


def projetar_cadeiras(mun: pl.DataFrame, votos_agr: pl.DataFrame, votos_cand: pl.DataFrame,
                      cand_info: pl.DataFrame, vagas: int, n_sim: int = N_SIM,
                      tabela_sigma: list[tuple[float, float, float]] | None = None) -> ProjecaoCadeiras:
    """`cand_info`: AGREMIACAO, NUMERO, NOME, PARTIDO, VALIDO, DESEMPATE (uma linha por candidato)."""
    agr, cp, pct = projetar_votos(mun, votos_agr, votos_cand)
    if agr["VOTOS_PROJ"].sum() <= 0:
        raise cd.v.TseDataError("ainda não há votos válidos apurados para projetar as cadeiras")
    agr_in = agr.select("AGREMIACAO", pl.col("AGREMIACAO").alias("NOME"),
                        pl.col("VOTOS_PROJ").round(0).cast(pl.Int64).alias("VOTOS"))
    cand = cand_info.drop([c for c in ("VOTOS", "VOTOS_ATUAIS", "VOTOS_PROJ") if c in cand_info.columns]).join(
        cp, on="NUMERO", how="left").with_columns(pl.col("VOTOS_ATUAIS", "VOTOS_PROJ").fill_null(0))
    if "DESEMPATE" not in cand.columns:
        cand = cand.with_columns(pl.lit(None, pl.Int64).alias("DESEMPATE"))
    base = cd.distribuir(agr_in, cand.with_columns(pl.col("VOTOS_PROJ").round(0).cast(pl.Int64).alias("VOTOS")),
                         vagas, int(agr_in["VOTOS"].sum()))
    sa, sc = sigma(pct, tabela_sigma)
    freq, vagas_sim = simular(agr.select("AGREMIACAO", "VOTOS_PROJ"), cand, vagas, sa, sc, n_sim)
    faixa = {a: (int(np.percentile(x, 5)), int(np.percentile(x, 95))) for a, x in vagas_sim.items()}
    agremiacoes = base.agremiacoes.join(agr.select("AGREMIACAO", "VOTOS_ATUAIS"), on="AGREMIACAO", how="left") \
        .with_columns(pl.col("AGREMIACAO").replace_strict({a: f[0] for a, f in faixa.items()}, default=0,
                                                          return_dtype=pl.Int64).alias("VAGAS_MIN"),
                      pl.col("AGREMIACAO").replace_strict({a: f[1] for a, f in faixa.items()}, default=0,
                                                          return_dtype=pl.Int64).alias("VAGAS_MAX"))
    candidatos = base.candidatos.with_columns(
        pl.col("NUMERO").replace_strict(freq, default=0.0, return_dtype=pl.Float64).alias("FREQ_ELEITO"),
    ).with_columns(pl.struct("FREQ_ELEITO", "SITUACAO_PROJETADA").map_elements(
        lambda r: status(r["FREQ_ELEITO"], r["SITUACAO_PROJETADA"].startswith("Eleito")), return_dtype=pl.String)
        .alias("STATUS"))
    return ProjecaoCadeiras(pct, base, agremiacoes, candidatos, n_sim)


# --------------------------------------------------------------------------
# Entrada do tempo real
# --------------------------------------------------------------------------
def entrada_divulgacao(totais: pl.DataFrame, candidatos: pl.DataFrame, partidos: pl.DataFrame, cargo: int, uf: str
                       ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, int]:
    """(municípios, votos das agremiações por município, votos dos candidatos por município, cadastro, vagas)."""
    _, cand_info, vagas, _ = cd.entrada_divulgacao(totais, candidatos, partidos, cargo, uf)
    mun, votos_cand = pj.entrada_divulgacao(totais, candidatos, cargo)
    votos_agr = (partidos.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
                 .with_columns(cd._chave_agremiacao("FEDERACAO", "PARTIDO").alias("AGREMIACAO"))
                 .group_by("CD_MUNICIPIO", "AGREMIACAO").agg(pl.col("VOTOS_TOTAL").fill_null(0).sum().alias("VOTOS")))
    return mun, votos_agr, votos_cand, cand_info, vagas


# --------------------------------------------------------------------------
# Apuração de 2022 reconstituída (calibração e validação)
# --------------------------------------------------------------------------
def votos_secao_deputado(votes: pl.LazyFrame, cand_info: pl.DataFrame, cargo_nome: str
                         ) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(agremiações por seção, candidatos por seção) com NUMERO = agremiação/candidato. Votos de
    candidatos inválidos (anulados) ficam fora; legenda vai para a agremiação do partido."""
    from apuracao.bairros import numero_partido
    part_agr = dict(cand_info.select(numero_partido(pl.col("NUMERO")).alias("P"), "AGREMIACAO").unique("P").iter_rows())
    invalidos = cand_info.filter(~pl.col("VALIDO"))["NUMERO"].to_list()
    vs = (votes.filter((pl.col("NR_TURNO") == 1) & cd.v.office_filter(cargo_nome)
                       & ~pl.col("NR_VOTAVEL").is_in(pj.ESPECIAIS) & ~pl.col("NR_VOTAVEL").is_in(invalidos))
          .group_by("CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum()).collect()
          .with_columns(numero_partido(pl.col("NR_VOTAVEL")).replace_strict(part_agr, default=None).alias("AGREMIACAO"))
          .drop_nulls("AGREMIACAO"))
    chave = ["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
    agr = vs.group_by(chave + ["AGREMIACAO"]).agg(pl.col("QT_VOTOS").sum().alias("VOTOS"))
    cand = vs.filter(pl.col("NR_VOTAVEL") >= 100).select(chave + [pl.col("NR_VOTAVEL").alias("NUMERO"),
                                                                  pl.col("QT_VOTOS").alias("VOTOS")])
    return agr, cand


def estado_em(secoes: pl.DataFrame, agr_secao: pl.DataFrame, cand_secao: pl.DataFrame, t) -> tuple:
    """(municípios, votos_agr, votos_cand) como o tempo real teria mostrado na hora `t`."""
    mun, vc = pj.estado_em(secoes, cand_secao, t)
    chave = ["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
    feitas = secoes.filter(pl.col("T") <= t).select(chave)
    va = agr_secao.join(feitas, on=chave, how="inner").group_by("CD_MUNICIPIO", "AGREMIACAO").agg(pl.col("VOTOS").sum())
    # os válidos do município incluem a legenda: vêm das agremiações, não só dos nominais
    val = va.group_by("CD_MUNICIPIO").agg(pl.col("VOTOS").sum().alias("_V"))
    mun = mun.join(val, on="CD_MUNICIPIO", how="left").with_columns(pl.col("_V").fill_null(0).alias("VALIDOS")).drop("_V")
    return mun, va, vc


def momentos(secoes: pl.DataFrame, pontos: list[float]) -> list[tuple[float, object]]:
    ordem = secoes.drop_nulls("T").sort("T").with_columns(
        (100 * pl.col("APTOS").cum_sum() / secoes["APTOS"].sum()).alias("ACUM"))
    return [(p, ordem.filter(pl.col("ACUM") >= p)["T"][0]) for p in pontos if not ordem.filter(pl.col("ACUM") >= p).is_empty()]


def calibrar_sigma(secoes, agr_secao, cand_secao, pontos: list[float], min_votos_cand: float) -> pl.DataFrame:
    """Log-erro (final ÷ projeção) das agremiações e dos candidatos com ≥ `min_votos_cand` votos finais,
    por momento. Colunas: PCT, TIPO, LOG_ERRO."""
    final_a = agr_secao.group_by("AGREMIACAO").agg(pl.col("VOTOS").sum().alias("FINAL"))
    final_c = cand_secao.group_by("NUMERO").agg(pl.col("VOTOS").sum().alias("FINAL")).filter(pl.col("FINAL") >= min_votos_cand)
    linhas = []
    for p, t in momentos(secoes, pontos):
        mun, va, vc = estado_em(secoes, agr_secao, cand_secao, t)
        a, c, pct = projetar_votos(mun, va, vc)
        for tipo, df, fin, k in (("agremiacao", a, final_a, "AGREMIACAO"), ("candidato", c, final_c, "NUMERO")):
            j = fin.join(df, on=k, how="inner").filter(pl.col("VOTOS_PROJ") > 0)
            linhas += [{"PCT": pct, "TIPO": tipo, "LOG_ERRO": float(x)}
                       for x in np.log(j["FINAL"].to_numpy() / j["VOTOS_PROJ"].to_numpy())]
    return pl.DataFrame(linhas)
