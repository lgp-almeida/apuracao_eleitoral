"""Análise das parciais de uma noite de apuração a partir do que o coletor guardou (TODO 21, rodada 42).

Entrada: `<dados>/raw/` (e `raw_brasil/`), onde o coletor grava cada VERSÃO distinta de cada JSON do TSE
(`<eleição>/<arquivo>/<AAAAMMDD>_<HHMMSS>_<idg>_<hash>.json.gz`). De cada versão:
  geração no TSE   `dg`/`hg` do próprio JSON;
  chegada aqui     a data de gravação do arquivo (mtime) — a cópia de segurança a preserva (`shutil.copy2`);
  totalização      `dt`/`ht` e % de seções do EA20; no acompanhamento (EA15 da UF, EA14 nacional), a de cada
                   abrangência — o "anúncio".

O que mede (funções sem I/O sobre as tabelas de `ler`):
  atraso da coleta         chegada − geração, por tipo de arquivo;
  anúncio × publicação     para cada totalização anunciada, quando chegou o EA20 gerado depois dela e se antes
                           veio a versão anterior (o TSE anuncia no EA15 antes de regerar o EA20 — rodada 36);
  atraso do TSE            geração do EA20 certo − hora anunciada, por janela de 30 min;
  pausas                   do TSE (acompanhamento sem nova geração) e nossas (nada gravado), separadas;
  critério do coletor      versões que a regra `gerado < anunciado` (`coletor._versao_anterior`) classifica como
                           anteriores × as que de fato eram outro conteúdo;
  peculiaridades           EA20 com dt antes do anúncio; acompanhamento com hora no futuro;
  fim da noite             última totalização em disco × a anunciada.

Limite: o coletor só guarda versões DISTINTAS (mesmo conteúdo = mesmo arquivo), e pede cada arquivo uma vez por
ciclo; duas versões publicadas no mesmo ciclo deixam só a última.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from apuracao.divulgacao import modelo as m

logger = logging.getLogger("apuracao.divulgacao.analise")

BRASILIA = ZoneInfo("America/Sao_Paulo")  # dg/hg e dt/ht do TSE são a hora de Brasília, sem fuso
NOME = re.compile(r"^(?P<uf>[a-z]{2})(?P<mun>\d+)?-(?:c(?P<cargo>\d+)-)?e(?P<ele>\d+)-(?P<tipo>u|ab)$")
CHAVE = ["ELEICAO", "ESCOPO", "UF", "CD_MUNICIPIO"]

VERSOES_SCHEMA = {
    "RAIZ": pl.String, "ELEICAO": pl.Int64, "ARQUIVO": pl.String, "TIPO": pl.String, "ESCOPO": pl.String,
    "UF": pl.String, "CD_MUNICIPIO": pl.Int64, "CARGO": pl.Int64, "GERADO": pl.Datetime, "CHEGADA": pl.Datetime,
    "DT_TOTALIZACAO": pl.Datetime, "PCT": pl.Float64, "FINAL": pl.Boolean, "HASH": pl.String,
}
ANUNCIOS_SCHEMA = {
    "ELEICAO": pl.Int64, "ESCOPO": pl.String, "UF": pl.String, "CD_MUNICIPIO": pl.Int64,
    "DT_ANUNCIADA": pl.Datetime, "PCT": pl.Float64, "GERADO_AB": pl.Datetime, "CHEGADA_AB": pl.Datetime,
    "ARQUIVO_AB": pl.String,
}


# --------------------------------------------------------------------------
# Leitura (I/O)
# --------------------------------------------------------------------------
def _chegada(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=BRASILIA).replace(tzinfo=None)


def ler(dados: Path, raizes: tuple[str, ...] = ("raw", "raw_brasil")) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(versões, anúncios) de tudo o que está em `<dados>/<raiz>/<eleição>/<arquivo>/*.json.gz`."""
    versoes: list[dict[str, Any]] = []
    anuncios: list[dict[str, Any]] = []
    for raiz in raizes:
        for gz in sorted((dados / raiz).glob("*/*/*.json.gz")):
            nome = NOME.match(gz.parent.name)
            if not nome:
                continue
            try:
                with gzip.open(gz, "rt", encoding="utf-8") as fh:
                    d = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("%s ilegível: %s", gz, exc)
                continue
            uf, mun = nome["uf"].upper(), int(nome["mun"]) if nome["mun"] else None
            gerado, chegada = m.to_datetime(d.get("dg"), d.get("hg")), _chegada(gz)
            ele = int(nome["ele"])
            if nome["tipo"] == "ab":
                for linha in m.parse_acompanhamento(d, nome["uf"]).iter_rows(named=True):
                    anuncios.append({"ELEICAO": ele, "ESCOPO": linha["ABRANGENCIA"], "UF": linha["UF"],
                                     "CD_MUNICIPIO": linha["CD_MUNICIPIO"], "DT_ANUNCIADA": linha["DT_TOTALIZACAO"],
                                     "PCT": linha["PCT_SECOES_TOTALIZADAS"], "GERADO_AB": gerado,
                                     "CHEGADA_AB": chegada, "ARQUIVO_AB": gz.parent.name})
                tipo, escopo, dt, pct, final = "acompanhamento", "br" if uf == "BR" else "uf", None, None, None
            else:
                tipo = "resultado"
                escopo = "br" if uf == "BR" else "mun" if mun is not None else "uf"
                dt = m.to_datetime(d.get("dt"), d.get("ht"))
                pct = m.to_float((d.get("s") or {}).get("pstn", (d.get("s") or {}).get("pst")))
                final = d.get("tf") == "s"
            versoes.append({"RAIZ": raiz, "ELEICAO": ele, "ARQUIVO": gz.parent.name, "TIPO": tipo, "ESCOPO": escopo,
                            "UF": uf, "CD_MUNICIPIO": mun, "CARGO": int(nome["cargo"]) if nome["cargo"] else None,
                            "GERADO": gerado, "CHEGADA": chegada, "DT_TOTALIZACAO": dt, "PCT": pct, "FINAL": final,
                            "HASH": gz.stem.removesuffix(".json").rsplit("_", 1)[-1]})
    return pl.DataFrame(versoes, schema=VERSOES_SCHEMA), pl.DataFrame(anuncios, schema=ANUNCIOS_SCHEMA)


# --------------------------------------------------------------------------
# Indicadores (sem I/O)
# --------------------------------------------------------------------------
def _minutos(expr: pl.Expr) -> pl.Expr:
    return expr.dt.total_seconds() / 60


def _estatisticas(col: str) -> list[pl.Expr]:
    return [pl.len().alias("N"), pl.col(col).median().round(2).alias("MEDIANA_MIN"),
            pl.col(col).quantile(0.95, "nearest").round(2).alias("P95_MIN"), pl.col(col).max().round(2).alias("MAX_MIN")]


def atraso_coleta(versoes: pl.DataFrame) -> pl.DataFrame:
    """Chegada − geração (min), por tipo de arquivo (acompanhamento; resultado da UF/BR; dos municípios)."""
    return (versoes.drop_nulls(["GERADO", "CHEGADA"])
            .with_columns(_minutos(pl.col("CHEGADA") - pl.col("GERADO")).alias("ATRASO"))
            .group_by("TIPO", "ESCOPO").agg(_estatisticas("ATRASO")).sort("TIPO", "ESCOPO"))


def anuncios_distintos(anuncios: pl.DataFrame) -> pl.DataFrame:
    """Cada totalização anunciada uma vez: a 1ª vez que um acompanhamento a trouxe. `LIMITE` = a hora anunciada,
    limitada à geração do próprio acompanhamento (o EA14 nacional traz hora no futuro — `coletor._limitar`)."""
    return (anuncios.drop_nulls("DT_ANUNCIADA").sort("CHEGADA_AB")
            .unique(CHAVE + ["DT_ANUNCIADA"], keep="first", maintain_order=True)
            .with_columns(pl.min_horizontal("DT_ANUNCIADA", "GERADO_AB").alias("LIMITE"),
                          (pl.col("DT_ANUNCIADA") > pl.col("GERADO_AB")).alias("HORA_NO_FUTURO")))


def publicacao(anuncios: pl.DataFrame, versoes: pl.DataFrame) -> pl.DataFrame:
    """Uma linha por (totalização anunciada × arquivo EA20 daquela abrangência): quando chegou a versão gerada depois
    do anúncio, quantas versões anteriores chegaram antes dela e o atraso do próprio TSE. As versões consideradas são
    as que chegaram entre este anúncio e o próximo da mesma abrangência."""
    an = anuncios_distintos(anuncios).sort("CHEGADA_AB")
    res = versoes.filter(pl.col("TIPO") == "resultado").sort("CHEGADA")
    por_chave: dict[tuple, list[dict]] = {}
    for r in res.iter_rows(named=True):
        por_chave.setdefault((r["ELEICAO"], r["ESCOPO"], r["UF"], r["CD_MUNICIPIO"]), []).append(r)
    linhas = []
    for chave, grupo in an.group_by(CHAVE, maintain_order=True):
        lista = grupo.sort("CHEGADA_AB").to_dicts()
        vers = por_chave.get(tuple(chave), [])
        arquivos = sorted({v["ARQUIVO"] for v in vers})
        for i, a in enumerate(lista):
            fim = lista[i + 1]["CHEGADA_AB"] if i + 1 < len(lista) else None
            for arq in arquivos:
                # o coletor lê o acompanhamento ANTES dos EA20 do mesmo ciclo: a janela começa na chegada do anúncio
                janela = [v for v in vers if v["ARQUIVO"] == arq and v["CHEGADA"] >= a["CHEGADA_AB"]
                          and (fim is None or v["CHEGADA"] < fim)]
                certa = next((v for v in janela if v["GERADO"] is not None and v["GERADO"] >= a["LIMITE"]), None)
                anteriores = [v for v in janela if certa is None or v["CHEGADA"] < certa["CHEGADA"]]
                anteriores = [v for v in anteriores if v["GERADO"] is not None and v["GERADO"] < a["LIMITE"]]
                linhas.append({
                    **{k: a[k] for k in CHAVE}, "ARQUIVO": arq, "CARGO": next(v["CARGO"] for v in vers if v["ARQUIVO"] == arq),
                    "DT_ANUNCIADA": a["DT_ANUNCIADA"], "LIMITE": a["LIMITE"], "CHEGADA_AB": a["CHEGADA_AB"],
                    "N_ANTERIORES": len(anteriores), "VEIO_ANTERIOR_PRIMEIRO": bool(anteriores),
                    "GERADO_CERTO": certa["GERADO"] if certa else None, "CHEGADA_CERTA": certa["CHEGADA"] if certa else None,
                    "DT_EA20": certa["DT_TOTALIZACAO"] if certa else None,
                    "HASH_CERTO": certa["HASH"] if certa else None,
                    "HASHES_ANTERIORES": [v["HASH"] for v in anteriores]})
    schema = {**{k: ANUNCIOS_SCHEMA[k] for k in CHAVE}, "ARQUIVO": pl.String, "CARGO": pl.Int64,
              "DT_ANUNCIADA": pl.Datetime, "LIMITE": pl.Datetime, "CHEGADA_AB": pl.Datetime, "N_ANTERIORES": pl.Int64,
              "VEIO_ANTERIOR_PRIMEIRO": pl.Boolean, "GERADO_CERTO": pl.Datetime, "CHEGADA_CERTA": pl.Datetime,
              "DT_EA20": pl.Datetime, "HASH_CERTO": pl.String, "HASHES_ANTERIORES": pl.List(pl.String)}
    return (pl.DataFrame(linhas, schema=schema)
            .with_columns(_minutos(pl.col("CHEGADA_CERTA") - pl.col("CHEGADA_AB")).alias("ESPERA_MIN"),
                          _minutos(pl.col("GERADO_CERTO") - pl.col("DT_ANUNCIADA")).alias("ATRASO_TSE_MIN")))


def resumo_publicacao(pub: pl.DataFrame) -> pl.DataFrame:
    """Por escopo: totalizações (anúncio × arquivo), quantas receberam primeiro a versão anterior, quantas ficaram sem a
    certa em disco, e a espera até a certa (mediana, p95, máx.), separando as que vieram certas de primeira."""
    base = pub.group_by("ESCOPO").agg(
        pl.len().alias("TOTALIZACOES"), pl.col("VEIO_ANTERIOR_PRIMEIRO").sum().alias("ANTERIOR_PRIMEIRO"),
        pl.col("CHEGADA_CERTA").is_null().sum().alias("SEM_A_CERTA"))
    espera = (pub.drop_nulls("ESPERA_MIN").group_by("ESCOPO", "VEIO_ANTERIOR_PRIMEIRO").agg(_estatisticas("ESPERA_MIN"))
              .sort("ESCOPO", "VEIO_ANTERIOR_PRIMEIRO"))
    return base.join(espera, on="ESCOPO", how="left").sort("ESCOPO", "VEIO_ANTERIOR_PRIMEIRO")


def atraso_tse_por_janela(pub: pl.DataFrame, minutos: int = 30) -> pl.DataFrame:
    """Geração do EA20 certo − hora anunciada, por janela de `minutos` da hora anunciada."""
    return (pub.drop_nulls("ATRASO_TSE_MIN")
            .with_columns(pl.col("DT_ANUNCIADA").dt.truncate(f"{minutos}m").alias("JANELA"))
            .group_by("JANELA").agg(_estatisticas("ATRASO_TSE_MIN")).sort("JANELA"))


def pausas(versoes: pl.DataFrame, minutos: float = 10) -> pl.DataFrame:
    """Intervalos sem novidade maiores que `minutos`: do TSE (gerações sucessivas do acompanhamento) e nossas
    (nenhuma versão gravada). Pausa nossa sem pausa do TSE ao mesmo tempo = coleta parada aqui."""
    def buracos(serie: pl.Series, origem: str) -> list[dict]:
        s = serie.drop_nulls().unique().sort().to_list()
        return [{"ORIGEM": origem, "INICIO": a, "FIM": b, "MINUTOS": round((b - a).total_seconds() / 60, 1)}
                for a, b in zip(s, s[1:]) if (b - a).total_seconds() > minutos * 60]
    tse = buracos(versoes.filter(pl.col("TIPO") == "acompanhamento")["GERADO"], "TSE")
    nossas = buracos(versoes["CHEGADA"], "coleta")
    for p_ in nossas:  # o TSE também parou (≥ 90% do intervalo)? então a pausa não é nossa
        dur = (p_["FIM"] - p_["INICIO"]).total_seconds()
        sobra = sum(max(0.0, (min(t["FIM"], p_["FIM"]) - max(t["INICIO"], p_["INICIO"])).total_seconds()) for t in tse)
        p_["TSE_TAMBEM"] = dur > 0 and sobra >= 0.9 * dur
    return pl.DataFrame(tse + nossas, schema={"ORIGEM": pl.String, "INICIO": pl.Datetime, "FIM": pl.Datetime,
                                               "MINUTOS": pl.Float64, "TSE_TAMBEM": pl.Boolean}).sort("INICIO")


def criterio(pub: pl.DataFrame) -> dict[str, int]:
    """A regra do coletor (`gerado < anunciado` = versão anterior) × o conteúdo: das versões que ela chama de
    anteriores, quantas eram de fato outro conteúdo que a certa (hash diferente); e quantas totalizações tiveram
    a certa reconhecida de primeira (sem anterior antes)."""
    com_certa = pub.filter(pl.col("HASH_CERTO").is_not_null())
    pares = com_certa.select("HASH_CERTO", "HASHES_ANTERIORES").explode("HASHES_ANTERIORES", empty_as_null=True).drop_nulls()
    return {"anteriores_pela_regra": int(pares.height),
            "anteriores_de_conteudo_diferente": int(pares.filter(pl.col("HASHES_ANTERIORES") != pl.col("HASH_CERTO")).height),
            "totalizacoes_com_a_certa": int(com_certa.height),
            "certas_de_primeira": int(com_certa.filter(~pl.col("VEIO_ANTERIOR_PRIMEIRO")).height)}


def peculiaridades(anuncios: pl.DataFrame, pub: pl.DataFrame) -> pl.DataFrame:
    """EA20 certo com dt/ht ANTES da hora anunciada (por cargo; nos de deputado o TSE grava 1–2 min antes) e
    acompanhamentos com hora anunciada depois da própria geração (o EA14 nacional em 4/10)."""
    dt_antes = (pub.drop_nulls("DT_EA20").filter(pl.col("DT_EA20") < pl.col("DT_ANUNCIADA"))
                .group_by("CARGO").agg(pl.len().alias("N"),
                                      _minutos(pl.col("DT_ANUNCIADA") - pl.col("DT_EA20")).max().round(2).alias("MAX_MIN"))
                .with_columns(pl.lit("EA20 com dt antes do anúncio").alias("O_QUE")))
    futuro = (anuncios_distintos(anuncios).filter(pl.col("HORA_NO_FUTURO")).group_by("ESCOPO")
              .agg(pl.len().alias("N"), _minutos(pl.col("DT_ANUNCIADA") - pl.col("GERADO_AB")).max().round(2).alias("MAX_MIN"))
              .with_columns(pl.lit("hora anunciada depois da geração do acompanhamento").alias("O_QUE")))
    return pl.concat([dt_antes.select("O_QUE", pl.col("CARGO").cast(pl.String).alias("ONDE"), "N", "MAX_MIN"),
                      futuro.select("O_QUE", pl.col("ESCOPO").alias("ONDE"), "N", "MAX_MIN")])


def fim_da_noite(versoes: pl.DataFrame, anuncios: pl.DataFrame) -> pl.DataFrame:
    """Por eleição e escopo uf/br: a última totalização e o % em disco (EA20, por cargo) × os anunciados."""
    disco = (versoes.filter((pl.col("TIPO") == "resultado") & pl.col("ESCOPO").is_in(["uf", "br"]))
             .sort("DT_TOTALIZACAO").group_by("ELEICAO", "ESCOPO", "UF", "CARGO")
             .agg(pl.col("DT_TOTALIZACAO").last().alias("DT_DISCO"), pl.col("PCT").last().alias("PCT_DISCO"),
                  pl.col("CHEGADA").last().alias("CHEGADA_ULTIMA")))
    anunciado = (anuncios.filter(pl.col("ESCOPO").is_in(["uf", "br"])).sort("DT_ANUNCIADA")
                 .group_by("ELEICAO", "ESCOPO", "UF").agg(pl.col("DT_ANUNCIADA").last().alias("DT_ANUNCIADA"),
                                                          pl.col("PCT").last().alias("PCT_ANUNCIADO")))
    return disco.join(anunciado, on=["ELEICAO", "ESCOPO", "UF"], how="left").sort("ELEICAO", "ESCOPO", "UF", "CARGO")


def linha_do_tempo(versoes: pl.DataFrame, anuncios: pl.DataFrame, uf: str, cargo: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(% apurado na UF anunciado pelo TSE, na hora da geração do acompanhamento; % do EA20 da UF em disco, na hora
    da chegada) — para o gráfico "TSE × aqui"."""
    tse = (anuncios.filter((pl.col("ESCOPO") == "uf") & (pl.col("UF") == uf.upper())).drop_nulls("GERADO_AB")
           .select(pl.col("GERADO_AB").alias("HORA"), "PCT").unique("HORA").sort("HORA"))
    aqui = (versoes.filter((pl.col("TIPO") == "resultado") & (pl.col("ESCOPO") == "uf") & (pl.col("UF") == uf.upper())
                           & (pl.col("CARGO") == cargo))
            .select(pl.col("CHEGADA").alias("HORA"), "PCT", "GERADO").sort("HORA"))
    if not tse.is_empty() and not aqui.is_empty() and (
            aqui["HORA"].min() > tse["HORA"].max() or aqui["HORA"].max() < tse["HORA"].min()):
        # relógios diferentes (ensaio: geração no relógio de 2022, chegada no real): usa a geração da versão
        aqui = aqui.select(pl.col("GERADO").alias("HORA"), "PCT").sort("HORA").with_columns(
            pl.lit("geração (relógios diferentes)").alias("REFERENCIA"))
    else:
        aqui = aqui.select("HORA", "PCT").with_columns(pl.lit("chegada").alias("REFERENCIA"))
    return tse, aqui
