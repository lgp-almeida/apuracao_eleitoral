"""Planilha de um candidato: votos por seção, local, zona e bairro × eleitorado por ano.

Montagem (`build_report`, sem I/O) separada da escrita (`write_workbook`).

Regras:
  * o local de cada seção é o do ARQUIVO DE VOTAÇÃO (onde a urna funcionou);
  * as mudanças de local são medidas entre o cadastro do ANO-BASE (por padrão, o ano
    do resultado) e o de 2026: coluna MUDANCA_<base>_2026;
  * bairro e coordenadas vêm do cadastro do ano do resultado; se o local não estiver
    nele, do de 2026, do ano-base e, por fim, do de 2024 (coluna FONTE_CADASTRO);
  * eleitorado de um local/zona/bairro em cada ano = soma de QT_ELEITOR_SECAO no
    cadastro daquele ano (seções agregadas incluídas), agrupado pelas chaves daquele
    ano. Sempre há ELEITORADO_2024 e ELEITORADO_2026, mais ELEITORADO_<base> se o
    ano-base for outro; VAR_ELEITORADO* vai do ano-base a 2026.
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
from xlsxwriter import Workbook

import votos_por_local_votacao as v
from apuracao import eleitorado as el
from apuracao import locais as lc
from apuracao.eleitorado import SECTION_KEY

VOTE_COLS = ["VOTOS_CANDIDATO", "VOTOS_NOMINAIS", "VOTOS_LEGENDA", "VOTOS_BRANCOS", "VOTOS_NULOS",
             "VOTOS_ANULADOS_SEPARADO", "VOTOS_APURADOS"]
ZONE_KEY = ["CD_MUNICIPIO", "NR_ZONA"]
BAIRRO_KEY = ["CD_MUNICIPIO", "_BAIRRO_N"]
SECTION_STATUS_COL = "STATUS_SECAO"
ALWAYS_ELECTORATE_YEARS = (2024, lc.NEW_YEAR)


def no_register(base: int, new: int = lc.NEW_YEAR) -> str:
    return f"SEM_CADASTRO_{base}_E_{new}"


def legend(base: int, new: int = lc.NEW_YEAR) -> list[tuple[str, object]]:
    return [
        (f"MUDANCA_{base}_{new}", f"mudanças entre o cadastro de eleitorado de {base} e o de {new} (--comparar-com)"),
        ("Chave do local", "município + zona + nº do local (o nº só é único dentro da zona)"),
        ("Destaque amarelo", f"local/seção com alguma mudança entre os cadastros de {base} e {new}"),
        ("Destaque vermelho", f"desativado em {new}, seção extinta ou local sem cadastro em {base} e {new}"),
        ("MANTIDO", "mesma chave, nome, endereço e ponto (até 150 m) nos dois anos"),
        ("RENOMEADO / ENDERECO_ALTERADO", "nome/endereço diferente (comparado só por letras e dígitos)"),
        ("DESLOCADO", f"coordenadas a mais de 150 m entre {base} e {new}"),
        (f"{lc.desativado(new)} / {lc.novo(new)}", "chave presente em um só dos cadastros"),
        ("SECOES_SAIRAM / SECOES_ENTRARAM", f"seções que trocaram de local entre {base} e {new}"),
        (f"REMANEJAMENTO_{new}", f"seções remanejadas em {new} (NR_LOCAL_VOTACAO_ORIGINAL diferente)"),
        (f"TEMPORARIO_{new}", f"local do tipo Temporário no cadastro de {new}"),
        (no_register(base, new), f"local do resultado ausente dos cadastros de {base} e de {new}"),
        (f"SITUACAO_LOCAL_{new} = BLOQUEADO", f"situação do local no cadastro {new}; não é mudança de local"),
        ("VAR_ELEITORADO / VAR_ELEITORADO_PCT", f"variação do eleitorado de {base} para {new}"),
        ("Eleitorado por zona/bairro", "eleitorado inteiro da zona/bairro em cada ano, não só dos locais com voto"),
    ]


@dataclass
class Registers:
    """Cadastros de eleitorado por ano (seções), já restritos à área da consulta."""

    sections: dict[int, pl.DataFrame]
    result_year: int
    base_year: int
    new_year: int = lc.NEW_YEAR
    places: dict[int, pl.DataFrame] = field(init=False)

    def __post_init__(self) -> None:
        for year in (self.base_year, self.new_year):
            if year not in self.sections:
                raise v.TseDataError(f"cadastro de eleitorado de {year} ausente")
        self.places = {y: el.places(s) for y, s in self.sections.items()}

    @property
    def electorate_years(self) -> list[int]:
        return sorted({self.base_year, *ALWAYS_ELECTORATE_YEARS} & set(self.places))

    @property
    def change_col(self) -> str:
        return lc.change_col(self.base_year, self.new_year)


@dataclass
class Report:
    summary: list[tuple[str, object]] = field(default_factory=list)  # aba "Resumo" (valores tipados)
    sheets: dict[str, pl.DataFrame] = field(default_factory=dict)
    highlight: dict[str, str] = field(default_factory=dict)  # aba -> coluna de status


# --------------------------------------------------------------------------
# Totalização
# --------------------------------------------------------------------------
def tally_sections(votes: pl.LazyFrame, turno: int, office: str, number: int, muni: int | None) -> pl.DataFrame:
    """Votos por seção (todas as seções do cargo na área, inclusive com 0 voto do candidato)."""
    cond = (pl.col("NR_TURNO") == turno) & v.office_filter(office)
    if muni is not None:
        cond &= pl.col("CD_MUNICIPIO") == muni
    proportional = v.normalize_text(office) in v.PROPORTIONAL_OFFICES
    names = [c for c in ("NM_MUNICIPIO", "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO") if c in votes.collect_schema()]
    df = (
        votes.filter(cond)
        .with_columns(v.classify_vote(proportional))
        .group_by(v.LOCAL_KEY + ["NR_SECAO"])
        .agg([pl.col(c).first() for c in names] + v._vote_breakdown(number))
        .sort(v.LOCAL_KEY + ["NR_SECAO"])
        .collect()
    )
    if df.is_empty():
        raise v.TseDataError(f"Nenhuma seção com votos para '{office}', turno {turno} na área pedida.")
    return df


def aggregate(sections: pl.DataFrame, keys: list[str], firsts: list[str]) -> pl.DataFrame:
    return v._with_shares(
        sections.group_by(keys)
        .agg([pl.col(c).first() for c in firsts] + [pl.col(c).sum() for c in VOTE_COLS]
             + [pl.len().alias("N_SECOES")])
    )


def _with_electorate(df: pl.DataFrame, keys: list[str], regs: Registers) -> pl.DataFrame:
    for year in regs.electorate_years:
        df = df.join(
            regs.places[year].group_by(keys).agg(pl.col("QT_ELEITORES").sum().alias(f"ELEITORADO_{year}")),
            on=keys, how="left",
        )
    base, new = pl.col(f"ELEITORADO_{regs.base_year}"), pl.col(f"ELEITORADO_{regs.new_year}")
    return df.with_columns(
        (new - base).alias("VAR_ELEITORADO"),
        pl.when(base > 0).then((100 * (new - base) / base).round(2)).otherwise(None).alias("VAR_ELEITORADO_PCT"),
    )


def _place_attributes(keys: pl.DataFrame, regs: Registers) -> pl.DataFrame:
    """Bairro/endereço/coordenadas por local: ano do resultado, 2026, ano-base, 2024."""
    order = [regs.result_year, regs.new_year, regs.base_year, 2024]
    years = [y for i, y in enumerate(order) if y in regs.places and y not in order[:i]]
    attrs = ["NM_BAIRRO", "_BAIRRO_N", "DS_ENDERECO", "NR_LATITUDE", "NR_LONGITUDE"]
    out = keys
    for y in years:
        out = out.join(regs.places[y].select(v.LOCAL_KEY + [pl.col(a).alias(f"{a}__{y}") for a in attrs]),
                       on=v.LOCAL_KEY, how="left")
    fonte = [pl.when(pl.col(f"_BAIRRO_N__{y}").is_not_null()).then(pl.lit(str(y))) for y in years]
    out = out.with_columns(
        [pl.coalesce([f"{a}__{y}" for y in years]).alias(a) for a in attrs]
        + [pl.coalesce(fonte).alias("FONTE_CADASTRO")]
    )
    return out.select(v.LOCAL_KEY + attrs + ["FONTE_CADASTRO"])


# --------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------
def build_report(sections: pl.DataFrame, regs: Registers, uf: str, header: list[tuple[str, object]],
                 tre: pl.DataFrame | None = None) -> Report:
    base, new, chg = regs.base_year, regs.new_year, regs.change_col
    missing = no_register(base, new)
    sec_cmp = lc.compare_sections(regs.sections[base], regs.sections[new], base, new)
    place_cmp = lc.compare_places(regs.places[base], regs.places[new], sec_cmp, base, new)

    attrs = _place_attributes(sections.select(v.LOCAL_KEY).unique(), regs)
    sec = sections.join(attrs, on=v.LOCAL_KEY, how="left")

    # ---- por local
    local_firsts = ["NM_MUNICIPIO", "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO", "NM_BAIRRO", "_BAIRRO_N",
                    "NR_LATITUDE", "NR_LONGITUDE", "FONTE_CADASTRO"]
    local_new = f"LOCAL_{new}"
    by_local = _with_electorate(
        aggregate(sec, v.LOCAL_KEY, [c for c in local_firsts if c in sec.columns]), v.LOCAL_KEY, regs,
    ).join(
        place_cmp.select(v.LOCAL_KEY + [chg, local_new, f"SITUACAO_LOCAL_{new}", "DISTANCIA_M",
                                        "SECOES_SAIRAM", "SECOES_ENTRARAM"]),
        on=v.LOCAL_KEY, how="left",
    ).with_columns(pl.col(chg).fill_null(missing)).with_columns(
        pl.when(pl.col(chg) == lc.MANTIDO).then(None).otherwise(pl.col(local_new)).alias(local_new)
    ).sort("VOTOS_CANDIDATO", "VOTOS_VALIDOS", descending=True)

    # ---- por zona (eleitorado da zona inteira, de cada ano)
    by_zone = _with_electorate(aggregate(sec, ZONE_KEY, ["NM_MUNICIPIO"]), ZONE_KEY, regs).join(
        by_local.group_by(ZONE_KEY).agg(
            (pl.col(chg) != lc.MANTIDO).sum().alias("LOCAIS_COM_MUDANCA"), pl.len().alias("N_LOCAIS")),
        on=ZONE_KEY, how="left",
    ).sort(ZONE_KEY)

    # ---- por bairro (chave = bairro normalizado dentro do município)
    bairro_label = (
        pl.concat([p.select(BAIRRO_KEY + ["NM_BAIRRO"]) for p in regs.places.values()]).group_by(BAIRRO_KEY)
        .agg(pl.col("NM_BAIRRO").drop_nulls().mode().sort().first().alias("BAIRRO"))
    )
    by_bairro = _with_electorate(
        aggregate(sec.filter(pl.col("_BAIRRO_N").is_not_null()), BAIRRO_KEY, ["NM_MUNICIPIO"]), BAIRRO_KEY, regs,
    ).join(bairro_label, on=BAIRRO_KEY, how="left").join(
        by_local.group_by(BAIRRO_KEY).agg(
            pl.len().alias("N_LOCAIS"), (pl.col(chg) != lc.MANTIDO).sum().alias("LOCAIS_COM_MUDANCA")),
        on=BAIRRO_KEY, how="left",
    ).sort("VOTOS_CANDIDATO", descending=True)
    no_bairro = sec.filter(pl.col("_BAIRRO_N").is_null())

    # ---- por seção
    by_section = v._with_shares(sec).join(
        sec_cmp.select(SECTION_KEY + [f"LOCAL_{base}", local_new, SECTION_STATUS_COL, "REMANEJADA"]),
        on=SECTION_KEY, how="left",
    ).with_columns(pl.col(SECTION_STATUS_COL).fill_null(missing)).sort(v.LOCAL_KEY + ["NR_SECAO"])

    # ---- mudanças e inconsistências
    place_changes = place_cmp.filter(pl.col(chg) != lc.MANTIDO)
    section_changes = sec_cmp.filter((pl.col(SECTION_STATUS_COL) != lc.MANTIDO) | pl.col("REMANEJADA"))
    issues = [lc.inconsistencies(place_cmp, regs.places[base], regs.places[new], uf, base, new)]
    if regs.result_year in regs.places:
        vote_places = sections.group_by(v.LOCAL_KEY).agg(pl.col("NM_LOCAL_VOTACAO").first())
        issues.append(lc.missing_from_register(vote_places, regs.places[regs.result_year], regs.result_year,
                                               base, new))
    if tre is not None:
        issues.append(lc.compare_with_tre(regs.places[new], tre, base, new))
    issues_df = pl.concat(issues, how="vertical")

    # ---- resumo
    tot = by_local.select([pl.col(c).sum() for c in VOTE_COLS + ["N_SECOES"]]).row(0, named=True)
    validos = tot["VOTOS_NOMINAIS"] + tot["VOTOS_LEGENDA"]
    summary: list[tuple[str, object]] = list(header) + [
        ("Comparação de locais", f"cadastro {base} × cadastro {new}"),
        ("Votos do candidato", tot["VOTOS_CANDIDATO"]),
        ("Votos válidos (nominais + legenda)", validos),
        ("% sobre válidos", round(100 * tot["VOTOS_CANDIDATO"] / validos, 3) if validos else None),
        ("Brancos", tot["VOTOS_BRANCOS"]), ("Nulos", tot["VOTOS_NULOS"]), ("Apurados", tot["VOTOS_APURADOS"]),
        ("Seções", tot["N_SECOES"]), ("Locais", by_local.height), ("Zonas", by_zone.height),
        ("Bairros", by_bairro.height),
        ("Seções sem bairro no cadastro", no_bairro.height),
    ]
    summary += [(f"Eleitorado {y} (cadastro, área)", int(regs.places[y]["QT_ELEITORES"].sum()))
                for y in regs.electorate_years]
    summary += [
        (f"Locais do resultado ({regs.result_year}) com mudança {base}→{new}",
         by_local.filter(pl.col(chg) != lc.MANTIDO).height),
        (f"Seções do resultado ({regs.result_year}) que mudaram de local {base}→{new}",
         by_section.filter(pl.col(SECTION_STATUS_COL) == "MUDOU_DE_LOCAL").height),
        ("Inconsistências apontadas", issues_df.height),
    ]
    summary += [(f"  {t}", n) for t, n in issues_df.group_by("TIPO").len().sort("TIPO").iter_rows()]
    summary += [("", None), ("LEGENDA", None)] + legend(base, new)

    rep = Report(summary=summary)
    rep.sheets["Por local"] = _public(by_local)
    rep.sheets["Por zona"] = _public(by_zone)
    rep.sheets["Por bairro"] = _public(by_bairro.select(["BAIRRO"] + [c for c in by_bairro.columns if c != "BAIRRO"]))
    rep.sheets["Por secao"] = _public(by_section)
    rep.sheets["Mudancas locais"] = _public(place_changes)
    rep.sheets["Mudancas secoes"] = _public(section_changes)
    rep.sheets["Inconsistencias"] = issues_df
    rep.highlight = {"Por local": chg, "Mudancas locais": chg,
                     "Por secao": SECTION_STATUS_COL, "Mudancas secoes": SECTION_STATUS_COL}
    return rep


def _public(df: pl.DataFrame) -> pl.DataFrame:
    """Remove colunas auxiliares (prefixo _) antes de ir para a planilha."""
    return df.select([c for c in df.columns if not c.startswith("_")])


def provenance_sheet(config: dict[str, object], files: list[Path]) -> pl.DataFrame:
    rows: list[tuple[str, str]] = [(f"config.{k}", str(val)) for k, val in config.items()]
    for f in files:
        prov = f.with_suffix(".proveniencia.json")
        rows.append((f"arquivo", f.name))
        if prov.exists():
            for k, val in json.loads(prov.read_text()).items():
                rows.append((f"  {f.stem}.{k}", str(val)))
        else:
            rows.append((f"  {f.stem}", "sem .proveniencia.json"))
    return pl.DataFrame({"ITEM": [r[0] for r in rows], "VALOR": [r[1] for r in rows]})


# --------------------------------------------------------------------------
# XLSX
# --------------------------------------------------------------------------
LONG_TEXT_PREFIXES = ("SECOES_", "VALOR_", "MUDANCA_", "DETALHE")
COORD_PREFIXES = ("NR_LATITUDE", "NR_LONGITUDE")
RED_WORDS = ("DESATIVADO", "EXTINTA", "SEM_CADASTRO")


def _is_long_text(name: str, df: pl.DataFrame) -> bool:
    """Colunas de texto longo (listas de seções, detalhes, local atual) ganham largura fixa."""
    return df.schema[name] == pl.String and (name.startswith(LONG_TEXT_PREFIXES + ("LOCAL_",)) or name == "VALOR")


def _col_letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = string.ascii_uppercase[r] + s
    return s


def _write_summary(wb: Workbook, rows: list[tuple[str, object]]) -> None:
    ws = wb.add_worksheet("Resumo")
    bold = wb.add_format({"bold": True})
    num = wb.add_format({"num_format": "#,##0"})
    dec = wb.add_format({"num_format": "0.000"})
    ws.write_row(0, 0, ["ITEM", "VALOR"], bold)
    for r, (item, value) in enumerate(rows, start=1):
        ws.write(r, 0, item, bold if item.isupper() and item and value is None else None)
        if isinstance(value, bool) or value is None:
            ws.write(r, 1, "" if value is None else str(value))
        elif isinstance(value, int):
            ws.write_number(r, 1, value, num)
        elif isinstance(value, float):
            ws.write_number(r, 1, value, dec)
        else:
            ws.write_string(r, 1, str(value))
    ws.set_column(0, 0, 44)
    ws.set_column(1, 1, 80)
    ws.freeze_panes(1, 0)


def write_workbook(path: Path, report: Report) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Workbook(str(path)) as wb:
        yellow = wb.add_format({"bg_color": "#FFF2CC"})
        red = wb.add_format({"bg_color": "#F8CBAD"})
        if report.summary:
            _write_summary(wb, report.summary)
        for name, df in report.sheets.items():
            fmt: dict[str, str] = {c: "0.0000000" for c in df.columns if c.startswith(COORD_PREFIXES)}
            fmt.update({c: "0.00" for c in df.columns if c.startswith("PCT") or c.endswith("_PCT")})
            fmt.update({c: "#,##0" for c in df.columns
                        if (c.startswith(("VOTOS_", "ELEITORADO_", "QT_")) or c == "VAR_ELEITORADO")
                        and df.schema[c].is_integer()})
            df.write_excel(workbook=wb, worksheet=name, autofit=True, freeze_panes=(1, 0),
                           autofilter=True, column_formats=fmt or None, header_format={"bold": True})
            ws = wb.get_worksheet_by_name(name)
            for i, c in enumerate(df.columns):
                if _is_long_text(c, df):
                    ws.set_column(i, i, 60 if name in ("Resumo",) else 45)
            status = report.highlight.get(name)
            if status and status in df.columns and df.height:
                col = _col_letter(df.columns.index(status))
                last_row, last_col = df.height, df.width - 1
                red_rule = "OR(" + ",".join(f'ISNUMBER(SEARCH("{w}",${col}2))' for w in RED_WORDS) + ")"
                ws.conditional_format(1, 0, last_row, last_col,
                                      {"type": "formula", "criteria": f"={red_rule}", "format": red,
                                       "stop_if_true": True})
                ws.conditional_format(1, 0, last_row, last_col,
                                      {"type": "formula",
                                       "criteria": f'=AND(${col}2<>"{lc.MANTIDO}",${col}2<>"")',
                                       "format": yellow})
    return path
