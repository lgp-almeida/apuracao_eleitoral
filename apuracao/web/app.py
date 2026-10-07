"""API e página do site local de apuração.

Lê o "último estado" gravado pelo coletor (dados_2026/<ambiente>/ultimo/*.parquet),
recarregando cada tabela quando o arquivo muda, e serve a página em static/.

Rotas:
  GET /                        página (abas Painel, Candidato, Mapas)
  GET /api/status              situação do coletor e da apuração
  GET /api/painel              totais + candidatos de cada cargo (Presidente BR/UF, Governador, Senador, Deputados)
  GET /api/candidatos          lista (número, nome, partido) de um cargo, para busca
  GET /api/candidato           um candidato: total na UF e votos por município
  GET /api/candidato/historico um candidato por município nesta eleição e na de referência (mesmo nome civil),
                               com a variação; /planilha devolve o mesmo em .xlsx (sem depender dos microdados)
  GET /api/mapa                valor por município (código IBGE) para uma métrica
  GET /api/mapa/locais         um ponto por local de votação: voto, perfil do eleitorado, resíduo do Perfil × voto
                               ou variação desde a eleição anterior
  GET /api/planilha            .xlsx de um candidato em ano com microdados (reaproveita planilha_candidato)
  GET /geo/municipios.geojson  malha municipal do IBGE (baixada uma vez para o cache)
  GET /geo/locais.geojson      locais de votação com coordenadas (cadastro de eleitorado)
  GET /api/bancadas[/planilha] bancadas de deputado × a eleição de referência (partidos, reeleitos, novatos)
  GET /api/comparacao[...]     comparação por município com uma eleição de referência (ex.: 2022);
                               /variacao: até 3 partidos, dispersão A × B e estatística da variação
  GET /api/projecao            projeção do resultado final (majoritários na UF) com margem calibrada em 2022
  GET /api/cadeiras            distribuição projetada das cadeiras de deputado (QE, QP, sobras) e eleitos
  GET /api/cadeiras/planilha   as listas de eleitos projetados em .xlsx (coluna "Destacado" para ?destacar=PL,PT)
  GET /api/mudancas            o que mudou desde o último boletim (painel)
  GET /api/alertas             alertas da noite (coletor, bloqueio, apuração parada, leitura da projeção,
                               candidatos de interesse); POST /api/alertas/interesse liga/desliga um deputado
  GET /api/transferencia[...] transferência de votos do 1º para o 2º turno (inferência ecológica) e abstenção extra
  GET /api/perfil/[...]        perfil do eleitorado (TSE) e Censo 2022 (IBGE) × voto por bairro:
                               correlações, dispersão e transferência entre eleições
"""

from __future__ import annotations

import ipaddress
import json
import logging
import math
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import polars as pl
import requests
from fastapi import FastAPI, HTTPException, Query, Request
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles

import votos_por_local_votacao as v
from apuracao import alertas as al
from apuracao import mapa_locais as ml
from apuracao import bairros as br
from apuracao import ibge
from apuracao import cadeiras as cd
from apuracao import projecao as pj
from apuracao import projecao_cadeiras as pcad
from apuracao import transferencia as tf
from apuracao import comparacao as cp
from apuracao import perfil as pf
from apuracao import areas_ponderacao as ap
from apuracao import perfil_local as pfl
from apuracao.web import exportar as ex
from apuracao.divulgacao import modelo as m
from apuracao.divulgacao import serie as sr

logger = logging.getLogger("apuracao.web")

STATIC = Path(__file__).parent / "static"
BRASILIA = ZoneInfo("America/Sao_Paulo")
# cartões do painel: (cargo, abrangência); "uf" é a UF configurada
PAINEL = [(1, "br"), (1, "uf"), (3, "uf"), (5, "uf"), (6, "uf"), (7, "uf")]
TOP_MAJORITARIO, TOP_PROPORCIONAL, TOP_PARTIDOS = 12, 20, 15
METRICAS_TOTAIS = {
    "abstencao_pct": ("PCT_ABSTENCAO", "Abstenção (%)"),
    "comparecimento_pct": ("PCT_COMPARECIMENTO", "Comparecimento (%)"),
    "brancos_pct": ("PCT_BRANCOS", "Brancos (%)"),
    "nulos_pct": ("PCT_NULOS", "Nulos (%)"),
    "brancos_nulos_pct": (None, "Brancos + nulos (%)"),
    "secoes_totalizadas_pct": ("PCT_SECOES_TOTALIZADAS", "Seções totalizadas (%)"),
}
# baixam microdados/malhas (centenas de MB) ou gastam muita CPU: com o site na rede, só da própria máquina
ROTAS_PESADAS = ("/api/planilha", "/api/mapa/bairros", "/api/mapa/areas", "/api/comparacao/bairros", "/api/perfil",
                 "/api/exportar", "/geo/locais.geojson", "/geo/bairros.geojson", "/geo/areas.geojson", "/api/transferencia",
                 "/api/mapa/locais")
# também só da própria máquina: rotas que ALTERAM estado
ROTAS_SO_LOCAL = ROTAS_PESADAS + ("/api/alertas/interesse",)
METRICAS_CANDIDATO = {"pct_candidato": "% dos válidos do candidato", "votos_candidato": "Votos do candidato"}
SCHEMAS = {"totais": m.TOTAIS_SCHEMA, "candidatos": m.CANDIDATOS_SCHEMA, "partidos": m.PARTIDOS_SCHEMA,
           "municipios": m.MUNICIPIOS_SCHEMA, "acompanhamento": m.ACOMPANHAMENTO_SCHEMA, "serie": sr.SCHEMA,
           "historico_totais": m.TOTAIS_SCHEMA, "brasil_totais": m.TOTAIS_SCHEMA,
           "brasil_candidatos": m.CANDIDATOS_SCHEMA}
NOME_UF = {"ZZ": "Exterior"}
TOP_BRASIL = 3  # candidatos com cor própria no mapa por UF (dataviz: no máximo 3 + "Outros")


class PedidoInteresse(BaseModel):
    """Corpo de POST /api/alertas/interesse."""

    cargo: int
    numero: int
    acompanhar: bool = True


class PedidoExportacao(BaseModel):
    """Corpo de POST /api/exportar/mapa (as cores e a legenda vêm prontas da página)."""

    formato: str = "png"
    camada: str = Field("municipios", pattern="^(municipios|bairros|locais|areas)$")
    ano: int | None = None  # camada "locais": o cadastro de eleitorado do ano (coordenadas)
    nome: str = "mapa"
    titulo: str = ""
    subtitulo: str = ""
    fonte: str = "Fonte: TSE; malha: IBGE"
    cores: dict[str, str] = {}
    legenda: list[tuple[str, str]] = []
    fundo: str = "#fcfcfb"
    texto: str = "#0b0b0b"
    sem_dado: str = "#f0efec"
    contorno: str = "#fcfcfb"
    dpi: int = 200
    extras: list[str] = []


@dataclass
class Dados:
    """Tabelas do coletor, recarregadas quando o Parquet muda no disco."""

    diretorio: Path
    _cache: dict[str, tuple[int, pl.DataFrame]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def tabela(self, nome: str) -> pl.DataFrame:
        return self.com_versao(nome)[0]

    def com_versao(self, nome: str) -> tuple[pl.DataFrame, int]:
        """A tabela e a versão dela (mtime_ns do Parquet lido; 0 se ainda não existe). A versão serve
        de chave de cache: id() de um DataFrame liberado é reaproveitado pelo CPython."""
        raiz = {"serie": sr.ARQUIVO, "historico_totais": "historico_totais.parquet"}
        path = self.diretorio / raiz[nome] if nome in raiz else self.diretorio / "ultimo" / f"{nome}.parquet"
        if not path.exists():
            return pl.DataFrame(schema=SCHEMAS[nome]), 0
        mtime = path.stat().st_mtime_ns
        with self._lock:
            hit = self._cache.get(nome)
            if hit and hit[0] == mtime:
                return hit[1], hit[0]
            df = pl.read_parquet(path)
            self._cache[nome] = (mtime, df)
            return df, mtime

    def tabelas_do_resultado(self) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, tuple[int, ...]]:
        """totais, candidatos, partidos e a versão conjunta das três."""
        (tot, vt), (cand, vc), (part, vp) = (self.com_versao(n) for n in ("totais", "candidatos", "partidos"))
        return tot, cand, part, (vt, vc, vp)

    def status(self) -> dict[str, Any]:
        path = self.diretorio / "status.json"
        return json.loads(path.read_text()) if path.exists() else {"erro": "coletor ainda não rodou"}


@dataclass(frozen=True)
class Consultas:
    """O que as rotas do site calculam, para quem roda no mesmo processo (o boletim): os mesmos números
    da página, com os mesmos caches. `projecao`/`cadeiras` levantam ValueError ou TseDataError."""

    dados: Dados
    uf: str
    status: Callable[[], dict[str, Any]]
    painel: Callable[[], dict[str, Any]]
    projecao: Callable[[int], dict[str, Any]]
    cadeiras: Callable[[int], dict[str, Any]]


# --------------------------------------------------------------------------
# Serialização
# --------------------------------------------------------------------------
def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None  # NaN/inf não existem em JSON
    return value


def caminho_no_app(request: Request) -> str:
    """Caminho dentro deste app, sem o prefixo da montagem (`/sp`, no site com várias UFs): o Starlette mantém
    o caminho inteiro em `url.path`, e as regras por rota (`ROTAS_SO_LOCAL`) valem para o app de cada UF."""
    raiz, caminho = request.scope.get("root_path", ""), request.url.path
    return caminho[len(raiz):] or "/" if raiz and caminho.startswith(raiz) else caminho


def _limpar(obj: Any) -> Any:
    """`_jsonable` em profundidade (dicts e listas aninhados), para respostas montadas no domínio."""
    if isinstance(obj, dict):
        return {k: _limpar(val) for k, val in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpar(val) for val in obj]
    return _jsonable(obj)


def _rows(df: pl.DataFrame) -> list[dict[str, Any]]:
    return [{k: _jsonable(val) for k, val in r.items()} for r in df.iter_rows(named=True)]


def _abrangencia(df: pl.DataFrame, abr: str, uf: str, municipio: int | None = None) -> pl.DataFrame:
    if abr == "br":
        return df.filter(pl.col("ABRANGENCIA") == "br")
    if abr == "uf":
        return df.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf))
    return df.filter((pl.col("ABRANGENCIA") == "mun") & (pl.col("CD_MUNICIPIO") == municipio))


def presidente_por_uf(tot: pl.DataFrame, cand: pl.DataFrame) -> dict[str, Any]:
    """Presidente em cada UF (+ exterior): apuração, 1º e 2º e o % dos `TOP_BRASIL` mais votados no
    conjunto das UFs. Entradas: `ultimo/brasil_{totais,candidatos}.parquet` do coletor."""
    tot = tot.filter((pl.col("CARGO") == 1) & (pl.col("ABRANGENCIA") == "uf")).unique("UF", keep="last")
    cand = cand.filter((pl.col("CARGO") == 1) & (pl.col("ABRANGENCIA") == "uf")).unique(["UF", "NUMERO"], keep="last")
    if tot.is_empty():
        return {"candidatos": [], "ufs": []}
    top = (cand.group_by("NUMERO").agg(pl.col("VOTOS").sum(), pl.col("NOME_URNA").first(), pl.col("PARTIDO").first())
           .sort(["VOTOS", "NUMERO"], descending=[True, False]))
    destaque = top.head(TOP_BRASIL)["NUMERO"].to_list()
    ufs = []
    for t in tot.sort(pl.col("UF") == "ZZ", "UF").iter_rows(named=True):
        c = cand.filter(pl.col("UF") == t["UF"]).sort(["VOTOS", "SEQ"], descending=[True, False], nulls_last=True)
        lado = [{"numero": r["NUMERO"], "nome": r["NOME_URNA"], "partido": r["PARTIDO"], "pct": r["PCT_VALIDOS"]}
                for r in c.filter(pl.col("VOTOS") > 0).head(2).iter_rows(named=True)]
        ufs.append({
            "uf": t["UF"], "nome": NOME_UF.get(t["UF"], t["UF"]), "cd_ibge": ibge.UF_IBGE.get(t["UF"]),
            "pct_secoes": t["PCT_SECOES_TOTALIZADAS"], "hora": _jsonable(t["DT_TOTALIZACAO"]),
            "final": t["TOTALIZACAO_FINAL"], "eleitorado": t["ELEITORADO"], "validos": t["VALIDOS"],
            "primeiro": lado[0] if lado else None, "segundo": lado[1] if len(lado) > 1 else None,
            "diferenca_pp": round((lado[0]["pct"] or 0) - (lado[1]["pct"] or 0), 2) if len(lado) > 1 else None,
            "pct": {str(r["NUMERO"]): r["PCT_VALIDOS"] for r in c.iter_rows(named=True) if r["NUMERO"] in destaque},
            # hint do mapa: todos os candidatos e os não válidos (percentuais do TSE: brancos/nulos sobre o
            # total de votos, abstenção sobre o eleitorado)
            "candidatos": [{"numero": r["NUMERO"], "nome": r["NOME_URNA"], "partido": r["PARTIDO"],
                            "votos": r["VOTOS"], "pct": r["PCT_VALIDOS"]} for r in c.iter_rows(named=True)],
            "brancos": t["BRANCOS"], "pct_brancos": t["PCT_BRANCOS"], "nulos": t["NULOS"], "pct_nulos": t["PCT_NULOS"],
            "abstencao": t["ABSTENCAO"], "pct_abstencao": t["PCT_ABSTENCAO"], "comparecimento": t["COMPARECIMENTO"],
        })
    return {"candidatos": _rows(top.head(TOP_BRASIL)), "ufs": ufs}


# --------------------------------------------------------------------------
# Aplicação
# --------------------------------------------------------------------------
def create_app(dados_dir: Path, uf: str = "RJ", cache_dir: Path = Path("cache_tse"),
               coletor_status: dict[str, Any] | None = None, referencia: Path | None = None,
               pesadas_so_local: bool = False, interesse: tuple[tuple[int, int], ...] = (),
               destacar: tuple[str, ...] = ()) -> FastAPI:
    """`coletor_status`: dict atualizado pela thread do coletor, se houver.
    `referencia`: diretório de outra eleição no mesmo formato (ex.: dados_2026/historico_2022_t1)
    para a aba de comparação por município.
    `pesadas_so_local`: site exposto na rede (sem senha): as rotas que baixam microdados ou gastam muita
    CPU (`ROTAS_PESADAS`) só atendem a própria máquina; os outros veem o painel, mapas e candidatos.
    `interesse`: deputados (cargo, número) com alerta de mudança de situação (app.state.vigia).
    `destacar`: partidos/federações destacados por padrão nas listas de eleitos (o navegador pode trocar)."""
    uf = uf.upper()
    dados = Dados(dados_dir)
    ref = cp.carregar_fonte(referencia, 2022) if referencia and (referencia / "ultimo").exists() else None
    app = FastAPI(title="Apuração 2026", docs_url="/api/docs", redoc_url=None)
    if pesadas_so_local:
        @app.middleware("http")
        async def so_local(request: Request, call_next: Any) -> Response:
            cliente = request.client.host if request.client else ""
            if caminho_no_app(request).startswith(ROTAS_SO_LOCAL) and not eh_loopback(cliente):
                return JSONResponse({"detail": "disponível só no computador do site (consulta pesada; o site "
                                               "está aberto na rede sem senha)"}, status_code=403)
            return await call_next(request)
    geo_cache: dict[str, Any] = {}

    cadeiras_cache: dict[tuple, Any] = {}
    falhas_munzona: dict[tuple, float] = {}  # (fonte, ano, cargo) → quando falhou (tenta de novo após 10 min)
    cadeiras_trava = threading.Lock()

    def distribuicao(cargo: int) -> tuple[cd.Distribuicao, str]:
        """Distribuição das cadeiras do cargo e a fonte. Eleição passada importada (status com "ano"):
        microdados oficiais do TSE (validados contra as 1.572 vagas de 2022). Tempo real: o `ultimo/`."""
        if cargo not in cd.PROPORCIONAIS:
            raise ValueError(f"cargo {cargo} não é proporcional (use 6, 7 ou 8)")
        st = dados.status()
        tot, cand, part, versao = dados.tabelas_do_resultado()
        with cadeiras_trava:
            if st.get("ano") and st.get("turno", 1) == 1:
                chave: tuple = ("munzona", st["ano"], cargo)
                falhou = falhas_munzona.get(chave)
                recente = falhou is not None and time.monotonic() - falhou < br.ESPERA_APOS_FALHA_S
                if chave not in cadeiras_cache and not recente:
                    try:
                        cadeiras_cache[chave] = (cd.distribuir(*cd.entrada_munzona(st["ano"], uf, cargo, cache_dir)),
                                                 f"microdados oficiais do TSE ({st['ano']})")
                    except (v.TseDataError, requests.RequestException) as exc:
                        # ex.: 2026 antes de o TSE publicar o votacao_partido_munzona: sem isto, cada pedido
                        # de cadeiras repetia o download (404) na CDN
                        falhas_munzona[chave] = time.monotonic()
                        logger.warning("sem microdados oficiais de %s para as cadeiras: %s", st["ano"], exc)
                if chave in cadeiras_cache:
                    return cadeiras_cache[chave]
            chave = ("divulgacao", cargo, versao)
            if chave not in cadeiras_cache:
                cadeiras_cache.clear() if len(cadeiras_cache) > 32 else None
                cadeiras_cache[chave] = (cd.distribuir(*cd.entrada_divulgacao(tot, cand, part, cargo, uf)),
                                         "divulgação do TSE")
            return cadeiras_cache[chave]

    def projecao_cadeiras(cargo: int) -> pcad.ProjecaoCadeiras:
        """Cadeiras e eleitos sobre os votos projetados (+ simulações), só na apuração em andamento."""
        tot, cand, part, versao = dados.tabelas_do_resultado()
        chave = ("projecao", cargo, versao)
        with cadeiras_trava:
            if chave not in cadeiras_cache:
                mun, va, vc, info, vagas = pcad.entrada_divulgacao(tot, cand, part, cargo, uf)
                cadeiras_cache[chave] = pcad.projetar_cadeiras(mun, va, vc, info, vagas)
            return cadeiras_cache[chave]

    def _projecao_cadeiras_json(cargo: int, linha: dict, completo: bool) -> dict[str, Any] | None:
        pct = linha.get("PCT_SECOES_TOTALIZADAS") or 0
        if dados.status().get("ano") or not 0 < pct < 100 or linha.get("TOTALIZACAO_FINAL"):
            return None
        p = projecao_cadeiras(cargo)
        st = p.candidatos["STATUS"]
        resp: dict[str, Any] = {
            "pct_apurado": p.pct_apurado, "ativa": p.pct_apurado >= pcad.PCT_MINIMO, "pct_minimo": pcad.PCT_MINIMO,
            "simulacoes": p.n_sim, "limiar": pcad.LIMIAR, "qe": p.base.qe,
            "consolidados": int((st == "consolidado").sum()),
            "em_disputa_dentro": int((st == "em disputa (dentro)").sum()),
            "em_disputa_fora": int((st == "em disputa (fora)").sum()),
            "agremiacoes": _rows(p.agremiacoes.filter(pl.col("VAGAS_MAX") > 0).select(
                "AGREMIACAO", "VOTOS_ATUAIS", "VOTOS", "VAGAS", "VAGAS_MIN", "VAGAS_MAX")),
        }
        if completo:
            resp["candidatos"] = _rows(p.candidatos.filter(pl.col("STATUS") != "fora").sort(
                ["FREQ_ELEITO", "VOTOS"], descending=True).select(
                "AGREMIACAO", "NUMERO", "NOME", "PARTIDO", pl.col("VOTOS").alias("VOTOS_PROJ"), "FREQ_ELEITO", "STATUS"))
        return resp

    def _cadeiras_json(cargo: int, completo: bool) -> dict[str, Any]:
        d, fonte = distribuicao(cargo)
        t = _abrangencia(dados.tabela("totais").filter(pl.col("CARGO") == cargo), "uf", uf)
        linha = t.row(0, named=True) if not t.is_empty() else {}
        eleitos = d.candidatos.filter(pl.col("SITUACAO_PROJETADA").str.starts_with("Eleito"))
        resp: dict[str, Any] = {
            "cargo": cargo, "ds_cargo": cd.PROPORCIONAIS[cargo], "fonte": fonte, "vagas": d.vagas,
            "validos": d.validos, "qe": d.qe, "limites": d.limites, "vagas_nao_preenchidas": d.vagas_nao_preenchidas,
            "pct_secoes": linha.get("PCT_SECOES_TOTALIZADAS"), "final": bool(linha.get("TOTALIZACAO_FINAL")),
            "eleitos_qp": int((eleitos["SITUACAO_PROJETADA"] == cd.ELEITO_QP).sum()),
            "eleitos_media": int((eleitos["SITUACAO_PROJETADA"] == cd.ELEITO_MEDIA).sum()),
            "agremiacoes": _rows(d.agremiacoes.filter(pl.col("VAGAS") > 0) if not completo else d.agremiacoes),
            # salvaguarda: os votos das agremiações têm de somar os válidos (no JSON do TSE somam exatamente)
            "soma_agremiacoes": int(d.agremiacoes["VOTOS"].sum()),
            "consistente": int(d.agremiacoes["VOTOS"].sum()) == d.validos,
            # partidos de cada agremiação (federação = vários), da mais votada à menos: opções do "Destacar"
            "composicao": [{"AGREMIACAO": ag, "PARTIDOS": sorted(p for p in ps if p)} for ag, ps in
                           d.agremiacoes.sort("VOTOS", descending=True).select("AGREMIACAO").join(
                               d.candidatos.group_by("AGREMIACAO").agg(pl.col("PARTIDO").unique()),
                               on="AGREMIACAO", how="left").iter_rows() if ps],
        }
        if "SITUACAO_TSE" in d.candidatos.columns:  # conferência com o que o TSE já declarou (eleito × não)
            of = d.candidatos["SITUACAO_TSE"].fill_null("").str.to_uppercase().str.starts_with("ELEITO")
            if of.any():
                pj = d.candidatos["SITUACAO_PROJETADA"].str.starts_with("Eleito")
                resp["conferencia_tse"] = {"eleitos_tse": int(of.sum()), "coincidentes": int((of & pj).sum()),
                                           "divergencias": int((of != pj).sum())}
        try:
            proj = _projecao_cadeiras_json(cargo, linha, completo)
        except (ValueError, v.TseDataError) as exc:
            logger.warning("projeção de cadeiras indisponível: %s", exc)
            proj = None
        if proj:
            resp["projecao"] = proj
        if completo:
            resp["eleitos"] = _rows(eleitos.sort("VOTOS", descending=True).select(
                "AGREMIACAO", "NUMERO", "NOME", "PARTIDO", "VOTOS", "SITUACAO_PROJETADA", "MARGEM"))
            resp["sobras"] = d.sobras
        return resp

    def _projecao_json(cargo: int, completo: bool) -> dict[str, Any]:
        if cargo not in (1, 3, 5):
            raise ValueError("projeção só para cargos majoritários (1, 3 ou 5)")
        tot, cand = dados.tabela("totais"), dados.tabela("candidatos")
        mun, votos = pj.entrada_divulgacao(tot, cand, cargo)
        if mun.is_empty():
            raise v.TseDataError(f"sem apuração por município do cargo {cargo}")
        t = _abrangencia(tot.filter(pl.col("CARGO") == cargo), "uf", uf)
        linha = t.row(0, named=True) if not t.is_empty() else {}
        turno = int(linha.get("TURNO") or 1)
        p = pj.projetar(mun, votos, turno)  # margem do turno (rodada 44)
        vagas = int(linha.get("VAGAS") or 1)
        nomes = _abrangencia(cand.filter(pl.col("CARGO") == cargo), "uf", uf).select("NUMERO", "NOME_URNA", "PARTIDO")
        c = p.candidatos.join(nomes, on="NUMERO", how="left")
        resp: dict[str, Any] = {
            "cargo": cargo, "pct_apurado": p.pct_apurado, "margem_pp": p.margem_pp, "vagas": vagas,
            "validos_atuais": p.validos_atuais, "validos_projetados": round(p.validos_projetados),
            "municipios_sem_apuracao": p.municipios_sem_apuracao,
            "situacao": pj.situacao(p, vagas, {1: "lideranca", 3: "maioria", 5: "vagas"}[cargo], turno),
            "candidatos": _rows(c.head(12 if completo else 6).select(
                "NUMERO", "NOME_URNA", "PARTIDO", "VOTOS", "PCT_ATUAL", "VOTOS_PROJ", "PCT_PROJ", "MIN", "MAX")),
            "metodo": "por município: o que falta em cada um segue o voto já apurado ali; margem = percentil 95 "
                      "do erro na apuração real, uma por turno (1º: 2022 e 2026; 2º: 2022 — Presidente nas 27 UFs, "
                      "Governador e Senador no RJ e no ES)",
        }
        if completo:
            falta = p.municipios.filter(pl.col("VALIDOS_RESTANTES") >= 1).head(15).join(
                dados.tabela("municipios").select("CD_MUNICIPIO", "NM_MUNICIPIO"), on="CD_MUNICIPIO", how="left")
            resp["faltam"] = _rows(falta.select("CD_MUNICIPIO", "NM_MUNICIPIO", "PCT_APURADO",
                                                pl.col("VALIDOS_RESTANTES").round(0)))
        return resp

    @app.get("/api/projecao")
    def projecao(cargo: int) -> dict[str, Any]:
        """Projeção do resultado final na UF (Presidente-UF, Governador, Senador) com margem calibrada."""
        try:
            return _projecao_json(cargo, completo=True)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except v.TseDataError as exc:
            raise HTTPException(404, str(exc)) from exc

    def st_ano() -> Any:
        return dados.status().get("ano")

    @app.get("/api/cadeiras")
    def cadeiras(cargo: int) -> dict[str, Any]:
        """Cadeiras projetadas (QE, QP, sobras em 2 fases — art. 12-A da Res. 23.677/2021) e eleitos."""
        try:
            return _cadeiras_json(cargo, completo=True)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except v.TseDataError as exc:
            raise HTTPException(404, str(exc)) from exc

    mudancas_cache: dict[str, Any] = {}

    @app.get("/api/mudancas")
    def api_mudancas() -> dict[str, Any]:
        """O que mudou entre o último boletim (<dados>/boletins/*.json) e agora. Guardado pela versão dos dados
        e do último boletim: o painel pede a cada minuto, e montar a comparação custa ~1 s."""
        from apuracao import boletim as bo  # boletim importa este módulo: import tardio
        pasta = dados_dir / "boletins"
        fotos = sorted(pasta.glob("boletim_*.json")) if pasta.exists() else []
        versao = (dados.tabelas_do_resultado()[3], max((f.stat().st_mtime_ns for f in fotos), default=0))
        if mudancas_cache.get("versao") != versao:
            try:
                r = bo.mudancas_agora(app.state.consultas, pasta)
            except (ValueError, v.TseDataError) as exc:
                raise HTTPException(404, str(exc)) from exc
            mudancas_cache.update(versao=versao, resposta=r)
        return mudancas_cache["resposta"]

    @app.get("/api/cadeiras/planilha")
    def cadeiras_planilha(cargo: int, destacar: str = "") -> Response:
        """As listas de eleitos projetados em .xlsx — os mesmos números de /api/cadeiras (e do boletim)."""
        from apuracao import boletim as bo  # boletim importa este módulo: import tardio
        try:
            cad = _cadeiras_json(cargo, completo=True)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except v.TseDataError as exc:
            raise HTTPException(404, str(exc)) from exc
        escolhidos = [x.strip() for x in destacar.split(",") if x.strip()][:50]
        t = _abrangencia(dados.tabela("totais").filter(pl.col("CARGO") == cargo), "uf", uf)
        dt = t["DT_TOTALIZACAO"].max() if not t.is_empty() else None
        sobre = [("Cargo", f"{cad['ds_cargo']} — {uf}"), ("Vagas", str(cad["vagas"])),
                 ("Seções totalizadas", "—" if cad["pct_secoes"] is None else f"{cad['pct_secoes']:.2f}%".replace(".", ",")),
                 ("Totalização do TSE", f"{dt:%d/%m/%Y %H:%M}" if dt else "—"),
                 ("Situação", "resultado final" if cad["final"] else "projeção — muda até o fim da apuração"),
                 ("Fonte", cad["fonte"]), ("Gerado em", f"{al.agora_brasilia():%d/%m/%Y %H:%M}")]
        conteudo = bo.planilha_eleitos(cad, uf, escolhidos, sobre)
        rotulo = re.sub(r"[^a-z0-9]+", "_", v.normalize_text(cad["ds_cargo"]).lower()).strip("_")
        nome = f"eleitos_projetados_{rotulo}_{uf}_{dt:%Y-%m-%d_%Hh%M}.xlsx" if dt else f"eleitos_projetados_{rotulo}_{uf}.xlsx"
        return Response(conteudo, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        st = dados.status()
        tot = dados.tabela("totais")
        progresso = _rows(
            tot.filter(pl.col("ABRANGENCIA").is_in(["br", "uf"]))
            .group_by("ELEICAO", "ABRANGENCIA", "UF")
            .agg(pl.col("PCT_SECOES_TOTALIZADAS").max(), pl.col("DT_TOTALIZACAO").max(),
                 pl.col("TOTALIZACAO_FINAL").all())
            .sort("ELEICAO", "ABRANGENCIA")
        )
        return {"coletor": st, "thread_coletor": coletor_status, "uf": uf, "progresso": progresso,
                "tem_dados": tot.height > 0, "cargos": sorted(tot["CARGO"].unique().to_list()),
                "dados": str(dados_dir), "destacar_padrao": list(destacar), "ultimo_boletim": ultimo_boletim()}

    def ultimo_boletim() -> dict[str, Any] | None:
        """Título e hora do boletim mais recente (fotografias <dados>/boletins/boletim_*.json)."""
        pasta = dados_dir / "boletins"
        melhor = None
        for arq in pasta.glob("boletim_*.json") if pasta.exists() else []:
            try:
                f = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if melhor is None or f.get("gerado_em", "") > melhor["gerado_em"]:
                melhor = {"titulo": f.get("titulo"), "gerado_em": f.get("gerado_em", "")}
        return melhor

    @app.get("/api/presidente/ufs")
    def presidente_ufs() -> dict[str, Any]:
        """Presidente por UF (bloco "Por estado" do cartão Brasil); cache pela versão das duas tabelas."""
        (tot, vt), (cand, vc) = dados.com_versao("brasil_totais"), dados.com_versao("brasil_candidatos")
        chave = f"presidente_ufs:{vt}:{vc}"
        if chave not in geo_cache:
            for velha in [k for k in geo_cache if k.startswith("presidente_ufs:")]:
                del geo_cache[velha]
            geo_cache[chave] = presidente_por_uf(tot, cand)
        return geo_cache[chave]

    @app.get("/api/painel")
    def painel() -> dict[str, Any]:
        tot, cand, part = dados.tabela("totais"), dados.tabela("candidatos"), dados.tabela("partidos")
        historico = dados.tabela("serie")
        cartoes = []
        for cargo, abr in PAINEL:
            t = _abrangencia(tot.filter(pl.col("CARGO") == cargo), abr, uf)
            if t.is_empty():
                continue
            linha = t.row(0, named=True)
            proporcional = cargo in (6, 7, 8)
            c = _abrangencia(cand.filter(pl.col("CARGO") == cargo), abr, uf).sort("VOTOS", descending=True)
            cartao = {
                "cargo": cargo, "ds_cargo": linha["DS_CARGO"], "abrangencia": "BRASIL" if abr == "br" else uf,
                "proporcional": proporcional, "totais": {k: _jsonable(val) for k, val in linha.items()},
                "candidatos": _rows(c.head(TOP_PROPORCIONAL if proporcional else TOP_MAJORITARIO).select(
                    "NUMERO", "NOME_URNA", "PARTIDO", "FEDERACAO", "VOTOS", "PCT_VALIDOS", "SITUACAO", "ELEITO", "SEQ",
                    "DESTINACAO")),
                "n_candidatos": c.height,
                "serie": sr.para_grafico(historico, cargo, abr, uf),
            }
            if not proporcional and abr == "uf" and 0 < (linha["PCT_SECOES_TOTALIZADAS"] or 0) < 100:
                try:
                    cartao["projecao"] = _projecao_json(cargo, completo=False)
                except (ValueError, v.TseDataError) as exc:
                    logger.warning("projeção de %s indisponível: %s", cargo, exc)
            if proporcional:
                p = (_abrangencia(part.filter(pl.col("CARGO") == cargo), abr, uf)
                     .group_by("PARTIDO", "NR_PARTIDO", "FEDERACAO")
                     .agg(pl.col("VOTOS_TOTAL").sum(), pl.col("VOTOS_LEGENDA").sum(), pl.col("VAGAS_AGREMIACAO").max())
                     .sort("VOTOS_TOTAL", descending=True))
                validos = linha["VALIDOS"] or 0
                cartao["partidos"] = _rows(p.head(TOP_PARTIDOS).with_columns(
                    (100 * pl.col("VOTOS_TOTAL") / validos).round(2).alias("PCT_VALIDOS") if validos
                    else pl.lit(None).alias("PCT_VALIDOS")))
                if abr == "uf" and validos:
                    try:
                        cartao["cadeiras"] = _cadeiras_json(cargo, completo=False)
                    except (ValueError, v.TseDataError) as exc:
                        logger.warning("cadeiras de %s indisponíveis: %s", cargo, exc)
            cartoes.append(cartao)
        return {"uf": uf, "cartoes": cartoes}

    @app.get("/api/candidatos")
    def candidatos(cargo: int, abrangencia: str = "uf") -> list[dict[str, Any]]:
        abr = "br" if abrangencia == "br" else "uf"
        c = _abrangencia(dados.tabela("candidatos").filter(pl.col("CARGO") == cargo), abr, uf)
        return _rows(c.select("NUMERO", "NOME_URNA", "PARTIDO", "VOTOS").sort("VOTOS", descending=True))

    @app.get("/api/candidato")
    def candidato(cargo: int, numero: int) -> dict[str, Any]:
        cand = dados.tabela("candidatos").filter((pl.col("CARGO") == cargo) & (pl.col("NUMERO") == numero))
        uf_row = _abrangencia(cand, "uf", uf)
        if uf_row.is_empty():
            raise HTTPException(404, f"candidato {numero} não encontrado no cargo {cargo} em {uf}")
        tot = dados.tabela("totais").filter(pl.col("CARGO") == cargo)
        mun = _municipios_com_nome(dados, cand.filter(pl.col("ABRANGENCIA") == "mun")).join(
            tot.filter(pl.col("ABRANGENCIA") == "mun").select("CD_MUNICIPIO", "VALIDOS", "PCT_SECOES_TOTALIZADAS"),
            on="CD_MUNICIPIO", how="left",
        ).sort("VOTOS", descending=True)
        rank = (dados.tabela("candidatos").filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
                .with_columns(pl.col("VOTOS").rank("min", descending=True).over("CD_MUNICIPIO").alias("POSICAO_MUN"))
                .filter(pl.col("NUMERO") == numero).select("CD_MUNICIPIO", "POSICAO_MUN"))
        mun = mun.join(rank, on="CD_MUNICIPIO", how="left")
        r = uf_row.row(0, named=True)
        todos_uf = _abrangencia(dados.tabela("candidatos").filter(pl.col("CARGO") == cargo), "uf", uf)
        posicao = todos_uf.filter(pl.col("VOTOS") > r["VOTOS"]).height + 1
        resp = {"candidato": {k: _jsonable(val) for k, val in r.items()}, "posicao_uf": posicao,
                "n_candidatos_uf": todos_uf.height, "municipios": _rows(mun)}
        br = _abrangencia(cand, "br", uf)
        if not br.is_empty():
            resp["brasil"] = {k: _jsonable(val) for k, val in br.row(0, named=True).items()}
        if cargo in cd.PROPORCIONAIS:
            try:
                d, fonte = distribuicao(cargo)
                me = d.candidatos.filter(pl.col("NUMERO") == numero)
                if not me.is_empty():
                    m_ = me.row(0, named=True)
                    ag = d.agremiacoes.filter(pl.col("AGREMIACAO") == m_["AGREMIACAO"]).row(0, named=True)
                    resp["cadeira"] = {"situacao": m_["SITUACAO_PROJETADA"], "margem": m_["MARGEM"],
                                       "ordem": m_["ORDEM"], "agremiacao": m_["AGREMIACAO"],
                                       "vagas_agremiacao": ag["VAGAS"], "qe": d.qe, "fonte": fonte,
                                       "cand_qp": d.limites["cand_qp"]}
                    t = _abrangencia(dados.tabela("totais").filter(pl.col("CARGO") == cargo), "uf", uf)
                    linha = t.row(0, named=True) if not t.is_empty() else {}
                    pct = linha.get("PCT_SECOES_TOTALIZADAS") or 0
                    if not st_ano() and 0 < pct < 100 and not linha.get("TOTALIZACAO_FINAL"):
                        pr = projecao_cadeiras(cargo)
                        if pr.pct_apurado >= pcad.PCT_MINIMO:
                            eu = pr.candidatos.filter(pl.col("NUMERO") == numero)
                            if not eu.is_empty():
                                e_ = eu.row(0, named=True)
                                resp["cadeira"]["projecao"] = {"status": e_["STATUS"], "freq": e_["FREQ_ELEITO"],
                                                               "votos_proj": e_["VOTOS"],
                                                               "pct_apurado": pr.pct_apurado}
            except (ValueError, v.TseDataError) as exc:
                logger.warning("cadeira do candidato indisponível: %s", exc)
        return resp

    @app.get("/api/candidato/serie")
    def candidato_serie(cargo: int, numero: int, municipio: int | None = None) -> dict[str, Any]:
        """Evolução do candidato no tempo: estado (e Brasil, se presidente) e, opcionalmente, um município."""
        abrs: list[tuple[str, int | None]] = [("uf", None)] + ([("br", None)] if cargo == 1 else [])
        if municipio is not None:
            abrs.insert(0, ("mun", municipio))
        return {"series": sr.serie_candidato(dados.diretorio, cargo, numero, abrs)}

    def _historico(cargo: int, numero: int, cargo_ref: int | None, numero_ref: int | None) -> cp.HistoricoCandidato:
        try:
            return cp.historico_candidato(fonte_atual(), ref, uf, cargo, numero, cargo_ref, numero_ref)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/candidato/historico")
    def candidato_historico(cargo: int, numero: int, cargo_ref: int | None = None,
                            numero_ref: int | None = None) -> dict[str, Any]:
        """O candidato por município nesta eleição e na de referência (`ref`), com a variação."""
        h = _historico(cargo, numero, cargo_ref, numero_ref)
        a, b = h.sufixos
        return {"ano": h.ano, "ano_ref": h.ano_ref, "sufixos": [a, b], "criterio": h.criterio, "notas": h.notas,
                "atual": {k: _jsonable(val) for k, val in h.atual.items()},
                "anterior": {k: _jsonable(val) for k, val in h.anterior.items()} if h.anterior else None,
                "opcoes": h.opcoes, "linhas": _rows(h.tabela)}

    @app.get("/api/candidato/historico/planilha")
    def candidato_historico_planilha(cargo: int, numero: int, cargo_ref: int | None = None,
                                     numero_ref: int | None = None) -> Response:
        h = _historico(cargo, numero, cargo_ref, numero_ref)
        gerado = datetime.now(BRASILIA).strftime("%d/%m/%Y %H:%M")
        nome = f"historico_{numero}_{uf}_{h.ano}x{h.ano_ref or 'sem_ref'}.xlsx"
        return Response(cp.planilha_historico(h, uf, gerado),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.get("/api/mapa")
    def mapa(cargo: int, metrica: str, numero: int | None = None, momento: str | None = None) -> dict[str, Any]:
        """Valor por município agora ou, com `momento` (ISO), como estava naquela hora da apuração."""
        muns = dados.tabela("municipios")
        t = _parse_momento(momento)
        if t is None:
            tot = dados.tabela("totais").filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
            cand_mun = dados.tabela("candidatos").filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "mun"))
        else:
            tot = sr.totais_ate(dados.tabela("historico_totais"), cargo, t)
            nomes = _abrangencia(dados.tabela("candidatos").filter(pl.col("CARGO") == cargo), "uf", uf).select(
                "NUMERO", "NOME_URNA", "PARTIDO")
            cand_mun = sr.candidatos_ate(dados.diretorio, cargo, t,
                                         numero if metrica in METRICAS_CANDIDATO else None).join(
                nomes, on="NUMERO", how="left")
        if metrica in METRICAS_TOTAIS:
            col, rotulo = METRICAS_TOTAIS[metrica]
            expr = (pl.col("PCT_BRANCOS") + pl.col("PCT_NULOS")) if col is None else pl.col(col)
            df = tot.select("CD_MUNICIPIO", expr.alias("VALOR"))
            tipo = "sequencial"
        elif metrica in METRICAS_CANDIDATO:
            if numero is None:
                raise HTTPException(400, "informe o número do candidato")
            c = cand_mun.filter(pl.col("NUMERO") == numero)
            col = "PCT_VALIDOS" if metrica == "pct_candidato" else "VOTOS"
            df = c.select("CD_MUNICIPIO", pl.col(col).alias("VALOR"))
            nome = _abrangencia(dados.tabela("candidatos").filter(
                (pl.col("CARGO") == cargo) & (pl.col("NUMERO") == numero)), "uf", uf)["NOME_URNA"].to_list()
            rotulo = f"{METRICAS_CANDIDATO[metrica]} — nº {numero}{' ' + nome[0] if nome else ''}"
            tipo = "sequencial"
        elif metrica == "vencedor":
            df = (cand_mun.sort("VOTOS", descending=True).group_by("CD_MUNICIPIO", maintain_order=True).first()
                  .select("CD_MUNICIPIO", pl.col("NUMERO").alias("VALOR"),
                          pl.format("{} ({}) — {}%", pl.col("NOME_URNA"), pl.col("PARTIDO"),
                                    pl.col("PCT_VALIDOS").round(2)).alias("ROTULO")))
            rotulo, tipo = "Mais votado no município", "categorico"
        else:
            raise HTTPException(400, f"métrica desconhecida: {metrica}")
        df = df.join(muns.select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO"), on="CD_MUNICIPIO", how="left")
        itens = {str(r["CD_MUNICIPIO_IBGE"]): {"valor": r["VALOR"], "municipio": r["NM_MUNICIPIO"],
                                               "rotulo": r.get("ROTULO")}
                 for r in df.iter_rows(named=True) if r["CD_MUNICIPIO_IBGE"] is not None}
        resp: dict[str, Any] = {"metrica": metrica, "rotulo": rotulo, "tipo": tipo, "itens": itens,
                                "momento": t.isoformat() if t else None}
        if tipo == "categorico":  # legenda: candidatos na ordem de votos na UF (a página colore só os 3 primeiros)
            uf_c = _abrangencia(dados.tabela("candidatos").filter(pl.col("CARGO") == cargo), "uf", uf)
            resp["categorias"] = _rows(uf_c.sort("VOTOS", descending=True).select("NUMERO", "NOME_URNA", "PARTIDO"))
        return resp

    @app.get("/api/mapa/momentos")
    def mapa_momentos(cargo: int) -> dict[str, Any]:
        """Horas das totalizações municipais do cargo (linha do tempo do mapa)."""
        return {"momentos": [d.isoformat() for d in sr.momentos(dados.tabela("historico_totais"), cargo)]}

    @app.get("/api/metricas")
    def metricas() -> dict[str, Any]:
        return {"totais": {k: r for k, (_, r) in METRICAS_TOTAIS.items()}, "candidato": METRICAS_CANDIDATO,
                "vencedor": "Mais votado no município"}

    def fonte_atual() -> cp.Fonte:
        return cp.Fonte(ano=dados.status().get("ano") or 2026, totais=dados.tabela("totais"),
                        candidatos=dados.tabela("candidatos"), partidos=dados.tabela("partidos"),
                        municipios=dados.tabela("municipios"))

    @app.get("/api/comparacao/info")
    def comparacao_info() -> dict[str, Any]:
        if ref is None:
            return {"disponivel": False}
        return {"disponivel": True, "ano_a": ref.ano, "ano_b": fonte_atual().ano,
                "metricas": {k: r for k, (_, r, _) in cp.METRICAS_TOTAIS.items()},
                "cargos": sorted(set(ref.totais["CARGO"].to_list()) & set(dados.tabela("totais")["CARGO"].to_list()))}

    @app.get("/api/comparacao/partidos")
    def comparacao_partidos(cargo: int) -> list[dict[str, Any]]:
        if ref is None:
            raise HTTPException(404, "sem eleição de referência (use --comparar-com)")
        return _rows(cp.partidos_disponiveis(ref, fonte_atual(), cargo))

    @app.get("/api/bancadas")
    def bancadas_api(cargo: int) -> dict[str, Any]:
        """Bancadas de deputado desta eleição × a de referência (partidos pela entidade; reeleitos e novatos)."""
        from apuracao import bancadas as bc
        if ref is None:
            raise HTTPException(404, "sem eleição de referência (use --comparar-com)")
        try:
            b = bc.bancadas(fonte_atual(), ref, uf, cargo)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ano": b.ano, "ano_ref": b.ano_ref, "cargo": cargo, "ds_cargo": bc.NOMES[cargo], "resumo": b.resumo,
                "partidos": _rows(b.partidos), "eleitos": _rows(b.eleitos), "sairam": _rows(b.sairam)}

    @app.get("/api/bancadas/planilha")
    def bancadas_planilha(cargo: int) -> Response:
        from apuracao import bancadas as bc
        if ref is None:
            raise HTTPException(404, "sem eleição de referência (use --comparar-com)")
        try:
            b = bc.bancadas(fonte_atual(), ref, uf, cargo)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        nome = f"bancadas_{cargo}_{uf}_{b.ano}x{b.ano_ref}.xlsx"
        return Response(bc.planilha(b, uf), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.get("/api/comparacao/variacao")
    def comparacao_variacao(cargo: int, partidos: str, ponderar: bool = False) -> dict[str, Any]:
        """% dos válidos de até 3 partidos na referência × agora por município, com a estatística da variação."""
        if ref is None:
            raise HTTPException(404, "sem eleição de referência (use --comparar-com)")
        try:
            d = cp.variacao_partidos(ref, fonte_atual(), cargo, partidos.split(","), ponderar)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return _limpar(d)

    @app.get("/api/comparacao")
    def comparacao(cargo: int, metrica: str, partido: str | None = None, numero_a: int | None = None,
                   numero_b: int | None = None) -> dict[str, Any]:
        if ref is None:
            raise HTTPException(404, "sem eleição de referência (use --comparar-com)")
        atual = fonte_atual()
        try:
            df = cp.comparar(ref, atual, cargo, metrica, partido, numero_a, numero_b)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if metrica in cp.METRICAS_TOTAIS:
            rotulo, unidade = cp.METRICAS_TOTAIS[metrica][1], cp.METRICAS_TOTAIS[metrica][2]
        elif metrica == "partido":
            sa, sb = cp.siglas_do_partido(ref, atual, partido)
            mesmo = " + ".join(sa) == " + ".join(sb)
            rotulo = (f"% dos válidos — {partido}" if mesmo else
                      f"% dos válidos — {' + '.join(sb) or 'sem correspondente'} ({atual.ano}) × "
                      f"{' + '.join(sa) or 'sem correspondente'} ({ref.ano})")
            unidade = "pp"
        else:
            rotulo, unidade = f"% dos válidos — nº {numero_a} ({ref.ano}) × nº {numero_b} ({atual.ano})", "pp"
        uf_row = df.filter(pl.col("ABRANGENCIA") == "uf")
        mun = df.filter(pl.col("ABRANGENCIA") == "mun")
        return {
            "ano_a": ref.ano, "ano_b": atual.ano, "rotulo": rotulo, "unidade": unidade,
            "uf": {k: _jsonable(val) for k, val in uf_row.row(0, named=True).items()} if uf_row.height else None,
            "municipios": _rows(mun.select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO", "VALOR_A", "VALOR_B", "DIF")),
            "itens": {str(r["CD_MUNICIPIO_IBGE"]): {"municipio": r["NM_MUNICIPIO"], "valor": r["DIF"],
                                                    "a": r["VALOR_A"], "b": r["VALOR_B"]}
                      for r in mun.iter_rows(named=True) if r["CD_MUNICIPIO_IBGE"] is not None},
        }

    def malha_municipios() -> dict[str, Any]:
        if "malha" not in geo_cache:
            try:
                path = ibge.caminho("malha_municipios", cache_dir, uf)
            except (requests.RequestException, ValueError) as exc:
                raise HTTPException(503, f"malha do IBGE indisponível: {exc}") from exc
            geo_cache["malha"] = json.loads(path.read_text())
        return geo_cache["malha"]

    bairros = br.Bairros(uf, cache_dir)

    def malha_bairros() -> dict[str, Any]:
        try:
            return bairros.geo()
        except (v.TseDataError, requests.RequestException) as exc:
            raise HTTPException(503, f"malha de bairros do IBGE indisponível: {exc}") from exc

    @app.get("/geo/bairros.geojson")
    def geo_bairros() -> JSONResponse:
        return JSONResponse(malha_bairros())

    @app.get("/api/bairros/anos")
    def bairros_anos() -> dict[str, Any]:
        """Anos com microdados por seção no cache (e cargos de cada um) para o mapa por bairro."""
        return {"anos": {str(a): c for a, c in bairros.anos_disponiveis().items()},
                "cargos": {str(k): n.title() for k, n in br.CARGOS.items()}, "metricas": br.METRICAS}

    comp_bairros = br.ComparacaoBairros(bairros)

    @app.get("/api/comparacao/bairros/info")
    def comparacao_bairros_info() -> dict[str, Any]:
        """Anos com votos por seção (e cargos) e anos com cadastro de eleitorado, para a comparação por bairro."""
        return {"anos_votos": {str(a): c for a, c in bairros.anos_disponiveis().items()},
                "anos_cadastro": comp_bairros.anos_cadastro(),
                "cargos": {str(k): n.title() for k, n in br.CARGOS.items()},
                "metricas": {k: r for k, (r, _) in br.METRICAS_COMPARACAO.items()}}

    @app.get("/api/comparacao/bairros/partidos")
    def comparacao_bairros_partidos(ano_a: int, cargo_a: int, ano_b: int, cargo_b: int,
                                    turno: int = 1) -> list[dict[str, Any]]:
        malha_bairros()
        return _rows(comp_bairros.partidos(ano_a, cargo_a, ano_b, cargo_b, turno))

    @app.get("/api/comparacao/bairros")
    def comparacao_bairros(ano_a: int, cargo_a: int, ano_b: int, cargo_b: int, metrica: str,
                           partido: int | None = None, numero_a: int | None = None, numero_b: int | None = None,
                           turno: int = 1) -> dict[str, Any]:
        """Diferença por bairro entre dois anos (e cargos), no formato de /api/comparacao."""
        malha_bairros()
        try:
            df, resumo = comp_bairros.comparar(ano_a, cargo_a, ano_b, cargo_b, metrica, partido, numero_a, numero_b,
                                               turno)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (v.TseDataError, requests.RequestException) as exc:
            raise HTTPException(404, f"dados indisponíveis ({exc}); votos por bairro de 2026 só depois que o TSE "
                                     "publicar os microdados por seção") from exc
        rotulo, unidade = br.METRICAS_COMPARACAO[metrica]
        nome_cargo = lambda c: br.CARGOS.get(c, str(c)).title()  # noqa: E731
        if metrica == "partido":
            sa, sb = comp_bairros.siglas(ano_a).get(partido), comp_bairros.siglas(ano_b).get(partido)
            rotulo = f"{rotulo} — {partido} {sa or ''}{'/' + sb if sb and sb != sa else ''}".rstrip()
        elif metrica == "candidato":
            rotulo = f"{rotulo} — nº {numero_a} ({ano_a}) × nº {numero_b} ({ano_b})"
        subtitulo = (f"Cadastro de eleitorado {ano_a} × {ano_b}" if metrica == "eleitorado"
                     else f"{nome_cargo(cargo_a)} {ano_a} × {nome_cargo(cargo_b)} {ano_b}")
        nomes = bairros.nomes()
        df = df.with_columns(pl.col("CD_BAIRRO").map_elements(
            lambda c: " — ".join(nomes.get(c, ("?", "?"))), return_dtype=pl.String).alias("NM_MUNICIPIO"))
        return {
            "camada": "bairros", "ano_a": ano_a, "ano_b": ano_b, "rotulo": rotulo, "unidade": unidade,
            "subtitulo": subtitulo, "uf": resumo,
            "municipios": _rows(df.select("CD_BAIRRO", "NM_MUNICIPIO", "VALOR_A", "VALOR_B", "DIF")),
            "itens": {r["CD_BAIRRO"]: {"municipio": r["NM_MUNICIPIO"], "valor": r["DIF"], "a": r["VALOR_A"],
                                       "b": r["VALOR_B"]} for r in df.iter_rows(named=True)},
        }

    perfis = {"bairro": pf.PerfilVoto(comp_bairros), "local": pfl.PerfilVotoLocal(comp_bairros),
              "area": ap.PerfilVotoArea(comp_bairros)}

    def _pv(unidade: str) -> pf.PerfilVoto:
        """Unidade de análise: "bairro" (malha de bairros do IBGE), "local" (local de votação, estado todo) ou
        "area" (área de ponderação do Censo: a única com religião e os demais resultados da amostra)."""
        if unidade not in perfis:
            raise HTTPException(400, f"unidade deve ser uma de {sorted(perfis)}")
        return perfis[unidade]

    def _alvo(ano: int, cargo: int, turno: int, numero: int | None, partido: int | None) -> pf.Alvo:
        try:
            return pf.Alvo(ano, cargo, turno, numero, partido)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def _perfil(chamada: Any, unidade: str = "bairro") -> Any:
        if unidade == "bairro":
            malha_bairros()
        try:
            return chamada()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (v.TseDataError, requests.RequestException) as exc:
            raise HTTPException(404, f"dados indisponíveis ({exc}); votos por bairro de 2026 só depois que o TSE "
                                     "publicar os microdados por seção") from exc

    @app.get("/api/perfil/info")
    def perfil_info(unidade: str = "bairro") -> dict[str, Any]:
        """Anos com votos por seção (e cargos), indicadores de perfil e municípios da unidade escolhida."""
        pv = _pv(unidade)
        return _perfil(lambda: {"unidade": unidade, "anos": {str(a): c for a, c in bairros.anos_disponiveis().items()},
                                "cargos": {str(k): n.title() for k, n in br.CARGOS.items()},
                                "indicadores": pv.indicadores(), "municipios": _rows(pv.municipios())}, unidade)

    @app.get("/api/perfil/candidatos")
    def perfil_candidatos(ano: int, cargo: int, turno: int = 1, municipio: int | None = None,
                          unidade: str = "bairro") -> list[dict[str, Any]]:
        pv = _pv(unidade)
        return _perfil(lambda: _rows(pv.candidatos(ano, cargo, turno, municipio)), unidade)

    @app.get("/api/perfil/partidos")
    def perfil_partidos(ano: int, cargo: int, turno: int = 1) -> list[dict[str, Any]]:
        def lista() -> list[dict[str, Any]]:
            ps = comp_bairros.partidos(ano, cargo, ano, cargo, turno).filter(pl.col("VOTOS_A").is_not_null())
            return _rows(ps.sort("VOTOS_A", descending=True).select("PARTIDO", pl.col("SIGLA_A").alias("SIGLA"),
                                                                    pl.col("VOTOS_A").alias("VOTOS")))
        return _perfil(lista)

    @app.get("/api/perfil/correlacoes")
    def perfil_correlacoes(ano: int, cargo: int, turno: int = 1, numero: int | None = None,
                           partido: int | None = None, min_validos: int = Query(200, ge=0),
                           ponderar: bool = False, municipio: int | None = None, unidade: str = "bairro") -> dict[str, Any]:
        """Correlação do voto com cada indicador de perfil (TSE e Censo), da mais forte para a mais fraca."""
        y, pv = _alvo(ano, cargo, turno, numero, partido), _pv(unidade)
        return _perfil(lambda: {"rotulo_y": pv.rotulo(y, municipio),
                                "correlacoes": pv.correlacoes(y, min_validos, ponderar, municipio)}, unidade)

    @app.get("/api/perfil/regressao")
    def perfil_regressao(ano: int, cargo: int, indicadores: str, turno: int = 1, numero: int | None = None,
                         partido: int | None = None, min_validos: int = Query(200, ge=0), ponderar: bool = False,
                         municipio: int | None = None, unidade: str = "bairro") -> dict[str, Any]:
        """Vários indicadores ao mesmo tempo (`indicadores=pct_superior,renda_media,...`): efeito de cada um,
        em p.p. por +1 desvio-padrão, com os demais fixos; IC 95%, p, VIF e o r simples para comparar."""
        y, pv = _alvo(ano, cargo, turno, numero, partido), _pv(unidade)
        chaves = [k for k in indicadores.split(",") if k]
        return _perfil(lambda: pv.regressao(y, chaves, min_validos, ponderar, municipio), unidade)

    @app.get("/api/perfil/dispersao")
    def perfil_dispersao(ano: int, cargo: int, x: str, turno: int = 1, numero: int | None = None,
                         partido: int | None = None, x_ano: int | None = None, x_cargo: int | None = None,
                         x_turno: int = 1, x_numero: int | None = None, x_partido: int | None = None,
                         min_validos: int = Query(200, ge=0), ponderar: bool = False,
                         municipio: int | None = None, unidade: str = "bairro") -> dict[str, Any]:
        """Um ponto por bairro ou local: X = indicador de perfil ou voto em outra eleição (x=voto), Y = voto."""
        y, pv = _alvo(ano, cargo, turno, numero, partido), _pv(unidade)
        if x == "voto":
            if x_ano is None or x_cargo is None:
                raise HTTPException(400, "para x=voto informe x_ano e x_cargo")
            eixo: str | pf.Alvo = _alvo(x_ano, x_cargo, x_turno, x_numero, x_partido)
        else:
            eixo = x
        d = _perfil(lambda: pv.dispersao(y, eixo, min_validos, ponderar, municipio), unidade)
        cols = ["CD_BAIRRO", "BAIRRO", "X", "Y", "VALIDOS", "RESIDUO"]
        return {**{k: d[k] for k in ("rotulo_x", "rotulo_y", "estatistica", "min_validos", "ponderado")},
                "pontos": _rows(d["pontos"].select(cols)), "acima": _rows(d["acima"].select(cols)),
                "abaixo": _rows(d["abaixo"].select(cols))}

    mapa_locais_cache: dict[tuple, dict[str, Any]] = {}

    @app.get("/api/mapa/locais")
    def mapa_locais(ano: int, camada: str = "voto", cargo: int = 3, turno: int = 1, metrica: str | None = None,
                    numero: int | None = None, indicador: str | None = None, municipio: int | None = None,
                    min_validos: int = Query(50, ge=0), ano_ref: int | None = None) -> dict[str, Any]:
        """Um ponto por local de votação (microdados): voto, perfil do eleitorado, resíduo do Perfil × voto ou
        variação desde `ano_ref` (padrão ano − 4). `municipio`: código IBGE; `numero` de 2 dígitos em cargo
        proporcional = partido (na variação, sempre o partido do número)."""
        chave = (ano, camada, cargo, turno, metrica, numero, indicador, municipio, min_validos, ano_ref)
        if chave not in mapa_locais_cache:
            d = _perfil(lambda: ml.pontos(perfis["local"], ano, camada, cargo, turno, metrica, numero, indicador,
                                          municipio, min_validos, ano_ref), "local")
            if len(mapa_locais_cache) > 24:
                mapa_locais_cache.clear()
            mapa_locais_cache[chave] = d
        return mapa_locais_cache[chave]

    def malha_areas() -> dict[str, Any]:
        if "malha_areas" not in geo_cache:
            try:
                geo_cache["malha_areas"] = ap.malha(uf, cache_dir)
            except (v.TseDataError, requests.RequestException) as exc:
                raise HTTPException(503, f"malha das áreas de ponderação indisponível: {exc}") from exc
        return geo_cache["malha_areas"]

    @app.get("/geo/areas.geojson")
    def geo_areas() -> JSONResponse:
        return JSONResponse(malha_areas())

    mapa_areas_cache: dict[tuple, dict[str, Any]] = {}

    @app.get("/api/mapa/areas")
    def mapa_areas(ano: int, camada: str = "voto", cargo: int = 3, turno: int = 1, metrica: str | None = None,
                   numero: int | None = None, indicador: str | None = None, municipio: int | None = None,
                   min_validos: int = Query(50, ge=0), ano_ref: int | None = None) -> dict[str, Any]:
        """Valor por área de ponderação do Censo (TODO 25): voto (microdados somados pelos locais da área), um
        indicador de perfil da unidade área (inclusive a religião e a amostra do Censo), o resíduo do Perfil × voto
        ou a variação desde `ano_ref` (padrão ano − 4) — estas duas em p.p., escala divergente."""
        chave = (ano, camada, cargo, turno, metrica, numero, indicador, municipio, min_validos, ano_ref)
        if chave not in mapa_areas_cache:
            d = _perfil(lambda: ap.mapa(perfis["area"], ano, camada, cargo, turno, metrica, numero, indicador,
                                        municipio, min_validos, ano_ref), "area")
            if len(mapa_areas_cache) > 24:
                mapa_areas_cache.clear()
            mapa_areas_cache[chave] = d
        return mapa_areas_cache[chave]

    @app.get("/api/mapa/bairros")
    def mapa_bairros(ano: int, cargo: int, metrica: str, numero: int | None = None, turno: int = 1) -> dict[str, Any]:
        """Valor por bairro do IBGE a partir dos votos de cada local de votação (microdados por seção)."""
        if metrica not in br.METRICAS:
            raise HTTPException(400, f"métrica indisponível por bairro: {metrica}. Use: {', '.join(br.METRICAS)}")
        malha_bairros()
        try:
            if metrica in br.PARTICIPACAO:
                vb, df = None, br.metrica_participacao(bairros.participacao(ano, cargo, turno), metrica)
            else:
                vb = bairros.votos(ano, cargo, turno)
                df = br.metrica(vb, cargo, metrica, numero)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (v.TseDataError, requests.RequestException) as exc:
            raise HTTPException(404, f"sem microdados por seção de {ano} ({exc}); para 2026 o TSE publica "
                                     "alguns dias depois do pleito") from exc
        nomes = bairros.nomes()
        itens = {r["CD_BAIRRO"]: {"valor": r["VALOR"], "municipio": " — ".join(nomes.get(r["CD_BAIRRO"], ("?", "?"))),
                                  "rotulo": r.get("ROTULO")} for r in df.iter_rows(named=True)}
        rotulo = f"{br.METRICAS[metrica]} — {ano}"
        if vb is not None and numero is not None and metrica in ("pct_candidato", "votos_candidato"):
            nome = vb.filter(pl.col("NR_VOTAVEL") == numero)["NM_VOTAVEL"].head(1).to_list()
            rotulo = f"{br.METRICAS[metrica]} — nº {numero}{' ' + nome[0] if nome else ''} — {ano}"
        resp: dict[str, Any] = {"metrica": metrica, "rotulo": rotulo, "ano": ano,
                                "tipo": "categorico" if metrica == "vencedor" else "sequencial", "itens": itens,
                                "cobertura": {"bairros_com_dado": len(itens), "bairros": len(nomes),
                                              "locais_em_bairro": bairros.local_bairro(ano).height}}
        if metrica == "vencedor":
            resp["categorias"] = br.categorias(vb, cargo)
        return resp

    @app.get("/geo/ufs.geojson")
    def malha_ufs() -> JSONResponse:
        if "malha_ufs" not in geo_cache:
            try:
                path = ibge.caminho("malha_ufs", cache_dir, uf)
            except (requests.RequestException, ValueError, v.TseDataError) as exc:
                raise HTTPException(503, f"malha das UFs do IBGE indisponível: {exc}") from exc
            geo_cache["malha_ufs"] = json.loads(path.read_text())
        return JSONResponse(geo_cache["malha_ufs"])

    @app.get("/geo/municipios.geojson")
    def malha() -> JSONResponse:
        return JSONResponse(malha_municipios())

    @app.post("/api/exportar/mapa")
    def exportar_mapa(pedido: PedidoExportacao) -> Response:
        """Arquivo PNG/JPEG/SVG do mapa com as cores e a legenda que a página mostra."""
        if pedido.camada == "municipios":
            geo, chave, contornos = malha_municipios(), "codarea", None
        elif pedido.camada == "locais":
            if pedido.ano is None:
                raise HTTPException(400, "camada locais: informe o ano")
            loc = _perfil(lambda: perfis["local"].locais(pedido.ano), "local")
            geo = {"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["LON"], r["LAT"]]},
                 "properties": {"UNIDADE": r["UNIDADE"], "QT_ELEITORES": r["QT_ELEITORES"]}}
                for r in loc.select("UNIDADE", "LAT", "LON", "QT_ELEITORES").iter_rows(named=True)]}
            chave, contornos = "UNIDADE", malha_municipios()
        elif pedido.camada == "areas":
            geo, chave, contornos = malha_areas(), "CD_AP", malha_municipios()
        else:
            geo, chave = malha_bairros(), "CD_BAIRRO"
            contornos = malha_municipios()
        p = ex.PedidoMapa(formato=pedido.formato, titulo=pedido.titulo, subtitulo=pedido.subtitulo,
                          cores=pedido.cores, legenda=[(c, t) for c, t in pedido.legenda], fonte=pedido.fonte,
                          fundo=pedido.fundo, texto=pedido.texto, sem_dado=pedido.sem_dado,
                          contorno=pedido.contorno, dpi=pedido.dpi, extras=pedido.extras)
        try:
            conteudo = ex.renderizar(geo, chave, p, contornos)
        except ex.PedidoInvalido as exc:
            raise HTTPException(400, str(exc)) from exc
        nome = re.sub(r"[^a-z0-9]+", "_", v.normalize_text(pedido.nome or "mapa").lower()).strip("_") or "mapa"
        return Response(conteudo, media_type=ex.FORMATOS[pedido.formato],
                        headers={"Content-Disposition": f'attachment; filename="{nome}.{pedido.formato}"'})

    @app.get("/geo/locais.geojson")
    def locais(ano: int = 2026) -> JSONResponse:
        chave = f"locais{ano}"
        if chave not in geo_cache:
            from apuracao import eleitorado as el
            try:
                pl_ = el.places(el.load_sections(ano, uf, cache_dir))
            except (v.TseDataError, requests.RequestException) as exc:
                raise HTTPException(503, f"cadastro de eleitorado {ano} indisponível: {exc}") from exc
            feats = [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["NR_LONGITUDE"], r["NR_LATITUDE"]]},
                 "properties": {"nome": r["NM_LOCAL_VOTACAO"], "bairro": r["NM_BAIRRO"], "municipio": r["NM_MUNICIPIO"],
                                "zona": r["NR_ZONA"], "local": r["NR_LOCAL_VOTACAO"], "eleitores": r["QT_ELEITORES"],
                                "secoes": r["N_SECOES"]}}
                for r in pl_.filter(pl.col("NR_LATITUDE").is_not_null()).iter_rows(named=True)
            ]
            geo_cache[chave] = {"type": "FeatureCollection", "features": feats}
        return JSONResponse(geo_cache[chave])

    @app.get("/api/planilha")
    def planilha(ano: int, cargo: str, numero: int, municipio: str | None = None, turno: int = 1,
                 comparar_com: int | None = Query(None)) -> FileResponse:
        import planilha_candidato as pc_cli
        saida = Path(tempfile.mkdtemp(prefix="planilha_")) / f"planilha_{numero}_{uf}_{ano}_t{turno}.xlsx"
        cfg = pc_cli.PlanilhaConfig(year=ano, uf=uf, turno=turno, office=cargo, candidate=numero,
                                    municipality=municipio or None, cache_dir=str(cache_dir), output=str(saida),
                                    tre_json=None, compare_with=comparar_com)
        try:
            pc_cli.run(cfg)
        except (v.TseDataError, requests.RequestException) as exc:
            shutil.rmtree(saida.parent, ignore_errors=True)
            raise HTTPException(400, str(exc)) from exc
        # o diretório temporário sai depois do envio (antes ficava no /tmp a cada planilha pedida)
        return FileResponse(saida, filename=saida.name,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            background=BackgroundTask(shutil.rmtree, saida.parent, ignore_errors=True))

    transf_cache: dict[tuple, dict[str, Any]] = {}
    transf_trava = threading.Lock()   # um cálculo por vez (10–30 s): pedidos iguais esperam e reaproveitam

    def dir_1t() -> Path | None:
        """No 2º turno, o diretório do 1º: <ambiente>_t2 -> <ambiente> (coletor) ou <nome>_t1 (histórico importado);
        com a UF no nome (rodada 39), <ambiente>_t2_<UF> -> <ambiente>_<UF> (no RJ, também a pasta antiga sem UF)."""
        from apuracao.ufs import dir_uf
        m_ = re.match(r"^(?P<base>.+)_t2(?:_(?P<uf>[A-Z]{2}))?$", dados_dir.name)
        if not m_:
            return None
        base, uf_ = m_["base"], m_["uf"]
        bases = (dados_dir.with_name(base), dados_dir.with_name(base + "_t1"))
        candidatos = [dir_uf(b, uf_) for b in bases] if uf_ else list(bases)
        return next((d for d in candidatos if (d / "ultimo" / "totais.parquet").exists()), None)

    @app.get("/api/transferencia/info")
    def transferencia_info() -> dict[str, Any]:
        """Anos com microdados no cache e se há os dois turnos do coletor (noite do 2º turno)."""
        anos = sorted({int(m.group(1)) for p in cache_dir.glob("votacao_secao_*.zip")
                       if (m := re.match(r"votacao_secao_(\d{4})_", p.name))})
        d1 = dir_1t()
        tempo_real = bool(d1 and (d1 / "ultimo" / "totais.parquet").exists() and dados.tabela("totais").height)
        cargos_tr = sorted(set(dados.tabela("totais")["CARGO"].unique().to_list()) & {1, 3, 11}) if tempo_real else []
        return {"anos": anos, "tempo_real": tempo_real, "cargos_tempo_real": cargos_tr,
                "cargos": {str(a): ([11] if a % 4 == 0 else [1, 3]) for a in anos}}

    @app.get("/api/transferencia/municipios")
    def transferencia_municipios(ano: int, cargo: int) -> list[dict[str, Any]]:
        """Municípios (TSE) do arquivo de votos do ano; em prefeito, só os que tiveram 2º turno."""
        try:
            if cargo == 11:
                det = v.load_section_details(ano, uf, cache_dir)
                com_2t = det.filter((pl.col("NR_TURNO") == 2) & (pl.col("CD_CARGO") == 11)).select(
                    "CD_MUNICIPIO").unique().collect()["CD_MUNICIPIO"].to_list()
            lz = v.load_section_votes(ano, uf, tf.NOMES_CARGO.get(cargo, "presidente"), cache_dir, False)
            muns = lz.filter(pl.col("SG_UF") == uf).select("CD_MUNICIPIO", "NM_MUNICIPIO").unique().collect()
        except (v.TseDataError, requests.RequestException) as exc:
            raise HTTPException(404, str(exc)) from exc
        if cargo == 11:
            muns = muns.filter(pl.col("CD_MUNICIPIO").is_in(com_2t))
        return _rows(muns.sort("NM_MUNICIPIO"))

    @app.get("/api/transferencia")
    def transferencia(fonte: str = "microdados", ano: int = 2022, cargo: int = 1, nivel: str = "local",
                      municipio: int | None = None) -> dict[str, Any]:
        """Para onde foi cada grupo do 1º turno no 2º (matriz com IC), abstenção extra, validação e, por
        unidade, os destaques. `fonte=tempo_real`: municípios, do que o coletor gravou nos dois turnos."""
        if fonte not in ("microdados", "tempo_real") or nivel not in tf.NIVEIS:
            raise HTTPException(400, "fonte: microdados|tempo_real; nível: secao|local|municipio")
        if fonte == "tempo_real":
            d1 = dir_1t()
            if not d1:
                raise HTTPException(400, "tempo real só no site do 2º turno (--turno 2)")
            versao = tuple((d / "ultimo" / "candidatos.parquet").stat().st_mtime_ns
                           for d in (d1, dados_dir) if (d / "ultimo" / "candidatos.parquet").exists())
            chave: tuple = ("tr", cargo, versao)
        else:
            chave = ("md", ano, cargo, nivel, municipio)
        with transf_trava:
            if chave not in transf_cache:
                try:
                    if fonte == "tempo_real":
                        res = tf.analisar(tf.unidades_divulgacao(d1, dados_dir, cargo, uf))
                    else:
                        res = tf.calcular(ano, uf, cargo, nivel, cache_dir, municipio)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                except (v.TseDataError, requests.RequestException, OSError) as exc:
                    raise HTTPException(404, str(exc)) from exc
                if len(transf_cache) > 12:
                    transf_cache.clear()
                transf_cache[chave] = tf.resumo(res)
            return transf_cache[chave]

    app.state.consultas = Consultas(dados, uf, status, painel, lambda cargo: _projecao_json(cargo, completo=True),
                                    lambda cargo: _cadeiras_json(cargo, completo=True))
    vigia = al.Vigia(app.state.consultas, dados_dir / al.ARQUIVO, coletor_status, interesse)
    app.state.vigia = vigia  # a verificação periódica é do site_apuracao (thread) ou do ensaio

    @app.get("/api/alertas")
    def alertas(desde: int = 0) -> dict[str, Any]:
        return vigia.lista(desde)

    @app.post("/api/alertas/interesse")
    def alertas_interesse(pedido: PedidoInteresse) -> dict[str, Any]:
        if dados.status().get("ano"):
            raise HTTPException(400, "eleição passada: não há alertas")
        try:
            vigia.definir_interesse(pedido.cargo, pedido.numero, pedido.acompanhar)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return vigia.lista(10**9)

    @app.middleware("http")
    async def sem_cache_da_pagina(request: Request, call_next: Any) -> Response:
        # sem Cache-Control o navegador reaproveita index.html/app.js antigos depois de uma atualização do site;
        # "no-cache" = sempre confere (ETag/304), então o custo é só a revalidação
        resp = await call_next(request)
        if not caminho_no_app(request).startswith(("/api/", "/geo/", "/vendor/")):
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def eh_loopback(host: str) -> bool:
    """O endereço é desta máquina? (127.0.0.1, ::1, localhost)"""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _parse_momento(momento: str | None) -> datetime | None:
    if not momento:
        return None
    try:
        t = datetime.fromisoformat(momento)
    except ValueError as exc:
        raise HTTPException(400, f"momento inválido: {momento}") from exc
    # a hora da totalização do TSE é a de Brasília, sem fuso: um momento com fuso é convertido para ela
    return t.astimezone(BRASILIA).replace(tzinfo=None) if t.tzinfo else t


def _municipios_com_nome(dados: Dados, df: pl.DataFrame) -> pl.DataFrame:
    muns = dados.tabela("municipios").select("CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO")
    return df.join(muns, on="CD_MUNICIPIO", how="left").select(
        "CD_MUNICIPIO", "CD_MUNICIPIO_IBGE", "NM_MUNICIPIO", "VOTOS", "PCT_VALIDOS")
