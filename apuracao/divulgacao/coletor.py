"""Coleta incremental da divulgação do TSE e persistência dos snapshots.

A cada ciclo:
  1. EA15 da UF (uma linha por município + a linha da UF) de cada eleição e, para a
     eleição federal, EA14 (linha br e uma linha por UF, para o presidente nas outras UFs);
  2. compara a hora da última totalização (dt/ht) de cada abrangência com o ciclo
     anterior e baixa o EA20 SÓ dos cargos cujas abrangências mudaram (no 1º ciclo, todos);
  3. grava o JSON bruto de cada arquivo que mudou (o TSE sobrescreve os parciais; o
     histórico é nosso), as tabelas "último estado" em Parquet e a série temporal dos totais.

Estrutura em <destino>/ (padrão dados_2026/<ambiente>/):
  raw/<eleicao>/<arquivo>/<AAAAMMDD>_<HHMMSS>_<idg>_<sha1[:10]>.json.gz
  ultimo/{totais,candidatos,partidos,municipios,acompanhamento}.parquet
  ultimo/brasil_{totais,candidatos}.parquet   presidente em cada UF (27 + zz, exterior)
  raw_brasil/<eleicao>/<arquivo>/...          brutos do presidente nas OUTRAS UFs: ficam fora de raw/,
                                              ultimo/totais, das séries e do histórico, que são da UF
  historico_totais.parquet
  historico_serie.parquet   % dos válidos por candidato/partido a cada totalização (UF e Brasil)
  historico_candidatos/     um bloco Parquet por ciclo: candidato × município/UF/BR a cada totalização
  status.json
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import requests

from apuracao.divulgacao import modelo as m
from apuracao.divulgacao import serie
from apuracao.divulgacao.cliente import BloqueioTSE, ClienteDivulgacao, DivulgacaoIndisponivel, Resposta

logger = logging.getLogger("apuracao.divulgacao")

CARGOS_ESTADUAIS = (3, 5, 6, 7)  # governador, senador, dep. federal, dep. estadual
CARGOS_2_TURNO = (3,)            # no 2º turno estadual só há governador (pedir os demais daria 404)
CARGO_DISTRITAL = 8               # só para o DF
CARGO_PRESIDENTE = 1
PAUSA_BLOQUEIO_S = 660            # bloqueio do TSE dura 10 min e reinicia a cada tentativa
TENTATIVAS_404 = 3                # EA20 com 404 é pedido de novo em até 3 ciclos (vários 404 bloqueiam o IP)
DOWNLOADS_SIMULTANEOS = 8         # a taxa continua limitada pelo LimitadorTaxa do cliente


@dataclass(frozen=True)
class Alvo:
    eleicao: int
    cargo: int
    uf: str                 # "br" para o arquivo nacional
    municipio: int | None = None


@dataclass
class ResumoCiclo:
    inicio: datetime
    fim: datetime | None = None
    arquivos_pedidos: int = 0
    arquivos_novos: int = 0
    arquivos_304: int = 0
    arquivos_404: int = 0
    arquivos_com_falha: int = 0   # rede, 5xx ou JSON que não se lê: pedidos de novo no ciclo seguinte
    abrangencias_alteradas: int = 0
    erro: str | None = None
    estatisticas: dict[str, int] = field(default_factory=dict)


class Coletor:
    def __init__(self, cliente: ClienteDivulgacao, destino: Path, uf: str = "RJ", turno: int = 1,
                 presidente_br: bool = True, downloads_simultaneos: int = DOWNLOADS_SIMULTANEOS,
                 presidente_ufs: bool = True) -> None:
        self.cliente = cliente
        self.downloads_simultaneos = downloads_simultaneos
        self.destino = destino
        self.uf = uf.lower()
        self.turno = turno
        self.presidente_br = presidente_br
        self.presidente_ufs = presidente_ufs and presidente_br  # as linhas por UF vêm do mesmo EA14
        self.cfg: m.ConfigEleicoes | None = None
        self.municipios = pl.DataFrame(schema=m.MUNICIPIOS_SCHEMA)
        self._eleicoes: dict[int, tuple[int, ...]] = {}          # eleição -> cargos coletados
        self._federal: int | None = None                           # eleição do presidente
        self._ultima_totalizacao: dict[tuple, datetime | None] = {}
        self._tentativas_404: dict[tuple, int] = {}
        self._resultados: dict[str, m.Resultado] = {}
        self._resultados_brasil: dict[str, m.Resultado] = {}     # presidente nas outras UFs
        self._acompanhamento: dict[str, pl.DataFrame] = {}
        self.ultimo_resumo: ResumoCiclo | None = None

    # ------------------------------------------------------------ preparação
    def preparar(self) -> None:
        """EA11 (eleições e cargos) e EA12 (municípios da UF)."""
        if (self.destino / "raw").exists():  # dados coletados antes de as séries existirem
            if not (self.destino / serie.ARQUIVO).exists():
                serie.reconstruir(self.destino)
            if not (self.destino / serie.CANDIDATOS_DIR).exists():
                serie.reconstruir_candidatos(self.destino)
        resp = self.cliente.get_json(self.cliente.caminho_config())
        if resp is None:
            raise DivulgacaoIndisponivel(
                f"divulgação ainda não disponível no ambiente {self.cliente.ambiente}: "
                f"{self.cliente.url(self.cliente.caminho_config())} respondeu 404 (o TSE carrega os "
                "parâmetros oficiais na véspera do pleito)")
        self.cfg = m.parse_config(resp.dados)
        self._eleicoes.clear()
        estadual = self.cfg.por_cargo(3, self.turno)
        if estadual is not None:
            cargos = CARGOS_2_TURNO if self.turno == 2 else (
                CARGOS_ESTADUAIS + ((CARGO_DISTRITAL,) if self.uf == "df" else ()))
            self._eleicoes[estadual.codigo] = tuple(c for c in cargos if estadual.cargo(c))
        federal = self.cfg.por_cargo(CARGO_PRESIDENTE, self.turno)
        self._federal = federal.codigo if federal is not None else None
        if federal is not None:
            self._eleicoes[federal.codigo] = (CARGO_PRESIDENTE,)
        if not self._eleicoes:
            raise DivulgacaoIndisponivel(f"nenhuma eleição do {self.turno}º turno no ele-c.json")
        base = estadual or federal
        assert base is not None
        mun = self.cliente.get_json(self.cliente.caminho_municipios(self.cfg, base.codigo))
        if mun is not None:
            self.municipios = m.parse_municipios(mun.dados).filter(pl.col("UF") == self.uf.upper())
        logger.info("ciclo %s, eleições %s, %d municípios de %s", self.cfg.ciclo,
                    {e: c for e, c in self._eleicoes.items()}, self.municipios.height, self.uf.upper())

    # ------------------------------------------------------------ ciclo
    def ciclo(self) -> ResumoCiclo:
        if self.cfg is None:
            self.preparar()
        assert self.cfg is not None
        resumo = ResumoCiclo(inicio=datetime.now(timezone.utc))
        self.cliente.novo_ciclo()
        antes = dict(self.cliente.estatisticas)
        alvos: list[Alvo] = []
        pendentes: dict[tuple, tuple[datetime | None, list[Alvo]]] = {}
        for eleicao, cargos in self._eleicoes.items():
            alterados = self._abrangencias_alteradas(eleicao)
            resumo.abrangencias_alteradas += len(alterados)
            for chave, dt, (uf, mun) in alterados:
                meus = [Alvo(eleicao, c, uf, mun) for c in cargos if uf != "br" or c == CARGO_PRESIDENTE]
                pendentes[chave] = (dt, meus)
                alvos += meus
        cfg = self.cfg
        caminhos = [(a, self.cliente.caminho_resultado(cfg, a.eleicao, a.uf, a.cargo, a.municipio)) for a in alvos]
        with ThreadPoolExecutor(max_workers=self.downloads_simultaneos) as pool:
            respostas = list(pool.map(lambda ac: self._baixar(ac[1]), caminhos))
        novos: list[m.Resultado] = []
        faltou: dict[Alvo, str] = {}  # alvo -> "404" ou "falha"
        for (alvo, caminho), resp in zip(caminhos, respostas):
            resumo.arquivos_pedidos += 1
            if isinstance(resp, Exception):
                resumo.arquivos_com_falha += 1
                faltou[alvo] = "falha"
                continue
            if resp is None:
                resumo.arquivos_404 += 1
                faltou[alvo] = "404"
                continue
            outra_uf = alvo.uf not in (self.uf, "br")
            guardados = self._resultados_brasil if outra_uf else self._resultados
            if not resp.mudou and caminho in guardados:
                resumo.arquivos_304 += 1
                continue
            # 304 de um arquivo que o coletor não guardou (o ciclo em que ele veio foi interrompido): usa o do cache
            resumo.arquivos_novos += 1
            try:
                resultado = m.parse_resultado(resp.dados, alvo.uf if alvo.uf != "br" else "br")
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                logger.error("%s: JSON com estrutura inesperada (%r); nova tentativa no próximo ciclo", caminho, exc)
                resumo.arquivos_com_falha += 1
                faltou[alvo] = "falha"
                continue
            self._guardar_bruto(alvo.eleicao, caminho, resp.dados, "raw_brasil" if outra_uf else "raw")
            guardados[caminho] = resultado
            if not outra_uf:  # série e histórico são da UF (e do Brasil)
                novos.append(resultado)
        self._confirmar(pendentes, faltou)
        self._gravar_estado(resumo)
        serie.gravar_bloco(self.destino, serie.linhas_candidatos(novos), f"{resumo.inicio:%Y%m%dT%H%M%S%f}")
        resumo.fim = datetime.now(timezone.utc)
        resumo.estatisticas = {k: v - antes.get(k, 0) for k, v in self.cliente.estatisticas.items()}
        self._gravar_status(resumo)
        self.ultimo_resumo = resumo
        return resumo

    def _baixar(self, caminho: str) -> Resposta | None | Exception:
        """get_json de um EA20; falha de rede, 5xx ou conteúdo que não é JSON volta como valor e não
        derruba o ciclo (a divulgação fora do ar já aparece no acompanhamento, lido antes). Bloqueio
        (403/429) interrompe o ciclo inteiro: insistir reinicia o bloqueio."""
        try:
            return self.cliente.get_json(caminho)
        except BloqueioTSE:
            raise
        except (requests.RequestException, DivulgacaoIndisponivel) as exc:
            logger.warning("%s: %s; nova tentativa no próximo ciclo", caminho, exc)
            return exc

    def _confirmar(self, pendentes: dict[tuple, tuple[datetime | None, list[Alvo]]], faltou: dict[Alvo, str]) -> None:
        """Dá por vista a totalização de cada abrangência cujos arquivos chegaram. Com falha (rede, 5xx,
        JSON ilegível), ela é pedida de novo no ciclo seguinte; com 404, no máximo `TENTATIVAS_404` vezes."""
        for chave, (dt, alvos) in pendentes.items():
            motivos = {faltou[a] for a in alvos if a in faltou}
            if "falha" in motivos:
                continue
            if motivos:  # só 404
                n = self._tentativas_404.get(chave, 0) + 1
                if n < TENTATIVAS_404:
                    self._tentativas_404[chave] = n
                    continue
                logger.warning("abrangência %s: 404 em %d ciclos seguidos; só volta na próxima totalização", chave, n)
            self._ultima_totalizacao[chave] = dt
            self._tentativas_404.pop(chave, None)

    def _abrangencias_alteradas(self, eleicao: int) -> list[tuple[tuple, datetime | None, tuple[str, int | None]]]:
        """(chave, dt/ht novo, (uf, município)) de cada abrangência cujo dt/ht mudou desde a última
        totalização confirmada, segundo EA15/EA14. Nada é confirmado aqui: ver `_confirmar`."""
        assert self.cfg is not None
        tabelas = []
        ufs = [self.uf] + (["br"] if eleicao == self._federal and self.presidente_br else [])
        for uf in ufs:
            resp = self.cliente.get_json(self.cliente.caminho_acompanhamento(self.cfg, eleicao, uf))
            if resp is None:
                logger.warning("acompanhamento %s da eleição %s indisponível (404)", uf, eleicao)
                continue
            if resp.mudou:
                self._guardar_bruto(eleicao, resp.caminho, resp.dados)
            ab = m.parse_acompanhamento(resp.dados, uf)
            if uf == "br":  # do EA14: a linha nacional e, para o presidente por UF, as das OUTRAS UFs
                outras = ab.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") != self.uf.upper()))
                ab = ab.filter(pl.col("ABRANGENCIA") == "br")
                if self.presidente_ufs:
                    tabelas.append(outras)
            tabelas.append(ab)
            self._acompanhamento[f"{eleicao}-{uf}"] = ab
        alterados = []
        for tab in tabelas:
            for row in tab.iter_rows(named=True):
                chave = (eleicao, row["ABRANGENCIA"], row["UF"], row["CD_MUNICIPIO"])
                if chave not in self._ultima_totalizacao or self._ultima_totalizacao[chave] != row["DT_TOTALIZACAO"]:
                    uf = ("br" if row["ABRANGENCIA"] == "br" else self.uf if row["UF"] == self.uf.upper()
                          else row["UF"].lower())
                    alterados.append((chave, row["DT_TOTALIZACAO"], (uf, row["CD_MUNICIPIO"])))
        return alterados

    # ------------------------------------------------------------ persistência
    def _guardar_bruto(self, eleicao: int, caminho: str, dados: dict[str, Any], raiz: str = "raw") -> None:
        """Guarda cada VERSÃO distinta do arquivo. O nome leva a geração (dg/hg), o idg e um hash
        do conteúdo: só o carimbo do TSE não basta para distinguir versões."""
        nome = caminho.rsplit("/", 1)[-1].removesuffix(".json")
        texto = json.dumps(dados, ensure_ascii=False, sort_keys=True)
        stamp = m.to_datetime(dados.get("dg"), dados.get("hg"))
        tag = f"{stamp:%Y%m%d_%H%M%S}" if stamp else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_coleta")
        digest = hashlib.sha1(texto.encode()).hexdigest()[:10]
        alvo = self.destino / raiz / str(eleicao) / nome / f"{tag}_{dados.get('idg', 'sem-idg')}_{digest}.json.gz"
        if alvo.exists():
            return
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            fh.write(texto)
        tmp.replace(alvo)

    def _gravar_estado(self, resumo: ResumoCiclo) -> None:
        ultimo = self.destino / "ultimo"
        ultimo.mkdir(parents=True, exist_ok=True)
        coletado = pl.lit(resumo.inicio.replace(tzinfo=None)).alias("COLETADO_EM")
        res = list(self._resultados.values())
        tabelas = {
            "totais": pl.concat([r.totais for r in res]) if res else pl.DataFrame(schema=m.TOTAIS_SCHEMA),
            "candidatos": pl.concat([r.candidatos for r in res]) if res else pl.DataFrame(schema=m.CANDIDATOS_SCHEMA),
            "partidos": pl.concat([r.partidos for r in res]) if res else pl.DataFrame(schema=m.PARTIDOS_SCHEMA),
            "municipios": self.municipios,
            "acompanhamento": (pl.concat(list(self._acompanhamento.values())) if self._acompanhamento
                               else pl.DataFrame(schema=m.ACOMPANHAMENTO_SCHEMA)),
        }
        # presidente por UF: as outras UFs + a própria (já coletada pelo EA15, não é pedida de novo)
        brasil = [r for r in res if r.totais.filter((pl.col("CARGO") == CARGO_PRESIDENTE)
                                                    & (pl.col("ABRANGENCIA") == "uf")).height]
        brasil += list(self._resultados_brasil.values())
        tabelas["brasil_totais"] = (pl.concat([r.totais for r in brasil]) if brasil
                                    else pl.DataFrame(schema=m.TOTAIS_SCHEMA))
        tabelas["brasil_candidatos"] = (pl.concat([r.candidatos for r in brasil]) if brasil
                                        else pl.DataFrame(schema=m.CANDIDATOS_SCHEMA))
        for nome, df in tabelas.items():
            _write_atomic(df, ultimo / f"{nome}.parquet")
        if resumo.arquivos_novos:
            novos = tabelas["totais"].with_columns(coletado)
            hist_path = self.destino / "historico_totais.parquet"
            if hist_path.exists():
                novos = pl.concat([pl.read_parquet(hist_path), novos], how="diagonal_relaxed").unique(
                    subset=["ELEICAO", "CARGO", "ABRANGENCIA", "UF", "CD_MUNICIPIO", "DT_TOTALIZACAO"],
                    keep="first", maintain_order=True)
            _write_atomic(novos, hist_path)
            serie.acrescentar(self.destino / serie.ARQUIVO,
                              serie.linhas(tabelas["totais"], tabelas["candidatos"], tabelas["partidos"]))

    def _gravar_status(self, resumo: ResumoCiclo, erro: str | None = None, tipo_erro: str | None = None) -> None:
        status = {
            "ambiente": self.cliente.ambiente, "uf": self.uf.upper(), "turno": self.turno,
            "ciclo_tse": self.cfg.ciclo if self.cfg else None,
            "eleicoes": {str(e): list(c) for e, c in self._eleicoes.items()},
            "ultimo_ciclo_inicio": resumo.inicio.isoformat(timespec="seconds"),
            "ultimo_ciclo_fim": resumo.fim.isoformat(timespec="seconds") if resumo.fim else None,
            "arquivos_novos": resumo.arquivos_novos, "arquivos_304": resumo.arquivos_304,
            "arquivos_404": resumo.arquivos_404, "arquivos_com_falha": resumo.arquivos_com_falha,
            "abrangencias_alteradas": resumo.abrangencias_alteradas,
            "estatisticas": resumo.estatisticas, "erro": erro or resumo.erro,
            # bloqueio | indisponivel | rede | inesperado (os alertas do site dependem do tipo)
            "tipo_erro": tipo_erro if (erro or resumo.erro) else None,
            "pausa_s": PAUSA_BLOQUEIO_S if tipo_erro == "bloqueio" else None,
            "base_url": self.cliente.url(""),
        }
        self.destino.mkdir(parents=True, exist_ok=True)
        tmp = self.destino / "status.json.tmp"
        tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False))
        tmp.replace(self.destino / "status.json")

    # ------------------------------------------------------------ laço
    def executar(self, intervalo: float = 60.0, parar: threading.Event | None = None,
                 max_ciclos: int | None = None) -> None:
        """Roda ciclos até `parar` ser acionado ou `max_ciclos` ser atingido."""
        parar = parar or threading.Event()
        n = 0
        while not parar.is_set() and (max_ciclos is None or n < max_ciclos):
            n += 1
            espera = intervalo
            try:
                r = self.ciclo()
                logger.info("ciclo %d: %d abrangências alteradas, %d arquivos novos, %d 304, %d 404, %d com falha (%.1fs)",
                            n, r.abrangencias_alteradas, r.arquivos_novos, r.arquivos_304, r.arquivos_404,
                            r.arquivos_com_falha,
                            (r.fim - r.inicio).total_seconds() if r.fim else 0)
            except DivulgacaoIndisponivel as exc:
                logger.warning("%s — nova tentativa em %.0fs", exc, max(intervalo, 300))
                self._registrar_erro(str(exc), "indisponivel")
                self.cfg = None  # recarrega o ele-c.json quando o ambiente entrar no ar
                espera = max(intervalo, 300)
            except BloqueioTSE as exc:
                logger.error("%s — pausa de %ds", exc, PAUSA_BLOQUEIO_S)
                self._registrar_erro(str(exc), "bloqueio")
                espera = PAUSA_BLOQUEIO_S
            except requests.RequestException as exc:
                logger.error("falha de rede: %s", exc)
                self._registrar_erro(f"falha de rede: {exc}", "rede")
            except Exception as exc:  # noqa: BLE001 — a coleta não pode parar na noite da eleição por um defeito
                logger.exception("erro inesperado no ciclo %d; nova tentativa em %.0fs", n, intervalo)
                self._registrar_erro(f"erro inesperado: {exc!r}", "inesperado")
            if max_ciclos is not None and n >= max_ciclos:
                break
            parar.wait(espera)

    def _registrar_erro(self, msg: str, tipo: str) -> None:
        resumo = ResumoCiclo(inicio=datetime.now(timezone.utc), erro=msg)
        resumo.fim = resumo.inicio
        self._gravar_status(resumo, erro=msg, tipo_erro=tipo)


def tipo_do_erro(exc: BaseException) -> str:
    """Rótulo gravado em `status.json` (`tipo_erro`), que os alertas do site leem."""
    if isinstance(exc, BloqueioTSE):
        return "bloqueio"
    if isinstance(exc, DivulgacaoIndisponivel):
        return "indisponivel"
    if isinstance(exc, requests.RequestException):
        return "rede"
    return "inesperado"


def _write_atomic(df: pl.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp)
    tmp.replace(path)


def destino_padrao(ambiente: str, raiz: Path = Path("dados_2026"), turno: int = 1) -> Path:
    """dados_2026/<ambiente> no 1º turno e dados_2026/<ambiente>_t2 no 2º: os turnos não se misturam
    (último estado, séries e JSON brutos de cada noite ficam separados)."""
    return raiz / (ambiente if turno == 1 else f"{ambiente}_t{turno}")
