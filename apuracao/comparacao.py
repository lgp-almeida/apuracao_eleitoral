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

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
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


# --------------------------------------------------------------------------
# Variação de partidos de A para B por município: dispersão, distribuição e estatística (aba Comparação)
# --------------------------------------------------------------------------
MAX_PARTIDOS_VARIACAO = 3  # dataviz: no máximo 3 cores categóricas
N_BOOTSTRAP = 2000
N_DESTAQUES = 5


def _reta_ponderada(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    """y = a + b·x por mínimos quadrados ponderados + EP de b, IC 95% e p de "b = 1" (deslocamento uniforme).
    Os pesos são reescalados para somar o n efetivo de Kish (pesos analíticos), então o EP não finge que
    cada eleitor é uma observação independente."""
    from apuracao.perfil import correlacao

    c = correlacao(x, y, w)
    if c["b"] is None:
        return {**c, "ep_b": None, "ic_b": None, "p_b1": None}
    n_ef = c["n_efetivo"]
    wn = w * n_ef / w.sum()
    mx = np.average(x, weights=wn)
    res = y - (c["a"] + c["b"] * x)
    gl = n_ef - 2
    ep = math.sqrt(np.sum(wn * res ** 2) / gl / np.sum(wn * (x - mx) ** 2)) if gl > 0 else None
    if not ep:
        return {**c, "ep_b": ep, "ic_b": None, "p_b1": None}
    return {**c, "ep_b": ep, "ic_b": [c["b"] - 1.96 * ep, c["b"] + 1.96 * ep],
            "p_b1": math.erfc(abs(c["b"] - 1) / ep / math.sqrt(2))}


def _media_bootstrap(d: np.ndarray, w: np.ndarray, rng: np.random.Generator) -> tuple[float, float, list[float]]:
    """Média e desvio-padrão ponderados + IC 95% (percentil) reamostrando os municípios."""
    media = float(np.average(d, weights=w))
    dp = float(math.sqrt(np.average((d - media) ** 2, weights=w)))
    idx = rng.integers(0, len(d), size=(N_BOOTSTRAP, len(d)))
    medias = (d[idx] * w[idx]).sum(axis=1) / w[idx].sum(axis=1)
    return media, dp, [float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))]


def _leitura(reta: dict) -> str:
    if reta.get("ic_b") is None:
        return "poucos municípios para ler o padrão"
    lo, hi = reta["ic_b"]
    if lo <= 1 <= hi:
        return "deslocamento uniforme: a variação não depende de quanto o partido tinha antes"
    if lo > 1:
        return "variação mais favorável onde o partido já era forte: a distância entre redutos e os demais aumentou"
    return ("variação mais favorável onde o partido era fraco: o voto ficou mais parecido entre os municípios "
            "(parte disso pode ser regressão à média — municípios pequenos oscilam mais de uma eleição para outra)")


def variacao_partidos(a: Fonte, b: Fonte, cargo: int, partidos: list[str], ponderar: bool = False,
                      semente: int = 0) -> dict:
    """% dos válidos de cada partido em A (x) e B (y) por município, com a estatística da variação:
    média da variação (IC 95% por bootstrap dos municípios), reta y = a + b·x (b = 1: deslocamento
    uniforme) e, com dois partidos, o swing de Butler do 1º para o 2º.
    Sem `ponderar` (padrão, como no Perfil × voto) cada município é uma observação; ponderando pelos
    válidos de B a capital domina (no RJ, n efetivo ≈ 7 de 92). A variação no ESTADO vem à parte (`uf`).
    Leitura ECOLÓGICA (municípios, não pessoas); os municípios são a população, não uma amostra."""
    partidos = [p for p in dict.fromkeys(x.strip().upper() for x in partidos) if p]
    if not partidos or len(partidos) > MAX_PARTIDOS_VARIACAO:
        raise ValueError(f"escolha de 1 a {MAX_PARTIDOS_VARIACAO} partidos")
    rng = np.random.default_rng(semente)
    pesos = b.totais.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun")).select(
        "CD_MUNICIPIO", pl.col("VALIDOS").alias("PESO"))
    nomes = pl.concat([b.municipios, a.municipios], how="diagonal_relaxed").unique(
        subset=["CD_MUNICIPIO"], keep="first").select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO")
    existentes = set(_votos_partido(a, cargo)["PARTIDO"].to_list()) | set(_votos_partido(b, cargo)["PARTIDO"].to_list())
    saida, difs = [], {}
    for p in partidos:
        if p not in existentes:
            raise ValueError(f"partido {p} sem votos no cargo {cargo} em {a.ano} e em {b.ano}")
        df = (_pct_partido(a, cargo, p).rename({"VALOR": "A"})
              .join(_pct_partido(b, cargo, p).rename({"VALOR": "B"}), on=CHAVE, how="inner", nulls_equal=True)
              .with_columns((pl.col("B") - pl.col("A")).alias("DIF")))
        uf = df.filter(pl.col("ABRANGENCIA") == "uf")
        mun = (df.filter((pl.col("ABRANGENCIA") == "mun") & pl.col("DIF").is_not_null())
               .join(pesos, on="CD_MUNICIPIO", how="inner").filter(pl.col("PESO") > 0)
               .join(nomes, on="CD_MUNICIPIO", how="left").sort("CD_MUNICIPIO"))
        if mun.height < 3:
            raise ValueError(f"partido {p}: menos de 3 municípios com votos válidos nos dois anos")
        x, y = mun["A"].to_numpy(), mun["B"].to_numpy()
        d = mun["DIF"].to_numpy()
        w = mun["PESO"].to_numpy().astype(float) if ponderar else np.ones(mun.height)
        media, dp, ic = _media_bootstrap(d, w, rng)
        reta = _reta_ponderada(x, y, w)
        destaque = set(np.argsort(-np.abs(d - media))[:N_DESTAQUES].tolist())
        difs[p] = mun.select("CD_MUNICIPIO", "NM_MUNICIPIO", "CD_MUNICIPIO_IBGE", "DIF", "PESO")
        saida.append({
            "partido": p, "uf": uf.select("A", "B", "DIF").row(0, named=True) if uf.height else None,
            "media": media, "dp": dp, "ic_media": ic, "reta": reta, "leitura": _leitura(reta),
            "pontos": [{**r, "DESTAQUE": i in destaque} for i, r in enumerate(mun.select(
                "CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO", "A", "B", "DIF", pl.col("PESO").alias("VALIDOS"))
                .to_dicts())],
        })
    butler = None
    if len(partidos) == 2:  # swing do 1º para o 2º partido: ((B2 − A2) − (B1 − A1)) / 2
        p1, p2 = partidos
        sw = (difs[p1].join(difs[p2].select("CD_MUNICIPIO", pl.col("DIF").alias("D2")), on="CD_MUNICIPIO")
              .with_columns(((pl.col("D2") - pl.col("DIF")) / 2).alias("VALOR")))
        u1, u2 = saida[0]["uf"], saida[1]["uf"]
        media, dp, ic = _media_bootstrap(sw["VALOR"].to_numpy(), sw["PESO"].to_numpy().astype(float) if ponderar
                                         else np.ones(sw.height), rng)
        butler = {"de": p1, "para": p2, "uf": (u2["DIF"] - u1["DIF"]) / 2 if u1 and u2 else None,
                  "media": media, "dp": dp, "ic_media": ic,
                  "pontos": sw.select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO", "VALOR").to_dicts()}
    return {"ano_a": a.ano, "ano_b": b.ano, "cargo": cargo, "ponderado": ponderar, "partidos": saida, "butler": butler}


# --------------------------------------------------------------------------
# Histórico de um candidato: o resultado atual por município e, se ele concorreu na eleição de
# referência, o daquela ao lado (planilha da aba Candidato, sem depender dos microdados)
# --------------------------------------------------------------------------
@dataclass
class HistoricoCandidato:
    """`criterio`: "nome completo" (casou pelo NOME civil, qualquer cargo), "indicado" (cargo/nº de
    referência dados à mão), "ambíguo" (homônimos: ver `opcoes`), "não concorreu" ou "sem referência".
    `tabela`: estado na 1ª linha e municípios; colunas com o ano no nome (`VOTOS_<ano>`…)."""

    ano: int
    ano_ref: int | None
    atual: dict
    anterior: dict | None
    criterio: str
    opcoes: list[dict]
    notas: list[str]
    tabela: pl.DataFrame

    @property
    def sufixos(self) -> tuple[str, str]:
        """Sufixos das colunas de cada eleição (o ano; "ref" sem referência)."""
        return _sufixos(self.ano, self.ano_ref)


def _sufixos(ano: int, ano_ref: int | None) -> tuple[str, str]:
    a, b = str(ano), str(ano_ref) if ano_ref else "ref"
    return a, (b if b != a else f"{b}_ref")


COLUNAS_CANDIDATO = ("CARGO", "NUMERO", "NOME_URNA", "NOME", "PARTIDO", "FEDERACAO", "VOTOS", "PCT_VALIDOS",
                     "SITUACAO")


def _linha_uf(f: Fonte, uf: str) -> pl.DataFrame:
    return f.candidatos.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf))


def _ficha(f: Fonte, uf: str, linha: dict) -> dict:
    """Dados do candidato na UF + nome do cargo e posição entre os do cargo."""
    todos = _linha_uf(f, uf).filter(pl.col("CARGO") == linha["CARGO"])
    ds = f.totais.filter((pl.col("CARGO") == linha["CARGO"]) & (pl.col("ABRANGENCIA") == "uf")
                         & (pl.col("UF") == uf))
    t = ds.row(0, named=True) if ds.height else {}
    return {**{k: linha.get(k) for k in COLUNAS_CANDIDATO}, "DS_CARGO": t.get("DS_CARGO"),
            "POSICAO_UF": todos.filter(pl.col("VOTOS") > linha["VOTOS"]).height + 1, "N_CANDIDATOS_UF": todos.height,
            "PCT_SECOES_TOTALIZADAS": t.get("PCT_SECOES_TOTALIZADAS"), "TOTALIZACAO_FINAL": t.get("TOTALIZACAO_FINAL")}


def _por_municipio(f: Fonte, uf: str, cargo: int, numero: int) -> pl.DataFrame:
    """Votos, % dos válidos e posição do candidato no estado e em cada município onde o cargo foi votado.
    O arquivo do TSE é esparso: município sem linha do candidato = 0 voto (posição nula)."""
    base = f.totais.filter((pl.col("CARGO") == cargo) & (pl.col("UF") == uf)
                           & pl.col("ABRANGENCIA").is_in(["uf", "mun"])).select(
        CHAVE + ["VALIDOS", "PCT_SECOES_TOTALIZADAS"])
    cand = (f.candidatos.filter((pl.col("CARGO") == cargo) & (pl.col("UF") == uf)
                                & pl.col("ABRANGENCIA").is_in(["uf", "mun"]))
            .with_columns(pl.col("VOTOS").rank("min", descending=True).over(CHAVE).cast(pl.Int64).alias("POSICAO"))
            .filter(pl.col("NUMERO") == numero).select(CHAVE + ["VOTOS", "PCT_VALIDOS", "POSICAO"]))
    return (base.join(cand, on=CHAVE, how="left", nulls_equal=True)
            .with_columns(pl.col("VOTOS").fill_null(0),
                          pl.when(pl.col("PCT_VALIDOS").is_not_null()).then(pl.col("PCT_VALIDOS"))
                          .when(pl.col("VALIDOS") > 0).then(pl.lit(0.0)).otherwise(None).alias("PCT_VALIDOS"))
            .drop("VALIDOS"))


def _candidato_ref(ref: Fonte, uf: str, atual: dict, cargo_ref: int | None,
                   numero_ref: int | None) -> tuple[dict | None, str, list[dict]]:
    from apuracao.eleitorado import compact

    cands = _linha_uf(ref, uf)
    if numero_ref is not None:
        c = cands.filter((pl.col("CARGO") == (cargo_ref or atual["CARGO"])) & (pl.col("NUMERO") == numero_ref))
        if c.is_empty():
            raise ValueError(f"nº {numero_ref} não encontrado em {ref.ano} no cargo {cargo_ref or atual['CARGO']}")
        return c.row(0, named=True), "indicado", []
    alvo = compact(atual["NOME"])
    if not alvo:
        return None, "não concorreu", []
    iguais = cands.filter(pl.col("NOME").map_elements(compact, return_dtype=pl.String) == alvo)
    if iguais.height > 1:  # homônimos: o mesmo cargo desempata
        mesmo = iguais.filter(pl.col("CARGO") == atual["CARGO"])
        iguais = mesmo if mesmo.height == 1 else iguais
    if iguais.height == 1:
        return iguais.row(0, named=True), "nome completo", []
    if iguais.height == 0:
        return None, "não concorreu", []
    return None, "ambíguo", [{k: r[k] for k in COLUNAS_CANDIDATO}
                             for r in iguais.sort("VOTOS", descending=True).iter_rows(named=True)]


def historico_candidato(atual: Fonte, ref: Fonte | None, uf: str, cargo: int, numero: int,
                        cargo_ref: int | None = None, numero_ref: int | None = None) -> HistoricoCandidato:
    """O candidato (cargo, número) na eleição `atual`, por município, e o MESMO candidato na de referência:
    o mesmo nome civil completo (comparado por `compact`), em qualquer cargo — o número muda de uma eleição
    para outra e o CPF não vem na divulgação. Com `numero_ref` (e `cargo_ref`, padrão o mesmo cargo) o
    candidato de referência é indicado à mão (homônimos). Variações: votos em %, % dos válidos em p.p."""
    linha = _linha_uf(atual, uf).filter((pl.col("CARGO") == cargo) & (pl.col("NUMERO") == numero))
    if linha.is_empty():
        raise LookupError(f"candidato {numero} não encontrado no cargo {cargo} em {uf}")
    ficha = _ficha(atual, uf, linha.row(0, named=True))
    a, b = _sufixos(atual.ano, ref.ano if ref else None)
    tab = _por_municipio(atual, uf, cargo, numero).rename(
        {"VOTOS": f"VOTOS_{a}", "PCT_VALIDOS": f"PCT_VALIDOS_{a}", "POSICAO": f"POSICAO_{a}"})
    anterior, criterio, opcoes, notas = None, "sem referência", [], []
    if ref is not None:
        r, criterio, opcoes = _candidato_ref(ref, uf, ficha, cargo_ref, numero_ref)
        anterior = _ficha(ref, uf, r) if r else None
    nomes = (pl.concat([atual.municipios, ref.municipios] if ref else [atual.municipios], how="diagonal_relaxed")
             .unique(subset=["CD_MUNICIPIO"], keep="first").select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO"))
    if anterior is not None:
        velho = _por_municipio(ref, uf, anterior["CARGO"], anterior["NUMERO"]).drop("PCT_SECOES_TOTALIZADAS").rename(
            {"VOTOS": f"VOTOS_{b}", "PCT_VALIDOS": f"PCT_VALIDOS_{b}", "POSICAO": f"POSICAO_{b}"})
        tab = tab.join(velho, on=CHAVE, how="full", coalesce=True, nulls_equal=True).rechunk()
        if anterior["CARGO"] != cargo:
            notas.append(f"Em {ref.ano} concorreu a {anterior['DS_CARGO'] or anterior['CARGO']}; "
                         f"em {atual.ano}, a {ficha['DS_CARGO'] or cargo}.")
        if cargo == 5 or anterior["CARGO"] == 5:
            notas.append("Senador: o nº de vagas (e de votos por eleitor) pode mudar de uma eleição para outra; "
                         "o % dos válidos não é diretamente comparável.")
    else:
        tab = tab.with_columns(pl.lit(None, pl.Int64).alias(f"VOTOS_{b}"), pl.lit(None, pl.Float64).alias(
            f"PCT_VALIDOS_{b}"), pl.lit(None, pl.Int64).alias(f"POSICAO_{b}"))
    va, vb = pl.col(f"VOTOS_{a}"), pl.col(f"VOTOS_{b}")
    tab = (tab.with_columns(
        pl.when(vb > 0).then(100 * (va.fill_null(0) - vb) / vb).otherwise(None).alias("VAR_VOTOS_PCT"),
        (pl.col(f"PCT_VALIDOS_{a}") - pl.col(f"PCT_VALIDOS_{b}")).alias("VAR_PCT_VALIDOS_PP"))
        .join(nomes, on="CD_MUNICIPIO", how="left")
        .with_columns(pl.when(pl.col("ABRANGENCIA") == "uf").then(pl.lit(uf)).otherwise(pl.col("NM_MUNICIPIO"))
                      .alias("NM_MUNICIPIO"))
        .sort(["ABRANGENCIA", f"VOTOS_{a}", "NM_MUNICIPIO"], descending=[True, True, False], nulls_last=True)
        .select("ABRANGENCIA", "CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO", f"VOTOS_{a}", f"PCT_VALIDOS_{a}",
                f"POSICAO_{a}", "PCT_SECOES_TOTALIZADAS", f"VOTOS_{b}", f"PCT_VALIDOS_{b}", f"POSICAO_{b}",
                "VAR_VOTOS_PCT", "VAR_PCT_VALIDOS_PP"))
    return HistoricoCandidato(atual.ano, ref.ano if ref else None, ficha, anterior, criterio, opcoes, notas, tab)


def planilha_historico(h: HistoricoCandidato, uf: str, gerado_em: str) -> bytes:
    """.xlsx (em memória): aba "Sobre" (os dois candidatos e o critério) e "Por município" (estado na 1ª linha)."""
    import io

    import xlsxwriter

    from apuracao import boletim as bo

    a, b = h.sufixos
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    formatos = bo.formatos_planilha(wb)

    def desc(c: dict | None) -> str:
        if not c:
            return "—"
        fed = f" · {c['FEDERACAO']}" if c.get("FEDERACAO") else ""
        return f"{c['NUMERO']} — {c['NOME_URNA']} ({c['NOME']}) · {c['PARTIDO']}{fed} · {c.get('DS_CARGO') or c['CARGO']}"

    at = h.atual
    andamento = "final" if at.get("TOTALIZACAO_FINAL") else (
        f"em andamento ({at['PCT_SECOES_TOTALIZADAS']:.2f}% das seções)" if at.get("PCT_SECOES_TOTALIZADAS") is not None
        else "—")
    sobre = [("Gerado em", gerado_em), ("UF", uf), (f"Candidato em {a}", desc(at)),
             (f"Votos em {a} (UF)", f"{at['VOTOS']:,}".replace(",", ".")), (f"Apuração de {a}", andamento),
             (f"Candidato em {b}", desc(h.anterior)),
             ("Identificação", {"nome completo": "mesmo nome civil completo (qualquer cargo)",
                                "indicado": "indicado à mão", "ambíguo": "homônimos: indique o cargo/nº à mão",
                                "não concorreu": f"não encontrado em {b} pelo nome completo",
                                "sem referência": "site sem eleição de referência"}.get(h.criterio, h.criterio)),
             ("Variação", "votos: % sobre o ano de referência; % dos válidos: pontos percentuais (p.p.)")]
    sobre += [("Nota", n) for n in h.notas]
    sobre += [("Homônimo", desc(o)) for o in h.opcoes]
    bo._aba(wb, "Sobre", [("ITEM", "Item", "txt"), ("VALOR", "Valor", "txt")],
            [{"ITEM": i, "VALOR": val} for i, val in sobre], formatos)
    cols = [("NM_MUNICIPIO", "Município", "txt"), ("CD_MUNICIPIO_IBGE", "Código IBGE", "txt"),
            (f"VOTOS_{a}", f"Votos {a}", "int"), (f"PCT_VALIDOS_{a}", f"% válidos {a}", "pct"),
            (f"POSICAO_{a}", f"Posição {a}", "int"), ("PCT_SECOES_TOTALIZADAS", f"Seções totalizadas {a}", "pct"),
            (f"VOTOS_{b}", f"Votos {b}", "int"), (f"PCT_VALIDOS_{b}", f"% válidos {b}", "pct"),
            (f"POSICAO_{b}", f"Posição {b}", "int"), ("VAR_VOTOS_PCT", "Variação dos votos", "var"),
            ("VAR_PCT_VALIDOS_PP", "Variação % válidos (p.p.)", "pp")]
    bo._aba(wb, "Por município", cols, h.tabela.to_dicts(), formatos)
    wb.close()
    return buf.getvalue()
