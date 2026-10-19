"""Acervo das versões dos arquivos do TSE no cache (rodada 72).

O TSE regera arquivos no MESMO endereço: o cadastro de eleitorado de 2026 saiu em 29/09, em 06/10 (com os dois
turnos) e em 15/10 (com os locais temporários do 2º turno). O `download` do núcleo nunca baixa de novo o que já
existe, e trocar o ZIP à mão apagava a versão anterior — e com ela a chance de refazer uma análise com os dados
que ela usou. Aqui cada versão fica guardada em

    <cache>/versoes/<nome do ZIP sem .zip>/<carimbo>/
        <ZIP>                       link físico do ZIP do cache (cópia em outro sistema de arquivos), só leitura
        <nome>.proveniencia.json    a proveniência gravada no download (cópia exata)
        versao.json                 carimbo, geração do TSE, SHA-512 conferido, de onde veio e quando foi guardada

A pasta de uma versão tem o layout do cache: serve de `--cache-dir` (o Parquet derivado é gravado nela).

- `carimbo` = a geração do TSE (DT_GERACAO + HH_GERACAO da 1ª linha do CSV, horário de Brasília:
  "2026-10-15T143326"); sem ela, o Last-Modified da CDN em UTC ("2026-10-15T173758Z").
- Guardar é idempotente (mesmo SHA-512 = mesma versão) e recusa ZIP que não confere com a própria proveniência.
- O link físico não ocupa espaço enquanto o cache tem o mesmo arquivo, e a troca do cache (sempre por
  `replace`, de forma atômica) não o afeta. Só leitura porque link e cache são o MESMO arquivo: um `cp` por
  cima do ZIP do cache estragaria as duas cópias (o modo vale para os dois nomes).
- `atualizar` guarda a versão do cache, baixa a nova por `microdados.baixar` (troca atômica; cópia velha da CDN
  recusada), guarda a nova e apaga os Parquet derivados — só se o conteúdo mudou.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

import votos_por_local_votacao as v
from apuracao import microdados as md

logger = logging.getLogger("apuracao.versoes")

PASTA = "versoes"
FICHA = "versao.json"
BLOCO = 4 * 1024 * 1024
SO_LEITURA = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH


class VersaoDivergente(v.TseDataError):
    """O ZIP não confere com o SHA-512 da própria proveniência: não é guardado nem trocado."""


@dataclass(frozen=True)
class Versao:
    """Uma versão guardada no acervo (o conteúdo de `versao.json`)."""

    carimbo: str
    pasta: Path
    arquivo: str
    sha512: str
    bytes: int
    geracao_tse: str | None
    last_modified: str | None
    url: str | None
    baixado_em: str | None
    guardada_em: str

    @property
    def zip(self) -> Path:
        return self.pasta / self.arquivo

    def descricao(self) -> str:
        """"2026-10-15T143326 (gerada pelo TSE em 15/10/2026 14:33:26; CDN: Thu, 15 Oct 2026 17:37:58 GMT)"."""
        partes = [f"gerada pelo TSE em {self.geracao_tse}" if self.geracao_tse else None,
                  f"CDN: {self.last_modified}" if self.last_modified else None]
        detalhe = "; ".join(p for p in partes if p)
        return f"{self.carimbo} ({detalhe})" if detalhe else self.carimbo

    def para_consulta(self) -> dict[str, str]:
        """Os campos que identificam a versão, para a aba de parâmetros de uma planilha."""
        return {"versão do arquivo (carimbo)": self.carimbo, "geração do TSE": self.geracao_tse or "",
                "Last-Modified da CDN": self.last_modified or "", "baixado em": self.baixado_em or "",
                "SHA-512": self.sha512, "URL": self.url or "", "acervo": str(self.pasta)}


def acervo(cache: Path, nome_zip: str) -> Path:
    """Pasta das versões de um arquivo: `<cache>/versoes/<nome sem .zip>`."""
    return cache / PASTA / nome_zip.removesuffix(".zip")


def _proveniencia(zip_path: Path) -> Path:
    return zip_path.with_suffix(".proveniencia.json")


def _ler_json(p: Path) -> dict[str, Any]:
    try:
        dados = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _data(texto: str | None) -> datetime | None:
    try:
        return parsedate_to_datetime(texto) if texto else None
    except (TypeError, ValueError):
        return None


def sha512_de(p: Path) -> str:
    sha = hashlib.sha512()
    with p.open("rb") as fh:
        while bloco := fh.read(BLOCO):
            sha.update(bloco)
    return sha.hexdigest()


def geracao_tse(zip_path: Path) -> str | None:
    """DT_GERACAO + HH_GERACAO da 1ª linha de dados do 1º CSV do ZIP (ordem de nome); None se não houver."""
    with zipfile.ZipFile(zip_path) as zf:
        csvs = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
        if not csvs:
            return None
        with zf.open(csvs[0]) as raw:
            texto = io.TextIOWrapper(raw, encoding="latin-1")
            cabecalho = [c.strip().strip('"') for c in texto.readline().rstrip("\r\n").split(";")]
            linha = [c.strip().strip('"') for c in texto.readline().rstrip("\r\n").split(";")]
    campos = dict(zip(cabecalho, linha))
    if not campos.get("DT_GERACAO"):
        return None
    return f"{campos['DT_GERACAO']} {campos.get('HH_GERACAO', '')}".strip()


def carimbo(geracao: str | None, last_modified: str | None, modificado: datetime | None = None) -> str:
    """Nome da pasta da versão: a geração do TSE ("15/10/2026 14:33:26" → "2026-10-15T143326", horário de
    Brasília) ou, sem ela, o Last-Modified (ou a data do arquivo) em UTC com "Z".

    Raises:
        ValueError: sem nenhuma das três datas.
    """
    if geracao:
        try:
            return datetime.strptime(geracao, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%dT%H%M%S")
        except ValueError:
            logger.warning("geração do TSE em formato inesperado: %r", geracao)
    quando = _data(last_modified) or modificado
    if quando is None:
        raise ValueError("sem geração do TSE, Last-Modified nem data do arquivo para nomear a versão")
    return quando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def _ler_versao(pasta: Path) -> Versao | None:
    f = _ler_json(pasta / FICHA)
    if not f.get("sha512") or not f.get("arquivo"):
        return None
    return Versao(carimbo=pasta.name, pasta=pasta, arquivo=f["arquivo"], sha512=f["sha512"],
                  bytes=int(f.get("bytes") or 0), geracao_tse=f.get("geracao_tse"),
                  last_modified=f.get("last_modified"), url=f.get("url"), baixado_em=f.get("baixado_em"),
                  guardada_em=f.get("guardada_em", ""))


def listar(cache: Path, nome_zip: str) -> list[Versao]:
    """As versões guardadas de um arquivo, da mais antiga para a mais nova (ordem do carimbo)."""
    base = acervo(cache, nome_zip)
    if not base.is_dir():
        return []
    versoes = (_ler_versao(p) for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith("."))
    return [x for x in versoes if x is not None]


def escolher(cache: Path, nome_zip: str, texto: str) -> Versao:
    """A versão pelo carimbo completo ou por um prefixo dele que só uma versão tenha ("2026-10-06").

    Raises:
        TseDataError: nenhuma versão ou mais de uma com esse prefixo (a mensagem lista as que existem).
    """
    versoes = listar(cache, nome_zip)
    exata = [x for x in versoes if x.carimbo == texto]
    achadas = exata or [x for x in versoes if x.carimbo.startswith(texto)]
    if len(achadas) == 1:
        return achadas[0]
    existentes = ", ".join(x.carimbo for x in versoes) or "nenhuma"
    problema = "mais de uma versão começa com" if achadas else "nenhuma versão guardada com"
    raise v.TseDataError(f"{problema} '{texto}' para {nome_zip} (guardadas: {existentes})")


def _ligar(origem: Path, destino: Path) -> None:
    """Link físico (sem ocupar espaço); em outro sistema de arquivos, cópia. O resultado fica só leitura."""
    try:
        os.link(origem, destino)
    except OSError:
        shutil.copy2(origem, destino)
    destino.chmod(SO_LEITURA)


def guardar(zip_path: Path, cache: Path, origem: str | None = None) -> Versao:
    """Guarda a versão de `zip_path` (com a proveniência ao lado dele) no acervo de `cache`.

    Idempotente: a versão com o mesmo SHA-512 já guardada é devolvida sem gravar nada (nem recalcular o SHA,
    quando a proveniência já o traz). Dois conteúdos com o mesmo carimbo (a CDN republicou com a mesma geração)
    ficam lado a lado: o 2º ganha `_<8 primeiros dígitos do SHA>` no carimbo.

    Args:
        zip_path: o ZIP a guardar (do cache ou de uma cópia feita à mão).
        cache: o cache cujo acervo recebe a versão.
        origem: de onde a versão veio, para a ficha (padrão: o caminho do ZIP).

    Raises:
        FileNotFoundError: `zip_path` não existe.
        VersaoDivergente: o SHA-512 do ZIP difere do da proveniência.
    """
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    nome = zip_path.name
    prov = _ler_json(_proveniencia(zip_path))
    guardadas = listar(cache, nome)
    if prov.get("sha512"):
        for x in guardadas:
            if x.sha512 == prov["sha512"] and x.bytes == zip_path.stat().st_size:
                return x
    sha = sha512_de(zip_path)
    if prov.get("sha512") and prov["sha512"] != sha:
        raise VersaoDivergente(f"{zip_path}: o SHA-512 do arquivo não é o da proveniência "
                               f"({_proveniencia(zip_path).name}) — o ZIP foi trocado sem registro; confira antes "
                               "de guardar ou atualizar")
    for x in guardadas:
        if x.sha512 == sha:
            return x
    geracao = geracao_tse(zip_path)
    nome_versao = carimbo(geracao, prov.get("last_modified"),
                          datetime.fromtimestamp(zip_path.stat().st_mtime, timezone.utc))
    base = acervo(cache, nome)
    if (base / nome_versao).exists():
        nome_versao = f"{nome_versao}_{sha[:8]}"
    tmp = base / f".{nome_versao}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    _ligar(zip_path, tmp / nome)
    if prov:
        _proveniencia(tmp / nome).write_text(json.dumps(prov, indent=2, ensure_ascii=False))
    ficha = {"arquivo": nome, "sha512": sha, "bytes": zip_path.stat().st_size, "geracao_tse": geracao,
             "last_modified": prov.get("last_modified"), "url": prov.get("url"),
             "baixado_em": prov.get("downloaded_at") or prov.get("registrado_em"),
             "guardada_em": datetime.now(timezone.utc).isoformat(), "origem": origem or str(zip_path)}
    (tmp / FICHA).write_text(json.dumps(ficha, indent=2, ensure_ascii=False))
    tmp.rename(base / nome_versao)
    logger.info("versão guardada: %s", base / nome_versao)
    versao = _ler_versao(base / nome_versao)
    assert versao is not None  # acabou de ser gravada
    return versao


def proveniencia_no_cache(cache: Path, nome_zip: str) -> dict[str, Any]:
    """A proveniência do ZIP que está no cache ({} se não houver)."""
    return _ler_json(_proveniencia(cache / nome_zip))


def em_uso(cache: Path, nome_zip: str) -> Versao:
    """A versão do ZIP que está no cache, guardando-a no acervo se ainda não estiver (para refazer a análise depois).

    Raises:
        FileNotFoundError: o ZIP não está no cache.
        VersaoDivergente: o ZIP não confere com a proveniência.
    """
    return guardar(cache / nome_zip, cache, origem="cache (versão usada numa análise)")


@dataclass(frozen=True)
class Atualizacao:
    """Resultado de `atualizar`.

    `situacao`: "baixado" (não havia no cache), "atualizado", "em dia" ou "republicado sem mudança" (Last-Modified
    novo, conteúdo igual).
    """

    situacao: str
    atual: Versao
    anterior: Versao | None
    derivados_apagados: tuple[str, ...] = ()


def _mais_novo(remoto: str | None, local: str | None) -> bool:
    r, loc = _data(remoto), _data(local)
    if r is None:
        return False  # sem Last-Modified não dá para saber: só com `forcar`
    return loc is None or r > loc


def atualizar(spec: v.DatasetSpec, cache: Path, sessao: Any = requests, forcar: bool = False) -> Atualizacao:
    """Traz para o cache a versão do TSE mais nova que a do cache, sem perder a anterior.

    Um HEAD compara o Last-Modified da CDN com o da proveniência do cache. Se é mais novo (ou `forcar`): a versão
    do cache vai para o acervo, a nova é baixada (troca atômica do ZIP e da proveniência), guardada também, e os
    Parquet derivados saem (são refeitos no próximo uso) — se o conteúdo não mudou, ficam.

    Raises:
        TseDataError: HEAD diferente de 200, CDN entregando cópia velha ou ZIP do cache sem conferir com a
            proveniência (nada é trocado).
        requests.RequestException: falha de rede (nada é trocado).
    """
    local = cache / spec.zip_name
    anterior = guardar(local, cache, origem="cache antes da atualização") if local.exists() else None
    r = sessao.head(spec.url, headers=v.HTTP_HEADERS, timeout=30, allow_redirects=True)
    if r.status_code != 200:
        raise v.TseDataError(f"HTTP {r.status_code} em {spec.url}")
    remoto = r.headers.get("Last-Modified")
    no_cache = proveniencia_no_cache(cache, spec.zip_name).get("last_modified")
    if anterior is not None and not forcar and not _mais_novo(remoto, no_cache):
        return Atualizacao("em dia", anterior, anterior)
    md.baixar(spec.url, local, sessao, esperado=remoto)
    atual = guardar(local, cache, origem=spec.url)
    if anterior is not None and atual.sha512 == anterior.sha512:
        return Atualizacao("republicado sem mudança", atual, anterior)
    apagados = md.derivados(cache, spec.zip_name)
    for d in apagados:
        d.unlink()
    return Atualizacao("atualizado" if anterior else "baixado", atual, anterior, tuple(d.name for d in apagados))
