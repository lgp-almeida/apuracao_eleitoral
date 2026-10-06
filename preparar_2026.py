"""Vigia e prepara os microdados de 2026 assim que o TSE publicar (item 4 do TODO).

    python preparar_2026.py                     # verifica agora (8 HEADs) e prepara o que chegou
    python preparar_2026.py --vigiar            # verifica a cada hora até chegarem os totais oficiais
    python preparar_2026.py --so-verificar      # só consulta o TSE (8 HEADs): não baixa, não importa
    python preparar_2026.py --limpar-vazios     # tira do cache ZIPs de 2026 que só têm cabeçalho

Ao chegar: baixa (e baixa de novo se o TSE atualizar o arquivo), converte para Parquet (mapas e
comparação por bairro, Perfil × voto e planilhas passam a oferecer 2026 sozinhos), importa o resultado
oficial para dados_2026/historico_2026_t<turno>/ (abrir com: python site_apuracao.py --dados ...)
e grava a transferência 2022 → 2026 por bairro em saidas/transferencia_2022_2026.csv.
Totais: os oficiais (detalhe_votacao_munzona) ou, até o TSE publicá-lo, os reconstruídos das seções
(provisórios, marcados no status.json); quando o oficial chega, importa de novo e grava a conferência
em saidas/conferencia_totais_<ano>_t<turno>.csv (rodada 40).
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
from apuracao.ufs import dir_uf

logger = logging.getLogger("preparar_2026")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Microdados de 2026: vigiar a publicação e preparar tudo sozinho.")
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    p.add_argument("--raiz", type=Path, default=Path("dados_2026"), help="destino do histórico importado")
    p.add_argument("--saidas", type=Path, default=Path("saidas"))
    modo = p.add_mutually_exclusive_group()
    modo.add_argument("--vigiar", action="store_true",
                      help="repetir a verificação até os totais oficiais (detalhe e partido munzona) chegarem")
    modo.add_argument("--so-verificar", action="store_true",
                      help="só consultar o TSE (um HEAD por arquivo) e mostrar o que há: não baixa nem importa")
    p.add_argument("--intervalo", type=float, default=3600, help="segundos entre verificações (mínimo 600)")
    p.add_argument("--limpar-vazios", action="store_true", help="apagar do cache os ZIPs só com cabeçalho")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def ao_chegar(a: argparse.Namespace):
    """Reação ao que chegou ou mudou (`mudaram`). O que já existe vem do CACHE (`md.no_cache`), não da memória
    do processo: numa execução nova, chegar só o detalhe munzona ainda dispara a importação (rodada 40)."""
    def reagir(mudaram: set[str]) -> None:
        tem = md.no_cache(a.cache_dir, a.ano, a.uf) | mudaram
        feitos = md.converter(a.cache_dir, a.ano, a.uf, mudaram)
        if feitos:
            logger.info("convertido para Parquet: %s", ", ".join(feitos))
        totais_de = md.fonte_dos_totais(tem)
        if totais_de and mudaram & md.PARA_IMPORTAR:
            importar(a, totais_de)
        if mudaram & {"votos_uf", "votos_br", "perfil"}:
            from apuracao import ibge
            for falha in ibge.preparar(a.cache_dir, a.uf):  # malhas e Censo para os mapas e o Perfil × voto de 2026
                logger.warning("IBGE: %s (python preparar_ibge.py)", falha)
        if "votos_uf" in mudaram:
            transferencia(a)
    return reagir


def importar(a: argparse.Namespace, totais_de: str) -> dict[int, str]:
    """Importa os dois turnos para dados_2026/historico_<ano>_t<turno> (na pasta da UF). Ao trocar totais
    reconstruídos (provisórios) pelos oficiais, grava a conferência entre os dois em <saidas>/."""
    from apuracao import historico
    feitos: dict[int, str] = {}
    try:
        detalhe = (historico.load_detalhe(a.ano, a.cache_dir) if totais_de == "munzona"
                   else historico.load_detalhe_secoes(a.ano, a.uf, a.cache_dir))  # os dois turnos, uma vez
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("totais de %s (%s) indisponíveis: %s", a.ano, totais_de, exc)
        return feitos
    for turno in (1, 2):
        destino = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf)  # cada UF na sua pasta
        antes = _totais_provisorios(destino) if totais_de == "munzona" else None
        try:
            n = historico.importar(a.ano, a.uf, turno, a.cache_dir, destino, totais_de=totais_de, detalhe=detalhe)
        except v.TseDataError as exc:
            logger.info("%sº turno de %s ainda sem dados: %s", turno, a.ano, exc)
            continue
        feitos[turno] = totais_de
        logger.info("resultado oficial de %s (%sº turno, totais %s) importado em %s: %s", a.ano, turno,
                    historico.DESCRICAO_TOTAIS[totais_de], destino, n)
        if antes is not None:
            conf = historico.conferir_totais(antes, pl.read_parquet(destino / "ultimo" / "totais.parquet"))
            a.saidas.mkdir(parents=True, exist_ok=True)
            alvo = a.saidas / f"conferencia_totais_{a.ano}_t{turno}.csv"
            conf.write_csv(alvo, separator=";")
            logger.info("totais reconstruídos × oficiais (%sº turno): %d linhas com diferença → %s",
                        turno, conf.height, alvo)
    return feitos


def totais_importados(a: argparse.Namespace) -> str | None:
    """"munzona"/"secoes" conforme o status.json do 1º turno importado; None se ainda não importado."""
    import json
    st = dir_uf(a.raiz / f"historico_{a.ano}_t1", a.uf) / "status.json"
    if not st.exists():
        return None
    dados = json.loads(st.read_text())
    return dados.get("totais_de", "munzona") if dados.get("ano") == a.ano else None


def garantir_importacao(a: argparse.Namespace) -> str | None:
    """Importa se o cache permite totais MELHORES que os importados (nada → provisório → oficial). Cobre o
    que chegou numa execução que não importou (versão antiga do gatilho, queda no meio). Devolve os totais
    importados depois disso."""
    melhor = md.fonte_dos_totais(md.no_cache(a.cache_dir, a.ano, a.uf))
    atual = totais_importados(a)
    ordem = {None: 0, "secoes": 1, "munzona": 2}
    if melhor and ordem[melhor] > ordem[atual]:
        importar(a, melhor)
        atual = totais_importados(a)
    return atual


def _totais_provisorios(destino: Path) -> pl.DataFrame | None:
    """Os totais de uma importação anterior com totais reconstruídos (para conferir com os oficiais)."""
    import json
    st, tot = destino / "status.json", destino / "ultimo" / "totais.parquet"
    if not (st.exists() and tot.exists()) or json.loads(st.read_text()).get("totais_de") != "secoes":
        return None
    return pl.read_parquet(tot)


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
    with pl.Config(tbl_rows=20, tbl_width_chars=190, fmt_str_lengths=45):
        print(pl.DataFrame([{"arquivo": e.zip, "CDN": e.http, "modificado no TSE": e.remoto_modificado,
                             "MB": round(e.remoto_bytes / 1e6, 1) if e.remoto_bytes and e.http == 200 else None,
                             "situação": e.situacao, "ação": e.acao} for e in estados]))


def resumo(a: argparse.Namespace, estados: list[md.Estado]) -> list[str]:
    """O que a verificação significa para a importação (sem baixar nada)."""
    nomes = {x.chave: x.zip(a.ano, a.uf) for x in md.ARQUIVOS}
    fora = [e.zip for e in estados if e.http == 404]
    novos = [e.zip for e in estados if e.acao in ("baixar", "baixar de novo")]
    cache = md.no_cache(a.cache_dir, a.ano, a.uf)
    importado = totais_importados(a)
    linhas = [f"ainda não publicados no TSE (404): {', '.join(fora) or 'nenhum'}",
              f"publicados e ainda não baixados (ou atualizados pelo TSE): {', '.join(novos) or 'nenhum'}"
              + (" — rode sem --so-verificar para baixar e importar" if novos else ""),
              f"importado: {historico_descricao(importado)}"]
    faltam = sorted(nomes[c] for c in md.FINAL - cache)
    if faltam:
        linhas.append(f"para os totais oficiais ainda falta no cache: {', '.join(faltam)}")
    return linhas


def historico_descricao(totais_de: str | None) -> str:
    return {None: "nada", "secoes": "sim, com totais PROVISÓRIOS (reconstruídos das seções)",
            "munzona": "sim, com os totais OFICIAIS"}[totais_de]


def main(argv: list[str] | None = None, sessao=requests) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if a.limpar_vazios:
        apagados = md.limpar_cache_vazio(a.cache_dir, a.ano, a.uf)
        print("apagados do cache (só cabeçalho):", ", ".join(apagados) or "nenhum")
    if a.so_verificar:
        try:
            estados = md.verificar(a.cache_dir, a.ano, a.uf, sessao)
        except requests.RequestException as exc:
            logger.error("verificação falhou: %s", exc)
            return 1
        imprimir(estados)
        print("\n".join(resumo(a, estados)))
        return 0
    intervalo = max(a.intervalo, 600)  # nunca martelar a CDN
    while True:
        try:
            estados = md.preparar(a.cache_dir, a.ano, a.uf, sessao, ao_chegar=ao_chegar(a))
        except requests.RequestException as exc:
            logger.error("verificação falhou (%s); tento de novo no próximo intervalo", exc)
            estados = []
        if estados:
            imprimir(estados)
            garantir_importacao(a)
        # encerra só com o que a importação DEFINITIVA usa (totais oficiais): antes disso a importação, se
        # houver, é a provisória, e o vigia precisa seguir para trocá-la pela oficial quando o TSE publicar
        pronto = md.FINAL <= md.no_cache(a.cache_dir, a.ano, a.uf)
        if not a.vigiar or pronto:
            if a.vigiar:
                print("microdados de", a.ano, "completos (com os totais oficiais) e preparados; vigia encerrado.")
            return 0
        logger.info("próxima verificação em %.0f min", intervalo / 60)
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
