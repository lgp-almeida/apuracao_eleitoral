"""Resultado por BAIRRO (malha de bairros do IBGE, Censo 2022) a partir dos microdados por seção.

Por que não pelo texto do TSE: o bairro do cadastro de eleitorado é texto livre (no Rio
coincide com o do IBGE em ~83% dos locais). Aqui cada local de votação é posicionado pela
coordenada do cadastro e contado no polígono do bairro que o contém (point-in-polygon).

Cobertura: a malha só existe onde há bairros definidos em lei — no RJ, 31 dos 92
municípios, ~79% do eleitorado. Tempo real do TSE só vai até o município: por bairro só
com os microdados por seção (eleições passadas; 2026 dias depois do pleito).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import eleitorado as el
from apuracao import ibge

logger = logging.getLogger("apuracao.bairros")

SIMPLIFICACAO_GRAUS = 0.0002  # ~20 m: GeoJSON leve para o navegador sem deformar os bairros
CARGOS = {1: "PRESIDENTE", 3: "GOVERNADOR", 5: "SENADOR", 6: "DEPUTADO FEDERAL", 7: "DEPUTADO ESTADUAL",
          8: "DEPUTADO DISTRITAL", 11: "PREFEITO", 13: "VEREADOR"}
PROPORCIONAIS = (6, 7, 8, 13)
ESPECIAIS = (95, 96, 97)
ESPERA_APOS_FALHA_S = 600  # microdados ausentes (ex.: 2026 antes da publicação): tenta de novo só após 10 min
METRICAS = {"vencedor": "Mais votado no bairro", "pct_candidato": "% dos válidos do candidato",
            "votos_candidato": "Votos do candidato", "brancos_nulos_pct": "Brancos + nulos (%)",
            "brancos_pct": "Brancos (%)", "nulos_pct": "Nulos (%)",
            "abstencao_pct": "Abstenção (%)", "comparecimento_pct": "Comparecimento (%)"}
# métricas de participação: vêm do detalhe_votacao_secao (aptos/comparecimento), não dos votos
PARTICIPACAO = {"abstencao_pct": "QT_ABSTENCOES", "comparecimento_pct": "QT_COMPARECIMENTO",
                "abstencao": "QT_ABSTENCOES", "comparecimento": "QT_COMPARECIMENTO"}
# votáveis contados em cada métrica de voto não válido (% sobre o total de votos, como no mapa por município)
NAO_VALIDOS = {"brancos_nulos_pct": [95, 96], "brancos_pct": [95], "nulos_pct": [96],
               "brancos_nulos": [95, 96], "brancos": [95], "nulos": [96]}


# --------------------------------------------------------------------------
# Malha
# --------------------------------------------------------------------------
def malha(uf: str, cache: Path) -> dict[str, Any]:
    """GeoJSON dos bairros da UF (id = CD_BAIRRO), baixado do IBGE uma vez e simplificado."""
    uf = uf.upper()
    destino = cache / "malhas" / f"bairros_{uf}.geojson"
    if not destino.exists():
        import geopandas as gpd

        try:
            zp = ibge.caminho("malha_bairros", cache, uf)
        except v.TseDataError as exc:  # 404: a UF não tem bairros definidos em lei na malha do Censo
            raise v.TseDataError(f"o IBGE não publica malha de bairros para {uf}") from exc
        g = gpd.read_file(f"zip://{zp}").to_crs("EPSG:4326")
        g["geometry"] = g.geometry.simplify(SIMPLIFICACAO_GRAUS, preserve_topology=True)
        g = g[["CD_BAIRRO", "NM_BAIRRO", "CD_MUN", "NM_MUN", "geometry"]].astype(
            {"CD_BAIRRO": str, "CD_MUN": "int64"})
        tmp = destino.with_suffix(".geojson.tmp")
        tmp.write_text(g.to_json(drop_id=True))
        tmp.replace(destino)
    return json.loads(destino.read_text())


def locais_em_bairros(places: pl.DataFrame, geo: dict[str, Any]) -> pl.DataFrame:
    """LOCAL_KEY → CD_BAIRRO/NM_BAIRRO/NM_MUN (só os locais que caem dentro de algum bairro)."""
    import geopandas as gpd

    vazio = pl.DataFrame(schema={**{k: pl.Int64 for k in v.LOCAL_KEY}, "CD_BAIRRO": pl.String,
                                 "NM_BAIRRO_IBGE": pl.String, "NM_MUN_IBGE": pl.String})
    pts = places.filter(pl.col("NR_LATITUDE").is_not_null() & pl.col("NR_LONGITUDE").is_not_null())
    if pts.is_empty() or not geo.get("features"):
        return vazio
    pdf = pts.select(v.LOCAL_KEY + ["NR_LATITUDE", "NR_LONGITUDE"]).to_pandas()
    gp = gpd.GeoDataFrame(pdf, geometry=gpd.points_from_xy(pdf.NR_LONGITUDE, pdf.NR_LATITUDE), crs="EPSG:4326")
    poly = gpd.GeoDataFrame.from_features(geo["features"], crs="EPSG:4326")[["CD_BAIRRO", "NM_BAIRRO", "NM_MUN",
                                                                             "geometry"]]
    j = gpd.sjoin(gp, poly, how="inner", predicate="within").drop_duplicates(subset=v.LOCAL_KEY)
    if j.empty:
        return vazio
    return pl.from_pandas(j[v.LOCAL_KEY + ["CD_BAIRRO", "NM_BAIRRO", "NM_MUN"]]).rename(
        {"NM_BAIRRO": "NM_BAIRRO_IBGE", "NM_MUN": "NM_MUN_IBGE"}).cast({k: pl.Int64 for k in v.LOCAL_KEY})


# --------------------------------------------------------------------------
# Votos por bairro
# --------------------------------------------------------------------------
def votos_por_bairro(votes: pl.LazyFrame, cargo: int, turno: int, local_bairro: pl.DataFrame) -> pl.DataFrame:
    """(CD_BAIRRO, NR_VOTAVEL) -> votos, somando os locais de cada bairro."""
    return (
        votes.filter((pl.col("NR_TURNO") == turno) & v.office_filter(CARGOS[cargo]))
        .group_by(v.LOCAL_KEY + ["NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum(), pl.col("NM_VOTAVEL").first())
        .collect()
        .join(local_bairro, on=v.LOCAL_KEY, how="inner")
        .group_by("CD_BAIRRO", "NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum(), pl.col("NM_VOTAVEL").first())
    )


def participacao_por_bairro(det: pl.LazyFrame, cargo: int, turno: int, local_bairro: pl.DataFrame) -> pl.DataFrame:
    """CD_BAIRRO -> QT_APTOS, QT_COMPARECIMENTO, QT_ABSTENCOES (seções do cargo e turno, somadas por bairro)."""
    qt = ["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]
    return (
        det.filter((pl.col("NR_TURNO") == turno) & (pl.col("CD_CARGO") == cargo))
        .group_by(v.LOCAL_KEY).agg(pl.col(qt).sum())
        .collect()
        .join(local_bairro, on=v.LOCAL_KEY, how="inner")
        .group_by("CD_BAIRRO").agg(pl.col(qt).sum())
    )


def metrica_participacao(pb: pl.DataFrame, metrica_: str) -> pl.DataFrame:
    """CD_BAIRRO, VALOR (% dos aptos), NUM, DEN — abstenção ou comparecimento."""
    return (pb.select("CD_BAIRRO", pl.col(PARTICIPACAO[metrica_]).alias("NUM"), pl.col("QT_APTOS").alias("DEN"))
            .with_columns(pl.when(pl.col("DEN") > 0).then(100 * pl.col("NUM") / pl.col("DEN")).alias("VALOR")))


def metrica(vb: pl.DataFrame, cargo: int, metrica_: str, numero: int | None = None) -> pl.DataFrame:
    """CD_BAIRRO, VALOR[, ROTULO] para a métrica pedida."""
    nominal = ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS) & (
        (pl.col("NR_VOTAVEL") >= 100) if cargo in PROPORCIONAIS else pl.lit(True))
    valido = ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS)
    tot = vb.group_by("CD_BAIRRO").agg(
        pl.col("QT_VOTOS").filter(valido).sum().alias("VALIDOS"),
        pl.col("QT_VOTOS").filter(pl.col("NR_VOTAVEL").is_in(NAO_VALIDOS.get(metrica_, []))).sum().alias("BN"),
        pl.col("QT_VOTOS").sum().alias("APURADOS"))
    if metrica_ in ("brancos_nulos_pct", "brancos_pct", "nulos_pct"):
        return tot.select("CD_BAIRRO", (100 * pl.col("BN") / pl.col("APURADOS")).alias("VALOR"))
    if metrica_ in ("pct_candidato", "votos_candidato"):
        if numero is None:
            raise ValueError("informe o número do candidato")
        c = vb.filter(pl.col("NR_VOTAVEL") == numero).select("CD_BAIRRO", "QT_VOTOS")
        df = tot.join(c, on="CD_BAIRRO", how="left").with_columns(pl.col("QT_VOTOS").fill_null(0))
        valor = (100 * pl.col("QT_VOTOS") / pl.col("VALIDOS")) if metrica_ == "pct_candidato" else pl.col("QT_VOTOS")
        return df.select("CD_BAIRRO", valor.cast(pl.Float64).alias("VALOR"))
    if metrica_ == "vencedor":
        top = (vb.filter(nominal).sort("QT_VOTOS", descending=True).group_by("CD_BAIRRO", maintain_order=True).first()
               .join(tot, on="CD_BAIRRO"))
        return top.select("CD_BAIRRO", pl.col("NR_VOTAVEL").alias("VALOR"),
                          pl.format("{} — {}%", pl.col("NM_VOTAVEL"),
                                    (100 * pl.col("QT_VOTOS") / pl.col("VALIDOS")).round(2)).alias("ROTULO"))
    raise ValueError(f"métrica indisponível por bairro: {metrica_}")


def categorias(vb: pl.DataFrame, cargo: int) -> list[dict[str, Any]]:
    """Mais votados na área coberta pelos bairros (a página colore os 3 primeiros)."""
    nominal = ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS) & (
        (pl.col("NR_VOTAVEL") >= 100) if cargo in PROPORCIONAIS else pl.lit(True))
    top = (vb.filter(nominal).group_by("NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum(), pl.col("NM_VOTAVEL").first())
           .sort("QT_VOTOS", descending=True).head(10))
    return [{"NUMERO": r["NR_VOTAVEL"], "NOME_URNA": r["NM_VOTAVEL"], "PARTIDO": ""} for r in top.iter_rows(named=True)]


# --------------------------------------------------------------------------
# Orquestração (usada pela API, com cache em memória)
# --------------------------------------------------------------------------
class Bairros:
    """Cache em memória: malha, local→bairro por ano e votos por bairro por (ano, cargo, turno)."""

    def __init__(self, uf: str, cache: Path) -> None:
        self.uf, self.cache = uf.upper(), cache
        self._local_bairro: dict[int, pl.DataFrame] = {}
        self._votos: dict[tuple[int, int, int], pl.DataFrame] = {}
        self._participacao: dict[tuple[int, int, int], pl.DataFrame] = {}
        self._falhas: dict[tuple, tuple[float, Exception]] = {}  # não repetir 404 no TSE
        self._geo: dict[str, Any] | None = None
        # a API atende pedidos em paralelo (a página pede dispersão e correlações juntas): sem a trava,
        # dois pedidos convertiam o mesmo ZIP ao mesmo tempo e colidiam nos arquivos temporários
        self.trava = threading.RLock()

    def geo(self) -> dict[str, Any]:
        if self._geo is None:
            self._geo = malha(self.uf, self.cache)
        return self._geo

    def nomes(self) -> dict[str, tuple[str, str]]:
        return {f["properties"]["CD_BAIRRO"]: (f["properties"]["NM_BAIRRO"], f["properties"]["NM_MUN"])
                for f in self.geo()["features"]}

    def local_bairro(self, ano: int) -> pl.DataFrame:
        with self.trava:
            return self._local_bairro_sem_trava(ano)

    def _local_bairro_sem_trava(self, ano: int) -> pl.DataFrame:
        if ano not in self._local_bairro:
            try:
                sec = el.load_sections(ano, self.uf, self.cache)
            except (v.TseDataError, requests.RequestException):
                logger.warning("sem cadastro de eleitorado de %s: coordenadas do cadastro de 2026", ano)
                sec = el.load_sections(2026, self.uf, self.cache)
            self._local_bairro[ano] = locais_em_bairros(el.places(sec), self.geo())
        return self._local_bairro[ano]

    def _carregar(self, chave: tuple, carregar: Any) -> Any:
        """Lê os microdados uma vez; se o TSE não tem o arquivo, a falha vale por 10 min."""
        with self.trava:
            return self._carregar_sem_trava(chave, carregar)

    def _carregar_sem_trava(self, chave: tuple, carregar: Any) -> Any:
        falha = self._falhas.get(chave)
        if falha and time.monotonic() - falha[0] < ESPERA_APOS_FALHA_S:
            raise falha[1]
        try:
            return carregar()
        except (v.TseDataError, requests.RequestException) as exc:
            self._falhas[chave] = (time.monotonic(), exc)
            raise

    def votos(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        with self.trava:
            return self._votos_sem_trava(ano, cargo, turno)

    def _votos_sem_trava(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        chave = (ano, cargo, turno)
        if chave not in self._votos:
            if cargo not in CARGOS:
                raise ValueError(f"cargo desconhecido: {cargo}")
            votes = self._carregar(("votos", ano, cargo),
                                   lambda: v.load_section_votes(ano, self.uf, CARGOS[cargo], self.cache, False))
            self._votos[chave] = votos_por_bairro(votes, cargo, turno, self.local_bairro(ano))
        return self._votos[chave]

    def participacao(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        """Aptos/comparecimento/abstenção por bairro (detalhe_votacao_secao, publicado junto com os votos)."""
        with self.trava:
            return self._participacao_sem_trava(ano, cargo, turno)

    def _participacao_sem_trava(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        chave = (ano, cargo, turno)
        if chave not in self._participacao:
            if cargo not in CARGOS:
                raise ValueError(f"cargo desconhecido: {cargo}")
            det = self._carregar(("detalhe", ano), lambda: v.load_section_details(ano, self.uf, self.cache))
            pb = participacao_por_bairro(det, cargo, turno, self.local_bairro(ano))
            if pb.is_empty():
                raise v.TseDataError(f"sem comparecimento de {CARGOS[cargo].title()} ({turno}º turno) em {ano}")
            self._participacao[chave] = pb
        return self._participacao[chave]

    def anos_disponiveis(self) -> dict[int, list[int]]:
        """Anos com votação por seção da UF no cache e os cargos de cada um (presidente se houver o _BR)."""
        with self.trava:  # pode converter ZIP
            return self._anos_sem_trava()

    def _anos_sem_trava(self) -> dict[int, list[int]]:
        saida: dict[int, list[int]] = {}
        anos = {int(f.name.split("_")[2]) for f in self.cache.glob(f"votacao_secao_*_{self.uf}.zip")}
        anos |= {int(f.name.split("_")[2]) for f in self.cache.glob(f"votacao_secao_*_{self.uf}__{self.uf}.parquet")}
        for ano in sorted(anos):
            try:  # ZIP ainda não convertido: converte agora (uma vez por ano)
                lf = v.load_section_votes(ano, self.uf, "governador", self.cache, False)
            except (v.TseDataError, requests.RequestException) as exc:
                logger.warning("microdados de %s ilegíveis: %s", ano, exc)
                continue
            ds = lf.select("DS_CARGO").unique().collect()["DS_CARGO"].to_list()
            cod = sorted(c for c, n in CARGOS.items() if n in ds)
            tem_br = any(self.cache.glob(f"votacao_secao_{ano}_BR*"))
            saida[ano] = ([1] if tem_br else []) + cod
        return saida


# --------------------------------------------------------------------------
# Comparação entre dois anos por bairro (aba Comparação)
# --------------------------------------------------------------------------
METRICAS_COMPARACAO = {"abstencao": ("Abstenção (%)", "pp"), "comparecimento": ("Comparecimento (%)", "pp"),
                       "brancos_nulos": ("Brancos + nulos (%)", "pp"), "brancos": ("Brancos (%)", "pp"),
                       "nulos": ("Nulos (%)", "pp"), "eleitorado": ("Eleitorado", "var_pct"),
                       "partido": ("% dos válidos do partido", "pp"),
                       "candidato": ("% dos válidos do candidato", "pp")}


def numero_partido(nr: pl.Expr) -> pl.Expr:
    """Nº do partido do votável: o próprio nº (legenda/majoritário de 2 dígitos) ou seus 2 primeiros dígitos."""
    return (pl.when(nr.is_in(ESPECIAIS)).then(None)
            .when(nr < 100).then(nr)
            .otherwise(nr.cast(pl.String).str.slice(0, 2).cast(pl.Int64)))


def valor_por_bairro(vb: pl.DataFrame, cargo: int, metrica_: str, partido: int | None = None,
                     numero: int | None = None) -> pl.DataFrame:
    """CD_BAIRRO, VALOR, NUM, DEN — com numerador/denominador para somar a área coberta (resumo)."""
    valido = ~pl.col("NR_VOTAVEL").is_in(ESPECIAIS)
    if metrica_ in ("brancos_nulos", "brancos", "nulos"):
        num = pl.col("QT_VOTOS").filter(pl.col("NR_VOTAVEL").is_in(NAO_VALIDOS[metrica_])).sum()
        den = pl.col("QT_VOTOS").sum()
    elif metrica_ == "partido":
        if partido is None:
            raise ValueError("informe o partido")
        num = pl.col("QT_VOTOS").filter(numero_partido(pl.col("NR_VOTAVEL")) == partido).sum()
        den = pl.col("QT_VOTOS").filter(valido).sum()
    elif metrica_ == "candidato":
        if numero is None:
            raise ValueError("informe o número do candidato em cada ano")
        num = pl.col("QT_VOTOS").filter(pl.col("NR_VOTAVEL") == numero).sum()
        den = pl.col("QT_VOTOS").filter(valido).sum()
    else:
        raise ValueError(f"métrica indisponível por bairro: {metrica_}")
    return (vb.group_by("CD_BAIRRO").agg(num.alias("NUM"), den.alias("DEN"))
            .with_columns(pl.when(pl.col("DEN") > 0).then(100 * pl.col("NUM") / pl.col("DEN")).alias("VALOR")))


class ComparacaoBairros:
    """Dois anos (e cargos) por bairro, sobre o mesmo cache de `Bairros`."""

    def __init__(self, bairros: Bairros) -> None:
        self.b = bairros
        self._siglas: dict[int, dict[int, str]] = {}

    def eleitorado(self, ano: int) -> pl.DataFrame:
        """CD_BAIRRO, VALOR (= eleitores do cadastro daquele ano nos locais do bairro), NUM, DEN."""
        sec = el.load_sections(ano, self.b.uf, self.b.cache)
        pl_ = el.places(sec).select(v.LOCAL_KEY + ["QT_ELEITORES"])
        return (pl_.join(self.b.local_bairro(ano), on=v.LOCAL_KEY, how="inner")
                .group_by("CD_BAIRRO").agg(pl.col("QT_ELEITORES").sum().cast(pl.Float64).alias("VALOR"))
                .with_columns(pl.col("VALOR").alias("NUM"), pl.lit(1.0).alias("DEN")))

    def siglas(self, ano: int) -> dict[int, str]:
        """Nº do partido -> sigla naquele ano (cadastro de candidatos do TSE; vazio se indisponível)."""
        if ano not in self._siglas:
            from apuracao import historico as h
            try:
                cand = h.load_candidatos(ano, self.b.cache)
                pares = (cand.select(pl.col("NR_PARTIDO").cast(pl.Int64, strict=False), "SG_PARTIDO")
                         .drop_nulls().unique(subset=["NR_PARTIDO"], keep="first"))
                self._siglas[ano] = dict(pares.iter_rows())
            except (v.TseDataError, requests.RequestException) as exc:
                logger.warning("sem cadastro de candidatos de %s para as siglas: %s", ano, exc)
                self._siglas[ano] = {}
        return self._siglas[ano]

    def lado(self, ano: int, cargo: int, metrica_: str, partido: int | None, numero: int | None,
             turno: int) -> pl.DataFrame:
        if metrica_ == "eleitorado":
            return self.eleitorado(ano)
        if metrica_ in PARTICIPACAO:
            return metrica_participacao(self.b.participacao(ano, cargo, turno), metrica_)
        return valor_por_bairro(self.b.votos(ano, cargo, turno), cargo, metrica_, partido, numero)

    def comparar(self, ano_a: int, cargo_a: int, ano_b: int, cargo_b: int, metrica_: str,
                 partido: int | None = None, numero_a: int | None = None, numero_b: int | None = None,
                 turno: int = 1) -> tuple[pl.DataFrame, dict[str, float | None]]:
        """(uma linha por bairro com VALOR_A, VALOR_B, DIF; resumo da área coberta)."""
        if metrica_ not in METRICAS_COMPARACAO:
            raise ValueError(f"métrica indisponível por bairro: {metrica_}")
        a = self.lado(ano_a, cargo_a, metrica_, partido, numero_a, turno)
        b = self.lado(ano_b, cargo_b, metrica_, partido, numero_b, turno)
        var_pct = METRICAS_COMPARACAO[metrica_][1] == "var_pct"
        df = (a.select("CD_BAIRRO", pl.col("VALOR").alias("VALOR_A"))
              .join(b.select("CD_BAIRRO", pl.col("VALOR").alias("VALOR_B")), on="CD_BAIRRO", how="full", coalesce=True)
              .with_columns(pl.when(pl.col("VALOR_A").is_not_null() & pl.col("VALOR_B").is_not_null())
                            .then(((pl.col("VALOR_B") - pl.col("VALOR_A")) / pl.col("VALOR_A") * 100) if var_pct
                                  else (pl.col("VALOR_B") - pl.col("VALOR_A")))
                            .alias("DIF")))

        def total(x: pl.DataFrame) -> float | None:
            num, den = x["NUM"].sum(), x["DEN"].sum()
            return float(num) if var_pct else (100 * num / den if den else None)

        ta, tb = total(a), total(b)
        dif = None if ta is None or tb is None else ((tb - ta) / ta * 100 if var_pct and ta else tb - ta)
        return df, {"VALOR_A": ta, "VALOR_B": tb, "DIF": dif}

    def partidos(self, ano_a: int, cargo_a: int, ano_b: int, cargo_b: int, turno: int = 1) -> pl.DataFrame:
        """Partidos (por NÚMERO, estável entre eleições) com votos em cada ano e a sigla de cada ano."""
        def votos(ano: int, cargo: int, sufixo: str) -> pl.DataFrame:
            try:
                vb = self.b.votos(ano, cargo, turno)
            except (v.TseDataError, requests.RequestException):
                return pl.DataFrame(schema={"PARTIDO": pl.Int64, f"VOTOS_{sufixo}": pl.Int64})
            return (vb.with_columns(numero_partido(pl.col("NR_VOTAVEL")).alias("PARTIDO")).drop_nulls("PARTIDO")
                    .group_by("PARTIDO").agg(pl.col("QT_VOTOS").sum().alias(f"VOTOS_{sufixo}")))
        sa, sb = self.siglas(ano_a), self.siglas(ano_b)
        return (votos(ano_a, cargo_a, "A").join(votos(ano_b, cargo_b, "B"), on="PARTIDO", how="full", coalesce=True)
                .with_columns(pl.col("PARTIDO").replace_strict(sa, default=None, return_dtype=pl.String).alias("SIGLA_A"),
                              pl.col("PARTIDO").replace_strict(sb, default=None, return_dtype=pl.String).alias("SIGLA_B"),
                              (pl.col("VOTOS_A").is_not_null() & pl.col("VOTOS_B").is_not_null()).alias("NOS_DOIS"))
                .sort(["NOS_DOIS", "VOTOS_B", "VOTOS_A"], descending=True, nulls_last=True))

    def anos_cadastro(self) -> list[int]:
        """Anos com cadastro de eleitorado no cache (métrica eleitorado não depende de votos)."""
        return sorted({int(f.name.split("_")[3].split(".")[0]) for f in self.b.cache.glob(
            "eleitorado_local_votacao_*.zip")})
