"""Vigia e prepara os microdados de 2026 assim que o TSE publicar (item 4 do TODO).

    python preparar_2026.py                     # verifica agora (8 HEADs) e prepara o que chegou
    python preparar_2026.py --vigiar            # verifica a cada hora até chegarem os votos por seção
    python preparar_2026.py --limpar-vazios     # tira do cache ZIPs de 2026 que só têm cabeçalho

Ao chegar: baixa (e baixa de novo se o TSE atualizar o arquivo), converte para Parquet (mapas e
comparação por bairro, Perfil × voto e planilhas passam a oferecer 2026 sozinhos), importa o resultado
oficial para dados_2026/historico_2026_t<turno>/ (abrir com: python site_apuracao.py --dados ...)
e grava a transferência 2022 → 2026 por bairro em saidas/transferencia_2022_2026.csv.
Estado da última verificação: cache_tse/microdados_2026.json.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import microdados as md

logger = logging.getLogger("preparar_2026")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Microdados de 2026: vigiar a publicação e preparar tudo sozinho.")
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    p.add_argument("--raiz", type=Path, default=Path("dados_2026"), help="destino do histórico importado")
    p.add_argument("--saidas", type=Path, default=Path("saidas"))
    p.add_argument("--vigiar", action="store_true", help="repetir a verificação até os votos por seção chegarem")
    p.add_argument("--intervalo", type=float, default=3600, help="segundos entre verificações (mínimo 600)")
    p.add_argument("--limpar-vazios", action="store_true", help="apagar do cache os ZIPs só com cabeçalho")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def ao_chegar(a: argparse.Namespace, todos_com_dados: set[str]):
    def reagir(mudaram: set[str]) -> None:
        tem = todos_com_dados | mudaram
        feitos = md.converter(a.cache_dir, a.ano, a.uf, mudaram)
        if feitos:
            logger.info("convertido para Parquet: %s", ", ".join(feitos))
        if set(md.PARA_IMPORTAR) <= tem and mudaram & set(md.PARA_IMPORTAR):
            from apuracao import historico
            for turno in (1, 2):
                destino = a.raiz / f"historico_{a.ano}_t{turno}"
                try:
                    n = historico.importar(a.ano, a.uf, turno, a.cache_dir, destino)
                    logger.info("resultado oficial de %s (%sº turno) importado em %s: %s", a.ano, turno, destino, n)
                except v.TseDataError as exc:
                    logger.info("%sº turno de %s ainda sem dados: %s", turno, a.ano, exc)
        if "votos_uf" in mudaram:
            transferencia(a)
    return reagir


def transferencia(a: argparse.Namespace) -> None:
    from apuracao import bairros as br
    from apuracao import perfil as pf
    try:
        pv = pf.PerfilVoto(br.ComparacaoBairros(br.Bairros(a.uf, a.cache_dir)))
        df = pl.concat([pv.transferencias(2022, a.ano, cargo) for cargo in (1, 3, 5)])
    except (v.TseDataError, requests.RequestException, ValueError) as exc:
        logger.warning("transferência 2022 → %s por bairro não calculada: %s", a.ano, exc)
        return
    a.saidas.mkdir(parents=True, exist_ok=True)
    alvo = a.saidas / f"transferencia_2022_{a.ano}.csv"
    df.write_csv(alvo, separator=";")
    logger.info("transferência 2022 → %s por bairro: %s (%d linhas)", a.ano, alvo, df.height)
    with pl.Config(tbl_rows=40, tbl_width_chars=160):
        print(df.with_columns(pl.col("PEARSON", "SPEARMAN", "INCLINACAO", "R2").round(2)))


def imprimir(estados: list[md.Estado]) -> None:
    with pl.Config(tbl_rows=20, tbl_width_chars=170, fmt_str_lengths=45):
        print(pl.DataFrame([{"arquivo": e.zip, "CDN": e.http, "modificado no TSE": e.remoto_modificado,
                             "situação": e.situacao, "ação": e.acao} for e in estados]))


def main(argv: list[str] | None = None, sessao=requests) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if a.limpar_vazios:
        apagados = md.limpar_cache_vazio(a.cache_dir, a.ano, a.uf)
        print("apagados do cache (só cabeçalho):", ", ".join(apagados) or "nenhum")
    intervalo = max(a.intervalo, 600)  # nunca martelar a CDN
    anteriores: set[str] = set()
    while True:
        try:
            estados = md.preparar(a.cache_dir, a.ano, a.uf, sessao, ao_chegar=ao_chegar(a, anteriores))
        except requests.RequestException as exc:
            logger.error("verificação falhou (%s); tento de novo no próximo intervalo", exc)
            estados = []
        if estados:
            imprimir(estados)
            anteriores = md.com_dados(estados)
        pronto = {"votos_uf", "votos_br", "detalhe_secao"} <= anteriores
        if not a.vigiar or pronto:
            if a.vigiar:
                print("votos por seção de", a.ano, "chegaram e foram preparados; vigia encerrado.")
            return 0
        logger.info("próxima verificação em %.0f min", intervalo / 60)
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
