"""Abstenção × mudança de local de votação entre duas eleições, por seção (rodada 56).

    python abstencao_mudanca_local.py --uf RJ                  # saidas/RJ/abstencao_mudanca_local_2022_2026.xlsx
    python abstencao_mudanca_local.py --uf todas               # uma planilha por UF
    python abstencao_mudanca_local.py --uf SP --ano-base 2022 --ano 2026 --turno 1 --saida x.xlsx

Usa só o cache (votos e detalhe por seção, cadastros de eleitorado e de candidatos dos dois anos): o que faltar é
baixado pelo núcleo. Método e ressalvas na aba LEIA-ME e em `apuracao/abstencao_locais.py`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import abstencao_locais as al
from apuracao import ufs as uf_mod

logger = logging.getLogger("abstencao_mudanca_local")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Abstenção por local de votação: seções que mudaram de lugar × as que ficaram.")
    p.add_argument("--uf", nargs="+", default=["RJ"], help="sigla(s) ou 'todas'")
    p.add_argument("--ano-base", type=int, default=2022)
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--turno", type=int, choices=[1, 2], default=1)
    p.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    p.add_argument("--saida", type=Path, help="arquivo .xlsx (só com uma UF); padrão saidas/<UF>/...")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _br(x: float, fmt: str) -> str:
    """Número no formato brasileiro (1.234,56)."""
    return format(x, fmt).replace(",", "_").replace(".", ",").replace("_", ".")


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        ufs = uf_mod.lista(a.uf)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if a.saida and len(ufs) > 1:
        print("--saida só com uma UF", file=sys.stderr)
        return 2
    falhas = []
    linhas: list[dict] = []
    perdidos: list[pl.DataFrame] = []
    for uf in ufs:
        destino = a.saida or Path("saidas") / uf / f"abstencao_mudanca_local_{a.ano_base}_{a.ano}{'_t2' if a.turno == 2 else ''}.xlsx"
        try:
            r = al.gerar(uf, a.cache_dir, a.ano_base, a.ano, a.turno)
            al.escrever(r, destino)
        except (v.TseDataError, requests.RequestException, OSError) as exc:
            logger.error("%s: %s", uf, exc)
            falhas.append(uf)
            continue
        geral = r.resumo.row(0, named=True) if r.resumo.height else {}
        linhas.append(_linha_uf(r, geral))
        perdidos.append(r.perdidos.with_columns(pl.lit(uf).alias("UF")))
        print(f"{uf}: {' · '.join(r.notas)}")
        if geral:
            print(f"   excesso de abstenção nas seções que mudaram: {_br(geral['EXCESSO_PP'], '+.2f')} p.p. "
                  f"(IC 95% {_br(r.ic[0], '+.2f')} a {_br(r.ic[1], '+.2f')}); "
                  f"{_br(geral['ELEITORES_A_MAIS_ABSTENDO'], ',.0f')} eleitores a mais abstendo → {destino}")
    if len(ufs) > 1 and linhas:
        destino = Path("saidas") / "BR" / f"abstencao_mudanca_local_{a.ano_base}_{a.ano}{'_t2' if a.turno == 2 else ''}_ufs.xlsx"
        consolidar(pl.DataFrame(linhas), pl.concat(perdidos, how="diagonal_relaxed"), destino)
        print(f"consolidado das UFs → {destino}")
    if falhas:
        print("falharam:", " ".join(falhas), file=sys.stderr)
    return 1 if falhas else 0


def _linha_uf(r: al.Relatorio, geral: dict) -> dict:
    classes = r.secoes.group_by("CLASSE").len()
    n = dict(classes.iter_rows())
    sn = f"_{r.novo}"
    return {"UF": r.uf, "SECOES_MUDOU": n.get(al.MUDOU, 0), "SECOES_MANTEVE": n.get(al.MANTEVE, 0),
            "SECOES_RENUMERADO": n.get(al.RENUMERADO, 0), "SECOES_FORA": n.get(al.FORA, 0),
            f"APTOS_MUDOU{sn}": geral.get("APTOS" + sn), "PCT_ELEITORADO_MUDOU":
                100 * (geral.get("APTOS" + sn) or 0) / r.secoes["APTOS" + sn].sum(),
            "DELTA_MUDOU_PP": geral.get("DELTA_PP"), "DELTA_CONTROLE_PP": geral.get("DELTA_CONTROLE_PP"),
            "EXCESSO_PP": geral.get("EXCESSO_PP"), "IC95_INF": r.ic[0], "IC95_SUP": r.ic[1],
            "SIGNIFICATIVO": bool(r.ic[0] > 0 or r.ic[1] < 0),
            "ELEITORES_A_MAIS_ABSTENDO": geral.get("ELEITORES_A_MAIS_ABSTENDO")}


def consolidar(ufs: pl.DataFrame, perdidos: pl.DataFrame, destino: Path) -> Path:
    """Uma linha por UF (efeito e IC) + o Presidente somado no país (votos perdidos estimados por candidato)."""
    pres = (perdidos.filter(pl.col("CARGO") == "Presidente")
            .group_by("NUMERO", "NOME", "PARTIDO").agg(pl.col("VOTOS_UF").sum().alias("VOTOS_NAS_UFS"),
                                                      pl.col("VOTOS_PERDIDOS_EST").sum())
            .with_columns((100 * pl.col("VOTOS_PERDIDOS_EST") / pl.col("VOTOS_NAS_UFS")).alias("PERDA_PCT_DOS_SEUS_VOTOS"))
            .sort("VOTOS_NAS_UFS", descending=True))
    por_uf = (perdidos.filter((pl.col("CARGO") == "Presidente") & pl.col("NUMERO").is_in(pres.head(3)["NUMERO"].to_list()))
              .pivot(on="NOME", index="UF", values="VOTOS_PERDIDOS_EST"))
    gov = perdidos.filter(pl.col("CARGO") == "Governador").select("UF", *[c for c in perdidos.columns if c not in ("UF", "CARGO")])
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp.xlsx")
    from xlsxwriter import Workbook
    with Workbook(str(tmp), {"nan_inf_to_errors": True}) as wb:
        neg = wb.add_format({"bold": True})
        for nome, df in (("UFs", ufs.sort("EXCESSO_PP", descending=True, nulls_last=True)),
                         ("Presidente no país", pres), ("Presidente por UF", por_uf), ("Governador por UF", gov)):
            ws = wb.add_worksheet(nome)
            al._tabela(ws, df, 0, neg)
            ws.freeze_panes(1, 1)
    tmp.replace(destino)
    return destino


if __name__ == "__main__":
    sys.exit(main())
