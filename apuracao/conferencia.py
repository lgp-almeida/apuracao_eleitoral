"""Conferência do resultado gravado na noite (tempo real) com o importado dos microdados (TODO 16, rodada 45).

Entradas: duas pastas no formato do coletor — a da noite (`dados_2026/oficial[_t2][_UF]`) e a importada
(`dados_2026/historico_<ano>_t<turno>[_UF]`, com totais oficiais ou reconstruídos das seções, rodada 40). Sem I/O
além da leitura das tabelas `ultimo/`.

Compara, por cargo × abrangência (UF e municípios):
  totais       eleitorado, comparecimento, abstenção, votos, válidos, brancos, nulos, anulados, sub judice, seções;
  candidatos   votos, situação e destinação de cada candidato; os que só aparecem num lado (nulo técnico: a
               divulgação não lista; candidato sem voto: os microdados não listam);
  cadeiras     eleitos de deputado pelas duas fontes (`cadeiras.entrada_divulgacao` + `distribuir`).

Achados conhecidos (rodada 40): o % dos válidos da divulgação usa válidos + sub judice no denominador (por isso
não se compara o % gravado, só os votos); a hora da totalização difere (a do TSE na noite × a da última seção ou a da
retotalização); o Presidente pode diferir enquanto a destinação dele não sai no candidato_munzona.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

import votos_por_local_votacao as v
from apuracao import cadeiras as cd

CHAVE = ["CARGO", "ABRANGENCIA", "CD_MUNICIPIO"]
COLUNAS_TOTAIS = ["ELEITORADO", "COMPARECIMENTO", "ABSTENCAO", "VOTOS_TOTAL", "VALIDOS", "NOMINAIS", "LEGENDA",
                  "BRANCOS", "NULOS", "ANULADOS", "ANULADOS_SUB_JUDICE", "SECOES_TOTAL"]


@dataclass
class Conferencia:
    totais: pl.DataFrame            # uma linha por cargo × abrangência × coluna com diferença
    resumo_totais: pl.DataFrame     # por cargo × coluna: linhas diferentes e soma |dif|
    candidatos: pl.DataFrame        # pares candidato × abrangência com votos/situação/destinação diferentes
    so_num_lado: pl.DataFrame       # candidatos só na noite ou só no importado (com votos)
    cadeiras: pl.DataFrame          # por cargo: eleitos iguais, só na noite, só no importado
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.totais.is_empty() and self.candidatos.is_empty() and bool(
            self.cadeiras.is_empty() or self.cadeiras["IGUAIS"].all())


def _ler(pasta: Path, tabela: str) -> pl.DataFrame:
    return pl.read_parquet(pasta / "ultimo" / f"{tabela}.parquet")


def comparar_totais(noite: pl.DataFrame, importado: pl.DataFrame) -> pl.DataFrame:
    """Linhas (cargo, abrangência, município, coluna) em que os totais diferem."""
    cols = [c for c in COLUNAS_TOTAIS if c in noite.columns and c in importado.columns]
    a = noite.filter(pl.col("ABRANGENCIA").is_in(["uf", "mun"])).select(CHAVE + cols)
    b = importado.filter(pl.col("ABRANGENCIA").is_in(["uf", "mun"])).select(CHAVE + cols)
    j = a.join(b, on=CHAVE, how="inner", nulls_equal=True, suffix="_IMPORTADO")
    partes = [j.filter(pl.col(c) != pl.col(f"{c}_IMPORTADO")).select(
        CHAVE + [pl.lit(c).alias("COLUNA"), pl.col(c).alias("NOITE"), pl.col(f"{c}_IMPORTADO").alias("IMPORTADO")])
        for c in cols]
    vazio = pl.DataFrame(schema={**{k: pl.Int64 for k in CHAVE}, "ABRANGENCIA": pl.String, "COLUNA": pl.String,
                                 "NOITE": pl.Int64, "IMPORTADO": pl.Int64})
    return (pl.concat([vazio.select(CHAVE + ["COLUNA", "NOITE", "IMPORTADO"]), *partes], how="vertical_relaxed")
            .with_columns((pl.col("IMPORTADO") - pl.col("NOITE")).alias("DIF")).sort(CHAVE + ["COLUNA"], nulls_last=True))


def comparar_candidatos(noite: pl.DataFrame, importado: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(diferenças em votos/situação/destinação; candidatos com voto só num lado)."""
    k = CHAVE + ["NUMERO"]
    cols = ["NOME_URNA", "VOTOS", "SITUACAO", "DESTINACAO"]
    a = noite.filter(pl.col("ABRANGENCIA").is_in(["uf", "mun"]) & (pl.col("VOTOS") > 0)).select(k + cols)
    b = importado.filter(pl.col("ABRANGENCIA").is_in(["uf", "mun"]) & (pl.col("VOTOS") > 0)).select(k + cols)
    j = a.join(b, on=k, how="full", coalesce=True, nulls_equal=True, suffix="_IMPORTADO").rechunk()
    ambos = j.filter(pl.col("VOTOS").is_not_null() & pl.col("VOTOS_IMPORTADO").is_not_null())
    # a situação só se compara no estado: nos municípios a divulgação repete a da UF e os microdados não trazem
    sit_dif = (pl.col("ABRANGENCIA") == "uf") & (pl.col("SITUACAO") != pl.col("SITUACAO_IMPORTADO"))
    dif = ambos.filter((pl.col("VOTOS") != pl.col("VOTOS_IMPORTADO")) | sit_dif
                       | (pl.col("DESTINACAO") != pl.col("DESTINACAO_IMPORTADO")))
    so = (j.filter(pl.col("VOTOS").is_null() | pl.col("VOTOS_IMPORTADO").is_null())
          .with_columns(pl.when(pl.col("VOTOS").is_null()).then(pl.lit("só no importado"))
                        .otherwise(pl.lit("só na noite")).alias("ONDE")))
    return dif.sort(k, nulls_last=True), so.sort(k, nulls_last=True)


def comparar_cadeiras(noite: tuple[pl.DataFrame, ...], importado: tuple[pl.DataFrame, ...], uf: str) -> pl.DataFrame:
    """Por cargo de deputado: os eleitos pela distribuição de cada fonte."""
    linhas = []
    for cargo in cd.PROPORCIONAIS:
        try:
            ea = set(cd.distribuir(*cd.entrada_divulgacao(*noite, cargo, uf)).candidatos.filter(
                pl.col("SITUACAO_PROJETADA").str.starts_with("Eleito"))["NUMERO"].to_list())
            eb = set(cd.distribuir(*cd.entrada_divulgacao(*importado, cargo, uf)).candidatos.filter(
                pl.col("SITUACAO_PROJETADA").str.starts_with("Eleito"))["NUMERO"].to_list())
        except (ValueError, v.TseDataError, pl.exceptions.PolarsError):
            continue  # cargo sem votos numa das fontes (DF tem distrital; 2º turno não tem deputado)
        if not ea and not eb:
            continue
        linhas.append({"CARGO": cargo, "ELEITOS_NOITE": len(ea), "ELEITOS_IMPORTADO": len(eb),
                       "SO_NA_NOITE": ", ".join(map(str, sorted(ea - eb))), "SO_NO_IMPORTADO": ", ".join(map(str, sorted(eb - ea))),
                       "IGUAIS": ea == eb})
    return pl.DataFrame(linhas, schema={"CARGO": pl.Int64, "ELEITOS_NOITE": pl.Int64, "ELEITOS_IMPORTADO": pl.Int64,
                                        "SO_NA_NOITE": pl.String, "SO_NO_IMPORTADO": pl.String, "IGUAIS": pl.Boolean})


def conferir(noite: Path, importado: Path, uf: str) -> Conferencia:
    tn, ti = _ler(noite, "totais"), _ler(importado, "totais")
    cn, ci = _ler(noite, "candidatos"), _ler(importado, "candidatos")
    pn, pi = _ler(noite, "partidos"), _ler(importado, "partidos")
    tot = comparar_totais(tn, ti)
    resumo = (tot.group_by("CARGO", "COLUNA").agg(pl.len().alias("LINHAS_DIFERENTES"),
                                                  pl.col("DIF").abs().sum().alias("SOMA_DIF_ABS"))
              .sort("CARGO", "COLUNA"))
    dif, so = comparar_candidatos(cn, ci)
    cad = comparar_cadeiras((tn, cn, pn), (ti, ci, pi), uf)
    avisos = []
    import json
    st = importado / "status.json"
    if st.exists():
        s = json.loads(st.read_text())
        if s.get("totais_de") == "secoes":
            avisos.append(f"importado com totais PROVISÓRIOS ({s.get('totais')})")
        avisos += s.get("avisos") or []
    return Conferencia(tot, resumo, dif, so, cad, avisos)


def para_planilha(c: Conferencia, destino: Path) -> Path:
    import xlsxwriter
    destino.parent.mkdir(parents=True, exist_ok=True)
    abas = {"resumo_totais": c.resumo_totais, "totais": c.totais, "candidatos": c.candidatos,
            "so_num_lado": c.so_num_lado, "cadeiras": c.cadeiras,
            "avisos": pl.DataFrame({"AVISO": c.avisos or ["nenhum"]})}
    with xlsxwriter.Workbook(str(destino)) as wb:
        for nome, df in abas.items():
            df.write_excel(wb, worksheet=nome, autofit=True)
    return destino
