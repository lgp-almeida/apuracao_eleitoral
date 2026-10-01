"""Perfil do eleitorado × voto por BAIRRO: correlação e transferência entre eleições.

Duas fontes de perfil, as duas já no recorte de bairro do IBGE (Censo 2022):

- TSE, `perfil_eleitor_secao_<ano>_<UF>`: eleitores INSCRITOS em cada seção por escolaridade, faixa
  etária e gênero. Somado pelos locais de votação que caem em cada bairro (mesma ponte local → bairro
  dos votos), descreve exatamente o eleitorado que votou ali. Raça/cor fica de fora: vazia até 2024 e,
  em 2026, 83% "não informado" (autodeclaração recente e parcial = amostra enviesada).
- IBGE, agregados do Censo 2022 por bairro (`CD_BAIRRO`, o mesmo da malha): renda do responsável,
  cor ou raça, densidade e moradores por domicílio. Descreve os MORADORES do bairro (não os eleitores).

Voto: % dos válidos de um candidato ou partido (nº, estável entre eleições) no bairro, dos microdados
por seção. X também pode ser o voto em OUTRA eleição (transferência 2022 → 2024, por exemplo).

Estatística (numpy, sem scipy): Pearson (opcionalmente ponderado pelos votos válidos do bairro),
Spearman (postos médios), IC 95% e p-valor pela transformação z de Fisher (aproximação normal; o
n efetivo de Kish entra quando há peso), reta de mínimos quadrados e resíduos. É correlação
ECOLÓGICA: associação entre bairros, não comportamento de indivíduos.
"""

from __future__ import annotations

import io
import logging
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import bairros as br

logger = logging.getLogger("apuracao.perfil")


class FonteIndisponivel(v.TseDataError):
    """Arquivo do TSE/IBGE ausente ou ilegível (vira HTTP 404 na API)."""


# --------------------------------------------------------------------------
# Perfil do eleitorado (TSE)
# --------------------------------------------------------------------------
PERFIL_WANTED = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "CD_GENERO",
                 "CD_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE",
                 "QT_ELEITORES_PERFIL", "QT_ELEITORES"]  # a contagem mudou de nome em 2026
PERFIL_REQUIRED = ["NR_ZONA", "NR_LOCAL_VOTACAO", "CD_GENERO", "CD_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE"]

# códigos do TSE: escolaridade 1 analfabeto, 2 lê e escreve, 3 fundamental incompleto … 8 superior
# completo; faixa etária AABB (1600 = 16 anos, 2124 = 21 a 24, 6064 = 60 a 64, 9999 = 100 ou mais);
# gênero 2 masculino, 4 feminino
INDICADORES_TSE: dict[str, tuple[str, pl.Expr]] = {
    "pct_superior": ("% com superior completo", pl.col("CD_GRAU_ESCOLARIDADE") == 8),
    "pct_sem_fundamental": ("% sem fundamental completo", pl.col("CD_GRAU_ESCOLARIDADE").is_in([1, 2, 3])),
    "pct_16_24": ("% de 16 a 24 anos", pl.col("CD_FAIXA_ETARIA") <= 2124),
    "pct_60_mais": ("% com 60 anos ou mais", pl.col("CD_FAIXA_ETARIA") >= 6064),
    "pct_mulheres": ("% de mulheres", pl.col("CD_GENERO") == 4),
}


def perfil_spec(ano: int, uf: str) -> v.DatasetSpec:
    nome = f"perfil_eleitor_secao_{ano}_{uf.upper()}"
    return v.DatasetSpec(nome, f"{v.CDN_BASE}/perfil_eleitor_secao/{nome}.zip", uf.upper())


def load_perfil(ano: int, uf: str, cache: Path) -> pl.LazyFrame:
    """Eleitores por seção e perfil (só a UF), com a contagem sempre em QT_ELEITORES_PERFIL."""
    spec = perfil_spec(ano, uf)
    pq = v.zip_to_parquet(v.download(spec, cache), spec, PERFIL_WANTED, PERFIL_REQUIRED, cache)
    lf = pl.scan_parquet(pq)
    if "QT_ELEITORES" in lf.collect_schema().names():
        lf = lf.rename({"QT_ELEITORES": "QT_ELEITORES_PERFIL"})
    return lf


def perfil_por_bairro(perfil: pl.LazyFrame, local_bairro: pl.DataFrame) -> pl.DataFrame:
    """CD_BAIRRO, ELEITORES e um % por indicador (eleitores inscritos nos locais do bairro)."""
    q = pl.col("QT_ELEITORES_PERFIL")
    por_local = (perfil.group_by(v.LOCAL_KEY)
                 .agg(q.sum().alias("ELEITORES"), *[q.filter(f).sum().alias(k) for k, (_, f) in INDICADORES_TSE.items()])
                 .collect())
    soma = por_local.join(local_bairro, on=v.LOCAL_KEY, how="inner").group_by("CD_BAIRRO").agg(
        pl.col(["ELEITORES", *INDICADORES_TSE]).sum())
    return soma.with_columns([(100 * pl.col(k) / pl.col("ELEITORES")).alias(k) for k in INDICADORES_TSE])


# --------------------------------------------------------------------------
# Censo 2022 por bairro (IBGE)
# --------------------------------------------------------------------------
CENSO_BASE = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022"
CENSO_ARQUIVOS = {  # o IBGE põe a data da versão no nome; se republicar, atualize aqui
    "renda": "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
             "Agregados_por_bairros_renda_responsavel_BR_20260508_csv.zip",
    "basico": "Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/Agregados_por_bairros_basico_BR_20260520.zip",
    "cor": "Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/Agregados_por_bairros_cor_ou_raca_BR.zip",
}
INDICADORES_CENSO = {
    "renda_media": "Renda média do responsável (R$)",
    "renda_mediana": "Renda mediana do responsável (R$)",
    "pct_pretos_pardos": "% de pretos e pardos (moradores)",
    "densidade": "Densidade (moradores/km²)",
    "moradores_domicilio": "Moradores por domicílio",
}
UF_IBGE = {"RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21, "PI": 22, "CE": 23,
           "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35,
           "PR": 41, "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53}


def _num(col: str) -> pl.Expr:
    """Número do IBGE (vírgula decimal); "X"/"." (sigilo) viram nulo."""
    return pl.col(col).str.strip_chars().str.replace(",", ".").cast(pl.Float64, strict=False)


def _ler_censo(zp: Path, prefixo: str) -> pl.DataFrame:
    with zipfile.ZipFile(zp) as z:
        membro = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        texto = z.read(membro).decode("latin-1")
    df = pl.read_csv(io.StringIO(texto), separator=";", infer_schema=False)
    df = df.rename({c: c.upper() for c in df.columns})  # o básico usa v0001, os demais V01317
    return df.filter(pl.col("CD_BAIRRO").str.starts_with(prefixo))


def indicadores_censo(renda: pl.DataFrame, basico: pl.DataFrame, cor: pl.DataFrame) -> pl.DataFrame:
    """CD_BAIRRO + indicadores do Censo (sem I/O)."""
    cores = ["V01317", "V01318", "V01319", "V01320", "V01321"]  # branca, preta, amarela, parda, indígena
    r = renda.select("CD_BAIRRO", _num("V06004").alias("renda_media"), _num("V06006").alias("renda_mediana"))
    b = basico.select("CD_BAIRRO", pl.when(_num("AREA_KM2") > 0).then(_num("V0001") / _num("AREA_KM2")).alias("densidade"),
                      _num("V0005").alias("moradores_domicilio"))
    total = pl.sum_horizontal([_num(x) for x in cores])
    c = cor.select("CD_BAIRRO", pl.when(total > 0).then(100 * (_num("V01318") + _num("V01320")) / total)
                   .alias("pct_pretos_pardos"))  # bairro sem morador: nulo, não NaN
    return b.join(r, on="CD_BAIRRO", how="left").join(c, on="CD_BAIRRO", how="left").select(
        "CD_BAIRRO", *INDICADORES_CENSO)


def censo_por_bairro(uf: str, cache: Path) -> pl.DataFrame:
    """Indicadores do Censo 2022 dos bairros da UF, com os ZIPs do IBGE em cache (baixa uma vez)."""
    destino = cache / "ibge_censo2022" / f"censo_bairros_{uf.upper()}.parquet"
    if destino.exists():
        return pl.read_parquet(destino)
    pasta = cache / "ibge_censo2022"
    prefixo = str(UF_IBGE[uf.upper()])
    partes = {}
    for chave, caminho in CENSO_ARQUIVOS.items():
        spec = v.DatasetSpec(f"censo2022_{chave}", f"{CENSO_BASE}/{caminho}", v.NATIONAL)
        try:
            partes[chave] = _ler_censo(v.download(spec, pasta), prefixo)
        except (v.TseDataError, requests.RequestException) as exc:
            raise FonteIndisponivel(f"agregados do Censo 2022 por bairro indisponíveis no IBGE ({exc})") from exc
    df = indicadores_censo(partes["renda"], partes["basico"], partes["cor"])
    tmp = destino.with_suffix(".parquet.tmp")
    df.write_parquet(tmp)
    tmp.replace(destino)
    return df


# --------------------------------------------------------------------------
# Estatística (pura)
# --------------------------------------------------------------------------
def _p_fisher(r: float, n: float, fator: float = 1.0) -> float | None:
    """p-valor bilateral de r ≠ 0 pela transformação z de Fisher (aproximação normal)."""
    if n <= 3:
        return None
    if abs(r) >= 1:
        return 0.0
    z = math.atanh(r) * math.sqrt(n - 3) / fator
    return math.erfc(abs(z) / math.sqrt(2))


def correlacao(x: Any, y: Any, peso: Any = None) -> dict[str, Any]:
    """Pearson (ponderado se houver peso), Spearman, IC 95%, p-valores e reta y = a + b·x."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = int(len(x))
    vazio = {"n": n, "n_efetivo": None, "pearson": None, "ic95": None, "p": None, "spearman": None,
             "p_spearman": None, "a": None, "b": None, "r2": None}
    if n < 5 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return vazio
    w = np.ones(n) if peso is None else np.asarray(peso, dtype=float)
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    sxx, syy = np.sum(w * (x - mx) ** 2), np.sum(w * (y - my) ** 2)
    sxy = np.sum(w * (x - mx) * (y - my))
    r = float(np.clip(sxy / math.sqrt(sxx * syy), -1, 1))
    b = float(sxy / sxx)
    n_ef = float(w.sum() ** 2 / np.sum(w ** 2))  # Kish: n efetivo com pesos desiguais
    ic = None
    if n_ef > 3 and abs(r) < 1:
        z, se = math.atanh(r), 1 / math.sqrt(n_ef - 3)
        ic = [math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)]
    postos = pl.DataFrame({"x": x, "y": y}).select(pl.col("x").rank("average"), pl.col("y").rank("average"))
    rho = float(np.corrcoef(postos["x"].to_numpy(), postos["y"].to_numpy())[0, 1])
    return {"n": n, "n_efetivo": n_ef, "pearson": r, "ic95": ic, "p": _p_fisher(r, n_ef),
            "spearman": rho, "p_spearman": _p_fisher(rho, n, math.sqrt(1.06)) if abs(rho) < 1 else 0.0,  # EP de Fieller
            "a": float(my - b * mx), "b": b, "r2": r * r}


def regressao_multipla(y: Any, xs: dict[str, Any], peso: Any = None) -> dict[str, Any]:
    """Mínimos quadrados (ponderados, se houver peso) do voto em VÁRIOS indicadores ao mesmo tempo.

    Cada indicador entra padronizado (z), então o coeficiente é "p.p. de voto por +1 desvio-padrão do
    indicador, com os demais fixos" — comparável entre indicadores de unidades diferentes (R$, %).
    EP clássico (sem correção de heterocedasticidade), IC 95% e p pela normal; VIF mede a
    colinearidade (acima de ~5, os efeitos individuais ficam instáveis: renda e escolaridade andam juntas).
    Também traz o r simples de cada indicador, para comparar "sozinho" × "controlado pelos demais"."""
    y = np.asarray(y, dtype=float)
    nomes = list(xs)
    X = np.column_stack([np.asarray(xs[k], dtype=float) for k in nomes])
    n, k = X.shape
    if n <= k + 2:
        raise ValueError(f"poucas unidades ({n}) para {k} indicadores")
    w = np.ones(n) if peso is None else np.asarray(peso, dtype=float)
    media = np.average(X, axis=0, weights=w)
    dp = np.sqrt(np.average((X - media) ** 2, axis=0, weights=w))
    if np.any(dp == 0):
        raise ValueError("indicador sem variação: " + ", ".join(n_ for n_, d in zip(nomes, dp) if d == 0))
    Z = np.column_stack([np.ones(n), (X - media) / dp])
    sw = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(Z * sw[:, None], y * sw, rcond=None)
    resid = y - Z @ coef
    n_ef = w.sum() ** 2 / np.sum(w ** 2)
    s2 = np.sum(w * resid ** 2) / (w.sum() * (n_ef - k - 1) / n_ef)
    cov = s2 * np.linalg.inv((Z * w[:, None]).T @ Z)
    ymed = np.average(y, weights=w)
    r2 = 1 - np.sum(w * resid ** 2) / np.sum(w * (y - ymed) ** 2)
    saida = []
    for j, nome in enumerate(nomes, start=1):
        ep = float(np.sqrt(cov[j, j]))
        outros = [i for i in range(len(nomes)) if i != j - 1]
        vif = 1.0
        if outros:  # R² do indicador explicado pelos demais
            Zo = np.column_stack([np.ones(n), X[:, outros]])
            co, *_ = np.linalg.lstsq(Zo * sw[:, None], X[:, j - 1] * sw, rcond=None)
            rj = X[:, j - 1] - Zo @ co
            r2j = 1 - np.sum(w * rj ** 2) / np.sum(w * (X[:, j - 1] - media[j - 1]) ** 2)
            vif = float(1 / max(1 - r2j, 1e-12))
        b = float(coef[j])
        z = b / ep if ep else float("inf")
        saida.append({"indicador": nome, "efeito_pp_por_dp": b, "ep": ep, "ic95": [b - 1.96 * ep, b + 1.96 * ep],
                      "p": math.erfc(abs(z) / math.sqrt(2)), "vif": vif, "dp_indicador": float(dp[j - 1]),
                      "r_simples": correlacao(X[:, j - 1], y, peso)["pearson"]})
    return {"n": n, "n_efetivo": float(n_ef), "r2": float(r2),
            "r2_ajustado": float(1 - (1 - r2) * (n_ef - 1) / (n_ef - k - 1)), "intercepto": float(coef[0]),
            "coeficientes": saida}


# --------------------------------------------------------------------------
# Voto e cruzamentos
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Alvo:
    """% dos válidos de um candidato (nº) ou de um partido (nº do partido) numa eleição."""

    ano: int
    cargo: int
    turno: int = 1
    numero: int | None = None
    partido: int | None = None

    def __post_init__(self) -> None:
        if (self.numero is None) == (self.partido is None):
            raise ValueError("informe o número do candidato OU o do partido")
        if self.cargo not in br.CARGOS:
            raise ValueError(f"cargo desconhecido: {self.cargo}")


MUNICIPAIS = (11, 13)  # prefeito e vereador: cada município tem sua própria eleição


def municipio_do_bairro() -> pl.Expr:
    """Código IBGE do município (os 7 primeiros dígitos do CD_BAIRRO)."""
    return pl.col("CD_BAIRRO").str.slice(0, 7).cast(pl.Int64)


def voto_por_bairro(vb: pl.DataFrame, alvo: Alvo) -> pl.DataFrame:
    """CD_BAIRRO, VOTOS, VALIDOS, VOTO (% dos válidos) — 0% onde o alvo concorreu e não teve voto.

    Em eleição municipal, o bairro de um município onde o alvo NÃO concorreu (nenhum voto no
    município inteiro) sai da conta: ali não há 0% de preferência, há ausência de candidatura."""
    valido = ~pl.col("NR_VOTAVEL").is_in(br.ESPECIAIS)
    sel = (pl.col("NR_VOTAVEL") == alvo.numero) if alvo.numero is not None else (
        br.numero_partido(pl.col("NR_VOTAVEL")) == alvo.partido)
    df = (vb.group_by("CD_BAIRRO").agg(pl.col("QT_VOTOS").filter(sel).sum().alias("VOTOS"),
                                       pl.col("QT_VOTOS").filter(valido).sum().alias("VALIDOS"))
          .filter(pl.col("VALIDOS") > 0))
    if alvo.cargo in MUNICIPAIS:
        df = df.filter(pl.col("VOTOS").sum().over(municipio_do_bairro()) > 0)
    return df.with_columns((100 * pl.col("VOTOS") / pl.col("VALIDOS")).alias("VOTO"))


class PerfilVoto:
    """Cruzamentos por bairro sobre os caches de `Bairros` (votos) e de `ComparacaoBairros` (siglas).

    A coluna-chave da unidade se chama CD_BAIRRO por história; `PerfilVotoLocal` (apuracao.perfil_local)
    põe nela o código do LOCAL de votação e troca só as fontes, pelos ganchos `_vb`, `_nomes`,
    `indicador`, `municipios` e `CENSO`."""

    CENSO = INDICADORES_CENSO
    UNIDADE = "bairro"

    def __init__(self, comp: br.ComparacaoBairros) -> None:
        self.comp, self.b = comp, comp.b
        self._perfil: dict[int, pl.DataFrame] = {}
        self._censo: pl.DataFrame | None = None

    # ---- fontes
    def perfil(self, ano: int) -> pl.DataFrame:
        with self.b.trava:  # a mesma trava dos votos: conversões de ZIP nunca em paralelo
            if ano not in self._perfil:
                lf = self.b._carregar(("perfil", ano), lambda: load_perfil(ano, self.b.uf, self.b.cache))
                self._perfil[ano] = perfil_por_bairro(lf, self.b.local_bairro(ano))
            return self._perfil[ano]

    def censo(self) -> pl.DataFrame:
        with self.b.trava:
            if self._censo is None:
                self._censo = self.b._carregar(("censo",), lambda: censo_por_bairro(self.b.uf, self.b.cache))
            return self._censo

    @classmethod
    def indicadores(cls) -> dict[str, dict[str, str]]:
        tse = {k: {"rotulo": r, "fonte": "TSE — eleitores inscritos"} for k, (r, _) in INDICADORES_TSE.items()}
        return tse | {k: {"rotulo": r, "fonte": "IBGE — Censo 2022 (moradores)"} for k, r in cls.CENSO.items()}

    def _vb(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        """Votos por unidade e votável (CD_BAIRRO, NR_VOTAVEL, QT_VOTOS, NM_VOTAVEL)."""
        return self.b.votos(ano, cargo, turno)

    def _nomes(self) -> dict[str, tuple[str, str]]:
        return self.b.nomes()

    def indicador(self, chave: str, ano: int) -> pl.DataFrame:
        """CD_BAIRRO, X para um indicador de perfil (TSE do ano da eleição ou Censo 2022)."""
        if chave in INDICADORES_TSE:
            return self.perfil(ano).select("CD_BAIRRO", pl.col(chave).cast(pl.Float64).alias("X"))
        if chave in self.CENSO:
            return self.censo().select("CD_BAIRRO", pl.col(chave).alias("X"))
        raise ValueError(f"indicador desconhecido: {chave}")

    def voto(self, alvo: Alvo) -> pl.DataFrame:
        return voto_por_bairro(self._vb(alvo.ano, alvo.cargo, alvo.turno), alvo)

    def _votos_area(self, ano: int, cargo: int, turno: int, municipio: int | None) -> pl.DataFrame:
        vb = self._vb(ano, cargo, turno)
        return vb if municipio is None else vb.filter(municipio_do_bairro() == municipio)

    def rotulo(self, alvo: Alvo, municipio: int | None = None) -> str:
        cargo = br.CARGOS[alvo.cargo].title()
        turno = f", {alvo.turno}º turno" if alvo.turno != 1 else ""
        if alvo.numero is not None:
            vb = self._votos_area(alvo.ano, alvo.cargo, alvo.turno, municipio)
            nomes = vb.filter(pl.col("NR_VOTAVEL") == alvo.numero)["NM_VOTAVEL"].unique().to_list()
            # eleição municipal: o mesmo nº é um candidato diferente em cada município
            quem = (f"nº {alvo.numero} {nomes[0]}" if len(nomes) == 1 else
                    f"nº {alvo.numero} ({len(nomes)} candidatos diferentes, um por município)" if nomes else
                    f"nº {alvo.numero}")
        else:
            sigla = self.comp.siglas(alvo.ano).get(alvo.partido)
            quem = f"partido {alvo.partido}{' ' + sigla if sigla else ''}"
        return f"% dos válidos — {quem} ({cargo} {alvo.ano}{turno})"

    def candidatos(self, ano: int, cargo: int, turno: int = 1, municipio: int | None = None,
                   limite: int = 400) -> pl.DataFrame:
        """Votáveis nominais mais votados na área dos bairros (para a lista de escolha).

        Em eleição municipal sem município escolhido, um nº reúne candidatos diferentes (um por
        município): o NOME diz quantos, em vez de mostrar só o primeiro."""
        vb = self._votos_area(ano, cargo, turno, municipio)
        nominal = ~pl.col("NR_VOTAVEL").is_in(br.ESPECIAIS) & (
            (pl.col("NR_VOTAVEL") >= 100) if cargo in br.PROPORCIONAIS else pl.lit(True))
        agg = (vb.filter(nominal).group_by("NR_VOTAVEL")
               .agg(pl.col("QT_VOTOS").sum(), pl.col("NM_VOTAVEL").first(), pl.col("NM_VOTAVEL").n_unique().alias("N")))
        return (agg.with_columns(pl.when(pl.col("N") > 1)
                                 .then(pl.format("{} candidatos diferentes (um por município)", pl.col("N")))
                                 .otherwise(pl.col("NM_VOTAVEL")).alias("NOME"))
                .sort("QT_VOTOS", descending=True).head(limite)
                .select(pl.col("NR_VOTAVEL").alias("NUMERO"), "NOME", pl.col("QT_VOTOS").alias("VOTOS")))

    # ---- cruzamentos
    def municipios(self) -> pl.DataFrame:
        """Municípios com malha de bairros: CD_MUN (IBGE), NM_MUN, número de bairros."""
        linhas = [(f["properties"]["CD_MUN"], f["properties"]["NM_MUN"]) for f in self.b.geo()["features"]]
        return (pl.DataFrame(linhas, schema={"CD_MUN": pl.Int64, "NM_MUN": pl.String}, orient="row")
                .group_by("CD_MUN", "NM_MUN").len("BAIRROS").sort("NM_MUN"))

    def _base(self, y: Alvo, min_validos: int, municipio: int | None = None) -> pl.DataFrame:
        df = self.voto(y).filter(pl.col("VALIDOS") >= min_validos)
        if municipio is not None:
            df = df.filter(municipio_do_bairro() == municipio)
        return df.select("CD_BAIRRO", pl.col("VOTO").alias("Y"), "VALIDOS")

    def dispersao(self, y: Alvo, x: str | Alvo, min_validos: int = 200, ponderar: bool = False,
                  municipio: int | None = None) -> dict[str, Any]:
        """Pontos (um por bairro), estatística, reta e bairros mais acima/abaixo da reta."""
        if isinstance(x, Alvo):
            xs = self.voto(x).select("CD_BAIRRO", pl.col("VOTO").alias("X"))
            rotulo_x = self.rotulo(x, municipio)
        else:
            xs = self.indicador(x, y.ano)
            rotulo_x = self.indicadores()[x]["rotulo"]
        df = self._base(y, min_validos, municipio).join(xs, on="CD_BAIRRO", how="inner").drop_nulls(["X", "Y"])
        est = correlacao(df["X"], df["Y"], df["VALIDOS"] if ponderar else None)
        if est["b"] is not None:
            df = df.with_columns((pl.col("Y") - (est["a"] + est["b"] * pl.col("X"))).alias("RESIDUO"))
        else:
            df = df.with_columns(pl.lit(None, pl.Float64).alias("RESIDUO"))
        nomes = self._nomes()
        df = df.with_columns(pl.col("CD_BAIRRO").map_elements(lambda c: " — ".join(nomes.get(c, ("?", "?"))),
                                                              return_dtype=pl.String).alias("BAIRRO"))
        ordenado = df.drop_nulls("RESIDUO").sort("RESIDUO", descending=True)
        return {"rotulo_x": rotulo_x, "rotulo_y": self.rotulo(y, municipio), "estatistica": est, "min_validos": min_validos,
                "ponderado": ponderar, "pontos": df, "acima": ordenado.head(10),
                "abaixo": ordenado.tail(10).reverse()}

    def transferencias(self, ano_x: int, ano_y: int, cargo: int, top: int = 3, turno: int = 1,
                       municipios: tuple[int | None, ...] = (None, 3304557), min_validos: int = 200) -> pl.DataFrame:
        """Para os `top` candidatos de `ano_y`, a correlação por bairro com o voto no MESMO partido
        (nº) no mesmo cargo em `ano_x` — a primeira leitura de "quem herdou a base de quem".
        Escopo: todos os bairros (None) e cada município pedido (padrão: a capital do RJ)."""
        linhas = []
        for r in self.candidatos(ano_y, cargo, turno).head(top).iter_rows(named=True):
            n = r["NUMERO"]
            partido = n if n < 100 else int(str(n)[:2])
            try:
                self.voto(Alvo(ano_x, cargo, turno, partido=partido))
            except (v.TseDataError, ValueError):
                continue
            for mun in municipios:
                d = self.dispersao(Alvo(ano_y, cargo, turno, numero=n), Alvo(ano_x, cargo, turno, partido=partido),
                                   min_validos, municipio=mun)
                e = d["estatistica"]
                linhas.append({"CARGO": cargo, "NUMERO": n, "CANDIDATO": r["NOME"], "PARTIDO": partido,
                               "ESCOPO": "todos os bairros" if mun is None else str(mun), "N": e["n"],
                               "PEARSON": e["pearson"], "SPEARMAN": e["spearman"], "INCLINACAO": e["b"], "R2": e["r2"]})
        return pl.DataFrame(linhas, schema={"CARGO": pl.Int64, "NUMERO": pl.Int64, "CANDIDATO": pl.String,
                                            "PARTIDO": pl.Int64, "ESCOPO": pl.String, "N": pl.Int64,
                                            "PEARSON": pl.Float64, "SPEARMAN": pl.Float64, "INCLINACAO": pl.Float64,
                                            "R2": pl.Float64})

    def regressao(self, y: Alvo, chaves: list[str], min_validos: int = 200, ponderar: bool = False,
                  municipio: int | None = None) -> dict[str, Any]:
        """Vários indicadores ao mesmo tempo (ex.: escolaridade controlada por renda)."""
        if not chaves:
            raise ValueError("escolha ao menos um indicador")
        df = self._base(y, min_validos, municipio)
        for k in chaves:
            df = df.join(self.indicador(k, y.ano).rename({"X": k}), on="CD_BAIRRO", how="inner")
        df = df.drop_nulls()
        r = regressao_multipla(df["Y"].to_numpy(), {k: df[k].to_numpy() for k in chaves},
                               df["VALIDOS"].to_numpy() if ponderar else None)
        rot = self.indicadores()
        for c in r["coeficientes"]:
            c["rotulo"], c["fonte"] = rot[c["indicador"]]["rotulo"], rot[c["indicador"]]["fonte"]
        return {**r, "rotulo_y": self.rotulo(y, municipio), "unidade": self.UNIDADE, "ponderado": ponderar}

    def correlacoes(self, y: Alvo, min_validos: int = 200, ponderar: bool = False,
                    municipio: int | None = None) -> list[dict[str, Any]]:
        """Correlação do voto com cada indicador de perfil, da mais forte (|r|) para a mais fraca."""
        base = self._base(y, min_validos, municipio)
        saida = []
        for chave, info in self.indicadores().items():
            try:
                df = base.join(self.indicador(chave, y.ano), on="CD_BAIRRO", how="inner").drop_nulls(["X", "Y"])
            except FonteIndisponivel as exc:
                logger.warning("indicador %s indisponível: %s", chave, exc)
                continue
            est = correlacao(df["X"], df["Y"], df["VALIDOS"] if ponderar else None)
            saida.append({"indicador": chave, **info, **{k: est[k] for k in ("n", "pearson", "ic95", "p", "spearman", "b")}})
        return sorted(saida, key=lambda e: -abs(e["pearson"] or 0))
