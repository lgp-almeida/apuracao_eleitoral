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
  consulta_cand_<ano>            nome de urna, partido, federação/coligação
  votacao_candidato_munzona_<ano>
                                 destinação dos votos e situação de cada candidato NA TOTALIZAÇÃO
                                 (rodada 40: o consulta_cand é regerado e reflete decisões posteriores —
                                 Castro 2022 consta INAPTO lá e "Válido"/"ELEITO" aqui)
  EA12 da divulgação 2026        código TSE → código IBGE dos municípios (para os mapas)

Totais (`importar(totais=...)`, rodada 40): "munzona" = os oficiais do detalhe_votacao_munzona; "secoes" =
reconstruídos, enquanto o TSE não publica o detalhe munzona, dos votos por seção + detalhe por seção
(aptos, comparecimento, abstenção) + destinação de cada candidato (`detalhe_de_secoes`). Conferido no RJ
2022: zero diferença nas 732 combinações zona × cargo (válidos, legenda, brancos, nulos, nulos técnicos,
anulados, sub judice). Rodada 48: a legenda segue a AGREMIAÇÃO (`destino_legenda`); 2022 igual ao oficial
em 16 das 25 UFs com votos por seção, 2026 igual à noite em 24 de 25.

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


FONTES = ("secao", "munzona", "bweb")
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


_COLS_DESTINACAO = ["NR_CANDIDATO", "NR_PARTIDO", "CD_ELEICAO", "NM_TIPO_DESTINACAO_VOTOS", "DS_SIT_TOT_TURNO"]
_COLS_FEDERACAO = ("SG_PARTIDO", "NR_FEDERACAO", "DS_COMPOSICAO_FEDERACAO")  # desde 2022 (federações)


def _cabecalho(dataset: str, ano: int, cache: Path) -> set[str]:
    """Colunas do CSV _BRASIL do ZIP nacional no cache."""
    with zipfile.ZipFile(cache / f"{dataset}_{ano}.zip") as zf:
        return set(v.read_header(zf, v.pick_csv_member(zf, v.NATIONAL, "_BRASIL.csv")))


def _parquet_com_colunas(dataset: str, ano: int, cache: Path, colunas: list[str],
                         opcionais: tuple[str, ...] = ()) -> Path:
    """`_munzona_parquet` garantindo as colunas: um Parquet convertido antes com menos colunas é refeito;
    se nem o ZIP as tiver (layout de outro ano), `TseDataError`. `opcionais` entram quando o CSV as tem (as
    federações só existem desde 2022): o Parquet só é refeito se faltar uma que o CSV tem."""
    todas = colunas + [c for c in opcionais if c not in colunas]
    pq = _munzona_parquet(dataset, ano, cache, todas)
    tem = set(pl.scan_parquet(pq).collect_schema().names())
    falta_opcional = set(opcionais) - tem
    if not set(colunas) <= tem or (falta_opcional and falta_opcional & _cabecalho(dataset, ano, cache)):
        pq.unlink()
        pq = _munzona_parquet(dataset, ano, cache, todas)
        faltam = set(colunas) - set(pl.scan_parquet(pq).collect_schema().names())
        if faltam:
            raise v.TseDataError(f"{dataset}_{ano} sem as colunas {', '.join(sorted(faltam))}")
    return pq


def destinacao_oficial(ano: int, cache: Path) -> pl.DataFrame:
    """Uma linha por (turno, UF, cargo, número): destinação dos votos e situação na totalização, do
    votacao_candidato_munzona (o gabarito: não é regerado como o consulta_cand). Presidente: em todas as UFs
    (e "ZZ", exterior). Candidato com candidatura negada ANTES da eleição não está aqui: os votos nele são
    nulos técnicos. Só do CACHE (sem rede): no 2026 o `preparar_2026` baixa o arquivo antes de importar, e os
    anos anteriores já estão lá; ausente → `TseDataError`."""
    if not (cache / f"votacao_candidato_munzona_{ano}.zip").exists():
        raise v.TseDataError(f"votacao_candidato_munzona_{ano}.zip não está no cache")
    pq = _parquet_com_colunas("votacao_candidato_munzona", ano, cache,
                              _COLS_MUNZONA + ["QT_VOTOS_NOMINAIS"] + _COLS_DESTINACAO, _COLS_FEDERACAO)
    inteiro = lambda c: pl.col(c).cast(pl.String).str.strip_chars().cast(pl.Int64, strict=False)  # noqa: E731
    tem = set(pl.scan_parquet(pq).collect_schema().names())
    texto = lambda c: pl.col(c).cast(pl.String) if c in tem else pl.lit(None, pl.String)  # noqa: E731
    federacao = inteiro("NR_FEDERACAO") if "NR_FEDERACAO" in tem else pl.lit(None, pl.Int64)
    return (pl.scan_parquet(pq)
            .select(inteiro("NR_TURNO").alias("NR_TURNO"), "SG_UF", inteiro("CD_CARGO").alias("CD_CARGO"),
                    inteiro("NR_CANDIDATO").alias("NUMERO"), inteiro("NR_PARTIDO").alias("NR_PARTIDO"),
                    inteiro("CD_ELEICAO").alias("CD_ELEICAO"),
                    pl.col("NM_TIPO_DESTINACAO_VOTOS").alias("DESTINACAO_TSE"),
                    pl.col("DS_SIT_TOT_TURNO").alias("SITUACAO_TSE"),
                    texto("SG_PARTIDO").alias("SG_PARTIDO"),
                    pl.when(federacao > 0).then(federacao).alias("NR_FEDERACAO"),  # -1 = sem federação
                    texto("DS_COMPOSICAO_FEDERACAO").alias("COMPOSICAO_FEDERACAO"))
            .unique(["NR_TURNO", "SG_UF", "CD_CARGO", "NUMERO"], keep="first").collect())


def _agremiacoes(destinacao: pl.DataFrame) -> pl.DataFrame:
    """NR_PARTIDO → _AGREMIACAO ("F<nº da federação>") dos partidos federados, inclusive o sócio sem candidato
    próprio, que só aparece pela SIGLA na composição ("PCDOB / PT / PV"; ligada ao número pela sigla dos
    candidatos de qualquer UF, comparada por `partidos.chave`). Partido fora daqui é a própria agremiação."""
    from apuracao import partidos as pt

    vazio = pl.DataFrame(schema={"NR_PARTIDO": pl.Int64, "_AGREMIACAO": pl.String})
    if "NR_FEDERACAO" not in destinacao.columns:
        return vazio
    numero = {pt.chave(s): n for s, n in destinacao.filter(pl.col("SG_PARTIDO").is_not_null())
              .select("SG_PARTIDO", "NR_PARTIDO").unique().iter_rows()}
    fed = destinacao.filter(pl.col("NR_FEDERACAO").is_not_null())
    pares = set(fed.select("NR_PARTIDO", "NR_FEDERACAO").iter_rows())
    for f, comp in fed.select("NR_FEDERACAO", "COMPOSICAO_FEDERACAO").unique().iter_rows():
        for sigla in (pt.normalizar_federacao(comp) or "").split("/"):
            if pt.chave(sigla) in numero:
                pares.add((numero[pt.chave(sigla)], f))
            elif sigla.strip():
                logger.debug("federação %s: sigla %r sem candidato em nenhuma UF", f, sigla)
    if not pares:
        return vazio
    return pl.DataFrame(sorted(pares), schema={"NR_PARTIDO": pl.Int64, "_F": pl.Int64}, orient="row").select(
        "NR_PARTIDO", pl.format("F{}", "_F").alias("_AGREMIACAO")).unique("NR_PARTIDO", keep="first")


def destino_legenda(legenda: pl.DataFrame, destinacao: pl.DataFrame) -> pl.DataFrame:
    """`legenda` (NR_TURNO, SG_UF, CD_CARGO, NR_VOTAVEL = nº do partido) + _DESTINO_LEGENDA: para onde vão os
    votos de legenda, pela situação da AGREMIAÇÃO (federação = um partido) no cargo e na UF. Gabarito: o
    detalhe munzona oficial de 2022 nas 25 UFs com votos por seção (rodada 48):
      algum candidato da agremiação com destinação "Válido*" → LEGENDA (válida);
      senão algum "Anulado sub judice" → SUBJUDICE; senão (todos anulados) → ANULADOS;
      agremiação sem candidato no cargo → NULOS_TECNICOS."""
    chave = ["NR_TURNO", "SG_UF", "CD_CARGO"]
    agrem = _agremiacoes(destinacao)
    proprio = lambda c: pl.coalesce("_AGREMIACAO", pl.format("P{}", c))  # noqa: E731
    d = pl.col("DESTINACAO_TSE")
    estado = (destinacao.filter(pl.col("CD_CARGO").is_in(list(PROPORCIONAIS)))
              .join(agrem, on="NR_PARTIDO", how="left").with_columns(proprio("NR_PARTIDO").alias("_AGREMIACAO"))
              .group_by(chave + ["_AGREMIACAO"])
              .agg(pl.when(d.str.starts_with("Válido")).then(3).when(d == "Anulado sub judice").then(2)
                   .otherwise(1).max().alias("_NIVEL")))
    return (legenda.join(agrem.rename({"NR_PARTIDO": "NR_VOTAVEL"}), on="NR_VOTAVEL", how="left")
            .with_columns(proprio("NR_VOTAVEL").alias("_AGREMIACAO"))
            .join(estado, on=chave + ["_AGREMIACAO"], how="left")
            .with_columns(pl.col("_NIVEL").replace_strict({3: "LEGENDA", 2: "SUBJUDICE", 1: "ANULADOS"},
                                                          default="NULOS_TECNICOS", return_dtype=pl.String)
                          .alias("_DESTINO_LEGENDA"))
            .drop("_AGREMIACAO", "_NIVEL"))


_CHAVE_ZONA = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO"]
_CATEGORIAS = ("NOMINAIS", "LEGENDA", "BRANCOS", "NULOS_DIGITADOS", "NULOS_TECNICOS", "ANULADOS", "SUBJUDICE",
               "APURACAO_SEPARADA")


def detalhe_de_secoes(votos: pl.LazyFrame, detalhe: pl.LazyFrame, destinacao: pl.DataFrame) -> pl.DataFrame:
    """O `detalhe_votacao_munzona` (as colunas QT_* que `totais` usa) reconstruído das seções, por
    (turno, UF, município, zona, cargo). Sem I/O.

    `votos`: votacao_secao (NR_TURNO, SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO, CD_CARGO, NR_VOTAVEL, QT_VOTOS);
    `detalhe`: detalhe_votacao_secao (aptos, comparecimento, abstenções, hora de entrada na totalização);
    `destinacao`: `destinacao_oficial`. Regras (rodada 48: iguais ao oficial de 2022 em 16 das 25 UFs com votos
    por seção e à noite de 2026 em 24 de 25; o resto depende do DRAP do partido, que não está nos arquivos):
      95 branco · 96 nulo · 97 anulado em apuração separada;
      proporcional, votável < 100 = legenda: destino pela agremiação (`destino_legenda`);
      nominal: "Válido (legenda)" → legenda; outra "Válido*" → válido; "Anulado sub judice" → sub judice;
      outra → anulado;
      número que não está na destinação (candidatura negada antes da eleição) → nulo técnico."""
    chave_cand = ["NR_TURNO", "SG_UF", "CD_CARGO"]
    dest = destinacao.select(chave_cand + ["NUMERO", "DESTINACAO_TSE"])
    pres = dest.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE).drop("SG_UF").unique(
        ["NR_TURNO", "CD_CARGO", "NUMERO"])  # presidente: a destinação é nacional
    v = (votos.group_by(_CHAVE_ZONA + ["NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum()).collect()
         .with_columns(pl.col("NR_TURNO", "CD_CARGO", "NR_VOTAVEL", "CD_MUNICIPIO", "NR_ZONA").cast(pl.Int64)))
    v_uf = v.filter(pl.col("CD_CARGO") != CARGO_PRESIDENTE).join(
        dest.rename({"NUMERO": "NR_VOTAVEL"}), on=chave_cand + ["NR_VOTAVEL"], how="left")
    v_pr = v.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE).join(
        pres.rename({"NUMERO": "NR_VOTAVEL"}), on=["NR_TURNO", "CD_CARGO", "NR_VOTAVEL"], how="left")
    cargos = cargos_com_destinacao(destinacao)
    v = (pl.concat([v_uf, v_pr], how="diagonal_relaxed")
         .join(cargos.filter(pl.col("CD_CARGO") != CARGO_PRESIDENTE), on=chave_cand, how="left")
         .join(cargos.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE).drop("SG_UF").unique(),
               on=["NR_TURNO", "CD_CARGO"], how="left", suffix="_PR")
         .with_columns(pl.coalesce("_TEM_DESTINACAO", "_TEM_DESTINACAO_PR").fill_null(False).alias("_TEM_DESTINACAO")))
    legenda = pl.col("CD_CARGO").is_in(PROPORCIONAIS) & (pl.col("NR_VOTAVEL") < 100) & ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS)
    v = destino_legenda(v, destinacao)
    destino = pl.col("DESTINACAO_TSE")
    cat = (pl.when(pl.col("NR_VOTAVEL") == 95).then(pl.lit("BRANCOS"))
           .when(pl.col("NR_VOTAVEL") == 96).then(pl.lit("NULOS_DIGITADOS"))
           .when(pl.col("NR_VOTAVEL") == 97).then(pl.lit("APURACAO_SEPARADA"))
           # cargo SEM nenhuma linha de destinação (o TSE ainda não publicou — Presidente em 06/10/2026): não
           # dá para saber quem foi anulado; os votos nominais e de legenda contam como válidos (aviso no status)
           .when(~pl.col("_TEM_DESTINACAO") & legenda).then(pl.lit("LEGENDA"))
           .when(~pl.col("_TEM_DESTINACAO")).then(pl.lit("NOMINAIS"))
           .when(legenda).then(pl.col("_DESTINO_LEGENDA"))
           .when(destino.is_null()).then(pl.lit("NULOS_TECNICOS"))
           .when(destino == "Válido (legenda)").then(pl.lit("LEGENDA"))  # nominal convertido em legenda
           .when(destino.str.starts_with("Válido")).then(pl.lit("NOMINAIS"))
           .when(destino == "Anulado sub judice").then(pl.lit("SUBJUDICE"))
           .otherwise(pl.lit("ANULADOS")))
    soma = lambda c: pl.col("QT_VOTOS").filter(pl.col("_C") == c).sum().alias(c)  # noqa: E731
    por_zona = v.with_columns(cat.alias("_C")).group_by(_CHAVE_ZONA).agg(
        pl.col("QT_VOTOS").sum().alias("QT_VOTOS"), *[soma(c) for c in _CATEGORIAS])
    tem = set(detalhe.collect_schema().names())
    # o detalhe por seção só lista as seções PRINCIPAIS; o oficial soma as agregadas (RJ 2022: 34.068 + 2.482 =
    # 36.550). O BU traz a lista das agregadas de cada principal (`bweb.detalhe_por_secao`): com ela, igual ao
    # oficial; sem ela, só as principais (entra só no % de seções totalizadas, 100% aqui)
    agregadas = pl.col("QT_SECOES_AGREGADAS").sum() if "QT_SECOES_AGREGADAS" in tem else pl.lit(0, pl.Int64)
    det = (detalhe.with_columns(pl.col("NR_TURNO", "CD_CARGO", "CD_MUNICIPIO", "NR_ZONA").cast(pl.Int64))
           .group_by(_CHAVE_ZONA).agg(
               pl.col("QT_APTOS").sum(), pl.col("QT_COMPARECIMENTO").sum(), pl.col("QT_ABSTENCOES").sum(),
               (pl.col("NR_SECAO").n_unique().cast(pl.Int64) + agregadas).alias("QT_TOTAL_SECOES"),
               pl.col("DS_CARGO").first().str.to_titlecase(),  # a conversão põe em maiúsculas; oficial: "Governador"
               pl.col("DT_PRIM_TOT_PARCIAL_HOR_TSE").cast(pl.String)
               .str.to_datetime("%d/%m/%Y %H:%M:%S", strict=False).max().alias("_HORA"),
               # o BU traz o código da eleição: reserva quando a destinação do turno ainda não saiu
               (pl.col("CD_ELEICAO").cast(pl.Int64).drop_nulls().first() if "CD_ELEICAO" in tem
                else pl.lit(None, pl.Int64)).alias("_ELEICAO_SECAO"))
           .collect())
    eleicao = destinacao.group_by("NR_TURNO", "CD_CARGO").agg(pl.col("CD_ELEICAO").drop_nulls().first())
    zero = pl.lit(0, pl.Int64)
    return (
        det.join(por_zona, on=_CHAVE_ZONA, how="full", coalesce=True).rechunk()
        .join(eleicao, on=["NR_TURNO", "CD_CARGO"], how="left")
        .with_columns(pl.coalesce("CD_ELEICAO", "_ELEICAO_SECAO").alias("CD_ELEICAO")).drop("_ELEICAO_SECAO")
        .with_columns(*[pl.col(c).fill_null(zero) for c in ("QT_VOTOS", *_CATEGORIAS)])
        .with_columns(
            (pl.col("NOMINAIS") + pl.col("LEGENDA")).alias("QT_TOTAL_VOTOS_VALIDOS"),
            pl.col("NOMINAIS").alias("QT_VOTOS_NOMINAIS_VALIDOS"), pl.col("LEGENDA").alias("QT_TOTAL_VOTOS_LEG_VALIDOS"),
            pl.col("BRANCOS").alias("QT_VOTOS_BRANCOS"), pl.col("NULOS_DIGITADOS").alias("QT_VOTOS_NULOS"),
            pl.col("NULOS_TECNICOS").alias("QT_VOTOS_NULOS_TECNICOS"),
            (pl.col("NULOS_DIGITADOS") + pl.col("NULOS_TECNICOS")).alias("QT_TOTAL_VOTOS_NULOS"),
            (pl.col("ANULADOS") + pl.col("SUBJUDICE")).alias("QT_TOTAL_VOTOS_ANULADOS_E_SUBJUD"),
            pl.col("ANULADOS").alias("QT_TOTAL_VOTOS_ANULADOS"), pl.col("SUBJUDICE").alias("QT_TOTAL_VOTOS_ANUL_SUBJUD"),
            pl.col("APURACAO_SEPARADA").alias("QT_VOTOS_ANULADOS_APU_SEP"),
            # hora: a da última seção a entrar na totalização, na noite. O oficial traz a da ÚLTIMA
            # totalização da zona, que pode ser uma retotalização meses depois (RJ 2022, 1º turno: 01/12/2022)
            pl.col("_HORA").dt.strftime("%d/%m/%Y").alias("DT_ULTIMA_TOTALIZACAO"),
            pl.col("_HORA").dt.strftime("%H:%M:%S").alias("HH_ULTIMA_TOTALIZACAO"))
        .drop("_HORA", "QT_TOTAL_VOTOS_ANULADOS_E_SUBJUD", *_CATEGORIAS)
    )


def cargos_com_destinacao(destinacao: pl.DataFrame) -> pl.DataFrame:
    """(turno, UF, cargo) que têm alguma linha no candidato_munzona — os outros ainda não foram publicados."""
    return destinacao.select("NR_TURNO", "SG_UF", "CD_CARGO").unique().with_columns(
        pl.lit(True).alias("_TEM_DESTINACAO"))


def cargos_sem_destinacao(destinacao: pl.DataFrame | None, uf: str, turno: int, cargos: list[int]) -> list[int]:
    """Cargos (dos `cargos` votados) sem nenhuma linha de destinação na UF (presidente: em qualquer UF)."""
    if destinacao is None:
        return sorted(cargos)
    d = destinacao.filter(pl.col("NR_TURNO") == turno)
    tem = set(d.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE)["CD_CARGO"].to_list()) | set(
        d.filter(pl.col("SG_UF") == uf.upper())["CD_CARGO"].to_list())
    return sorted(set(cargos) - tem)


def load_detalhe_secoes(ano: int, uf: str, cache: Path) -> pl.DataFrame:
    """`detalhe_de_secoes` com os arquivos do cache: votos por seção da UF (cargos estaduais) e do Brasil
    (presidente, todas as UFs e o exterior, para a abrangência "br"), detalhe por seção nacional e destinação."""
    from apuracao import projecao as pj

    votos_uf, votos_br = load_votos(ano, uf, cache)
    colunas = _CHAVE_ZONA + ["NR_VOTAVEL", "QT_VOTOS"]
    votos = pl.concat([votos_uf.filter((pl.col("SG_UF") == uf.upper()) & (pl.col("CD_CARGO") != CARGO_PRESIDENTE))
                       .select(colunas),
                       votos_br.filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE).select(colunas)], how="vertical_relaxed")
    det = pj.detalhe_nacional(ano, cache).filter(
        ((pl.col("SG_UF") == uf.upper()) & pl.col("CD_CARGO").is_in(list(CARGOS_UF)))
        | (pl.col("CD_CARGO") == CARGO_PRESIDENTE))
    return detalhe_de_secoes(votos, det, destinacao_oficial(ano, cache))


# --------------------------------------------------------------------------
# Boletim de Urna (fonte "bweb", rodada 55): os mesmos intermediários da fonte "secao", traduzidos do BU
# --------------------------------------------------------------------------
_DESTINACAO_VAZIA = {"NR_TURNO": pl.Int64, "SG_UF": pl.String, "CD_CARGO": pl.Int64, "NUMERO": pl.Int64,
                     "NR_PARTIDO": pl.Int64, "CD_ELEICAO": pl.Int64, "DESTINACAO_TSE": pl.String,
                     "SITUACAO_TSE": pl.String, "SG_PARTIDO": pl.String, "NR_FEDERACAO": pl.Int64,
                     "COMPOSICAO_FEDERACAO": pl.String}


def _bus(ano: int, turno: int, uf: str, cache: Path, brasil: bool) -> dict[str, Path]:
    """UF → BU conferido no cache: a pedida e, com `brasil`, as 27 + o exterior (Presidente na abrangência
    Brasil). Faltando algum, `TseDataError` (nada de Brasil pela metade)."""
    from apuracao import bweb
    from apuracao.ufs import UFS

    quais = [*UFS, bweb.EXTERIOR] if brasil else [uf.upper()]
    achados = {u: bweb.no_cache(cache, ano, turno, u) for u in quais}
    faltam = sorted(u for u, zp in achados.items() if zp is None)
    if faltam:
        raise v.TseDataError(f"Boletim de Urna de {ano}, {turno}º turno, fora do cache: {', '.join(faltam)}")
    return achados  # type: ignore[return-value]


def load_votos_bweb(ano: int, turno: int, uf: str, cache: Path, brasil: bool = False
                    ) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Os mesmos (votos da UF, votos nacionais) de `load_votos`, dos BUs do turno. Sem `brasil`, os votos
    "nacionais" são só os da UF: quem importa tira a abrangência Brasil (`importar`)."""
    from apuracao import bweb

    bus = _bus(ano, turno, uf, cache, brasil)
    votos = {u: bweb.votos_por_secao(bweb.ler(zp, u)) for u, zp in bus.items()}
    nacional = pl.concat(list(votos.values()), how="vertical_relaxed").filter(pl.col("CD_CARGO") == CARGO_PRESIDENTE)
    return votos[uf.upper()], nacional


def load_detalhe_bweb(ano: int, turno: int, uf: str, cache: Path, brasil: bool = False,
                      destinacao: pl.DataFrame | None = None) -> pl.DataFrame:
    """`detalhe_de_secoes` sobre os BUs do turno (nenhuma regra de classificação nova). Sem a destinação do
    turno (2º turno antes do candidato_munzona), os votos nominais e de legenda contam como válidos, como na
    fonte "secoes" (aviso no status.json)."""
    from apuracao import bweb

    bus = _bus(ano, turno, uf, cache, brasil)
    lidos = {u: bweb.ler(zp, u) for u, zp in bus.items()}
    for u, bu in lidos.items():
        logger.info("Boletim de Urna %s: %s", bus[u].name, bweb.verificar(bu))
    colunas = _CHAVE_ZONA + ["NR_VOTAVEL", "QT_VOTOS"]
    votos = pl.concat([bweb.votos_por_secao(bu).filter(
        (pl.col("CD_CARGO") == CARGO_PRESIDENTE) | ((pl.col("SG_UF") == uf.upper()) & pl.col("CD_CARGO").is_in(list(CARGOS_UF))))
        .select(colunas) for bu in lidos.values()], how="vertical_relaxed")
    det = pl.concat([bweb.detalhe_por_secao(bu) for bu in lidos.values()], how="vertical_relaxed").filter(
        (pl.col("CD_CARGO") == CARGO_PRESIDENTE) | ((pl.col("SG_UF") == uf.upper()) & pl.col("CD_CARGO").is_in(list(CARGOS_UF))))
    if destinacao is None:
        destinacao = _destinacao_ou_nada(ano, cache)
    if destinacao is None:
        destinacao = pl.DataFrame(schema=_DESTINACAO_VAZIA)
    return detalhe_de_secoes(votos, det.lazy(), destinacao)


# --------------------------------------------------------------------------
# votacao_partido_munzona reconstruído (rodada 55): para as cadeiras enquanto o TSE não publica o oficial
# --------------------------------------------------------------------------
QT_PARTIDO_MUNZONA = ["QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_NOM_CONVR_LEG_VALIDOS", "QT_TOTAL_VOTOS_LEG_VALIDOS",
                      "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA_ANUL_SUBJUD", "QT_VOTOS_NOMINAIS_ANUL_SUBJUD",
                      "QT_VOTOS_LEGENDA_ANULADOS", "QT_VOTOS_NOMINAIS_ANULADOS"]
# atributos da agremiação (iguais em todas as zonas): copiados do votacao_candidato_munzona, no formato dele
_ATRIBUTOS_PARTIDO = ["CD_ELEICAO", "DS_CARGO", "TP_AGREMIACAO", "SG_PARTIDO", "NM_PARTIDO", "NR_FEDERACAO",
                      "NM_FEDERACAO", "SG_FEDERACAO", "DS_COMPOSICAO_FEDERACAO", "SQ_COLIGACAO", "NM_COLIGACAO",
                      "DS_COMPOSICAO_COLIGACAO"]
_CHAVE_PARTIDO = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO", "NR_PARTIDO"]
# esquema de saída: o cabeçalho real do votacao_partido_munzona (2022), tipado; sem DT/HH_GERACAO, NM_UE etc.
ESQUEMA_PARTIDO_MUNZONA = {
    "ANO_ELEICAO": pl.Int64, "CD_TIPO_ELEICAO": pl.Int64, "NR_TURNO": pl.Int64, "CD_ELEICAO": pl.Int64,
    "SG_UF": pl.String, "CD_MUNICIPIO": pl.Int64, "NM_MUNICIPIO": pl.String, "NR_ZONA": pl.Int64,
    "CD_CARGO": pl.Int64, "DS_CARGO": pl.String, "TP_AGREMIACAO": pl.String, "NR_PARTIDO": pl.Int64,
    "SG_PARTIDO": pl.String, "NM_PARTIDO": pl.String, "NR_FEDERACAO": pl.Int64, "NM_FEDERACAO": pl.String,
    "SG_FEDERACAO": pl.String, "DS_COMPOSICAO_FEDERACAO": pl.String, "SQ_COLIGACAO": pl.Int64,
    "NM_COLIGACAO": pl.String, "DS_COMPOSICAO_COLIGACAO": pl.String, "ST_VOTO_EM_TRANSITO": pl.String,
    **{c: pl.Int64 for c in QT_PARTIDO_MUNZONA}}


def load_candidatos_zona(ano: int, uf: str, cache: Path) -> pl.DataFrame:
    """As linhas do votacao_candidato_munzona da UF (Presidente: as da UF), tipadas, por município × zona.
    Só do CACHE, como a destinação."""
    if not (cache / f"votacao_candidato_munzona_{ano}.zip").exists():
        raise v.TseDataError(f"votacao_candidato_munzona_{ano}.zip não está no cache")
    colunas = _COLS_MUNZONA + ["NR_ZONA", "NM_MUNICIPIO", "QT_VOTOS_NOMINAIS"] + _COLS_DESTINACAO
    pq = _parquet_com_colunas("votacao_candidato_munzona", ano, cache, colunas,
                              tuple(dict.fromkeys((*_COLS_FEDERACAO, *_ATRIBUTOS_PARTIDO, "ST_VOTO_EM_TRANSITO"))))
    lf = pl.scan_parquet(pq).filter(pl.col("SG_UF") == uf.upper())
    tem = set(lf.collect_schema().names())
    inteiro = lambda c: pl.col(c).cast(pl.String).str.strip_chars().cast(pl.Int64, strict=False)  # noqa: E731
    ints = {"NR_TURNO", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO", "NR_CANDIDATO", "NR_PARTIDO", "CD_ELEICAO",
            "QT_VOTOS_NOMINAIS", "NR_FEDERACAO", "SQ_COLIGACAO"}
    return lf.select([(inteiro(c) if c in ints else pl.col(c).cast(pl.String)).alias(c) if c in tem
                      else pl.lit(None, pl.Int64 if c in ints else pl.String).alias(c)
                      for c in dict.fromkeys(colunas + list(_COLS_FEDERACAO) + _ATRIBUTOS_PARTIDO)]).collect()


def legenda_por_zona(votos: pl.LazyFrame) -> pl.DataFrame:
    """Votos de legenda (votável de 2 dígitos nos proporcionais) somados por zona, dos votos por seção
    (fonte "secao" ou "bweb")."""
    return (votos.filter(pl.col("CD_CARGO").is_in(list(PROPORCIONAIS)) & (pl.col("NR_VOTAVEL") < 100)
                         & ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS))
            .group_by(_CHAVE_ZONA + ["NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum()).collect()
            .with_columns(pl.col("NR_TURNO", "CD_MUNICIPIO", "NR_ZONA", "CD_CARGO", "NR_VOTAVEL", "QT_VOTOS")
                          .cast(pl.Int64)))


def partidos_munzona(candidatos: pl.DataFrame, legenda: pl.DataFrame, destinacao: pl.DataFrame,
                     ano: int) -> pl.DataFrame:
    """O votacao_partido_munzona reconstruído, por município × zona × cargo × partido. Sem I/O.

    `candidatos`: `load_candidatos_zona` (nominais por candidato, com a destinação da totalização);
    `legenda`: `legenda_por_zona`; `destinacao`: `destinacao_oficial`.
      nominais, pela destinação do candidato: "Válido (legenda)" → convertidos em legenda; outra "Válido*" →
        nominais válidos; "Anulado sub judice" → nominais sub judice; outra "Anulado*" → nominais anulados;
      legenda, pela agremiação (`destino_legenda`, a mesma regra dos totais): válida, sub judice, anulada; o
        nulo técnico (agremiação sem candidato no cargo) não é do partido;
      QT_TOTAL_VOTOS_LEG_VALIDOS = legenda válida + nominais convertidos.
    ST_VOTO_EM_TRANSITO fica nulo: a legenda por seção não se separa por voto em trânsito (soma dos dois)."""
    d, q = pl.col("NM_TIPO_DESTINACAO_VOTOS"), pl.col("QT_VOTOS_NOMINAIS")
    valido_legenda = d == "Válido (legenda)"
    nom = candidatos.group_by(_CHAVE_PARTIDO).agg(
        q.filter(d.str.starts_with("Válido") & ~valido_legenda).sum().alias("QT_VOTOS_NOMINAIS_VALIDOS"),
        q.filter(valido_legenda).sum().alias("QT_VOTOS_NOM_CONVR_LEG_VALIDOS"),
        q.filter(d == "Anulado sub judice").sum().alias("QT_VOTOS_NOMINAIS_ANUL_SUBJUD"),
        q.filter(d.str.starts_with("Anulado") & (d != "Anulado sub judice")).sum().alias("QT_VOTOS_NOMINAIS_ANULADOS"))
    destino = pl.col("_DESTINO_LEGENDA")
    leg = (destino_legenda(legenda, destinacao).filter(destino != "NULOS_TECNICOS")
           .rename({"NR_VOTAVEL": "NR_PARTIDO"}).group_by(_CHAVE_PARTIDO).agg(
               pl.col("QT_VOTOS").filter(destino == "LEGENDA").sum().alias("QT_VOTOS_LEGENDA_VALIDOS"),
               pl.col("QT_VOTOS").filter(destino == "SUBJUDICE").sum().alias("QT_VOTOS_LEGENDA_ANUL_SUBJUD"),
               pl.col("QT_VOTOS").filter(destino == "ANULADOS").sum().alias("QT_VOTOS_LEGENDA_ANULADOS")))
    atributos = (candidatos.sort("NR_CANDIDATO").group_by("NR_TURNO", "SG_UF", "CD_CARGO", "NR_PARTIDO")
                 .agg(pl.col(_ATRIBUTOS_PARTIDO).drop_nulls().first()))
    municipios = candidatos.group_by("CD_MUNICIPIO").agg(pl.col("NM_MUNICIPIO").drop_nulls().first())
    return (nom.join(leg, on=_CHAVE_PARTIDO, how="full", coalesce=True).rechunk()
            .with_columns(pl.col(c).fill_null(0) for c in QT_PARTIDO_MUNZONA if c != "QT_TOTAL_VOTOS_LEG_VALIDOS")
            .with_columns((pl.col("QT_VOTOS_LEGENDA_VALIDOS") + pl.col("QT_VOTOS_NOM_CONVR_LEG_VALIDOS"))
                          .alias("QT_TOTAL_VOTOS_LEG_VALIDOS"))
            .join(atributos, on=["NR_TURNO", "SG_UF", "CD_CARGO", "NR_PARTIDO"], how="left")
            .join(municipios, on="CD_MUNICIPIO", how="left")
            .with_columns(pl.lit(ano).alias("ANO_ELEICAO"), pl.lit(int(v.ORDINARY_ELECTION)).alias("CD_TIPO_ELEICAO"),
                          pl.lit(None, pl.String).alias("ST_VOTO_EM_TRANSITO"))
            .select([pl.col(c).cast(t) for c, t in ESQUEMA_PARTIDO_MUNZONA.items()])
            .sort(_CHAVE_PARTIDO))


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
    """Uma linha por (UF do cadastro, cargo, número): prefere candidatura APTA com situação preenchida.
    FEDERACAO no formato "PT/PC do B/PV" em todos os anos (o cadastro de 2026 traz "13-PT/65-PC do B/43-PV";
    o tempo real e 2022, sem os números — `partidos.normalizar_federacao`)."""
    # "13-PT/65-PC do B/43-PV" → "PT/PC do B/PV" (mesma regra de partidos.normalizar_federacao, vetorizada)
    federacao = (pl.coalesce(pl.col("SG_FEDERACAO"), pl.col("NM_FEDERACAO"))
                 .str.replace_all(r"(^|/)\s*\d+\s*-\s*", "$1"))
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
            federacao.alias("FEDERACAO"),
            # federação sozinha vem com NM_COLIGACAO = "FEDERAÇÃO" (texto genérico: as 5 federações de 2026
            # ficavam com o mesmo nome — rodada 41): a agremiação é a própria federação
            pl.when(pl.col("NM_COLIGACAO") == "PARTIDO ISOLADO").then(pl.col("SG_PARTIDO"))
            .when((pl.col("NM_COLIGACAO") == "FEDERAÇÃO") & federacao.is_not_null()).then(federacao)
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


def _com_destinacao(c: pl.DataFrame, destinacao: pl.DataFrame | None, uf: str, turno: int) -> pl.DataFrame:
    """DESTINACAO e SITUACAO da totalização (votacao_candidato_munzona) no lugar das do consulta_cand, que o
    TSE regera depois. Número votado que não está lá: candidatura negada antes da eleição → nulo técnico."""
    if destinacao is None or destinacao.is_empty():
        return c
    d = destinacao.filter((pl.col("NR_TURNO") == turno)
                          & ((pl.col("SG_UF") == uf.upper()) | (pl.col("CD_CARGO") == CARGO_PRESIDENTE)))
    d = d.unique(["CD_CARGO", "NUMERO"], keep="first").select(
        pl.col("CD_CARGO").alias("CARGO"), "NUMERO", "DESTINACAO_TSE", "SITUACAO_TSE")
    tem_cargo = set(d["CARGO"].to_list())  # cargo sem nenhuma linha (arquivo incompleto): fica o cadastro
    no_arquivo = pl.col("CARGO").is_in(list(tem_cargo))
    return (c.join(d, on=["CARGO", "NUMERO"], how="left")
            .with_columns(
                pl.when(pl.col("DESTINACAO_TSE").is_not_null()).then(pl.col("DESTINACAO_TSE"))
                .when(no_arquivo).then(pl.lit("Nulo técnico")).otherwise(pl.col("DESTINACAO")).alias("DESTINACAO"),
                pl.when(pl.col("SITUACAO_TSE").is_not_null()).then(_situacao(pl.col("SITUACAO_TSE")))
                .when(no_arquivo).then(pl.lit("Não eleito")).otherwise(pl.col("SITUACAO")).alias("SITUACAO"))
            .drop("DESTINACAO_TSE", "SITUACAO_TSE"))


def candidatos_e_partidos(votos_uf: pl.LazyFrame, votos_br: pl.LazyFrame, cand: pl.DataFrame, tot: pl.DataFrame,
                          uf: str, turno: int, destinacao: pl.DataFrame | None = None
                          ) -> tuple[pl.DataFrame, pl.DataFrame]:
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
        .pipe(_com_destinacao, destinacao, uf, turno)
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
    # só os nominais VÁLIDOS contam para o partido (as cadeiras do histórico usam esta tabela quando o
    # votacao_partido_munzona falta): voto em candidato anulado/sub judice/nulo técnico não é do partido
    # (Dep. Estadual RJ 2026: 338 mil votos sub judice mudavam 3 eleitos). Sem a destinação oficial
    # (DESTINACAO vinda do consulta_cand), fica como antes: todos.
    valido = pl.col("DESTINACAO").str.starts_with("Válido") | (destinacao is None)
    nomin = c.filter(proporcional).group_by(chave + ["NR_PARTIDO"]).agg(
        pl.col("VOTOS").filter(valido).sum().alias("VOTOS_NOMINAIS"),
        pl.col("SITUACAO").str.starts_with("Eleito").sum().cast(pl.Int64).alias("VAGAS_AGREMIACAO"))
    leg = (votos.filter(proporcional & (pl.col("NR_VOTAVEL") < 100) & ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS))
           .select(chave + [pl.col("NR_VOTAVEL").alias("NR_PARTIDO"), pl.col("QT_VOTOS").alias("VOTOS_LEGENDA")]))
    if destinacao is not None and not destinacao.is_empty():  # só a legenda VÁLIDA é do partido (`destino_legenda`)
        leg = (destino_legenda(leg.with_columns(pl.lit(turno, pl.Int64).alias("NR_TURNO"), pl.lit(uf.upper()).alias("SG_UF"),
                                                pl.col("CARGO").alias("CD_CARGO"), pl.col("NR_PARTIDO").alias("NR_VOTAVEL")),
                               destinacao)
               .with_columns(pl.when(pl.col("_DESTINO_LEGENDA") == "LEGENDA").then(pl.col("VOTOS_LEGENDA"))
                             .otherwise(0).alias("VOTOS_LEGENDA"))
               .select(chave + ["NR_PARTIDO", "VOTOS_LEGENDA"]))
    # agremiação POR CARGO: o mesmo partido pode estar coligado para governador e isolado (ou em federação) para
    # deputado; sem o cargo na chave, a escolha dependia da ordem das linhas (rodada 40)
    siglas = (cad.select("CARGO", "NR_PARTIDO", "PARTIDO", "FEDERACAO", "AGREMIACAO")
              .sort("CARGO", "NR_PARTIDO", "AGREMIACAO", nulls_last=True)
              .unique(subset=["CARGO", "NR_PARTIDO"], keep="first", maintain_order=True))
    partidos = (
        nomin.join(leg, on=chave + ["NR_PARTIDO"], how="full", coalesce=True, nulls_equal=True)
        .join(siglas, on=["CARGO", "NR_PARTIDO"], how="left")
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


def conferir_totais(antes: pl.DataFrame, depois: pl.DataFrame) -> pl.DataFrame:
    """Diferenças (depois − antes) por cargo × abrangência × município nas colunas somadas dos totais — ex.:
    os reconstruídos das seções × os oficiais, quando o detalhe munzona chega. Só as linhas com diferença."""
    chave = ["CARGO", "ABRANGENCIA", "UF", "CD_MUNICIPIO"]
    cols = [c for c in _SOMAS if c in antes.columns and c in depois.columns]
    j = antes.select(chave + cols).join(depois.select(chave + cols), on=chave, how="full", coalesce=True,
                                        nulls_equal=True, suffix="_OFICIAL").rechunk()
    difs = [(pl.col(f"{c}_OFICIAL").fill_null(0) - pl.col(c).fill_null(0)).alias(f"DIF_{c}") for c in cols]
    return (j.with_columns(difs).filter(pl.any_horizontal([pl.col(f"DIF_{c}") != 0 for c in cols]))
            .sort(chave, nulls_last=True))


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------
TOTAIS = ("munzona", "secoes", "bweb")
DESCRICAO_TOTAIS = {"munzona": "oficiais (detalhe_votacao_munzona)",
                    "secoes": "reconstruídos das seções (provisório, até o TSE publicar o detalhe_votacao_munzona)",
                    "bweb": "reconstruídos do Boletim de Urna (provisório, até o TSE publicar os microdados)"}
DESCRICAO_PARTIDOS = {"munzona": "oficiais (votacao_partido_munzona)",
                      "secoes": "reconstruídos: candidato_munzona + legenda das seções (provisório)",
                      "bweb": "reconstruídos: candidato_munzona + legenda do Boletim de Urna (provisório)"}
_PROVISORIO = {"munzona": "", "secoes": " · totais provisórios", "bweb": " · totais provisórios (BU)"}
PARTIDOS_MUNZONA = "partidos_munzona.parquet"  # em <destino>/ultimo/: o reconstruído, lido pelas cadeiras


def _destinacao_ou_nada(ano: int, cache: Path) -> pl.DataFrame | None:
    try:
        return destinacao_oficial(ano, cache)
    except (v.TseDataError, requests.RequestException) as exc:  # ex.: candidato_munzona do ano ainda não saiu
        logger.warning("sem a destinação oficial dos votos de %s (fica a do consulta_cand): %s", ano, exc)
        return None


def partido_oficial_publicado(ano: int, uf: str, cache: Path) -> bool:
    """O votacao_partido_munzona oficial do ano está no cache com linhas da UF (só cabeçalho não conta)."""
    from apuracao import microdados as md

    zp = cache / f"votacao_partido_munzona_{ano}.zip"
    try:
        return zp.exists() and md.tem_dados(zp, f"_{uf.upper()}.csv")
    except (OSError, ValueError):
        return False


def _partidos_reconstruidos(ano: int, uf: str, turno: int, cache: Path, votos_uf: pl.LazyFrame,
                            destinacao: pl.DataFrame | None) -> pl.DataFrame | None:
    """`partidos_munzona` do turno, ou None se faltar o candidato_munzona/destinação ou o turno não tiver
    cargo proporcional (2º turno)."""
    if destinacao is None:
        return None
    try:
        cand = load_candidatos_zona(ano, uf, cache).filter(pl.col("NR_TURNO") == turno)
    except (v.TseDataError, requests.RequestException) as exc:
        logger.warning("votos por partido não reconstruídos (%s): %s", ano, exc)
        return None
    if cand.filter(pl.col("CD_CARGO").is_in(list(PROPORCIONAIS))).is_empty():
        return None
    legenda = legenda_por_zona(votos_uf.filter(pl.col("NR_TURNO") == turno))
    return partidos_munzona(cand, legenda, destinacao, ano)


def importar(ano: int, uf: str, turno: int, cache: Path, destino: Path, fonte: str | None = None,
             totais_de: str = "munzona", detalhe: pl.DataFrame | None = None, brasil: bool = False
             ) -> dict[str, int]:
    """Grava destino/ultimo/*.parquet + status.json no formato lido pelo site. `fonte` dos votos:
    "secao" (votacao_secao da UF + BR), "munzona" (arquivos nacionais por município e zona) ou "bweb"
    (Boletim de Urna do turno, rodada 55); padrão: `fonte_padrao`. `totais_de`: "munzona" (oficiais),
    "secoes" (reconstruídos das seções — exige a fonte "secao") ou "bweb" (reconstruídos do BU — exige a fonte
    "bweb"); os dois últimos são marcados como provisórios no status.json. `detalhe`: o de `load_detalhe`/
    `load_detalhe_secoes` já carregado (traz os dois turnos; evita refazer a reconstrução, ~1 min no RJ).
    `brasil` (só "bweb"): usa os BUs das 27 UFs + exterior para o Presidente no Brasil; sem ele, a abrangência
    Brasil sai (com aviso), porque o BU da UF não dá o total do país.

    Votos por partido (as cadeiras): os oficiais (votacao_partido_munzona) se publicados; senão reconstruídos
    (`partidos_munzona`, gravado em ultimo/partidos_munzona.parquet) com a fonte "secao" ou "bweb"; o
    status.json diz qual (`partidos_de`)."""
    if totais_de not in TOTAIS:
        raise ValueError(f"totais desconhecidos: {totais_de} (use {', '.join(TOTAIS)})")
    fonte = fonte or {"secoes": "secao", "bweb": "bweb"}.get(totais_de) or fonte_padrao(ano, uf, cache)
    if fonte not in FONTES:
        raise ValueError(f"fonte desconhecida: {fonte} (use {', '.join(FONTES)})")
    if totais_de == "secoes" and fonte != "secao":
        raise ValueError("totais reconstruídos das seções exigem a fonte de votos \"secao\"")
    if (totais_de == "bweb") != (fonte == "bweb"):
        raise ValueError("o Boletim de Urna é fonte e totais ao mesmo tempo (fonte \"bweb\" com totais \"bweb\")")
    cand = load_candidatos(ano, cache)
    destinacao = _destinacao_ou_nada(ano, cache)
    if detalhe is not None:
        det = detalhe
    elif totais_de == "munzona":
        det = load_detalhe(ano, cache)
    elif totais_de == "secoes":
        det = load_detalhe_secoes(ano, uf, cache)
    else:
        det = load_detalhe_bweb(ano, turno, uf, cache, brasil, destinacao)
    tot = totais(det, uf, turno)
    if tot.is_empty():
        raise v.TseDataError(f"sem totais para {uf} {ano}, {turno}º turno")
    if fonte == "bweb":
        votos_uf, votos_br = load_votos_bweb(ano, turno, uf, cache, brasil)
    else:
        votos_uf, votos_br = (load_votos if fonte == "secao" else load_votos_munzona)(ano, uf, cache)
    candidatos, partidos = candidatos_e_partidos(votos_uf, votos_br, cand, tot, uf, turno, destinacao)
    sem_destinacao = cargos_sem_destinacao(destinacao, uf, turno, tot["CARGO"].unique().to_list())
    tot = vagas(tot, candidatos)
    sem_brasil = fonte == "bweb" and not brasil
    if sem_brasil:  # o "Brasil" seria só a UF
        tot, candidatos, partidos = (df.filter(pl.col("ABRANGENCIA") != "br") for df in (tot, candidatos, partidos))
    municipios = municipios_tse_ibge(uf, cache)

    if partido_oficial_publicado(ano, uf, cache):
        partidos_de, partidos_mz = "munzona", None
    else:
        partidos_mz = (_partidos_reconstruidos(ano, uf, turno, cache, votos_uf, destinacao)
                       if fonte in ("secao", "bweb") else None)
        partidos_de = None if partidos_mz is None else ("secoes" if fonte == "secao" else "bweb")

    ultimo = destino / "ultimo"
    ultimo.mkdir(parents=True, exist_ok=True)
    tabelas = [("totais", tot), ("candidatos", candidatos), ("partidos", partidos), ("municipios", municipios),
               ("acompanhamento", pl.DataFrame(schema=m.ACOMPANHAMENTO_SCHEMA))]
    if partidos_mz is not None:
        tabelas.append((PARTIDOS_MUNZONA.removesuffix(".parquet"), partidos_mz))
    else:
        (ultimo / PARTIDOS_MUNZONA).unlink(missing_ok=True)  # de uma importação provisória anterior
    for nome, df in tabelas:
        tmp = ultimo / f"{nome}.parquet.tmp"
        df.write_parquet(tmp)
        tmp.replace(ultimo / f"{nome}.parquet")
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    provisorio = totais_de != "munzona"
    avisos = ([f"cargos {', '.join(map(str, sem_destinacao))}: o TSE ainda não publicou a destinação dos votos "
               f"(votacao_candidato_munzona_{ano}); "
               + ("votos nominais contados como válidos e " if provisorio else "")
               + "situação/destinação dos candidatos vêm do consulta_cand"] if sem_destinacao else [])
    if sem_brasil:
        avisos.append("Presidente sem a abrangência Brasil: só o Boletim de Urna da UF no cache "
                      "(os 27 + exterior com --bweb-brasil)")
    if fonte == "bweb":
        from apuracao import bweb
        bus = [f"{zp.stem} (Boletim de Urna, SHA-512 conferido)" for zp in
               (bweb.no_cache(cache, ano, turno, u) for u in ([uf.upper()] if not brasil else _bus(ano, turno, uf, cache, True)))
               if zp is not None]
        fontes_totais = [*bus, f"votacao_candidato_munzona_{ano} (destinação)"]
        fontes_votos: list[str] = []
    else:
        fontes_totais = ([f"detalhe_votacao_munzona_{ano}"] if not provisorio
                         else [f"detalhe_votacao_secao_{ano}", f"votacao_candidato_munzona_{ano} (destinação)"])
        fontes_votos = ([f"votacao_secao_{ano}_{uf.upper()}", f"votacao_secao_{ano}_BR"] if fonte == "secao"
                        else [f"votacao_candidato_munzona_{ano}", f"votacao_partido_munzona_{ano}"])
    status = {
        "ambiente": f"{ano} · {turno}º turno (microdados{_PROVISORIO[totais_de]})",
        "ano": ano, "uf": uf.upper(), "turno": turno,
        "ciclo_tse": f"microdados {ano}", "ultimo_ciclo_inicio": agora, "ultimo_ciclo_fim": agora, "erro": None,
        "totais": DESCRICAO_TOTAIS[totais_de], "totais_de": totais_de,
        "partidos": DESCRICAO_PARTIDOS.get(partidos_de or "", "da divulgação importada (sem microdados por partido)"),
        "partidos_de": partidos_de,
        "avisos": avisos,
        "fontes": [*fontes_totais, *fontes_votos, f"consulta_cand_{ano}", "EA12 (divulgação TSE 2026) para o código IBGE"],
    }
    (destino / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    return {"totais": tot.height, "candidatos": candidatos.height, "partidos": partidos.height,
            "municipios": municipios.height}
