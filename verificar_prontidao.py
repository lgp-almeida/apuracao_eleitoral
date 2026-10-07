"""Verificação de prontidão para a noite da eleição (rodar em 3/10 e às 16h de 4/10).

    python verificar_prontidao.py              # checagens rápidas (poucos acessos ao TSE)
    python verificar_prontidao.py --testes     # + a suíte de testes sem navegador
    python verificar_prontidao.py --turno 2 --ufs todas   # noite do 2º turno com o site de várias UFs (rodada 43)

Cada linha sai como OK, AVISO ou FALHA; qualquer FALHA faz o comando terminar com código 1.
"""

from __future__ import annotations

import argparse
import email.utils
import importlib
import json
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from apuracao import ibge
from apuracao.divulgacao import modelo as m
from apuracao.divulgacao.cliente import AMBIENTES, ClienteDivulgacao, DivulgacaoIndisponivel

CODIGOS_OFICIAIS = {6257, 6259}  # Anexo I, bloco A6: Federal (Presidente) e Estaduais
Resultado = tuple[str, str, str]  # (situação, item, detalhe)


def _dependencias() -> list[Resultado]:
    out = []
    if sys.version_info < (3, 12):
        out.append(("FALHA", "Python", f"{sys.version.split()[0]} (precisa de 3.12)"))
    for mod, obrig in (("polars", True), ("fastapi", True), ("uvicorn", True), ("numpy", True), ("requests", True),
                       ("geopandas", False), ("playwright", False)):
        try:
            importlib.import_module(mod)
            out.append(("OK", f"módulo {mod}", ""))
        except ImportError:
            out.append(("FALHA" if obrig else "AVISO", f"módulo {mod}", "não instalado (pip install -r requirements.txt)"))
    return out + versoes_fixadas(Path(__file__).with_name("requirements.txt"))


def versoes_fixadas(requirements: Path, instalada: Any = None) -> list[Resultado]:
    """Versões instaladas × as fixadas em requirements.txt (as que passaram nos testes e no ensaio)."""
    from importlib import metadata
    instalada = instalada or metadata.version
    diferentes = []
    for linha in requirements.read_text(encoding="utf-8").splitlines():
        pacote, _, versao = linha.split("#", 1)[0].strip().partition("==")
        if not versao:
            continue
        try:
            atual = instalada(pacote)
        except metadata.PackageNotFoundError:
            continue  # a falta de um módulo já aparece acima
        if atual != versao.strip():
            diferentes.append(f"{pacote} {atual} (fixada {versao.strip()})")
    if diferentes:
        return [("AVISO", "versões fixadas", "; ".join(diferentes) + " — pip install -r requirements.txt")]
    return [("OK", "versões fixadas", "iguais às de requirements.txt")]


def _disco(dados: Path) -> list[Resultado]:
    livre = shutil.disk_usage(dados if dados.exists() else Path(".")).free / 1e9
    sit = "OK" if livre >= 5 else ("AVISO" if livre >= 1 else "FALHA")
    return [(sit, "espaço em disco", f"{livre:.1f} GB livres (a noite grava ~1–2 GB de JSON bruto)")]


def _cache(cache: Path) -> list[Resultado]:
    itens = [
        (cache / "malhas" / "municipios_RJ.geojson", True, "malha dos municípios (mapas)"),
        (cache / "malhas" / "bairros_RJ.geojson", False, "malha dos bairros (mapas por bairro)"),
        (cache / "ibge_censo2022" / "censo_bairros_RJ.parquet", False, "Censo 2022 por bairro (Perfil × voto)"),
        (cache / "ibge_censo2022" / "censo_setores_RJ.parquet", False, "Censo 2022 por setor (Perfil × voto por local)"),
        (Path("dados_2026/historico_2022_t1/ultimo/totais.parquet"), False, "2022 importado (aba Comparação)"),
        (cache / "votacao_candidato_munzona_2022.zip", False, "microdados de 2022 (cadeiras de 2022 e ensaio)"),
        (cache / "eleitorado_local_votacao_2026__RJ.parquet", False, "eleitorado 2026 (planilhas e locais)"),
    ]
    return ([("OK" if p.exists() else ("FALHA" if obrig else "AVISO"), desc, str(p)) for p, obrig, desc in itens]
            + _ibge(cache))


def _ibge(cache: Path) -> list[Resultado]:
    """Última verificação de `preparar_ibge.py` (sem rede): idade e ações pendentes."""
    estado = ibge.ler_estado(cache)
    if estado is None:
        return [("AVISO", "IBGE atualizado", "nunca verificado — python preparar_ibge.py")]
    idade = (datetime.now(timezone.utc) - datetime.fromisoformat(estado["verificado_em"])).days
    pendentes = [f["chave"] for f in estado.get("fontes", []) if f.get("acao") not in ("", "baixado", "atualizado")]
    if pendentes:
        return [("AVISO", "IBGE atualizado", f"pendente: {', '.join(pendentes)} — python preparar_ibge.py")]
    if idade > ibge.IDADE_MAX_API_DIAS:
        return [("AVISO", "IBGE atualizado", f"verificado há {idade} dias — python preparar_ibge.py")]
    return [("OK", "IBGE atualizado", f"verificado há {idade} dias")]


def _relogio() -> list[Resultado]:
    """A hora vem no cabeçalho Date de uma resposta pequena (o ele-c.json): do oficial e, se ele falhar, do
    simulado (o simulado sai do ar depois do 1º turno: em 07/10/2026 o nome nem resolvia)."""
    erros = []
    for ambiente in ("oficial", "simulado"):
        try:
            r = requests.get(ClienteDivulgacao(ambiente).url(ClienteDivulgacao.caminho_config()), timeout=15)
            servidor = email.utils.parsedate_to_datetime(r.headers["Date"])
            break
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            erros.append(f"{ambiente}: {exc.__class__.__name__}")
    else:
        return [("AVISO", "relógio × TSE", f"não deu para ler a hora do TSE ({'; '.join(erros)})")]
    dif = abs((datetime.now(timezone.utc) - servidor).total_seconds())
    return [("OK" if dif < 60 else "AVISO", "relógio × TSE", f"diferença de {dif:.0f} s")]


def _ambiente(nome: str) -> list[Resultado]:
    cli = ClienteDivulgacao(nome, max_rps=2)
    url = cli.url(cli.caminho_config())
    try:
        resp = cli.get_json(cli.caminho_config())
    except DivulgacaoIndisponivel as exc:
        return [("AVISO", f"TSE {nome}: configuração", f"ainda não publicada ({exc})")]
    except requests.RequestException as exc:
        return [("FALHA", f"TSE {nome}: configuração", f"sem acesso a {url}: {exc}")]
    if resp is None:
        sit = "AVISO" if nome == "oficial" else "FALHA"
        return [(sit, f"TSE {nome}: configuração", f"404 em {url} (o oficial entra na véspera, 3/10)")]
    cfg = m.parse_config(resp.dados)
    codigos = {e.codigo for e in cfg.eleicoes}
    out: list[Resultado] = [("OK", f"TSE {nome}: configuração",
                             f"ciclo {cfg.ciclo}; eleições {sorted(codigos)}; gerado em {cfg.gerado_em}")]
    if nome == "oficial" and not CODIGOS_OFICIAIS <= codigos:
        out.append(("AVISO", "TSE oficial: códigos", f"esperados {sorted(CODIGOS_OFICIAIS)} (Anexo I), vieram "
                                                      f"{sorted(codigos)} — o coletor usa os do arquivo, sem problema"))
    # o que o COLETOR acharia nesta configuração (04/10/2026: o oficial listava 2024 primeiro e o coletor não
    # achava 2026 — a prontidão só conferia que o arquivo respondia)
    faltam = [nome_ for cargo_, nome_ in ((3, "Governador"), (1, "Presidente")) if cfg.por_cargo(cargo_) is None]
    if faltam:
        ainda = m._ano_do_ciclo(cfg.ciclo) < 2026
        out.append(("AVISO" if ainda else "FALHA", f"TSE {nome}: eleições que o coletor usaria",
                    f"sem {', '.join(faltam)} no ciclo {cfg.ciclo}" + (" (2026 ainda não publicado)" if ainda
                                                                        else " — o coletor ficaria sem eleição")))
    est = cfg.por_cargo(3)
    if est is not None:
        ab = cli.get_json(cli.caminho_acompanhamento(cfg, est.codigo, "rj"))
        out.append(("OK" if ab is not None else "AVISO", f"TSE {nome}: acompanhamento do RJ",
                    "publicado" if ab is not None else "ainda 404 (normal antes das 17h de 4/10)"))
    return out


def _portas(portas: tuple[int, ...]) -> list[Resultado]:
    out = []
    for p in portas:
        with socket.socket() as s:
            livre = s.connect_ex(("127.0.0.1", p)) != 0
        if livre:
            out.append(("OK", f"porta {p}", "livre"))
            continue
        try:
            st = requests.get(f"http://127.0.0.1:{p}/api/status", timeout=5).json()
            amb = (st.get("coletor") or {}).get("ambiente")
            out.append(("AVISO", f"porta {p}", f"já há um site no ar (ambiente {amb}); encerre-o antes da noite"))
        except (requests.RequestException, ValueError):
            out.append(("AVISO", f"porta {p}", "ocupada por outro programa"))
    return out


def _destino(dados: Path) -> list[Resultado]:
    st = dados / "status.json"
    if not st.exists():
        return [("OK", "dados do oficial", f"{dados} vazio: a noite começa do zero")]
    amb = json.loads(st.read_text()).get("ambiente")
    if amb != "oficial":
        return [("FALHA", "dados do oficial", f"{dados} tem dados do ambiente {amb}: apague ou use outro --dados")]
    return [("OK", "dados do oficial", f"{dados} já tem coleta do oficial (o coletor continua de onde parou)")]


def ufs_com_segundo_turno(base_1t: Path, ufs: list[str], cargo: int = 3) -> list[str]:
    """UFs cujo resultado do 1º turno (coletado em `<base_1t>[_<UF>]`) tem candidato do cargo na situação
    "2º turno" — sem rede (04/10/2026: Governador em AC, AM, DF, ES, RJ, RN e TO)."""
    import polars as pl

    from apuracao.ufs import dir_uf
    saida = []
    for uf in ufs:
        arq = dir_uf(base_1t, uf) / "ultimo" / "candidatos.parquet"
        if not arq.exists():
            continue
        c = pl.read_parquet(arq, columns=["CARGO", "ABRANGENCIA", "SITUACAO"])
        if c.filter((pl.col("CARGO") == cargo) & (pl.col("ABRANGENCIA") == "uf")
                    & (pl.col("SITUACAO") == "2º turno")).height:
            saida.append(uf)
    return saida


def _segundo_turno(ufs: list[str], raiz: Path = Path("dados_2026")) -> list[Resultado]:
    """Por UF, sem rede: a pasta do 2º turno (vazia ou do oficial), a referência de 2022 do 2º turno (aba
    Comparação) e a pasta do 1º turno (transferência 1º → 2º turno)."""
    from apuracao.ufs import dir_uf, tem_dados
    out: list[Resultado] = []
    com_gov = ufs_com_segundo_turno(raiz / "oficial", ufs)
    out.append(("OK" if com_gov else "AVISO", "2º turno para Governador",
                f"{', '.join(com_gov)} (do resultado do 1º turno)" if com_gov else "nenhuma UF com o 1º turno coletado"))
    for uf in ufs:
        destino, ref, t1 = (dir_uf(raiz / "oficial_t2", uf), dir_uf(raiz / "historico_2022_t2", uf),
                            dir_uf(raiz / "oficial", uf))
        sit, item, det = _destino(destino)[0]
        out.append((sit, f"{uf}: dados do 2º turno", det))
        out.append(("OK" if tem_dados(ref) else "AVISO", f"{uf}: 2022 do 2º turno (Comparação)",
                    str(ref) if tem_dados(ref) else f"falta {ref} — python baixar_ufs.py --etapas historico --turnos 2"))
        out.append(("OK" if tem_dados(t1) else "AVISO", f"{uf}: 1º turno (transferência)",
                    str(t1) if tem_dados(t1) else f"falta {t1} — python baixar_ufs.py --ufs {uf} --etapas divulgacao"))
    return out


def _ambiente_2t(ufs_gov: list[str]) -> list[Resultado]:
    """Oficial, 2º turno: as eleições (cdt2) no ele-c.json e o acompanhamento só das UFs com 2º turno para
    Governador (poucos pedidos: 404 repetido bloqueia o IP)."""
    cli = ClienteDivulgacao("oficial", max_rps=2)
    try:
        resp = cli.get_json(cli.caminho_config())
    except (DivulgacaoIndisponivel, requests.RequestException) as exc:
        return [("FALHA", "TSE oficial (2º turno): configuração", str(exc))]
    if resp is None:
        return [("FALHA", "TSE oficial (2º turno): configuração", "404")]
    cfg = m.parse_config(resp.dados)
    out: list[Resultado] = []
    for cargo, nome in ((3, "Governador"), (1, "Presidente")):
        e = cfg.por_cargo(cargo, 2)
        out.append(("OK" if e else "FALHA", f"TSE oficial: eleição do 2º turno ({nome})",
                    f"código {e.codigo}" if e else "sem cdt2 no ele-c.json — o coletor ficaria sem eleição"))
    est = cfg.por_cargo(3, 2)
    for uf in ufs_gov if est else []:
        ab = cli.get_json(cli.caminho_acompanhamento(cfg, est.codigo, uf.lower()))
        out.append(("OK" if ab is not None else "AVISO", f"TSE oficial: acompanhamento do 2º turno ({uf})",
                    "publicado" if ab is not None else "ainda 404 (normal antes das 17h de 25/10)"))
    return out


def _testes() -> list[Resultado]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-m", "not e2e"], capture_output=True, text=True)
    ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
    return [("OK" if r.returncode == 0 else "FALHA", "testes (sem navegador)", ultima)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prontidão para a noite da eleição.")
    ap.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    ap.add_argument("--dados", type=Path, default=Path("dados_2026/oficial"))
    ap.add_argument("--testes", action="store_true", help="rodar também a suíte de testes sem navegador")
    ap.add_argument("--turno", type=int, choices=[1, 2], default=1)
    ap.add_argument("--ufs", nargs="+", help="siglas ou 'todas': confere cada UF (pastas, referência, 1º turno)")
    a = ap.parse_args(argv)
    from apuracao import ufs as uf_mod
    ufs = uf_mod.lista(a.ufs) if a.ufs else ["RJ"]
    if a.turno == 2:
        linhas = (_dependencias() + _disco(a.dados) + _relogio() + _segundo_turno(ufs)
                  + _ambiente_2t(ufs_com_segundo_turno(Path("dados_2026/oficial"), ufs))
                  + _portas((8000, 8001) if a.ufs else (8000,)) + (_testes() if a.testes else []))
    else:
        linhas = (_dependencias() + _disco(a.dados) + _cache(a.cache_dir) + _relogio()
                  + [x for amb in sorted(AMBIENTES) for x in _ambiente(amb)] + _portas((8000,)) + _destino(a.dados)
                  + (_testes() if a.testes else []))
    largura = max(len(i) for _, i, _ in linhas)
    for sit, item, det in linhas:
        print(f"{sit:5}  {item:<{largura}}  {det}")
    falhas = sum(1 for s, _, _ in linhas if s == "FALHA")
    avisos = sum(1 for s, _, _ in linhas if s == "AVISO")
    print(f"\n{'PRONTO' if not falhas else 'NÃO PRONTO'}: {falhas} falha(s), {avisos} aviso(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
