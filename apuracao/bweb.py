"""Boletim de Urna (bweb) como terceira fonte dos totais e dos votos (rodada 55).

O TSE publica o BU de cada UF (`resultados-<ano>-boletim-de-urna` no CKAN) dias ANTES de atualizar os
microdados no 2º turno: em 2022, BU do 2º turno em 01/11 e `votacao_secao`/`detalhe_votacao_secao`/munzona
em 05/11. Este módulo só TRADUZ o BU para os mesmos dados intermediários que a fonte "secoes" já consome
(votos por seção no esquema do `votacao_secao` e detalhe por seção no do `detalhe_votacao_secao`): a
classificação dos votos continua num lugar só (`historico.detalhe_de_secoes`/`destino_legenda`).

Nomes com carimbo (`bweb_1t_RJ_051020261403.zip`): nunca fixados aqui — `recursos` lê o CKAN e `escolher`
fica com o de maior carimbo. Cache em `<cache>/bweb/<ano>/` (o carimbo é a data de GERAÇÃO, não o ano da
eleição). Um BU só vale com o SHA-512 conferido contra o `.sha512` publicado (`no_cache`).

Mapeamento de colunas (cabeçalhos reais de 2022 e 2026 conferidos; 45 colunas, nomes que mudam entre anos):

| BU                                         | votacao_secao / detalhe_votacao_secao                      |
|--------------------------------------------|------------------------------------------------------------|
| CD_CARGO_PERGUNTA                          | CD_CARGO                                                   |
| DS_CARGO_PERGUNTA                          | DS_CARGO (maiúsculas, como a conversão do núcleo)          |
| CD_TIPO_VOTAVEL/DS_TIPO_VOTAVEL + NR_VOTAVEL| NR_VOTAVEL: Branco → 95, Nulo → 96 (já vêm assim no BU)   |
| DS_AGREGADAS (2022) / DS_SECOES_AGREGADAS (2026) | QT_SECOES_AGREGADAS (nº de seções na lista)          |
| DT_BU_RECEBIDO (2022 "dd/mm/aaaa hh:mm:ss"; 2026 "aaaa-mm-dd hh:mm:ss") | DT_PRIM_TOT_PARCIAL_HOR_TSE ("dd/mm/aaaa hh:mm:ss") |
| QT_APTOS/QT_COMPARECIMENTO/QT_ABSTENCOES (repetidos em cada votável) | uma vez por seção × cargo        |
| CD_TIPO_ELEICAO 0 + NM_TIPO_ELEICAO "Eleição Ordinária" | (o votacao_secao usa CD_TIPO_ELEICAO 2)       |
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import microdados as md

logger = logging.getLogger("apuracao.bweb")

CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show"
PACOTE = "resultados-{ano}-boletim-de-urna"
EXTERIOR = "ZZ"
_NOME = re.compile(r"bweb_(?P<turno>\d)t_(?P<uf>[A-Z]{2})_(?P<carimbo>\d{12})\.zip$")


@dataclass(frozen=True)
class RecursoBU:
    ano: int
    turno: int
    uf: str
    url: str
    carimbo: datetime  # data de geração no nome do arquivo

    @property
    def nome(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def pasta(cache: Path, ano: int) -> Path:
    return cache / "bweb" / str(ano)


def _carimbo(texto: str) -> datetime:
    return datetime.strptime(texto, "%d%m%Y%H%M")


def recursos(ano: int, sessao: Any = requests) -> list[RecursoBU]:
    """Os BUs do ano listados no CKAN (uma chamada). CKAN fora do ar ou pacote inexistente → lista vazia, com
    aviso: o BU é só um fallback, a falta dele nunca pode parar a importação."""
    try:
        r = sessao.get(CKAN, params={"id": PACOTE.format(ano=ano)}, headers=v.HTTP_HEADERS, timeout=60)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        dados = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("CKAN do TSE indisponível para os BUs de %s: %s", ano, exc)
        return []
    if not dados.get("success"):
        return []
    saida = []
    for res in dados.get("result", {}).get("resources", []):
        m = _NOME.search(res.get("url") or "")
        if m:
            saida.append(RecursoBU(ano, int(m["turno"]), m["uf"], res["url"], _carimbo(m["carimbo"])))
    return saida


def escolher(lista: list[RecursoBU], turno: int, uf: str) -> RecursoBU | None:
    """O BU mais novo (maior carimbo) do turno e da UF."""
    achados = [r for r in lista if r.turno == turno and r.uf == uf.upper()]
    return max(achados, key=lambda r: r.carimbo, default=None)


def descobrir(ano: int, turno: int, uf: str, sessao: Any = requests) -> RecursoBU | None:
    return escolher(recursos(ano, sessao), turno, uf)


def _sha_publicado(url: str, sessao: Any) -> str:
    r = sessao.get(f"{url}.sha512", headers=v.HTTP_HEADERS, timeout=60)
    if r.status_code == 404:
        raise v.TseDataError(f"o TSE não publicou o SHA-512 de {url.rsplit('/', 1)[-1]}")
    r.raise_for_status()
    sha = (r.text.split() or [""])[0].lower()
    if not re.fullmatch(r"[0-9a-f]{128}", sha):
        raise v.TseDataError(f"SHA-512 publicado ilegível para {url.rsplit('/', 1)[-1]}")
    return sha


def _proveniencia(zp: Path) -> dict[str, Any]:
    p = zp.with_suffix(".proveniencia.json")
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def conferido(zp: Path) -> bool:
    """ZIP no cache, com o SHA-512 calculado no download igual ao publicado pelo TSE e com dados."""
    prov = _proveniencia(zp)
    if not zp.exists() or not prov.get("sha512") or prov.get("sha512") != prov.get("sha512_publicado"):
        return False
    try:
        return md.tem_dados(zp, "")
    except (OSError, ValueError) as exc:  # zipfile.BadZipFile é ValueError
        logger.warning("%s ilegível no cache: %s", zp.name, exc)
        return False


def baixar(recurso: RecursoBU, cache: Path, sessao: Any = requests) -> Path:
    """Baixa (troca atômica, cópia velha da CDN recusada) e confere o SHA-512 com o publicado; divergente →
    `TseDataError` sem tocar no cache. Já conferido no cache → nada a fazer. Versões anteriores do mesmo
    turno e UF (e os Parquet delas) saem quando a nova chega."""
    destino = pasta(cache, recurso.ano) / recurso.nome
    if conferido(destino):
        return destino
    sha = _sha_publicado(recurso.url, sessao)
    logger.info("baixando %s (Boletim de Urna)", recurso.nome)
    md.baixar(recurso.url, destino, sessao, sha512=sha)
    prov_p = destino.with_suffix(".proveniencia.json")
    prov = json.loads(prov_p.read_text())
    prov["sha512_publicado"] = sha
    prov_p.write_text(json.dumps(prov, indent=2))
    for antigo in _no_disco(cache, recurso.ano, recurso.turno, recurso.uf):
        if antigo != destino:
            for f in (antigo, antigo.with_suffix(".proveniencia.json"), *derivados(antigo)):
                f.unlink(missing_ok=True)
    return destino


def derivados(zp: Path) -> list[Path]:
    return sorted(zp.parent.glob(f"{zp.stem}__*.parquet"))


def _no_disco(cache: Path, ano: int, turno: int, uf: str) -> list[Path]:
    return sorted(pasta(cache, ano).glob(f"bweb_{turno}t_{uf.upper()}_*.zip"))


def no_cache(cache: Path, ano: int, turno: int, uf: str) -> Path | None:
    """O BU do turno e da UF que vale (o mais novo com SHA conferido e dados), lido do DISCO."""
    validos = [zp for zp in _no_disco(cache, ano, turno, uf) if _NOME.search(zp.name) and conferido(zp)]
    return max(validos, key=lambda zp: _carimbo(_NOME.search(zp.name)["carimbo"]), default=None)


# --------------------------------------------------------------------------
# Leitura e tradução (sem rede)
# --------------------------------------------------------------------------
LIDAS = ["NR_TURNO", "NM_TIPO_ELEICAO", "CD_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
         "NR_LOCAL_VOTACAO", "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA", "NR_PARTIDO", "QT_APTOS", "QT_COMPARECIMENTO",
         "QT_ABSTENCOES", "CD_TIPO_URNA", "DS_TIPO_URNA", "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL", "NR_VOTAVEL",
         "NM_VOTAVEL", "QT_VOTOS", "DS_AGREGADAS", "DS_SECOES_AGREGADAS", "DT_BU_RECEBIDO"]
OBRIGATORIAS = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA",
                "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "DS_TIPO_VOTAVEL", "NR_VOTAVEL", "QT_VOTOS",
                "DT_BU_RECEBIDO"]
# DS_TIPO_VOTAVEL (comparado por `compact`) → NR_VOTAVEL na convenção do votacao_secao; None = o número do
# próprio votável (candidato ou, na legenda, o partido)
TIPOS_VOTAVEL = {"NOMINAL": None, "LEGENDA": None, "BRANCO": 95, "NULO": 96}
CHAVE_SECAO = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO"]
# esquemas que os consumidores já leem (Parquet do votacao_secao e do detalhe_votacao_secao)
ESQUEMA_VOTOS = {"NR_TURNO": pl.Int64, "SG_UF": pl.String, "CD_MUNICIPIO": pl.Int64, "NM_MUNICIPIO": pl.String,
                 "NR_ZONA": pl.Int64, "NR_SECAO": pl.Int64, "DS_CARGO": pl.String, "NR_VOTAVEL": pl.Int64,
                 "NM_VOTAVEL": pl.String, "QT_VOTOS": pl.Int64, "NR_LOCAL_VOTACAO": pl.Int64, "CD_CARGO": pl.Int64,
                 "SQ_CANDIDATO": pl.Int64, "NM_LOCAL_VOTACAO": pl.String, "DS_LOCAL_VOTACAO_ENDERECO": pl.String}
ESQUEMA_DETALHE = {"NR_TURNO": pl.Int64, "SG_UF": pl.String, "CD_MUNICIPIO": pl.Int64, "NR_ZONA": pl.Int64,
                   "NR_SECAO": pl.Int64, "CD_CARGO": pl.Int64, "NR_LOCAL_VOTACAO": pl.Int64, "QT_APTOS": pl.Int64,
                   "QT_COMPARECIMENTO": pl.Int64, "QT_ABSTENCOES": pl.Int64, "DS_CARGO": pl.String,
                   "DT_PRIM_TOT_PARCIAL_HOR_TSE": pl.String, "QT_SECOES_AGREGADAS": pl.Int64, "CD_ELEICAO": pl.Int64}


def ler(zp: Path, uf: str) -> pl.LazyFrame:
    """O CSV do BU (latin-1, ';') convertido UMA vez para Parquet ao lado do ZIP (só as colunas usadas: o do
    RJ de 2026 tem 3,3 GB) e normalizado: cargo, agregadas e hora com os nomes do votacao_secao, inteiros
    negativos (-1) nulos, só a eleição ordinária."""
    spec = v.DatasetSpec(zp.stem, "", uf.upper())
    antigo = zp.parent / f"{spec.name}__{spec.uf_filter}.parquet"
    if antigo.exists():  # convertido com menos colunas (LIDAS mudou): refaz
        with zipfile.ZipFile(zp) as zf:
            cabecalho = set(v.read_header(zf, v.pick_csv_member(zf, spec.uf_filter)))
        if (set(LIDAS) & cabecalho) - set(pl.scan_parquet(antigo).collect_schema().names()):
            antigo.unlink()
    pq = v.zip_to_parquet(zp, spec, LIDAS, OBRIGATORIAS, zp.parent, tipo_ordinario=None)
    lf = pl.scan_parquet(pq)
    tem = set(lf.collect_schema().names())
    inteiro = lambda c: pl.col(c).cast(pl.String).str.strip_chars().cast(pl.Int64, strict=False)  # noqa: E731
    positivo = lambda c: pl.when(inteiro(c) >= 0).then(inteiro(c)).alias(c)  # noqa: E731
    texto = lambda c: (pl.col(c) if c in tem else pl.lit(None, pl.String)).cast(pl.String)  # noqa: E731
    hora = pl.col("DT_BU_RECEBIDO").str.strip_chars()
    if "NM_TIPO_ELEICAO" in tem:  # ordinária pelo nome: o código do BU é outro (0)
        lf = lf.filter(pl.col("NM_TIPO_ELEICAO").str.to_uppercase().str.contains("ORDIN"))
    return lf.select(
        "NR_TURNO", "SG_UF", "CD_MUNICIPIO", texto("NM_MUNICIPIO").alias("NM_MUNICIPIO"), "NR_ZONA", "NR_SECAO",
        (pl.col("NR_LOCAL_VOTACAO") if "NR_LOCAL_VOTACAO" in tem else pl.lit(None, pl.Int64)).alias("NR_LOCAL_VOTACAO"),
        positivo("CD_CARGO_PERGUNTA").alias("CD_CARGO"),
        pl.col("DS_CARGO_PERGUNTA").str.to_uppercase().str.strip_chars().alias("DS_CARGO"),
        positivo("NR_PARTIDO") if "NR_PARTIDO" in tem else pl.lit(None, pl.Int64).alias("NR_PARTIDO"),
        "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
        positivo("CD_TIPO_URNA") if "CD_TIPO_URNA" in tem else pl.lit(None, pl.Int64).alias("CD_TIPO_URNA"),
        texto("DS_TIPO_URNA").alias("DS_TIPO_URNA"), texto("DS_TIPO_VOTAVEL").alias("DS_TIPO_VOTAVEL"),
        "NR_VOTAVEL", texto("NM_VOTAVEL").alias("NM_VOTAVEL"), "QT_VOTOS",
        (positivo("CD_ELEICAO") if "CD_ELEICAO" in tem else pl.lit(None, pl.Int64)).alias("CD_ELEICAO"),
        pl.coalesce(texto("DS_SECOES_AGREGADAS"), texto("DS_AGREGADAS")).alias("_AGREGADAS"),
        pl.coalesce(hora.str.to_datetime("%d/%m/%Y %H:%M:%S", strict=False),
                    hora.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False))
        .dt.strftime("%d/%m/%Y %H:%M:%S").alias("DT_PRIM_TOT_PARCIAL_HOR_TSE"),
    )


def _numero_votavel(bu: pl.LazyFrame) -> pl.Expr:
    """NR_VOTAVEL na convenção do votacao_secao, pela tabela DS_TIPO_VOTAVEL do PRÓPRIO arquivo. Tipo que não
    está em `TIPOS_VOTAVEL` → `TseDataError` (melhor parar que classificar errado)."""
    from apuracao.eleitorado import compact

    tipos = bu.select(pl.col("DS_TIPO_VOTAVEL").unique()).collect()["DS_TIPO_VOTAVEL"].to_list()
    desconhecidos = [t for t in tipos if compact(t) not in TIPOS_VOTAVEL]
    if desconhecidos:
        raise v.TseDataError(f"tipo de votável desconhecido no BU: {desconhecidos}")
    expr = pl.col("NR_VOTAVEL")
    for t in tipos:
        codigo = TIPOS_VOTAVEL[compact(t)]
        if codigo is not None:
            expr = pl.when(pl.col("DS_TIPO_VOTAVEL") == t).then(pl.lit(codigo, pl.Int64)).otherwise(expr)
    return expr


def votos_por_secao(bu: pl.LazyFrame) -> pl.LazyFrame:
    """Votos por seção e votável no esquema do Parquet do `votacao_secao` (o que `historico.load_votos`
    devolve). Colunas que o BU não tem (SQ_CANDIDATO, nome e endereço do local) ficam nulas."""
    numero = _numero_votavel(bu)
    return bu.select(
        *[(numero if c == "NR_VOTAVEL" else pl.col(c)).cast(t).alias(c) if c in bu.collect_schema().names()
          else pl.lit(None, t).alias(c) for c, t in ESQUEMA_VOTOS.items()])


def detalhe_por_secao(bu: pl.LazyFrame) -> pl.DataFrame:
    """Aptos, comparecimento e abstenções UMA vez por seção × cargo (o BU repete em cada votável), no esquema
    do Parquet do `detalhe_votacao_secao`, + QT_SECOES_AGREGADAS (as agregadas já estão nos aptos da
    principal; contá-las dá o QT_TOTAL_SECOES do oficial). Valor que varia dentro da seção × cargo →
    `TseDataError` (nunca somar repetido)."""
    qt = ["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]
    g = (bu.group_by(CHAVE_SECAO)
         .agg(*[pl.col(c).n_unique().alias(f"_N_{c}") for c in qt], *[pl.col(c).first() for c in qt],
              pl.col("NR_LOCAL_VOTACAO").first(), pl.col("DS_CARGO").first(),
              pl.col("DT_PRIM_TOT_PARCIAL_HOR_TSE").first(), pl.col("_AGREGADAS").first(),
              pl.col("CD_ELEICAO").first())
         .collect())
    variando = g.filter(pl.any_horizontal([pl.col(f"_N_{c}") > 1 for c in qt]))
    if variando.height:
        raise v.TseDataError(f"BU com aptos/comparecimento diferentes na mesma seção × cargo em {variando.height} "
                             f"casos (ex.: {variando.select(CHAVE_SECAO).row(0)})")
    agregadas = (pl.col("_AGREGADAS").str.strip_chars().str.split("/").list.eval(
        pl.element().str.strip_chars().filter(pl.element() != "")).list.len().fill_null(0).cast(pl.Int64))
    return g.with_columns(agregadas.alias("QT_SECOES_AGREGADAS")).select(
        [pl.col(c).cast(t) for c, t in ESQUEMA_DETALHE.items()])


def relatorio(bu: pl.LazyFrame) -> dict[str, Any]:
    """Contagens para o documento da rodada: seções por tipo de urna, chave seção × votável duplicada e
    seções com agregadas."""
    secoes = bu.select("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_TIPO_URNA", "DS_TIPO_URNA",
                       "_AGREGADAS").unique(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]).collect()
    duplicadas = (bu.group_by(CHAVE_SECAO + ["NR_VOTAVEL", "DS_TIPO_VOTAVEL"]).len()
                  .filter(pl.col("len") > 1).select(pl.len()).collect().item())
    return {"secoes": secoes.height,
            "por_tipo_de_urna": {f"{c} {d}": n for c, d, n in
                                 secoes.group_by("CD_TIPO_URNA", "DS_TIPO_URNA").len().sort("CD_TIPO_URNA").iter_rows()},
            "chaves_duplicadas": duplicadas,
            "secoes_com_agregadas": secoes.filter(pl.col("_AGREGADAS").is_not_null()).height}


def verificar(bu: pl.LazyFrame) -> dict[str, Any]:
    """`relatorio`, recusando (`TseDataError`) BU com votável repetido na mesma seção × cargo: somaria duas
    vezes (o RJ de 2022, nos dois turnos, não tem nenhum; se aparecer, é para olhar antes de importar)."""
    r = relatorio(bu)
    if r["chaves_duplicadas"]:
        raise v.TseDataError(f"Boletim de Urna com {r['chaves_duplicadas']} votável(is) repetido(s) na mesma seção "
                             "× cargo (urna substituída?): não importado")
    return r
