"""Transferência de votos do 1º para o 2º turno (inferência ecológica) e abstenção extra.

Pergunta: dos eleitores de cada opção do 1º turno (os dois finalistas, os eliminados, branco/nulo,
abstenção), que fração foi para cada opção do 2º turno (finalista A, finalista B, branco/nulo, abstenção)?

Ninguém sabe o voto de cada eleitor: só os totais de cada UNIDADE (seção, local de votação ou município)
nos dois turnos. O modelo supõe a MESMA matriz de transferência B em todas as unidades da área:

    y_i ≈ x_i · B        x_i = composição do 1º turno na unidade i (frações do eleitorado apto, soma 1)
                         y_i = composição do 2º turno (idem), B = K × J, linhas somam 1, B ≥ 0

e estima B por mínimos quadrados ponderados pelo eleitorado, com as restrições (FISTA com projeção de
cada linha no simplex; só numpy). As seções são as mesmas nos dois turnos (mesmos eleitores), o que faz
da seção a melhor unidade; local e município servem de comparação (viés de agregação).

Ressalvas (vão para a tela e para a planilha): correlação ECOLÓGICA — B é o padrão médio que melhor
explica as diferenças entre unidades, não o voto de pessoas; se o comportamento varia com a composição
da unidade, B fica enviesado. O intervalo (bootstrap por local) mede só a variação amostral, não esse viés.
A validação com 2022 (`validar`) mede o erro fora da amostra contra o "swing uniforme".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

import votos_por_local_votacao as v
from apuracao import projecao as pj

logger = logging.getLogger("apuracao.transferencia")

BRANCO_NULO, ABSTENCAO, OUTROS, ELIMINADOS = "Branco/nulo", "Abstenção", "Outros", "Eliminados"
NAO_CANDIDATOS = (95, 96, 97)          # branco, nulo, anulado em separado
MIN_PCT_GRUPO = 1.0                    # eliminado com ≥ 1% dos válidos do 1º turno na área vira grupo próprio
MAX_ELIMINADOS = 5                     # os demais vão para "Outros"
NIVEIS = ("secao", "local", "municipio")
NOMES_CARGO = {1: "presidente", 3: "governador", 5: "senador", 11: "prefeito"}
SECAO = ["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]


# --------------------------------------------------------------------------
# Estimação (numpy puro)
# --------------------------------------------------------------------------
def projetar_simplex(m: np.ndarray) -> np.ndarray:
    """Projeção euclidiana de cada LINHA no simplex {b ≥ 0, Σb = 1} (Duchi et al., 2008)."""
    k = m.shape[1]
    u = -np.sort(-m, axis=1)
    css = np.cumsum(u, axis=1) - 1.0
    ind = np.arange(1, k + 1)
    rho = np.count_nonzero(u - css / ind > 0, axis=1)
    theta = css[np.arange(m.shape[0]), rho - 1] / rho
    return np.maximum(m - theta[:, None], 0.0)


def estimar(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """B (K×J) que minimiza Σ w_i ‖y_i − x_i B‖² com linhas no simplex. Convexo: FISTA converge ao ótimo."""
    xw = x * w[:, None]
    return _fista(xw.T @ x, xw.T @ y)             # a função só depende destas duas matrizes pequenas


def _fista(g: np.ndarray, c: np.ndarray, iteracoes: int = 10_000, tol: float = 1e-10,
           b0: np.ndarray | None = None) -> np.ndarray:
    return _fista_lote(g[None], c[None], iteracoes, tol, None if b0 is None else b0[None])[0]


def _fista_lote(g: np.ndarray, c: np.ndarray, iteracoes: int = 10_000, tol: float = 1e-10,
                b0: np.ndarray | None = None) -> np.ndarray:
    """FISTA com reinício adaptativo (O'Donoghue & Candès, 2015), para S problemas de uma vez (g: S×K×K,
    c: S×K×J; um por estrato): vetorizado, o laço em Python roda uma vez para todos. G é mal condicionada
    (10⁴ nas seções, 10⁶ nos municípios do RJ): sem o reinício, 5.000 iterações ainda erravam 0,1 p.p.;
    com ele, < 10⁻⁵. `b0`: ponto de partida (o bootstrap parte da estimativa)."""
    s_, k, j = c.shape
    passo = 1.0 / (2.0 * np.maximum(np.linalg.eigvalsh(g).max(axis=1), 1e-12))[:, None, None]
    b = np.full((s_, k, j), 1.0 / j) if b0 is None else b0.copy()
    z, t = b.copy(), np.ones(s_)
    ativo = np.arange(s_)                  # só os estratos que ainda não convergiram seguem iterando
    for _ in range(iteracoes):
        ga, ca, za, ba, ta = g[ativo], c[ativo], z[ativo], b[ativo], t[ativo]
        novo = projetar_simplex((za - passo[ativo] * 2.0 * (ga @ za - ca)).reshape(-1, j)).reshape(-1, k, j)
        dif = np.abs(novo - ba).max(axis=(1, 2))
        volta = np.sum((za - novo) * (novo - ba), axis=(1, 2)) > 0   # o momento apontou para trás: recomeça
        t_novo = (1 + np.sqrt(1 + 4 * ta * ta)) / 2
        mom = np.where(volta, 0.0, (ta - 1) / t_novo)[:, None, None]
        z[ativo] = novo + mom * (novo - ba)
        t[ativo] = np.where(volta, 1.0, t_novo)
        b[ativo] = novo
        ativo = ativo[dif >= tol]
        if not len(ativo):
            break
    return b


# --------------------------------------------------------------------------
# Dados: unidades com a composição dos dois turnos
# --------------------------------------------------------------------------
@dataclass
class Unidades:
    """Contagens por unidade. Colunas: UNIDADE, CD_MUNICIPIO, NM_MUNICIPIO, GRUPO (bloco do bootstrap),
    NOME (rótulo), APTOS_1, APTOS_2 e uma coluna por categoria: "1:<cat>" e "2:<cat>" (eleitores)."""

    tabela: pl.DataFrame
    cat1: list[str]
    cat2: list[str]
    nivel: str
    descricao: str
    finalistas: list[str] = field(default_factory=list)

    def matrizes(self, t: pl.DataFrame | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        t = self.tabela if t is None else t
        a1 = t["APTOS_1"].to_numpy().astype(float)
        a2 = t["APTOS_2"].to_numpy().astype(float)
        x = t.select([f"1:{c}" for c in self.cat1]).to_numpy().astype(float) / a1[:, None]
        y = t.select([f"2:{c}" for c in self.cat2]).to_numpy().astype(float) / a2[:, None]
        return x, y, a1


def _categorias(votos: pl.DataFrame, nomes: dict[int, str], min_pct: float, max_eliminados: int
                ) -> tuple[list[int], list[int], dict[int, str]]:
    """(finalistas, eliminados com grupo próprio, rótulo de cada número) a partir dos votos da ÁREA."""
    cand2 = (votos.filter((pl.col("NR_TURNO") == 2) & ~pl.col("NR_VOTAVEL").is_in(NAO_CANDIDATOS))
             .group_by("NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum()).sort("QT_VOTOS", descending=True))
    if cand2.height != 2:
        raise v.TseDataError(f"o 2º turno precisa de 2 candidatos na área; há {cand2.height}")
    finalistas = cand2["NR_VOTAVEL"].to_list()
    c1 = (votos.filter((pl.col("NR_TURNO") == 1) & ~pl.col("NR_VOTAVEL").is_in(NAO_CANDIDATOS))
          .group_by("NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum()).sort("QT_VOTOS", descending=True))
    validos = c1["QT_VOTOS"].sum() or 1
    elim = [n for n, q in c1.iter_rows() if n not in finalistas and 100 * q / validos >= min_pct][:max_eliminados]
    rot = {n: nomes.get(n, str(n)) for n in finalistas + elim}
    return finalistas, elim, rot


def montar_unidades(secoes: pl.DataFrame, votos: pl.DataFrame, nomes: dict[int, str], nivel: str = "local",
                    municipio: int | None = None, min_pct: float = MIN_PCT_GRUPO,
                    max_eliminados: int | None = None, descricao: str = "") -> Unidades:
    """`secoes`: uma linha por seção com CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, NR_SECAO, NR_LOCAL_VOTACAO,
    NM_LOCAL_VOTACAO, APTOS_1, APTOS_2. `votos`: NR_TURNO, CD_MUNICIPIO, NR_ZONA, NR_SECAO, NR_VOTAVEL, QT_VOTOS.
    A abstenção é o eleitorado apto menos os votos (as categorias somam o eleitorado em cada turno).
    `max_eliminados` None: 5 grupos próprios em seções e locais; nos MUNICÍPIOS, um grupo só ("Eliminados") —
    com 92 unidades, separar os eliminados deixava 15 das 28 células no limite (ex.: Ciro → 100% Lula, RJ 2022)."""
    if max_eliminados is None:
        max_eliminados = 0 if nivel == "municipio" else MAX_ELIMINADOS
    if nivel not in NIVEIS:
        raise ValueError(f"nível deve ser um de {NIVEIS}")
    if municipio is not None:
        secoes = secoes.filter(pl.col("CD_MUNICIPIO") == municipio)
        votos = votos.filter(pl.col("CD_MUNICIPIO") == municipio)
    if secoes.is_empty():
        raise v.TseDataError("nenhuma seção na área escolhida")
    finalistas, elim, rot = _categorias(votos, nomes, min_pct, max_eliminados)
    resto = OUTROS if elim else ELIMINADOS
    cat1 = [rot[n] for n in finalistas + elim] + [resto, BRANCO_NULO, ABSTENCAO]
    cat2 = [rot[n] for n in finalistas] + [BRANCO_NULO, ABSTENCAO]

    def rotulo(turno: int) -> pl.Expr:
        n = pl.col("NR_VOTAVEL")
        grupos = finalistas if turno == 2 else finalistas + elim
        e = pl.when(n.is_in(NAO_CANDIDATOS)).then(pl.lit(BRANCO_NULO))
        for numero in grupos:
            e = e.when(n == numero).then(pl.lit(rot[numero]))
        return e.otherwise(pl.lit(resto))

    largas = []
    for turno, cats in ((1, cat1), (2, cat2)):
        vt = (votos.filter(pl.col("NR_TURNO") == turno).with_columns(rotulo(turno).alias("CAT"))
              .group_by(SECAO + ["CAT"]).agg(pl.col("QT_VOTOS").sum())
              .pivot(on="CAT", index=SECAO, values="QT_VOTOS"))
        faltam = [c for c in cats if c != ABSTENCAO and c not in vt.columns]
        vt = vt.with_columns([pl.lit(0).alias(c) for c in faltam]).rename(
            {c: f"{turno}:{c}" for c in cats if c != ABSTENCAO})
        largas.append(vt.select(SECAO + [f"{turno}:{c}" for c in cats if c != ABSTENCAO]))
    s = (secoes.join(largas[0], on=SECAO, how="inner").join(largas[1], on=SECAO, how="inner")
         .with_columns(pl.col("^[12]:.*$").fill_null(0)))
    if nivel == "secao":
        s = s.with_columns(pl.format("{}-{}-{}", *SECAO).alias("UNIDADE"),
                           pl.format("{}-{}-{}", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO").alias("GRUPO"),
                           pl.format("{} (zona {}, seção {})", "NM_LOCAL_VOTACAO", "NR_ZONA", "NR_SECAO").alias("NOME"))
    else:
        chave = ["CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"] if nivel == "local" else ["CD_MUNICIPIO"]
        soma = [pl.col("APTOS_1").sum(), pl.col("APTOS_2").sum(), pl.col("^[12]:.*$").sum(),
                pl.col("NM_MUNICIPIO").first(), pl.col("NM_LOCAL_VOTACAO").first(), pl.len().alias("SECOES")]
        s = s.group_by(chave).agg(soma)
        if nivel == "local":
            s = s.with_columns(pl.format("{}-{}-{}", *chave).alias("UNIDADE"), pl.col("NM_LOCAL_VOTACAO").alias("NOME"))
        else:
            s = s.with_columns(pl.col("CD_MUNICIPIO").cast(pl.String).alias("UNIDADE"),
                               pl.col("NM_MUNICIPIO").alias("NOME"))
        s = s.with_columns(pl.col("UNIDADE").alias("GRUPO"))
    votos1 = pl.sum_horizontal([f"1:{c}" for c in cat1 if c != ABSTENCAO])
    votos2 = pl.sum_horizontal([f"2:{c}" for c in cat2 if c != ABSTENCAO])
    s = s.with_columns((pl.col("APTOS_1") - votos1).clip(0).alias(f"1:{ABSTENCAO}"),
                       (pl.col("APTOS_2") - votos2).clip(0).alias(f"2:{ABSTENCAO}"))
    # eleitorado da unidade = aptos (a abstenção fecha a conta; seção com mais votos que aptos fica com 0)
    s = s.with_columns(pl.max_horizontal("APTOS_1", votos1).alias("APTOS_1"),
                       pl.max_horizontal("APTOS_2", votos2).alias("APTOS_2")).filter(
        (pl.col("APTOS_1") > 0) & (pl.col("APTOS_2") > 0))
    # grupo do 1º turno sem nenhum eleitor na área (ex.: "Outros" em Petrópolis 2024) não tem linha na matriz
    cat1 = [c for c in cat1 if c in (BRANCO_NULO, ABSTENCAO) or c in [rot[n] for n in finalistas]
            or s[f"1:{c}"].sum() > 0]
    cols = ["UNIDADE", "GRUPO", "NOME", "CD_MUNICIPIO", "NM_MUNICIPIO"] + (["NR_ZONA", "NR_LOCAL_VOTACAO"]
                                                                          if nivel != "municipio" else [])
    tab = s.select(cols + ["APTOS_1", "APTOS_2"] + [f"1:{c}" for c in cat1] + [f"2:{c}" for c in cat2])
    return Unidades(tab.sort("UNIDADE"), cat1, cat2, nivel, descricao, [rot[n] for n in finalistas])


def carregar_microdados(ano: int, uf: str, cargo: int, cache: Path, municipio: int | None = None
                        ) -> tuple[pl.DataFrame, pl.DataFrame, dict[int, str]]:
    """(seções, votos, nomes) dos dois turnos a partir dos microdados do TSE (votacao_secao + detalhe).
    Prefeito: `municipio` obrigatório — o número do candidato se repete entre municípios (e o nome também
    seria o de outro candidato)."""
    if cargo == 11 and municipio is None:
        raise ValueError("prefeito: escolha um município (o número do candidato só vale dentro dele)")
    uf = uf.upper()
    if cargo not in NOMES_CARGO:
        raise ValueError(f"cargo {cargo} não tem 2º turno (use 1, 3 ou 11)")
    det = (pj.detalhe_nacional(ano, cache).filter(pl.col("SG_UF") == uf) if cargo == 1
           else v.load_section_details(ano, uf, cache))
    det = det.filter(pl.col("CD_CARGO") == cargo).select("NR_TURNO", *SECAO, pl.col("QT_APTOS")).collect()
    aptos = det.pivot(on="NR_TURNO", index=SECAO, values="QT_APTOS", aggregate_function="sum")
    if "2" not in aptos.columns:
        raise v.TseDataError(f"sem 2º turno de {NOMES_CARGO[cargo]} em {ano} ({uf})")
    aptos = aptos.rename({"1": "APTOS_1", "2": "APTOS_2"}).drop_nulls(["APTOS_1", "APTOS_2"])
    lz = v.load_section_votes(ano, uf, NOMES_CARGO[cargo], cache, False).filter(
        v.office_filter(NOMES_CARGO[cargo].upper()) & (pl.col("SG_UF") == uf))
    if cargo == 11:
        lz = lz.filter(pl.col("CD_MUNICIPIO") == municipio)
        aptos = aptos.filter(pl.col("CD_MUNICIPIO") == municipio)
    votos = lz.select("NR_TURNO", *SECAO, "NR_VOTAVEL", "QT_VOTOS").collect()
    locais = (lz.filter(pl.col("NR_TURNO") == 1).select(*SECAO, "NR_LOCAL_VOTACAO", "NM_MUNICIPIO",
                                                         "NM_LOCAL_VOTACAO").unique(SECAO).collect())
    nomes = dict(lz.filter(~pl.col("NR_VOTAVEL").is_in(NAO_CANDIDATOS)).select("NR_VOTAVEL", "NM_VOTAVEL")
                 .unique("NR_VOTAVEL").collect().iter_rows())
    nomes.update(_nomes_de_urna(ano, uf, cargo, cache))
    secoes = aptos.join(locais, on=SECAO, how="inner")
    return secoes, votos, nomes


def _nomes_de_urna(ano: int, uf: str, cargo: int, cache: Path) -> dict[int, str]:
    """"LULA (PT)" no lugar de "LUIZ INÁCIO LULA DA SILVA" (o mesmo rótulo da divulgação); sem o cadastro
    de candidatos no cache, fica o nome dos microdados. Prefeito: o número só vale no município (não usado)."""
    if cargo == 11:
        return {}
    try:
        from apuracao import historico as h
        c = h.load_candidatos(ano, cache)
    except (v.TseDataError, OSError, ValueError) as exc:
        logger.info("sem cadastro de candidatos de %s para os nomes de urna: %s", ano, exc)
        return {}
    c = c.filter((pl.col("CD_CARGO").cast(pl.Int64, strict=False) == cargo)
                 & (pl.col("SG_UF") == ("BR" if cargo == 1 else uf)))
    return {int(n): f"{u} ({p})" for n, u, p in c.select("NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO")
            .unique("NR_CANDIDATO").iter_rows()}


_CACHE_MICRODADOS: dict[tuple, tuple[pl.DataFrame, pl.DataFrame, dict[int, str]]] = {}


def calcular(ano: int, uf: str, cargo: int, nivel: str, cache: Path, municipio: int | None = None,
             n_boot: int = 200) -> Resultado:
    """Carrega (uma vez por ano/UF/cargo, em memória) e analisa. Prefeito exige município: o número do
    candidato só é único dentro dele."""
    if cargo == 11 and municipio is None:
        raise ValueError("prefeito: escolha um município (o número do candidato só vale dentro dele)")
    chave = (ano, uf.upper(), cargo, str(cache), municipio if cargo == 11 else None)
    if chave not in _CACHE_MICRODADOS:
        _CACHE_MICRODADOS.clear() if len(_CACHE_MICRODADOS) > 4 else None
        _CACHE_MICRODADOS[chave] = carregar_microdados(ano, uf, cargo, cache, municipio)
    secoes, votos, nomes = _CACHE_MICRODADOS[chave]
    area = next(iter(secoes.filter(pl.col("CD_MUNICIPIO") == municipio)["NM_MUNICIPIO"]), None) if municipio else uf
    u = montar_unidades(secoes, votos, nomes, nivel, municipio, descricao=(
        f"{NOMES_CARGO[cargo].capitalize()} {ano}, {area or municipio}, por "
        f"{dict(secao='seção', local='local de votação', municipio='município')[nivel]}"))
    return analisar(u, n_boot=n_boot)


def unidades_divulgacao(dir1: Path, dir2: Path, cargo: int, uf: str) -> Unidades:
    """Municípios como unidades, a partir do que o COLETOR gravou nos dois turnos (noite do 2º turno,
    antes dos microdados). Mesmo formato de `montar_unidades`; categorias iguais às dos microdados."""
    uf = uf.upper()
    partes = []
    for turno, d in ((1, dir1), (2, dir2)):
        tot = pl.read_parquet(d / "ultimo" / "totais.parquet").filter(
            (pl.col("ABRANGENCIA") == "mun") & (pl.col("CARGO") == cargo) & (pl.col("UF") == uf))
        cand = pl.read_parquet(d / "ultimo" / "candidatos.parquet").filter(
            (pl.col("ABRANGENCIA") == "mun") & (pl.col("CARGO") == cargo) & (pl.col("UF") == uf))
        if tot.is_empty():
            raise v.TseDataError(f"sem resultado municipal do cargo {cargo} em {d}")
        # branco/nulo = comparecimento menos os votos de candidatos: as categorias somam o comparecimento
        votos = pl.concat([
            cand.select("CD_MUNICIPIO", "NUMERO", pl.col("VOTOS").fill_null(0)).rename(
                {"NUMERO": "NR_VOTAVEL", "VOTOS": "QT_VOTOS"}),
            tot.join(cand.group_by("CD_MUNICIPIO").agg(pl.col("VOTOS").fill_null(0).sum().alias("CAND")),
                     on="CD_MUNICIPIO", how="left")
            .select("CD_MUNICIPIO", pl.lit(95, pl.Int64).alias("NR_VOTAVEL"),
                    (pl.col("COMPARECIMENTO") - pl.col("CAND").fill_null(0)).clip(0).alias("QT_VOTOS")),
        ]).with_columns(pl.lit(turno, pl.Int64).alias("NR_TURNO"), pl.lit(0, pl.Int64).alias("NR_ZONA"),
                        pl.lit(0, pl.Int64).alias("NR_SECAO"))
        partes.append((tot.select("CD_MUNICIPIO", pl.col("ELEITORADO").alias(f"APTOS_{turno}")), votos, cand))
    muns = pl.read_parquet(dir2 / "ultimo" / "municipios.parquet").select("CD_MUNICIPIO", "NM_MUNICIPIO")
    secoes = (partes[0][0].join(partes[1][0], on="CD_MUNICIPIO").join(muns, on="CD_MUNICIPIO", how="left")
              .with_columns(pl.lit(0, pl.Int64).alias("NR_ZONA"), pl.lit(0, pl.Int64).alias("NR_SECAO"),
                            pl.lit(0, pl.Int64).alias("NR_LOCAL_VOTACAO"),
                            pl.col("NM_MUNICIPIO").alias("NM_LOCAL_VOTACAO")))
    votos = pl.concat([partes[0][1], partes[1][1]]).select("NR_TURNO", *SECAO, "NR_VOTAVEL", "QT_VOTOS")
    nomes = {n: f"{u} ({p})" for n, u, p in pl.concat([partes[0][2], partes[1][2]])
             .select("NUMERO", "NOME_URNA", "PARTIDO").unique("NUMERO").iter_rows()}
    return montar_unidades(secoes, votos, nomes, "municipio",
                           descricao="municípios, da divulgação em tempo real (antes dos microdados)")


# --------------------------------------------------------------------------
# Análise: matriz, intervalo, ajuste, abstenção extra, validação
# --------------------------------------------------------------------------
ESTRATO_PADRAO = {"secao": "zona", "local": "municipio", "municipio": None}
MIN_UNIDADES_ESTRATO = 30   # estrato menor que isto vai para o "restante" (uma matriz para todos eles)


@dataclass
class Resultado:
    unidades: Unidades
    matriz: np.ndarray            # K × J (frações): combinação das matrizes dos estratos pelo eleitorado
    baixo: np.ndarray             # IC 95% (bootstrap por bloco)
    alto: np.ndarray
    eleitores_1: np.ndarray       # eleitores de cada categoria do 1º turno (K)
    r2: dict[str, float]          # por categoria do 2º turno (ponderado)
    por_unidade: pl.DataFrame     # observado × ajustado, abstenção extra e destino dos eliminados no estrato
    n_boot: int
    estrato: str | None = None
    matriz_unica: np.ndarray | None = None      # uma só matriz para a área (sem estratos), para comparar
    estratos: pl.DataFrame | None = None        # um estrato por linha: eleitores e destino dos eliminados
    validacao: dict[str, Any] | None = None

    @property
    def fluxos(self) -> np.ndarray:
        """Eleitores estimados de cada categoria do 1º turno para cada uma do 2º (K × J)."""
        return self.matriz * self.eleitores_1[:, None]


def estratos(u: Unidades, estrato: str | None, minimo: int = MIN_UNIDADES_ESTRATO) -> tuple[np.ndarray, list[str]]:
    """Índice do estrato de cada unidade e os rótulos. "zona" = município + zona; "municipio"; None = um só."""
    if estrato is None:
        return np.zeros(u.tabela.height, dtype=int), ["área inteira"]
    t = u.tabela
    if estrato == "zona":
        rot = (t["NM_MUNICIPIO"] + " — zona " + t["NR_ZONA"].cast(pl.String)).to_numpy()
    elif estrato == "municipio":
        rot = t["NM_MUNICIPIO"].fill_null(t["CD_MUNICIPIO"].cast(pl.String)).to_numpy()
    else:
        raise ValueError("estrato: zona, municipio ou None")
    nomes, cont = np.unique(rot, return_counts=True)
    pequenos = set(nomes[cont < minimo])
    rot = np.where(np.isin(rot, list(pequenos)), "restante (estratos pequenos)", rot)
    rotulos, idx = np.unique(rot, return_inverse=True)
    return idx, rotulos.tolist()


class _Somas:
    """Por estrato: G = Xᵀ W X, C = Xᵀ W Y e o total de eleitores de cada categoria do 1º turno. Os produtos
    por unidade são calculados uma vez, ordenados por estrato; cada bootstrap só troca os pesos (reduceat)."""

    def __init__(self, x: np.ndarray, y: np.ndarray, e: np.ndarray, n: int) -> None:
        ordem = np.argsort(e, kind="stable")
        self.x, self.e, self.n = x[ordem], e[ordem], n
        self.ordem = ordem
        self.xx = self.x[:, :, None] * self.x[:, None, :]
        self.xy = self.x[:, :, None] * y[ordem][:, None, :]
        self.inicio = np.searchsorted(self.e, np.arange(n))
        self.presentes = np.isin(np.arange(n), self.e)

    def __call__(self, pesos: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p = pesos[self.ordem]
        k, j = self.xy.shape[1], self.xy.shape[2]
        g, c, tot = np.zeros((self.n, k, k)), np.zeros((self.n, k, j)), np.zeros((self.n, k))
        ini = self.inicio[self.presentes]
        g[self.presentes] = np.add.reduceat(self.xx * p[:, None, None], ini, axis=0)
        c[self.presentes] = np.add.reduceat(self.xy * p[:, None, None], ini, axis=0)
        tot[self.presentes] = np.add.reduceat(self.x * p[:, None], ini, axis=0)
        return g, c, tot


def _somas(x: np.ndarray, y: np.ndarray, pesos: np.ndarray, e: np.ndarray, n: int
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return _Somas(x, y, e, n)(pesos)


def _por_estrato(g: np.ndarray, c: np.ndarray, b0: np.ndarray | None = None, tol: float = 1e-10,
                 iteracoes: int = 10_000) -> np.ndarray:
    return _fista_lote(g, c, iteracoes, tol, b0)


def _combinar(bs: np.ndarray, tot: np.ndarray) -> np.ndarray:
    """Matriz da área: fluxos dos estratos somados e divididos pelos eleitores de cada categoria."""
    fluxo = (tot[:, :, None] * bs).sum(axis=0)
    soma = tot.sum(axis=0)[:, None]
    return np.divide(fluxo, soma, out=np.full_like(fluxo, np.nan), where=soma > 0)


def _estimar_estratos(u: Unidades, x: np.ndarray, y: np.ndarray, w: np.ndarray,
                      estrato: str | None = "auto") -> tuple[np.ndarray, np.ndarray]:
    """(matrizes por estrato, eleitores por estrato e categoria) — sem bootstrap."""
    e, rotulos = estratos(u, ESTRATO_PADRAO[u.nivel] if estrato == "auto" else estrato)
    g, c, tot = _Somas(x, y, e, len(rotulos))(w)
    return _por_estrato(g, c), tot


def _eliminados(u: Unidades) -> list[int]:
    """Índices do 1º turno que não têm para onde ir no 2º: eliminados e "Outros"."""
    return [i for i, c in enumerate(u.cat1) if c not in u.cat2]


def analisar(u: Unidades, n_boot: int = 100, semente: int = 7, validar_cv: bool = True,
             estrato: str | None = "auto") -> Resultado:
    """`estrato`: uma matriz por zona (seções) ou por município (locais) — "auto" —, combinadas pelo
    eleitorado. Na validação com 2022 (RJ, Presidente) isso reduziu o erro fora da amostra (seções:
    1,64 → 1,54 p.p.; locais: 0,98 → 0,87 p.p.) e dá a cada local o padrão da sua região."""
    estr = ESTRATO_PADRAO[u.nivel] if estrato == "auto" else estrato
    x, y, w = u.matrizes()
    if len(w) < 2 * len(u.cat1):
        raise v.TseDataError(f"poucas unidades ({len(w)}) para {len(u.cat1)} categorias do 1º turno")
    e, rotulos = estratos(u, estr)
    somas = _Somas(x, y, e, len(rotulos))
    g, c, tot = somas(w)
    bs = _por_estrato(g, c)
    b = _combinar(bs, tot)
    rng = np.random.default_rng(semente)
    grupos, idx = np.unique(u.tabela["GRUPO"].to_numpy(), return_inverse=True)
    amostras = []
    for _ in range(n_boot):   # bootstrap por bloco (local): seções do mesmo local não são independentes
        cont = np.bincount(rng.integers(0, len(grupos), len(grupos)), minlength=len(grupos))[idx]
        gr, cr, tr_ = somas(w * cont)
        # parte da estimativa: 1.500 iterações mudam o IC em < 0,7 p.p. (locais) e 0,001 p.p. (seções) no RJ 2022
        amostras.append(_combinar(_por_estrato(gr, cr, b0=bs, tol=1e-6, iteracoes=1500), tr_))
    pilha = np.stack(amostras) if amostras else b[None]
    ajuste = np.einsum("ik,ikj->ij", x, bs[e])
    r2 = {}
    for j, cat in enumerate(u.cat2):
        media = np.average(y[:, j], weights=w)
        sst = np.sum(w * (y[:, j] - media) ** 2)
        r2[cat] = float(1 - np.sum(w * (y[:, j] - ajuste[:, j]) ** 2) / sst) if sst > 0 else float("nan")
    # destino dos votos dos eliminados (e "Outros") em cada estrato — o que vale para cada local
    el = _eliminados(u)
    fluxo_el = (tot[:, el, None] * bs[:, el, :]).sum(axis=1)
    el_tot = tot[:, el].sum(axis=1)
    destino_el = 100 * np.divide(fluxo_el, el_tot[:, None], out=np.full_like(fluxo_el, np.nan),
                                 where=el_tot[:, None] > 0)
    tab_estr = pl.DataFrame({"ESTRATO": rotulos, "UNIDADES": np.bincount(e, minlength=len(rotulos)),
                             "ELEITORES_1T": tot.sum(axis=1).round(), "ELIMINADOS_1T": el_tot.round(),
                             **{f"ELIM_PARA_{c}_PCT": destino_el[:, j] for j, c in enumerate(u.cat2)}})
    a = u.cat2[0]
    por = u.tabela.select([col for col in ("UNIDADE", "NOME", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
                                            "NR_LOCAL_VOTACAO") if col in u.tabela.columns] + ["APTOS_1", "APTOS_2"]
                          ).with_columns(
        pl.Series("ESTRATO", np.array(rotulos, dtype=object)[e].tolist()),
        pl.Series("ABST_1_PCT", 100 * x[:, u.cat1.index(ABSTENCAO)]),
        pl.Series("ABST_2_PCT", 100 * y[:, u.cat2.index(ABSTENCAO)]),
        pl.Series("ELIMINADOS_1_PCT", 100 * x[:, el].sum(axis=1)),
        *[pl.Series(f"{col}_2_PCT", 100 * y[:, j]) for j, col in enumerate(u.cat2[:2])],
        *[pl.Series(f"{col}_2_AJUSTE_PCT", 100 * ajuste[:, j]) for j, col in enumerate(u.cat2[:2])],
        *[pl.Series(f"ELIM_PARA_{col}_PCT", destino_el[e, j]) for j, col in enumerate(u.cat2)],
    ).with_columns((pl.col("ABST_2_PCT") - pl.col("ABST_1_PCT")).alias("ABST_EXTRA_PP"),
                   (pl.col(f"{a}_2_PCT") - pl.col(f"{a}_2_AJUSTE_PCT")).alias("RESIDUO_A_PP"))
    # percentil do bootstrap; com as restrições (0 e 100%) a distribuição pode ficar toda de um lado da
    # estimativa (ex.: 4,0% com IC 4,1–6,6%): o intervalo é estendido até ela
    # (nanpercentile: numa replicação, uma categoria rara pode ficar sem eleitores e sem linha)
    baixo = np.fmin(np.nanpercentile(pilha, 2.5, axis=0), b)
    alto = np.fmax(np.nanpercentile(pilha, 97.5, axis=0), b)
    res = Resultado(u, b, baixo, alto,
                    tot.sum(axis=0), r2, por, n_boot, estr, estimar(x, y, w), tab_estr)
    if validar_cv:
        res.validacao = validacao_cruzada(u, estr)
    return res


def validacao_cruzada(u: Unidades, estrato: str | None = None, dobras: int = 5, semente: int = 11
                      ) -> dict[str, Any]:
    """Erro fora da amostra (p.p. do eleitorado, ponderado): o modelo, treinado em 4/5 dos blocos (locais),
    prevê a composição do 2º turno do 1/5 restante. Comparações: a matriz única (sem estratos) e o swing
    uniforme (cada finalista, branco/nulo e abstenção mudam na unidade o que mudaram na área de treino)."""
    x, y, w = u.matrizes()
    grupos, idx = np.unique(u.tabela["GRUPO"].to_numpy(), return_inverse=True)
    dobra = np.random.default_rng(semente).permutation(len(grupos))[idx] % dobras
    e, rotulos = estratos(u, estrato)
    mapa = [u.cat1.index(c) for c in u.cat2]      # A→A, B→B, branco/nulo→branco/nulo, abstenção→abstenção
    erros: dict[str, list] = {"modelo": [], "matriz_unica": [], "swing": []}
    for k in range(dobras):
        tr_, te = dobra != k, dobra == k
        if not te.any() or not tr_.any():
            continue
        unica = estimar(x[tr_], y[tr_], w[tr_])
        g, c, _ = _somas(x[tr_], y[tr_], w[tr_], e[tr_], len(rotulos))
        treinado = np.bincount(e[tr_], minlength=len(rotulos)) >= 2 * len(u.cat1)
        bs = np.where(treinado[:, None, None], _fista_lote(g, c), unica[None])
        delta = np.average(y[tr_], axis=0, weights=w[tr_]) - np.average(x[tr_][:, mapa], axis=0, weights=w[tr_])
        previsoes = {"modelo": np.einsum("ik,ikj->ij", x[te], bs[e[te]]), "matriz_unica": x[te] @ unica,
                     "swing": x[te][:, mapa] + delta}
        for nome, p in previsoes.items():
            erros[nome].append(((w[te][:, None] * (p - y[te]) ** 2).sum(axis=0), w[te].sum()))

    def rmse(lista: list) -> list[float]:
        num = sum(n for n, _ in lista)
        den = sum(d for _, d in lista)
        return [float(100 * np.sqrt(n / den)) for n in num]

    r = {nome: rmse(lista) for nome, lista in erros.items()}
    return {"dobras": dobras, "categorias": u.cat2, "estrato": estrato,
            **{f"rmse_{n}_pp": val for n, val in r.items()},
            **{f"rmse_{n}_medio_pp": float(np.mean(val)) for n, val in r.items()}}


def resumo(res: Resultado) -> dict[str, Any]:
    """O resultado em JSON (API e planilha)."""
    u = res.unidades
    tot1, tot2 = u.tabela["APTOS_1"].sum(), u.tabela["APTOS_2"].sum()
    abst1 = int(u.tabela[f"1:{ABSTENCAO}"].sum())
    abst2 = int(u.tabela[f"2:{ABSTENCAO}"].sum())
    linhas = []
    for i, c1 in enumerate(u.cat1):
        linhas.append({"origem": c1, "eleitores_1t": int(round(res.eleitores_1[i])),
                       "pct_1t": 100 * res.eleitores_1[i] / tot1,
                       "destinos": [{"destino": c2, "pct": 100 * res.matriz[i, j], "baixo": 100 * res.baixo[i, j],
                                     "alto": 100 * res.alto[i, j], "eleitores": int(round(res.fluxos[i, j]))}
                                    for j, c2 in enumerate(u.cat2)]})
    j_abs = u.cat2.index(ABSTENCAO)
    novos = res.fluxos[:, j_abs].copy()
    novos[u.cat1.index(ABSTENCAO)] = 0   # quem já se absteve no 1º turno não é abstenção "extra"
    ordem = res.por_unidade.sort("ABST_EXTRA_PP", descending=True)
    return {
        "descricao": u.descricao, "nivel": u.nivel, "unidades": u.tabela.height, "categorias_1t": u.cat1,
        "categorias_2t": u.cat2, "finalistas": u.finalistas, "eleitores_1t": int(tot1), "eleitores_2t": int(tot2),
        "matriz": linhas, "r2": res.r2, "bootstrap": res.n_boot,
        "abstencao": {"pct_1t": 100 * abst1 / tot1, "pct_2t": 100 * abst2 / tot2, "eleitores_1t": abst1,
                      "eleitores_2t": abst2, "extra_pp": 100 * (abst2 / tot2 - abst1 / tot1),
                      "novos_abstencionistas": [{"origem": c, "eleitores": int(round(n))}
                                                for c, n in zip(u.cat1, novos) if c != ABSTENCAO]},
        "validacao": res.validacao,
        "estrato": res.estrato,
        "n_estratos": 0 if res.estratos is None else res.estratos.height,
        "estratos": [] if res.estratos is None else _linhas(res.estratos.sort("ELEITORES_1T", descending=True).head(40)),
        "matriz_unica_pct": None if res.matriz_unica is None else (100 * res.matriz_unica).round(2).tolist(),
        # célula em 0% ou 100% = a restrição segurou o modelo (sem ela sairia um valor impossível): ler com cautela
        "celulas_no_limite": int(((res.matriz < 1e-4) | (res.matriz > 1 - 1e-4)).sum()),
        "maior_abstencao_extra": _linhas(ordem.head(15)),
        "residuos_a": {"acima": _linhas(res.por_unidade.sort("RESIDUO_A_PP", descending=True).head(10)),
                       "abaixo": _linhas(res.por_unidade.sort("RESIDUO_A_PP").head(10))},
    }


def _linhas(df: pl.DataFrame) -> list[dict[str, Any]]:
    return [{k: (round(val, 3) if isinstance(val, float) else val) for k, val in r.items()}
            for r in df.iter_rows(named=True)]


def comparar_niveis(secoes: pl.DataFrame, votos: pl.DataFrame, nomes: dict[int, str],
                    municipio: int | None = None) -> dict[str, Any]:
    """Viés de agregação: a mesma matriz (estratificada como em `analisar`) estimada com seções, locais e
    municípios. Diferença grande entre os níveis = o comportamento varia com a composição da unidade."""
    mats = {}
    for nivel in NIVEIS:
        if nivel == "municipio" and municipio is not None:
            continue
        u = montar_unidades(secoes, votos, nomes, nivel, municipio, max_eliminados=MAX_ELIMINADOS)  # mesmas categorias
        x, y, w = u.matrizes()
        if len(w) >= 2 * len(u.cat1):
            mats[nivel] = (u, _combinar(*_estimar_estratos(u, x, y, w)))
    base = mats["secao"][1]
    return {"categorias_1t": mats["secao"][0].cat1, "categorias_2t": mats["secao"][0].cat2,
            "niveis": {n: {"unidades": u.tabela.height, "matriz_pct": (100 * b).round(1).tolist(),
                           "max_dif_pp_vs_secao": float(100 * np.abs(b - base).max())}
                       for n, (u, b) in mats.items()}}


# --------------------------------------------------------------------------
# Planilha
# --------------------------------------------------------------------------
def para_planilha(r: dict[str, Any], por_unidade: pl.DataFrame, destino: Path) -> None:
    import xlsxwriter

    wb = xlsxwriter.Workbook(str(destino))
    cab = wb.add_format({"bold": True, "bg_color": "#E9EEF8"})
    pct = wb.add_format({"num_format": "0.0"})
    ws = wb.add_worksheet("Matriz")
    ws.write(0, 0, f"Transferência do 1º para o 2º turno — {r['descricao']} ({r['unidades']} unidades)", cab)
    linha = 2
    ws.write_row(linha, 0, ["Origem (1º turno)", "Eleitores no 1º turno"]
                 + [f"{c} (%)" for c in r["categorias_2t"]] + [f"{c} IC 95%" for c in r["categorias_2t"]]
                 + [f"{c} (eleitores)" for c in r["categorias_2t"]], cab)
    for m in r["matriz"]:
        linha += 1
        ws.write(linha, 0, m["origem"])
        ws.write_number(linha, 1, m["eleitores_1t"])
        for j, d in enumerate(m["destinos"]):
            ws.write_number(linha, 2 + j, d["pct"], pct)
            ws.write(linha, 2 + len(m["destinos"]) + j, f"{d['baixo']:.1f}–{d['alto']:.1f}")
            ws.write_number(linha, 2 + 2 * len(m["destinos"]) + j, d["eleitores"])
    linha += 2
    ws.write(linha, 0, "Leia: da linha 'origem', que % foi para cada opção do 2º turno. Inferência ECOLÓGICA "
                       "(unidades, não pessoas); o IC mede só a variação amostral (bootstrap por local).")
    if r.get("validacao"):
        val = r["validacao"]
        linha += 2
        ws.write(linha, 0, "Validação cruzada (erro fora da amostra, p.p. do eleitorado)", cab)
        ws.write_row(linha + 1, 0, ["", *val["categorias"], "média"], cab)
        ws.write_row(linha + 2, 0, ["modelo", *val["rmse_modelo_pp"], val["rmse_modelo_medio_pp"]])
        ws.write_row(linha + 3, 0, ["swing uniforme", *val["rmse_swing_pp"], val["rmse_swing_medio_pp"]])
    ws.set_column(0, 0, 28)
    ws.set_column(1, 30, 14)
    ws2 = wb.add_worksheet("Por unidade")
    cols = por_unidade.columns
    ws2.write_row(0, 0, cols, cab)
    for i, row in enumerate(por_unidade.iter_rows(), start=1):
        for j, val in enumerate(row):
            if val is not None:
                ws2.write(i, j, val)
    ws2.freeze_panes(1, 0)
    ws2.autofilter(0, 0, por_unidade.height, len(cols) - 1)
    wb.close()
