"""Baixar e preparar os dados de várias UFs (ou de todas) de uma vez.

    python baixar_ufs.py --so-plano                                   # o que falta, sem baixar nada
    python baixar_ufs.py --etapas divulgacao historico               # resultado 2026 + 2022 das 27 UFs
    python baixar_ufs.py --ufs SP MG --anos 2022 2018 2014 --turnos 1 2
    python baixar_ufs.py --etapas microdados --vigiar                # espera o TSE publicar a votação por seção de 2026

Em segundo plano, com log:
    nohup python baixar_ufs.py --etapas divulgacao historico > lote_ufs.log 2>&1 &

Cada UF fica em dados_2026/<base>_<UF> (oficial_SP, historico_2022_t1_SP…; no RJ, as pastas antigas sem a UF).
O estado de cada UF × etapa fica em dados_2026/lote_ufs.json: rodar de novo retoma do que faltou (--refazer
refaz tudo). A divulgação usa UM limite de acessos ao TSE para todas as UFs (--max-rps, padrão 10/s).
Depois: python site_apuracao.py --ufs todas --porta 8001   (site com seletor de UF)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import polars as pl

from apuracao import lote_ufs as lt
from apuracao import ufs as uf_mod
from apuracao.divulgacao.cliente import AMBIENTES

logger = logging.getLogger("baixar_ufs")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Baixar e preparar os dados de várias UFs.")
    p.add_argument("--ufs", nargs="+", default=["todas"], help="siglas (ex.: SP MG) ou 'todas' (padrão)")
    p.add_argument("--etapas", nargs="+", choices=lt.ETAPAS, default=list(lt.ETAPAS))
    p.add_argument("--anos", nargs="+", type=int, default=[2022], help="anos do histórico (padrão: 2022)")
    p.add_argument("--turnos", nargs="+", type=int, choices=[1, 2], default=[1])
    p.add_argument("--anos-eleitorado", nargs="+", type=int, default=[2022, 2026])
    p.add_argument("--ambiente", choices=sorted(AMBIENTES), default="oficial")
    p.add_argument("--raiz", type=Path, default=Path("dados_2026"))
    p.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    p.add_argument("--max-rps", type=float, default=10.0, help="acessos por segundo ao TSE, somando TODAS as UFs")
    p.add_argument("--refazer", action="store_true", help="refazer também o que já está completo")
    p.add_argument("--so-plano", action="store_true", help="só mostrar o que seria feito (nada é baixado)")
    p.add_argument("--vigiar", action="store_true", help="repetir o que ficou 'aguardando' a cada --intervalo")
    p.add_argument("--intervalo", type=float, default=3600, help="segundos entre repetições com --vigiar (mín. 600)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def imprimir(df: pl.DataFrame) -> None:
    with pl.Config(tbl_rows=40, tbl_cols=20, tbl_width_chars=200, fmt_str_lengths=20, tbl_hide_dataframe_shape=True):
        print(df)


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    try:
        ufs = uf_mod.lista(a.ufs)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    cfg = lt.Config(ufs=ufs, etapas=tuple(a.etapas), anos=tuple(a.anos), turnos=tuple(a.turnos),
                    anos_eleitorado=tuple(a.anos_eleitorado), ambiente=a.ambiente, raiz=a.raiz, cache=a.cache_dir,
                    max_rps=a.max_rps, refazer=a.refazer)
    lote = lt.Lote(cfg)
    tarefas = lote.tarefas()
    faltam = [(c, u) for c, u, _ in tarefas if not lote.ja_feita(c, u)]
    print(f"{len(ufs)} UF(s), {len(tarefas)} tarefas, {len(faltam)} a fazer "
          f"({len(tarefas) - len(faltam)} já feitas, ver {cfg.raiz / lt.ARQUIVO_ESTADO})")
    if a.so_plano:
        por_etapa: dict[str, list[str]] = {}
        for c, u in faltam:
            por_etapa.setdefault(c, []).append(u)
        for c, us in por_etapa.items():
            print(f"  {c:<22} {len(us):>2} UF(s): {' '.join(us)}")
        if "divulgacao" in cfg.etapas:
            n = sum(1 for c, _ in faltam if c.startswith("divulgacao"))
            print(f"  divulgação: ~1.000 acessos por UF média (SP ~3.500); a {cfg.max_rps:g}/s, "
                  f"~{n * 1000 / cfg.max_rps / 60:.0f} min")
        return 0

    def ao_terminar(chave: str, uf: str, r: lt.Resultado) -> None:
        print(f"{uf} {chave:<20} {r.situacao:<12} {r.segundos:6.1f}s  {r.detalhe}", flush=True)

    intervalo = max(a.intervalo, 600)
    while True:
        try:
            estado = lote.executar(ao_terminar)
        except KeyboardInterrupt:
            print("\ninterrompido; rode de novo para continuar do ponto em que parou")
            return 130
        print()
        imprimir(lt.resumo(estado, ufs))
        aguardando = [(u, c) for u in ufs for c, e in estado.get(u, {}).items() if e["situacao"] == lt.AGUARDANDO]
        problemas = [(u, c) for u in ufs for c, e in estado.get(u, {}).items()
                     if e["situacao"] in (lt.ERRO, lt.INCOMPLETO, lt.PENDENTE)]
        if not a.vigiar or not aguardando:
            if problemas:
                print(f"\n{len(problemas)} tarefa(s) com erro, incompleta(s) ou pendente(s): rode de novo para tentar "
                      f"outra vez (detalhes em {cfg.raiz / lt.ARQUIVO_ESTADO})")
            return 1 if problemas else 0
        logger.info("%d tarefa(s) aguardando o TSE; nova verificação em %.0f min", len(aguardando), intervalo / 60)
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main())
