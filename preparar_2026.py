"""Vigia e prepara os microdados de 2026 assim que o TSE publicar (item 4 do TODO).

    python preparar_2026.py                     # verifica agora (8 HEADs) e prepara o que chegou
    python preparar_2026.py --vigiar            # verifica a cada hora até chegarem os totais oficiais
    python preparar_2026.py --so-verificar      # só consulta o TSE (8 HEADs): não baixa, não importa
    python preparar_2026.py --limpar-vazios     # tira do cache ZIPs de 2026 que só têm cabeçalho

Ao chegar: baixa (e baixa de novo se o TSE atualizar o arquivo), converte para Parquet (mapas e
comparação por bairro, Perfil × voto e planilhas passam a oferecer 2026 sozinhos), importa o resultado
oficial para dados_2026/historico_2026_t<turno>/ (abrir com: python site_apuracao.py --dados ...)
e grava a transferência 2022 → 2026 por bairro em saidas/transferencia_2022_2026.csv.
Totais, POR TURNO, do melhor para o pior (rodada 55): os oficiais (detalhe_votacao_munzona), os
reconstruídos das seções (rodada 40) ou os reconstruídos do Boletim de Urna (o BU sai dias antes dos
microdados no 2º turno: procurado no CKAN só quando nada melhor existe para o turno). Os provisórios são
marcados no status.json; um nível melhor substitui o pior (nunca o contrário) e grava a conferência entre os
dois em saidas/conferencia_<antigo>_x_<novo>_<turno>t.csv.
    --politica-totais {auto,oficial,secoes,bweb}  # fixa o nível (falha se indisponível; nunca cai para outro)
    --bweb-brasil                                 # Presidente no Brasil pelo BU: baixa os 28 BUs do turno
Estado da última verificação: cache_tse/microdados_2026.json.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
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
    modo.add_argument("--acompanhar", action="store_true",
                      help="como --vigiar, mas sem parar nos totais oficiais: segue verificando (a cada "
                           "--intervalo-final) e reimporta quando o TSE regera um arquivo")
    modo.add_argument("--so-verificar", action="store_true",
                      help="só consultar o TSE (um HEAD por arquivo) e mostrar o que há: não baixa nem importa")
    p.add_argument("--intervalo", type=float, default=3600, help="segundos entre verificações (mínimo 600)")
    p.add_argument("--intervalo-final", type=float, default=3 * 3600,
                   help="com --acompanhar, depois dos totais oficiais: segundos entre verificações (mínimo 3600)")
    p.add_argument("--ate", type=date.fromisoformat, help="com --acompanhar: parar depois deste dia (AAAA-MM-DD)")
    p.add_argument("--limpar-vazios", action="store_true", help="apagar do cache os ZIPs só com cabeçalho")
    p.add_argument("--politica-totais", choices=list(md.POLITICAS), default="auto",
                   help="nível dos totais: o melhor disponível (auto) ou um fixo, que falha se indisponível")
    p.add_argument("--bweb-brasil", action="store_true",
                   help="com o Boletim de Urna, baixar os das 27 UFs + exterior (Presidente no Brasil)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def ao_chegar(a: argparse.Namespace):
    """Reação ao que chegou ou mudou (`mudaram`). O que já existe vem do CACHE (`md.no_cache`), não da memória
    do processo: numa execução nova, chegar só o detalhe munzona ainda dispara a importação (rodada 40)."""
    def reagir(mudaram: set[str]) -> None:
        feitos = md.converter(a.cache_dir, a.ano, a.uf, mudaram)
        if feitos:
            logger.info("convertido para Parquet: %s", ", ".join(feitos))
        atualizar(a, mudaram)
        if mudaram & {"votos_uf", "votos_br", "perfil"}:
            from apuracao import ibge
            for falha in ibge.preparar(a.cache_dir, a.uf):  # malhas e Censo para os mapas e o Perfil × voto de 2026
                logger.warning("IBGE: %s (python preparar_ibge.py)", falha)
        if "votos_uf" in mudaram:
            transferencia(a)
    return reagir


def _politica(a: argparse.Namespace) -> str:
    return getattr(a, "politica_totais", "auto")


def nivel(a: argparse.Namespace, turno: int, com: set[str] | None = None) -> str | None:
    """O nível dos totais a importar no turno (`md.escolher_nivel`); política fixa indisponível → erro."""
    return md.escolher_nivel(md.niveis_disponiveis(a.cache_dir, a.ano, a.uf, turno, com), _politica(a))


def atualizar(a: argparse.Namespace, mudaram: set[str] | frozenset[str] = frozenset()) -> dict[int, str | None]:
    """Por turno: importa quando o nível disponível é MELHOR que o importado, ou é o mesmo e um insumo dele
    mudou; nunca troca um nível melhor por um pior (só a política fixa, pedida explicitamente). Devolve o
    nível importado em cada turno depois disso."""
    com = md.no_cache(a.cache_dir, a.ano, a.uf)
    memo: dict[str, object] = {}
    feitos: dict[int, str | None] = {}
    for turno in (1, 2):
        try:
            alvo = nivel(a, turno, com)
        except md.PoliticaIndisponivel as exc:
            logger.error("%sº turno: %s", turno, exc)
            feitos[turno] = totais_importados(a, turno)
            continue
        atual = totais_importados(a, turno)
        insumos = md.PARA_IMPORTAR | {md.BWEB} if alvo == "bweb" else md.PARA_IMPORTAR
        fixa = _politica(a) != "auto"
        # rodada 59: a versão de um arquivo usado mudou desde a importação — inclusive baixado por OUTRA UF (os
        # munzona são nacionais) ou por outro processo; importação antiga, sem o registro, é refeita uma vez
        defasada = alvo == atual and alvo is not None and insumos_importados(a, turno) != md.insumos_atuais(
            a.cache_dir, a.ano, a.uf, turno)
        if alvo and (md.ORDEM[alvo] > md.ORDEM[atual] or (alvo == atual and (mudaram & insumos or defasada))
                     or (fixa and alvo != atual)):
            importar(a, alvo, turno, memo)
        feitos[turno] = totais_importados(a, turno)
    return feitos


def importar(a: argparse.Namespace, totais_de: str, turno: int, memo: dict | None = None) -> bool:
    """Importa um turno para dados_2026/historico_<ano>_t<turno> (na pasta da UF). Ao trocar totais
    provisórios por outros, grava a conferência entre os dois em <saidas>/. `memo` guarda o detalhe dos
    níveis "munzona"/"secoes" (traz os dois turnos: carregado uma vez por verificação)."""
    from apuracao import historico
    memo = {} if memo is None else memo
    destino = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf)  # cada UF na sua pasta
    antes_de = totais_importados(a, turno)
    mesmo_nivel = antes_de == totais_de
    antes = (_totais_provisorios(destino) if antes_de not in (None, totais_de)
             else _totais_atuais(destino) if mesmo_nivel else None)
    try:
        if totais_de == "bweb":
            detalhe = None  # por turno, do BU (historico.load_detalhe_bweb)
        elif totais_de in memo:
            detalhe = memo[totais_de]
        else:
            detalhe = memo[totais_de] = (historico.load_detalhe(a.ano, a.cache_dir) if totais_de == "munzona"
                                         else historico.load_detalhe_secoes(a.ano, a.uf, a.cache_dir))
        n = historico.importar(a.ano, a.uf, turno, a.cache_dir, destino, totais_de=totais_de, detalhe=detalhe,
                               brasil=getattr(a, "bweb_brasil", False) and totais_de == "bweb")
    except (v.TseDataError, requests.RequestException) as exc:
        logger.info("%sº turno de %s ainda sem dados (%s): %s", turno, a.ano, totais_de, exc)
        return False
    logger.info("resultado de %s (%sº turno, totais %s) importado em %s: %s", a.ano, turno,
                historico.DESCRICAO_TOTAIS[totais_de], destino, n)
    conferir_com_a_noite(a, turno, destino)
    if antes is not None:
        conf = historico.conferir_totais(antes, pl.read_parquet(destino / "ultimo" / "totais.parquet"))
        a.saidas.mkdir(parents=True, exist_ok=True)
        if mesmo_nivel:  # o TSE regerou um arquivo: o que mudou nos totais (rodada 59)
            alvo = a.saidas / f"conferencia_atualizacao_{datetime.now():%Y%m%d_%H%M}_{turno}t.csv"
            conf.write_csv(alvo, separator=";")
            logger.info("reimportado (%sº turno: arquivo regerado pelo TSE, ou importação sem o registro): %s", turno,
                        f"{conf.height} linhas dos totais mudaram → {alvo}" if conf.height
                        else "nenhum total mudou")
        else:
            alvo = a.saidas / f"conferencia_{antes_de}_x_{totais_de}_{turno}t.csv"
            conf.write_csv(alvo, separator=";")
            logger.info("totais %s × %s (%sº turno): %d linhas com diferença → %s", antes_de, totais_de, turno,
                        conf.height, alvo)
    if antes_de == "bweb" and totais_de != "bweb":  # o BU deixou de ser a fonte: os Parquet dele saem
        from apuracao import bweb
        zp = bweb.no_cache(a.cache_dir, a.ano, turno, a.uf)
        for d in bweb.derivados(zp) if zp else []:
            d.unlink(missing_ok=True)
    return True


def procurar_bu(a: argparse.Namespace, sessao=requests, lista: list | None = None) -> set[str]:
    """Boletim de Urna dos turnos em que nada melhor existe (ou com `--politica-totais bweb`): uma chamada ao
    CKAN (`lista`, se já consultada); com `--bweb-brasil`, os 27 + exterior. Devolve {md.BWEB} se chegou BU
    novo."""
    from apuracao import bweb
    com = md.no_cache(a.cache_dir, a.ano, a.uf)
    turnos = [t for t in (1, 2) if _politica(a) == "bweb"
              or (_politica(a) == "auto" and not [n for n in md.niveis_disponiveis(a.cache_dir, a.ano, a.uf, t, com)
                                                  if n != "bweb"])]
    if not turnos or "candidatos" not in com:
        return set()
    lista = bweb.recursos(a.ano, sessao) if lista is None else lista
    ufs = [a.uf.upper()]
    if getattr(a, "bweb_brasil", False):
        from apuracao.ufs import UFS
        ufs = list(dict.fromkeys([a.uf.upper(), *UFS, bweb.EXTERIOR]))
    chegou = set()
    for turno in turnos:
        for uf in ufs:
            recurso = bweb.escolher(lista, turno, uf)
            if recurso is None:
                continue
            ja = bweb.no_cache(a.cache_dir, a.ano, turno, uf)
            if ja is not None and ja.name == recurso.nome:
                continue
            try:
                bweb.baixar(recurso, a.cache_dir, sessao)
            except (v.TseDataError, requests.RequestException) as exc:
                logger.error("Boletim de Urna %s: %s (tento de novo na próxima verificação)", recurso.nome, exc)
                continue
            chegou.add(md.BWEB)
    return chegou


def conferir_com_a_noite(a: argparse.Namespace, turno: int, importado: Path) -> None:
    """Tempo real (o que o coletor gravou na noite) × o recém-importado — `saidas/conferencia_<ano>_t<turno>.xlsx`
    (TODO 16, rodada 45). Sem a pasta da noite, nada a conferir."""
    from apuracao import conferencia as cf
    from apuracao.divulgacao.coletor import destino_padrao
    from apuracao.ufs import tem_dados
    noite = dir_uf(destino_padrao("oficial", a.raiz, turno), a.uf)
    if not tem_dados(noite):
        return
    try:
        c = cf.conferir(noite, importado, a.uf)
        saida = cf.para_planilha(c, a.saidas / f"conferencia_{a.ano}_t{turno}.xlsx")
    except Exception:  # a conferência nunca impede a importação
        logger.exception("conferência com a noite falhou")
        return
    logger.info("conferência tempo real × importado (%sº turno): %s — %s", turno,
                "tudo igual" if c.ok else f"{c.totais.height} totais e {c.candidatos.height} candidatos diferentes",
                saida)


def totais_importados(a: argparse.Namespace, turno: int = 1) -> str | None:
    """"munzona"/"secoes"/"bweb" conforme o status.json do turno importado; None se ainda não importado."""
    import json
    st = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf) / "status.json"
    if not st.exists():
        return None
    dados = json.loads(st.read_text())
    return dados.get("totais_de", "munzona") if dados.get("ano") == a.ano else None


def garantir_importacao(a: argparse.Namespace) -> str | None:
    """Importa o que o cache permite e ainda não foi importado (nada → BU → seções → oficial, por turno). Cobre
    o que chegou numa execução que não importou (versão antiga do gatilho, queda no meio). Devolve os totais
    do 1º turno importados depois disso."""
    return atualizar(a)[1]


def insumos_importados(a: argparse.Namespace, turno: int = 1) -> dict[str, str] | None:
    """As versões dos arquivos usados na importação do turno (status.json `insumos`); None se não registrado."""
    import json
    st = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf) / "status.json"
    try:
        dados = json.loads(st.read_text())
    except (OSError, ValueError):
        return None
    return dados.get("insumos") if dados.get("ano") == a.ano else None


def _totais_atuais(destino: Path) -> pl.DataFrame | None:
    tot = destino / "ultimo" / "totais.parquet"
    return pl.read_parquet(tot) if tot.exists() else None


def _totais_provisorios(destino: Path) -> pl.DataFrame | None:
    """Os totais de uma importação anterior com totais reconstruídos (para conferir com os oficiais)."""
    import json
    st, tot = destino / "status.json", destino / "ultimo" / "totais.parquet"
    if not (st.exists() and tot.exists()) or json.loads(st.read_text()).get("totais_de") not in ("secoes", "bweb"):
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


def resumo(a: argparse.Namespace, estados: list[md.Estado], bus: dict | None = None) -> list[str]:
    """O que a verificação significa para a importação (sem baixar nada). `bus`: turno → BU listado no CKAN."""
    bus = bus or {}
    nomes = {x.chave: x.zip(a.ano, a.uf) for x in md.ARQUIVOS}
    fora = [e.zip for e in estados if e.http == 404]
    novos = [e.zip for e in estados if e.acao in ("baixar", "baixar de novo")]
    cache = md.no_cache(a.cache_dir, a.ano, a.uf)
    linhas = [f"ainda não publicados no TSE (404): {', '.join(fora) or 'nenhum'}",
              f"publicados e ainda não baixados (ou atualizados pelo TSE): {', '.join(novos) or 'nenhum'}"
              + (" — rode sem --so-verificar para baixar e importar" if novos else "")]
    for turno in (1, 2):
        disp = md.niveis_disponiveis(a.cache_dir, a.ano, a.uf, turno, cache)
        linhas.append(f"{turno}º turno — importado: {historico_descricao(totais_importados(a, turno))}; "
                      f"no cache dá para: {', '.join(disp) or 'nada'}; votos por partido: "
                      f"{md.fonte_dos_partidos(a.cache_dir, a.ano, a.uf, turno, cache) or 'divulgação'}"
                      + (f"; Boletim de Urna no CKAN: {bu.nome}" if (bu := bus.get(turno)) else "")
                      + _situacao_insumos(a, turno))
    faltam = sorted(nomes[c] for c in md.FINAL - cache)
    if faltam:
        linhas.append(f"para os totais oficiais ainda falta no cache: {', '.join(faltam)}")
    return linhas


def _situacao_insumos(a: argparse.Namespace, turno: int) -> str:
    if totais_importados(a, turno) is None:
        return ""
    gravados, atuais = insumos_importados(a, turno), md.insumos_atuais(a.cache_dir, a.ano, a.uf, turno)
    if gravados is None:
        return "; arquivos da importação: sem registro (reimporta na próxima execução)"
    mudaram = sorted(k for k in set(gravados) | set(atuais) if gravados.get(k) != atuais.get(k))
    return "; arquivos da importação: em dia" if not mudaram else f"; arquivos mudaram desde a importação: {', '.join(mudaram)}"


def historico_descricao(totais_de: str | None) -> str:
    return {None: "nada", "secoes": "sim, com totais PROVISÓRIOS (reconstruídos das seções)",
            "bweb": "sim, com totais PROVISÓRIOS (reconstruídos do Boletim de Urna)",
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
        from apuracao import bweb
        lista = bweb.recursos(a.ano, sessao)  # uma consulta ao CKAN (sem baixar)
        print("\n".join(resumo(a, estados, {t: bweb.escolher(lista, t, a.uf) for t in (1, 2)})))
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
            if procurar_bu(a, sessao):
                atualizar(a, {md.BWEB})
            garantir_importacao(a)
        # encerra só com o que a importação DEFINITIVA usa (totais oficiais): antes disso a importação, se
        # houver, é a provisória, e o vigia precisa seguir para trocá-la pela oficial quando o TSE publicar
        pronto = md.FINAL <= md.no_cache(a.cache_dir, a.ano, a.uf)
        if a.acompanhar:  # rodada 59: depois dos oficiais, segue de olho nas regerações do TSE
            if a.ate and date.today() > a.ate:
                print(f"acompanhamento encerrado (--ate {a.ate:%Y-%m-%d}).")
                return 0
            pausa = max(a.intervalo_final, 3600) if pronto else intervalo
            logger.info("próxima verificação em %.0f min%s", pausa / 60, " (totais oficiais: acompanhando)" if pronto else "")
            time.sleep(pausa)
            continue
        if not a.vigiar or pronto:
            if a.vigiar:
                print("microdados de", a.ano, "completos (com os totais oficiais) e preparados; vigia encerrado.")
            return 0
        logger.info("próxima verificação em %.0f min", intervalo / 60)
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
