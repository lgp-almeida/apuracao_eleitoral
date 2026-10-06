"""Resultado de uma eleição passada (microdados do TSE) no formato das tabelas do coletor.

O site de apuração lê dados_2026/<X>/ultimo/{totais,candidatos,partidos,municipios}.parquet.
A divulgação em JSON de eleições passadas saiu do ar (ex.: ele2022 → 404), então este
módulo monta as MESMAS tabelas a partir dos microdados da CDN:

  detalhe_votacao_munzona_<ano>  totais oficiais por município/zona e cargo (aptos,
                                 comparecimento, abstenção, válidos, legenda, brancos,
                                 nulos, anulados, anulados sub judice, seções)
  votacao_secao_<ano>_<UF>/_BR   votos por votável; somados por município, UF e Brasil (fonte "secao")
  votacao_{candidato,partido}_munzona_<ano>
                                 os mesmos votos já somados por município e zona (fonte "munzona",
                                 rodada 39): um arquivo nacional por ano serve às 27 UFs, sem baixar
                                 o votacao_secao de cada UF (vários GB por ano)
  consulta_cand_<ano>            nome de urna, partido, federação/coligação, situação por turno
  EA12 da divulgação 2026        código TSE → código IBGE dos municípios (para os mapas)

Abrangências: Brasil (só presidente, exterior incluído), a UF e cada município da UF.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao.divulgacao import modelo as m

logger = logging.getLogger("apuracao.historico")

CARGOS_UF = (3, 5, 6, 7, 8)  # 8 = deputado distrital (só DF)
CARGO_PRESIDENTE = 1
PROPORCIONAIS = (6, 7, 8)
ESPECIAIS = (95, 96, 97)  # branco, nulo, anulado em separado
MUNICIPIOS_CACHE = "municipios_tse_ibge.parquet"


# --------------------------------------------------------------------------
# Leitura dos arquivos pequenos (CSV latin-1 dentro do ZIP)
# --------------------------------------------------------------------------
def _spec(dataset: str, arquivo: str) -> v.DatasetSpec:
    return v.DatasetSpec(arquivo.removesuffix(".zip"), f"{v.CDN_BASE}/{dataset}/{arquivo}", v.NATIONAL)


def read_zip_csv(zip_path: Path, suffix: str = "_BRASIL.csv") -> pl.DataFrame:
    """CSV do TSE (latin-1, ';', aspas) como DataFrame de texto. Usa o membro *_BRASIL.csv."""
    with zipfile.ZipFile(zip_path) as zf:
        member = next((n for n in zf.namelist() if n.upper().endswith(suffix.upper())), None)
        if member is None:
            raise v.TseDataError(f"{zip_path.name}: sem membro {suffix}")
        data = zf.read(member).decode("latin-1").encode()
    return pl.read_csv(io.BytesIO(data), separator=";", infer_schema=False, null_values=v.TSE_NULL_MARKERS)


def load_detalhe(ano: int, cache: Path) -> pl.DataFrame:
    zp = v.download(_spec("detalhe_votacao_munzona", f"detalhe_votacao_munzona_{ano}.zip"), cache)
    return read_zip_csv(zp)


def load_candidatos(ano: int, cache: Path) -> pl.DataFrame:
    zp = v.download(_spec("consulta_cand", f"consulta_cand_{ano}.zip"), cache)
    return read_zip_csv(zp)


def load_votos(ano: int, uf: str, cache: Path) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """(votos da UF — cargos estaduais, votos do arquivo nacional — presidente, todas as UFs)."""
    uf_votes = v.load_section_votes(ano, uf, "governador", cache, False)
    spec = v.DatasetSpec(f"votacao_secao_{ano}_BR", f"{v.CDN_BASE}/votacao_secao/votacao_secao_{ano}_BR.zip", v.NATIONAL)
    zp = v.download(spec, cache)
    pq = v.zip_to_parquet(zp, spec, v.SECTION_VOTES_REQUIRED + v.SECTION_VOTES_OPTIONAL, v.SECTION_VOTES_REQUIRED, cache)
    return uf_votes, pl.scan_parquet(pq)


FONTES = ("secao", "munzona")
_COLS_MUNZONA = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "CD_CARGO"]
# votos de legenda no votacao_secao = todos os digitados para o partido (válidos, anulados e anulados sub judice)
_LEGENDA = ["QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_LEGENDA_ANUL_SUBJUD", "QT_VOTOS_LEGENDA_ANULADOS"]


def fonte_padrao(ano: int, uf: str, cache: Path) -> str:
    """"secao" se o votacao_secao da UF já está no cache (o RJ continua como sempre); senão "munzona"."""
    return "secao" if (cache / f"votacao_secao_{ano}_{uf.upper()}.zip").exists() else "munzona"


def _munzona_parquet(dataset: str, ano: int, cache: Path, colunas: list[str]) -> Path:
    """O CSV _BRASIL do arquivo nacional (todas as UFs, presidente e exterior uma vez só) convertido para
    Parquet uma vez; cada UF filtra depois."""
    spec = v.DatasetSpec(f"{dataset}_{ano}", f"{v.CDN_BASE}/{dataset}/{dataset}_{ano}.zip", v.NATIONAL,
                         member="_BRASIL.csv")
    zp = v.download(spec, cache)
    return v.zip_to_parquet(zp, spec, colunas, colunas[:4], cache)


def load_votos_munzona(ano: int, uf: str, cache: Path) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Os mesmos (votos da UF, votos nacionais) de `load_votos`, com as mesmas colunas, a partir dos arquivos
    por município e zona: nominais = QT_VOTOS_NOMINAIS de cada candidato; legenda (votável = nº do partido,
    só nos proporcionais) = votos de legenda válidos + anulados + anulados sub judice.

    Diferença conhecida (RJ 2022, rodada 39): o arquivo por município NÃO lista candidato com candidatura
    inapta (votos anulados — ex.: Daniel Silveira, senador, 1,57 milhão), nem o partido dele quando só ele
    teve votos; os votos dos demais candidatos, os válidos, os percentuais e os eleitos são idênticos à
    fonte "secao"."""
    cand = pl.scan_parquet(_munzona_parquet("votacao_candidato_munzona", ano, cache,
                                            _COLS_MUNZONA + ["NR_CANDIDATO", "QT_VOTOS_NOMINAIS"]))
    part_pq = _munzona_parquet("votacao_partido_munzona", ano, cache, _COLS_MUNZONA + ["NR_PARTIDO"] + _LEGENDA)
    part = pl.scan_parquet(part_pq)
    tem = set(part.collect_schema().names())  # 2014/2018 não têm todas as colunas
    inteiro = lambda c: pl.col(c).cast(pl.String).str.strip_chars().cast(pl.Int64, strict=False)  # noqa: E731
    soma = lambda cs: pl.sum_horizontal([inteiro(c).fill_null(0) for c in cs if c in tem] or [pl.lit(0)])  # noqa: E731
    nominais = cand.select(*_COLS_MUNZONA, inteiro("NR_CANDIDATO").alias("NR_VOTAVEL"),
                           inteiro("QT_VOTOS_NOMINAIS").alias("QT_VOTOS"))
    leg = (part.filter(pl.col("CD_CARGO").is_in(list(PROPORCIONAIS)))
           .select(*_COLS_MUNZONA, inteiro("NR_PARTIDO").alias("NR_VOTAVEL"), soma(_LEGENDA).alias("QT_VOTOS")))
    todos = (pl.concat([nominais, leg], how="vertical_relaxed").filter(pl.col("QT_VOTOS") > 0)
             .group_by(_COLS_MUNZONA + ["NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum()))
    return (todos.filter((pl.col("SG_UF") == uf.upper()) & (pl.col("CD_CARGO") != CARGO_PRESIDENTE)),
            todos.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE))


def municipios_tse_ibge(uf: str, cache: Path) -> pl.DataFrame:
    """Municípios da UF com código IBGE, a partir do EA12 da divulgação do TSE (em cache). UF ausente do cache
    (ex.: DF num cache gerado do EA12 de uma eleição municipal, que não tem o DF): o cache é refeito uma vez."""
    path = cache / MUNICIPIOS_CACHE
    if not path.exists():
        _baixar_municipios(path)
    df = pl.read_parquet(path).filter(pl.col("UF") == uf.upper())
    if df.is_empty():
        logger.warning("%s sem a UF %s: refazendo a tabela de municípios do TSE", path.name, uf.upper())
        _baixar_municipios(path)
        df = pl.read_parquet(path).filter(pl.col("UF") == uf.upper())
    return df


def _baixar_municipios(path: Path) -> None:
    """EA12 da eleição estadual mais recente do `ele-c.json` (oficial; senão simulado), gravado em `path`."""
    from apuracao.divulgacao.cliente import BloqueioTSE, ClienteDivulgacao, DivulgacaoIndisponivel
    for ambiente in ("oficial", "simulado"):
        cli = ClienteDivulgacao(ambiente)
        try:
            resp = cli.get_json(cli.caminho_config())
            if resp is None:
                continue
            cfg = m.parse_config(resp.dados)
            e = cfg.por_cargo(3) or cfg.eleicoes[0]
            cm = cli.get_json(cli.caminho_municipios(cfg, e.codigo))
            if cm is not None:
                tmp = path.with_suffix(".parquet.tmp")
                m.parse_municipios(cm.dados).write_parquet(tmp)
                tmp.replace(path)
                return
        except (DivulgacaoIndisponivel, BloqueioTSE, requests.RequestException) as exc:
            logger.warning("EA12 indisponível no ambiente %s: %s", ambiente, exc)
    raise v.TseDataError("não foi possível obter a tabela de municípios (EA12) do TSE")


# --------------------------------------------------------------------------
# Totais (detalhe_votacao_munzona)
# --------------------------------------------------------------------------
_SOMAS = {
    "ELEITORADO": "QT_APTOS", "COMPARECIMENTO": "QT_COMPARECIMENTO", "ABSTENCAO": "QT_ABSTENCOES",
    "SECOES_TOTAL": "QT_TOTAL_SECOES", "VOTOS_TOTAL": "QT_VOTOS", "VALIDOS": "QT_TOTAL_VOTOS_VALIDOS",
    "NOMINAIS": "QT_VOTOS_NOMINAIS_VALIDOS", "LEGENDA": "QT_TOTAL_VOTOS_LEG_VALIDOS", "BRANCOS": "QT_VOTOS_BRANCOS",
    "NULOS": "QT_TOTAL_VOTOS_NULOS", "ANULADOS": "QT_TOTAL_VOTOS_ANULADOS",
    "ANULADOS_SUB_JUDICE": "QT_TOTAL_VOTOS_ANUL_SUBJUD",
}


def _pct(num: str, den: str) -> pl.Expr:
    return pl.when(pl.col(den) > 0).then(100 * pl.col(num) / pl.col(den)).otherwise(None)


def totais(detalhe: pl.DataFrame, uf: str, turno: int) -> pl.DataFrame:
    """Totais por cargo e abrangência (br só para presidente; uf; municípios da UF)."""
    uf = uf.upper()
    d = detalhe.with_columns(
        [pl.col(c).cast(pl.Int64) for c in ("NR_TURNO", "CD_CARGO", "CD_ELEICAO", "CD_MUNICIPIO")]
        + [pl.col(c).cast(pl.Int64) for c in _SOMAS.values()]
        + [pl.concat_str([pl.col("DT_ULTIMA_TOTALIZACAO"), pl.col("HH_ULTIMA_TOTALIZACAO")], separator=" ")
           .str.to_datetime("%d/%m/%Y %H:%M:%S", strict=False).alias("_DT")]
    ).filter(pl.col("NR_TURNO") == turno)
    d_uf = d.filter((pl.col("SG_UF") == uf) & pl.col("CD_CARGO").is_in([*CARGOS_UF, CARGO_PRESIDENTE]))
    d_br = d.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE)
    aggs = [pl.col("CD_ELEICAO").first().alias("ELEICAO"), pl.col("DS_CARGO").first(), pl.col("_DT").max()] + [
        pl.col(src).sum().alias(dst) for dst, src in _SOMAS.items()]
    partes = [
        d_uf.group_by("CD_CARGO", "CD_MUNICIPIO").agg(aggs).with_columns(
            pl.lit("mun").alias("ABRANGENCIA"), pl.lit(uf).alias("UF")),
        d_uf.group_by("CD_CARGO").agg(aggs).with_columns(
            pl.lit("uf").alias("ABRANGENCIA"), pl.lit(uf).alias("UF"), pl.lit(None, dtype=pl.Int64).alias("CD_MUNICIPIO")),
        d_br.group_by("CD_CARGO").agg(aggs).with_columns(
            pl.lit("br").alias("ABRANGENCIA"), pl.lit("BR").alias("UF"), pl.lit(None, dtype=pl.Int64).alias("CD_MUNICIPIO")),
    ]
    t = pl.concat(partes, how="diagonal_relaxed").with_columns(
        pl.col("CD_CARGO").alias("CARGO"), pl.lit(turno).alias("TURNO"),
        pl.col("_DT").alias("DT_TOTALIZACAO"), pl.lit(True).alias("TOTALIZACAO_FINAL"),
        pl.lit(False).alias("MATEMATICAMENTE_DEFINIDA"),
        pl.col("SECOES_TOTAL").alias("SECOES_TOTALIZADAS"), pl.lit(100.0).alias("PCT_SECOES_TOTALIZADAS"),
        _pct("COMPARECIMENTO", "ELEITORADO").alias("PCT_COMPARECIMENTO"),
        _pct("ABSTENCAO", "ELEITORADO").alias("PCT_ABSTENCAO"),
        _pct("VALIDOS", "VOTOS_TOTAL").alias("PCT_VALIDOS"), _pct("BRANCOS", "VOTOS_TOTAL").alias("PCT_BRANCOS"),
        _pct("NULOS", "VOTOS_TOTAL").alias("PCT_NULOS"),
        _pct("ANULADOS_SUB_JUDICE", "VOTOS_TOTAL").alias("PCT_ANULADOS_SUB_JUDICE"),
        pl.lit(None, dtype=pl.Int64).alias("VAGAS"), pl.lit(None, dtype=pl.Int64).alias("QUOCIENTE_ELEITORAL"),
        pl.lit(None, dtype=pl.String).alias("IDG"),
    )
    return t.select([pl.col(c).cast(tp) for c, tp in m.TOTAIS_SCHEMA.items()])


# --------------------------------------------------------------------------
# Candidatos e partidos (votacao_secao + consulta_cand)
# --------------------------------------------------------------------------
def cadastro(cand: pl.DataFrame, uf: str, turno: int) -> pl.DataFrame:
    """Uma linha por (UF do cadastro, cargo, número): prefere candidatura APTA com situação preenchida."""
    c = cand.with_columns([pl.col(x).cast(pl.Int64) for x in ("NR_TURNO", "CD_CARGO", "NR_CANDIDATO", "NR_PARTIDO",
                                                              "SQ_CANDIDATO")]).filter(
        (pl.col("NR_TURNO") == turno) & (
            ((pl.col("SG_UF") == uf.upper()) & pl.col("CD_CARGO").is_in(CARGOS_UF))
            | ((pl.col("SG_UF") == "BR") & (pl.col("CD_CARGO") == CARGO_PRESIDENTE))))
    return (
        c.with_columns(((pl.col("DS_SITUACAO_CANDIDATURA") == "APTO").cast(pl.Int8) * 2
                        + pl.col("DS_SIT_TOT_TURNO").is_not_null().cast(pl.Int8)).alias("_pref"))
        .sort("_pref", descending=True)
        .unique(subset=["CD_CARGO", "NR_CANDIDATO"], keep="first")
        .select(
            pl.col("CD_CARGO").alias("CARGO"), pl.col("NR_CANDIDATO").alias("NUMERO"),
            pl.col("NM_URNA_CANDIDATO").alias("NOME_URNA"), pl.col("NM_CANDIDATO").alias("NOME"), "SQ_CANDIDATO",
            pl.col("SG_PARTIDO").alias("PARTIDO"), "NR_PARTIDO",
            pl.coalesce(pl.col("SG_FEDERACAO"), pl.col("NM_FEDERACAO")).alias("FEDERACAO"),
            pl.when(pl.col("NM_COLIGACAO") == "PARTIDO ISOLADO").then(pl.col("SG_PARTIDO"))
            .otherwise(pl.col("NM_COLIGACAO")).alias("AGREMIACAO"),
            pl.col("DS_COMPOSICAO_COLIGACAO").alias("COMPOSICAO"),
            _situacao(pl.col("DS_SIT_TOT_TURNO")).alias("SITUACAO"),
            # o consulta_cand é regerado pelo TSE e reflete decisões POSTERIORES ao pleito (ex.: em
            # 2022 Cláudio Castro foi eleito com votos válidos, mas consta INAPTO no cadastro de
            # 29/09/2026). Não dá para deduzir daqui a destinação do voto na totalização.
            pl.when(pl.col("DS_SITUACAO_CANDIDATURA") == "APTO").then(pl.lit("Válido"))
            .otherwise(pl.format("candidatura {} no cadastro de {}", pl.col("DS_SITUACAO_CANDIDATURA"),
                                 pl.col("DT_GERACAO"))).alias("DESTINACAO"),
        )
    )


def _situacao(expr: pl.Expr) -> pl.Expr:
    """"ELEITO POR QP" -> "Eleito por QP" (mesma grafia da divulgação em tempo real)."""
    s = expr.str.to_lowercase()
    s = pl.concat_str([s.str.slice(0, 1).str.to_uppercase(), s.str.slice(1)])
    return s.str.replace(" qp", " QP")


def _votos_por_abrangencia(lf: pl.LazyFrame, uf: str, turno: int, cargos: tuple[int, ...], com_br: bool) -> pl.DataFrame:
    base = lf.filter((pl.col("NR_TURNO") == turno) & pl.col("CD_CARGO").is_in(list(cargos)))
    no_uf = base.filter(pl.col("SG_UF") == uf.upper())
    partes = [
        no_uf.group_by("CD_CARGO", "CD_MUNICIPIO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum())
        .with_columns(pl.lit("mun").alias("ABRANGENCIA"), pl.lit(uf.upper()).alias("UF")),
        no_uf.group_by("CD_CARGO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum())
        .with_columns(pl.lit("uf").alias("ABRANGENCIA"), pl.lit(uf.upper()).alias("UF"),
                      pl.lit(None, dtype=pl.Int64).alias("CD_MUNICIPIO")),
    ]
    if com_br:
        partes.append(base.group_by("CD_CARGO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum()).with_columns(
            pl.lit("br").alias("ABRANGENCIA"), pl.lit("BR").alias("UF"), pl.lit(None, dtype=pl.Int64).alias("CD_MUNICIPIO")))
    return pl.concat([p.collect() for p in partes], how="diagonal_relaxed").rename({"CD_CARGO": "CARGO"})


def candidatos_e_partidos(votos_uf: pl.LazyFrame, votos_br: pl.LazyFrame, cand: pl.DataFrame, tot: pl.DataFrame,
                          uf: str, turno: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    votos = pl.concat([
        _votos_por_abrangencia(votos_uf, uf, turno, CARGOS_UF, com_br=False),
        _votos_por_abrangencia(votos_br, uf, turno, (CARGO_PRESIDENTE,), com_br=True),
    ], how="diagonal_relaxed")
    chave = ["CARGO", "ABRANGENCIA", "UF", "CD_MUNICIPIO"]
    validos = tot.select(chave + ["ELEICAO", "VALIDOS"])
    cad = cadastro(cand, uf, turno)
    proporcional = pl.col("CARGO").is_in(PROPORCIONAIS)
    nominal = ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS) & (~proporcional | (pl.col("NR_VOTAVEL") >= 100))

    c = (
        votos.filter(nominal).rename({"NR_VOTAVEL": "NUMERO", "QT_VOTOS": "VOTOS"})
        .join(cad, on=["CARGO", "NUMERO"], how="left")
        .join(validos, on=chave, how="left", nulls_equal=True)
        .with_columns(
            pl.when(pl.col("VALIDOS") > 0).then(100 * pl.col("VOTOS") / pl.col("VALIDOS")).otherwise(None)
            .alias("PCT_VALIDOS"),
            pl.col("VOTOS").rank("ordinal", descending=True).over(chave).cast(pl.Int64).alias("SEQ"),
            pl.col("SITUACAO").fill_null("Não informado"),
            pl.col("DESTINACAO").fill_null("Válido"),
            pl.lit(None, dtype=pl.String).alias("VICES"),
        )
        .with_columns(pl.col("SITUACAO").str.starts_with("Eleito").or_(pl.col("SITUACAO") == "2º turno").alias("ELEITO"))
    )
    candidatos = c.select([pl.col(k).cast(tp) for k, tp in m.CANDIDATOS_SCHEMA.items()])

    # partidos (proporcionais): nominais dos candidatos + votos de legenda (votável de 2 dígitos)
    nomin = c.filter(proporcional).group_by(chave + ["NR_PARTIDO"]).agg(
        pl.col("VOTOS").sum().alias("VOTOS_NOMINAIS"),
        pl.col("SITUACAO").str.starts_with("Eleito").sum().cast(pl.Int64).alias("VAGAS_AGREMIACAO"))
    leg = (votos.filter(proporcional & (pl.col("NR_VOTAVEL") < 100) & ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS))
           .select(chave + [pl.col("NR_VOTAVEL").alias("NR_PARTIDO"), pl.col("QT_VOTOS").alias("VOTOS_LEGENDA")]))
    siglas = cad.select("NR_PARTIDO", "PARTIDO", "FEDERACAO", "AGREMIACAO").unique(subset=["NR_PARTIDO"], keep="first")
    partidos = (
        nomin.join(leg, on=chave + ["NR_PARTIDO"], how="full", coalesce=True, nulls_equal=True)
        .join(siglas, on="NR_PARTIDO", how="left")
        .join(validos.select(chave + ["ELEICAO"]), on=chave, how="left", nulls_equal=True)
        .with_columns(pl.col("VOTOS_NOMINAIS").fill_null(0), pl.col("VOTOS_LEGENDA").fill_null(0))
        .with_columns((pl.col("VOTOS_NOMINAIS") + pl.col("VOTOS_LEGENDA")).alias("VOTOS_TOTAL"))
        .select([pl.col(k).cast(tp) for k, tp in m.PARTIDOS_SCHEMA.items()])
    )
    return candidatos, partidos


def vagas(tot: pl.DataFrame, candidatos: pl.DataFrame) -> pl.DataFrame:
    """Vagas por cargo = nº de eleitos na UF/BR (majoritário sem eleito ainda — 2º turno pendente — conta 1)."""
    eleitos = (candidatos.filter(pl.col("ABRANGENCIA").is_in(["uf", "br"]) & pl.col("SITUACAO").str.starts_with("Eleito"))
               .group_by("CARGO", "ABRANGENCIA").len().rename({"len": "_V"}))
    return (tot.join(eleitos, on=["CARGO", "ABRANGENCIA"], how="left")
            .with_columns(pl.when(pl.col("CARGO").is_in(PROPORCIONAIS)).then(pl.col("_V"))
                          .otherwise(pl.col("_V").fill_null(1)).alias("VAGAS"))
            .drop("_V").select(list(m.TOTAIS_SCHEMA)))


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------
def importar(ano: int, uf: str, turno: int, cache: Path, destino: Path, fonte: str | None = None) -> dict[str, int]:
    """Grava destino/ultimo/*.parquet + status.json no formato lido pelo site. `fonte` dos votos:
    "secao" (votacao_secao da UF + BR) ou "munzona" (arquivos nacionais por município e zona);
    padrão: `fonte_padrao`."""
    fonte = fonte or fonte_padrao(ano, uf, cache)
    if fonte not in FONTES:
        raise ValueError(f"fonte desconhecida: {fonte} (use {' ou '.join(FONTES)})")
    det, cand = load_detalhe(ano, cache), load_candidatos(ano, cache)
    tot = totais(det, uf, turno)
    if tot.is_empty():
        raise v.TseDataError(f"sem totais para {uf} {ano}, {turno}º turno")
    votos_uf, votos_br = (load_votos if fonte == "secao" else load_votos_munzona)(ano, uf, cache)
    candidatos, partidos = candidatos_e_partidos(votos_uf, votos_br, cand, tot, uf, turno)
    tot = vagas(tot, candidatos)
    municipios = municipios_tse_ibge(uf, cache)

    ultimo = destino / "ultimo"
    ultimo.mkdir(parents=True, exist_ok=True)
    for nome, df in (("totais", tot), ("candidatos", candidatos), ("partidos", partidos), ("municipios", municipios),
                     ("acompanhamento", pl.DataFrame(schema=m.ACOMPANHAMENTO_SCHEMA))):
        tmp = ultimo / f"{nome}.parquet.tmp"
        df.write_parquet(tmp)
        tmp.replace(ultimo / f"{nome}.parquet")
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = {
        "ambiente": f"{ano} · {turno}º turno (microdados)", "ano": ano, "uf": uf.upper(), "turno": turno,
        "ciclo_tse": f"microdados {ano}", "ultimo_ciclo_inicio": agora, "ultimo_ciclo_fim": agora, "erro": None,
        "fontes": [f"detalhe_votacao_munzona_{ano}",
                   *([f"votacao_secao_{ano}_{uf.upper()}", f"votacao_secao_{ano}_BR"] if fonte == "secao"
                     else [f"votacao_candidato_munzona_{ano}", f"votacao_partido_munzona_{ano}"]),
                   f"consulta_cand_{ano}", "EA12 (divulgação TSE 2026) para o código IBGE"],
    }
    (destino / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    return {"totais": tot.height, "candidatos": candidatos.height, "partidos": partidos.height,
            "municipios": municipios.height}
