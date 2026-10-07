"""Vigia e preparo dos microdados de 2026 (item 4 do TODO).

O TSE publica os microdados por seção dias depois do pleito, e antes disso alguns arquivos JÁ
EXISTEM na CDN só com o cabeçalho (em 30/09/2026: `detalhe_votacao_munzona_2026`,
`votacao_candidato_munzona_2026` e `votacao_partido_munzona_2026`, com 671 bytes por UF). Por isso:

- publicado = o CSV da UF tem pelo menos uma linha de dados, e não apenas "a URL responde 200";
- o TSE REGERA os arquivos (retotalizações, correções). A cada verificação compara o
  `Last-Modified` da CDN com o do download (`<zip>.proveniencia.json`) e baixa de novo quando muda,
  trocando o ZIP de forma atômica e apagando os Parquet derivados (senão o cache ficaria com a
  versão vazia para sempre: `votos_por_local_votacao.download` nunca baixa de novo o que já existe);
- uma verificação = um HEAD por arquivo (8 pedidos), feita no máximo a cada hora pelo vigia.

Quando os dados chegam: converte para Parquet (o que os mapas por bairro, a comparação e o Perfil ×
voto usam, sem intervenção), importa o resultado oficial para `dados_2026/historico_2026_t<turno>/`
(o mesmo formato do coletor: o site abre com --dados) e, com os votos por seção, calcula a primeira
análise: a transferência 2022 → 2026 por bairro. A importação usa os totais oficiais
(`detalhe_votacao_munzona`) ou, até ele sair, os reconstruídos das seções (`fonte_dos_totais`), e é
refeita quando um arquivo dela muda — o oficial chegando substitui o provisório (rodada 40).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

import polars as pl
import requests

import votos_por_local_votacao as v

logger = logging.getLogger("apuracao.microdados")

ESTADO = "microdados_{ano}.json"


@dataclass(frozen=True)
class Arquivo:
    chave: str
    pasta: str
    nome: str          # modelo do ZIP: {ano}, {uf}
    membro: str        # sufixo do CSV onde procurar dados: "_{uf}.csv", "_BRASIL.csv" ou "" (único CSV)
    para: str          # o que depende dele (texto para o relatório)

    def zip(self, ano: int, uf: str) -> str:
        return self.nome.format(ano=ano, uf=uf.upper())

    def url(self, ano: int, uf: str) -> str:
        return f"{v.CDN_BASE}/{self.pasta}/{self.zip(ano, uf)}"


ARQUIVOS = [
    Arquivo("votos_uf", "votacao_secao", "votacao_secao_{ano}_{uf}.zip", "_{uf}.csv",
            "mapas e comparação por bairro, Perfil × voto, planilhas, transferência 2022 → 2026"),
    Arquivo("votos_br", "votacao_secao", "votacao_secao_{ano}_BR.zip", "",
            "Presidente por seção (bairros, perfil, histórico)"),
    Arquivo("detalhe_secao", "detalhe_votacao_secao", "detalhe_votacao_secao_{ano}.zip", "_BRASIL.csv",
            "abstenção/comparecimento por bairro; hora de cada seção (recalibrar projeções com 2026)"),
    Arquivo("detalhe_munzona", "detalhe_votacao_munzona", "detalhe_votacao_munzona_{ano}.zip", "_{uf}.csv",
            "totais oficiais (importar o resultado de 2026 para o site)"),
    Arquivo("candidatos", "consulta_cand", "consulta_cand_{ano}.zip", "_{uf}.csv",
            "nomes e situação dos candidatos (importar o resultado)"),
    Arquivo("candidato_munzona", "votacao_candidato_munzona", "votacao_candidato_munzona_{ano}.zip", "_{uf}.csv",
            "eleitos oficiais e destinação dos votos (conferir as cadeiras)"),
    Arquivo("partido_munzona", "votacao_partido_munzona", "votacao_partido_munzona_{ano}.zip", "_{uf}.csv",
            "votos válidos por partido (cadeiras oficiais)"),
    Arquivo("perfil", "perfil_eleitor_secao", "perfil_eleitor_secao_{ano}_{uf}.zip", "_{uf}.csv",
            "perfil do eleitorado por seção (Perfil × voto)"),
]
# Importar o resultado oficial (historico.importar) precisa dos votos, do cadastro e dos TOTAIS: os oficiais
# (detalhe_munzona) ou, enquanto ele não sai, os reconstruídos das seções (detalhe por seção + destinação de
# cada candidato no candidato_munzona; rodada 40 — iguais ao oficial nas 732 zonas × cargo do RJ 2022).
BASE_IMPORTAR = frozenset({"votos_uf", "votos_br", "candidatos"})
TOTAIS_OFICIAIS = frozenset({"detalhe_munzona"})
TOTAIS_DE_SECOES = frozenset({"detalhe_secao", "candidato_munzona"})
PARA_IMPORTAR = BASE_IMPORTAR | TOTAIS_OFICIAIS | TOTAIS_DE_SECOES  # o que, ao mudar, pede nova importação
# o vigia só encerra com o que a importação DEFINITIVA usa (totais oficiais e votos de partido das cadeiras)
FINAL = BASE_IMPORTAR | TOTAIS_OFICIAIS | {"partido_munzona"}


def fonte_dos_totais(com_dados: set[str]) -> str | None:
    """"munzona" (oficiais), "secoes" (reconstruídos, provisórios) ou None (ainda não dá para importar), só
    pelos arquivos presentes (sem olhar o turno: ver `niveis_disponiveis`)."""
    if BASE_IMPORTAR | TOTAIS_OFICIAIS <= com_dados:
        return "munzona"
    if BASE_IMPORTAR | TOTAIS_DE_SECOES <= com_dados:
        return "secoes"
    return None


# --------------------------------------------------------------------------
# Nível dos totais por turno (rodada 55): munzona > secoes > bweb > None, sem rebaixar
# --------------------------------------------------------------------------
ORDEM: dict[str | None, int] = {None: 0, "bweb": 1, "secoes": 2, "munzona": 3}
POLITICAS: dict[str, str | None] = {"auto": None, "oficial": "munzona", "secoes": "secoes", "bweb": "bweb"}
BWEB = "bweb"  # chave de "mudou" quando chega um Boletim de Urna novo (não está em ARQUIVOS: nome com carimbo)


class PoliticaIndisponivel(v.TseDataError):
    """`--politica-totais` fixa um nível que o cache ainda não permite (nunca cai para outro sozinha)."""


def turnos(cache: Path, ano: int, uf: str, chave: str) -> set[int]:
    """Turnos com linhas DA UF no arquivo: o 1º turno nos arquivos do ano não significa o 2º (o TSE só
    acrescenta o 2º turno dias depois). "votos" = votacao_secao da UF ∪ do BR (Presidente); "detalhe_secao";
    "detalhe_munzona" (o CSV _BRASIL: o da UF não tem o Presidente). Ilegível ou ausente → vazio."""
    try:
        if chave == "votos":
            partes = [v.load_section_votes(ano, uf, cargo, cache, False) for cargo, arq in
                      (("governador", "votos_uf"), ("presidente", "votos_br"))
                      if (cache / next(a for a in ARQUIVOS if a.chave == arq).zip(ano, uf)).exists()]
            lf = pl.concat([p.select("SG_UF", "NR_TURNO") for p in partes]) if partes else None
        elif chave == "detalhe_secao":
            lf = v.load_section_details(ano, uf, cache).select("SG_UF", "NR_TURNO")
        elif chave == "detalhe_munzona":
            from apuracao import historico
            lf = historico.load_detalhe(ano, cache).lazy().select("SG_UF", pl.col("NR_TURNO").cast(pl.Int64))
        else:
            raise ValueError(f"chave sem turnos: {chave}")
        if lf is None:
            return set()
        return set(lf.filter(pl.col("SG_UF") == uf.upper()).select(pl.col("NR_TURNO").unique())
                   .collect()["NR_TURNO"].drop_nulls().to_list())
    except (v.TseDataError, requests.RequestException, OSError, pl.exceptions.PolarsError,
            zipfile.BadZipFile) as exc:
        logger.debug("turnos de %s (%s %s) indisponíveis: %s", chave, ano, uf, exc)
        return set()


def niveis_disponiveis(cache: Path, ano: int, uf: str, turno: int, com_dados: set[str] | None = None) -> list[str]:
    """Os níveis de totais que o cache permite PARA O TURNO, do melhor para o pior:
      munzona: detalhe munzona com linhas do turno + votos e cadastro;
      secoes:  votos e detalhe por seção com linhas do turno + cadastro + destinação (candidato_munzona);
      bweb:    Boletim de Urna do turno com SHA-512 conferido + cadastro."""
    from apuracao import bweb

    com = no_cache(cache, ano, uf) if com_dados is None else com_dados
    saida = []
    if BASE_IMPORTAR | TOTAIS_OFICIAIS <= com and turno in turnos(cache, ano, uf, "detalhe_munzona"):
        saida.append("munzona")
    if (BASE_IMPORTAR | TOTAIS_DE_SECOES <= com and turno in turnos(cache, ano, uf, "votos")
            and turno in turnos(cache, ano, uf, "detalhe_secao")):
        saida.append("secoes")
    if "candidatos" in com and bweb.no_cache(cache, ano, turno, uf) is not None:
        saida.append("bweb")
    return saida


def escolher_nivel(disponiveis: list[str], politica: str = "auto") -> str | None:
    """`auto`: o melhor disponível (ou None). Política fixa: aquele nível, ou `PoliticaIndisponivel`."""
    if politica not in POLITICAS:
        raise ValueError(f"política desconhecida: {politica} (use {', '.join(POLITICAS)})")
    alvo = POLITICAS[politica]
    if alvo is None:
        return disponiveis[0] if disponiveis else None
    if alvo not in disponiveis:
        raise PoliticaIndisponivel(f"totais \"{alvo}\" pedidos (--politica-totais {politica}), mas o cache não tem "
                                   f"o necessário (disponível: {', '.join(disponiveis) or 'nada'})")
    return alvo


def fonte_dos_partidos(cache: Path, ano: int, uf: str, turno: int, com_dados: set[str] | None = None) -> str | None:
    """De onde viriam os votos por partido das cadeiras: o votacao_partido_munzona oficial; senão o
    candidato_munzona + a legenda das seções ("secoes") ou do BU ("bweb"); senão None (divulgação)."""
    from apuracao import bweb

    com = no_cache(cache, ano, uf) if com_dados is None else com_dados
    if "partido_munzona" in com:
        return "munzona"
    if "candidato_munzona" not in com:
        return None
    if {"votos_uf", "votos_br"} & com and turno in turnos(cache, ano, uf, "votos"):
        return "secoes"
    return "bweb" if bweb.no_cache(cache, ano, turno, uf) is not None else None


@dataclass
class Estado:
    chave: str
    zip: str
    url: str
    http: int | None = None                # status do HEAD
    remoto_modificado: str | None = None   # Last-Modified da CDN
    remoto_bytes: int | None = None
    local_modificado: str | None = None    # Last-Modified gravado no download
    tem_dados: bool | None = None          # None = ainda não inspecionado
    situacao: str = ""                     # não publicado | só cabeçalho | com dados | ...
    acao: str = ""


def _data(texto: str | None) -> datetime | None:
    try:
        return parsedate_to_datetime(texto) if texto else None
    except (TypeError, ValueError):
        return None


def _proveniencia(cache: Path, nome_zip: str) -> dict[str, Any]:
    p = (cache / nome_zip).with_suffix(".proveniencia.json")
    return json.loads(p.read_text()) if p.exists() else {}


def tem_dados(zp: Path, membro: str) -> bool:
    """O CSV escolhido tem pelo menos uma linha além do cabeçalho?"""
    with zipfile.ZipFile(zp) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        alvo = [n for n in csvs if membro and n.upper().endswith(membro.upper())] or csvs
        for nome in alvo[:1]:
            with z.open(nome) as fh:
                texto = io.TextIOWrapper(fh, encoding="latin-1")
                texto.readline()
                return bool(texto.readline().strip())
    return False


def verificar(cache: Path, ano: int, uf: str, sessao: Any = requests) -> list[Estado]:
    """Um HEAD por arquivo; compara com o que está no cache (sem baixar nada)."""
    saida = []
    for a in ARQUIVOS:
        e = Estado(a.chave, a.zip(ano, uf), a.url(ano, uf))
        try:
            r = sessao.head(e.url, headers=v.HTTP_HEADERS, timeout=30, allow_redirects=True)
            e.http = r.status_code
            e.remoto_modificado = r.headers.get("Last-Modified")
            e.remoto_bytes = int(r.headers["Content-Length"]) if r.headers.get("Content-Length") else None
        except requests.RequestException as exc:
            e.situacao, e.acao = f"erro de rede ({exc.__class__.__name__})", "tentar de novo"
            saida.append(e)
            continue
        prov = _proveniencia(cache, e.zip)
        e.local_modificado = prov.get("last_modified")
        local = cache / e.zip
        if e.http == 404:
            e.situacao = "não publicado"
            e.acao = "esperar"
        elif e.http != 200:
            e.situacao, e.acao = f"HTTP {e.http}", "tentar de novo"
        elif not local.exists():
            e.situacao, e.acao = "publicado, fora do cache", "baixar"
        elif (_data(e.remoto_modificado) or datetime.min.replace(tzinfo=timezone.utc)) > (
                _data(e.local_modificado) or datetime.min.replace(tzinfo=timezone.utc)):
            e.situacao, e.acao = "o TSE atualizou o arquivo", "baixar de novo"
        else:
            e.tem_dados = tem_dados(local, a.membro.format(uf=uf.upper()))
            e.situacao = "com dados, em dia" if e.tem_dados else "só cabeçalho (sem votos ainda), em dia"
            e.acao = "nada"
        saida.append(e)
    return saida


RETOMADAS = 5          # tentativas de continuar um download que caiu, dentro da mesma verificação
PAUSA_RETOMADA_S = 5.0
BLOCO = 4 * 1024 * 1024


def _parcial(destino: Path) -> tuple[Path, Path]:
    """O download em andamento (`<zip>.parcial`) e a versão a que ele pertence (`<zip>.parcial.json`)."""
    return destino.with_name(destino.name + ".parcial"), destino.with_name(destino.name + ".parcial.json")


def _descartar(destino: Path) -> None:
    for f in _parcial(destino):
        f.unlink(missing_ok=True)


def _get(url: str, pedido: str, destino: Path, sessao: Any) -> dict[str, Any]:
    """Um GET de `pedido` para `<destino>.parcial`, CONTINUANDO o que já está lá se for da mesma versão: pede só
    o que falta (`Range`) com `If-Range` = a versão do parcial — se o TSE trocou o arquivo, o servidor manda o
    arquivo inteiro (200) e o parcial recomeça. Devolve a proveniência (com a `url` sem parâmetros)."""
    parcial, meta = _parcial(destino)
    versao = None
    if parcial.exists() and meta.exists():
        try:
            versao = json.loads(meta.read_text()).get("last_modified")
        except (OSError, ValueError):
            versao = None
    inicio = parcial.stat().st_size if versao and parcial.exists() else 0
    headers = dict(v.HTTP_HEADERS)
    if inicio:
        headers.update({"Range": f"bytes={inicio}-", "If-Range": versao})
    with sessao.get(pedido, headers=headers, stream=True, timeout=(30, 600)) as r:
        if r.status_code == 404:
            raise v.TseDataError(f"404 em {pedido}")
        if r.status_code == 416:  # o parcial já tem tudo (ou é maior que o arquivo): recomeça
            _descartar(destino)
            raise requests.ConnectionError("intervalo pedido fora do arquivo; recomeçando")
        r.raise_for_status()
        continua = inicio and r.status_code == 206 and str(r.headers.get("Content-Range", "")).startswith(
            f"bytes {inicio}-")
        lm = versao if continua else r.headers.get("Last-Modified")
        if not continua:
            inicio = 0
            meta.write_text(json.dumps({"url": url, "last_modified": lm}))
        else:
            logger.info("%s: continuando o download de %.0f MB", destino.name, inicio / 1e6)
        with parcial.open("ab" if continua else "wb") as fh:
            for bloco in r.iter_content(chunk_size=BLOCO):
                fh.write(bloco)
    sha, n = hashlib.sha512(), 0
    with parcial.open("rb") as fh:  # o SHA do arquivo inteiro (o que veio antes e o que veio agora)
        while bloco := fh.read(BLOCO):
            sha.update(bloco)
            n += len(bloco)
    return {"url": url, "downloaded_at": datetime.now(timezone.utc).isoformat(), "last_modified": lm, "bytes": n,
            "sha512": sha.hexdigest()}


def _get_com_retomada(url: str, pedido: str, destino: Path, sessao: Any) -> dict[str, Any]:
    """`_get`, continuando de onde parou quando a conexão cai (até `RETOMADAS` vezes). Se ainda falhar, o parcial
    FICA no cache e a próxima verificação continua dele (06/10/2026: o votacao_secao do RJ, 290 MB, caiu duas vezes
    no meio e era pedido inteiro de novo)."""
    for tentativa in range(1, RETOMADAS + 1):
        try:
            return _get(url, pedido, destino, sessao)
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
            if tentativa == RETOMADAS:
                raise
            feito = _parcial(destino)[0].stat().st_size if _parcial(destino)[0].exists() else 0
            logger.warning("%s: conexão caiu com %.0f MB (%s); continuando (%d/%d)", destino.name, feito / 1e6,
                           exc.__class__.__name__, tentativa, RETOMADAS - 1)
            time.sleep(PAUSA_RETOMADA_S)
    raise AssertionError("inalcançável")


def baixar(url: str, destino: Path, sessao: Any = requests, esperado: str | None = None,
           sha512: str | None = None) -> Path:
    """Baixa para `<destino>.parcial` (continuando um download interrompido da mesma versão) e troca o ZIP (e a
    proveniência) de forma atômica.

    `esperado` = Last-Modified que o HEAD anunciou. A CDN do TSE tem nós com cópias velhas: em 07/10/2026 o
    HEAD dizia 06/10 19:22 e o GET entregava a versão de 04:58 (e o vigia baixaria tudo de novo a cada hora,
    gravando a velha como nova). GET mais velho que o HEAD é repetido UMA vez com um parâmetro que fura o
    cache da CDN; se ainda vier velho, é recusado (`TseDataError`: o arquivo fica para a próxima verificação).
    Um parcial de versão diferente da anunciada é descartado antes de começar.
    `sha512`: o publicado pelo TSE (BU, `.sha512` ao lado do ZIP); divergente → recusado sem tocar no cache."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    minimo = _data(esperado)
    parcial, meta = _parcial(destino)
    if parcial.exists() and esperado:  # parcial de outra versão: não serve
        try:
            antiga = json.loads(meta.read_text()).get("last_modified") if meta.exists() else None
        except (OSError, ValueError):
            antiga = None
        if antiga != esperado:
            _descartar(destino)
    for pedido in (url, f"{url}?v={int(datetime.now(timezone.utc).timestamp())}"):
        prov = _get_com_retomada(url, pedido, destino, sessao)
        recebido = _data(prov["last_modified"])
        if minimo is None or (recebido is not None and recebido >= minimo):
            break
        logger.warning("%s: a CDN entregou a versão de %s, o HEAD anuncia %s", destino.name,
                       prov["last_modified"], esperado)
        _descartar(destino)
    else:
        raise v.TseDataError(f"a CDN ainda entrega a versão de {prov['last_modified']} (o HEAD anuncia {esperado})")
    if sha512 is not None and prov["sha512"] != sha512.strip().lower():
        _descartar(destino)
        raise v.TseDataError(f"SHA-512 de {destino.name} não confere com o publicado pelo TSE")
    parcial.replace(destino)
    meta.unlink(missing_ok=True)
    destino.with_suffix(".proveniencia.json").write_text(json.dumps(prov, indent=2))
    return destino


def derivados(cache: Path, nome_zip: str) -> list[Path]:
    """Parquet (e CSV temporários) gerados a partir do ZIP: precisam sair quando o ZIP muda."""
    stem = nome_zip.removesuffix(".zip")
    return sorted(cache.glob(f"{stem}__*.parquet")) + sorted(cache.glob(f"{stem}.utf8.csv"))


def preparar(cache: Path, ano: int, uf: str, sessao: Any = requests,
             ao_chegar: Callable[[set[str]], None] | None = None) -> list[Estado]:
    """Verifica, baixa o que é novo ou foi atualizado e, se há dados, apaga os Parquet derivados e
    avisa `ao_chegar` com as chaves que passaram a ter dados (ou mudaram) nesta rodada. Uma falha de rede num
    arquivo não perde os outros: ele fica "tentar de novo" (`com_erro`) e a reação roda com o que chegou."""
    estados = verificar(cache, ano, uf, sessao)
    mudaram: set[str] = set()
    por_chave = {a.chave: a for a in ARQUIVOS}
    for e in estados:
        if e.acao not in ("baixar", "baixar de novo"):
            continue
        a = por_chave[e.chave]
        try:
            zp = baixar(e.url, cache / e.zip, sessao, esperado=e.remoto_modificado)
        except (requests.RequestException, v.TseDataError) as exc:
            e.situacao, e.acao = f"falha no download ({exc.__class__.__name__}: {exc})"[:200], "tentar de novo"
            logger.error("%s: %s", e.zip, e.situacao)
            continue
        for d in derivados(cache, e.zip):
            d.unlink()
        e.local_modificado = _proveniencia(cache, e.zip).get("last_modified")
        e.tem_dados = tem_dados(zp, a.membro.format(uf=uf.upper()))
        e.situacao = "com dados (baixado agora)" if e.tem_dados else "só cabeçalho (sem votos ainda), baixado"
        e.acao = "baixado"
        logger.info("%s: %s", e.zip, e.situacao)
        if e.tem_dados:
            mudaram.add(e.chave)
    gravar_estado(cache, ano, estados)
    if mudaram and ao_chegar is not None:
        ao_chegar(mudaram)
    return estados


def gravar_estado(cache: Path, ano: int, estados: list[Estado]) -> Path:
    alvo = cache / ESTADO.format(ano=ano)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps({"verificado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "arquivos": [asdict(e) for e in estados]}, indent=2, ensure_ascii=False))
    tmp.replace(alvo)
    return alvo


def com_dados(estados: list[Estado]) -> set[str]:
    return {e.chave for e in estados if e.tem_dados}


def com_erro(estados: list[Estado]) -> list[Estado]:
    """Arquivos a pedir de novo na próxima verificação (erro de rede no HEAD ou no download, HTTP inesperado)."""
    return [e for e in estados if e.acao == "tentar de novo"]


INSUMOS = PARA_IMPORTAR | {"partido_munzona"}  # o que uma importação usa (rodada 59)


def insumos_atuais(cache: Path, ano: int, uf: str, turno: int) -> dict[str, str]:
    """Versão de cada arquivo do cache que uma importação de (ano, UF, turno) usa: nome do ZIP → `Last-Modified`
    gravado no download (o BU do turno: o SHA-512). A importação grava isto no status.json (`insumos`); se mudar,
    é preciso reimportar — mesmo que o download tenha sido feito por OUTRA UF (os munzona são nacionais) ou por
    outro processo (rodada 59: o TSE regerou o partido munzona três vezes em 07/10, depois dos totais oficiais)."""
    from apuracao import bweb

    saida = {}
    for a in ARQUIVOS:
        if a.chave in INSUMOS and (cache / a.zip(ano, uf)).exists():
            prov = _proveniencia(cache, a.zip(ano, uf))
            saida[a.zip(ano, uf)] = prov.get("last_modified") or prov.get("sha512") or ""
    zp = bweb.no_cache(cache, ano, turno, uf)
    if zp is not None:
        saida[zp.name] = bweb._proveniencia(zp).get("sha512") or ""
    return saida


def no_cache(cache: Path, ano: int, uf: str) -> set[str]:
    """Chaves cujo ZIP está no cache COM dados — o "já chegou" vem do disco, não da memória do processo
    (antes, uma execução nova esquecia o que a anterior baixou e não importava quando faltava só um arquivo)."""
    tem = set()
    for a in ARQUIVOS:
        zp = cache / a.zip(ano, uf)
        try:
            if zp.exists() and tem_dados(zp, a.membro.format(uf=uf.upper())):
                tem.add(a.chave)
        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("%s ilegível no cache: %s", zp.name, exc)
    return tem


def converter(cache: Path, ano: int, uf: str, chaves: set[str]) -> list[str]:
    """Converte para Parquet o que chegou (é o que os mapas por bairro, a comparação e o Perfil ×
    voto leem). Cada conversão é independente: uma falha não impede as outras."""
    feitos = []
    passos: list[tuple[str, Callable[[], Any]]] = []
    if "votos_uf" in chaves:
        passos.append(("votos por seção da UF", lambda: v.load_section_votes(ano, uf, "governador", cache, False)))
    if "votos_br" in chaves:
        passos.append(("votos por seção do Brasil (UF)", lambda: v.load_section_votes(ano, uf, "presidente", cache, False)))
    if "detalhe_secao" in chaves:
        passos.append(("detalhe por seção", lambda: v.load_section_details(ano, uf, cache)))
    if "perfil" in chaves:
        from apuracao import perfil as pf
        passos.append(("perfil do eleitorado", lambda: pf.load_perfil(ano, uf, cache)))
    for nome, passo in passos:
        try:
            passo()
            feitos.append(nome)
        except (v.TseDataError, OSError, ValueError) as exc:
            logger.error("falha ao converter %s: %s", nome, exc)
    return feitos


def limpar_cache_vazio(cache: Path, ano: int, uf: str) -> list[str]:
    """Apaga do cache ZIPs de `ano` que só têm cabeçalho (baixados antes da publicação por algum
    caminho que usa `download`): a próxima verificação os baixa de novo quando tiverem dados."""
    apagados = []
    for a in ARQUIVOS:
        zp = cache / a.zip(ano, uf)
        if zp.exists() and not tem_dados(zp, a.membro.format(uf=uf.upper())):
            for p in [zp, zp.with_suffix(".proveniencia.json"), *derivados(cache, zp.name)]:
                p.unlink(missing_ok=True)
            apagados.append(zp.name)
    return apagados

