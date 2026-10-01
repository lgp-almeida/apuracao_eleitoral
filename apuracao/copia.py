"""Cópia de segurança dos dados da noite, automática, para outra pasta (de preferência outro disco).

Duas partes, com custos diferentes:
  * `raw/` — TODAS as versões dos JSON do TSE (a evolução da apuração, parcial a parcial; o TSE as
    sobrescreve). Os arquivos nunca mudam depois de gravados: a cópia é um ESPELHO incremental (só entram
    os novos), refeito a cada `espelho_min` minutos;
  * o resto (último estado, séries, histórico de totais e de candidatos, boletins, alertas, status) — um
    INSTANTÂNEO por hora cheia e um "final" quando todos os cargos da UF têm totalização final. Guarda os
    `manter` últimos da hora e sempre o final.

    destino/raw/…, destino/raw_brasil/…  espelho de dados/raw e dados/raw_brasil
    destino/instantaneos/2026-10-04_20h00/{ultimo,historico_*.parquet,historico_candidatos,boletins,…}
    destino/instantaneos/final/…
    destino/copias.json                o registro das cópias (quando, quantos arquivos novos)

Restaurar: copiar um instantâneo de volta para dados/ e o espelho de raw/ para dados/raw/
(docs/ROTEIRO_NOITE_DA_ELEICAO.md).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from apuracao.alertas import agora_brasilia

logger = logging.getLogger("apuracao.copia")
FINAL = "final"


RAIZES_BRUTAS = ("raw", "raw_brasil")  # espelhadas a cada poucos minutos (arquivos nunca mudam)


class Copiador:
    def __init__(self, origem: Path, destino: Path, uf: str = "RJ", intervalo_min: int = 60, manter: int = 6,
                 espelho_min: float = 5, agora: Callable[[], datetime] = agora_brasilia) -> None:
        if origem.resolve() == destino.resolve() or destino.resolve().is_relative_to(origem.resolve()):
            raise ValueError("a cópia não pode ficar dentro da pasta de dados")
        if not 0 < intervalo_min <= 24 * 60:
            raise ValueError("intervalo_min deve estar entre 1 e 1440")
        self.origem, self.destino, self.uf = origem, destino, uf.upper()
        self.intervalo_min, self.manter, self.espelho_min, self.agora = intervalo_min, manter, espelho_min, agora
        self._ultimo_espelho = 0.0

    # ------------------------------------------------------------ espelho de raw/
    def espelhar_raw(self) -> int:
        """Copia para destino/<raw> os arquivos de raw/ e raw_brasil/ (presidente nas outras UFs) que ainda
        não estão lá. Devolve quantos."""
        novos = 0
        for raiz in RAIZES_BRUTAS:
            base = self.origem / raiz
            if not base.exists():
                continue
            for arq in base.rglob("*.json.gz"):
                alvo = self.destino / raiz / arq.relative_to(base)
                if alvo.exists() and alvo.stat().st_size == arq.stat().st_size:
                    continue
                alvo.parent.mkdir(parents=True, exist_ok=True)
                tmp = alvo.with_name(alvo.name + ".tmp")
                shutil.copy2(arq, tmp)
                os.replace(tmp, alvo)
                novos += 1
        self._ultimo_espelho = time.monotonic()
        return novos

    # ------------------------------------------------------------ instantâneo
    def instantaneo(self, nome: str) -> Path:
        """Tudo menos raw/ e raw_brasil/, numa pasta com o nome dado (troca atômica: a pasta só aparece completa)."""
        pasta = self.destino / "instantaneos" / nome
        tmp = self.destino / "instantaneos" / f".{nome}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        for item in self.origem.iterdir():
            if item.name in RAIZES_BRUTAS or item.name.endswith(".tmp"):
                continue
            try:
                if item.is_dir():
                    shutil.copytree(item, tmp / item.name, ignore=shutil.ignore_patterns("*.tmp", ".*"))
                else:
                    shutil.copy2(item, tmp / item.name)
            except FileNotFoundError:  # o coletor trocou o arquivo durante a cópia: a próxima pega
                logger.warning("cópia: %s mudou durante a cópia", item)
        antigo = pasta.with_name(f".{nome}.antigo")
        if pasta.exists():
            os.replace(pasta, antigo)
        os.replace(tmp, pasta)
        shutil.rmtree(antigo, ignore_errors=True)
        return pasta

    def podar(self) -> list[str]:
        """Apaga os instantâneos DA HORA (nome AAAA-MM-DD_HHhMM) além dos `manter` mais recentes; o final e as
        cópias manuais nunca."""
        pasta = self.destino / "instantaneos"
        horas = sorted(p.name for p in pasta.iterdir() if p.is_dir() and p.name[:4].isdigit()) if pasta.exists() else []
        apagar = horas[:-self.manter] if len(horas) > self.manter else []
        for nome in apagar:
            shutil.rmtree(pasta / nome, ignore_errors=True)
        return apagar

    def copiar(self, nome: str) -> dict[str, Any]:
        t0 = time.monotonic()
        novos = self.espelhar_raw()
        pasta = self.instantaneo(nome)
        apagados = self.podar()
        registro = {"nome": nome, "hora": self.agora().isoformat(timespec="seconds"), "raw_novos": novos,
                    "instantaneo": str(pasta), "podados": apagados, "segundos": round(time.monotonic() - t0, 1)}
        log = self.destino / "copias.json"
        historico = json.loads(log.read_text()) if log.exists() else []
        log.write_text(json.dumps((historico + [registro])[-500:], indent=1, ensure_ascii=False))
        logger.info("cópia de segurança %s em %s (%d arquivos novos de raw/, %.1f s)", nome, pasta, novos,
                    registro["segundos"])
        return registro

    # ------------------------------------------------------------ quando copiar
    def situacao(self) -> str:
        """"sem dados", "andamento" ou "final" (todos os cargos NA UF com totalização final)."""
        arq = self.origem / "ultimo" / "totais.parquet"
        if not arq.exists():
            return "sem dados"
        t = pl.read_parquet(arq).filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == self.uf))
        if t.is_empty() or not (t["PCT_SECOES_TOTALIZADAS"].fill_null(0) > 0).any():
            return "sem dados"
        return "final" if t["TOTALIZACAO_FINAL"].fill_null(False).all() else "andamento"

    def _horario(self, t: datetime) -> datetime:
        minutos = (t.hour * 60 + t.minute) // self.intervalo_min * self.intervalo_min
        return t.replace(hour=minutos // 60, minute=minutos % 60, second=0, microsecond=0)

    def verificar(self) -> dict[str, Any] | None:
        """Espelha raw/ se passou `espelho_min`; faz o instantâneo da hora ou o final se for a vez."""
        sit = self.situacao()
        if sit == "sem dados":
            return None
        pasta = self.destino / "instantaneos"
        if sit == "final":
            if (pasta / FINAL).exists():
                return None
            return self.copiar(FINAL)
        nome = f"{self._horario(self.agora()):%Y-%m-%d_%Hh%M}"
        if not (pasta / nome).exists():
            return self.copiar(nome)
        if time.monotonic() - self._ultimo_espelho >= 60 * self.espelho_min:
            n = self.espelhar_raw()
            if n:
                logger.info("cópia de segurança: %d parciais novas espelhadas", n)
        return None

    def executar(self, parar: threading.Event, verificar_s: float = 60.0) -> None:
        """Laço até `parar`; um erro (ex.: disco da cópia cheio ou desconectado) vai para o log e o
        laço segue — a cópia nunca pode derrubar o site nem o coletor."""
        while not parar.is_set():
            try:
                self.verificar()
            except Exception:
                logger.exception("cópia de segurança falhou; nova tentativa em %.0f s", verificar_s)
            parar.wait(verificar_s)
