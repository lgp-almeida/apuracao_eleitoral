"""Cliente HTTP da divulgação de resultados do TSE, respeitando as regras de acesso.

Regras (Informações técnicas 2026; Anexo I, bloco A6):
  * até 100 requisições/s por IP; acima disso, bloqueio de 10 min (reiniciado a cada
    tentativa durante o bloqueio). Aqui o padrão é 20 req/s;
  * respostas 304 também contam no limite;
  * vários 404 podem bloquear o IP: cada URL com 404 é memorizada e não é pedida de novo
    no mesmo ciclo;
  * antes da divulgação o ambiente oficial responde 200 com uma PÁGINA HTML — isso vira
    `DivulgacaoIndisponivel`, não um erro de parse.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from apuracao.divulgacao.modelo import ConfigEleicoes

logger = logging.getLogger("apuracao.divulgacao")

AMBIENTES = {
    "oficial": ("https://resultados.tse.jus.br", "oficial"),
    "simulado": ("https://resultados-sim.tse.jus.br/simulado", "simulado2026"),
}
USER_AGENT = "estudo-eleitoral-python/1.0 (apuracao 2026; coleta local)"
CONFIG_PATH = "comum/config/ele-c.json"
# esquema do Anexo I, usado se o ele-c.json não trouxer os modelos de diretório
DEFAULT_DIRS = {
    "cm": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/config",
    "ab": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>",
    "u": "<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>",
}


class DivulgacaoIndisponivel(RuntimeError):
    """O endereço respondeu, mas não com JSON (ex.: página "nova versão em breve")."""


class BloqueioTSE(RuntimeError):
    """403/429: o TSE limitou o IP. É preciso esperar antes de tentar de novo."""


@dataclass
class Resposta:
    caminho: str
    dados: dict[str, Any]
    etag: str | None
    mudou: bool  # False quando veio 304 (conteúdo reaproveitado do cache em memória)


class LimitadorTaxa:
    """Intervalo mínimo entre requisições, compartilhado entre threads."""

    def __init__(self, max_rps: float, relogio: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], None] = time.sleep) -> None:
        self.intervalo = 1.0 / max_rps
        self._relogio, self._dormir = relogio, dormir
        self._ultimo = -float("inf")
        self._lock = threading.Lock()

    def aguardar(self) -> None:
        with self._lock:
            espera = self.intervalo - (self._relogio() - self._ultimo)
            if espera > 0:
                self._dormir(espera)
            self._ultimo = self._relogio()


class ClienteDivulgacao:
    def __init__(self, ambiente: str = "simulado", sessao: requests.Session | None = None, max_rps: float = 20.0,
                 timeout: float = 30.0, limitador: LimitadorTaxa | None = None) -> None:
        if ambiente not in AMBIENTES:
            raise ValueError(f"ambiente deve ser um de {sorted(AMBIENTES)}")
        self.ambiente = ambiente
        self.base, self.nome_ambiente = AMBIENTES[ambiente]
        self.sessao = sessao or requests.Session()
        self.sessao.headers.setdefault("User-Agent", USER_AGENT)
        self.timeout = timeout
        self.limitador = limitador or LimitadorTaxa(max_rps)
        self._cache: dict[str, tuple[str | None, dict[str, Any]]] = {}
        self._nao_encontrados: set[str] = set()
        self.estatisticas: Counter[str] = Counter()
        self._lock = threading.Lock()  # get_json é chamado por várias threads do coletor

    # ---------------------------------------------------------------- HTTP
    def url(self, caminho: str) -> str:
        return f"{self.base}/{self.nome_ambiente}/{caminho}"

    def novo_ciclo(self) -> None:
        """Esquece os 404 do ciclo anterior (um arquivo pode passar a existir)."""
        with self._lock:
            self._nao_encontrados.clear()

    def _contar(self, chave: str) -> None:
        with self._lock:
            self.estatisticas[chave] += 1

    def get_json(self, caminho: str) -> Resposta | None:
        """JSON do caminho; None se 404. Usa ETag para não baixar de novo o que não mudou."""
        with self._lock:
            if caminho in self._nao_encontrados:
                self.estatisticas["404_evitado"] += 1
                return None
            cached = self._cache.get(caminho)
        headers = {"If-None-Match": cached[0]} if cached and cached[0] else {}
        self.limitador.aguardar()
        self._contar("requisicoes")
        resp = self.sessao.get(self.url(caminho), headers=headers, timeout=self.timeout)
        self._contar(str(resp.status_code))
        if resp.status_code == 304 and cached:
            return Resposta(caminho, cached[1], cached[0], mudou=False)
        if resp.status_code == 404:
            with self._lock:
                self._nao_encontrados.add(caminho)
            return None
        if resp.status_code in (403, 429):
            raise BloqueioTSE(f"HTTP {resp.status_code} em {caminho}: provável limite de acesso do TSE")
        resp.raise_for_status()
        dados = self._json_ou_indisponivel(resp, caminho)
        etag = resp.headers.get("ETag")
        with self._lock:
            self._cache[caminho] = (etag, dados)
        return Resposta(caminho, dados, etag, mudou=True)

    @staticmethod
    def _json_ou_indisponivel(resp: requests.Response, caminho: str) -> dict[str, Any]:
        ctype = resp.headers.get("Content-Type", "")
        texto = resp.text.lstrip()
        if "json" not in ctype and not texto.startswith(("{", "[")):
            raise DivulgacaoIndisponivel(
                f"{caminho}: o TSE respondeu {ctype or 'sem Content-Type'} em vez de JSON "
                "(divulgação ainda não disponível neste ambiente)"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise DivulgacaoIndisponivel(f"{caminho}: JSON inválido ({exc})") from exc

    # ---------------------------------------------------------------- caminhos
    @staticmethod
    def caminho_config() -> str:
        return CONFIG_PATH

    @staticmethod
    def _dir(cfg: ConfigEleicoes, tipo: str, eleicao: int, uf: str = "") -> str:
        modelo = cfg.diretorios.get(tipo) or DEFAULT_DIRS[tipo]
        return (modelo.replace("<base>/<ambiente>/", "").replace("<ciclo>", cfg.ciclo)
                .replace("<cd_eleicao>", str(eleicao)).replace("<uf>", uf.lower()))

    def caminho_municipios(self, cfg: ConfigEleicoes, eleicao: int) -> str:
        return f"{self._dir(cfg, 'cm', eleicao)}/mun-e{eleicao:06d}-cm.json"

    def caminho_acompanhamento(self, cfg: ConfigEleicoes, eleicao: int, uf: str) -> str:
        uf = uf.lower()
        return f"{self._dir(cfg, 'ab', eleicao, uf)}/{uf}-e{eleicao:06d}-ab.json"

    def caminho_resultado(self, cfg: ConfigEleicoes, eleicao: int, uf: str, cargo: int,
                          municipio: int | None = None) -> str:
        uf = uf.lower()
        abr = uf if municipio is None else f"{uf}{municipio:05d}"
        return f"{self._dir(cfg, 'u', eleicao, uf)}/{abr}-c{cargo:04d}-e{eleicao:06d}-u.json"
