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
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

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
    """"munzona" (oficiais), "secoes" (reconstruídos, provisórios) ou None (ainda não dá para importar)."""
    if BASE_IMPORTAR | TOTAIS_OFICIAIS <= com_dados:
        return "munzona"
    if BASE_IMPORTAR | TOTAIS_DE_SECOES <= com_dados:
        return "secoes"
    return None


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


def baixar(url: str, destino: Path, sessao: Any = requests) -> Path:
    """Baixa para um diretório temporário e troca o ZIP (e a proveniência) de forma atômica."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino.parent) as tmp:
        parcial = Path(tmp) / destino.name
        with sessao.get(url, headers=v.HTTP_HEADERS, stream=True, timeout=(30, 600)) as r:
            if r.status_code == 404:
                raise v.TseDataError(f"404 em {url}")
            r.raise_for_status()
            sha, n = hashlib.sha512(), 0
            with parcial.open("wb") as fh:
                for bloco in r.iter_content(chunk_size=4 * 1024 * 1024):
                    fh.write(bloco)
                    sha.update(bloco)
                    n += len(bloco)
            prov = {"url": url, "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "last_modified": r.headers.get("Last-Modified"), "bytes": n, "sha512": sha.hexdigest()}
        parcial.replace(destino)
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
            zp = baixar(e.url, cache / e.zip, sessao)
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

