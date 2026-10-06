"""Bancadas de deputado: esta eleição × a de referência (TODO 15, rodada 45). Sem I/O.

Entradas: duas `comparacao.Fonte` (a atual — tempo real ou importada — e a de referência, ex.: 2022 importado).
  partidos   eleitos por partido nos dois anos, ligados pela ENTIDADE (`apuracao/partidos.py`: o PRD de 2026 soma
             os eleitos de PTB e PATRIOTA em 2022; o MISSÃO, nº 14 reaproveitado, não herda os do PTB);
  eleitos    cada eleito agora, com a trajetória: reeleito (mesmo cargo), eleito antes para outro cargo, já tinha
             concorrido sem se eleger, ou novato — pelo nome civil completo (`compact`, como em
             `comparacao.historico_candidato`: o número muda de uma eleição para outra);
  sairam     cada eleito da referência que não se elegeu agora para o mesmo cargo, e o que fez agora.
Homônimos com o mesmo nome civil completo não se distinguem (raro; a planilha mostra partido e número dos dois anos).
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from apuracao import partidos as pt
from apuracao.comparacao import Fonte, _mapa_partidos
from apuracao.eleitorado import compact

PROPORCIONAIS = (6, 7, 8)
NOMES = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual",
         8: "Deputado Distrital"}


@dataclass
class Bancadas:
    ano: int
    ano_ref: int
    cargo: int
    partidos: pl.DataFrame
    eleitos: pl.DataFrame
    sairam: pl.DataFrame
    resumo: dict[str, int]


def _uf(f: Fonte, uf: str) -> pl.DataFrame:
    c = f.candidatos.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf.upper()))
    return c.with_columns(pl.col("NOME").map_elements(compact, return_dtype=pl.String).alias("_CHAVE"),
                          pl.col("SITUACAO").fill_null("").str.starts_with("Eleito").alias("_ELEITO"))


def bancadas(atual: Fonte, ref: Fonte, uf: str, cargo: int) -> Bancadas:
    if cargo not in PROPORCIONAIS:
        raise ValueError("bancadas só de deputado (cargo 6, 7 ou 8)")
    agora, antes = _uf(atual, uf), _uf(ref, uf)
    el_agora = agora.filter((pl.col("CARGO") == cargo) & pl.col("_ELEITO"))
    el_antes = antes.filter((pl.col("CARGO") == cargo) & pl.col("_ELEITO"))
    if el_agora.is_empty() and el_antes.is_empty():
        raise ValueError(f"sem eleitos de {NOMES[cargo]} em {uf} nos dois anos")

    # partidos pela entidade: nº de agora → nºs que formavam o mesmo partido na referência
    corr = pt.correspondencia(_mapa_partidos(ref), _mapa_partidos(atual), ref.ano, atual.ano)
    sigla_antes = _mapa_partidos(ref)
    n_antes = dict(el_antes.group_by("NR_PARTIDO").len().iter_rows())
    linhas, usados = [], set()
    for nr, sigla in sorted(_mapa_partidos(atual).items()):
        ants = corr.get(nr, [])
        usados |= set(ants)
        e_agora = el_agora.filter(pl.col("NR_PARTIDO") == nr).height
        e_antes = sum(n_antes.get(a, 0) for a in ants)
        if e_agora or e_antes:
            linhas.append({"PARTIDO": sigla, "NR_PARTIDO": nr,
                           "ANTES_COMO": " + ".join(sigla_antes.get(a, str(a)) for a in ants) or None,
                           "ELEITOS_ANTES": e_antes, "ELEITOS_AGORA": e_agora})
    for nr, n in sorted(n_antes.items()):  # partido da referência sem sucessor (raro: a tabela de eventos cobre)
        if nr not in usados:
            linhas.append({"PARTIDO": None, "NR_PARTIDO": None, "ANTES_COMO": sigla_antes.get(nr, str(nr)),
                           "ELEITOS_ANTES": n, "ELEITOS_AGORA": 0})
    partidos = (pl.DataFrame(linhas, schema={"PARTIDO": pl.String, "NR_PARTIDO": pl.Int64, "ANTES_COMO": pl.String,
                                             "ELEITOS_ANTES": pl.Int64, "ELEITOS_AGORA": pl.Int64})
                .with_columns((pl.col("ELEITOS_AGORA") - pl.col("ELEITOS_ANTES")).alias("VARIACAO"))
                .sort(["ELEITOS_AGORA", "ELEITOS_ANTES"], descending=True))

    # pessoas: a trajetória de cada eleito agora e o destino de cada eleito antes
    def trajetoria(r: dict) -> tuple[str, str | None]:
        ali = antes.filter(pl.col("_CHAVE") == r["_CHAVE"])
        if ali.filter((pl.col("CARGO") == cargo) & pl.col("_ELEITO")).height:
            return "reeleito", None
        outro = ali.filter(pl.col("_ELEITO"))
        if outro.height:
            return "eleito antes para outro cargo", NOMES.get(outro["CARGO"][0], str(outro["CARGO"][0]))
        if ali.height:
            return "já concorreu, sem se eleger", ali.sort("VOTOS", descending=True)["SITUACAO"][0]
        return "novato", None

    linhas_e = []
    for r in el_agora.sort("VOTOS", descending=True).iter_rows(named=True):
        t, det = trajetoria(r)
        linhas_e.append({"NUMERO": r["NUMERO"], "NOME_URNA": r["NOME_URNA"], "NOME": r["NOME"], "PARTIDO": r["PARTIDO"],
                         "VOTOS": r["VOTOS"], "SITUACAO": r["SITUACAO"], "TRAJETORIA": t, "DETALHE": det})
    eleitos = pl.DataFrame(linhas_e, schema={"NUMERO": pl.Int64, "NOME_URNA": pl.String, "NOME": pl.String,
                                             "PARTIDO": pl.String, "VOTOS": pl.Int64, "SITUACAO": pl.String,
                                             "TRAJETORIA": pl.String, "DETALHE": pl.String})
    reeleitos = set(el_agora["_CHAVE"].to_list())
    linhas_s = []
    for r in el_antes.filter(~pl.col("_CHAVE").is_in(list(reeleitos))).sort("VOTOS", descending=True).iter_rows(named=True):
        hoje = agora.filter(pl.col("_CHAVE") == r["_CHAVE"]).sort("VOTOS", descending=True)
        if hoje.is_empty():
            destino = "não concorreu"
        else:
            h = hoje.row(0, named=True)
            mesmo = h["CARGO"] == cargo
            destino = (("concorreu de novo e não se elegeu" if mesmo else
                        f"concorreu a outro cargo ({NOMES.get(h['CARGO'], h['CARGO'])})")
                       + (f": {h['SITUACAO']}" if h["SITUACAO"] else ""))
        linhas_s.append({"NUMERO_ANTES": r["NUMERO"], "NOME_URNA": r["NOME_URNA"], "NOME": r["NOME"],
                         "PARTIDO_ANTES": r["PARTIDO"], "VOTOS_ANTES": r["VOTOS"], "DESTINO": destino})
    sairam = pl.DataFrame(linhas_s, schema={"NUMERO_ANTES": pl.Int64, "NOME_URNA": pl.String, "NOME": pl.String,
                                            "PARTIDO_ANTES": pl.String, "VOTOS_ANTES": pl.Int64, "DESTINO": pl.String})
    resumo = {"eleitos_antes": el_antes.height, "eleitos_agora": el_agora.height,
              **{k: int((eleitos["TRAJETORIA"] == k).sum()) for k in
                 ("reeleito", "eleito antes para outro cargo", "já concorreu, sem se eleger", "novato")},
              "nao_reeleitos": sairam.height}
    return Bancadas(atual.ano, ref.ano, cargo, partidos, eleitos, sairam, resumo)


def planilha(b: Bancadas, uf: str) -> bytes:
    """.xlsx em memória: Resumo, Partidos, Eleitos e Saíram."""
    import io

    import xlsxwriter
    buf = io.BytesIO()
    with xlsxwriter.Workbook(buf, {"in_memory": True}) as wb:
        pl.DataFrame({"ITEM": ["UF", "Cargo", "Anos", *b.resumo], "VALOR": [
            uf, NOMES[b.cargo], f"{b.ano} × {b.ano_ref}", *[str(x) for x in b.resumo.values()]]}).write_excel(
            wb, worksheet="Resumo", autofit=True)
        b.partidos.write_excel(wb, worksheet="Partidos", autofit=True)
        b.eleitos.write_excel(wb, worksheet=f"Eleitos {b.ano}", autofit=True)
        b.sairam.write_excel(wb, worksheet=f"Eleitos {b.ano_ref} que saíram", autofit=True)
    return buf.getvalue()
