"""Quem migrou para quem entre duas eleições (ex.: 2022 → 2026), por local de votação (TODO 22, rodada 46).

A mesma inferência ECOLÓGICA de `transferencia.py` (y ≈ x·B, linhas de B no simplex, estratos por município,
IC por bootstrap e validação fora da amostra), com outra unidade e outras categorias:

  unidade      o LOCAL de votação presente nos dois cadastros (chave município + zona + nº do local, a mesma
               identidade de `locais.compare_places`). As seções são renumeradas e remanejadas entre anos (não dá
               para usar a seção); local novo ou desativado não entra, e local cujo eleitorado mudou demais
               (`VARIACAO_MAX`: mais que dobrou ou caiu à metade — remanejamento grande) também sai.
  categorias   em cada ano, os candidatos com ≥ 1% dos válidos na área (até 5), "Outros", branco/nulo e
               abstenção. Os candidatos são OUTROS em cada ano (Bolsonaro 2022 × Flávio 2026): a validação usa
               como "swing uniforme" o MESMO PARTIDO (entidade, `apuracao/partidos.py`).

Ressalvas (como na rodada 30, mais fortes aqui): o eleitorado de um local não é o mesmo nos dois anos (mudanças
de domicílio eleitoral, mortes, novos eleitores); B é o padrão médio entre locais, não o voto de pessoas.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

import votos_por_local_votacao as v
from apuracao import partidos as pt
from apuracao import projecao as pj
from apuracao import transferencia as tf

logger = logging.getLogger("apuracao.migracao")

CHAVE = list(v.LOCAL_KEY)
VARIACAO_MAX = 2.0   # local com eleitorado que mais que dobrou (ou caiu à metade) entre os anos sai da conta
# Senador fica de fora: o nº de vagas muda entre eleições (1 em 2022, 2 em 2026 — dois votos por eleitor), e a
# abstenção, calculada como eleitorado − votos, deixa de fazer sentido
NOMES_CARGO = {1: "presidente", 3: "governador"}


def carregar_ano(ano: int, uf: str, cargo: int, cache: Path, turno: int = 1
                 ) -> tuple[pl.DataFrame, pl.DataFrame, dict[int, tuple[str, str]]]:
    """(locais: LOCAL_KEY, NM_MUNICIPIO, NM_LOCAL_VOTACAO, APTOS; votos: LOCAL_KEY, NR_VOTAVEL, QT_VOTOS;
    candidatos: nº → (rótulo "NOME (PARTIDO)", sigla)) de um ano, a partir dos microdados por seção."""
    uf = uf.upper()
    nome = NOMES_CARGO[cargo]
    det = (pj.detalhe_nacional(ano, cache).filter(pl.col("SG_UF") == uf) if cargo == 1
           else v.load_section_details(ano, uf, cache))
    aptos = (det.filter((pl.col("NR_TURNO") == turno) & (pl.col("CD_CARGO") == cargo))
             .group_by(tf.SECAO).agg(pl.col("QT_APTOS").sum()).collect())
    lz = v.load_section_votes(ano, uf, nome, cache, False).filter(
        v.office_filter(nome.upper()) & (pl.col("SG_UF") == uf) & (pl.col("NR_TURNO") == turno))
    secao_local = lz.select(*tf.SECAO, "NR_LOCAL_VOTACAO", "NM_MUNICIPIO", "NM_LOCAL_VOTACAO").unique(tf.SECAO).collect()
    locais = (aptos.join(secao_local, on=tf.SECAO, how="inner").group_by(CHAVE)
              .agg(pl.col("QT_APTOS").sum().alias("APTOS"), pl.col("NM_MUNICIPIO").first(),
                   pl.col("NM_LOCAL_VOTACAO").first()))
    votos = lz.group_by(CHAVE + ["NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum()).collect()
    cand: dict[int, tuple[str, str]] = {}
    try:
        from apuracao import historico as h
        c = h.load_candidatos(ano, cache).filter(
            (pl.col("CD_CARGO").cast(pl.Int64, strict=False) == cargo)
            & (pl.col("SG_UF") == ("BR" if cargo == 1 else uf)))
        cand = {int(n): (f"{u} ({p}) {ano}", p) for n, u, p in
                c.select("NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO").unique("NR_CANDIDATO").iter_rows()}
    except (v.TseDataError, OSError, ValueError) as exc:
        logger.info("sem cadastro de candidatos de %s: %s", ano, exc)
    return locais, votos, cand


def _categorias(votos: pl.DataFrame, cand: dict[int, tuple[str, str]], ano: int, min_pct: float, maximo: int
                ) -> tuple[list[int], dict[int, str]]:
    c = (votos.filter(~pl.col("NR_VOTAVEL").is_in(tf.NAO_CANDIDATOS)).group_by("NR_VOTAVEL")
         .agg(pl.col("QT_VOTOS").sum()).sort("QT_VOTOS", descending=True))
    validos = c["QT_VOTOS"].sum() or 1
    grupos = [n for n, q in c.iter_rows() if 100 * q / validos >= min_pct][:maximo]
    return grupos, {n: cand.get(n, (f"nº {n} {ano}", ""))[0] for n in grupos}


def montar(ano_a: int, a: tuple, ano_b: int, b: tuple, municipio: int | None = None,
           min_pct: float = tf.MIN_PCT_GRUPO, maximo: int = tf.MAX_ELIMINADOS, descricao: str = "") -> tf.Unidades:
    """`a`, `b`: o que `carregar_ano` devolve para cada ano. Unidades no formato de `transferencia.Unidades`
    (lado 1 = ano A, lado 2 = ano B), com `mapa_swing` pelo partido."""
    (loc_a, vot_a, cand_a), (loc_b, vot_b, cand_b) = a, b
    if municipio is not None:
        loc_a, vot_a = loc_a.filter(pl.col("CD_MUNICIPIO") == municipio), vot_a.filter(pl.col("CD_MUNICIPIO") == municipio)
        loc_b, vot_b = loc_b.filter(pl.col("CD_MUNICIPIO") == municipio), vot_b.filter(pl.col("CD_MUNICIPIO") == municipio)
    g_a, rot_a = _categorias(vot_a, cand_a, ano_a, min_pct, maximo)
    g_b, rot_b = _categorias(vot_b, cand_b, ano_b, min_pct, maximo)
    if not g_a or not g_b:
        raise v.TseDataError("sem candidatos com votos na área escolhida")
    cat1 = [rot_a[n] for n in g_a] + [tf.OUTROS, tf.BRANCO_NULO, tf.ABSTENCAO]
    cat2 = [rot_b[n] for n in g_b] + [tf.OUTROS, tf.BRANCO_NULO, tf.ABSTENCAO]

    def largas(vot: pl.DataFrame, grupos: list[int], rot: dict[int, str], lado: int) -> pl.DataFrame:
        n = pl.col("NR_VOTAVEL")
        e = pl.when(n.is_in(tf.NAO_CANDIDATOS)).then(pl.lit(tf.BRANCO_NULO))
        for numero in grupos:
            e = e.when(n == numero).then(pl.lit(rot[numero]))
        w = (vot.with_columns(e.otherwise(pl.lit(tf.OUTROS)).alias("CAT")).group_by(CHAVE + ["CAT"])
             .agg(pl.col("QT_VOTOS").sum()).pivot(on="CAT", index=CHAVE, values="QT_VOTOS"))
        cats = [c for c in (cat1 if lado == 1 else cat2) if c != tf.ABSTENCAO]
        w = w.with_columns([pl.lit(0).alias(c) for c in cats if c not in w.columns])
        return w.select(CHAVE + [pl.col(c).fill_null(0).alias(f"{lado}:{c}") for c in cats])

    s = (loc_a.rename({"APTOS": "APTOS_1"}).join(loc_b.select(CHAVE + [pl.col("APTOS").alias("APTOS_2")]), on=CHAVE)
         .join(largas(vot_a, g_a, rot_a, 1), on=CHAVE).join(largas(vot_b, g_b, rot_b, 2), on=CHAVE))
    antes = s.height
    s = s.filter((pl.col("APTOS_2") / pl.col("APTOS_1")).is_between(1 / VARIACAO_MAX, VARIACAO_MAX))
    logger.info("locais nos dois anos: %d; fora por eleitorado muito diferente: %d", antes, antes - s.height)
    v1 = pl.sum_horizontal([f"1:{c}" for c in cat1 if c != tf.ABSTENCAO])
    v2 = pl.sum_horizontal([f"2:{c}" for c in cat2 if c != tf.ABSTENCAO])
    s = (s.with_columns((pl.col("APTOS_1") - v1).clip(0).alias(f"1:{tf.ABSTENCAO}"),
                        (pl.col("APTOS_2") - v2).clip(0).alias(f"2:{tf.ABSTENCAO}"))
         .with_columns(pl.max_horizontal("APTOS_1", v1).alias("APTOS_1"), pl.max_horizontal("APTOS_2", v2).alias("APTOS_2"))
         .filter((pl.col("APTOS_1") > 0) & (pl.col("APTOS_2") > 0))
         .with_columns(pl.format("{}-{}-{}", *CHAVE).alias("UNIDADE"))
         .with_columns(pl.col("UNIDADE").alias("GRUPO"), pl.col("NM_LOCAL_VOTACAO").alias("NOME")))
    cat1 = [c for c in cat1 if c in (tf.BRANCO_NULO, tf.ABSTENCAO) or s[f"1:{c}"].sum() > 0]
    cat2 = [c for c in cat2 if c in (tf.BRANCO_NULO, tf.ABSTENCAO) or s[f"2:{c}"].sum() > 0]
    # swing uniforme: cada categoria de B ↔ a do MESMO partido em A (Flávio/PL 2026 ↔ Bolsonaro/PL 2022); sem
    # correspondente (partido novo, outro partido), ↔ "Outros"
    sigla_a = {rot_a[n]: cand_a.get(n, ("", ""))[1] for n in g_a}
    sigla_b = {rot_b[n]: cand_b.get(n, ("", ""))[1] for n in g_b}
    mapa = []
    for c in cat2:
        if c in (tf.OUTROS, tf.BRANCO_NULO, tf.ABSTENCAO):
            mapa.append(cat1.index(c) if c in cat1 else cat1.index(tf.OUTROS))
            continue
        par = [ca for ca in cat1 if ca in sigla_a and sigla_a[ca]
               and pt.descendente(sigla_a[ca], ano_a, ano_b) == pt.chave(sigla_b.get(c))]
        mapa.append(cat1.index(par[0]) if par else (cat1.index(tf.OUTROS) if tf.OUTROS in cat1 else 0))
    cols = ["UNIDADE", "GRUPO", "NOME", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"]
    tab = s.select(cols + ["APTOS_1", "APTOS_2"] + [f"1:{c}" for c in cat1] + [f"2:{c}" for c in cat2]).sort("UNIDADE")
    return tf.Unidades(tab, cat1, cat2, "local", descricao or f"{ano_a} → {ano_b}, por local de votação",
                       [], mapa)


def calcular(ano_a: int, ano_b: int, uf: str, cargo: int, cache: Path, municipio: int | None = None,
             n_boot: int = 100) -> tf.Resultado:
    nome = NOMES_CARGO.get(cargo)
    if nome is None:
        raise ValueError("migração entre anos: Presidente (1) ou Governador (3) (Senador muda o nº de vagas)")
    a = carregar_ano(ano_a, uf, cargo, cache)
    b = carregar_ano(ano_b, uf, cargo, cache)
    u = montar(ano_a, a, ano_b, b, municipio,
               descricao=f"{nome.capitalize()}, {ano_a} → {ano_b}, {uf}{f' (município {municipio})' if municipio else ''}, "
                         "por local de votação")
    return tf.analisar(u, n_boot=n_boot)
