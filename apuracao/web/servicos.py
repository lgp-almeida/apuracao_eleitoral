"""Boletim, cópia de segurança e alertas de CADA UF no site de várias UFs (rodada 43, TODO 18).

No site de uma UF, cada serviço tem a sua thread (`site_apuracao.py`). Com `--ufs`, o mesmo trabalho é feito
para todas as UFs montadas por UMA thread que percorre as UFs: os alertas a cada passo (15 s), o boletim a cada
30 s e a cópia a cada 60 s — os próprios objetos decidem se há algo a fazer (hora cheia, espelho de 5 min). Uma
UF montada depois (ganhou dados durante a noite) entra pelo `registrar`, chamado pelo `ao_montar` do
`create_multi_app`. Um erro numa UF vai para o log e não para as outras.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from apuracao.boletim import Boletineiro
from apuracao.copia import Copiador
from apuracao.web.multi import EntradaUF

logger = logging.getLogger("apuracao.web.servicos")

PERIODOS_S = {"alertas": 15.0, "boletim": 30.0, "copia": 60.0}


@dataclass
class ServicosUFs:
    boletim: bool = True
    boletim_min: int = 60
    copia: bool = True
    copia_base: Path = Path("copias")
    copia_min: int = 60
    alertas: bool = True
    destacar: tuple[str, ...] = ()
    itens: dict[str, dict[str, Any]] = field(default_factory=dict)
    _trava: threading.Lock = field(default_factory=threading.Lock)

    def registrar(self, e: EntradaUF, app: FastAPI) -> None:
        """Cria os serviços da UF (chamado a cada UF montada no site)."""
        objs: dict[str, Any] = {}
        if self.boletim:
            objs["boletim"] = Boletineiro(app.state.consultas, e.dados / "boletins", self.boletim_min,
                                          destacar=self.destacar)
        if self.copia:
            try:
                objs["copia"] = Copiador(e.dados, self.copia_base / e.dados.name, e.uf, self.copia_min)
            except ValueError as exc:  # destino dentro da pasta de dados
                logger.error("%s: cópia de segurança desligada: %s", e.uf, exc)
        if self.alertas:
            objs["alertas"] = app.state.vigia
        with self._trava:
            self.itens[e.uf] = objs
        logger.info("%s: %s", e.uf, ", ".join(objs) or "sem serviços")

    def passo(self, agora: float, ultimo: dict[str, float]) -> None:
        """Uma volta: cada tipo de serviço, se já passou o seu período, em todas as UFs."""
        with self._trava:
            itens = {uf: dict(objs) for uf, objs in self.itens.items()}
        for tipo, periodo in PERIODOS_S.items():
            if agora - ultimo.get(tipo, float("-inf")) < periodo:
                continue
            ultimo[tipo] = agora
            for uf, objs in itens.items():
                obj = objs.get(tipo)
                if obj is None:
                    continue
                try:
                    obj.verificar()
                except Exception:  # um serviço de uma UF nunca derruba os outros nem o site
                    logger.exception("%s: %s falhou; nova tentativa na próxima volta", uf, tipo)

    def executar(self, parar: threading.Event, atualizar: Callable[[], Any] | None = None,
                 relogio: Callable[[], float] = time.monotonic) -> None:
        """Laço até `parar`. `atualizar` (o `raiz.state.atualizar` do site) monta as UFs que ganharam dados."""
        ultimo: dict[str, float] = {}
        while not parar.is_set():
            if atualizar is not None:
                try:
                    atualizar()
                except Exception:
                    logger.exception("montagem de UF nova falhou; nova tentativa na próxima volta")
            self.passo(relogio(), ultimo)
            parar.wait(PERIODOS_S["alertas"])
