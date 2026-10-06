"""Baixar e preparar os dados de várias UFs de uma vez (rodada 39) — o motor de `baixar_ufs.py`.

Etapas (cada uma idempotente: o que já está completo é pulado, a menos que `refazer`):
  divulgacao  resultado 2026 da divulgação do TSE (o mesmo `Coletor` da noite), uma UF depois da outra com UM
              limitador de acessos para todas (vários processos somariam 20 req/s cada no mesmo IP)
  historico   resultado oficial de anos anteriores (`historico.importar`; sem o votacao_secao da UF no cache,
              pela fonte "munzona", que serve às 27 UFs com um arquivo nacional por ano)
  eleitorado  cadastro de eleitorado (seções → locais) e perfil do eleitorado por seção
  ibge        malhas e Censo 2022 da UF (`ibge.preparar`)
  microdados  votação por seção de 2026, quando o TSE publicar (`microdados.preparar`); antes disso, "aguardando"

O estado de cada UF × etapa fica em `<raiz>/lote_ufs.json`: uma falha numa UF não para as outras, e rodar de
novo retoma do que faltou. Bloqueio do TSE interrompe só a etapa da divulgação (as outras usam a CDN).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao.divulgacao.cliente import BloqueioTSE, ClienteDivulgacao, DivulgacaoIndisponivel, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor, destino_padrao
from apuracao.ufs import dir_uf

logger = logging.getLogger("apuracao.lote_ufs")

ETAPAS = ("divulgacao", "historico", "eleitorado", "ibge", "microdados")
OK, ERRO, AGUARDANDO, INCOMPLETO, NAO_SE_APLICA, PENDENTE = (
    "ok", "erro", "aguardando", "incompleto", "não se aplica", "pendente")
ARQUIVO_ESTADO = "lote_ufs.json"


@dataclass
class Config:
    ufs: list[str]
    etapas: tuple[str, ...] = ETAPAS
    anos: tuple[int, ...] = (2022,)                 # histórico
    turnos: tuple[int, ...] = (1,)
    anos_eleitorado: tuple[int, ...] = (2022, 2026)
    ambiente: str = "oficial"
    raiz: Path = Path("dados_2026")
    cache: Path = Path("cache_tse")
    max_rps: float = 10.0
    max_ciclos: int = 3        # divulgação: ciclos por UF para buscar o que deu 404 ou veio na versão anterior
    pausa_ciclos: float = 2.0
    refazer: bool = False


@dataclass
class Resultado:
    situacao: str
    detalhe: str = ""
    segundos: float = 0.0


@dataclass
class Lote:
    """Executa as etapas. `sessao` (requests) e `relogio` são injetáveis para os testes."""

    cfg: Config
    sessao: Any = None
    relogio: Callable[[], float] = time.monotonic
    limitador: LimitadorTaxa = field(init=False)
    estado: dict[str, dict[str, dict[str, Any]]] = field(init=False)
    _bloqueado: str | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.limitador = LimitadorTaxa(self.cfg.max_rps)  # UM para todas as UFs
        self.estado = carregar_estado(self.cfg.raiz)

    # ------------------------------------------------------------ plano
    def tarefas(self) -> list[tuple[str, str, Callable[[], Resultado]]]:
        """(chave da etapa, UF, função) na ordem de execução: uma etapa para todas as UFs, depois a próxima."""
        c = self.cfg
        out: list[tuple[str, str, Callable[[], Resultado]]] = []
        for etapa in c.etapas:
            for uf in c.ufs:
                if etapa == "divulgacao":
                    out += [(f"divulgacao_t{t}", uf, lambda uf=uf, t=t: self.divulgacao(uf, t)) for t in c.turnos]
                elif etapa == "historico":
                    out += [(f"historico_{a}_t{t}", uf, lambda uf=uf, a=a, t=t: self.historico(uf, a, t))
                            for a in c.anos for t in c.turnos]
                elif etapa == "eleitorado":
                    out += [(f"eleitorado_{a}", uf, lambda uf=uf, a=a: self.eleitorado(uf, a)) for a in c.anos_eleitorado]
                    out += [(f"perfil_{a}", uf, lambda uf=uf, a=a: self.perfil(uf, a)) for a in c.anos_eleitorado]
                elif etapa == "ibge":
                    out.append(("ibge", uf, lambda uf=uf: self.ibge(uf)))
                elif etapa == "microdados":
                    out.append(("microdados_2026", uf, lambda uf=uf: self.microdados(uf)))
                else:
                    raise ValueError(f"etapa desconhecida: {etapa} (use {', '.join(ETAPAS)})")
        return out

    def ja_feita(self, chave: str, uf: str) -> bool:
        return not self.cfg.refazer and self.estado.get(uf, {}).get(chave, {}).get("situacao") in (OK, NAO_SE_APLICA)

    def executar(self, ao_terminar: Callable[[str, str, Resultado], None] | None = None) -> dict:
        for chave, uf, fazer in self.tarefas():
            if self.ja_feita(chave, uf):
                continue
            if chave.startswith("divulgacao") and self._bloqueado:
                r = Resultado(PENDENTE, f"TSE bloqueou os acessos ({self._bloqueado}); rode de novo mais tarde")
            else:
                t0 = self.relogio()
                try:
                    r = fazer()
                except Exception as exc:  # noqa: BLE001 — uma UF com defeito não pode parar as outras 26
                    logger.exception("%s %s: erro inesperado", uf, chave)
                    r = Resultado(ERRO, f"erro inesperado: {exc!r}")
                r.segundos = self.relogio() - t0
            self.registrar(uf, chave, r)
            if ao_terminar:
                ao_terminar(chave, uf, r)
        return self.estado

    def registrar(self, uf: str, chave: str, r: Resultado) -> None:
        self.estado.setdefault(uf, {})[chave] = {
            "situacao": r.situacao, "detalhe": r.detalhe, "segundos": round(r.segundos, 1),
            "em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        gravar_estado(self.cfg.raiz, self.estado)

    # ------------------------------------------------------------ etapas
    def divulgacao(self, uf: str, turno: int) -> Resultado:
        destino = dir_uf(destino_padrao(self.cfg.ambiente, self.cfg.raiz, turno), uf)
        if not self.cfg.refazer and divulgacao_completa(destino):
            return Resultado(OK, f"já completa em {destino}")
        cliente = ClienteDivulgacao(self.cfg.ambiente, sessao=self.sessao, limitador=self.limitador)
        coletor = Coletor(cliente, destino, uf, turno, presidente_ufs=False)  # o presidente da UF vem no EA20 dela
        novos = 0
        try:
            for i in range(1, self.cfg.max_ciclos + 1):
                r = coletor.ciclo()
                novos += r.arquivos_novos
                limpo = r.arquivos_com_falha == 0 and r.arquivos_antigos == 0
                if limpo and divulgacao_completa(destino):
                    return Resultado(OK, f"{i} ciclo(s), {novos} arquivos novos → {destino}")
                if i < self.cfg.max_ciclos:
                    time.sleep(self.cfg.pausa_ciclos)
        except DivulgacaoIndisponivel as exc:
            return Resultado(AGUARDANDO, str(exc))
        except BloqueioTSE as exc:
            self._bloqueado = str(exc)
            return Resultado(PENDENTE, f"TSE bloqueou os acessos: {exc}")
        except requests.RequestException as exc:
            return Resultado(ERRO, f"rede: {exc}")
        pend = f"{r.arquivos_com_falha} com falha, {r.arquivos_antigos} na versão anterior"
        situacao = OK if divulgacao_completa(destino) else INCOMPLETO
        return Resultado(situacao, f"{self.cfg.max_ciclos} ciclos, {novos} arquivos novos; {pend} → {destino}")

    def historico(self, uf: str, ano: int, turno: int) -> Resultado:
        from apuracao import historico as h

        destino = dir_uf(self.cfg.raiz / f"historico_{ano}_t{turno}", uf)
        st = _status(destino)
        if not self.cfg.refazer and st.get("ano") == ano and (destino / "ultimo" / "totais.parquet").exists():
            return Resultado(OK, f"já importado em {destino}")
        try:
            n = h.importar(ano, uf, turno, self.cfg.cache, destino)
        except v.TseDataError as exc:
            if turno == 2 and "sem totais" in str(exc):
                return Resultado(NAO_SE_APLICA, f"sem 2º turno em {ano}")
            return Resultado(ERRO, str(exc))
        except requests.RequestException as exc:
            return Resultado(ERRO, f"rede: {exc}")
        fonte = "secao" if any(f.startswith("votacao_secao") for f in _status(destino).get("fontes", [])) else "munzona"
        return Resultado(OK, f"{n['candidatos']} linhas de candidatos, {n['municipios']} municípios "
                             f"(fonte {fonte}) → {destino}")

    def eleitorado(self, uf: str, ano: int) -> Resultado:
        from apuracao import eleitorado as el

        try:
            secoes = el.load_sections(ano, uf, self.cfg.cache)
        except (v.TseDataError, requests.RequestException, OSError) as exc:
            return _indisponivel(exc)
        return Resultado(OK, f"{secoes.height:,} seções".replace(",", "."))

    def perfil(self, uf: str, ano: int) -> Resultado:
        from apuracao import perfil as pf

        try:
            n = pf.load_perfil(ano, uf, self.cfg.cache).select(pl.len()).collect().item()
        except (v.TseDataError, requests.RequestException, OSError) as exc:
            return _indisponivel(exc)
        return Resultado(OK, f"{n:,} linhas".replace(",", "."))

    def ibge(self, uf: str) -> Resultado:
        from apuracao import ibge

        falhas = ibge.preparar(self.cfg.cache, uf, self.sessao or requests)
        return Resultado(ERRO, "; ".join(falhas)) if falhas else Resultado(OK, "malhas e Censo no cache")

    def microdados(self, uf: str, ano: int = 2026) -> Resultado:
        import argparse

        import preparar_2026 as p26
        from apuracao import microdados as md

        args = argparse.Namespace(ano=ano, uf=uf, cache_dir=self.cfg.cache, raiz=self.cfg.raiz,
                                  saidas=Path("saidas") / uf)
        try:
            estados = md.preparar(self.cfg.cache, ano, uf, self.sessao or requests, ao_chegar=p26.ao_chegar(args, set()))
        except requests.RequestException as exc:
            return Resultado(ERRO, f"rede: {exc}")
        com = md.com_dados(estados)
        if {"votos_uf", "votos_br", "detalhe_secao"} <= com:
            return Resultado(OK, f"publicados e preparados: {', '.join(sorted(com))}")
        return Resultado(AGUARDANDO, f"TSE ainda não publicou ({', '.join(sorted(com)) or 'nada'} com dados)")


# --------------------------------------------------------------------------
# Apoio
# --------------------------------------------------------------------------
def divulgacao_completa(destino: Path) -> bool:
    """Todos os cargos da UF com totalização final e o último ciclo sem erro."""
    arq = destino / "ultimo" / "totais.parquet"
    if not arq.exists() or _status(destino).get("erro"):
        return False
    uf = pl.read_parquet(arq).filter(pl.col("ABRANGENCIA") == "uf")
    return uf.height > 0 and bool(uf["TOTALIZACAO_FINAL"].fill_null(False).all())


def _indisponivel(exc: BaseException) -> Resultado:
    texto = str(exc)
    if "404" in texto or "Not Found" in texto:
        return Resultado(AGUARDANDO, f"ainda não publicado pelo TSE: {texto}")
    return Resultado(ERRO, texto)


def _status(pasta: Path) -> dict[str, Any]:
    try:
        return json.loads((pasta / "status.json").read_text())
    except (OSError, ValueError):
        return {}


def carregar_estado(raiz: Path) -> dict[str, dict[str, dict[str, Any]]]:
    try:
        return json.loads((raiz / ARQUIVO_ESTADO).read_text())
    except (OSError, ValueError):
        return {}


def gravar_estado(raiz: Path, estado: dict) -> None:
    raiz.mkdir(parents=True, exist_ok=True)
    tmp = raiz / f"{ARQUIVO_ESTADO}.tmp"
    tmp.write_text(json.dumps(estado, indent=2, ensure_ascii=False, sort_keys=True))
    tmp.replace(raiz / ARQUIVO_ESTADO)


def resumo(estado: dict, ufs: list[str]) -> pl.DataFrame:
    """Uma linha por UF, uma coluna por etapa, com a situação."""
    chaves = sorted({k for uf in ufs for k in estado.get(uf, {})})
    return pl.DataFrame([{"UF": uf, **{k: estado.get(uf, {}).get(k, {}).get("situacao", "—") for k in chaves}}
                         for uf in ufs])
