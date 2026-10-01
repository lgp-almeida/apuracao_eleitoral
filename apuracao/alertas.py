"""Alertas durante a noite: avisos no site (destaque e som) e no terminal, sem serviço externo.

Dois tipos:
  * CONDIÇÕES, que valem enquanto durarem e avisam ao começar e ao terminar ("resolvido"):
    coletor encerrado ou parado, bloqueio do TSE, erro na coleta, apuração sem avanço;
  * EVENTOS, que avisam uma vez: a leitura da projeção de um cargo majoritário mudou ("indefinido" →
    "vitória no 1º turno projetada"…) e a situação de um candidato de interesse (deputado) mudou
    (em disputa → consolidado, saiu da disputa, eleito…).

O estado fica em `<dados>/alertas.json` (histórico, condições ativas, última leitura de cada cargo,
situação de cada candidato de interesse): reiniciar o site não repete alertas nem os perde.
A 1ª observação de uma leitura ou de um candidato é gravada em silêncio: só MUDANÇA vira alerta.

    vigia = app.state.vigia          # criado por create_app, com as mesmas consultas das rotas
    vigia.verificar()                # novos alertas (a thread do site chama a cada 15 s)
    vigia.lista(desde=12)            # o que a página mostra (GET /api/alertas)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import polars as pl

import votos_por_local_votacao as v

if TYPE_CHECKING:  # web.app importa este módulo
    from apuracao.web.app import Consultas

logger = logging.getLogger("apuracao.alertas")

BRASILIA = ZoneInfo("America/Sao_Paulo")
ARQUIVO = "alertas.json"
NIVEIS = ("critico", "aviso", "noticia", "ok")
MAX_HISTORICO = 300
MAX_INTERESSE = 50
PARADO_MIN_S = 600          # coleta parada: nenhum ciclo há max(10 min, 3 intervalos) (+ a pausa de um bloqueio)
ESTAGNADA_MIN = 20          # apuração sem nova totalização do TSE na UF há 20 min, com seções faltando
CAUDA_PCT = 99.5            # acima disto a demora é a cauda normal (ensaio de 2022: 99,99% das 23h33 às 00h07)
PERSISTENCIA_S = {"coletor:erro:rede": 150}  # falha de rede isolada se resolve no ciclo seguinte: só avisa se durar
MAJORITARIOS = (3, 5, 1)
PROPORCIONAIS = (6, 7, 8)
STATUS_PROJECAO = {"consolidado": "consolidado", "em disputa (dentro)": "em disputa, dentro das vagas",
                   "em disputa (fora)": "em disputa, fora das vagas"}
TITULO_ERRO = {"indisponivel": ("Divulgação do TSE indisponível", "O coletor tenta de novo a cada 5 min."),
               "rede": ("Falha de rede na coleta", "O coletor tenta de novo a cada ciclo."),
               "inesperado": ("Erro inesperado no coletor", "A coleta continua; veja o log do terminal."),
               None: ("Erro na coleta", "")}


def agora_brasilia() -> datetime:
    """Hora de Brasília sem fuso (a mesma convenção da hora de totalização do TSE)."""
    return datetime.now(BRASILIA).replace(tzinfo=None)


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _minutos(segundos: float) -> str:
    m = int(segundos // 60)
    return f"{m} min" if m < 120 else f"{m // 60} h {m % 60:02d} min"


def _n(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".")


def _p(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",") + "%"


def _hora_brasilia(iso_utc: str) -> str:
    t = datetime.fromisoformat(iso_utc)
    return f"{(t.astimezone(BRASILIA) if t.tzinfo else t):%H:%M}"


class Vigia:
    """Compara o estado da apuração com o da verificação anterior e registra os alertas."""

    def __init__(self, consultas: Consultas, arquivo: Path, coletor_status: dict[str, Any] | None = None,
                 interesse: Iterable[tuple[int, int]] = (), agora: Callable[[], datetime] = agora_brasilia,
                 relogio_utc: Callable[[], datetime] = agora_utc, estagnada_min: float = ESTAGNADA_MIN) -> None:
        self.consultas, self.arquivo, self.coletor_status = consultas, arquivo, coletor_status
        self.agora, self.relogio_utc, self.estagnada_min = agora, relogio_utc, estagnada_min
        self._trava = threading.RLock()
        self._vistas: dict[str, datetime] = {}   # condição -> quando foi vista pela 1ª vez (persistência)
        self.estado: dict[str, Any] = {"proximo_id": 1, "historico": [], "condicoes": {}, "leituras": {},
                                       "candidatos": {}, "interesse": []}
        if arquivo.exists():
            try:
                self.estado.update(json.loads(arquivo.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:  # arquivo corrompido não pode impedir o site de subir
                logger.warning("alertas.json ilegível (%s); começando do zero", exc)
        for cargo, numero in interesse:
            self._validar(cargo, numero)
            if [cargo, numero] not in self.estado["interesse"]:
                self.estado["interesse"].append([cargo, numero])

    # ------------------------------------------------------------ verificação
    def verificar(self) -> list[dict[str, Any]]:
        """Novos alertas desde a última verificação (também registrados no histórico e no log)."""
        with self._trava:
            st = self.consultas.dados.status()
            if st.get("ano"):  # eleição passada importada: nada acontece
                return []
            antes = json.dumps(self.estado, sort_keys=True, default=str)
            t = self.consultas.dados.tabela("totais")
            uf = t.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == self.consultas.uf))
            final = not uf.is_empty() and bool(uf["TOTALIZACAO_FINAL"].fill_null(False).all())
            novos = self._atualizar_condicoes(self._condicoes(st, uf, final))
            novos += self._leituras(uf)
            novos += self._candidatos()
            if json.dumps(self.estado, sort_keys=True, default=str) != antes:
                self._gravar()
            for a in novos:
                self._anunciar(a)
            return novos

    def _condicoes(self, st: dict[str, Any], uf: pl.DataFrame, final: bool) -> dict[str, tuple[str, str, str]]:
        """Condições que valem AGORA: chave -> (nível, título, detalhe)."""
        c: dict[str, tuple[str, str, str]] = {}
        cs = self.coletor_status
        if cs is not None and cs.get("erro"):
            c["coletor:encerrado"] = ("critico", "Coletor encerrado por erro",
                                      f"{cs['erro']}. Reinicie o site (roteiro da noite).")
        tipo, erro = st.get("tipo_erro"), st.get("erro")
        fim = st.get("ultimo_ciclo_fim") or st.get("ultimo_ciclo_inicio")
        if fim and not final:
            intervalo = float((cs or {}).get("intervalo_s") or 60)
            limite = max(PARADO_MIN_S, 3 * intervalo) + (float(st.get("pausa_s") or 0) if tipo == "bloqueio" else 0)
            idade = (self.relogio_utc() - datetime.fromisoformat(fim)).total_seconds()
            if idade > limite:
                c["coletor:parado"] = ("critico", f"Coleta parada há {_minutos(idade)}",
                                       f"Último ciclo às {_hora_brasilia(fim)}. Veja o terminal do coletor; "
                                       "se o processo caiu, suba de novo (o histórico é preservado).")
        if erro and tipo == "bloqueio":
            c["coletor:bloqueio"] = ("critico", "TSE bloqueou o acesso (403/429)",
                                     f"{erro}. O coletor pausa {int(st.get('pausa_s') or 660) // 60} min e tenta de "
                                     "novo sozinho: não reinicie nem rode outro coletor.")
        elif erro:
            titulo, dica = TITULO_ERRO.get(tipo, TITULO_ERRO[None])
            c[f"coletor:erro:{tipo}"] = ("aviso", titulo, f"{erro}. {dica}".strip())
        andamento = uf.filter((pl.col("PCT_SECOES_TOTALIZADAS").fill_null(0) > 0)
                              & ~pl.col("TOTALIZACAO_FINAL").fill_null(False))
        coleta_ok = not any(k in c for k in ("coletor:parado", "coletor:bloqueio", "coletor:encerrado"))
        if not andamento.is_empty() and coleta_ok:  # coleta com problema: a causa já está avisada
            ultima = uf["DT_TOTALIZACAO"].max()
            idade = (self.agora() - ultima).total_seconds() if ultima else 0
            if idade > 60 * self.estagnada_min and andamento["PCT_SECOES_TOTALIZADAS"].min() < CAUDA_PCT:
                menor = andamento.sort("PCT_SECOES_TOTALIZADAS").row(0, named=True)
                c["apuracao:estagnada"] = (
                    "aviso", f"Apuração sem avanço há {_minutos(idade)}",
                    f"Última totalização do TSE na UF às {ultima:%H:%M}; {menor['DS_CARGO']} com "
                    f"{_p(menor['PCT_SECOES_TOTALIZADAS'], 2)} das seções. Confira no site do TSE se a divulgação "
                    "parou para todos.")
        return c

    def _atualizar_condicoes(self, atuais: dict[str, tuple[str, str, str]]) -> list[dict[str, Any]]:
        novos = []
        agora = self.relogio_utc()
        for chave in list(self._vistas):
            if chave not in atuais:
                del self._vistas[chave]
        ativas = self.estado["condicoes"]
        for chave, (nivel, titulo, detalhe) in atuais.items():
            vista = self._vistas.setdefault(chave, agora)
            if chave in ativas:  # já avisada: só atualiza o texto (ex.: "parada há 14 min")
                ativas[chave].update(titulo=titulo, detalhe=detalhe)
            elif (agora - vista).total_seconds() >= PERSISTENCIA_S.get(chave, 0):
                a = self._registrar(chave, nivel, titulo, detalhe)
                ativas[chave] = {"id": a["id"], "nivel": nivel, "titulo": titulo, "detalhe": detalhe,
                                 "desde": a["momento"]}
                novos.append(a)
        for chave in [k for k in ativas if k not in atuais]:
            cond = ativas.pop(chave)
            novos.append(self._registrar(f"{chave}:resolvido", "ok", f"Resolvido: {cond['titulo']}",
                                         f"Condição avisada às {cond['desde'][11:16]} não vale mais."))
        return novos

    def _leituras(self, uf: pl.DataFrame) -> list[dict[str, Any]]:
        """Leitura da projeção (majoritários na UF): alerta quando a categoria muda."""
        novos = []
        for cargo in MAJORITARIOS:
            linha = uf.filter(pl.col("CARGO") == cargo)
            if linha.is_empty() or not (linha["PCT_SECOES_TOTALIZADAS"][0] or 0) > 0:
                continue
            try:
                p = self.consultas.projecao(cargo)
            except (ValueError, v.TseDataError) as exc:
                logger.debug("sem projeção de %s: %s", cargo, exc)
                continue
            situacao = p["situacao"]
            leitura = situacao.split(":")[0].strip()   # "indefinido: o líder está…" -> "indefinido"
            anterior = self.estado["leituras"].get(str(cargo))
            self.estado["leituras"][str(cargo)] = leitura
            sem_leitura = ("cedo demais", "sem apuração")
            if anterior is None or anterior == leitura or leitura in sem_leitura \
                    or (anterior in sem_leitura and leitura == "indefinido"):  # passar a ler "indefinido" não é notícia
                continue
            ds = linha["DS_CARGO"][0]
            k = p["candidatos"][0] if p["candidatos"] else {}
            if k.get("PCT_PROJ") is None:
                lider = ""
            elif p.get("margem_pp") == 0:  # apuração completa: é o resultado, não projeção
                lider = f" {k['NOME_URNA']} ({k['PARTIDO']}) com {_p(k['PCT_PROJ'])} dos válidos."
            else:
                lider = (f" Líder: {k['NOME_URNA']} ({k['PARTIDO']}), projeção de {_p(k['PCT_PROJ'])} "
                         f"(de {_p(k['MIN'])} a {_p(k['MAX'])}).")
            novos.append(self._registrar(f"leitura:{cargo}", "noticia", f"{ds}: {leitura}",
                                         f"Antes: {anterior}.{lider} {_p(p['pct_apurado'])} do eleitorado "
                                         "apurado."))
        return novos

    def _candidatos(self) -> list[dict[str, Any]]:
        novos = []
        for cargo, numero in self.estado["interesse"]:
            situacao, detalhe = self.situacao_candidato(cargo, numero)
            chave = f"{cargo}:{numero}"
            anterior = self.estado["candidatos"].get(chave)
            if situacao is None:
                continue
            self.estado["candidatos"][chave] = situacao
            if anterior is None or anterior == situacao:
                continue
            novos.append(self._registrar(f"candidato:{chave}", "noticia",
                                         f"{self._nome(cargo, numero)}: {situacao}",
                                         f"Antes: {anterior}. {detalhe}".strip()))
        return novos

    def situacao_candidato(self, cargo: int, numero: int) -> tuple[str | None, str]:
        """(situação, detalhe) de um deputado: eleito/não eleito no fim; na projeção (a partir de 30%
        apurado) consolidado, em disputa ou fora da disputa; antes disso, None."""
        try:
            cad = self.consultas.cadeiras(cargo)
        except (ValueError, v.TseDataError) as exc:
            logger.debug("sem cadeiras de %s: %s", cargo, exc)
            return None, ""
        if cad.get("final"):
            eleito = next((e for e in cad.get("eleitos", []) if e["NUMERO"] == numero), None)
            return ("eleito", f"{eleito['SITUACAO_PROJETADA']}, {_n(eleito['VOTOS'])} votos.") \
                if eleito else ("não eleito", "Totalização final.")
        proj = cad.get("projecao")
        if not proj or not proj.get("ativa"):
            return None, ""
        k = next((c for c in proj.get("candidatos", []) if c["NUMERO"] == numero), None)
        if k is None:
            return "fora da disputa", f"Eleito em menos de 5% das {proj['simulacoes']} simulações."
        return STATUS_PROJECAO.get(k["STATUS"], k["STATUS"]), (
            f"Eleito em {_p(100 * k['FREQ_ELEITO'], 0)} das {proj['simulacoes']} simulações; "
            f"{_n(k['VOTOS_PROJ'])} votos projetados com {_p(proj['pct_apurado'])} apurado.")

    def _nome(self, cargo: int, numero: int) -> str:
        c = self.consultas.dados.tabela("candidatos").filter(
            (pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == self.consultas.uf) & (pl.col("CARGO") == cargo)
            & (pl.col("NUMERO") == numero))
        return f"{numero} {c['NOME_URNA'][0]}" if c.height else str(numero)

    # ------------------------------------------------------------ interesse
    @staticmethod
    def _validar(cargo: int, numero: int) -> None:
        if cargo not in PROPORCIONAIS:
            raise ValueError(f"candidato de interesse só de deputado (cargo 6, 7 ou 8), não {cargo}")
        if not 0 < numero < 100_000:
            raise ValueError(f"número inválido: {numero}")

    def definir_interesse(self, cargo: int, numero: int, acompanhar: bool) -> None:
        """Liga/desliga os alertas de um deputado. A situação atual é gravada em silêncio."""
        self._validar(cargo, numero)
        with self._trava:
            lista = self.estado["interesse"]
            if acompanhar and [cargo, numero] not in lista:
                if len(lista) >= MAX_INTERESSE:
                    raise ValueError(f"no máximo {MAX_INTERESSE} candidatos de interesse")
                lista.append([cargo, numero])
                situacao, _ = self.situacao_candidato(cargo, numero)
                if situacao:
                    self.estado["candidatos"][f"{cargo}:{numero}"] = situacao
            elif not acompanhar and [cargo, numero] in lista:
                lista.remove([cargo, numero])
                self.estado["candidatos"].pop(f"{cargo}:{numero}", None)
            self._gravar()

    # ------------------------------------------------------------ leitura (página)
    def lista(self, desde: int = 0) -> dict[str, Any]:
        with self._trava:
            return {
                "ultimo_id": self.estado["proximo_id"] - 1,
                "alertas": [a for a in self.estado["historico"] if a["id"] > desde][-100:],
                "ativos": [{"chave": k, **c} for k, c in self.estado["condicoes"].items()],
                "interesse": [{"cargo": c, "numero": n, "nome": self._nome(c, n),
                               "situacao": self.estado["candidatos"].get(f"{c}:{n}")}
                              for c, n in self.estado["interesse"]],
            }

    # ------------------------------------------------------------ registro
    def _registrar(self, chave: str, nivel: str, titulo: str, detalhe: str) -> dict[str, Any]:
        a = {"id": self.estado["proximo_id"], "chave": chave, "nivel": nivel, "titulo": titulo,
             "detalhe": detalhe, "momento": self.agora().isoformat(timespec="seconds")}
        self.estado["proximo_id"] += 1
        self.estado["historico"] = (self.estado["historico"] + [a])[-MAX_HISTORICO:]
        return a

    def _anunciar(self, a: dict[str, Any]) -> None:
        nivel = {"critico": logging.ERROR, "aviso": logging.WARNING}.get(a["nivel"], logging.INFO)
        logger.log(nivel, "ALERTA [%s] %s — %s", a["nivel"], a["titulo"], a["detalhe"])
        if a["nivel"] in ("critico", "aviso") and sys.stderr.isatty():
            sys.stderr.write("\a")  # campainha do terminal
            sys.stderr.flush()

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.estado, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, self.arquivo)

    def executar(self, parar: threading.Event, verificar_s: float = 15.0) -> None:
        """Laço até `parar`: um erro vai para o log e a verificação seguinte roda normalmente."""
        while not parar.is_set():
            try:
                self.verificar()
            except Exception:  # os alertas nunca podem derrubar o site nem o coletor
                logger.exception("verificação de alertas falhou; nova tentativa em %.0f s", verificar_s)
            parar.wait(verificar_s)
