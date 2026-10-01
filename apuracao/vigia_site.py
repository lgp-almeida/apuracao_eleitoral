"""Vigia de processo: sobe o site (ou o coletor) como processo filho e o reinicia se ele terminar ou parar
de responder. A saída do site continua no mesmo terminal; os eventos do vigia vão também para
`<pasta>/porta_<N>.log` e o estado para `<pasta>/porta_<N>.json`, que o portal lê.

    python vigiar_site.py -- python site_apuracao.py --ambiente oficial --coletar --abrir

Reiniciar não perde nada: o coletor retoma de `dados_2026/<ambiente>` (último estado, séries e raw/).
No reinício, `--abrir` sai do comando (não abrir outra janela do Chrome a cada queda).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("apuracao.vigia_site")
PASTA_PADRAO = Path("dados_2026/vigia")


def sondar_http(porta: int, timeout: float = 10.0) -> bool:
    try:
        return requests.get(f"http://127.0.0.1:{porta}/api/status", timeout=timeout).ok
    except requests.RequestException:
        return False


def porta_do_comando(comando: list[str], padrao: int = 8000) -> int:
    for i, arg in enumerate(comando):
        if arg == "--porta" and i + 1 < len(comando):
            return int(comando[i + 1])
        if arg.startswith("--porta="):
            return int(arg.split("=", 1)[1])
    return padrao


class VigiaSite:
    def __init__(self, comando: list[str], porta: int | None = None, pasta: Path = PASTA_PADRAO,
                 intervalo_s: float = 30.0, falhas_max: int = 3, espera_inicial_s: float = 90.0,
                 sondar: Callable[[int], bool] = sondar_http) -> None:
        if not comando:
            raise ValueError("informe o comando a vigiar depois de --")
        self.comando, self.porta = list(comando), porta or porta_do_comando(comando)
        self.pasta, self.intervalo_s, self.falhas_max = pasta, intervalo_s, falhas_max
        self.espera_inicial_s, self.sondar = espera_inicial_s, sondar
        self.proc: subprocess.Popen | None = None
        self.inicio = 0.0
        self.falhas = 0
        self.reinicios: list[float] = []
        self.eventos: list[dict[str, Any]] = []
        self.estado = "iniciando"

    # ------------------------------------------------------------ processo
    def iniciar(self) -> None:
        cmd = self.comando if not self.reinicios else [a for a in self.comando if a != "--abrir"]
        self.proc = subprocess.Popen(cmd)
        self.inicio = time.monotonic()
        self.falhas = 0
        self.estado = "iniciando"
        self._evento("inicio", f"processo {self.proc.pid}: {' '.join(cmd)}")

    def matar(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(5)

    def reiniciar(self, motivo: str) -> None:
        agora = time.monotonic()
        recentes = [t for t in self.reinicios if agora - t < 600]
        self.reinicios.append(agora)
        self._evento("reinicio", f"{motivo} — reinício nº {len(self.reinicios)}", nivel=logging.ERROR)
        if len(recentes) >= 5:  # caindo em série (ex.: porta ocupada): não martelar
            self._evento("pausa", "5 reinícios em 10 min: pausa de 60 s antes de tentar de novo", nivel=logging.ERROR)
            time.sleep(60)
        self.iniciar()

    # ------------------------------------------------------------ verificação
    def passo(self) -> None:
        """Uma verificação: processo vivo? respondendo? (com tolerância no início e a falhas isoladas)"""
        assert self.proc is not None
        codigo = self.proc.poll()
        if codigo is not None:
            self.estado = "fora do ar"
            self.reiniciar(f"o processo terminou (código {codigo})")
            return
        if time.monotonic() - self.inicio < self.espera_inicial_s:
            if self.sondar(self.porta):
                self._no_ar()
            return
        if self.sondar(self.porta):
            self._no_ar()
            return
        self.falhas += 1
        self._evento("sem_resposta", f"/api/status sem resposta ({self.falhas} de {self.falhas_max})",
                     nivel=logging.WARNING)
        if self.falhas >= self.falhas_max:
            self.estado = "fora do ar"
            self.matar()
            self.reiniciar(f"sem resposta em {self.falhas} verificações seguidas")

    def _no_ar(self) -> None:
        if self.estado != "no ar":
            self._evento("no_ar", f"respondendo na porta {self.porta}")
        self.estado, self.falhas = "no ar", 0
        self._gravar()

    # ------------------------------------------------------------ registro
    def _evento(self, tipo: str, detalhe: str, nivel: int = logging.INFO) -> None:
        ev = {"hora": datetime.now().isoformat(timespec="seconds"), "tipo": tipo, "detalhe": detalhe}
        self.eventos = (self.eventos + [ev])[-100:]
        logger.log(nivel, "VIGIA porta %d: %s", self.porta, detalhe)
        if nivel >= logging.ERROR and sys.stderr.isatty():
            sys.stderr.write("\a")
        self.pasta.mkdir(parents=True, exist_ok=True)
        with open(self.pasta / f"porta_{self.porta}.log", "a", encoding="utf-8") as fh:
            fh.write(f"{ev['hora']} {tipo}: {detalhe}\n")
        self._gravar()

    def _gravar(self) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        estado = {"porta": self.porta, "estado": self.estado, "pid": self.proc.pid if self.proc else None,
                  "comando": self.comando, "reinicios": len(self.reinicios), "vigia_pid": os.getpid(),
                  "atualizado": datetime.now().isoformat(timespec="seconds"), "eventos": self.eventos[-20:]}
        tmp = self.pasta / f"porta_{self.porta}.json.tmp"
        tmp.write_text(json.dumps(estado, indent=1, ensure_ascii=False))
        os.replace(tmp, self.pasta / f"porta_{self.porta}.json")

    def executar(self, parar: threading.Event) -> None:
        self.iniciar()
        try:
            while not parar.is_set():
                parar.wait(self.intervalo_s)
                if not parar.is_set():
                    self.passo()
        finally:
            self.estado = "encerrado"
            self._evento("fim", "vigia encerrado: processo vigiado parado")
            self.matar()
