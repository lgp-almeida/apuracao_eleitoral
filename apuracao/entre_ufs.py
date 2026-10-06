"""Comparação entre UFs (TODO 20, rodada 47): abstenção, brancos/nulos e transferência 1º → 2º turno lado a lado.

Entradas: as pastas no formato do coletor de cada UF e eleição (`apuracao.ufs.dir_uf`):
  atual       `dados_2026/oficial[_t2]_<UF>` (tempo real; no RJ, a pasta antiga sem sufixo);
  referência  `dados_2026/historico_2022_t<turno>_<UF>` (microdados importados).
Pasta que falta (UF sem 2º turno, 2º turno de 2026 ainda não apurado) = sem linha, não erro.

  participacao   por UF × cargo × eleição × turno: abstenção (% do eleitorado) e brancos + nulos (% do total de
                 votos, o mesmo denominador do mapa), com o % apurado — a noite em andamento aparece como parcial;
  variacao       atual − referência em p.p., por UF × cargo × turno;
  transferencia  1º → 2º turno por UF (municípios como unidades, `transferencia.unidades_divulgacao`): para onde
                 foram os votos dos eliminados e a abstenção extra. Leitura FRÁGIL (viés de agregação medido em
                 2022, rodada 30) e impossível onde há poucos municípios (DF tem 1): a linha diz por quê.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import polars as pl

import votos_por_local_votacao as v
from apuracao import transferencia as tf
from apuracao import ufs as uu

logger = logging.getLogger("apuracao.entre_ufs")

CARGOS = {1: "Presidente", 3: "Governador"}
SCHEMA_PART = {"UF": pl.String, "CARGO": pl.Int64, "ELEICAO": pl.String, "TURNO": pl.Int64, "PCT_APURADO": pl.Float64,
               "ELEITORADO": pl.Int64, "ABSTENCAO_PCT": pl.Float64, "BRANCOS_NULOS_PCT": pl.Float64,
               "BRANCOS_PCT": pl.Float64, "NULOS_PCT": pl.Float64}


@dataclass(frozen=True)
class Eleicao:
    """Uma eleição comparável: rótulo ("2026"), e a base das pastas do 1º e do 2º turno."""
    rotulo: str
    base_t1: Path
    base_t2: Path


def eleicoes_padrao(dados: Path, ambiente: str = "oficial", ano_ref: int = 2022) -> list[Eleicao]:
    return [Eleicao("2026", dados / ambiente, dados / f"{ambiente}_t2"),
            Eleicao(str(ano_ref), dados / f"historico_{ano_ref}_t1", dados / f"historico_{ano_ref}_t2")]


def _totais(pasta: Path) -> pl.DataFrame | None:
    f = pasta / "ultimo" / "totais.parquet"
    return pl.read_parquet(f) if f.exists() else None


def participacao_uf(tot: pl.DataFrame, uf: str, cargo: int) -> dict | None:
    """Abstenção e brancos/nulos do cargo no estado (linha "uf" da UF)."""
    r = tot.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf) & (pl.col("CARGO") == cargo))
    if r.is_empty():
        return None
    r = r.row(0, named=True)
    el, vt = r["ELEITORADO"] or 0, r["VOTOS_TOTAL"] or 0
    pct = lambda n, d: 100 * n / d if d else None  # noqa: E731
    return {"TURNO": r["TURNO"], "PCT_APURADO": r["PCT_SECOES_TOTALIZADAS"], "ELEITORADO": el,
            "ABSTENCAO_PCT": pct(r["ABSTENCAO"] or 0, el),
            "BRANCOS_NULOS_PCT": pct((r["BRANCOS"] or 0) + (r["NULOS"] or 0), vt),
            "BRANCOS_PCT": pct(r["BRANCOS"] or 0, vt), "NULOS_PCT": pct(r["NULOS"] or 0, vt)}


def participacao(eleicoes: list[Eleicao], ufs: Iterable[str], cargos: Iterable[int] = tuple(CARGOS)) -> pl.DataFrame:
    linhas = []
    for e in eleicoes:
        for turno, base in ((1, e.base_t1), (2, e.base_t2)):
            for uf in ufs:
                tot = _totais(uu.dir_uf(base, uf))
                if tot is None:
                    continue
                for cargo in cargos:
                    p = participacao_uf(tot, uf, cargo)
                    if p is not None:
                        linhas.append({"UF": uf, "CARGO": cargo, "ELEICAO": e.rotulo, **p, "TURNO": turno})
    return pl.DataFrame(linhas, schema=SCHEMA_PART).sort("CARGO", "TURNO", "UF", "ELEICAO")


def variacao(part: pl.DataFrame, atual: str, ref: str) -> pl.DataFrame:
    """Atual − referência (p.p.) por UF × cargo × turno; só onde as duas existem."""
    cols = ["ABSTENCAO_PCT", "BRANCOS_NULOS_PCT"]
    a = part.filter(pl.col("ELEICAO") == atual).select("UF", "CARGO", "TURNO", "PCT_APURADO", *cols)
    b = part.filter(pl.col("ELEICAO") == ref).select("UF", "CARGO", "TURNO", *cols)
    j = a.join(b, on=["UF", "CARGO", "TURNO"], suffix=f"_{ref}").rename({c: f"{c}_{atual}" for c in cols})
    return (j.with_columns([(pl.col(f"{c}_{atual}") - pl.col(f"{c}_{ref}")).alias(c.replace("_PCT", "_VAR_PP"))
                            for c in cols])
            .sort("CARGO", "TURNO", "ABSTENCAO_VAR_PP", descending=[False, False, True]))


def transferencia_uf(dir1: Path, dir2: Path, uf: str, cargo: int) -> dict:
    """Resumo da transferência 1º → 2º turno na UF, por município. Sem n_boot nem validação (comparação rápida
    entre UFs; para o IC, use `transferencia_turnos.py --dados-1t/--dados-2t`)."""
    u = tf.unidades_divulgacao(dir1, dir2, cargo, uf)
    res = tf.analisar(u, n_boot=0, validar_cv=False)
    r = tf.resumo(res)
    a, b = u.cat2[0], u.cat2[1]   # os finalistas vêm primeiro (mais votado no 2º turno, na área, à frente)
    i_el = u.cat1.index(tf.ELIMINADOS) if tf.ELIMINADOS in u.cat1 else None
    j = {c: u.cat2.index(c) for c in (a, b, tf.BRANCO_NULO, tf.ABSTENCAO)}
    d = {"FINALISTA_A": a, "FINALISTA_B": b, "MUNICIPIOS": u.tabela.height,
         "ABSTENCAO_EXTRA_PP": r["abstencao"]["extra_pp"],
         "ELIMINADOS_PCT_ELEITORADO": None, "ELIM_PARA_A": None, "ELIM_PARA_B": None,
         "ELIM_PARA_BRANCO_NULO": None, "ELIM_PARA_ABSTENCAO": None,
         "A_FICOU": 100 * res.matriz[u.cat1.index(a), j[a]] if a in u.cat1 else None,
         "B_FICOU": 100 * res.matriz[u.cat1.index(b), j[b]] if b in u.cat1 else None,
         "R2_A": r["r2"].get(a), "CELULAS_NO_LIMITE": r["celulas_no_limite"], "NOTA": None}
    if i_el is not None:
        m = 100 * res.matriz[i_el]
        d.update(ELIMINADOS_PCT_ELEITORADO=r["matriz"][i_el]["pct_1t"], ELIM_PARA_A=m[j[a]], ELIM_PARA_B=m[j[b]],
                 ELIM_PARA_BRANCO_NULO=m[j[tf.BRANCO_NULO]], ELIM_PARA_ABSTENCAO=m[j[tf.ABSTENCAO]])
    return d


SCHEMA_TRANSF = {"UF": pl.String, "CARGO": pl.Int64, "ELEICAO": pl.String, "FINALISTA_A": pl.String,
                 "FINALISTA_B": pl.String, "MUNICIPIOS": pl.Int64, "ABSTENCAO_EXTRA_PP": pl.Float64,
                 "ELIMINADOS_PCT_ELEITORADO": pl.Float64, "ELIM_PARA_A": pl.Float64, "ELIM_PARA_B": pl.Float64,
                 "ELIM_PARA_BRANCO_NULO": pl.Float64, "ELIM_PARA_ABSTENCAO": pl.Float64, "A_FICOU": pl.Float64,
                 "B_FICOU": pl.Float64, "R2_A": pl.Float64, "CELULAS_NO_LIMITE": pl.Int64, "NOTA": pl.String}


def transferencias(eleicoes: list[Eleicao], ufs: Iterable[str], cargos: Iterable[int] = tuple(CARGOS)) -> pl.DataFrame:
    """Uma linha por UF × cargo × eleição com 2º turno. UF sem 2º turno daquele cargo não aparece; UF com 2º turno
    mas sem como estimar (poucos municípios) aparece com a NOTA."""
    linhas = []
    for e in eleicoes:
        for uf in ufs:
            d1, d2 = uu.dir_uf(e.base_t1, uf), uu.dir_uf(e.base_t2, uf)
            t2 = _totais(d2)
            if t2 is None or _totais(d1) is None:
                continue
            for cargo in cargos:
                if participacao_uf(t2, uf, cargo) is None:
                    continue   # sem 2º turno desse cargo na UF
                base = {"UF": uf, "CARGO": cargo, "ELEICAO": e.rotulo}
                try:
                    linhas.append({**base, **transferencia_uf(d1, d2, uf, cargo)})
                except (v.TseDataError, ValueError, IndexError) as exc:
                    logger.info("%s %s %s: %s", e.rotulo, uf, cargo, exc)
                    linhas.append({**base, "NOTA": str(exc)})
    return pl.DataFrame(linhas, schema=SCHEMA_TRANSF).sort("CARGO", "ELEICAO", "UF")


def para_planilha(part: pl.DataFrame, var: pl.DataFrame, transf: pl.DataFrame, destino: Path) -> Path:
    import xlsxwriter
    destino.parent.mkdir(parents=True, exist_ok=True)
    nota = pl.DataFrame({"LEIA": [
        "Abstenção: % do eleitorado. Brancos + nulos: % do total de votos (o denominador do mapa).",
        "PCT_APURADO < 100: a eleição ainda estava em apuração quando a pasta foi lida.",
        "Transferência: municípios como unidades (inferência ECOLÓGICA, leitura frágil; ver rodada 30). "
        "ELIM_PARA_*: % dos votos dos eliminados do 1º turno que foram para cada opção do 2º.",
        "A_FICOU/B_FICOU: % do eleitorado de cada finalista no 1º turno que votou nele de novo.",
        "CELULAS_NO_LIMITE: células da matriz em 0% ou 100% (a restrição segurou o modelo): quanto mais, mais frágil "
        "(ex.: RR 2022, 15 municípios, eliminados → 100% num finalista)."]})
    with xlsxwriter.Workbook(str(destino)) as wb:
        for nome, df in {"leia": nota, "participacao": part, "variacao": var, "transferencia": transf}.items():
            df.write_excel(wb, worksheet=nome, autofit=True, float_precision=2)
    return destino


def grafico(var: pl.DataFrame, cargo: int, turno: int, destino: Path, atual: str, ref: str) -> Path | None:
    """PNG: abstenção por UF na referência e na atual (um par de pontos por UF, ordenado pela atual)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = var.filter((pl.col("CARGO") == cargo) & (pl.col("TURNO") == turno)).sort(f"ABSTENCAO_PCT_{atual}")
    if d.is_empty():
        return None
    fig, ax = plt.subplots(figsize=(7, 0.28 * d.height + 1.4), dpi=150)
    y = range(d.height)
    xa, xb = d[f"ABSTENCAO_PCT_{ref}"].to_list(), d[f"ABSTENCAO_PCT_{atual}"].to_list()
    ax.hlines(list(y), xa, xb, color="#b8b8b8", lw=1.2, zorder=1)
    ax.scatter(xa, list(y), color="#9aa4b1", s=22, label=ref, zorder=2)
    ax.scatter(xb, list(y), color="#2a6fdb", s=26, label=atual, zorder=3)
    ax.set_yticks(list(y), d["UF"].to_list(), fontsize=8)
    ax.set_xlabel("Abstenção (% do eleitorado)")
    ax.set_title(f"Abstenção por UF — {CARGOS.get(cargo, cargo)}, {turno}º turno: {ref} × {atual}", fontsize=10)
    ax.grid(axis="x", color="#e6e6e6", lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino)
    plt.close(fig)
    return destino
