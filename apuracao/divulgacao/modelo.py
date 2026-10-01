"""Parse puro (sem I/O) dos JSON da divulgação do TSE para estruturas Python/Polars.

Arquivos (especificações do TSE; nomes conferidos no simulado de 2026):
  EA11  comum/config/ele-c.json                       ciclo, pleitos, eleições, cargos, modelos de diretório
  EA12  <ciclo>/<e>/config/mun-e<e:06>-cm.json        municípios por UF (código TSE, código IBGE, zonas)
  EA14  <ciclo>/<e>/dados/br/br-e<e:06>-ab.json       acompanhamento por UF (+ linha br)
  EA15  <ciclo>/<e>/dados/<uf>/<uf>-e<e:06>-ab.json   acompanhamento por município (+ linha uf)
  EA20  <ciclo>/<e>/dados/<uf>/<abr>-c<cargo:04>-e<e:06>-u.json   resultado unificado (abr = uf ou uf+mun)

Todos os números vêm como texto, com vírgula decimal ("9,04"); os campos com sufixo
"n" (ex.: pvapn) trazem o percentual com mais casas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import polars as pl

CARGOS_MAJORITARIOS_TP = "1"
CARGOS_PROPORCIONAIS_TP = "2"


# --------------------------------------------------------------------------
# Conversões
# --------------------------------------------------------------------------
def to_int(value: Any) -> int | None:
    f = to_float(value)
    return None if f is None else int(f)


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def to_datetime(dt: str | None, ht: str | None) -> datetime | None:
    if not dt:
        return None
    try:
        return datetime.strptime(f"{dt} {ht or '00:00:00'}", "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None


def _pct(d: dict, key: str) -> float | None:
    """Percentual preferindo o campo de alta precisão (<key>n)."""
    return to_float(d.get(f"{key}n", d.get(key)))


# --------------------------------------------------------------------------
# EA11 — configuração de eleições
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Cargo:
    codigo: int
    nome: str
    proporcional: bool


@dataclass(frozen=True)
class Eleicao:
    codigo: int
    codigo_2t: int | None
    nome: str
    turno: int
    cargos: tuple[Cargo, ...]

    def cargo(self, codigo: int) -> Cargo | None:
        return next((c for c in self.cargos if c.codigo == codigo), None)


@dataclass(frozen=True)
class ConfigEleicoes:
    ciclo: str
    pleito: int
    gerado_em: datetime | None
    eleicoes: tuple[Eleicao, ...]
    diretorios: dict[str, str] = field(default_factory=dict)  # tp -> modelo "<base>/<ambiente>/..."

    def por_cargo(self, cargo: int, turno: int = 1) -> Eleicao | None:
        """Eleição (1º turno) que contém o cargo; para o 2º turno devolve o código cdt2."""
        for e in self.eleicoes:
            if e.cargo(cargo) is not None:
                if turno == 1:
                    return e
                if e.codigo_2t is None:
                    return None
                return Eleicao(e.codigo_2t, None, e.nome.replace("1º Turno", "2º Turno"), 2, e.cargos)
        return None


def parse_config(data: dict) -> ConfigEleicoes:
    """EA11. Considera o primeiro pleito da lista (um pleito por ambiente em 2026)."""
    pleito = data["pl"][0]
    eleicoes = []
    for e in pleito["e"]:
        cargos = []
        for abr in e.get("abr", []):
            for c in abr.get("cp", []):
                cargos.append(Cargo(int(c["cd"]), c["ds"], c.get("tp") == CARGOS_PROPORCIONAIS_TP))
        eleicoes.append(Eleicao(int(e["cd"]), to_int(e.get("cdt2")), e.get("nm", ""), int(e.get("t", 1)),
                                tuple(cargos)))
    return ConfigEleicoes(
        ciclo=pleito["c"], pleito=int(pleito["cd"]), gerado_em=to_datetime(data.get("dg"), data.get("hg")),
        eleicoes=tuple(eleicoes), diretorios={a["tp"]: a["dir"] for a in data.get("arq", [])},
    )


# --------------------------------------------------------------------------
# EA12 — municípios
# --------------------------------------------------------------------------
MUNICIPIOS_SCHEMA = {"UF": pl.String, "CD_MUNICIPIO": pl.Int64, "CD_MUNICIPIO_IBGE": pl.Int64,
                     "NM_MUNICIPIO": pl.String, "CAPITAL": pl.Boolean, "ZONAS": pl.String}


def parse_municipios(data: dict) -> pl.DataFrame:
    rows = [
        {"UF": uf["cd"].upper(), "CD_MUNICIPIO": int(m["cd"]), "CD_MUNICIPIO_IBGE": to_int(m.get("cdi")),
         "NM_MUNICIPIO": m["nm"], "CAPITAL": m.get("c") == "s",
         "ZONAS": ",".join(str(int(z)) for z in m.get("z", []))}
        for uf in data.get("abr", []) for m in uf.get("mu", [])
    ]
    return pl.DataFrame(rows, schema=MUNICIPIOS_SCHEMA)


# --------------------------------------------------------------------------
# Blocos comuns (s = seções, e = eleitorado, v = votos)
# --------------------------------------------------------------------------
def _secoes_eleitorado(d: dict) -> dict[str, Any]:
    s, e = d.get("s", {}), d.get("e", {})
    return {
        "SECOES_TOTAL": to_int(s.get("ts")), "SECOES_TOTALIZADAS": to_int(s.get("st")),
        "PCT_SECOES_TOTALIZADAS": _pct(s, "pst"),
        "ELEITORADO": to_int(e.get("te")), "COMPARECIMENTO": to_int(e.get("c")), "PCT_COMPARECIMENTO": _pct(e, "pc"),
        "ABSTENCAO": to_int(e.get("a")), "PCT_ABSTENCAO": _pct(e, "pa"),
    }


def _abrangencia(tpabr: str, cdabr: str, uf: str) -> dict[str, Any]:
    tp = {"mu": "mun"}.get(tpabr, tpabr)
    return {"ABRANGENCIA": tp, "UF": (uf if tp == "mun" else cdabr).upper(),
            "CD_MUNICIPIO": int(cdabr) if tp == "mun" else None}


# --------------------------------------------------------------------------
# EA14/EA15 — acompanhamento
# --------------------------------------------------------------------------
ACOMPANHAMENTO_SCHEMA = {
    "ELEICAO": pl.Int64, "ABRANGENCIA": pl.String, "UF": pl.String, "CD_MUNICIPIO": pl.Int64,
    "DT_TOTALIZACAO": pl.Datetime, "ANDAMENTO": pl.String,
    "SECOES_TOTAL": pl.Int64, "SECOES_TOTALIZADAS": pl.Int64, "PCT_SECOES_TOTALIZADAS": pl.Float64,
    "ELEITORADO": pl.Int64, "COMPARECIMENTO": pl.Int64, "PCT_COMPARECIMENTO": pl.Float64,
    "ABSTENCAO": pl.Int64, "PCT_ABSTENCAO": pl.Float64,
}


def parse_acompanhamento(data: dict, uf: str) -> pl.DataFrame:
    """EA14 (uf='br') ou EA15 (uf='rj'): uma linha por abrangência com a hora da última totalização."""
    rows = []
    for a in data.get("abr", []):
        rows.append({"ELEICAO": int(data["ele"]), **_abrangencia(a["tpabr"], a["cdabr"], uf),
                     "DT_TOTALIZACAO": to_datetime(a.get("dt"), a.get("ht")), "ANDAMENTO": a.get("and"),
                     **_secoes_eleitorado(a)})
    return pl.DataFrame(rows, schema=ACOMPANHAMENTO_SCHEMA)


# --------------------------------------------------------------------------
# EA20 — resultado unificado
# --------------------------------------------------------------------------
TOTAIS_SCHEMA = {
    "ELEICAO": pl.Int64, "TURNO": pl.Int64, "CARGO": pl.Int64, "DS_CARGO": pl.String, "VAGAS": pl.Int64,
    "QUOCIENTE_ELEITORAL": pl.Int64, "ABRANGENCIA": pl.String, "UF": pl.String, "CD_MUNICIPIO": pl.Int64,
    "DT_TOTALIZACAO": pl.Datetime, "TOTALIZACAO_FINAL": pl.Boolean, "MATEMATICAMENTE_DEFINIDA": pl.Boolean,
    "SECOES_TOTAL": pl.Int64, "SECOES_TOTALIZADAS": pl.Int64, "PCT_SECOES_TOTALIZADAS": pl.Float64,
    "ELEITORADO": pl.Int64, "COMPARECIMENTO": pl.Int64, "PCT_COMPARECIMENTO": pl.Float64,
    "ABSTENCAO": pl.Int64, "PCT_ABSTENCAO": pl.Float64,
    "VOTOS_TOTAL": pl.Int64, "VALIDOS": pl.Int64, "PCT_VALIDOS": pl.Float64,
    "NOMINAIS": pl.Int64, "LEGENDA": pl.Int64, "BRANCOS": pl.Int64, "PCT_BRANCOS": pl.Float64,
    "NULOS": pl.Int64, "PCT_NULOS": pl.Float64, "ANULADOS": pl.Int64,
    "ANULADOS_SUB_JUDICE": pl.Int64, "PCT_ANULADOS_SUB_JUDICE": pl.Float64, "IDG": pl.String,
}
CANDIDATOS_SCHEMA = {
    "ELEICAO": pl.Int64, "CARGO": pl.Int64, "ABRANGENCIA": pl.String, "UF": pl.String, "CD_MUNICIPIO": pl.Int64,
    "NUMERO": pl.Int64, "NOME_URNA": pl.String, "NOME": pl.String, "SQ_CANDIDATO": pl.Int64,
    "PARTIDO": pl.String, "NR_PARTIDO": pl.Int64, "FEDERACAO": pl.String, "AGREMIACAO": pl.String,
    "COMPOSICAO": pl.String, "VOTOS": pl.Int64, "PCT_VALIDOS": pl.Float64, "SEQ": pl.Int64,
    "SITUACAO": pl.String, "ELEITO": pl.Boolean, "DESTINACAO": pl.String, "VICES": pl.String,
}
PARTIDOS_SCHEMA = {
    "ELEICAO": pl.Int64, "CARGO": pl.Int64, "ABRANGENCIA": pl.String, "UF": pl.String, "CD_MUNICIPIO": pl.Int64,
    "NR_PARTIDO": pl.Int64, "PARTIDO": pl.String, "FEDERACAO": pl.String, "AGREMIACAO": pl.String,
    "VOTOS_NOMINAIS": pl.Int64, "VOTOS_LEGENDA": pl.Int64, "VOTOS_TOTAL": pl.Int64, "VAGAS_AGREMIACAO": pl.Int64,
}


@dataclass
class Resultado:
    """EA20 de um cargo numa abrangência."""

    totais: pl.DataFrame
    candidatos: pl.DataFrame
    partidos: pl.DataFrame


def parse_resultado(data: dict, uf: str) -> Resultado:
    ab = _abrangencia(data["tpabr"], data["cdabr"], uf)
    v = data.get("v", {})
    base = {"ELEICAO": int(data["ele"]), **ab}
    totals, cands, parts = [], [], []
    for c in data.get("carg", []):
        cargo = int(c["cd"])
        feds = {p: f.get("sg") or f.get("nm") for f in c.get("fed", []) for p in f.get("npar", [])}
        totals.append({
            **base, "TURNO": to_int(data.get("t")), "CARGO": cargo, "DS_CARGO": c.get("nmn"),
            "VAGAS": to_int(c.get("nv")), "QUOCIENTE_ELEITORAL": to_int(c.get("qe")),
            "DT_TOTALIZACAO": to_datetime(data.get("dt"), data.get("ht")),
            "TOTALIZACAO_FINAL": data.get("tf") == "s", "MATEMATICAMENTE_DEFINIDA": data.get("esae") == "s",
            **_secoes_eleitorado(data),
            "VOTOS_TOTAL": to_int(v.get("tv")), "VALIDOS": to_int(v.get("vv")), "PCT_VALIDOS": _pct(v, "pvv"),
            "NOMINAIS": to_int(v.get("vnom")), "LEGENDA": to_int(v.get("vl")) or 0,
            "BRANCOS": to_int(v.get("vb")), "PCT_BRANCOS": _pct(v, "pvb"),
            "NULOS": to_int(v.get("tvn")), "PCT_NULOS": _pct(v, "ptvn"), "ANULADOS": to_int(v.get("van")),
            "ANULADOS_SUB_JUDICE": to_int(v.get("vansj")), "PCT_ANULADOS_SUB_JUDICE": _pct(v, "pvansj"),
            "IDG": data.get("idg"),
        })
        for a in c.get("agr", []):
            for p in a.get("par", []):
                fed = feds.get(p.get("n"))
                nominais, legenda = to_int(p.get("tvtn")), to_int(p.get("tvtl"))
                parts.append({**base, "CARGO": cargo, "NR_PARTIDO": to_int(p.get("n")), "PARTIDO": p.get("sg"),
                              "FEDERACAO": fed, "AGREMIACAO": a.get("nm"), "VOTOS_NOMINAIS": nominais,
                              "VOTOS_LEGENDA": legenda,
                              "VOTOS_TOTAL": None if nominais is None and legenda is None else (nominais or 0) + (legenda or 0),
                              "VAGAS_AGREMIACAO": to_int(a.get("vag"))})
                for k in p.get("cand", []):
                    cands.append({
                        **base, "CARGO": cargo, "NUMERO": to_int(k.get("n")), "NOME_URNA": k.get("nmu"),
                        "NOME": k.get("nm"), "SQ_CANDIDATO": to_int(k.get("sqcand")),
                        "PARTIDO": p.get("sg"), "NR_PARTIDO": to_int(p.get("n")), "FEDERACAO": fed,
                        "AGREMIACAO": a.get("nm"), "COMPOSICAO": a.get("com"),
                        "VOTOS": to_int(k.get("vap")) or 0, "PCT_VALIDOS": _pct(k, "pvap"), "SEQ": to_int(k.get("seq")),
                        "SITUACAO": k.get("st"), "ELEITO": k.get("e") == "s", "DESTINACAO": k.get("dvt"),
                        "VICES": "; ".join(f"{x.get('nmu')} ({x.get('sgp')})" for x in k.get("vs", [])) or None,
                    })
    return Resultado(pl.DataFrame(totals, schema=TOTAIS_SCHEMA), pl.DataFrame(cands, schema=CANDIDATOS_SCHEMA),
                     pl.DataFrame(parts, schema=PARTIDOS_SCHEMA))
