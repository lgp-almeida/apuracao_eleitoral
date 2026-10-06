"""Análise das parciais de uma noite de apuração: TSE × coletor (TODO 21, rodada 42). Sem rede.

    python analisar_coleta.py --dados dados_2026/oficial                       # resumo no terminal
    python analisar_coleta.py --dados dados_2026/oficial_t2 --saida saidas/coleta_t2.xlsx --grafico saidas/coleta_t2.png
    python analisar_coleta.py --dados copias/oficial                           # a partir da cópia de segurança
    python analisar_coleta.py --dados dados_2026/oficial --log vigia.log       # cruza as pausas com os reinícios

Mede, a partir de <dados>/raw/ e raw_brasil/ (cada versão distinta de cada JSON do TSE que o coletor gravou):
atraso da coleta (chegada − geração), anúncio × publicação (o EA20 gerado depois do anúncio do EA15 e as versões
anteriores que chegaram antes dele), atraso do próprio TSE por janela de 30 min, pausas do TSE e nossas, o critério
do coletor (versão anterior) e o fim da noite. Detalhes em apuracao/divulgacao/analise.py.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

from apuracao.divulgacao import analise as an

logger = logging.getLogger("analisar_coleta")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Análise das parciais de uma noite de apuração (TSE × coletor).")
    p.add_argument("--dados", type=Path, required=True, help="pasta do coletor (ou da cópia), com raw/")
    p.add_argument("--pausa-min", type=float, default=10, help="intervalo sem novidade que conta como pausa (min)")
    p.add_argument("--log", type=Path, help="log do vigia/site: as linhas com 'reinici' entram ao lado das pausas")
    p.add_argument("--saida", type=Path, help="planilha .xlsx com versões, totalizações e indicadores")
    p.add_argument("--grafico", type=Path, help="PNG: %% apurado na UF anunciado pelo TSE × o que chegou aqui")
    p.add_argument("--cargo-grafico", type=int, default=3, help="cargo do gráfico (padrão: 3, governador)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def reinicios(log: Path) -> pl.DataFrame:
    """Linhas do log com 'reinici' e a hora no início (AAAA-MM-DD HH:MM:SS ou HH:MM:SS)."""
    linhas = []
    for texto in log.read_text(errors="replace").splitlines():
        if "reinici" not in texto.lower():
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2})", texto)
        linhas.append({"HORA": m.group(1) if m else None, "LINHA": texto.strip()[:200]})
    return pl.DataFrame(linhas, schema={"HORA": pl.String, "LINHA": pl.String})


def grafico(tse: pl.DataFrame, aqui: pl.DataFrame, destino: Path, titulo: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    ax.step(tse["HORA"].to_list(), tse["PCT"].to_list(), where="post", label="anunciado pelo TSE (acompanhamento)")
    ref = aqui["REFERENCIA"][0] if aqui.height else "chegada"
    ax.step(aqui["HORA"].to_list(), aqui["PCT"].to_list(), where="post", label=f"em disco aqui (EA20 da UF; hora de {ref})")
    ax.set_ylabel("% de seções totalizadas")
    ax.set_title(titulo)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if not (a.dados / "raw").exists():
        print(f"{a.dados}/raw não existe: nada a analisar", file=sys.stderr)
        return 1
    versoes, anuncios = an.ler(a.dados)
    if versoes.is_empty():
        print(f"{a.dados}/raw sem versões", file=sys.stderr)
        return 1
    pub = an.publicacao(anuncios, versoes)
    tabelas = {
        "atraso_coleta": an.atraso_coleta(versoes),
        "publicacao_resumo": an.resumo_publicacao(pub),
        "atraso_tse_30min": an.atraso_tse_por_janela(pub),
        "pausas": an.pausas(versoes, a.pausa_min),
        "peculiaridades": an.peculiaridades(anuncios, pub),
        "fim_da_noite": an.fim_da_noite(versoes, anuncios),
    }
    if a.log:
        tabelas["reinicios_no_log"] = reinicios(a.log)
    crit = an.criterio(pub)

    with pl.Config(tbl_rows=40, tbl_width_chars=160, fmt_str_lengths=60):
        print(f"{a.dados}: {versoes.height} versões ({versoes['CHEGADA'].min()} a {versoes['CHEGADA'].max()}), "
              f"{an.anuncios_distintos(anuncios).height} totalizações anunciadas")
        for nome, df in tabelas.items():
            print(f"\n== {nome.replace('_', ' ')}\n{df}")
        print("\n== critério do coletor (versão anterior)")
        for k, val in crit.items():
            print(f"  {k.replace('_', ' ')}: {val:,}".replace(",", "."))

    if a.saida:
        a.saida.parent.mkdir(parents=True, exist_ok=True)
        planilhas = {"resumo": pl.DataFrame({"ITEM": list(crit), "VALOR": [str(x) for x in crit.values()]}),
                     **tabelas, "totalizacoes": pub.drop("HASHES_ANTERIORES"),
                     "versoes": versoes}
        import xlsxwriter
        with xlsxwriter.Workbook(str(a.saida)) as wb:
            for nome, df in planilhas.items():
                df.write_excel(wb, worksheet=nome[:31], autofit=True)
        print(f"\nplanilha: {a.saida}")
    if a.grafico:
        ufs = versoes.filter(pl.col("ESCOPO") == "uf")["UF"].unique().to_list()
        uf = ufs[0] if ufs else "RJ"
        tse, aqui = an.linha_do_tempo(versoes, anuncios, uf, a.cargo_grafico)
        grafico(tse, aqui, a.grafico, f"{uf}: % apurado — TSE × coleta ({datetime.now():%d/%m/%Y})")
        print(f"gráfico: {a.grafico}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
