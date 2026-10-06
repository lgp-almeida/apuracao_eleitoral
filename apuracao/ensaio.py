"""Ensaio geral: a apuração real de 2022 (RJ) tocada de novo, em JSON no formato do TSE.

Cada seção de 2022 tem a hora em que entrou na totalização (`DT_PRIM_TOT_PARCIAL_HOR_TSE`). Um
relógio virtual percorre a noite da eleição (acelerado) e `SessaoEnsaio` responde, como o servidor
do TSE, os arquivos EA11/EA12 (configuração e municípios do simulado de 2026), EA14/EA15
(acompanhamento, com a hora da última totalização de cada abrangência) e EA20 (resultado de cada
cargo na UF, em cada município e, para Presidente, no Brasil) com o que já estava apurado naquela
hora — com ETag/304 como o TSE. O `Coletor` de verdade coleta disso, e o site lê o que ele grava:
é a noite de 4/10 em miniatura, sem tocar no TSE.

Cargos: Presidente (UF, municípios e Brasil), Governador, Senador, Dep. Federal e Dep. Estadual.
Validade dos votos: a destinação oficial de cada candidato (`votacao_candidato_munzona`); votos de
candidato anulado vão para "anulados". Presidente: todos válidos (não há o arquivo da UF para ele).
Situação dos candidatos (st/e): vazia durante a apuração; a oficial quando a UF termina.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

import votos_por_local_votacao as v
from apuracao import cadeiras as cd
from apuracao import projecao as pj
from apuracao.bairros import numero_partido

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "divulgacao"
ELEICAO_FEDERAL, ELEICAO_ESTADUAL = 21270, 21272  # códigos do simulado de 2026 (ele-c.json dos recortes)
ELEICAO_FEDERAL_2T, ELEICAO_ESTADUAL_2T = 21271, 21273  # os cdt2 do mesmo ele-c.json (2º turno, rodada 43)
FEDERAIS = (ELEICAO_FEDERAL, ELEICAO_FEDERAL_2T)
CARGOS_POR_TURNO = {1: (1, 3, 5, 6, 7), 2: (1, 3)}  # no 2º turno só Presidente e Governador
NOMES = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual"}
ESPECIAIS = (95, 96, 97)
SITUACAO = {"ELEITO": "Eleito", "ELEITO POR QP": "Eleito por QP", "ELEITO POR MÉDIA": "Eleito por média",
            "SUPLENTE": "Suplente", "NÃO ELEITO": "Não eleito", "2º TURNO": "2º turno"}


def _br(x: float, casas: int = 2) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _pct(parte: float, todo: float) -> tuple[str, str]:
    p = 100 * parte / todo if todo else 0.0
    return _br(p), _br(p, 9)


# --------------------------------------------------------------------------
# Relógio virtual
# --------------------------------------------------------------------------
class Relogio:
    """Hora da noite de 2022 correspondente a agora, acelerada `velocidade` vezes."""

    def __init__(self, inicio: datetime, fim: datetime, velocidade: float = 60.0) -> None:
        self.inicio, self.fim, self.velocidade = inicio, fim, velocidade
        self._t0 = time.monotonic()
        self._fixo: datetime | None = None

    def agora(self) -> datetime:
        if self._fixo is not None:
            return self._fixo
        t = self.inicio + timedelta(seconds=(time.monotonic() - self._t0) * self.velocidade)
        return min(t, self.fim)

    def fixar(self, t: datetime | None) -> None:
        """Congela o relógio numa hora (testes) ou devolve ao tempo corrido (None)."""
        self._fixo = t

    @property
    def terminou(self) -> bool:
        return self.agora() >= self.fim


# --------------------------------------------------------------------------
# Dados de 2022
# --------------------------------------------------------------------------
@dataclass
class DadosCargo:
    cargo: int
    eleicao: int
    vagas: int
    secoes: pl.DataFrame      # SG_UF, CD_MUNICIPIO, T, APTOS, COMPARECIMENTO, ABSTENCOES (uma linha por seção)
    votos: pl.DataFrame       # SG_UF, CD_MUNICIPIO, T, NR_VOTAVEL, QT_VOTOS (por seção e votável)
    candidatos: pl.DataFrame  # NUMERO, NOME_URNA, NOME, SQ, PARTIDO, NR_PARTIDO, FEDERACAO, VALIDO, SITUACAO_FINAL
    partidos: pl.DataFrame    # NR_PARTIDO, PARTIDO, FEDERACAO


@dataclass
class Reconstituicao:
    uf: str
    cargos: dict[int, DadosCargo]
    inicio: datetime
    fim: datetime
    turno: int = 1
    _cache: dict[tuple, Any] = field(default_factory=dict)
    _trava: threading.Lock = field(default_factory=threading.Lock)

    def fotografia(self, cargo: int, t: datetime) -> dict[str, pl.DataFrame]:
        """O que estava apurado na hora `t` (arredondada ao minuto), por município e no total."""
        tq = t.replace(second=0, microsecond=0)
        chave = (cargo, tq)
        with self._trava:
            if chave in self._cache:
                return self._cache[chave]
        d = self.cargos[cargo]
        s = d.secoes.with_columns((pl.col("T") <= tq).alias("FEITA"))
        feitas = s.filter(pl.col("FEITA"))
        grupos = {"mun": ["CD_MUNICIPIO"], "uf": ["SG_UF"]}
        foto: dict[str, pl.DataFrame] = {}
        for nome, g in grupos.items():
            tot = s.group_by(g).agg(pl.len().alias("TS"), pl.col("APTOS").sum().alias("TE"))
            fe = feitas.group_by(g).agg(pl.len().alias("ST"), pl.col("APTOS").sum().alias("EST"),
                                        pl.col("COMPARECIMENTO").sum().alias("C"), pl.col("ABSTENCOES").sum().alias("A"),
                                        pl.col("T").max().alias("DT"))
            foto[f"secoes_{nome}"] = tot.join(fe, on=g, how="left").with_columns(
                pl.col("ST", "EST", "C", "A").fill_null(0))
            foto[f"votos_{nome}"] = (d.votos.filter(pl.col("T") <= tq).group_by(g + ["NR_VOTAVEL"])
                                     .agg(pl.col("QT_VOTOS").sum()))
        with self._trava:
            if len(self._cache) > 40:
                self._cache.clear()
            self._cache[chave] = foto
        return foto


def _secoes_e_votos(det: pl.LazyFrame, votos: pl.LazyFrame, cargo: int, nome: str, uf: str | None, turno: int = 1
                    ) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Seções (com hora e eleitorado) e votos por seção de um cargo; `uf=None` = todas as UFs."""
    chave = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
    filtro_uf = (pl.col("SG_UF") == uf) if uf else pl.lit(True)
    secoes = (det.filter((pl.col("NR_TURNO") == turno) & (pl.col("CD_CARGO") == cargo) & filtro_uf)
              .select(chave + [pl.col("DT_PRIM_TOT_PARCIAL_HOR_TSE").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M:%S",
                                                                                   strict=False).alias("T"),
                               pl.col("QT_APTOS").alias("APTOS"), "QT_COMPARECIMENTO", "QT_ABSTENCOES"])
              .rename({"QT_COMPARECIMENTO": "COMPARECIMENTO", "QT_ABSTENCOES": "ABSTENCOES"})
              .collect().drop_nulls("T"))
    vs = (votos.filter((pl.col("NR_TURNO") == turno) & v.office_filter(nome) & filtro_uf)
          .group_by(chave + ["NR_VOTAVEL"]).agg(pl.col("QT_VOTOS").sum()).collect()
          .join(secoes.select(chave + ["T"]), on=chave, how="inner"))
    return secoes.drop("NR_ZONA", "NR_SECAO"), vs.select("SG_UF", "CD_MUNICIPIO", "T", "NR_VOTAVEL", "QT_VOTOS")


def carregar_2022(cache: Path, uf: str = "RJ", cargos: tuple[int, ...] | None = None, turno: int = 1) -> Reconstituicao:
    """Monta a reconstituição a partir do cache (detalhe e votos por seção, candidatos e destinação oficiais).
    `turno` 2 (rodada 43): só Presidente e Governador; cargo sem 2º turno na UF (Governador do RJ em 2022) sai."""
    from apuracao.ufs import dir_uf

    cargos = cargos or CARGOS_POR_TURNO[turno]
    import zipfile
    import io

    ano = 2022
    det_uf = v.load_section_details(ano, uf, cache)
    votos_uf = v.load_section_votes(ano, uf, "governador", cache, False)
    ultimo = dir_uf(Path(f"dados_2026/historico_2022_t{turno}"), uf) / "ultimo"
    cadastro = pl.read_parquet(ultimo / "candidatos.parquet").filter(pl.col("ABRANGENCIA") == "uf") \
        if (ultimo / "candidatos.parquet").exists() else None
    with zipfile.ZipFile(cache / "votacao_candidato_munzona_2022.zip") as z:
        oficial = pl.read_csv(io.BytesIO(z.read(f"votacao_candidato_munzona_2022_{uf}.csv").decode("latin-1").encode()),
                              separator=";", infer_schema=False,
                              columns=["NR_TURNO", "CD_CARGO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "NM_CANDIDATO",
                                       "SQ_CANDIDATO", "SG_PARTIDO", "NR_PARTIDO", "NR_FEDERACAO", "SG_FEDERACAO",
                                       "NM_TIPO_DESTINACAO_VOTOS", "DS_SIT_TOT_TURNO", "CD_TIPO_ELEICAO"])
    oficial = oficial.filter((pl.col("NR_TURNO") == str(turno)) & (pl.col("CD_TIPO_ELEICAO") == "2")).unique(
        ["CD_CARGO", "NR_CANDIDATO"])
    dados: dict[int, DadosCargo] = {}
    for cargo in cargos:
        nome = NOMES[cargo].upper()
        if cargo == 1:
            det = pj.detalhe_nacional(ano, cache)
            votos = v.load_section_votes(ano, "BR", "presidente", cache, False)
            secoes, vs = _secoes_e_votos(det, votos, 1, nome, None, turno)
        else:
            secoes, vs = _secoes_e_votos(det_uf, votos_uf, cargo, nome, uf, turno)
        if secoes.filter(pl.col("SG_UF") == uf).is_empty():  # cargo sem esse turno na UF
            continue
        cand = _candidatos(cargo, oficial, cadastro, vs, uf, turno)
        partidos = cand.select("NR_PARTIDO", "PARTIDO", "FEDERACAO").unique("NR_PARTIDO")
        vagas = {1: 1, 3: 1, 5: 1}.get(cargo) or int(cand["SITUACAO_FINAL"].str.starts_with("Eleito").sum())
        eleicao = (ELEICAO_FEDERAL if cargo == 1 else ELEICAO_ESTADUAL) if turno == 1 else (
            ELEICAO_FEDERAL_2T if cargo == 1 else ELEICAO_ESTADUAL_2T)
        dados[cargo] = DadosCargo(cargo, eleicao, vagas, secoes, vs, cand, partidos)
    horas = pl.concat([d.secoes.filter(pl.col("SG_UF") == uf).select("T") for d in dados.values()])["T"]
    # a foto arredonda ao minuto: o fim é o minuto seguinte à última seção (senão a UF nunca fecha)
    fim = (horas.max() + timedelta(minutes=1)).replace(second=0, microsecond=0)
    return Reconstituicao(uf, dados, (horas.min() - timedelta(minutes=5)).replace(second=0, microsecond=0), fim, turno)


def _candidatos(cargo: int, oficial: pl.DataFrame, cadastro: pl.DataFrame | None, vs: pl.DataFrame, uf: str,
                turno: int = 1) -> pl.DataFrame:
    if cargo == 1:  # presidente: não está no arquivo da UF; cadastro do histórico importado e todos válidos
        base = cadastro.filter(pl.col("CARGO") == 1) if cadastro is not None else pl.DataFrame()
        tot = vs.filter(pl.col("NR_VOTAVEL") < 95).group_by("NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum()).sort(
            "QT_VOTOS", descending=True)
        # 1º turno: os 2 mais votados no Brasil vão ao 2º; no 2º, o mais votado é o eleito
        destaque, rotulo = (set(tot["NR_VOTAVEL"].head(2).to_list()), "2º turno") if turno == 1 else (
            set(tot["NR_VOTAVEL"].head(1).to_list()), "Eleito")
        return base.select(
            "NUMERO", "NOME_URNA", "NOME", pl.col("SQ_CANDIDATO").alias("SQ"), "PARTIDO", "NR_PARTIDO",
            pl.lit(None, pl.String).alias("FEDERACAO"), pl.lit(True).alias("VALIDO"),
            pl.when(pl.col("NUMERO").is_in(list(destaque))).then(pl.lit(rotulo)).otherwise(pl.lit("Não eleito"))
            .alias("SITUACAO_FINAL"))
    o = oficial.filter(pl.col("CD_CARGO") == str(cargo))
    return o.select(
        pl.col("NR_CANDIDATO").cast(pl.Int64).alias("NUMERO"), pl.col("NM_URNA_CANDIDATO").alias("NOME_URNA"),
        pl.col("NM_CANDIDATO").alias("NOME"), pl.col("SQ_CANDIDATO").cast(pl.Int64, strict=False).alias("SQ"),
        pl.col("SG_PARTIDO").alias("PARTIDO"), pl.col("NR_PARTIDO").cast(pl.Int64).alias("NR_PARTIDO"),
        pl.when(pl.col("NR_FEDERACAO").cast(pl.Int64, strict=False) > 0).then(pl.col("SG_FEDERACAO")).alias("FEDERACAO"),
        (pl.col("NM_TIPO_DESTINACAO_VOTOS") == "Válido").alias("VALIDO"),
        pl.col("DS_SIT_TOT_TURNO").replace_strict(SITUACAO, default=None).alias("SITUACAO_FINAL"))


# --------------------------------------------------------------------------
# JSON no formato do TSE
# --------------------------------------------------------------------------
def _bloco_s(ts: int, st: int) -> dict[str, str]:
    p, pn = _pct(st, ts)
    return {"ts": str(ts), "st": str(st), "pst": p, "pstn": pn, "snt": str(ts - st)}


def _bloco_e(te: int, est: int, c: int, a: int) -> dict[str, str]:
    pest, pestn = _pct(est, te)
    pc, pcn = _pct(c, c + a)
    pa, pan = _pct(a, c + a)
    return {"te": str(te), "est": str(est), "pest": pest, "pestn": pestn, "c": str(c), "pc": pc, "pcn": pcn,
            "a": str(a), "pa": pa, "pan": pan}


def _dt(t: datetime | None) -> tuple[str, str]:
    return (t.strftime("%d/%m/%Y"), t.strftime("%H:%M:%S")) if t else ("", "")


class Gerador:
    """Monta os EA14/EA15/EA20 de uma hora virtual."""

    def __init__(self, rec: Reconstituicao, relogio: Relogio, atraso_ea20_min: float = 0.0) -> None:
        """`atraso_ea20_min`: o EA20 (resultado) mostra a apuração de N minutos antes do EA14/EA15
        (acompanhamento) — como o TSE em 04/10/2026, que anunciava a totalização antes de publicá-la."""
        self.rec, self.relogio, self.atraso_ea20_min = rec, relogio, atraso_ea20_min
        self._idg = 0

    def _cabecalho(self, eleicao: int, agora: datetime | None = None) -> dict[str, str]:
        agora = agora or self.relogio.agora()
        self._idg += 1
        dg, hg = _dt(agora)
        return {"ele": str(eleicao), "t": str(self.rec.turno), "f": "s", "dg": dg, "hg": hg,
                "idg": str(200000000 + self._idg)}

    # ---- EA14/EA15
    def acompanhamento(self, eleicao: int, uf: str) -> dict[str, Any]:
        cargo = 1 if eleicao in FEDERAIS else 3
        if cargo not in self.rec.cargos:  # reconstituição sem esse cargo: nada a acompanhar
            return {**self._cabecalho(eleicao), "abr": []}
        foto = self.rec.fotografia(cargo, self.relogio.agora())
        linhas = []
        if uf == "br":
            s = foto["secoes_uf"].select(pl.col("TS", "TE", "ST", "EST", "C", "A").sum(), pl.col("DT").max())
            linhas.append(("br", "br", s.row(0, named=True)))
        else:
            s = foto["secoes_uf"].filter(pl.col("SG_UF") == self.rec.uf)
            if not s.is_empty():
                linhas.append(("uf", uf, s.row(0, named=True)))
            muns = foto["secoes_mun"].join(
                self.rec.cargos[cargo].secoes.filter(pl.col("SG_UF") == self.rec.uf).select("CD_MUNICIPIO").unique(),
                on="CD_MUNICIPIO", how="inner")
            linhas += [("mun", f"{r['CD_MUNICIPIO']:05d}", r) for r in muns.iter_rows(named=True)]
        abr = []
        for tp, cd_, r in linhas:
            dt, ht = _dt(r["DT"] or self.rec.inicio)
            abr.append({"and": "f" if r["ST"] == r["TS"] else "p", "tpabr": tp, "cdabr": cd_, "dt": dt, "ht": ht,
                        "s": _bloco_s(r["TS"], r["ST"]), "e": _bloco_e(r["TE"], r["EST"], r["C"], r["A"])})
        return {**self._cabecalho(eleicao), "abr": abr}

    # ---- EA20
    def resultado(self, eleicao: int, cargo: int, abrangencia: str) -> dict[str, Any] | None:
        """`abrangencia`: "br", a UF ("rj") ou a UF + município ("rj60011")."""
        if cargo not in self.rec.cargos or (abrangencia == "br" and cargo != 1):
            return None
        d = self.rec.cargos[cargo]
        if eleicao != d.eleicao:
            return None
        agora = self.relogio.agora() - timedelta(minutes=self.atraso_ea20_min)
        foto = self.rec.fotografia(cargo, agora)
        if abrangencia == "br":
            sec = foto["secoes_uf"].select(pl.col("TS", "TE", "ST", "EST", "C", "A").sum(), pl.col("DT").max())
            vt = foto["votos_uf"].group_by("NR_VOTAVEL").agg(pl.col("QT_VOTOS").sum())
            tp, cdabr = "br", "br"
        elif len(abrangencia) == 2:
            sec = foto["secoes_uf"].filter(pl.col("SG_UF") == self.rec.uf).drop("SG_UF")
            vt = foto["votos_uf"].filter(pl.col("SG_UF") == self.rec.uf).drop("SG_UF")
            tp, cdabr = "uf", abrangencia
        else:
            mun = int(abrangencia[2:])
            sec = foto["secoes_mun"].filter(pl.col("CD_MUNICIPIO") == mun).drop("CD_MUNICIPIO")
            vt = foto["votos_mun"].filter(pl.col("CD_MUNICIPIO") == mun).drop("CD_MUNICIPIO")
            tp, cdabr = "mu", f"{mun:05d}"
        if sec.is_empty():
            return None
        r = sec.row(0, named=True)
        votos = dict(zip(vt["NR_VOTAVEL"], vt["QT_VOTOS"]))
        cands = d.candidatos
        validos_c = {n for n, ok in zip(cands["NUMERO"], cands["VALIDO"]) if ok}
        proporcional = cargo in (6, 7)
        nominais = sum(q for n, q in votos.items() if n in validos_c)
        legenda = sum(q for n, q in votos.items() if proporcional and n < 95) if proporcional else 0
        anulados = sum(q for n, q in votos.items()
                       if n not in ESPECIAIS and (n >= 100 or not proporcional) and n not in validos_c)
        vv = nominais + legenda
        brancos, nulos = votos.get(95, 0), votos.get(96, 0) + votos.get(97, 0)
        uf_final = self.rec.fotografia(cargo, agora)["secoes_uf"].filter(pl.col("SG_UF") == self.rec.uf)
        final_uf = bool(uf_final.row(0, named=True)["ST"] == uf_final.row(0, named=True)["TS"]) if not uf_final.is_empty() else False
        dt, ht = _dt(r["DT"] or self.rec.inicio)
        doc: dict[str, Any] = {**self._cabecalho(eleicao, agora), "tpabr": tp, "cdabr": cdabr, "dt": dt, "ht": ht,
                               "tf": "s" if r["ST"] == r["TS"] else "n", "and": "f" if r["ST"] == r["TS"] else "p",
                               "esae": "n", "s": _bloco_s(r["TS"], r["ST"]),
                               "e": _bloco_e(r["TE"], r["EST"], r["C"], r["A"])}
        pvv, pvvn = _pct(vv, r["C"])
        pb, pbn = _pct(brancos, r["C"])
        pn, pnn = _pct(nulos, r["C"])
        doc["v"] = {"tv": str(r["C"]), "vv": str(vv), "pvv": pvv, "pvvn": pvvn, "vnom": str(nominais), "vl": str(legenda),
                    "vb": str(brancos), "pvb": pb, "pvbn": pbn, "tvn": str(nulos), "ptvn": pn, "ptvnn": pnn,
                    "van": str(max(anulados, 0)), "vansj": "0", "pvansj": "0,00"}
        # candidatos, agrupados por agremiação (federação ou partido) e partido
        ordem = sorted(cands.iter_rows(named=True), key=lambda c: (-votos.get(c["NUMERO"], 0), c["NUMERO"]))
        seq = {c["NUMERO"]: i + 1 for i, c in enumerate(ordem)}
        agrs: dict[str, dict] = {}
        for c in ordem:
            ag = c["FEDERACAO"] or c["PARTIDO"]
            a = agrs.setdefault(ag, {"n": str(len(agrs) + 1), "nm": ag, "com": ag, "par": {}})
            p = a["par"].setdefault(c["NR_PARTIDO"], {"n": str(c["NR_PARTIDO"]), "sg": c["PARTIDO"], "tvtn": 0,
                                                       "tvtl": votos.get(c["NR_PARTIDO"], 0) if proporcional else 0,
                                                       "cand": []})
            q = votos.get(c["NUMERO"], 0)
            if c["VALIDO"]:
                p["tvtn"] += q
            pv, pvn = _pct(q, vv)
            st = (c["SITUACAO_FINAL"] or "") if final_uf else ""
            p["cand"].append({"n": str(c["NUMERO"]), "sqcand": str(c["SQ"] or ""), "nm": c["NOME"] or c["NOME_URNA"],
                              "nmu": c["NOME_URNA"], "dvt": "Válido" if c["VALIDO"] else "Anulado",
                              "seq": str(seq[c["NUMERO"]]), "e": "s" if st.startswith("Eleito") else "n", "st": st,
                              "vap": str(q), "pvap": pv, "pvapn": pvn})
        feds = {}
        for c in cands.filter(pl.col("FEDERACAO").is_not_null()).iter_rows(named=True):
            feds.setdefault(c["FEDERACAO"], set()).add(str(c["NR_PARTIDO"]))
        carg = {"cd": str(cargo), "nmn": NOMES[cargo], "nv": str(d.vagas),
                "fed": [{"n": str(i), "sg": f, "nm": f, "com": f, "npar": sorted(ps)} for i, (f, ps) in enumerate(feds.items())],
                "agr": [{**{k: a[k] for k in ("n", "nm", "com")},
                         "par": [{**{k: p[k] for k in ("n", "sg")}, "tvtn": str(p["tvtn"]), "tvtl": str(p["tvtl"]),
                                  "cand": p["cand"]} for p in a["par"].values()]} for a in agrs.values()]}
        if proporcional and vv:
            carg["qe"] = str(cd.quociente_eleitoral(vv, d.vagas))
        doc["carg"] = [carg]
        return doc


# --------------------------------------------------------------------------
# Sessão HTTP falsa (o "servidor do TSE" do ensaio)
# --------------------------------------------------------------------------
class RespostaEnsaio:
    def __init__(self, status: int, texto: str = "", etag: str | None = None) -> None:
        self.status_code, self.text = status, texto
        self.headers = {"Content-Type": "application/json", **({"ETag": etag} if etag else {})}

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SessaoEnsaio:
    """Responde como o TSE: configuração dos recortes do simulado; o resto gerado na hora. `municipios`
    (formato `ultimo/municipios.parquet`, ex.: o de 2022 importado) substitui a lista de 3 municípios do
    recorte: sem ela, os outros 89 do RJ ficam sem nome no site e no boletim."""

    def __init__(self, gerador: Gerador, municipios: pl.DataFrame | None = None) -> None:
        self.gerador = gerador
        self.headers: dict[str, str] = {}  # o cliente põe o User-Agent aqui, como numa requests.Session
        self.pedidos: list[str] = []
        self._fixos = {p.name: p.read_text(encoding="utf-8") for p in (FIXTURES / "ele-c.json",
                                                                        FIXTURES / "mun-e021272-cm.json")}
        self._trava = threading.Lock()
        # como o TSE, anuncia só os cargos que publica: cargo anunciado e não gerado daria 404 a cada ciclo
        cfg = json.loads(self._fixos["ele-c.json"])
        for e in cfg["pl"][0]["e"]:
            for abr in e.get("abr", []):
                abr["cp"] = [c for c in abr.get("cp", []) if int(c["cd"]) in gerador.rec.cargos]
        self._fixos["ele-c.json"] = json.dumps(cfg, ensure_ascii=False)
        if municipios is not None and not municipios.is_empty():
            doc = json.loads(self._fixos["mun-e021272-cm.json"])
            doc["abr"] = [{"cd": uf.lower(), "ds": uf, "mu": [
                {"cd": f"{r['CD_MUNICIPIO']:05d}", "cdi": str(r["CD_MUNICIPIO_IBGE"] or ""), "nm": r["NM_MUNICIPIO"],
                 "c": "s" if r["CAPITAL"] else "n", "z": [f"{int(z):04d}" for z in (r["ZONAS"] or "").split(",") if z]}
                for r in grupo.iter_rows(named=True)]}
                for (uf,), grupo in municipios.sort("CD_MUNICIPIO").group_by("UF", maintain_order=True)]
            self._fixos["mun-e021272-cm.json"] = json.dumps(doc, ensure_ascii=False)

    def _documento(self, nome: str) -> dict | str | None:
        if nome == "ele-c.json":
            return self._fixos[nome]
        if nome.startswith("mun-e") and nome.endswith("-cm.json"):
            return self._fixos["mun-e021272-cm.json"]
        if nome.endswith("-ab.json"):  # <uf>-e<eleicao:06>-ab.json
            uf, ele = nome.removesuffix("-ab.json").split("-e")
            return self.gerador.acompanhamento(int(ele), uf)
        if nome.endswith("-u.json"):   # <abr>-c<cargo:04>-e<eleicao:06>-u.json
            abr, resto = nome.removesuffix("-u.json").split("-c")
            cargo, ele = resto.split("-e")
            return self.gerador.resultado(int(ele), int(cargo), abr)
        return None

    def get(self, url: str, headers: dict | None = None, timeout: float = 0) -> RespostaEnsaio:
        nome = url.rsplit("/", 1)[-1]
        with self._trava:
            self.pedidos.append(nome)
        doc = self._documento(nome)
        if doc is None:
            return RespostaEnsaio(404, "{}")
        if isinstance(doc, dict):  # o carimbo de geração muda a cada pedido; a ETag olha só o conteúdo
            conteudo = {k: x for k, x in doc.items() if k not in ("dg", "hg", "idg")}
            etag = '"' + hashlib.md5(json.dumps(conteudo, sort_keys=True).encode()).hexdigest() + '"'
            texto = json.dumps(doc, ensure_ascii=False)
        else:
            texto, etag = doc, '"' + hashlib.md5(doc.encode()).hexdigest() + '"'
        if headers and headers.get("If-None-Match") == etag:
            return RespostaEnsaio(304, "", etag)
        return RespostaEnsaio(200, texto, etag)
