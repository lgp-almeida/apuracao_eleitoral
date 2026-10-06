"""Site local de acompanhamento da apuração 2026 (abrir no Chrome).

    python site_apuracao.py --ambiente simulado --coletar          # coleta + site num só comando
    python site_apuracao.py --ambiente oficial --coletar --abrir   # noite da eleição
    python site_apuracao.py --ambiente oficial                     # só o site (coletor rodando à parte)

Com --coletar, o coletor (coletar_resultados.py) roda numa thread do mesmo processo, e o boletim para a
equipe (HTML de um arquivo + planilha) é gravado a cada hora e no fim em <dados>/boletins/ (--sem-boletim desliga),
e a cópia de segurança vai para --copia-dir (padrão copias/<nome dos dados>; prefira outro disco): as parciais do TSE
(raw/) a cada 5 min e um instantâneo do resto por hora e no fim (--sem-copia desliga).
Várias UFs num site só, com seletor de UF no cabeçalho (cada UF em /<uf>/; dados de baixar_ufs.py):
    python site_apuracao.py --ambiente oficial --ufs todas --porta 8001
Resultados de eleições passadas (importar_resultado_historico.py), sem --coletar:
    python site_apuracao.py --dados dados_2026/historico_2022_t1 --porta 8022
O site lê dados_2026/<ambiente>/ e se atualiza sozinho a cada 60 s. Alertas (coletor parado, bloqueio do TSE,
apuração sem avanço, leitura da projeção mudando, deputados de interesse) aparecem no site com som e no terminal:
    python site_apuracao.py --ambiente oficial --coletar --interesse 7:13713 6:1234
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import uvicorn

from apuracao.boletim import Boletineiro
from apuracao.copia import Copiador
from apuracao import ufs as uf_mod
from apuracao.divulgacao.cliente import AMBIENTES, ClienteDivulgacao, LimitadorTaxa
from apuracao.divulgacao.coletor import Coletor, destino_padrao
from apuracao.web.app import create_app, eh_loopback
from apuracao.web.multi import EntradaUF, create_multi_app

logger = logging.getLogger("site_apuracao")
CHROME_WINDOWS = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Site local da apuração 2026.")
    p.add_argument("--ambiente", choices=sorted(AMBIENTES), default="simulado")
    p.add_argument("--uf", default="RJ", type=str.upper, help="UF do site (com --ufs, a que abre primeiro)")
    p.add_argument("--ufs", nargs="+", metavar="UF",
                   help="várias UFs num site só, com seletor (ex.: SP MG RJ, ou 'todas'); cada uma em /<uf>/")
    p.add_argument("--max-rps", type=float, default=20.0,
                   help="acessos por segundo ao TSE do coletor (com --ufs, somando todas as UFs)")
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 para acessar de outra máquina da rede")
    p.add_argument("--dados", help="diretório de dados (padrão: dados_2026/<ambiente>[_t2]_<UF>; no RJ, a pasta "
                                   "antiga sem a UF; com --ufs, a base: <dados>_<UF>)")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--coletar", action="store_true", help="rodar o coletor junto")
    p.add_argument("--intervalo", type=float, default=60.0, help="segundos entre ciclos do coletor")
    p.add_argument("--sem-presidente-ufs", action="store_true",
                   help="não baixar o presidente nas outras UFs (bloco 'Por estado' do cartão Brasil)")
    p.add_argument("--sem-boletim", action="store_true", help="não gravar o boletim a cada hora (só com --coletar)")
    p.add_argument("--boletim-min", type=int, default=60, help="minutos entre boletins (padrão: 60, na hora cheia)")
    p.add_argument("--interesse", nargs="+", default=[], metavar="CARGO:NUMERO", type=_cargo_numero,
                   help="deputados com alerta de mudança de situação (ex.: 7:13713); também pela aba Candidato")
    p.add_argument("--copia-dir", help="pasta da cópia de segurança (padrão: copias/<nome dos dados>); prefira outro disco")
    p.add_argument("--copia-min", type=int, default=60, help="minutos entre instantâneos da cópia (padrão 60)")
    p.add_argument("--sem-copia", action="store_true", help="não fazer cópia de segurança (só com --coletar)")
    p.add_argument("--destacar", nargs="+", default=[], metavar="SIGLA",
                   help='partidos/federações destacados nas listas de eleitos (site e boletim), ex.: PL "PT/PC do B/PV"')
    p.add_argument("--sem-alertas", action="store_true", help="não verificar alertas")
    p.add_argument("--abrir", action="store_true", help="abrir o Chrome ao iniciar")
    p.add_argument("--comparar-com", metavar="DIR",
                   help="eleição de referência para a aba Comparação (padrão: dados_2026/historico_2022_t<turno>, se existir)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _cargo_numero(texto: str) -> tuple[int, int]:
    try:
        cargo, numero = (int(x) for x in texto.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"use CARGO:NUMERO (ex.: 7:13713), não {texto!r}") from None
    if cargo not in (6, 7, 8):
        raise argparse.ArgumentTypeError(f"candidato de interesse só de deputado (cargo 6, 7 ou 8): {texto}")
    return cargo, numero


def _iniciar_coletor(args: argparse.Namespace, destino: Path, status: dict[str, Any]) -> threading.Event:
    parar = threading.Event()
    coletor = Coletor(ClienteDivulgacao(args.ambiente, max_rps=args.max_rps), destino, args.uf, args.turno,
                      presidente_ufs=not args.sem_presidente_ufs)

    def rodar() -> None:
        status["ativo"] = True
        try:
            coletor.executar(args.intervalo, parar)
        except Exception as exc:  # a thread não pode morrer calada: o site mostra o erro
            logger.exception("coletor encerrado por erro")
            status["erro"] = repr(exc)
        finally:
            status["ativo"] = False

    threading.Thread(target=rodar, name="coletor", daemon=True).start()
    return parar


def _iniciar_coletor_ufs(args: argparse.Namespace, entradas: list[EntradaUF],
                         status: dict[str, dict[str, Any]]) -> threading.Event:
    """Um coletor para várias UFs: uma UF depois da outra a cada ciclo, com UM limite de acessos para todas
    (vários coletores somariam o limite de cada um no mesmo IP)."""
    parar = threading.Event()
    limitador = LimitadorTaxa(args.max_rps)
    coletores = {e.uf: Coletor(ClienteDivulgacao(args.ambiente, limitador=limitador), e.dados, e.uf, args.turno,
                               presidente_ufs=False) for e in entradas}

    def rodar() -> None:
        for st in status.values():
            st["ativo"] = True
        while not parar.is_set():
            for uf, col in coletores.items():
                if parar.is_set():
                    break
                col.executar(0, parar, max_ciclos=1)  # trata e registra os erros como o coletor de uma UF
            parar.wait(args.intervalo)
        for st in status.values():
            st["ativo"] = False

    threading.Thread(target=rodar, name="coletor_ufs", daemon=True).start()
    return parar


def _main_ufs(args: argparse.Namespace) -> int:
    """Site com várias UFs: o app de cada uma montado em /<uf>/ (apuracao/web/multi.py)."""
    try:
        ufs = uf_mod.lista(args.ufs)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    base = Path(args.dados) if args.dados else destino_padrao(args.ambiente, turno=args.turno)
    ref_base = Path(args.comparar_com) if args.comparar_com else Path(f"dados_2026/historico_2022_t{args.turno}")
    entradas = []
    for uf in ufs:
        ref = uf_mod.dir_uf(ref_base, uf)
        entradas.append(EntradaUF(uf, uf_mod.dir_uf(base, uf), ref if uf_mod.tem_dados(ref) else None))
    sem = [e.uf for e in entradas if not uf_mod.tem_dados(e.dados)]
    if sem:
        logger.warning("sem dados em %s para: %s (python baixar_ufs.py --ufs %s --etapas divulgacao)",
                       base, " ".join(sem), " ".join(sem))
    for opcao in ("interesse", "copia_dir"):
        if getattr(args, opcao):
            logger.warning("--%s vale só para o site de uma UF; ignorado com --ufs", opcao.replace("_", "-"))
    exposto = not eh_loopback(args.host)
    com_dados = [e for e in entradas if uf_mod.tem_dados(e.dados)]
    # o coletor percorre todas as UFs pedidas; as que ainda não tinham dados aparecem no site ao reiniciá-lo
    status: dict[str, dict[str, Any]] = {e.uf: {"ativo": False, "intervalo_s": args.intervalo} for e in entradas}
    parar = _iniciar_coletor_ufs(args, entradas, status) if args.coletar else None

    def fabrica(e: EntradaUF):
        return create_app(e.dados, e.uf, Path(args.cache_dir), status[e.uf] if args.coletar else None, e.referencia,
                          pesadas_so_local=exposto, destacar=tuple(args.destacar))

    try:
        app = create_multi_app(entradas, args.uf, fabrica)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    url = f"http://localhost:{args.porta}/"
    print(f"\nApuração — {len(com_dados)} UF(s) com dados ({' '.join(e.uf for e in com_dados)}): {url}  "
          "(Ctrl+C encerra)\n", flush=True)
    if args.coletar:
        print("Coletor: as UFs uma depois da outra, a cada ciclo; boletim, cópia e alertas só no site de uma UF.")
    if args.abrir:
        threading.Timer(1.5, _abrir_chrome, [url]).start()
    try:
        uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
    finally:
        if parar is not None:
            parar.set()
    return 0


def _abrir_chrome(url: str) -> None:
    for cmd in (shutil.which("google-chrome"), CHROME_WINDOWS if Path(CHROME_WINDOWS).exists() else None):
        if cmd:
            subprocess.Popen([cmd, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    logger.warning("Chrome não encontrado; abra %s manualmente", url)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    if args.ufs:
        return _main_ufs(args)
    destino = Path(args.dados) if args.dados else uf_mod.dir_uf(destino_padrao(args.ambiente, turno=args.turno),
                                                                   args.uf)
    status: dict[str, Any] = {"ativo": False, "intervalo_s": args.intervalo} if args.coletar else {}
    parar = _iniciar_coletor(args, destino, status) if args.coletar else None
    referencia = Path(args.comparar_com) if args.comparar_com else uf_mod.dir_uf(
        Path(f"dados_2026/historico_2022_t{args.turno}"), args.uf)
    if referencia.resolve() == destino.resolve() or not (referencia / "ultimo").exists():
        referencia = None
    exposto = not eh_loopback(args.host)
    if exposto:
        logger.warning("site aberto na rede em %s:%d SEM SENHA e sem HTTPS: qualquer máquina que alcance esta vê "
                       "o painel. Planilha, bairros, perfil e exportação ficam só para este computador.",
                       args.host, args.porta)
    app = create_app(destino, args.uf, Path(args.cache_dir), status if args.coletar else None, referencia,
                     pesadas_so_local=exposto, interesse=tuple(args.interesse), destacar=tuple(args.destacar))
    if parar is not None and not args.sem_boletim:
        boletineiro = Boletineiro(app.state.consultas, destino / "boletins", args.boletim_min, destacar=args.destacar)
        threading.Thread(target=boletineiro.executar, args=(parar,), name="boletim", daemon=True).start()
        logger.info("boletins a cada %d min e no fim em %s", args.boletim_min, destino / "boletins")
    if parar is not None and not args.sem_copia:
        copia_dir = Path(args.copia_dir) if args.copia_dir else Path("copias") / destino.name
        copiador = Copiador(destino, copia_dir, args.uf, args.copia_min)
        threading.Thread(target=copiador.executar, args=(parar,), name="copia", daemon=True).start()
        logger.info("cópia de segurança em %s (parciais a cada 5 min, instantâneo a cada %d min e no fim)%s",
                    copia_dir, args.copia_min, "" if args.copia_dir else " — use --copia-dir num OUTRO disco")
    if not args.sem_alertas:
        parar_alertas = parar or threading.Event()
        threading.Thread(target=app.state.vigia.executar, args=(parar_alertas,), name="alertas", daemon=True).start()
    url = f"http://localhost:{args.porta}/"
    print(f"\nApuração — {destino} ({args.uf}): {url}  (Ctrl+C encerra)\n", flush=True)
    if args.abrir:
        threading.Timer(1.5, _abrir_chrome, [url]).start()
    try:
        uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
    finally:
        if parar is not None:
            parar.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
