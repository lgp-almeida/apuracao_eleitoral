"""Site local de acompanhamento da apuração 2026 (abrir no Chrome).

    python site_apuracao.py --ambiente simulado --coletar          # coleta + site num só comando
    python site_apuracao.py --ambiente oficial --coletar --abrir   # noite da eleição
    python site_apuracao.py --ambiente oficial                     # só o site (coletor rodando à parte)

Com --coletar, o coletor (coletar_resultados.py) roda numa thread do mesmo processo, e o boletim para a
equipe (HTML de um arquivo + planilha) é gravado a cada hora e no fim em <dados>/boletins/ (--sem-boletim desliga),
e a cópia de segurança vai para --copia-dir (padrão copias/<nome dos dados>; prefira outro disco): as parciais do TSE
(raw/) a cada 5 min e um instantâneo do resto por hora e no fim (--sem-copia desliga).
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
from apuracao.divulgacao.cliente import AMBIENTES, ClienteDivulgacao
from apuracao.divulgacao.coletor import Coletor, destino_padrao
from apuracao.web.app import create_app, eh_loopback

logger = logging.getLogger("site_apuracao")
CHROME_WINDOWS = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Site local da apuração 2026.")
    p.add_argument("--ambiente", choices=sorted(AMBIENTES), default="simulado")
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 para acessar de outra máquina da rede")
    p.add_argument("--dados", help="diretório de dados (padrão: dados_2026/<ambiente>)")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--coletar", action="store_true", help="rodar o coletor junto")
    p.add_argument("--intervalo", type=float, default=60.0, help="segundos entre ciclos do coletor")
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
    coletor = Coletor(ClienteDivulgacao(args.ambiente), destino, args.uf, args.turno)

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
    destino = Path(args.dados) if args.dados else destino_padrao(args.ambiente, turno=args.turno)
    status: dict[str, Any] = {"ativo": False, "intervalo_s": args.intervalo} if args.coletar else {}
    parar = _iniciar_coletor(args, destino, status) if args.coletar else None
    referencia = Path(args.comparar_com) if args.comparar_com else Path(f"dados_2026/historico_2022_t{args.turno}")
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
