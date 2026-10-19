"""Diferenças entre duas versões do cadastro de eleitorado (acervo de `apuracao/versoes.py`).

O TSE regera o cadastro no mesmo endereço (em outubro de 2026, uma vez por dia). Duas leituras dizem o que mudou:

- **linha a linha, no CSV do TSE:** todas as colunas, como texto, sem interpretação. Chave = turno + UF + município
  + zona + seção (`CHAVE`); `DT_GERACAO`/`HH_GERACAO` ficam de fora porque mudam a cada geração. Dá as células
  alteradas e as linhas criadas e extintas;
- **a situação de cada seção entre os turnos** (`locais_turnos`) em cada versão, e as seções que mudaram de
  situação ou de local no 2º turno de uma versão para a outra. "—" = sem situação (o mesmo local nos dois turnos).

Sem I/O, exceto `ler_csv` e `para_planilha`.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

import votos_por_local_votacao as v
from apuracao import locais_turnos as lt

CHAVE = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
INTEIROS = ("NR_TURNO", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")
IGNORAR = ("DT_GERACAO", "HH_GERACAO")
CONTEXTO = ["NM_MUNICIPIO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO", "QT_ELEITOR_SECAO"]
SEM_SITUACAO = "—"
LIMITE_EXCEL = 1_048_575  # linhas de dados numa aba (o Excel tem 1.048.576 com o cabeçalho)


@dataclass(frozen=True)
class Diferencas:
    """O que mudou no CSV de uma versão para a outra.

    Attributes:
        linhas_antes / linhas_depois: linhas (seção × turno) de cada versão.
        celulas: uma linha por célula alterada (CHAVE + município e nº do local de depois + COLUNA, ANTES, DEPOIS).
        criadas / extintas: as linhas só na versão de depois / só na de antes (CHAVE + `CONTEXTO`).
        colunas_novas / colunas_removidas: colunas só na versão de depois / só na de antes (não comparadas).
    """

    linhas_antes: int
    linhas_depois: int
    celulas: pl.DataFrame
    criadas: pl.DataFrame
    extintas: pl.DataFrame
    colunas_novas: tuple[str, ...]
    colunas_removidas: tuple[str, ...]


@dataclass(frozen=True)
class Turnos:
    """As seções de uma versão no 1º e no 2º turno e a comparação entre eles (None sem linhas do 2º turno)."""

    t1: pl.DataFrame
    t2: pl.DataFrame
    comparacao: lt.Comparacao | None


def turnos(t1: pl.DataFrame, t2: pl.DataFrame) -> Turnos:
    return Turnos(t1, t2, None if t2.is_empty() else lt.comparar(t1, t2))


def ler_csv(zip_path: Path, ufs: list[str]) -> pl.DataFrame:
    """As linhas das UFs no CSV do TSE: todas as colunas como texto (a chave como inteiro), sem a hora da geração.

    Lê cada CSV do ZIP uma vez: o da UF, quando o ano tem um CSV por UF, ou o nacional filtrado pela UF.
    """
    partes = []
    with zipfile.ZipFile(zip_path) as zf:
        por_csv: dict[str, list[str]] = {}
        for uf in ufs:
            por_csv.setdefault(v.pick_csv_member(zf, uf), []).append(uf)
        for membro, lista in por_csv.items():
            df = pl.read_csv(io.BytesIO(zf.read(membro).decode("latin-1").encode()), separator=";",
                             infer_schema=False)
            if "SG_UF" in df.columns:
                df = df.filter(pl.col("SG_UF").is_in(lista))
            partes.append(df.drop([c for c in IGNORAR if c in df.columns]))
    df = pl.concat(partes, how="diagonal")
    return df.with_columns(pl.col(c).cast(pl.Int64) for c in INTEIROS if c in df.columns)


def _ordenar(df: pl.DataFrame) -> pl.DataFrame:
    return df.sort(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_TURNO"])


def comparar_linhas(antes: pl.DataFrame, depois: pl.DataFrame) -> Diferencas:
    """Compara as linhas de duas versões (de `ler_csv`) pela `CHAVE`, coluna a coluna.

    Raises:
        TseDataError: falta coluna da chave, ou uma versão repete a chave.
    """
    falta = [c for c in CHAVE if c not in antes.columns or c not in depois.columns]
    if falta:
        raise v.TseDataError(f"o cadastro não tem as colunas da chave: {', '.join(falta)}")
    for nome, df in (("antes", antes), ("depois", depois)):
        repetidas = df.height - df.select(CHAVE).n_unique()
        if repetidas:
            raise v.TseDataError(f"versão de {nome}: {repetidas} linha(s) com a chave repetida ({' + '.join(CHAVE)})")
    comuns = [c for c in antes.columns if c in depois.columns and c not in CHAVE]
    j = (antes.select(CHAVE + comuns).with_columns(pl.lit(True).alias("_ANTES"))
         .join(depois.select(CHAVE + comuns).with_columns(pl.lit(True).alias("_DEPOIS")),
               on=CHAVE, how="full", coalesce=True, suffix="__D")
         .rechunk())
    ambos = j.filter(pl.col("_ANTES") & pl.col("_DEPOIS"))
    contexto = [pl.col(f"{c}__D").alias(c) if c in comuns else pl.lit(None, pl.String).alias(c)
                for c in ("NM_MUNICIPIO", "NR_LOCAL_VOTACAO")]
    vazio = pl.DataFrame(schema={**{c: pl.Int64 for c in INTEIROS}, "SG_UF": pl.String, "NM_MUNICIPIO": pl.String,
                                 "NR_LOCAL_VOTACAO": pl.String, "COLUNA": pl.String, "ANTES": pl.String,
                                 "DEPOIS": pl.String})
    celulas = pl.concat(
        [vazio.select(CHAVE + ["NM_MUNICIPIO", "NR_LOCAL_VOTACAO", "COLUNA", "ANTES", "DEPOIS"])]
        + [ambos.filter(pl.col(c).ne_missing(pl.col(f"{c}__D")))
           .select(CHAVE + contexto + [pl.lit(c).alias("COLUNA"), pl.col(c).alias("ANTES"),
                                      pl.col(f"{c}__D").alias("DEPOIS")]) for c in comuns])
    so = {lado: j.filter(pl.col(outro).is_null()) for lado, outro in (("antes", "_DEPOIS"), ("depois", "_ANTES"))}
    return Diferencas(
        linhas_antes=antes.height, linhas_depois=depois.height,
        celulas=_ordenar(celulas.with_columns(pl.col("NR_LOCAL_VOTACAO").cast(pl.Int64, strict=False))),
        criadas=_ordenar(so["depois"].select(CHAVE + [
            (pl.col(f"{c}__D") if c in comuns else pl.lit(None, pl.String)).alias(c) for c in CONTEXTO])),
        extintas=_ordenar(so["antes"].select(CHAVE + [
            (pl.col(c) if c in comuns else pl.lit(None, pl.String)).alias(c) for c in CONTEXTO])),
        colunas_novas=tuple(c for c in depois.columns if c not in antes.columns),
        colunas_removidas=tuple(c for c in antes.columns if c not in depois.columns),
    )


def _um_csv_por_uf(zip_path: Path, ufs: list[str]) -> bool:
    with zipfile.ZipFile(zip_path) as zf:
        return len({v.pick_csv_member(zf, uf) for uf in ufs}) == len(ufs)


def comparar_zips(zip_antes: Path, zip_depois: Path, ufs: list[str]) -> Diferencas:
    """`comparar_linhas` das UFs pedidas nos dois ZIPs. Com um CSV por UF nos dois, compara UF por UF (a memória
    fica na da maior UF: o país inteiro de uma vez passa de 4 GB); senão (CSV nacional), tudo de uma vez."""
    if not (_um_csv_por_uf(zip_antes, ufs) and _um_csv_por_uf(zip_depois, ufs)):
        return comparar_linhas(ler_csv(zip_antes, ufs), ler_csv(zip_depois, ufs))
    partes = [comparar_linhas(ler_csv(zip_antes, [uf]), ler_csv(zip_depois, [uf])) for uf in ufs]
    return Diferencas(
        linhas_antes=sum(x.linhas_antes for x in partes), linhas_depois=sum(x.linhas_depois for x in partes),
        celulas=pl.concat([x.celulas for x in partes], how="vertical_relaxed"),
        criadas=pl.concat([x.criadas for x in partes], how="vertical_relaxed"),
        extintas=pl.concat([x.extintas for x in partes], how="vertical_relaxed"),
        colunas_novas=tuple(dict.fromkeys(c for x in partes for c in x.colunas_novas)),
        colunas_removidas=tuple(dict.fromkeys(c for x in partes for c in x.colunas_removidas)),
    )


def resumo_colunas(d: Diferencas) -> pl.DataFrame:
    """Linhas alteradas por coluna, em cada turno (a coluna mais alterada primeiro)."""
    return (d.celulas.group_by("COLUNA")
            .agg(pl.len().alias("LINHAS"), (pl.col("NR_TURNO") == 1).sum().alias("LINHAS_1T"),
                 (pl.col("NR_TURNO") == 2).sum().alias("LINHAS_2T"))
            .sort(["LINHAS", "COLUNA"], descending=[True, False]))


def alteracoes(d: Diferencas) -> pl.DataFrame:
    """As células agrupadas por local: uma linha por (UF, município, zona, local, turno, coluna, antes, depois), com
    as seções. O nº do local é o da versão de depois."""
    grupo = ["SG_UF", "NM_MUNICIPIO", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NR_TURNO", "COLUNA", "ANTES",
             "DEPOIS"]
    return (d.celulas.group_by(grupo)
            .agg(pl.len().alias("N_SECOES"), pl.col("NR_SECAO").sort().cast(pl.String).str.join(", ").alias("SECOES"))
            .sort(["SG_UF", "NM_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NR_TURNO", "COLUNA", "ANTES"],
                  nulls_last=True))


def temporarios(t: Turnos) -> pl.DataFrame:
    """Por UF, as seções em local temporário (local onde vota ≠ local cadastrado) em cada turno."""
    def por_uf(df: pl.DataFrame, nome: str) -> pl.DataFrame:
        return df.group_by("SG_UF").agg(pl.col("REMANEJADA").sum().cast(pl.Int64).alias(nome))

    return (por_uf(t.t1, "TEMPORARIAS_1T").join(por_uf(t.t2, "TEMPORARIAS_2T"), on="SG_UF", how="full",
                                                 coalesce=True)
            .rechunk().fill_null(0))


def resumo_ufs(d: Diferencas, antes: Turnos, depois: Turnos) -> pl.DataFrame:
    """Por UF: linhas e células alteradas, linhas criadas e extintas e seções em local temporário nas duas versões."""
    alteradas = d.celulas.group_by("SG_UF").agg(pl.struct(CHAVE).n_unique().alias("LINHAS_ALTERADAS"),
                                                 pl.len().alias("CELULAS"))
    criadas = d.criadas.group_by("SG_UF").agg(pl.len().alias("CRIADAS"))
    extintas = d.extintas.group_by("SG_UF").agg(pl.len().alias("EXTINTAS"))
    temp = [temporarios(t).rename({c: f"{c}_{s}" for c in ("TEMPORARIAS_1T", "TEMPORARIAS_2T")})
            for t, s in ((antes, "ANTES"), (depois, "DEPOIS"))]
    ufs = pl.concat([x.select("SG_UF") for x in (alteradas, criadas, extintas, *temp)]).unique()
    r = ufs
    for x in (alteradas, criadas, extintas, *temp):
        r = r.join(x, on="SG_UF", how="left")
    return r.with_columns(pl.exclude("SG_UF").fill_null(0)).sort("SG_UF")


def situacoes(antes: Turnos, depois: Turnos) -> pl.DataFrame:
    """As situações entre os turnos nas duas versões, lado a lado (seções e eleitores; nulo sem 2º turno)."""
    lados = []
    for t, s in ((antes, "ANTES"), (depois, "DEPOIS")):
        if t.comparacao is None:
            lados.append(pl.DataFrame({"SITUACAO": list(lt.SITUACOES), f"SECOES_{s}": [None] * len(lt.SITUACOES),
                                       f"ELEITORES_{s}": [None] * len(lt.SITUACOES)},
                                      schema_overrides={f"SECOES_{s}": pl.Int64, f"ELEITORES_{s}": pl.Int64}))
        else:
            lados.append(lt.resumo(t.comparacao).select(
                "SITUACAO", pl.col("SECOES").cast(pl.Int64).alias(f"SECOES_{s}"),
                pl.col("ELEITORES").cast(pl.Int64).alias(f"ELEITORES_{s}")))
    return lados[0].join(lados[1], on="SITUACAO", how="left", maintain_order="left")


def mudancas_de_situacao(antes: Turnos, depois: Turnos) -> pl.DataFrame | None:
    """As seções presentes no 2º turno das duas versões que mudaram de situação entre os turnos ou de local no 2º
    turno (None se uma versão não tem 2º turno). Criadas e extintas ficam em `Diferencas`."""
    if antes.comparacao is None or depois.comparacao is None:
        return None

    def local_2t(df: pl.DataFrame, s: str) -> pl.DataFrame:
        return df.select(lt.CHAVE + [pl.col("NR_LOCAL_VOTACAO").alias(f"NR_LOCAL_2T_{s}"),
                                     pl.col("NM_LOCAL_VOTACAO").alias(f"NM_LOCAL_2T_{s}")])

    def situacao(c: lt.Comparacao, s: str) -> pl.DataFrame:
        return c.secoes.select(lt.CHAVE + [pl.col("SITUACAO").alias(f"SITUACAO_{s}")])

    j = (depois.t2.select(lt.CHAVE + ["NM_MUNICIPIO", "QT_ELEITOR_SECAO"])
         .join(depois.t1.select(lt.CHAVE + [pl.col("NR_LOCAL_VOTACAO").alias("NR_LOCAL_1T"),
                                            pl.col("NM_LOCAL_VOTACAO").alias("NM_LOCAL_1T")]), on=lt.CHAVE, how="left")
         .join(local_2t(antes.t2, "ANTES"), on=lt.CHAVE, how="inner")
         .join(local_2t(depois.t2, "DEPOIS"), on=lt.CHAVE, how="left")
         .join(situacao(antes.comparacao, "ANTES"), on=lt.CHAVE, how="left")
         .join(situacao(depois.comparacao, "DEPOIS"), on=lt.CHAVE, how="left"))
    m = j.filter(pl.col("SITUACAO_ANTES").ne_missing(pl.col("SITUACAO_DEPOIS"))
                 | pl.col("NR_LOCAL_2T_ANTES").ne_missing(pl.col("NR_LOCAL_2T_DEPOIS")))
    return (m.with_columns(pl.col("SITUACAO_ANTES", "SITUACAO_DEPOIS").fill_null(SEM_SITUACAO))
            .select("SG_UF", "NM_MUNICIPIO", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "QT_ELEITOR_SECAO",
                    "SITUACAO_ANTES", "SITUACAO_DEPOIS", "NR_LOCAL_1T", "NM_LOCAL_1T", "NR_LOCAL_2T_ANTES",
                    "NM_LOCAL_2T_ANTES", "NR_LOCAL_2T_DEPOIS", "NM_LOCAL_2T_DEPOIS")
            .sort("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"))


def quadro_de_situacoes(m: pl.DataFrame) -> pl.DataFrame:
    """De `mudancas_de_situacao`: seções e eleitores por (situação antes, situação depois), com as UFs."""
    return (m.group_by("SITUACAO_ANTES", "SITUACAO_DEPOIS")
            .agg(pl.len().alias("SECOES"), pl.col("QT_ELEITOR_SECAO").sum().alias("ELEITORES"),
                 pl.col("SG_UF").unique().sort().str.join(" ").alias("UFS"))
            .sort(["SECOES", "SITUACAO_ANTES", "SITUACAO_DEPOIS"], descending=[True, False, False]))


def para_planilha(abas: dict[str, pl.DataFrame], consulta: dict[str, Any], destino: Path) -> Path:
    """.xlsx com as abas dadas e a "Consulta" (parâmetros, as duas versões e as contagens). Aba maior que o Excel
    aceita sai cortada, com aviso na Consulta. Gravação atômica."""
    import xlsxwriter

    destino.parent.mkdir(parents=True, exist_ok=True)
    itens = dict(consulta)
    cortadas = {}
    for nome, df in abas.items():
        if df.height > LIMITE_EXCEL:
            itens[f"aba {nome}"] = f"{df.height} linhas; só as primeiras {LIMITE_EXCEL} na planilha"
        cortadas[nome] = df.head(LIMITE_EXCEL)
    cortadas["Consulta"] = pl.DataFrame({"ITEM": list(itens), "VALOR": [str(x) for x in itens.values()]})
    tmp = destino.with_name(destino.name + ".tmp")
    with xlsxwriter.Workbook(str(tmp)) as wb:
        for nome, df in cortadas.items():
            df.write_excel(wb, worksheet=nome, autofit=True, freeze_panes=(1, 0))
    tmp.replace(destino)
    return destino
