"""Abstenção × mudança de local de votação entre duas eleições (ex.: 2022 → 2026), por seção (rodada 56).

Pergunta: as seções que mudaram de LUGAR entre as eleições tiveram abstenção maior (ou menor) que as que
ficaram, e isso tirou votos de quem, para Presidente e Governador?

  seção        (município, zona, nº), a chave do TSE; só entram no efeito as seções PRINCIPAIS com aptos nos dois
               anos (nova, extinta ou agregada num dos anos: listada com o motivo, fora do efeito).
  lugar        o local onde a urna funcionou (arquivo de votação), com endereço e coordenadas do cadastro do ano.
               O nº do local NÃO identifica o prédio (RJ 2022 → 2026: 2.760 seções com o mesmo nº e outro nome e
               outro endereço) e as coordenadas também não (o TSE repete o ponto em prédios diferentes; o cadastro
               de 2026 foi regeocodificado). Mesmo lugar = mesmo nome OU mesmo endereço (`compact`) OU, até 150 m,
               nomes parecidos (`similaridade` ≥ 0,5, sem as palavras genéricas). A distância é só a faixa.
  classes      MUDOU (outro lugar) · RENUMERADO (outro nº, mesmo lugar: fora do efeito) · MANTEVE (controle) ·
               FORA (sem par no outro ano).
  efeito       diferença em diferenças DENTRO DA ZONA: Δ abstenção da seção (p.p., ano novo − base) − Δ das
               seções MANTEVE da mesma zona (ponderado pelos aptos). Eleitores a mais abstendo = excesso × aptos.
               IC por bootstrap de LOCAIS (seções do mesmo local não são independentes), semente fixa.
  candidatos   (a) votos perdidos estimados: o excesso de cada seção MUDOU repartido como votou quem
               compareceu nela no ano novo; (b) desempenho por partido: % do eleitorado de cada partido (ligado
               pela entidade, `partidos.correspondencia`) nos dois anos, MUDOU × MANTEVE da mesma zona.

Inferência ECOLÓGICA (seções, não pessoas); o eleitorado de uma seção muda entre eleições (`VAR_MAX_PCT`:
sensibilidade sem as seções com eleitorado muito diferente); (a) supõe que quem se absteve votaria como quem foi.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

import votos_por_local_votacao as v
from apuracao import eleitorado as el
from apuracao import partidos as pt

logger = logging.getLogger("apuracao.abstencao_locais")

CHAVE = list(el.SECTION_KEY)
PRESIDENTE, GOVERNADOR = 1, 3
CARGOS = {PRESIDENTE: "Presidente", GOVERNADOR: "Governador"}
PERTO_M = 150.0            # até aqui, nomes parecidos = o mesmo prédio (mesmo critério de `locais.MOVE_THRESHOLD_M`)
SIMILAR_MIN = 0.5
VAR_MAX_PCT = 50.0         # sensibilidade: fora as seções cujo eleitorado variou mais que isto
BOOTSTRAP, SEMENTE = 1000, 2026
MUDOU, RENUMERADO, MANTEVE, FORA = "MUDOU", "RENUMERADO", "MANTEVE", "FORA"
FAIXAS = [(PERTO_M, "até 150 m"), (500.0, "150–500 m"), (2000.0, "0,5–2 km"), (float("inf"), "mais de 2 km")]
SEM_COORDENADA = "sem coordenada"
# palavras que não distinguem um prédio de outro ("E. M." / "ESCOLA MUNICIPAL"...)
GENERICAS = {"ESCOLA", "ESC", "MUNICIPAL", "MUNICIPALIZADA", "ESTADUAL", "COLEGIO", "COL", "CE", "EM", "EE", "E", "M",
             "DE", "DA", "DO", "DAS", "DOS", "D", "O", "A", "AS", "OS", "PROF", "PROFESSOR", "PROFESSORA", "DR",
             "DOUTOR", "DRA", "CIEP", "CRECHE", "UNIDADE", "ANEXO", "INSTITUTO", "CENTRO", "EDUCACIONAL", "ENSINO",
             "FUNDAMENTAL", "MEDIO", "TECNICO", "FEDERAL", "SECOES", "SECAO", "LTDA", "SA", "PREDIO", "BLOCO"}


def tokens(nome: str | None) -> frozenset[str]:
    palavras = re.split(r"[^A-Z0-9]+", v.normalize_text(nome))
    return frozenset(p for p in palavras if p and p not in GENERICAS)


def similaridade(a: str | None, b: str | None) -> float:
    """Sobreposição das palavras que distinguem os nomes (|A∩B| / min(|A|,|B|)); 0 se um lado não tiver nenhuma."""
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0


# --------------------------------------------------------------------------
# Leitura (microdados do cache)
# --------------------------------------------------------------------------
def secoes_do_ano(ano: int, uf: str, cache: Path, turno: int = 1) -> pl.DataFrame:
    """Uma linha por seção principal com voto no ano: local (do arquivo de votação), endereço e coordenadas (do
    cadastro), aptos/comparecimento/abstenções de Presidente e de Governador (detalhe por seção)."""
    uf = uf.upper()
    votos = (v.load_section_votes(ano, uf, "governador", cache, False)
             .filter((pl.col("NR_TURNO") == turno) & (pl.col("SG_UF") == uf))
             .select(CHAVE + ["NM_MUNICIPIO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO"]).unique(CHAVE).collect())
    cad = (el.load_sections(ano, uf, cache).select(v.LOCAL_KEY + ["DS_ENDERECO", "NM_BAIRRO", "NR_LATITUDE", "NR_LONGITUDE"])
           .unique(v.LOCAL_KEY, keep="first"))
    det = (v.load_section_details(ano, uf, cache).filter((pl.col("NR_TURNO") == turno)
                                                          & pl.col("CD_CARGO").is_in([PRESIDENTE, GOVERNADOR])).collect())
    largo = [det.filter(pl.col("CD_CARGO") == c).select(
        CHAVE + [pl.col("QT_APTOS").alias(f"APTOS{s}"), pl.col("QT_COMPARECIMENTO").alias(f"COMPARECIMENTO{s}"),
                 pl.col("QT_ABSTENCOES").alias(f"ABSTENCOES{s}")]) for c, s in ((PRESIDENTE, ""), (GOVERNADOR, "_GOV"))]
    return (votos.join(cad, on=v.LOCAL_KEY, how="left").join(largo[0], on=CHAVE, how="left")
            .join(largo[1], on=CHAVE, how="left"))


def votos_do_ano(ano: int, uf: str, cache: Path, turno: int = 1) -> pl.DataFrame:
    """Votos por seção e votável de Presidente (arquivo BR, só a UF) e Governador: CHAVE, CD_CARGO, NR_VOTAVEL, QT_VOTOS."""
    uf = uf.upper()
    partes = [v.load_section_votes(ano, uf, nome, cache, False).filter(
        (pl.col("NR_TURNO") == turno) & (pl.col("SG_UF") == uf) & (pl.col("CD_CARGO") == cargo))
        for cargo, nome in ((PRESIDENTE, "presidente"), (GOVERNADOR, "governador"))]
    return (pl.concat([p.select(CHAVE + ["CD_CARGO", "NR_VOTAVEL", "QT_VOTOS"]) for p in partes])
            .group_by(CHAVE + ["CD_CARGO", "NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum()).collect())


def candidatos_do_ano(ano: int, uf: str, cache: Path, turno: int = 1) -> pl.DataFrame:
    """CD_CARGO, NUMERO, NOME (de urna), PARTIDO dos candidatos a Presidente (BR) e Governador (UF)."""
    from apuracao import historico as h

    c = h.load_candidatos(ano, cache).with_columns(pl.col("CD_CARGO", "NR_CANDIDATO", "NR_TURNO").cast(pl.Int64, strict=False))
    c = c.filter((pl.col("NR_TURNO") == turno) & (((pl.col("CD_CARGO") == PRESIDENTE) & (pl.col("SG_UF") == "BR"))
                                                  | ((pl.col("CD_CARGO") == GOVERNADOR) & (pl.col("SG_UF") == uf.upper()))))
    apto = (pl.col("DS_SITUACAO_CANDIDATURA") == "APTO").cast(pl.Int8) if "DS_SITUACAO_CANDIDATURA" in c.columns else pl.lit(0)
    return (c.with_columns(apto.alias("_A")).sort("_A", descending=True).unique(["CD_CARGO", "NR_CANDIDATO"], keep="first")
            .select("CD_CARGO", pl.col("NR_CANDIDATO").alias("NUMERO"), pl.col("NM_URNA_CANDIDATO").alias("NOME"),
                    pl.col("SG_PARTIDO").alias("PARTIDO")))


# --------------------------------------------------------------------------
# Montagem (sem I/O)
# --------------------------------------------------------------------------
def _faixa(dist: pl.Expr) -> pl.Expr:
    e = pl.when(dist.is_null()).then(pl.lit(SEM_COORDENADA))
    for limite, rotulo in FAIXAS:
        e = e.when(dist <= limite).then(pl.lit(rotulo))
    return e


def classificar(a: pl.DataFrame, b: pl.DataFrame, base: int, novo: int) -> pl.DataFrame:
    """Uma linha por seção de algum dos anos, com o local de cada ano, a distância, a semelhança dos nomes e a
    classe (MUDOU / RENUMERADO / MANTEVE / FORA) e o motivo de quem fica fora."""
    sb, sn = f"_{base}", f"_{novo}"
    cols = [c for c in a.columns if c not in CHAVE]
    j = a.rename({c: c + sb for c in cols}).join(b.rename({c: c + sn for c in cols}), on=CHAVE, how="full",
                                                    coalesce=True).rechunk()
    nome_a, nome_b = pl.col("NM_LOCAL_VOTACAO" + sb), pl.col("NM_LOCAL_VOTACAO" + sn)
    sim = pl.struct(nome_a.alias("a"), nome_b.alias("b")).map_elements(
        lambda r: similaridade(r["a"], r["b"]), return_dtype=pl.Float64)
    dist = el.haversine_m(pl.col("NR_LATITUDE" + sb), pl.col("NR_LONGITUDE" + sb),
                          pl.col("NR_LATITUDE" + sn), pl.col("NR_LONGITUDE" + sn))
    j = j.with_columns(dist.round(0).alias("DISTANCIA_M"), sim.round(2).alias("SIMILARIDADE_NOME"),
                       (el.compact_expr("NM_LOCAL_VOTACAO" + sb) == el.compact_expr("NM_LOCAL_VOTACAO" + sn)).alias("_NOME_IGUAL"),
                       (el.compact_expr("DS_ENDERECO" + sb) == el.compact_expr("DS_ENDERECO" + sn)).alias("_END_IGUAL"))
    mesmo_lugar = (pl.col("_NOME_IGUAL").fill_null(False) | pl.col("_END_IGUAL").fill_null(False)
                   | ((pl.col("DISTANCIA_M") <= PERTO_M) & (pl.col("SIMILARIDADE_NOME") >= SIMILAR_MIN)))
    sem_par = (pl.when(pl.col("NR_LOCAL_VOTACAO" + sb).is_null()).then(pl.lit(f"seção nova em {novo}"))
               .when(pl.col("NR_LOCAL_VOTACAO" + sn).is_null()).then(pl.lit(f"seção sem voto em {novo} (extinta ou agregada)"))
               .when(pl.col("APTOS" + sb).fill_null(0) == 0).then(pl.lit(f"sem aptos em {base}"))
               .when(pl.col("APTOS" + sn).fill_null(0) == 0).then(pl.lit(f"sem aptos em {novo}")))
    classe = (pl.when(sem_par.is_not_null()).then(pl.lit(FORA))
              .when(~mesmo_lugar).then(pl.lit(MUDOU))
              .when(pl.col("NR_LOCAL_VOTACAO" + sb) != pl.col("NR_LOCAL_VOTACAO" + sn)).then(pl.lit(RENUMERADO))
              .otherwise(pl.lit(MANTEVE)))
    return (j.with_columns(classe.alias("CLASSE"), sem_par.alias("MOTIVO_FORA"),
                           pl.when(classe == MUDOU).then(_faixa(pl.col("DISTANCIA_M"))).alias("FAIXA_DISTANCIA"),
                           pl.coalesce("NM_MUNICIPIO" + sn, "NM_MUNICIPIO" + sb).alias("NM_MUNICIPIO"))
            .drop("_NOME_IGUAL", "_END_IGUAL", "NM_MUNICIPIO" + sb, "NM_MUNICIPIO" + sn).sort(CHAVE))


def excesso(sec: pl.DataFrame, base: int, novo: int) -> pl.DataFrame:
    """Abstenção (%) de cada ano, Δ (p.p.), Δ das seções MANTEVE da mesma zona (controle, ponderado pelos aptos
    do ano novo), excesso (p.p.) e eleitores a mais abstendo; marca as seções com eleitorado muito diferente."""
    sb, sn = f"_{base}", f"_{novo}"
    pct = lambda s: 100 * pl.col("ABSTENCOES" + s) / pl.col("APTOS" + s)  # noqa: E731
    s = sec.with_columns(pct(sb).alias("ABST_PCT" + sb), pct(sn).alias("ABST_PCT" + sn),
                         (100 * (pl.col("APTOS" + sn) - pl.col("APTOS" + sb)) / pl.col("APTOS" + sb)).alias("VAR_APTOS_PCT"))
    s = s.with_columns((pl.col("ABST_PCT" + sn) - pl.col("ABST_PCT" + sb)).alias("DELTA_PP"),
                       (pl.col("VAR_APTOS_PCT").abs() <= VAR_MAX_PCT).alias("ELEITORADO_ESTAVEL"))
    ctrl = (s.filter(pl.col("CLASSE") == MANTEVE).group_by("CD_MUNICIPIO", "NR_ZONA")
            .agg(((pl.col("DELTA_PP") * pl.col("APTOS" + sn)).sum() / pl.col("APTOS" + sn).sum()).alias("DELTA_CONTROLE_ZONA_PP"),
                 pl.len().alias("SECOES_CONTROLE_ZONA")))
    s = s.join(ctrl, on=["CD_MUNICIPIO", "NR_ZONA"], how="left")
    efeito = pl.col("CLASSE") == MUDOU
    return s.with_columns(
        pl.when(efeito).then(pl.col("DELTA_PP") - pl.col("DELTA_CONTROLE_ZONA_PP")).alias("EXCESSO_PP"),
    ).with_columns((pl.col("EXCESSO_PP") / 100 * pl.col("APTOS" + sn)).alias("ELEITORES_A_MAIS_ABSTENDO"))


def _agg(sb: str, sn: str) -> list[pl.Expr]:
    return [pl.len().alias("SECOES"), pl.col("APTOS" + sb).sum(), pl.col("APTOS" + sn).sum(),
            pl.col("ABSTENCOES" + sb).sum(), pl.col("ABSTENCOES" + sn).sum(),
            pl.col("ELEITORES_A_MAIS_ABSTENDO").sum(),
            (pl.col("DELTA_CONTROLE_ZONA_PP") * pl.col("APTOS" + sn)).sum().alias("_CTRL")]


def _pcts(df: pl.DataFrame, sb: str, sn: str) -> pl.DataFrame:
    return df.with_columns(
        (100 * pl.col("ABSTENCOES" + sb) / pl.col("APTOS" + sb)).alias("ABST_PCT" + sb),
        (100 * pl.col("ABSTENCOES" + sn) / pl.col("APTOS" + sn)).alias("ABST_PCT" + sn),
    ).with_columns(
        (pl.col("ABST_PCT" + sn) - pl.col("ABST_PCT" + sb)).alias("DELTA_PP"),
        (pl.col("_CTRL") / pl.col("APTOS" + sn)).alias("DELTA_CONTROLE_PP"),
        (100 * pl.col("ELEITORES_A_MAIS_ABSTENDO") / pl.col("APTOS" + sn)).alias("EXCESSO_PP"),
    ).drop("_CTRL")


def agregar(s: pl.DataFrame, por: list[str], base: int, novo: int, so_mudou: bool = True) -> pl.DataFrame:
    """Somas por grupo (numerador e denominador, nunca média de %): abstenção de cada ano, Δ, Δ do controle e
    excesso das seções que mudaram (ponderados pelos aptos do ano novo)."""
    sb, sn = f"_{base}", f"_{novo}"
    d = s.filter(pl.col("CLASSE") == MUDOU) if so_mudou else s
    return _pcts(d.group_by(por).agg(_agg(sb, sn)), sb, sn).sort(por)


def ic_bootstrap(s: pl.DataFrame, novo: int, n: int = BOOTSTRAP, semente: int = SEMENTE) -> tuple[float, float]:
    """IC 95% do excesso geral (p.p.) reamostrando os LOCAIS de destino das seções que mudaram."""
    sn = f"_{novo}"
    m = (s.filter(pl.col("CLASSE") == MUDOU)
         .group_by("CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO" + sn)
         .agg(pl.col("ELEITORES_A_MAIS_ABSTENDO").sum().alias("E"), pl.col("APTOS" + sn).sum().alias("A"))
         .sort("CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO" + sn))  # group_by não tem ordem: mesma semente, mesmo IC
    if m.height < 2:
        return (float("nan"), float("nan"))
    e, a = m["E"].to_numpy(), m["A"].to_numpy()
    idx = np.random.default_rng(semente).integers(0, len(e), size=(n, len(e)))
    est = 100 * e[idx].sum(axis=1) / a[idx].sum(axis=1)
    return float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))


def votos_perdidos(s: pl.DataFrame, votos: pl.DataFrame, candidatos: pl.DataFrame, novo: int) -> pl.DataFrame:
    """(a) Em cada seção MUDOU, os eleitores a mais abstendo repartidos como votou quem compareceu nela (por
    candidato, brancos e nulos): votos que cada um deixou de ter (negativo = ganhou). PARTE_DA_PERDA_PCT ×
    PCT_VOTOS_UF: prejudicado se perdeu mais que a sua parte dos votos."""
    m = s.filter((pl.col("CLASSE") == MUDOU) & pl.col("ELEITORES_A_MAIS_ABSTENDO").is_not_null()).select(
        CHAVE + ["ELEITORES_A_MAIS_ABSTENDO"])
    tot = votos.group_by(CHAVE + ["CD_CARGO"]).agg(pl.col("QT_VOTOS").sum().alias("_T"))
    vv = (votos.join(m, on=CHAVE, how="inner").join(tot, on=CHAVE + ["CD_CARGO"])
          .with_columns((pl.col("ELEITORES_A_MAIS_ABSTENDO") * pl.col("QT_VOTOS") / pl.col("_T")).alias("_P")))
    rotulo = pl.when(pl.col("NR_VOTAVEL") == 95).then(pl.lit("Brancos")).when(pl.col("NR_VOTAVEL") == 96).then(pl.lit("Nulos"))
    uf = votos.group_by("CD_CARGO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum().alias("VOTOS_UF"))
    nas = vv.group_by("CD_CARGO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum().alias("VOTOS_NAS_SECOES_QUE_MUDARAM"),
                                                    pl.col("_P").sum().alias("VOTOS_PERDIDOS_EST"))
    r = (uf.join(nas, on=["CD_CARGO", "NR_VOTAVEL"], how="left")
         .join(candidatos.rename({"NUMERO": "NR_VOTAVEL"}), on=["CD_CARGO", "NR_VOTAVEL"], how="left")
         .with_columns(pl.col("VOTOS_NAS_SECOES_QUE_MUDARAM", "VOTOS_PERDIDOS_EST").fill_null(0),
                       pl.coalesce(rotulo, pl.col("NOME"), pl.format("nº {}", "NR_VOTAVEL")).alias("NOME")))
    validos = ~pl.col("NR_VOTAVEL").is_in([95, 96, 97])
    return (r.with_columns(
        (100 * pl.col("VOTOS_UF") / pl.col("VOTOS_UF").filter(validos).sum().over("CD_CARGO")).alias("PCT_VALIDOS_UF"),
        (100 * pl.col("VOTOS_PERDIDOS_EST") / pl.col("VOTOS_UF")).alias("PERDA_PCT_DOS_SEUS_VOTOS"),
        (100 * pl.col("VOTOS_PERDIDOS_EST") / pl.col("VOTOS_PERDIDOS_EST").filter(validos).sum().over("CD_CARGO"))
        .alias("PARTE_DA_PERDA_PCT"),
        # o que perderia se a perda dos válidos fosse repartida pela votação dele na UF inteira
        (pl.col("VOTOS_PERDIDOS_EST") - pl.col("VOTOS_PERDIDOS_EST").filter(validos).sum().over("CD_CARGO")
         * pl.col("VOTOS_UF") / pl.col("VOTOS_UF").filter(validos).sum().over("CD_CARGO")).alias("PERDA_ALEM_DA_PROPORCIONAL"))
        .with_columns(pl.when(~validos).then(None)
                      .when(pl.col("PARTE_DA_PERDA_PCT") > pl.col("PCT_VALIDOS_UF")).then(pl.lit("prejudicado"))
                      .otherwise(pl.lit("favorecido")).alias("LEITURA"),
                      pl.col("CD_CARGO").replace_strict(CARGOS, return_dtype=pl.String).alias("CARGO"))
        .sort("CD_CARGO", "VOTOS_UF", descending=[False, True])
        .select("CARGO", pl.col("NR_VOTAVEL").alias("NUMERO"), "NOME", "PARTIDO", "VOTOS_UF", "PCT_VALIDOS_UF",
                "VOTOS_NAS_SECOES_QUE_MUDARAM", "VOTOS_PERDIDOS_EST", "PERDA_PCT_DOS_SEUS_VOTOS", "PARTE_DA_PERDA_PCT",
                pl.when(validos).then(pl.col("PERDA_ALEM_DA_PROPORCIONAL")).alias("PERDA_ALEM_DA_PROPORCIONAL"),
                "LEITURA"))


def efeito_na_margem(perdidos: pl.DataFrame, top: int = 3) -> pl.DataFrame:
    """Para cada par entre os `top` mais votados de cada cargo: quanto a abstenção a mais mexeu na margem
    (votos perdidos do 2º − do 1º do par; positivo = a margem do 1º do par cresceu)."""
    linhas = []
    for cargo in perdidos["CARGO"].unique(maintain_order=True).to_list():
        c = perdidos.filter((pl.col("CARGO") == cargo) & pl.col("LEITURA").is_not_null()).head(top).to_dicts()
        for i in range(len(c)):
            for k in range(i + 1, len(c)):
                linhas.append({"CARGO": cargo, "CANDIDATO_A": f"{c[i]['NOME']} ({c[i]['PARTIDO']})",
                               "CANDIDATO_B": f"{c[k]['NOME']} ({c[k]['PARTIDO']})",
                               "MARGEM_A_SOBRE_B": c[i]["VOTOS_UF"] - c[k]["VOTOS_UF"],
                               "EFEITO_NA_MARGEM_EST": c[k]["VOTOS_PERDIDOS_EST"] - c[i]["VOTOS_PERDIDOS_EST"]})
    return pl.DataFrame(linhas, schema={"CARGO": pl.String, "CANDIDATO_A": pl.String, "CANDIDATO_B": pl.String,
                                        "MARGEM_A_SOBRE_B": pl.Int64, "EFEITO_NA_MARGEM_EST": pl.Float64})


def desempenho_partidos(s: pl.DataFrame, votos_a: pl.DataFrame, votos_b: pl.DataFrame, cand_a: pl.DataFrame,
                        cand_b: pl.DataFrame, base: int, novo: int) -> pl.DataFrame:
    """(b) % do eleitorado (votos / aptos) de cada partido do ano novo e do MESMO partido no ano-base (entidade:
    `partidos.correspondencia`), nas seções que mudaram × nas que ficaram da mesma zona: Δ e diferença em
    diferenças (p.p., ponderada pelos aptos do ano novo). Sem candidato do partido no ano-base: nulo."""
    sb, sn = f"_{base}", f"_{novo}"
    saida = []
    for cargo in CARGOS:
        ca, cb = cand_a.filter(pl.col("CD_CARGO") == cargo), cand_b.filter(pl.col("CD_CARGO") == cargo)
        mapa_a = {n: p for n, p in ca.select("NUMERO", "PARTIDO").iter_rows() if p}
        mapa_b = {n: p for n, p in cb.select("NUMERO", "PARTIDO").iter_rows() if p}
        corr = pt.correspondencia(mapa_a, mapa_b, base, novo)
        va = votos_a.filter(pl.col("CD_CARGO") == cargo)
        vb = votos_b.filter(pl.col("CD_CARGO") == cargo)
        for numero, sigla in sorted(mapa_b.items()):
            if vb.filter(pl.col("NR_VOTAVEL") == numero).is_empty():
                continue
            antigos = corr.get(numero, [])
            x = (s.filter(pl.col("CLASSE").is_in([MUDOU, MANTEVE])).select(CHAVE + ["CLASSE", "APTOS" + sb, "APTOS" + sn])
                 .join(vb.filter(pl.col("NR_VOTAVEL") == numero).select(*CHAVE, pl.col("QT_VOTOS").alias("_VB")), on=CHAVE, how="left")
                 .join(va.filter(pl.col("NR_VOTAVEL").is_in(antigos)).group_by(CHAVE).agg(pl.col("QT_VOTOS").sum().alias("_VA")),
                       on=CHAVE, how="left")
                 .with_columns(pl.col("_VB", "_VA").fill_null(0))
                 .with_columns((100 * pl.col("_VA") / pl.col("APTOS" + sb)).alias("_PA"),
                               (100 * pl.col("_VB") / pl.col("APTOS" + sn)).alias("_PB"))
                 .with_columns((pl.col("_PB") - pl.col("_PA")).alias("_D")))
            ctrl = (x.filter(pl.col("CLASSE") == MANTEVE).group_by("CD_MUNICIPIO", "NR_ZONA")
                    .agg(((pl.col("_D") * pl.col("APTOS" + sn)).sum() / pl.col("APTOS" + sn).sum()).alias("_C")))
            m = x.filter(pl.col("CLASSE") == MUDOU).join(ctrl, on=["CD_MUNICIPIO", "NR_ZONA"], how="inner")
            w = lambda col, d=m: float((d[col] * d["APTOS" + sn]).sum() / d["APTOS" + sn].sum()) if d.height else None  # noqa: E731
            pct = lambda vcol, acol, d: float(100 * d[vcol].sum() / d[acol].sum()) if d.height else None  # noqa: E731
            mant = x.filter(pl.col("CLASSE") == MANTEVE)
            tem_base = bool(antigos)
            linha = {"CARGO": CARGOS[cargo], "NUMERO": numero, "PARTIDO": sigla,
                     "CANDIDATO": cb.filter(pl.col("NUMERO") == numero)["NOME"].first(),
                     f"PARTIDO_EM_{base}": "/".join(mapa_a[n] for n in antigos) if tem_base else None,
                     f"PCT_ELEITORADO_MUDOU{sb}": pct("_VA", "APTOS" + sb, m) if tem_base else None,
                     f"PCT_ELEITORADO_MUDOU{sn}": pct("_VB", "APTOS" + sn, m),
                     f"PCT_ELEITORADO_MANTEVE{sb}": pct("_VA", "APTOS" + sb, mant) if tem_base else None,
                     f"PCT_ELEITORADO_MANTEVE{sn}": pct("_VB", "APTOS" + sn, mant),
                     "DELTA_MUDOU_PP": w("_D") if tem_base else None,
                     "DELTA_CONTROLE_ZONA_PP": w("_C") if tem_base else None}
            linha["DIF_EM_DIF_PP"] = (linha["DELTA_MUDOU_PP"] - linha["DELTA_CONTROLE_ZONA_PP"]
                                      if tem_base and linha["DELTA_MUDOU_PP"] is not None else None)
            saida.append(linha)
    return pl.DataFrame(saida).sort("CARGO", f"PCT_ELEITORADO_MANTEVE{sn}", descending=[True, True])


@dataclass
class Relatorio:
    uf: str
    base: int
    novo: int
    turno: int
    secoes: pl.DataFrame
    resumo: pl.DataFrame
    por_faixa: pl.DataFrame
    por_municipio: pl.DataFrame
    por_zona: pl.DataFrame
    locais: pl.DataFrame
    perdidos: pl.DataFrame
    margem: pl.DataFrame
    partidos: pl.DataFrame
    ic: tuple[float, float]
    notas: list[str] = field(default_factory=list)


def montar(a: pl.DataFrame, b: pl.DataFrame, votos_a: pl.DataFrame, votos_b: pl.DataFrame, cand_a: pl.DataFrame,
           cand_b: pl.DataFrame, uf: str, base: int, novo: int, turno: int = 1) -> Relatorio:
    sb, sn = f"_{base}", f"_{novo}"
    s = excesso(classificar(a, b, base, novo), base, novo)
    estavel = s.filter(pl.col("ELEITORADO_ESTAVEL").fill_null(False))
    geral = []
    for rotulo, d in (("todas as seções que mudaram", s), (f"sem eleitorado variando > {VAR_MAX_PCT:.0f}%", estavel)):
        g = agregar(d, [], base, novo) if d.filter(pl.col("CLASSE") == MUDOU).height else None
        if g is not None and g.height:
            geral.append(g.with_columns(pl.lit(rotulo).alias("RECORTE")))
    classes = (s.group_by("CLASSE").agg(pl.len().alias("SECOES"), pl.col("APTOS" + sn).sum()).sort("CLASSE"))
    ic = ic_bootstrap(s, novo)
    resumo = pl.concat(geral, how="diagonal_relaxed") if geral else pl.DataFrame()
    locais = (s.filter(pl.col("CLASSE") == MUDOU)
              .group_by("CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO" + sb, "NM_LOCAL_VOTACAO" + sb,
                        "NR_LOCAL_VOTACAO" + sn, "NM_LOCAL_VOTACAO" + sn)
              .agg(pl.col("DISTANCIA_M").max(), pl.col("NR_SECAO").sort().cast(pl.String).str.join(",").alias("SECOES_LISTA"),
                   *_agg(sb, sn))
              .pipe(_pcts, sb, sn).sort("ELEITORES_A_MAIS_ABSTENDO", descending=True, nulls_last=True))
    perdidos = votos_perdidos(s, votos_b, cand_b, novo)
    return Relatorio(
        uf=uf.upper(), base=base, novo=novo, turno=turno, secoes=s,
        resumo=resumo, por_faixa=agregar(s, ["FAIXA_DISTANCIA"], base, novo),
        por_municipio=agregar(s, ["CD_MUNICIPIO", "NM_MUNICIPIO"], base, novo),
        por_zona=agregar(s, ["CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA"], base, novo),
        locais=locais, perdidos=perdidos, margem=efeito_na_margem(perdidos),
        partidos=desempenho_partidos(s, votos_a, votos_b, cand_a, cand_b, base, novo), ic=ic,
        notas=[f"{r['CLASSE']}: {r['SECOES']:,} seções, {r['APTOS' + sn]:,} aptos em {novo}".replace(",", ".")
               for r in classes.to_dicts()])


def gerar(uf: str, cache: Path, base: int = 2022, novo: int = 2026, turno: int = 1) -> Relatorio:
    """Lê os microdados dos dois anos no cache e monta o relatório."""
    a, b = secoes_do_ano(base, uf, cache, turno), secoes_do_ano(novo, uf, cache, turno)
    return montar(a, b, votos_do_ano(base, uf, cache, turno), votos_do_ano(novo, uf, cache, turno),
                  candidatos_do_ano(base, uf, cache, turno), candidatos_do_ano(novo, uf, cache, turno),
                  uf, base, novo, turno)


# --------------------------------------------------------------------------
# Planilha
# --------------------------------------------------------------------------
def _leia_me(r: Relatorio) -> list[tuple[str, str]]:
    b, n = r.base, r.novo
    return [
        ("Pergunta", f"As seções que mudaram de LUGAR de votação entre {b} e {n} ({r.uf}, {r.turno}º turno) tiveram "
                     "abstenção diferente das que ficaram? Quem ganhou ou perdeu com isso (Presidente e Governador)?"),
        ("Seção", "chave do TSE: município + zona + nº da seção. Só entram as seções principais com aptos nos dois anos."),
        ("Lugar", "local onde a urna funcionou (arquivo de votação), endereço e coordenadas do cadastro de cada ano. "
                  "O nº do local NÃO identifica o prédio (o TSE reaproveita números e repete coordenadas): mesmo lugar = "
                  "mesmo nome OU mesmo endereço (só letras e dígitos) OU, até 150 m, nomes parecidos."),
        ("MUDOU (amarelo)", "a seção foi para outro prédio. Faixa de distância: até 150 m (vizinho), 150–500 m, "
                            "0,5–2 km, mais de 2 km, sem coordenada."),
        ("RENUMERADO (cinza)", "outro nº de local, mesmo prédio: fora do efeito."),
        ("MANTEVE", "mesmo nº e mesmo prédio: grupo de comparação."),
        ("FORA (cinza)", "seção nova, extinta/agregada ou sem aptos num dos anos: fora do efeito (motivo na coluna)."),
        ("Abstenção", "abstenções / aptos de Presidente (detalhe por seção do TSE); a de Governador também vai na aba Seções."),
        ("EXCESSO_PP", f"Δ abstenção da seção ({n} − {b}, p.p.) − Δ das seções MANTEVE da MESMA ZONA (ponderado pelos "
                       "aptos). Positivo = a seção que mudou passou a se abster mais que as vizinhas que ficaram."),
        ("ELEITORES_A_MAIS_ABSTENDO", f"EXCESSO_PP × aptos de {n}. Somado em cada grupo (nunca média de %)."),
        ("IC 95%", "bootstrap dos locais de destino (seções do mesmo local não são independentes), 1.000 reamostras, "
                   "semente fixa."),
        ("Votos perdidos (a)", f"em cada seção que mudou, os eleitores a mais abstendo repartidos como votou quem "
                               f"compareceu nela em {n} (VOTOS_PERDIDOS_EST; negativo = ganhou)."),
        ("Duas leituras", "EFEITO_NA_MARGEM_EST (aba Margem) = votos perdidos de B − de A: quanto a abstenção a mais "
                          "mexeu na distância entre os dois, em votos (negativo = a vantagem de A diminuiu). LEITURA / "
                          "PERDA_ALEM_DA_PROPORCIONAL = perdeu mais (prejudicado) ou menos (favorecido) do que perderia "
                          "se a perda fosse repartida pela votação dele na UF: diz se as seções que mudaram eram mais "
                          "ou menos dele que a média. O mais votado pode perder mais votos em número e ainda assim ser "
                          "'favorecido' nessa leitura."),
        ("Partidos (b)", f"% do eleitorado (votos / aptos) do partido em {b} e {n} (mesmo partido pela entidade: "
                         "fusões e renomeações), seções que mudaram × que ficaram na mesma zona: diferença em diferenças."),
        ("Ressalvas", "inferência ECOLÓGICA (seções, não pessoas); o nº da seção pode ter sido reaproveitado; o "
                      "eleitorado da seção muda entre eleições (veja o recorte sem variação > 50%); (a) supõe que quem "
                      "se absteve votaria como quem compareceu."),
    ]


def escrever(r: Relatorio, destino: Path) -> Path:
    """A planilha (xlsxwriter): LEIA-ME, Resumo, Seções (MUDOU em amarelo; fora do efeito em cinza), Locais,
    Zonas, Municípios, Candidatos, Margem e Partidos."""
    from xlsxwriter import Workbook

    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp.xlsx")
    sn = f"_{r.novo}"
    with Workbook(str(tmp), {"nan_inf_to_errors": True}) as wb:
        neg = wb.add_format({"bold": True})
        amarelo = wb.add_format({"bg_color": "#FFF2CC"})
        cinza = wb.add_format({"bg_color": "#E7E6E6", "font_color": "#595959"})
        quebra = wb.add_format({"text_wrap": True, "valign": "top"})

        ws = wb.add_worksheet("LEIA-ME")
        ws.set_column(0, 0, 26)
        ws.set_column(1, 1, 120, quebra)
        for i, (k, t) in enumerate(_leia_me(r)):
            ws.write(i, 0, k, neg)
            ws.write(i, 1, t)

        ws = wb.add_worksheet("Resumo")
        linha = 0
        ws.write(linha, 0, f"Abstenção × mudança de local — {r.uf}, {r.base} → {r.novo}, {r.turno}º turno", neg)
        linha += 2
        for nota in r.notas:
            ws.write(linha, 0, nota)
            linha += 1
        linha += 1
        geral = r.resumo.row(0, named=True) if r.resumo.height else {}
        br = lambda x: f"{x:+.2f}".replace(".", ",")  # noqa: E731
        if geral:
            eleitores = f"{geral['ELEITORES_A_MAIS_ABSTENDO']:,.0f}".replace(",", ".")
            ws.write(linha, 0, f"Excesso de abstenção nas seções que mudaram: {br(geral['EXCESSO_PP'])} p.p. (IC 95% "
                               f"por bootstrap de locais: {br(r.ic[0])} a {br(r.ic[1])}); {eleitores} eleitores a mais "
                               "abstendo", neg)
        linha += 2
        for titulo, df in (("Geral", r.resumo), ("Por faixa de distância", r.por_faixa),
                           ("Candidatos — votos perdidos estimados (a)", r.perdidos),
                           ("Efeito na margem entre os mais votados (a)", r.margem),
                           ("Partidos — diferença em diferenças (b)", r.partidos)):
            ws.write(linha, 0, titulo, neg)
            linha = _tabela(ws, df, linha + 1, neg) + 2

        for nome, df in (("Seções", r.secoes), ("Locais que mudaram", r.locais), ("Zonas", r.por_zona),
                         ("Municípios", r.por_municipio), ("Candidatos", r.perdidos), ("Margem", r.margem),
                         ("Partidos", r.partidos)):
            ws = wb.add_worksheet(nome)
            fim = _tabela(ws, df, 0, neg)
            ws.freeze_panes(1, 0)
            if nome == "Seções" and df.height:
                col = df.columns.index("CLASSE")
                letra = _letra(col)
                ultima = _letra(len(df.columns) - 1)
                ws.conditional_format(1, 0, fim, len(df.columns) - 1, {
                    "type": "formula", "criteria": f'=${letra}2="{MUDOU}"', "format": amarelo})
                ws.conditional_format(1, 0, fim, len(df.columns) - 1, {
                    "type": "formula", "criteria": f'=OR(${letra}2="{RENUMERADO}",${letra}2="{FORA}")', "format": cinza})
                ws.autofilter(0, 0, fim, len(df.columns) - 1)
                del ultima
    tmp.replace(destino)
    logger.info("planilha: %s (%d seções, %s mudaram)", destino, r.secoes.height,
                r.secoes.filter(pl.col("CLASSE") == MUDOU).height)
    return destino


def _letra(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, rto = divmod(i - 1, 26)
        s = chr(65 + rto) + s
    return s


def _tabela(ws, df: pl.DataFrame, linha: int, cab) -> int:
    """Escreve `df` a partir de `linha` (cabeçalho + linhas); floats com 2 casas. Devolve a última linha escrita."""
    if df.is_empty():
        ws.write(linha, 0, "(sem dados)")
        return linha
    for j, c in enumerate(df.columns):
        ws.write(linha, j, c, cab)
        ws.set_column(j, j, max(10, min(40, len(c) + 2)))
    for i, row in enumerate(df.iter_rows(), start=linha + 1):
        for j, val in enumerate(row):
            if isinstance(val, float):
                ws.write_number(i, j, round(val, 2)) if np.isfinite(val) else ws.write_blank(i, j, None)
            elif val is None:
                ws.write_blank(i, j, None)
            else:
                ws.write(i, j, val)
    return linha + df.height
