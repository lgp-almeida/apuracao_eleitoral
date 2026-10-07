"""Dados do IBGE: catálogo, descoberta de versão, verificação e atualização (rodada 34).

Malhas e agregados do Censo 2022 que os mapas por bairro/local, o Perfil × voto e a transferência
usam. Antes, cada módulo baixava a sua parte com uma URL fixa e nunca mais olhava o IBGE. Duas armadilhas:

- o IBGE REPUBLICA agregados com a data da versão no nome (`…basico_BR_20260520.zip`): uma URL fixa
  vira 404 e uma instalação nova quebra. Aqui a fonte guarda o MODELO do nome (`{versao}` = "" ou
  `_AAAAMMDD`) e a versão é descoberta no índice do diretório (o FTP lista por HTTPS);
- o cache nunca era renovado e os derivados (GeoJSON simplificado, Parquet do Censo) também não.

`caminho` é o que os módulos de domínio chamam: o arquivo mais novo do cache, sem rede; só se faltar,
descobre a versão e baixa uma vez (pelo `v.download`, que os testes trocam por "sem rede").
`verificar` (índices + HEAD, sem baixar) e `atualizar` (baixa, troca de forma atômica, refaz os
derivados e, se um derivado falhar com a versão nova, volta à anterior) são usados por `preparar_ibge.py`.
A malha municipal vem da API `servicodados`, que não aceita HEAD: só é conferida (GET + SHA-512) com
`forcar_api` ou depois de `IDADE_MAX_API_DIAS`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

import requests

import votos_por_local_votacao as v

logger = logging.getLogger("apuracao.ibge")

CENSO = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022"
GEOFTP_CD2022 = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
                 "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022")
API_MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{cod}"
             "?formato=application/vnd.geo%2Bjson&intrarregiao=municipio&qualidade=intermediaria")
API_MALHA_UFS = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
                 "?formato=application/vnd.geo%2Bjson&intrarregiao=UF&qualidade=minima")  # ~100 kB; codarea = UF
UF_IBGE = {"RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21, "PI": 22, "CE": 23,
           "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35,
           "PR": 41, "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53}
ESTADO = "ibge_estado.json"
IDADE_MAX_API_DIAS = 30
ANTERIOR = ".anterior"  # sufixo da versão guardada enquanto o derivado novo não fica pronto
_VERSAO = re.compile(r"\{versao\}")


@dataclass(frozen=True)
class Fonte:
    chave: str
    tipo: str          # "ftp": versão no nome, descoberta no índice | "fixo": nome sem versão (HEAD) | "api"
    diretorio: str     # URL do diretório ("ftp"/"fixo", com {uf}) ou da API (com {cod})
    modelo: str        # nome do arquivo; {versao} = "" ou "_AAAAMMDD"; {uf} = sigla
    conhecida: str     # versão conhecida (AAAAMMDD ou ""), usada se o índice não responder
    pasta: str         # subpasta do cache
    derivados: tuple[str, ...]  # caminhos (relativos ao cache, com {uf}) a refazer quando o arquivo muda
    para: str

    def nome(self, uf: str, versao: str | None = None) -> str:
        versao = self.conhecida if versao is None else versao
        return self.modelo.replace("{versao}", f"_{versao}" if versao else "").replace("{uf}", uf.upper())

    def padrao(self, uf: str) -> re.Pattern[str]:
        partes = _VERSAO.split(self.modelo.replace("{uf}", uf.upper()))
        return re.compile(r"(?:_(\d{8}))?".join(re.escape(p) for p in partes))

    def url(self, uf: str, nome: str | None = None) -> str:
        if self.tipo == "api":
            return self.diretorio.format(cod=UF_IBGE[uf.upper()])
        return f"{self.diretorio.format(uf=uf.upper())}/{nome or self.nome(uf)}"


_BAIRROS_PQ = ("ibge_censo2022/censo_bairros_{uf}.parquet",)
_SETORES_PQ = ("ibge_censo2022/censo_setores_{uf}.parquet",)
_AG_BAIRRO = f"{CENSO}/Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv"
_AG_SETOR = f"{CENSO}/Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv"
_RENDA = f"{CENSO}/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel"
_ENTORNO = f"{CENSO}/Agregados_por_Setores_Censitarios_Caracteristicas_urbanisticas_do_entorno_dos_domicilios/Agregados_por_Setor_csv"
_AP = f"{CENSO}/Microdados_e_Areas_de_Ponderacao"
_AP_PQ = ("ibge_censo2022/ap_composicao.parquet",)
_AMOSTRA_PQ = ("ibge_censo2022/ap_amostra.parquet",)
FONTES = [
    Fonte("malha_municipios", "api", API_MALHA, "municipios_{uf}.geojson", "", "malhas", (),
          "mapas por município (todas as abas)"),
    Fonte("malha_ufs", "api", API_MALHA_UFS, "ufs_BR.geojson", "", "malhas", (),
          "mapa do presidente por UF (cartão Brasil do painel)"),
    Fonte("malha_bairros", "fixo", f"{GEOFTP_CD2022}/bairros/shp/UF", "{uf}_bairros_CD2022.zip", "", "malhas",
          ("malhas/bairros_{uf}.geojson",), "mapas e comparação por bairro, Perfil × voto por bairro"),
    Fonte("malha_setores", "fixo", f"{GEOFTP_CD2022}/setores/shp/UF", "{uf}_setores_CD2022.zip", "", "ibge_censo2022",
          _SETORES_PQ, "Perfil × voto e mapa por local (ligação setor → local)"),
    Fonte("bairros_renda", "ftp", _RENDA, "Agregados_por_bairros_renda_responsavel_BR{versao}_csv.zip", "20260508",
          "ibge_censo2022", _BAIRROS_PQ, "Perfil × voto por bairro (renda)"),
    Fonte("bairros_basico", "ftp", _AG_BAIRRO, "Agregados_por_bairros_basico_BR{versao}.zip", "20260520",
          "ibge_censo2022", _BAIRROS_PQ, "Perfil × voto por bairro (densidade, moradores)"),
    Fonte("bairros_cor", "ftp", _AG_BAIRRO, "Agregados_por_bairros_cor_ou_raca_BR{versao}.zip", "",
          "ibge_censo2022", _BAIRROS_PQ, "Perfil × voto por bairro (cor ou raça)"),
    Fonte("setores_renda", "ftp", _RENDA, "Agregados_por_setores_renda_responsavel_BR{versao}_csv.zip", "20260508",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto por local (renda)"),
    Fonte("setores_basico", "ftp", _AG_SETOR, "Agregados_por_setores_basico_BR{versao}.zip", "20260520",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto por local (densidade, favela)"),
    Fonte("setores_cor", "ftp", _AG_SETOR, "Agregados_por_setores_cor_ou_raca_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto por local (cor ou raça)"),
    Fonte("bairros_demografia", "ftp", _AG_BAIRRO, "Agregados_por_bairros_demografia_BR{versao}.zip", "",
          "ibge_censo2022", _BAIRROS_PQ, "Perfil × voto por bairro (sexo e idade dos moradores)"),
    Fonte("setores_demografia", "ftp", _AG_SETOR, "Agregados_por_setores_demografia_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto por local (sexo e idade dos moradores)"),
    # rodada 49: catálogo de contagens por setor (`apuracao.censo`), nas três unidades do Perfil × voto
    Fonte("setores_alfabetizacao", "ftp", _AG_SETOR, "Agregados_por_setores_alfabetizacao_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto (alfabetização)"),
    Fonte("setores_domicilio1", "ftp", _AG_SETOR, "Agregados_por_setores_caracteristicas_domicilio1_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto (apartamento, um morador; domicílios)"),
    Fonte("setores_domicilio2", "ftp", _AG_SETOR, "Agregados_por_setores_caracteristicas_domicilio2_BR{versao}.zip",
          "20250417", "ibge_censo2022", _SETORES_PQ, "Perfil × voto (água, esgoto, lixo, banheiro)"),
    Fonte("setores_parentesco", "ftp", _AG_SETOR, "Agregados_por_setores_parentesco_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto (domicílios chefiados por mulher)"),
    Fonte("setores_indigenas", "ftp", _AG_SETOR, "Agregados_por_setores_pessoas_indigenas_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto (pessoas indígenas)"),
    Fonte("setores_quilombolas", "ftp", _AG_SETOR, "Agregados_por_setores_pessoas_quilombolas_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto (pessoas quilombolas)"),
    Fonte("setores_entorno", "ftp", _ENTORNO, "Agregados_por_setores_entorno_moradores_BR{versao}.zip", "",
          "ibge_censo2022", _SETORES_PQ, "Perfil × voto (pavimentação, iluminação, calçada, árvores)"),
    # amostra do Censo por área de ponderação (religião, educação, renda per capita, trabalho…), nacionais
    Fonte("ap_composicao", "fixo", f"{_AP}/Documentacao/Áreas de ponderação", "Composição das Áreas de Ponderação.xlsx",
          "", "ibge_censo2022", _AP_PQ, "Perfil × voto por área de ponderação (setor → área)"),
    Fonte("ap_tabelas", "fixo", f"{_AP}/Areas_de_Ponderacao", "tabelas_xlsx.zip", "", "ibge_censo2022", _AMOSTRA_PQ,
          "Perfil × voto por área de ponderação (religião e demais resultados da amostra)"),
]
POR_CHAVE = {f.chave: f for f in FONTES}


@dataclass
class Estado:
    chave: str
    url: str
    arquivo: str                         # nome no IBGE (versão mais nova encontrada)
    local: str | None = None             # nome no cache
    http: int | None = None
    remoto_modificado: str | None = None
    remoto_bytes: int | None = None
    local_modificado: str | None = None
    situacao: str = ""
    acao: str = ""                       # "" | baixar | baixar versão nova | baixar de novo | conferir | tentar de novo


# --------------------------------------------------------------------------
# Cache local (sem rede)
# --------------------------------------------------------------------------
def _versao(fonte: Fonte, uf: str, nome: str) -> str | None:
    """Versão ("" = sem data) de um nome que segue o modelo da fonte; None se não segue."""
    m = fonte.padrao(uf).fullmatch(nome)
    return None if m is None else (m.group(1) or "") if m.groups() else ""


def local(fonte: Fonte, cache: Path, uf: str) -> Path | None:
    """O arquivo da fonte no cache, na versão mais nova (a data no nome; sem data = a mais antiga)."""
    pasta = cache / fonte.pasta
    if not pasta.is_dir():
        return None
    achados = [(ver, p) for p in pasta.iterdir() if p.is_file() and (ver := _versao(fonte, uf, p.name)) is not None]
    return max(achados)[1] if achados else None


def _proveniencia(arquivo: Path) -> dict[str, Any]:
    p = arquivo.with_suffix(".proveniencia.json")
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def _gravar_proveniencia(arquivo: Path, dados: dict[str, Any]) -> None:
    alvo = arquivo.with_suffix(".proveniencia.json")
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, indent=2))
    tmp.replace(alvo)


# --------------------------------------------------------------------------
# IBGE (rede)
# --------------------------------------------------------------------------
def listar(url_diretorio: str, sessao: Any = requests) -> list[str]:
    """Nomes de arquivo do índice HTML de um diretório do FTP do IBGE (servido por HTTPS)."""
    r = sessao.get(url_diretorio + "/", headers=v.HTTP_HEADERS, timeout=60)
    r.raise_for_status()
    return sorted({h.rsplit("/", 1)[-1] for h in re.findall(r'href="([^"?#]+)"', r.text)})


def resolver(fonte: Fonte, uf: str, sessao: Any = requests, indices: dict[str, list[str]] | None = None) -> str:
    """Nome da versão mais nova publicada. "fixo"/"api": o próprio modelo. Erro de rede propaga."""
    if fonte.tipo != "ftp":
        return fonte.nome(uf, "")
    indices = {} if indices is None else indices
    d = fonte.diretorio.format(uf=uf.upper())
    if d not in indices:
        indices[d] = listar(d, sessao)
    achados = [(ver, n) for n in indices[d] if (ver := _versao(fonte, uf, n)) is not None]
    if not achados:
        raise v.TseDataError(f"nenhum arquivo como {fonte.nome(uf, '')} em {d}/ (o IBGE mudou o nome?)")
    return max(achados)[1]


def _baixar_api(fonte: Fonte, uf: str, destino: Path, sessao: Any = requests) -> tuple[bool, Path]:
    """GET da API; grava (de forma atômica) só se o conteúdo mudou. Devolve (mudou, caminho)."""
    url = fonte.url(uf)
    r = sessao.get(url, headers=v.HTTP_HEADERS, timeout=120)
    r.raise_for_status()
    corpo = r.content
    json.loads(corpo)  # resposta que não é JSON (página de erro) não entra no cache
    sha = hashlib.sha512(corpo).hexdigest()
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prov = _proveniencia(destino)
    mudou = not destino.exists() or prov.get("sha512") != sha
    if mudou:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(destino.suffix + ".part")
        tmp.write_bytes(corpo)
        tmp.replace(destino)
        prov = {"url": url, "downloaded_at": agora, "last_modified": r.headers.get("Last-Modified"),
                "bytes": len(corpo), "sha512": sha}
    prov["conferido_em"] = agora
    _gravar_proveniencia(destino, prov)
    return mudou, destino


def caminho(chave: str, cache: Path, uf: str, sessao: Any = requests) -> Path:
    """O arquivo da fonte: o do cache, sem rede; se faltar, descobre a versão e baixa uma vez.
    404 → `v.TseDataError`; falha de rede → `requests.RequestException` (quem chama decide a mensagem)."""
    fonte = POR_CHAVE[chave]
    achado = local(fonte, cache, uf)
    if achado is not None:
        return achado
    pasta = cache / fonte.pasta
    if fonte.tipo == "api":
        logger.info("baixando %s do IBGE (%s)", chave, uf)
        return _baixar_api(fonte, uf, pasta / fonte.nome(uf, ""), sessao)[1]
    try:
        nome = resolver(fonte, uf, sessao)
    except (requests.RequestException, v.TseDataError) as exc:  # sem índice: a versão conhecida
        logger.warning("índice do IBGE indisponível para %s (%s); tentando %s", chave, exc, fonte.nome(uf))
        nome = fonte.nome(uf)
    logger.info("baixando %s do IBGE (%s)", nome, uf)
    return v.download(v.DatasetSpec(chave, fonte.url(uf, nome), v.NATIONAL), pasta)


# --------------------------------------------------------------------------
# Verificação e atualização
# --------------------------------------------------------------------------
def _data(texto: str | None) -> datetime | None:
    try:
        return parsedate_to_datetime(texto) if texto else None
    except (TypeError, ValueError):
        return None


def _verificar_api(fonte: Fonte, cache: Path, uf: str, e: Estado, forcar_api: bool) -> None:
    achado = local(fonte, cache, uf)
    if achado is None:
        e.situacao, e.acao = "não está no cache", "baixar"
        return
    e.local = achado.name
    prov = _proveniencia(achado)
    e.local_modificado = prov.get("conferido_em") or prov.get("downloaded_at")
    quando = datetime.fromisoformat(e.local_modificado) if e.local_modificado else None
    idade = (datetime.now(timezone.utc) - quando).days if quando else None
    if forcar_api or idade is None or idade >= IDADE_MAX_API_DIAS:
        e.situacao = "a conferir (a API não aceita HEAD)" if idade is None else f"conferida há {idade} dias"
        e.acao = "conferir"
    else:
        e.situacao = f"em dia (conferida há {idade} dias)"


def verificar(cache: Path, uf: str, sessao: Any = requests, forcar_api: bool = False) -> list[Estado]:
    """Índices + um HEAD por arquivo; compara com o cache (sem baixar nada)."""
    indices: dict[str, list[str]] = {}
    saida = []
    for fonte in FONTES:
        e = Estado(fonte.chave, fonte.url(uf), fonte.nome(uf, ""))
        saida.append(e)
        if fonte.tipo == "api":
            _verificar_api(fonte, cache, uf, e, forcar_api)
            continue
        try:
            e.arquivo = resolver(fonte, uf, sessao, indices)
            e.url = fonte.url(uf, e.arquivo)
            r = sessao.head(e.url, headers=v.HTTP_HEADERS, timeout=30, allow_redirects=True)
            e.http = r.status_code
            e.remoto_modificado = r.headers.get("Last-Modified")
            e.remoto_bytes = int(r.headers["Content-Length"]) if r.headers.get("Content-Length") else None
        except (requests.RequestException, v.TseDataError) as exc:
            e.situacao, e.acao = f"IBGE indisponível ({exc.__class__.__name__}: {exc})"[:160], "tentar de novo"
            continue
        achado = local(fonte, cache, uf)
        e.local = achado.name if achado else None
        if e.http != 200:
            e.situacao, e.acao = f"HTTP {e.http}", "tentar de novo"
            continue
        if achado is None:
            e.situacao, e.acao = "não está no cache", "baixar"
            continue
        prov = _proveniencia(achado)
        e.local_modificado = prov.get("last_modified")
        v_remota, v_local = _versao(fonte, uf, e.arquivo), _versao(fonte, uf, achado.name)
        remoto, loc = _data(e.remoto_modificado), _data(e.local_modificado)
        if (v_remota or "") > (v_local or ""):
            e.situacao, e.acao = f"versão nova no IBGE ({v_remota})", "baixar versão nova"
        elif remoto and loc and remoto > loc:
            e.situacao, e.acao = "atualizado no IBGE (Last-Modified mais novo)", "baixar de novo"
        elif not loc and e.remoto_bytes is not None and e.remoto_bytes != achado.stat().st_size:
            e.situacao, e.acao = "tamanho difere do IBGE (cache sem data)", "baixar de novo"
        else:
            e.situacao = "em dia"
    return saida


def _geradores() -> dict[str, Callable[[str, Path], Any]]:
    """Derivado (modelo do caminho) → função que o gera (importação tardia: esses módulos usam este)."""
    from apuracao import areas_ponderacao as ap
    from apuracao import bairros as br
    from apuracao import perfil as pf
    from apuracao import perfil_local as pfl
    return {"malhas/bairros_{uf}.geojson": lambda uf, cache: br.malha(uf, cache),
            "ibge_censo2022/censo_bairros_{uf}.parquet": pf.censo_por_bairro,
            "ibge_censo2022/censo_setores_{uf}.parquet": pfl.setores,
            "ibge_censo2022/ap_composicao.parquet": lambda uf, cache: ap.composicao(cache),  # nacionais
            "ibge_censo2022/ap_amostra.parquet": lambda uf, cache: ap.amostra(cache)}


def _guardar(p: Path) -> Path | None:
    """Renomeia `p` (e a proveniência) para `<nome>.anterior`; devolve o novo caminho."""
    if not p.exists():
        return None
    alvo = p.with_name(p.name + ANTERIOR)
    p.replace(alvo)
    prov = p.with_suffix(".proveniencia.json")
    if prov.exists():
        prov.replace(prov.with_name(prov.name + ANTERIOR))
    return alvo


def _restaurar(guardado: Path) -> None:
    original = guardado.with_name(guardado.name.removesuffix(ANTERIOR))
    guardado.replace(original)
    prov = original.with_suffix(".proveniencia.json")
    prov_g = prov.with_name(prov.name + ANTERIOR)
    if prov_g.exists():
        prov_g.replace(prov)


def _apagar(p: Path) -> None:
    p.unlink(missing_ok=True)
    if p.name.endswith(ANTERIOR):
        prov = p.with_name(p.name.removesuffix(ANTERIOR)).with_suffix(".proveniencia.json")
        prov.with_name(prov.name + ANTERIOR).unlink(missing_ok=True)
    else:
        p.with_suffix(".proveniencia.json").unlink(missing_ok=True)


def atualizar(cache: Path, uf: str, sessao: Any = requests, forcar_api: bool = False,
              baixar: Callable[[str, Path, Any], Path] | None = None) -> list[Estado]:
    """Verifica, baixa o que é novo/atualizado e refaz os derivados. A versão anterior (arquivo e
    derivado) fica guardada até o derivado novo ficar pronto; se ele falhar, ela volta."""
    if baixar is None:
        from apuracao.microdados import baixar
    estados = verificar(cache, uf, sessao, forcar_api)
    # por derivado: os arquivos novos que o afetam e o que foi guardado para voltar atrás
    novos: dict[str, list[Path]] = {}
    guardados: dict[str, list[Path]] = {}
    for e in estados:
        fonte = POR_CHAVE[e.chave]
        pasta = cache / fonte.pasta
        guardar: list[Path] = []
        try:
            if e.acao == "conferir":
                mudou, _ = _baixar_api(fonte, uf, pasta / fonte.nome(uf, ""), sessao)
                e.situacao, e.acao = ("mudou no IBGE; atualizada" if mudou else "conferida: igual"), (
                    "atualizado" if mudou else "")
                continue
            if e.acao == "baixar" and fonte.tipo == "api":
                _baixar_api(fonte, uf, pasta / fonte.nome(uf, ""), sessao)
                e.local, e.situacao, e.acao = e.arquivo, "baixado agora", "baixado"
                continue
            if e.acao not in ("baixar", "baixar versão nova", "baixar de novo"):
                continue
            destino = pasta / e.arquivo
            anterior = local(fonte, cache, uf)
            if anterior is not None and anterior.name == e.arquivo:  # mesma versão republicada no lugar
                if (g := _guardar(anterior)) is not None:
                    guardar.append(g)
            elif anterior is not None:  # versão antiga com outro nome: sai se o derivado novo der certo
                guardar.append(anterior)
            baixar(e.url, destino, sessao)
        except (requests.RequestException, v.TseDataError, OSError, ValueError) as exc:
            for g in guardar:
                if g.name.endswith(ANTERIOR):
                    _restaurar(g)
            e.situacao, e.acao = f"falha ao baixar ({exc.__class__.__name__}: {exc})"[:160], "tentar de novo"
            logger.error("%s: %s", e.chave, e.situacao)
            continue
        e.local, e.situacao, e.acao = e.arquivo, "baixado agora", "baixado"
        logger.info("%s: %s baixado", e.chave, e.arquivo)
        if not fonte.derivados:
            for g in guardar:
                _apagar(g)
        for d in fonte.derivados:
            novos.setdefault(d, []).append(destino)
            guardados.setdefault(d, []).extend(guardar)
    _refazer_derivados(cache, uf, estados, novos, guardados)
    gravar_estado(cache, estados)
    return estados


def _refazer_derivados(cache: Path, uf: str, estados: list[Estado], novos: dict[str, list[Path]],
                       guardados: dict[str, list[Path]]) -> None:
    geradores = _geradores()
    por_arquivo = {e.local: e for e in estados if e.local}
    for modelo, arquivos in novos.items():
        alvo = cache / modelo.format(uf=uf.upper())
        derivado_antigo = _guardar(alvo)
        try:
            geradores[modelo](uf.upper(), cache)
        except Exception as exc:  # noqa: BLE001 — qualquer falha de conversão: voltar à versão anterior
            logger.error("derivado %s falhou com a versão nova (%s); voltando à anterior", alvo.name, exc)
            for a in arquivos:
                _apagar(a)
                if (e := por_arquivo.get(a.name)) is not None:
                    e.situacao, e.acao = f"versão nova não convertida ({exc})"[:160], "tentar de novo"
            for g in guardados.get(modelo, []):
                if g.name.endswith(ANTERIOR):
                    _restaurar(g)
            alvo.unlink(missing_ok=True)
            if derivado_antigo is not None:
                _restaurar(derivado_antigo)
            continue
        if derivado_antigo is not None:
            derivado_antigo.unlink(missing_ok=True)
        for g in guardados.get(modelo, []):
            if g.exists():
                _apagar(g)


def preparar(cache: Path, uf: str, sessao: Any = requests) -> list[str]:
    """Garante no cache todas as fontes e os derivados (baixa só o que falta). Devolve as falhas."""
    falhas = []
    for fonte in FONTES:
        try:
            caminho(fonte.chave, cache, uf, sessao)
        except (requests.RequestException, v.TseDataError, OSError, ValueError) as exc:
            falhas.append(f"{fonte.chave}: {exc}")
    for modelo, gerar in _geradores().items():
        try:
            gerar(uf.upper(), cache)
        except Exception as exc:  # noqa: BLE001 — relatório: uma falha não impede os outros derivados
            falhas.append(f"{modelo.format(uf=uf.upper())}: {exc}")
    for f in falhas:
        logger.error("IBGE: %s", f)
    return falhas


def gravar_estado(cache: Path, estados: list[Estado]) -> Path:
    alvo = cache / ESTADO
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps({"verificado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "fontes": [asdict(e) for e in estados]}, indent=2, ensure_ascii=False))
    tmp.replace(alvo)
    return alvo


def ler_estado(cache: Path) -> dict[str, Any] | None:
    p = cache / ESTADO
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except (OSError, ValueError):
        return None
