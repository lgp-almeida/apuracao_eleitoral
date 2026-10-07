"""
Votação por LOCAL DE VOTAÇÃO e por SEÇÃO ELEITORAL — dados abertos do TSE.

Fontes (Portal de Dados Abertos do TSE -> arquivos em cdn.tse.jus.br):

  1) Votação por seção eleitoral  (dataset "resultados-<ano>")
       votacao_secao/votacao_secao_<ano>_<UF>.zip
       -> uma linha por (turno, zona, seção, cargo, votável) com QT_VOTOS e,
          desde 2020, as colunas NR_LOCAL_VOTACAO, NM_LOCAL_VOTACAO e
          DS_LOCAL_VOTACAO_ENDERECO. É o único arquivo que precisamos para a
          totalização. Nos arquivos por UF estão Governador, Senador, Dep.
          Federal e Dep. Estadual; o cargo de Presidente só está no _BR.zip.

  2) Eleitorado por local de votação  (dataset "eleitorado-<ano>", OPCIONAL)
       eleitorado_locais_votacao/eleitorado_local_votacao_<ano>.zip
       -> uma linha por (turno, zona, seção) com eleitorado apto, bairro, CEP,
          latitude/longitude e, quando existir, a indicação de agregação.

Subcomandos:

  locais     Lista/busca locais de votação de um município (zona, nº, nome).
  secoes     Para um candidato, totaliza os votos SEÇÃO A SEÇÃO dentro de um
             local de votação (+ linha de total do local).
  por-local  Para um candidato, totaliza os votos de TODOS os locais de um
             município (ou da UF), com coordenadas quando disponíveis.

Exemplos:

  python votos_por_local_votacao.py locais --uf RJ --municipio "Rio de Janeiro" \
      --busca "pedro ii"

  python votos_por_local_votacao.py secoes --uf RJ --cargo "deputado estadual" \
      --candidato 13713 --zona 4 --local 1015

  python votos_por_local_votacao.py por-local --uf RJ --cargo "deputado estadual" \
      --candidato 13713 --municipio "Niterói" --com-eleitorado

Detalhes de modelagem que importam:
  * NR_LOCAL_VOTACAO só é único DENTRO da zona -> chave = (NR_ZONA, NR_LOCAL_VOTACAO).
  * O arquivo de votação é esparso: seção em que o candidato teve 0 voto não
    tem linha para ele. As seções do local vêm das linhas de TODOS os votáveis.
  * Seções agregadas não aparecem no arquivo de votação: os votos delas estão
    na seção principal. Use --com-eleitorado para ver quem foi agregada a quem.
  * Voto em trânsito: locais "(VT)" têm votos mas eleitorado 0.

Cache: os ZIP baixados e a conversão para Parquet ficam em --cache-dir. A
primeira execução por UF é lenta (download + conversão); as seguintes são
imediatas, para qualquer candidato/local.

Requisitos:
    pip install polars requests

Acesso à internet necessário: cdn.tse.jus.br (rode localmente).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import shutil
import sys
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import requests

logger = logging.getLogger("votos_local")

# --------------------------------------------------------------------------
# Constantes do domínio TSE
# --------------------------------------------------------------------------
CDN_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
HTTP_HEADERS = {"User-Agent": "estudo-eleitoral-python/1.0 (votos-por-local)"}

VOTO_BRANCO, VOTO_NULO, VOTO_ANULADO_SEPARADO = 95, 96, 97

PROPORTIONAL_OFFICES = {"DEPUTADO FEDERAL", "DEPUTADO ESTADUAL", "DEPUTADO DISTRITAL", "VEREADOR"}
NATIONAL_FILE_OFFICES = {"PRESIDENTE"}  # só no votacao_secao_<ano>_BR.zip
NATIONAL = "BR"  # uf_filter que mantém todas as UFs na conversão para Parquet

# Marcadores de nulo usados nos CSV do TSE
TSE_NULL_MARKERS = ["#NULO#", "#NULO", "#NE#", "#NE", ""]

SECTION_VOTES_REQUIRED = [
    "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
    "DS_CARGO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO",
]
SECTION_VOTES_OPTIONAL = ["CD_CARGO", "SQ_CANDIDATO", "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO"]

# detalhe_votacao_secao: aptos, comparecimento e abstenção por seção e cargo (o votacao_secao não tem)
SECTION_DETAILS_REQUIRED = [
    "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "NR_LOCAL_VOTACAO",
    "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
]
SECTION_DETAILS_OPTIONAL = ["DS_CARGO", "DT_PRIM_TOT_PARCIAL_HOR_TSE"]  # hora em que a seção entrou na totalização

# Os arquivos de um ano também trazem eleições suplementares posteriores (ex.: votacao_secao_2024_RJ
# inclui a suplementar de Três Rios de 05/10/2025 como "turno 1", nas mesmas seções): só a ordinária fica.
ORDINARY_ELECTION = "2"  # CD_TIPO_ELEICAO: 1 = suplementar/extraordinária, 2 = ordinária

ELECTORATE_WANTED = [
    "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
    "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO", "NM_BAIRRO", "NR_CEP",
    "NR_LATITUDE", "NR_LONGITUDE", "QT_ELEITOR_SECAO", "NR_SECAO_PRINCIPAL",
    # layout 2026 (ausentes em anos anteriores são ignoradas na conversão)
    "CD_TIPO_SECAO_AGREGADA", "DS_TIPO_SECAO_AGREGADA", "DS_TIPO_LOCAL", "DS_SITU_LOCAL_VOTACAO",
    "QT_ELEITOR_ELEICAO_FEDERAL", "QT_ELEITOR_ELEICAO_ESTADUAL", "QT_ELEITOR_ELEICAO_MUNICIPAL",
    "NR_LOCAL_VOTACAO_ORIGINAL", "NM_LOCAL_VOTACAO_ORIGINAL", "DS_ENDERECO_LOCVT_ORIGINAL",
]

INT_COLUMNS = {
    "NR_TURNO", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "NR_VOTAVEL",
    "QT_VOTOS", "NR_LOCAL_VOTACAO", "SQ_CANDIDATO", "QT_ELEITOR_SECAO", "NR_SECAO_PRINCIPAL",
    "CD_TIPO_SECAO_AGREGADA", "QT_ELEITOR_ELEICAO_FEDERAL", "QT_ELEITOR_ELEICAO_ESTADUAL",
    "QT_ELEITOR_ELEICAO_MUNICIPAL", "NR_LOCAL_VOTACAO_ORIGINAL", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
    # perfil_eleitor_secao (a contagem se chama QT_ELEITORES a partir de 2026)
    "CD_GENERO", "CD_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE", "QT_ELEITORES_PERFIL", "QT_ELEITORES",
}
FLOAT_COLUMNS = {"NR_LATITUDE", "NR_LONGITUDE"}

LOCAL_KEY = ["CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO"]


class TseDataError(RuntimeError):
    """Erro de conteúdo/estrutura nos arquivos do TSE."""


# --------------------------------------------------------------------------
# Utilitários puros
# --------------------------------------------------------------------------
def normalize_text(value: str | None) -> str:
    """Maiúsculas, sem acento e com espaços colapsados (para buscas)."""
    if value is None:
        return ""
    txt = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(txt.upper().split())


@dataclass(frozen=True)
class DatasetSpec:
    """Um arquivo do TSE: URL, membro CSV desejado e filtro de UF."""

    name: str
    url: str
    uf_filter: str  # UF a manter na conversão para Parquet
    member: str | None = None  # sufixo do CSV preferido no ZIP (ex.: "_BRASIL.csv"), antes do da UF

    @property
    def zip_name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def section_votes_spec(year: int, uf: str, office: str) -> DatasetSpec:
    file_uf = "BR" if normalize_text(office) in NATIONAL_FILE_OFFICES else uf
    url = f"{CDN_BASE}/votacao_secao/votacao_secao_{year}_{file_uf}.zip"
    return DatasetSpec(name=f"votacao_secao_{year}_{file_uf}", url=url, uf_filter=uf)


def section_details_spec(year: int, uf: str) -> DatasetSpec:
    # o CSV _BRASIL tem todos os cargos (inclusive presidente e o 2º turno dele), o da UF não
    url = f"{CDN_BASE}/detalhe_votacao_secao/detalhe_votacao_secao_{year}.zip"
    return DatasetSpec(name=f"detalhe_votacao_secao_{year}", url=url, uf_filter=uf, member="_BRASIL.csv")


def electorate_spec(year: int, uf: str) -> DatasetSpec:
    url = f"{CDN_BASE}/eleitorado_locais_votacao/eleitorado_local_votacao_{year}.zip"
    return DatasetSpec(name=f"eleitorado_local_votacao_{year}", url=url, uf_filter=uf)


# --------------------------------------------------------------------------
# I/O: download com cache, SHA-512 opcional e registro de proveniência
# --------------------------------------------------------------------------
def download(spec: DatasetSpec, cache_dir: Path, verify_sha512: bool = False) -> Path:
    """Baixa o ZIP em streaming (sem carregar em memória). Idempotente."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / spec.zip_name
    if target.exists():
        logger.info("cache: %s", target)
        return target

    logger.info("baixando %s", spec.url)
    tmp = target.with_suffix(".zip.part")
    with requests.get(spec.url, headers=HTTP_HEADERS, stream=True, timeout=(30, 600)) as resp:
        if resp.status_code == 404:
            dica = (" Para eleição recente, os microdados podem ainda não ter sido publicados "
                    "(o TSE publica alguns dias após o pleito).") if spec.url.startswith(CDN_BASE) else ""
            raise TseDataError(f"404 em {spec.url}.{dica}")  # o IBGE (ibge.py) também baixa por aqui
        resp.raise_for_status()
        sha = hashlib.sha512()
        size = 0
        with tmp.open("wb") as fh:
            for block in resp.iter_content(chunk_size=4 * 1024 * 1024):
                fh.write(block)
                sha.update(block)
                size += len(block)
        last_modified = resp.headers.get("Last-Modified")

    if verify_sha512:
        _verify_sha512(spec.url, sha.hexdigest())
    tmp.replace(target)

    provenance = {
        "url": spec.url,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "last_modified": last_modified,
        "bytes": size,
        "sha512": sha.hexdigest(),
    }
    target.with_suffix(".proveniencia.json").write_text(json.dumps(provenance, indent=2))
    logger.info("  -> %.1f MB", size / 1e6)
    return target


def _verify_sha512(url: str, digest: str) -> None:
    resp = requests.get(url + ".sha512", headers=HTTP_HEADERS, timeout=60)
    if resp.status_code != 200:
        logger.warning("sem .sha512 publicado para %s (HTTP %s)", url, resp.status_code)
        return
    expected = resp.text.split()[0].strip().lower()
    if expected != digest:
        raise TseDataError(f"SHA-512 não confere para {url}")
    logger.info("  SHA-512 ok")


# --------------------------------------------------------------------------
# I/O: ZIP (latin-1) -> Parquet (tipado, filtrado por UF)
# --------------------------------------------------------------------------
def pick_csv_member(zf: zipfile.ZipFile, uf: str, preferred: str | None = None) -> str:
    """Escolhe o CSV certo: alguns ZIP do TSE trazem um CSV por UF + _BRASIL."""
    csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csvs:
        raise TseDataError("ZIP sem CSV")
    for suffix in ((preferred,) if preferred else ()) + (f"_{uf}.csv", "_BRASIL.csv", "_BR.csv"):
        match = [n for n in csvs if n.upper().endswith(suffix.upper())]
        if match:
            return match[0]
    if len(csvs) == 1:
        return csvs[0]
    raise TseDataError(f"Não sei qual CSV usar entre: {csvs}")


def read_header(zf: zipfile.ZipFile, member: str) -> list[str]:
    with zf.open(member) as raw:
        first = io.TextIOWrapper(raw, encoding="latin-1").readline()
    return [c.strip().strip('"') for c in first.rstrip("\r\n").split(";")]


def zip_to_parquet(
    zip_path: Path,
    spec: DatasetSpec,
    wanted: list[str],
    required: list[str],
    cache_dir: Path,
    tipo_ordinario: str | None = ORDINARY_ELECTION,
) -> Path:
    """Converte uma vez o CSV do TSE para Parquet (UTF-8, tipado, só a UF).

    O Polars só lê UTF-8; por isso transcodificamos latin-1 -> UTF-8 em blocos
    (sem laço por linha), depois fazemos scan lazy + sink em streaming.
    `tipo_ordinario`: o CD_TIPO_ELEICAO mantido; None = não filtrar (o Boletim de Urna usa outra tabela de
    códigos — 0 = "Eleição Ordinária" — e filtra pelo nome em `apuracao.bweb`).
    """
    out = cache_dir / f"{spec.name}__{spec.uf_filter}.parquet"
    if out.exists():
        return out

    with zipfile.ZipFile(zip_path) as zf:
        member = pick_csv_member(zf, spec.uf_filter, spec.member)
        header = read_header(zf, member)
        missing = [c for c in required if c not in header]
        if missing:
            raise TseDataError(f"{member}: colunas obrigatórias ausentes {missing}")
        cols = [c for c in wanted if c in header]
        logger.info("convertendo %s -> %s", member, out.name)

        tmp_csv = cache_dir / f"{spec.name}.utf8.csv"
        with zf.open(member) as raw, tmp_csv.open("w", encoding="utf-8", newline="") as dst:
            src = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)

    try:
        lf = pl.scan_csv(
            tmp_csv, separator=";", quote_char='"', infer_schema=False,
            null_values=TSE_NULL_MARKERS, low_memory=True,
        )
        if "CD_TIPO_ELEICAO" in header and tipo_ordinario is not None:  # suplementares posteriores vêm no mesmo arquivo
            lf = lf.filter(pl.col("CD_TIPO_ELEICAO").str.strip_chars() == tipo_ordinario)
        lf = lf.select(cols)
        if "SG_UF" in cols and spec.uf_filter != NATIONAL:  # NATIONAL = arquivo inteiro (todas as UFs)
            lf = lf.filter(pl.col("SG_UF") == spec.uf_filter)
        lf = lf.with_columns(_typed_expressions(cols))
        tmp_parquet = out.with_suffix(".parquet.tmp")
        lf.sink_parquet(tmp_parquet)
        tmp_parquet.replace(out)  # escrita atômica
    finally:
        tmp_csv.unlink(missing_ok=True)

    n = pl.scan_parquet(out).select(pl.len()).collect().item()
    logger.info("  -> %s linhas para UF=%s", f"{n:,}", spec.uf_filter)
    if n == 0:
        out.unlink()
        raise TseDataError(f"Nenhuma linha para UF={spec.uf_filter} em {member}")
    return out


def _typed_expressions(cols: list[str]) -> list[pl.Expr]:
    exprs: list[pl.Expr] = []
    for c in cols:
        if c in INT_COLUMNS:
            v = pl.col(c).str.strip_chars().cast(pl.Int64, strict=False)
            # TSE usa -1/-3 como "não se aplica"/"não informado" em campos numéricos
            exprs.append(pl.when(v < 0).then(None).otherwise(v).alias(c))
        elif c in FLOAT_COLUMNS:
            v = pl.col(c).str.strip_chars().str.replace(",", ".").cast(pl.Float64, strict=False)
            exprs.append(pl.when(v == -1).then(None).otherwise(v).alias(c))
        elif c == "DS_CARGO":
            exprs.append(pl.col(c).str.to_uppercase().str.strip_chars().alias(c))
    return exprs


def load_section_votes(year: int, uf: str, office: str, cache_dir: Path, sha: bool) -> pl.LazyFrame:
    spec = section_votes_spec(year, uf, office)
    zp = download(spec, cache_dir, sha)
    pq = zip_to_parquet(
        zp, spec, SECTION_VOTES_REQUIRED + SECTION_VOTES_OPTIONAL, SECTION_VOTES_REQUIRED, cache_dir
    )
    return pl.scan_parquet(pq)


def load_section_details(year: int, uf: str, cache_dir: Path, sha: bool = False) -> pl.LazyFrame:
    """Aptos, comparecimento e abstenção por seção e cargo (detalhe_votacao_secao), só a UF."""
    spec = section_details_spec(year, uf)
    zp = download(spec, cache_dir, sha)
    pq = zip_to_parquet(
        zp, spec, SECTION_DETAILS_REQUIRED + SECTION_DETAILS_OPTIONAL, SECTION_DETAILS_REQUIRED, cache_dir
    )
    return pl.scan_parquet(pq)


def load_electorate(year: int, uf: str, cache_dir: Path, sha: bool) -> pl.LazyFrame:
    spec = electorate_spec(year, uf)
    zp = download(spec, cache_dir, sha)
    pq = zip_to_parquet(
        zp, spec, ELECTORATE_WANTED, ["NR_ZONA", "NR_SECAO", "QT_ELEITOR_SECAO"], cache_dir
    )
    return pl.scan_parquet(pq)


# --------------------------------------------------------------------------
# Domínio: seleção e totalização (sem I/O)
# --------------------------------------------------------------------------
def resolve_municipality(votes: pl.LazyFrame, name: str | None) -> int | None:
    """Nome livre (com ou sem acento) -> CD_MUNICIPIO (código TSE, não IBGE!)."""
    if not name:
        return None
    munis = votes.select("CD_MUNICIPIO", "NM_MUNICIPIO").unique().collect()
    alvo = normalize_text(name)
    hits = [r for r in munis.iter_rows(named=True) if normalize_text(r["NM_MUNICIPIO"]) == alvo]
    if not hits:
        parecidos = sorted(
            r["NM_MUNICIPIO"] for r in munis.iter_rows(named=True)
            if alvo in normalize_text(r["NM_MUNICIPIO"])
        )
        raise TseDataError(f"Município '{name}' não encontrado. Parecidos: {parecidos[:10]}")
    return int(hits[0]["CD_MUNICIPIO"])


def office_filter(office: str) -> pl.Expr:
    return pl.col("DS_CARGO") == normalize_text(office)


def classify_vote(proportional: bool) -> pl.Expr:
    """NOMINAL / LEGENDA / BRANCO / NULO / ANULADO_SEPARADO."""
    nr = pl.col("NR_VOTAVEL")
    expr = (
        pl.when(nr == VOTO_BRANCO).then(pl.lit("BRANCO"))
        .when(nr == VOTO_NULO).then(pl.lit("NULO"))
        .when(nr == VOTO_ANULADO_SEPARADO).then(pl.lit("ANULADO_SEPARADO"))
    )
    if proportional:  # nos proporcionais, votável de 2 dígitos = voto de legenda
        expr = expr.when(nr < 100).then(pl.lit("LEGENDA"))
    return expr.otherwise(pl.lit("NOMINAL")).alias("TIPO_VOTO")


def list_polling_places(votes: pl.LazyFrame, turno: int, muni: int | None, zona: int | None) -> pl.DataFrame:
    lf = votes.filter(pl.col("NR_TURNO") == turno)
    if muni is not None:
        lf = lf.filter(pl.col("CD_MUNICIPIO") == muni)
    if zona is not None:
        lf = lf.filter(pl.col("NR_ZONA") == zona)
    extra = [c for c in ("NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO") if c in votes.collect_schema()]
    return (
        lf.group_by(LOCAL_KEY + ["NM_MUNICIPIO"])
        .agg([pl.col(c).first() for c in extra] + [pl.col("NR_SECAO").n_unique().alias("N_SECOES")])
        .sort(LOCAL_KEY)
        .collect()
    )


def search_places(places: pl.DataFrame, term: str) -> pl.DataFrame:
    alvo = normalize_text(term)
    mask = [
        alvo in normalize_text(r.get("NM_LOCAL_VOTACAO")) or alvo in normalize_text(r.get("DS_LOCAL_VOTACAO_ENDERECO"))
        for r in places.iter_rows(named=True)
    ]
    return places.filter(pl.Series(mask, dtype=pl.Boolean))


def candidate_name(votes: pl.LazyFrame, turno: int, office: str, number: int, muni: int | None = None) -> str:
    """Nome do votável. Em eleição municipal o nº só é único dentro do município."""
    cond = (pl.col("NR_TURNO") == turno) & office_filter(office) & (pl.col("NR_VOTAVEL") == number)
    if muni is not None:
        cond &= pl.col("CD_MUNICIPIO") == muni
    names = sorted(votes.filter(cond).select("NM_VOTAVEL").unique().collect()["NM_VOTAVEL"].to_list())
    if not names:
        raise TseDataError(
            f"Nenhum voto para o nº {number} no cargo '{office}', turno {turno}. "
            "Confira cargo/turno/município (nº de candidato só é único dentro do cargo+UF, "
            "ou cargo+município nas eleições municipais)."
        )
    if len(names) > 1:
        raise TseDataError(
            f"O nº {number} corresponde a {len(names)} votáveis em '{office}' ({', '.join(names[:5])}…): "
            "informe --municipio."
        )
    return names[0]


def _vote_breakdown(number: int) -> list[pl.Expr]:
    q, t = pl.col("QT_VOTOS").fill_null(0), pl.col("TIPO_VOTO")
    return [
        q.filter(pl.col("NR_VOTAVEL") == number).sum().alias("VOTOS_CANDIDATO"),
        q.filter(t == "NOMINAL").sum().alias("VOTOS_NOMINAIS"),
        q.filter(t == "LEGENDA").sum().alias("VOTOS_LEGENDA"),
        q.filter(t == "BRANCO").sum().alias("VOTOS_BRANCOS"),
        q.filter(t == "NULO").sum().alias("VOTOS_NULOS"),
        q.filter(t == "ANULADO_SEPARADO").sum().alias("VOTOS_ANULADOS_SEPARADO"),
        q.sum().alias("VOTOS_APURADOS"),
    ]


def _with_shares(df: pl.DataFrame) -> pl.DataFrame:
    validos = pl.col("VOTOS_NOMINAIS") + pl.col("VOTOS_LEGENDA")
    return df.with_columns(validos.alias("VOTOS_VALIDOS")).with_columns(
        pl.when(pl.col("VOTOS_VALIDOS") > 0)
        .then((100 * pl.col("VOTOS_CANDIDATO") / pl.col("VOTOS_VALIDOS")).round(3))
        .otherwise(None)
        .alias("PCT_VALIDOS")
    )


def tally_by_section(
    votes: pl.LazyFrame, turno: int, office: str, number: int, zona: int, local: int, muni: int | None
) -> pl.DataFrame:
    """Votos do candidato em cada seção de UM local (inclui seções com 0 voto)."""
    cond = (
        (pl.col("NR_TURNO") == turno) & office_filter(office)
        & (pl.col("NR_ZONA") == zona) & (pl.col("NR_LOCAL_VOTACAO") == local)
    )
    if muni is not None:
        cond &= pl.col("CD_MUNICIPIO") == muni
    proportional = normalize_text(office) in PROPORTIONAL_OFFICES
    df = (
        votes.filter(cond)
        .with_columns(classify_vote(proportional))
        .group_by(["NR_ZONA", "NR_LOCAL_VOTACAO", "NR_SECAO"])
        .agg(_vote_breakdown(number))
        .sort("NR_SECAO")
        .collect()
    )
    if df.is_empty():
        raise TseDataError(f"Nenhuma seção para zona {zona}, local {local}, cargo '{office}', turno {turno}.")
    return _with_shares(df)


def tally_by_place(
    votes: pl.LazyFrame, turno: int, office: str, number: int, muni: int | None
) -> pl.DataFrame:
    cond = (pl.col("NR_TURNO") == turno) & office_filter(office)
    if muni is not None:
        cond &= pl.col("CD_MUNICIPIO") == muni
    proportional = normalize_text(office) in PROPORTIONAL_OFFICES
    names = [c for c in ("NM_MUNICIPIO", "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO") if c in votes.collect_schema()]
    df = (
        votes.filter(cond)
        .with_columns(classify_vote(proportional))
        .group_by(LOCAL_KEY)
        .agg([pl.col(c).first() for c in names] + _vote_breakdown(number) + [pl.col("NR_SECAO").n_unique().alias("N_SECOES")])
        .collect()
    )
    return _with_shares(df).sort("VOTOS_CANDIDATO", descending=True)


def add_total_row(df: pl.DataFrame) -> pl.DataFrame:
    numeric = [c for c in df.columns if c.startswith("VOTOS_") or c in ("QT_ELEITOR_SECAO", "QT_ELEITORES_EFETIVOS")]
    total = df.select([pl.col(c).sum() for c in numeric])
    total = total.with_columns(
        pl.when(pl.col("VOTOS_VALIDOS") > 0)
        .then((100 * pl.col("VOTOS_CANDIDATO") / pl.col("VOTOS_VALIDOS")).round(3))
        .otherwise(None).alias("PCT_VALIDOS"),
        pl.lit("TOTAL DO LOCAL").alias("SECAO"),
    )
    body = df.with_columns(pl.col("NR_SECAO").cast(pl.String).alias("SECAO"))
    return pl.concat([body, total], how="diagonal_relaxed")


# --------------------------------------------------------------------------
# Enriquecimento com o arquivo de eleitorado (opcional)
# --------------------------------------------------------------------------
def electorate_by_section(elect: pl.LazyFrame, turno: int) -> pl.DataFrame:
    """Uma linha por seção, com eleitorado próprio + das seções agregadas a ela."""
    schema = elect.collect_schema()
    lf = elect.filter(pl.col("NR_TURNO") == turno) if "NR_TURNO" in schema else elect
    lf = lf.unique(subset=["NR_ZONA", "NR_SECAO"], keep="first")
    base = lf.collect()

    if "NR_SECAO_PRINCIPAL" not in schema:
        logger.warning("arquivo de eleitorado sem NR_SECAO_PRINCIPAL: agregação não será exibida")
        return base.with_columns(
            pl.col("QT_ELEITOR_SECAO").alias("QT_ELEITORES_EFETIVOS"),
            pl.lit(None, dtype=pl.String).alias("SECOES_AGREGADAS"),
        )

    is_aggregated = pl.col("NR_SECAO_PRINCIPAL").is_not_null() & (pl.col("NR_SECAO_PRINCIPAL") != pl.col("NR_SECAO"))
    aggregated = (
        base.filter(is_aggregated)
        .group_by(["NR_ZONA", "NR_SECAO_PRINCIPAL"])
        .agg(
            pl.col("NR_SECAO").sort().cast(pl.String).str.join(",").alias("SECOES_AGREGADAS"),
            pl.col("QT_ELEITOR_SECAO").sum().alias("_ELEIT_AGREG"),
        )
        .rename({"NR_SECAO_PRINCIPAL": "NR_SECAO"})
    )
    return base.join(aggregated, on=["NR_ZONA", "NR_SECAO"], how="left").with_columns(
        (pl.col("QT_ELEITOR_SECAO").fill_null(0) + pl.col("_ELEIT_AGREG").fill_null(0)).alias("QT_ELEITORES_EFETIVOS")
    ).drop("_ELEIT_AGREG")


def enrich_sections(df: pl.DataFrame, elect_sec: pl.DataFrame) -> pl.DataFrame:
    keep = [c for c in ("NR_ZONA", "NR_SECAO", "QT_ELEITOR_SECAO", "QT_ELEITORES_EFETIVOS", "SECOES_AGREGADAS")
            if c in elect_sec.columns]
    out = df.join(elect_sec.select(keep), on=["NR_ZONA", "NR_SECAO"], how="left")
    if "QT_ELEITORES_EFETIVOS" in out.columns:
        out = out.with_columns(
            pl.when(pl.col("QT_ELEITORES_EFETIVOS") > 0)
            .then((100 * pl.col("VOTOS_APURADOS") / pl.col("QT_ELEITORES_EFETIVOS")).round(2))
            .otherwise(None).alias("PCT_COMPARECIMENTO_APROX")
        )
    return out


def enrich_places(df: pl.DataFrame, votes: pl.LazyFrame, elect_sec: pl.DataFrame, turno: int, office: str) -> pl.DataFrame:
    """Leva bairro/CEP/coordenadas/eleitorado ao nível do local.

    A ponte seção -> local vem do ARQUIVO DE VOTAÇÃO (onde a urna funcionou),
    não do cadastro, para respeitar remanejamentos provisórios de seção.
    """
    bridge = (
        votes.filter((pl.col("NR_TURNO") == turno) & office_filter(office))
        .select(LOCAL_KEY + ["NR_SECAO"]).unique().collect()
    )
    attrs = [c for c in ("NM_BAIRRO", "NR_CEP", "NR_LATITUDE", "NR_LONGITUDE") if c in elect_sec.columns]
    eleit_col = "QT_ELEITORES_EFETIVOS" if "QT_ELEITORES_EFETIVOS" in elect_sec.columns else "QT_ELEITOR_SECAO"
    per_place = (
        bridge.join(elect_sec, on=["NR_ZONA", "NR_SECAO"], how="left", suffix="_CAD")
        .group_by(LOCAL_KEY)
        .agg([pl.col(c).drop_nulls().first() for c in attrs] + [pl.col(eleit_col).sum().alias("QT_ELEITORES")])
    )
    return df.join(per_place, on=LOCAL_KEY, how="left")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RunConfig:
    command: str
    year: int
    uf: str
    turno: int
    office: str
    municipality: str | None
    cache_dir: str
    candidate: int | None = None
    zona: int | None = None
    local: int | None = None
    search: str | None = None
    with_electorate: bool = False


def _save(df: pl.DataFrame, path: Path, cfg: RunConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(path, separator=";")
    meta = {"config": asdict(cfg), "generated_at": datetime.now(timezone.utc).isoformat(), "rows": df.height}
    path.with_suffix(".proveniencia.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    logger.info("salvo: %s", path)


def cmd_locais(args: argparse.Namespace, cfg: RunConfig) -> None:
    votes = load_section_votes(cfg.year, cfg.uf, cfg.office, Path(cfg.cache_dir), args.sha512)
    muni = resolve_municipality(votes, cfg.municipality)
    places = list_polling_places(votes, cfg.turno, muni, cfg.zona)
    if cfg.search:
        places = search_places(places, cfg.search)
    with pl.Config(tbl_rows=60, tbl_width_chars=200, fmt_str_lengths=60):
        print(places)
    if args.saida:
        _save(places, Path(args.saida), cfg)


def _resolve_place(votes: pl.LazyFrame, cfg: RunConfig, muni: int | None) -> tuple[int, int]:
    if cfg.zona is not None and cfg.local is not None:
        return cfg.zona, cfg.local
    if not cfg.search:
        raise TseDataError("Informe --zona e --local, ou --busca (com --municipio).")
    hits = search_places(list_polling_places(votes, cfg.turno, muni, cfg.zona), cfg.search)
    if hits.height != 1:
        with pl.Config(tbl_rows=30, tbl_width_chars=200, fmt_str_lengths=60):
            print(hits)
        raise TseDataError(f"A busca '{cfg.search}' retornou {hits.height} locais; refine ou use --zona/--local.")
    row = hits.row(0, named=True)
    logger.info("local: zona %s, nº %s — %s", row["NR_ZONA"], row["NR_LOCAL_VOTACAO"], row.get("NM_LOCAL_VOTACAO"))
    return int(row["NR_ZONA"]), int(row["NR_LOCAL_VOTACAO"])


def cmd_secoes(args: argparse.Namespace, cfg: RunConfig) -> None:
    cache = Path(cfg.cache_dir)
    votes = load_section_votes(cfg.year, cfg.uf, cfg.office, cache, args.sha512)
    muni = resolve_municipality(votes, cfg.municipality)
    assert cfg.candidate is not None
    nome = candidate_name(votes, cfg.turno, cfg.office, cfg.candidate, muni)
    zona, local = _resolve_place(votes, cfg, muni)

    df = tally_by_section(votes, cfg.turno, cfg.office, cfg.candidate, zona, local, muni)
    if cfg.with_electorate:
        elect = electorate_by_section(load_electorate(cfg.year, cfg.uf, cache, args.sha512), cfg.turno)
        df = enrich_sections(df, elect)
    df = add_total_row(df)

    info = (
        votes.filter((pl.col("NR_ZONA") == zona) & (pl.col("NR_LOCAL_VOTACAO") == local))
        .select([c for c in ("NM_MUNICIPIO", "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO")
                 if c in votes.collect_schema()])
        .head(1).collect().row(0, named=True)
    )
    print(f"\n{cfg.candidate} — {nome} | {normalize_text(cfg.office)} | {cfg.uf} {cfg.year}, {cfg.turno}º turno")
    print(f"Local: zona {zona}, nº {local} — {info.get('NM_LOCAL_VOTACAO')} — "
          f"{info.get('DS_LOCAL_VOTACAO_ENDERECO')} ({info.get('NM_MUNICIPIO')})\n")
    show = ["SECAO", "VOTOS_CANDIDATO", "VOTOS_VALIDOS", "PCT_VALIDOS", "VOTOS_BRANCOS", "VOTOS_NULOS",
            "VOTOS_APURADOS", "QT_ELEITORES_EFETIVOS", "SECOES_AGREGADAS"]
    with pl.Config(tbl_rows=200, tbl_width_chars=200):
        print(df.select([c for c in show if c in df.columns]))

    saida = Path(args.saida or f"secoes_{cfg.candidate}_z{zona}_l{local}_{cfg.uf}_{cfg.year}_t{cfg.turno}.csv")
    _save(df, saida, cfg)


def cmd_por_local(args: argparse.Namespace, cfg: RunConfig) -> None:
    cache = Path(cfg.cache_dir)
    votes = load_section_votes(cfg.year, cfg.uf, cfg.office, cache, args.sha512)
    muni = resolve_municipality(votes, cfg.municipality)
    assert cfg.candidate is not None
    nome = candidate_name(votes, cfg.turno, cfg.office, cfg.candidate, muni)
    df = tally_by_place(votes, cfg.turno, cfg.office, cfg.candidate, muni)
    if cfg.with_electorate:
        elect = electorate_by_section(load_electorate(cfg.year, cfg.uf, cache, args.sha512), cfg.turno)
        df = enrich_places(df, votes, elect, cfg.turno, cfg.office)

    print(f"\n{cfg.candidate} — {nome}: {df['VOTOS_CANDIDATO'].sum():,} votos em {df.height:,} locais")
    with pl.Config(tbl_rows=20, tbl_width_chars=200, fmt_str_lengths=45):
        print(df.select([c for c in ("NR_ZONA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "N_SECOES",
                                     "VOTOS_CANDIDATO", "VOTOS_VALIDOS", "PCT_VALIDOS") if c in df.columns]))
    saida = Path(args.saida or f"locais_{cfg.candidate}_{cfg.uf}_{cfg.year}_t{cfg.turno}.csv")
    _save(df, saida, cfg)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ano", type=int, default=2022)
    common.add_argument("--uf", required=True, type=str.upper)
    common.add_argument("--turno", type=int, default=1, choices=[1, 2])
    common.add_argument("--municipio", help="nome do município (acentos opcionais)")
    common.add_argument("--zona", type=int)
    common.add_argument("--cache-dir", default="cache_tse")
    common.add_argument("--saida", help="caminho do CSV de saída")
    common.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE, se publicado")
    common.add_argument("-v", "--verbose", action="store_true")

    p = argparse.ArgumentParser(description="Votos por local de votação / seção (TSE).")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("locais", parents=[common], help="listar/buscar locais de votação")
    s.add_argument("--cargo", default="DEPUTADO ESTADUAL", help="define qual arquivo ler (UF ou BR)")
    s.add_argument("--busca", help="trecho do nome ou endereço do local")

    for name, hlp in (("secoes", "votos por seção de um local"), ("por-local", "votos por local")):
        s = sub.add_parser(name, parents=[common], help=hlp)
        s.add_argument("--cargo", required=True, help='ex.: "deputado estadual", "presidente"')
        s.add_argument("--candidato", required=True, type=int, help="número na urna")
        s.add_argument("--com-eleitorado", action="store_true",
                       help="baixar eleitorado_local_votacao (agregação, bairro, coordenadas)")
        if name == "secoes":
            s.add_argument("--local", type=int, help="NR_LOCAL_VOTACAO (único dentro da zona)")
            s.add_argument("--busca", help="alternativa a --zona/--local: trecho do nome do local")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
    )
    cfg = RunConfig(
        command=args.command, year=args.ano, uf=args.uf, turno=args.turno, office=args.cargo,
        municipality=args.municipio, cache_dir=args.cache_dir,
        candidate=getattr(args, "candidato", None), zona=args.zona, local=getattr(args, "local", None),
        search=getattr(args, "busca", None), with_electorate=getattr(args, "com_eleitorado", False),
    )
    handlers = {"locais": cmd_locais, "secoes": cmd_secoes, "por-local": cmd_por_local}
    try:
        handlers[args.command](args, cfg)
    except (TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
