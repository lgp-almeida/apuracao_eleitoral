"""Distribuição das cadeiras de deputado (sistema proporcional) — quociente eleitoral, partidário e sobras.

Regras (Código Eleitoral arts. 106–109; Res.-TSE 23.677/2021, art. 12-A na redação da Res. 23.748/2026):

1. QE  = votos válidos ÷ vagas, desprezada a fração ≤ 0,5 e arredondada para cima se > 0,5 (art. 106).
2. QP  = votos da agremiação ÷ QE, desprezada a fração (art. 107). Agremiação = partido isolado ou
   FEDERAÇÃO (conta como um só partido). Ocupam as vagas do QP os candidatos mais votados da
   agremiação que tenham ≥ 10% do QE (art. 108); a vaga do QP sem candidato assim vai para as sobras.
3. Sobras, fase 1 (art. 109 I–II): maior média = votos ÷ (lugares obtidos + 1), só entre agremiações
   com ≥ 80% do QE e que ainda tenham candidato com ≥ 20% do QE; a vaga vai para esse candidato.
4. Sobras, fase 2 (art. 109 III; art. 12-A II): acabadas as agremiações da fase 1, as vagas restantes
   vão pela maior média a TODAS as agremiações que disputaram, ocupadas pelo mais votado não eleito,
   sem votação mínima. É a regra do STF (ADIs 7228/7263/7325), positivada para 2026 e aplicada
   retroativamente a 2022.

Validação (rodada 20): com os microdados oficiais de 2022 (regerados pelo TSE em 30/09/2026, já com o
recálculo do STF), esta regra reproduz as 1.572 vagas de deputado das 27 UFs sem nenhuma divergência,
inclusive QP × média; 9 delas saem na fase 2 (AP, DF, RO, TO — as trocadas pelo STF em 2025).

Desempates: média igual → a agremiação mais votada; candidatos com o mesmo voto → o mais idoso
(art. 110). O JSON do tempo real não traz a idade, mas traz a ordem do próprio TSE (`seq`), que já
embute esse desempate: é o DESEMPATE da divulgação (no simulado, 2 empates exatos só batem assim).
Sem DESEMPATE, vence o menor número.

Tudo aqui é puro (sem I/O): as entradas vêm do tempo real (`entrada_divulgacao`) ou dos microdados
oficiais (`entrada_munzona`, usada para validar contra 2022).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

import votos_por_local_votacao as v

PROPORCIONAIS = {6: "Deputado Federal", 7: "Deputado Estadual", 8: "Deputado Distrital"}
ELEITO_QP, ELEITO_MEDIA, SUPLENTE, NAO_ELEITO = "Eleito por QP", "Eleito por média", "Suplente", "Não eleito"


def quociente_eleitoral(validos: int, vagas: int) -> int:
    """Art. 106: fração ≤ 0,5 desprezada; > 0,5 arredonda para cima (aritmética inteira, sem float)."""
    if vagas <= 0:
        raise ValueError("vagas deve ser positivo")
    q, r = divmod(validos, vagas)
    return q + (1 if 2 * r > vagas else 0)


@dataclass
class Distribuicao:
    """Resultado da distribuição, com o passo a passo das sobras (para conferir e explicar)."""

    vagas: int
    validos: int
    qe: int
    agremiacoes: pl.DataFrame          # AGREMIACAO, NOME, VOTOS, QP, VAGAS_QP, VAGAS_MEDIA, VAGAS, PCT_QE
    candidatos: pl.DataFrame           # entrada + SITUACAO_PROJETADA, ORDEM, MARGEM
    sobras: list[dict] = field(default_factory=list)  # uma linha por vaga de sobra: fase, agremiação, média
    vagas_nao_preenchidas: int = 0

    @property
    def limites(self) -> dict[str, float]:
        return {"cand_qp": 0.1 * self.qe, "cand_sobras": 0.2 * self.qe, "agrem_sobras": 0.8 * self.qe}


def distribuir(agremiacoes: pl.DataFrame, candidatos: pl.DataFrame, vagas: int, validos: int) -> Distribuicao:
    """`agremiacoes`: AGREMIACAO, NOME, VOTOS (válidos: nominais + legenda).
    `candidatos`: AGREMIACAO, NUMERO, NOME, VOTOS (nominais válidos), VALIDO (pode assumir vaga) e,
    opcional, DESEMPATE (menor vence no empate de votos: `seq` do TSE ou data de nascimento AAAAMMDD)."""
    if validos <= 0:  # início da apuração: sem voto válido não há quociente (e não se divide por zero)
        raise v.TseDataError("ainda não há votos válidos apurados para distribuir as cadeiras")
    qe = quociente_eleitoral(validos, vagas)
    votos = dict(zip(agremiacoes["AGREMIACAO"], agremiacoes["VOTOS"]))
    tem_desempate = "DESEMPATE" in candidatos.columns
    fila: dict[str, list[dict]] = {a: [] for a in votos}  # candidatos aptos por agremiação, do mais votado
    ordem = candidatos.with_columns(
        (pl.col("DESEMPATE") if tem_desempate else pl.lit(None, pl.Int64)).fill_null(2**62).alias("_DESEMP"))
    for c in ordem.filter(pl.col("VALIDO")).sort(["VOTOS", "_DESEMP", "NUMERO"], descending=[True, False, False]) \
                  .iter_rows(named=True):
        fila.setdefault(c["AGREMIACAO"], []).append(c)
        votos.setdefault(c["AGREMIACAO"], 0)

    eleitos, lugares, vagas_qp, sobras, restantes = _eleger(votos, fila, vagas, qe)

    # situação de cada candidato, ordem na lista da agremiação e margem para o último eleito
    ultimo = {}
    for a, lista in fila.items():
        el = [c["VOTOS"] for c in lista if (a, c["NUMERO"]) in eleitos]
        ultimo[a] = min(el) if el else None
    primeiro_supl = {a: next((c["VOTOS"] for c in lista if (a, c["NUMERO"]) not in eleitos), None)
                     for a, lista in fila.items()}
    pos = {(a, c["NUMERO"]): i + 1 for a, lista in fila.items() for i, c in enumerate(lista)}

    def situacao(a: str, n: int, valido: bool) -> str:
        if (a, n) in eleitos:
            return eleitos[(a, n)]
        return SUPLENTE if valido else NAO_ELEITO

    cand = candidatos.with_columns(
        pl.struct("AGREMIACAO", "NUMERO", "VALIDO").map_elements(
            lambda r: situacao(r["AGREMIACAO"], r["NUMERO"], r["VALIDO"]), return_dtype=pl.String)
        .alias("SITUACAO_PROJETADA"),
        pl.struct("AGREMIACAO", "NUMERO").map_elements(lambda r: pos.get((r["AGREMIACAO"], r["NUMERO"])),
                                                       return_dtype=pl.Int64).alias("ORDEM"),
    ).with_columns(
        # eleito: vantagem sobre o 1º suplente da agremiação; suplente: votos que faltam para passar o
        # último eleito da agremiação (com o nº de cadeiras dela mantido)
        pl.struct("AGREMIACAO", "VOTOS", "SITUACAO_PROJETADA").map_elements(
            lambda r: _margem(r, ultimo, primeiro_supl), return_dtype=pl.Int64).alias("MARGEM"))

    agr = agremiacoes.select("AGREMIACAO", "NOME", "VOTOS").with_columns(
        (pl.col("VOTOS") // qe).alias("QP"),
        pl.col("AGREMIACAO").replace_strict(vagas_qp, default=0, return_dtype=pl.Int64).alias("VAGAS_QP"),
        pl.col("AGREMIACAO").replace_strict(lugares, default=0, return_dtype=pl.Int64).alias("VAGAS"),
        (100 * pl.col("VOTOS") / qe).alias("PCT_QE"),
    ).with_columns((pl.col("VAGAS") - pl.col("VAGAS_QP")).alias("VAGAS_MEDIA")) \
     .sort(["VAGAS", "VOTOS"], descending=True)
    return Distribuicao(vagas, validos, qe, agr, cand, sobras, restantes)


def _eleger(votos: dict, fila: dict[str, list[dict]], vagas: int, qe: int
            ) -> tuple[dict[tuple[str, int], str], dict[str, int], dict[str, int], list[dict], int]:
    """Núcleo da distribuição em Python puro (rápido o bastante para centenas de simulações).
    `fila[a]`: candidatos aptos da agremiação `a` (dicts com NUMERO, NOME, VOTOS), do mais votado.
    Devolve (eleitos {(agremiação, nº): situação}, lugares, vagas pelo QP, sobras, vagas não preenchidas)."""
    eleitos: dict[tuple[str, int], str] = {}
    lugares = {a: 0 for a in votos}
    vagas_qp = {a: 0 for a in votos}

    def proximo(a: str, minimo: float) -> dict | None:
        return next((c for c in fila.get(a, ()) if (a, c["NUMERO"]) not in eleitos and c["VOTOS"] >= minimo), None)

    # QP: as vagas do quociente partidário, para quem tem ≥ 10% do QE
    for a, vt in votos.items():
        for _ in range(int(vt // qe)):
            c = proximo(a, 0.1 * qe)
            if c is None:
                break  # vaga do QP sem candidato com 10% do QE: vai para as sobras
            eleitos[(a, c["NUMERO"])] = ELEITO_QP
            lugares[a] += 1
            vagas_qp[a] += 1
    restantes = vagas - sum(lugares.values())
    if restantes < 0:
        raise ValueError("mais vagas pelo QP do que vagas em disputa (entrada inconsistente)")

    sobras: list[dict] = []

    def rodada(fase: int, participa, minimo_cand: float) -> bool:
        aptas = [a for a in votos if participa(a) and proximo(a, minimo_cand) is not None]
        if not aptas:
            return False
        a = max(aptas, key=lambda x: (votos[x] / (lugares[x] + 1), votos[x]))
        c = proximo(a, minimo_cand)
        sobras.append({"FASE": fase, "AGREMIACAO": a, "MEDIA": votos[a] / (lugares[a] + 1), "NUMERO": c["NUMERO"],
                       "NOME": c["NOME"]})
        eleitos[(a, c["NUMERO"])] = ELEITO_MEDIA
        lugares[a] += 1
        return True

    # sobras, fase 1: agremiações com 80% do QE e candidato com 20% do QE
    while restantes and rodada(1, lambda a: votos[a] >= 0.8 * qe, 0.2 * qe):
        restantes -= 1
    # sobras, fase 2: todas as agremiações, sem votação mínima do candidato
    while restantes and rodada(2, lambda a: True, 0):
        restantes -= 1
    return eleitos, lugares, vagas_qp, sobras, restantes


def _margem(r: dict, ultimo: dict, primeiro_supl: dict) -> int | None:
    a, vt, s = r["AGREMIACAO"], r["VOTOS"], r["SITUACAO_PROJETADA"]
    if s in (ELEITO_QP, ELEITO_MEDIA):
        sup = primeiro_supl.get(a)
        return None if sup is None else vt - sup
    if s == SUPLENTE and ultimo.get(a) is not None:
        return ultimo[a] - vt + 1
    return None


# --------------------------------------------------------------------------
# Entradas
# --------------------------------------------------------------------------
def _chave_agremiacao(federacao: str, partido: str) -> pl.Expr:
    """Federação conta como um só partido; partido isolado é ele mesmo."""
    return pl.when(pl.col(federacao).is_not_null()).then(pl.col(federacao)).otherwise(pl.col(partido))


def entrada_divulgacao(totais: pl.DataFrame, candidatos: pl.DataFrame, partidos: pl.DataFrame, cargo: int,
                       uf: str) -> tuple[pl.DataFrame, pl.DataFrame, int, int]:
    """(agremiações, candidatos, vagas, válidos) a partir do `ultimo/` do coletor (UF inteira).

    Vale para a apuração parcial: a distribuição é a que sairia se a apuração parasse ali."""
    t = totais.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf.upper()))
    if t.is_empty() or t["VAGAS"][0] is None:
        raise v.TseDataError(f"sem totais de {PROPORCIONAIS.get(cargo, cargo)} para {uf}")
    vagas, validos = int(t["VAGAS"][0]), int(t["VALIDOS"][0] or 0)
    filtro = (pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf.upper())
    p = partidos.filter(filtro).with_columns(_chave_agremiacao("FEDERACAO", "PARTIDO").alias("AGREMIACAO_ID"))
    agr = (p.group_by("AGREMIACAO_ID")
           .agg(pl.col("VOTOS_TOTAL").fill_null(0).sum().alias("VOTOS"),
                pl.col("PARTIDO").unique().sort().str.join("/").alias("_PARTIDOS"))
           .with_columns(pl.when(pl.col("_PARTIDOS") == pl.col("AGREMIACAO_ID")).then(pl.col("AGREMIACAO_ID"))
                         .otherwise(pl.format("{} ({})", pl.col("AGREMIACAO_ID"), pl.col("_PARTIDOS"))).alias("NOME"))
           .select(pl.col("AGREMIACAO_ID").alias("AGREMIACAO"), "NOME", "VOTOS"))
    cand = (candidatos.filter(filtro)
            .select(_chave_agremiacao("FEDERACAO", "PARTIDO").alias("AGREMIACAO"), "NUMERO",
                    pl.col("NOME_URNA").alias("NOME"), "PARTIDO", pl.col("VOTOS").fill_null(0),
                    (pl.col("DESTINACAO").fill_null("Válido") == "Válido").alias("VALIDO"),
                    pl.col("SEQ").alias("DESEMPATE"), pl.col("SITUACAO").alias("SITUACAO_TSE")))
    return agr, cand, vagas, validos


def _ler_uf(zp: Path, uf: str, colunas: list[str]) -> pl.DataFrame:
    with zipfile.ZipFile(zp) as z:
        membro = v.pick_csv_member(z, uf)
        texto = z.read(membro).decode("latin-1")
    return pl.read_csv(io.StringIO(texto), separator=";", infer_schema=False, columns=colunas,
                       null_values=v.TSE_NULL_MARKERS)


def entrada_munzona(ano: int, uf: str, cargo: int, cache: Path, partidos: pl.DataFrame | None = None
                    ) -> tuple[pl.DataFrame, pl.DataFrame, int, int]:
    """(agremiações, candidatos com SITUACAO_TSE oficial, vagas, válidos) dos microdados.

    `votacao_partido_munzona` dá os válidos da agremiação (legenda + nominais válidos + nominais
    convertidos em legenda); `votacao_candidato_munzona` dá os nominais válidos, a destinação e a
    situação final de cada candidato (o gabarito). Vagas = eleitos oficiais. `partidos`: o
    votacao_partido_munzona RECONSTRUÍDO (`historico.partidos_munzona`, rodada 55) no lugar do oficial,
    enquanto o TSE não o publica (RJ 2022: igual ao oficial em todas as linhas)."""
    base = f"{v.CDN_BASE}"
    zp_c = v.download(v.DatasetSpec(f"votacao_candidato_munzona_{ano}",
                                    f"{base}/votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip", uf), cache)
    ordin = (pl.col("CD_TIPO_ELEICAO") == "2") & (pl.col("NR_TURNO") == "1") & (pl.col("CD_CARGO") == str(cargo))
    colunas_p = ["CD_TIPO_ELEICAO", "NR_TURNO", "CD_CARGO", "SG_PARTIDO", "NR_FEDERACAO", "SG_FEDERACAO",
                 "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_NOMINAIS_VALIDOS"]
    if partidos is None:
        zp_p = v.download(v.DatasetSpec(f"votacao_partido_munzona_{ano}",
                                        f"{base}/votacao_partido_munzona/votacao_partido_munzona_{ano}.zip", uf), cache)
        p = _ler_uf(zp_p, uf, colunas_p).filter(ordin)
    else:  # tipado: como texto, igual ao CSV
        p = partidos.filter(pl.col("SG_UF") == uf.upper()).select(pl.col(colunas_p).cast(pl.String)).filter(ordin)
    p = p.with_columns(pl.when(pl.col("NR_FEDERACAO").cast(pl.Int64, strict=False) > 0).then(pl.col("SG_FEDERACAO"))
                       .alias("FEDERACAO"))
    agr = (p.with_columns(_chave_agremiacao("FEDERACAO", "SG_PARTIDO").alias("AGREMIACAO"))
           .group_by("AGREMIACAO")
           .agg((pl.col("QT_TOTAL_VOTOS_LEG_VALIDOS").cast(pl.Int64) + pl.col("QT_VOTOS_NOMINAIS_VALIDOS").cast(pl.Int64))
                .sum().alias("VOTOS"))
           .with_columns(pl.col("AGREMIACAO").alias("NOME")).select("AGREMIACAO", "NOME", "VOTOS"))
    c = _ler_uf(zp_c, uf, ["CD_TIPO_ELEICAO", "NR_TURNO", "CD_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO",
                           "NM_URNA_CANDIDATO", "SG_PARTIDO", "NR_FEDERACAO", "SG_FEDERACAO",
                           "NM_TIPO_DESTINACAO_VOTOS", "QT_VOTOS_NOMINAIS_VALIDOS", "DS_SIT_TOT_TURNO"]).filter(ordin)
    c = c.with_columns(pl.when(pl.col("NR_FEDERACAO").cast(pl.Int64, strict=False) > 0).then(pl.col("SG_FEDERACAO"))
                       .alias("FEDERACAO"))
    cand = (c.group_by("SQ_CANDIDATO")
            .agg(_chave_agremiacao("FEDERACAO", "SG_PARTIDO").first().alias("AGREMIACAO"),
                 pl.col("NR_CANDIDATO").first().cast(pl.Int64).alias("NUMERO"),
                 pl.col("NM_URNA_CANDIDATO").first().alias("NOME"), pl.col("SG_PARTIDO").first().alias("PARTIDO"),
                 pl.col("QT_VOTOS_NOMINAIS_VALIDOS").cast(pl.Int64).sum().alias("VOTOS"),
                 (pl.col("NM_TIPO_DESTINACAO_VOTOS").first() == "Válido").alias("VALIDO"),
                 pl.col("DS_SIT_TOT_TURNO").first().alias("SITUACAO_TSE"))
            .drop("SQ_CANDIDATO"))
    validos = int(agr["VOTOS"].sum())
    vagas = int(cand["SITUACAO_TSE"].str.starts_with("ELEITO").sum())
    return agr, cand, vagas, validos


def comparar_com_oficial(d: Distribuicao) -> pl.DataFrame:
    """Candidatos em que a situação projetada difere da oficial (eleito × não eleito, e QP × média)."""
    norm = pl.col("SITUACAO_TSE").str.to_uppercase().str.replace("É", "E")
    return d.candidatos.with_columns(
        pl.when(norm.str.contains("QP")).then(pl.lit(ELEITO_QP))
        .when(norm.str.contains("MEDIA")).then(pl.lit(ELEITO_MEDIA)).otherwise(pl.lit("não eleito")).alias("_OF"),
        pl.when(pl.col("SITUACAO_PROJETADA").str.starts_with("Eleito")).then(pl.col("SITUACAO_PROJETADA"))
        .otherwise(pl.lit("não eleito")).alias("_PJ"),
    ).filter(pl.col("_OF") != pl.col("_PJ")).drop("_OF", "_PJ")
