"""Perfil × voto por LOCAL DE VOTAÇÃO no estado inteiro (item 5 do TODO).

A malha de bairros do IBGE cobre só 31 dos 92 municípios do RJ (79% do eleitorado). Os SETORES
censitários do Censo 2022 cobrem o estado todo: aqui cada local de votação recebe os setores do seu
entorno, e o Perfil × voto passa a ter uma unidade mais fina e sem buracos — o local.

Setores (IBGE, Censo 2022): malha `RJ_setores_CD2022.zip` (geoftp) + agregados por setor (básico,
renda do responsável, cor ou raça). "X" = sigilo: o setor sai da soma DAQUELE indicador (nunca vira 0).
O arquivo de renda por setor usa ponto decimal; o de bairro, vírgula — `_num` aceita os dois.

Ligação setor → local (`METODOS`), escolhida por validação (rodada 26):
- "contem":     o setor que contém o ponto do local;
- "raio":       os setores com centro a até `RAIO_M` do local;
- "influencia": cada setor vai para o local mais próximo do MESMO município (área de influência,
                como um Voronoi): cada setor conta uma vez e o estado inteiro é coberto;
- "raio+contem": raio de 800 m e, para os locais sem setor no raio (área rural), o setor que contém
                o local — o PADRÃO: 100% dos locais e a correspondência mais forte.
Critério: o perfil de quem vota no local (TSE: % com superior completo) deve concordar com o do
entorno medido pelo IBGE (renda, cor); a ligação geograficamente melhor dá correlação mais forte.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

import votos_por_local_votacao as v
from apuracao import censo as cs
from apuracao import eleitorado as el
from apuracao import ibge
from apuracao import perfil as pf

logger = logging.getLogger("apuracao.perfil_local")

AGREGADOS_SETOR = {"basico": "setores_basico", "renda": "setores_renda", "cor": "setores_cor",
                   "demografia": "setores_demografia"}  # apuracao.ibge.FONTES
# contagens de sexo e idade por setor (`pf.DEMOGRAFIA`): MORADORES_DEM = V01006, o denominador
DEMOGRAFIA_SETOR = {"MORADORES_DEM": [pf.DEMOGRAFIA_TOTAL], "MULHERES": pf.DEMOGRAFIA["pct_mulheres_censo"],
                    "IDADE_0_14": pf.DEMOGRAFIA["pct_0_14_censo"], "IDADE_15_24": pf.DEMOGRAFIA["pct_15_24_censo"],
                    "IDADE_60_MAIS": pf.DEMOGRAFIA["pct_60_mais_censo"]}
METODOS = ("contem", "raio", "influencia", "raio+contem")
METODO_PADRAO = "raio+contem"  # vencedor da validação (rodada 26): raio de 800 m; sem setor no raio, o que contém
RAIO_M = 800.0
INDICADORES_CENSO_LOCAL = pf.INDICADORES_CENSO | {"pct_favela": "% de moradores em favela ou comunidade urbana"}


def _num(col: str) -> pl.Expr:
    """Número do IBGE com vírgula OU ponto decimal; "X"/"." (sigilo) → nulo."""
    return pl.col(col).str.strip_chars().str.replace(",", ".").cast(pl.Float64, strict=False)


def _baixar(fonte: str, cache: Path, uf: str) -> Path:
    """ZIP do IBGE em cache (versão mais nova; baixa se faltar) — catálogo em `apuracao.ibge`."""
    return ibge.caminho(fonte, cache, uf)


def _ler_setores_csv(zp: Path, prefixo: str, colunas: list[str]) -> pl.DataFrame:
    """Só as linhas da UF: o CSV é nacional (a alfabetização passa de 1 GB descomprimida), então é lido em
    STREAMING, linha a linha, filtrando pelo prefixo do CD_SETOR (com ou sem aspas). Coluna pedida que não
    existe no arquivo fica de fora (quem usa trata como sem dado)."""
    with zipfile.ZipFile(zp) as z:
        membro = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(membro) as bruto:
            texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
            linhas = [next(texto)] + [ln for ln in texto if ln.lstrip('"')[:2] == prefixo]
    df = pl.read_csv(io.StringIO("".join(linhas)), separator=";", infer_schema=False)
    df = df.rename({c: c.upper() for c in df.columns})
    if "CD_SETOR" not in df.columns and "SETOR" in df.columns:  # o domicílio 2 chama a chave de "setor"
        df = df.rename({"SETOR": "CD_SETOR"})
    pedidas = list(dict.fromkeys(c.upper() for c in colunas))  # sem repetição (o catálogo também pede V0001)
    faltam = [c for c in pedidas if c not in df.columns]
    if faltam:
        logger.warning("%s sem as colunas %s", zp.name, ", ".join(faltam))
    return df.select([c for c in pedidas if c in df.columns])


def _pontos(g) -> pl.DataFrame:
    """Malha de setores → CD_SETOR, CD_MUN, CD_BAIRRO (nulo onde o IBGE não tem bairro), LON, LAT (ponto
    representativo, WGS 84). Setor sem município sai: no RS, a Lagoa dos Patos e a Lagoa Mirim são setores sem
    CD_MUN (e sem população)."""
    g = g[g["CD_MUN"].notna()].to_crs("EPSG:4326")
    pt = g.geometry.representative_point()
    bairro = ([None if b is None or b != b else str(b) for b in g["CD_BAIRRO"]] if "CD_BAIRRO" in g.columns
              else [None] * len(g))  # b != b: NaN
    return pl.DataFrame({"CD_SETOR": g["CD_SETOR"].astype(str).to_list(), "CD_MUN": g["CD_MUN"].astype(int).to_list(),
                         "CD_BAIRRO": pl.Series(bairro, dtype=pl.String),
                         "LON": pt.x.to_numpy(), "LAT": pt.y.to_numpy()})


def setores(uf: str, cache: Path) -> pl.DataFrame:
    """Um setor por linha: CD_SETOR, CD_MUN (IBGE), LON, LAT (ponto representativo), TIPO, AREA_KM2,
    POP, DOMICILIOS, MORADORES_DOM, RESP (responsáveis com renda), RENDA_MEDIA, RENDA_MEDIANA,
    BRANCOS…INDIGENAS (cor ou raça), MORADORES_DEM, MULHERES, IDADE_0_14, IDADE_15_24, IDADE_60_MAIS (sexo e
    idade), CD_BAIRRO e N_<chave>/D_<chave> do catálogo `apuracao.censo` (rodada 49).
    Cache: ibge_censo2022/censo_setores_<UF>.parquet (refeito se gravado antes de uma coluna nova)."""
    destino = cache / "ibge_censo2022" / f"censo_setores_{uf.upper()}.parquet"
    if destino.exists():
        df = pl.read_parquet(destino)
        if set(DEMOGRAFIA_SETOR) | set(cs.COLUNAS) | {"CD_BAIRRO"} <= set(df.columns):
            return df
        logger.info("%s sem colunas novas: refazendo", destino.name)
    import geopandas as gpd

    prefixo = str(pf.UF_IBGE[uf.upper()])
    malha = _baixar("malha_setores", cache, uf)
    geo = _pontos(gpd.read_file(f"zip://{malha}", columns=["CD_SETOR", "CD_MUN", "CD_BAIRRO"]))
    b = _ler_setores_csv(_baixar(AGREGADOS_SETOR["basico"], cache, uf), prefixo,
                         ["CD_SETOR", "CD_TIPO", "AREA_KM2", "v0001", "v0005", "v0007",
                          *cs.colunas_por_fonte().get(AGREGADOS_SETOR["basico"], [])])
    r = _ler_setores_csv(_baixar(AGREGADOS_SETOR["renda"], cache, uf), prefixo, ["CD_SETOR", "V06001", "V06004", "V06006"])
    c = _ler_setores_csv(_baixar(AGREGADOS_SETOR["cor"], cache, uf), prefixo,
                         ["CD_SETOR", "V01317", "V01318", "V01319", "V01320", "V01321"])
    d = _ler_setores_csv(_baixar(AGREGADOS_SETOR["demografia"], cache, uf), prefixo,
                         ["CD_SETOR", *sorted({x for cols in DEMOGRAFIA_SETOR.values() for x in cols})])
    df = (geo.join(b.select("CD_SETOR", _num("CD_TIPO").cast(pl.Int64).alias("TIPO"), _num("AREA_KM2").alias("AREA_KM2"),
                            _num("V0001").alias("POP"), _num("V0005").alias("MORADORES_DOM"),
                            _num("V0007").alias("DOMICILIOS")), on="CD_SETOR", how="left")
          .join(r.select("CD_SETOR", _num("V06001").alias("RESP"), _num("V06004").alias("RENDA_MEDIA"),
                         _num("V06006").alias("RENDA_MEDIANA")), on="CD_SETOR", how="left")
          .join(c.select("CD_SETOR", _num("V01317").alias("BRANCOS"), _num("V01318").alias("PRETOS"),
                         _num("V01319").alias("AMARELOS"), _num("V01320").alias("PARDOS"),
                         _num("V01321").alias("INDIGENAS")), on="CD_SETOR", how="left")
          .join(d.select("CD_SETOR", *[sum(_num(x) for x in cols).alias(k)  # um "X" (sigilo) → nulo
                                       for k, cols in DEMOGRAFIA_SETOR.items()]), on="CD_SETOR", how="left"))
    brutos = geo.select("CD_SETOR")  # catálogo de contagens: as colunas de cada fonte, juntas por setor
    for fonte, cols in cs.colunas_por_fonte().items():
        quadro = b if fonte == AGREGADOS_SETOR["basico"] else _ler_setores_csv(_baixar(fonte, cache, uf), prefixo,
                                                                               ["CD_SETOR", *cols])
        brutos = brutos.join(quadro.select("CD_SETOR", *[c for c in cols if c in quadro.columns]
                                           ).unique("CD_SETOR"), on="CD_SETOR", how="left")
    df = df.join(cs.contagens(brutos), on="CD_SETOR", how="left")
    tmp = destino.with_suffix(".parquet.tmp")
    df.write_parquet(tmp)
    tmp.replace(destino)
    return df


# --------------------------------------------------------------------------
# Locais de votação e ligação com os setores
# --------------------------------------------------------------------------
def locais(ano: int, uf: str, cache: Path) -> pl.DataFrame:
    """Locais com coordenada: LOCAL_KEY, NM_LOCAL_VOTACAO, NM_MUN, CD_MUN (IBGE), QT_ELEITORES, LAT, LON, UNIDADE.
    UNIDADE = IBGE do município (7) + zona (4) + local (5): os 7 primeiros dígitos são o município,
    como no CD_BAIRRO — o filtro por município e a regra de ausência de candidatura valem igual."""
    from apuracao import historico as h
    sec = el.load_sections(ano, uf, cache)
    p = el.places(sec).filter(pl.col("NR_LATITUDE").is_not_null() & pl.col("NR_LONGITUDE").is_not_null())
    muns = h.municipios_tse_ibge(uf, cache).select("CD_MUNICIPIO", pl.col("CD_MUNICIPIO_IBGE").alias("CD_MUN"),
                                                   pl.col("NM_MUNICIPIO").alias("NM_MUN"))
    return (p.join(muns, on="CD_MUNICIPIO", how="inner")
            .select(v.LOCAL_KEY + ["NM_LOCAL_VOTACAO", "NM_MUN", "CD_MUN", "QT_ELEITORES",
                                   pl.col("NR_LATITUDE").alias("LAT"), pl.col("NR_LONGITUDE").alias("LON")])
            .with_columns(pl.format("{}{}{}", pl.col("CD_MUN"), pl.col("NR_ZONA").cast(pl.String).str.zfill(4),
                                    pl.col("NR_LOCAL_VOTACAO").cast(pl.String).str.zfill(5)).alias("UNIDADE"))
            .unique("UNIDADE"))


UTM = "EPSG:31983"  # SIRGAS 2000 / UTM 23S: metros no RJ


def ligar(uf: str, cache: Path, locais_: pl.DataFrame, metodo: str, raio_m: float = RAIO_M) -> pl.DataFrame:
    """CD_SETOR → UNIDADE (no método "raio" um setor pode ir para mais de um local)."""
    import geopandas as gpd

    if metodo not in METODOS:
        raise ValueError(f"método de ligação desconhecido: {metodo}")
    if metodo == "raio+contem":
        raio = ligar(uf, cache, locais_, "raio", raio_m)
        contem = ligar(uf, cache, locais_, "contem")
        return pl.concat([raio, contem.filter(~pl.col("UNIDADE").is_in(raio["UNIDADE"].unique().to_list()))])
    pts = gpd.GeoDataFrame(locais_.select("UNIDADE", "CD_MUN").to_pandas(),
                           geometry=gpd.points_from_xy(locais_["LON"].to_numpy(), locais_["LAT"].to_numpy()),
                           crs="EPSG:4326").to_crs(UTM)
    if metodo == "contem":
        malha = _baixar("malha_setores", cache, uf)
        pol = gpd.read_file(f"zip://{malha}", columns=["CD_SETOR"]).to_crs(UTM)
        j = gpd.sjoin(pts, pol, how="inner", predicate="within").drop_duplicates("UNIDADE")
        return pl.DataFrame({"CD_SETOR": j["CD_SETOR"].astype(str).to_list(), "UNIDADE": j["UNIDADE"].to_list()})
    st = setores(uf, cache)
    cen = gpd.GeoDataFrame(st.select("CD_SETOR", "CD_MUN").to_pandas(),
                           geometry=gpd.points_from_xy(st["LON"].to_numpy(), st["LAT"].to_numpy()),
                           crs="EPSG:4326").to_crs(UTM)
    if metodo == "raio":
        buf = pts.copy()
        buf["geometry"] = buf.geometry.buffer(raio_m)
        j = gpd.sjoin(cen, buf[["UNIDADE", "geometry"]], how="inner", predicate="within")
        return pl.DataFrame({"CD_SETOR": j["CD_SETOR"].astype(str).to_list(), "UNIDADE": j["UNIDADE"].to_list()})
    partes = []  # influência: o local mais próximo DO MESMO MUNICÍPIO
    for mun, grupo in cen.groupby("CD_MUN"):
        alvo = pts[pts["CD_MUN"] == mun]
        if alvo.empty:
            continue
        j = gpd.sjoin_nearest(grupo, alvo[["UNIDADE", "geometry"]], how="inner").drop_duplicates("CD_SETOR")
        partes.append(pl.DataFrame({"CD_SETOR": j["CD_SETOR"].astype(str).to_list(), "UNIDADE": j["UNIDADE"].to_list()}))
    return pl.concat(partes)


def agregar(setores_: pl.DataFrame, ligacao: pl.DataFrame) -> pl.DataFrame:
    """Indicadores do Censo por UNIDADE (local), somando os setores ligados a ela.
    Renda: média dos setores ponderada pelos responsáveis com renda; mediana: idem (aproximação);
    cor e sexo/idade: soma das contagens dos setores SEM sigilo; densidade: moradores ÷ área somadas."""
    cores = ["BRANCOS", "PRETOS", "AMARELOS", "PARDOS", "INDIGENAS"]
    dem_ok = pl.all_horizontal([pl.col(c).is_not_null() for c in DEMOGRAFIA_SETOR])
    dem = lambda c: (100 * pl.col(c).filter(dem_ok).sum() / pl.col("MORADORES_DEM").filter(dem_ok).sum())  # noqa: E731
    s = setores_.join(ligacao, on="CD_SETOR", how="inner").with_columns(
        pl.all_horizontal([pl.col(c).is_not_null() for c in cores]).alias("_COR_OK"),
        (pl.col("TIPO") == 1).alias("_FAVELA"))
    return s.group_by("UNIDADE").agg(
        ((pl.col("RENDA_MEDIA") * pl.col("RESP")).sum() / pl.col("RESP").filter(pl.col("RENDA_MEDIA").is_not_null()).sum())
        .alias("renda_media"),
        ((pl.col("RENDA_MEDIANA") * pl.col("RESP")).sum() / pl.col("RESP").filter(pl.col("RENDA_MEDIANA").is_not_null()).sum())
        .alias("renda_mediana"),
        (100 * (pl.col("PRETOS") + pl.col("PARDOS")).filter(pl.col("_COR_OK")).sum()
         / pl.sum_horizontal(cores).filter(pl.col("_COR_OK")).sum()).alias("pct_pretos_pardos"),
        (pl.col("POP").sum() / pl.col("AREA_KM2").sum()).alias("densidade"),
        ((pl.col("MORADORES_DOM") * pl.col("DOMICILIOS")).sum() / pl.col("DOMICILIOS").filter(
            pl.col("MORADORES_DOM").is_not_null()).sum()).alias("moradores_domicilio"),
        (100 * pl.col("POP").filter(pl.col("_FAVELA")).sum() / pl.col("POP").sum()).alias("pct_favela"),
        dem("MULHERES").alias("pct_mulheres_censo"), dem("IDADE_0_14").alias("pct_0_14_censo"),
        dem("IDADE_15_24").alias("pct_15_24_censo"), dem("IDADE_60_MAIS").alias("pct_60_mais_censo"),
        *[cs.taxa(k) for k in cs.INDICADORES],  # catálogo de contagens (rodada 49)
        pl.len().alias("SETORES"), pl.col("POP").sum().alias("MORADORES"),
    ).with_columns([pl.when(pl.col(c).is_finite()).then(pl.col(c)).alias(c)
                    for c in ("renda_media", "renda_mediana", "pct_pretos_pardos", "densidade", "moradores_domicilio",
                              "pct_favela", "pct_mulheres_censo", "pct_0_14_censo", "pct_15_24_censo",
                              "pct_60_mais_censo")])


def perfil_tse_por_local(perfil_lf: pl.LazyFrame, locais_: pl.DataFrame) -> pl.DataFrame:
    """Indicadores do TSE (eleitores inscritos) por UNIDADE."""
    q = pl.col("QT_ELEITORES_PERFIL")
    por_local = (perfil_lf.group_by(v.LOCAL_KEY)
                 .agg(q.sum().alias("ELEITORES"), *[q.filter(f).sum().alias(k) for k, (_, f) in pf.INDICADORES_TSE.items()])
                 .collect())
    return (por_local.join(locais_.select(v.LOCAL_KEY + ["UNIDADE"]), on=v.LOCAL_KEY, how="inner")
            .select("UNIDADE", "ELEITORES", *[(100 * pl.col(k) / pl.col("ELEITORES")).alias(k) for k in pf.INDICADORES_TSE]))


def validar_metodos(ano: int, uf: str, cache: Path) -> pl.DataFrame:
    """Para cada método de ligação: cobertura e correlação entre o perfil dos ELEITORES do local (TSE)
    e o do ENTORNO (IBGE). Ligação melhor → correspondência mais forte."""
    loc = locais(ano, uf, cache)
    tse = perfil_tse_por_local(pf.load_perfil(ano, uf, cache), loc).filter(pl.col("ELEITORES") >= 200)
    st = setores(uf, cache)
    linhas = []
    pares = [("pct_superior", "renda_media"), ("pct_superior", "renda_mediana"),
             ("pct_sem_fundamental", "renda_media"), ("pct_superior", "pct_pretos_pardos")]
    for metodo in METODOS:
        lig = ligar(uf, cache, loc, metodo)
        ag = agregar(st, lig)
        j = tse.join(ag, on="UNIDADE", how="inner")
        linha = {"METODO": metodo, "LOCAIS": j.height, "DE": tse.height,
                 "SETORES_USADOS": lig["CD_SETOR"].n_unique(), "SETORES_TOTAL": st.height}
        for a, b in pares:
            x = j.select(a, pl.col(b).log() if b.startswith("renda") else pl.col(b)).drop_nulls()
            linha[f"{a}×{b}"] = pf.correlacao(x[a], x[x.columns[1]])["pearson"]
        linhas.append(linha)
    return pl.DataFrame(linhas)


# --------------------------------------------------------------------------
# Perfil × voto com o LOCAL como unidade
# --------------------------------------------------------------------------
class PerfilVotoLocal(pf.PerfilVoto):
    """Como `PerfilVoto`, mas a unidade é o local de votação (estado inteiro). A chave CD_BAIRRO guarda
    a UNIDADE do local (IBGE do município + zona + local)."""

    CENSO = INDICADORES_CENSO_LOCAL
    UNIDADE = "local"

    def __init__(self, comp, metodo: str = METODO_PADRAO) -> None:
        super().__init__(comp)
        self.metodo = metodo
        self._locais: dict[int, pl.DataFrame] = {}
        self._votos: dict[tuple[int, int, int], pl.DataFrame] = {}
        self._censo_ano: dict[int, pl.DataFrame] = {}

    def locais(self, ano: int) -> pl.DataFrame:
        with self.b.trava:
            if ano not in self._locais:
                self._locais[ano] = self.b._carregar(("locais", ano), lambda: locais(ano, self.b.uf, self.b.cache))
            return self._locais[ano]

    def _vb(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        from apuracao import bairros as br
        chave = (ano, cargo, turno)
        with self.b.trava:
            if chave not in self._votos:
                if cargo not in br.CARGOS:
                    raise ValueError(f"cargo desconhecido: {cargo}")
                lf = self.b._carregar(("votos", ano, cargo),
                                      lambda: v.load_section_votes(ano, self.b.uf, br.CARGOS[cargo], self.b.cache, False))
                por_local = (lf.filter((pl.col("NR_TURNO") == turno) & v.office_filter(br.CARGOS[cargo]))
                             .group_by(v.LOCAL_KEY + ["NR_VOTAVEL"])
                             .agg(pl.col("QT_VOTOS").sum(), pl.col("NM_VOTAVEL").first()).collect())
                self._votos[chave] = (por_local.join(self.locais(ano).select(v.LOCAL_KEY + ["UNIDADE"]),
                                                     on=v.LOCAL_KEY, how="inner")
                                      .select(pl.col("UNIDADE").alias("CD_BAIRRO"), "NR_VOTAVEL", "QT_VOTOS", "NM_VOTAVEL"))
            return self._votos[chave]

    def _nomes(self) -> dict[str, tuple[str, str]]:
        nomes: dict[str, tuple[str, str]] = {}
        for loc in list(self._locais.values()):
            nomes.update({u: (n, m) for u, n, m in loc.select("UNIDADE", "NM_LOCAL_VOTACAO", "NM_MUN").iter_rows()})
        return nomes

    def perfil(self, ano: int) -> pl.DataFrame:
        with self.b.trava:
            if ano not in self._perfil:
                lf = self.b._carregar(("perfil", ano), lambda: pf.load_perfil(ano, self.b.uf, self.b.cache))
                self._perfil[ano] = perfil_tse_por_local(lf, self.locais(ano)).rename({"UNIDADE": "CD_BAIRRO"})
            return self._perfil[ano]

    def censo_local(self, ano: int) -> pl.DataFrame:
        """Indicadores do Censo 2022 por local (setores ligados pelo método escolhido)."""
        with self.b.trava:
            if ano not in self._censo_ano:
                st = self.b._carregar(("setores",), lambda: setores(self.b.uf, self.b.cache))
                lig = ligar(self.b.uf, self.b.cache, self.locais(ano), self.metodo)
                self._censo_ano[ano] = agregar(st, lig).rename({"UNIDADE": "CD_BAIRRO"})
            return self._censo_ano[ano]

    def indicador(self, chave: str, ano: int) -> pl.DataFrame:
        if chave in self.CENSO:
            return self.censo_local(ano).select("CD_BAIRRO", pl.col(chave).alias("X"))
        return super().indicador(chave, ano)

    def municipios(self) -> pl.DataFrame:
        """Todos os municípios da UF, com o número de locais de votação com coordenada (cadastro de 2026)."""
        anos = sorted(self._locais) or [2026]
        loc = self.locais(anos[-1])
        return (loc.group_by(pl.col("CD_MUN").cast(pl.Int64), pl.col("NM_MUN")).len("BAIRROS").sort("NM_MUN"))
