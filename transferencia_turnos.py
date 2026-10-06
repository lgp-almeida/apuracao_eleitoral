"""Transferência de votos do 1º para o 2º turno (inferência ecológica) e abstenção extra.

Microdados do TSE (seção, local de votação ou município como unidade):
    python transferencia_turnos.py --ano 2022 --uf RJ --cargo presidente --nivel secao
    python transferencia_turnos.py --ano 2022 --cargo presidente --nivel local --municipio "Rio de Janeiro" --saida saidas/t.xlsx
    python transferencia_turnos.py --ano 2022 --cargo presidente --comparar-niveis     # viés de agregação

Noite do 2º turno (antes dos microdados), por município, com o que o coletor gravou nos dois turnos:
    python transferencia_turnos.py --dados-1t dados_2026/oficial --dados-2t dados_2026/oficial_t2 --cargo governador

Ver apuracao/transferencia.py (método e ressalvas) e docs/RODADA_30_*.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import polars as pl

import votos_por_local_votacao as v
from apuracao import transferencia as tr

CARGOS = {"presidente": 1, "governador": 3, "prefeito": 11}


def _cargo(texto: str) -> int:
    t = texto.strip().lower()
    if t.isdigit():
        return int(t)
    if t not in CARGOS:
        raise argparse.ArgumentTypeError(f"cargo com 2º turno: {', '.join(CARGOS)}")
    return CARGOS[t]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transferência de votos do 1º para o 2º turno (inferência ecológica).")
    p.add_argument("--ano", type=int, default=2022)
    p.add_argument("--uf", default="RJ", type=str.upper)
    p.add_argument("--cargo", type=_cargo, default=1, help="presidente, governador ou prefeito")
    p.add_argument("--nivel", choices=tr.NIVEIS, default="secao", help="unidade de análise (padrão: seção)")
    p.add_argument("--municipio", help="restringe a um município (nome ou código TSE)")
    p.add_argument("--bootstrap", type=int, default=200, help="replicações do bootstrap (0 = sem intervalo)")
    p.add_argument("--comparar-niveis", action="store_true", help="mesma matriz com seções, locais e municípios")
    p.add_argument("--dados-1t", help="diretório do coletor do 1º turno (tempo real, por município)")
    p.add_argument("--dados-2t", help="diretório do coletor do 2º turno")
    p.add_argument("--saida", help="planilha .xlsx (matriz, validação e uma linha por unidade)")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def imprimir(r: dict, lados: tuple[str, str] = ("1º turno", "2º turno")) -> None:
    """`lados`: como chamar o lado 1 e o 2 (`migracao_votos.py` usa os anos)."""
    eleitores = f"{r['eleitores_1t']:,}".replace(",", ".")
    print(f"\n{r['descricao']} — {r['unidades']} unidades, {eleitores} eleitores")
    linhas = [{f"origem ({lados[0]})": m["origem"], "% do eleitorado": round(m["pct_1t"], 1),
               **{d["destino"]: f"{d['pct']:.1f} ({d['baixo']:.1f}–{d['alto']:.1f})" for d in m["destinos"]}}
              for m in r["matriz"]]
    with pl.Config(tbl_rows=30, tbl_cols=12, tbl_width_chars=200, fmt_str_lengths=40):
        print(f"\nPara onde foi cada grupo ({lados[0]} → {lados[1]}; % e IC 95% do bootstrap):")
        print(pl.DataFrame(linhas))
    a = r["abstencao"]
    print(f"\nAbstenção: {a['pct_1t']:.2f}% ({lados[0]}) → {a['pct_2t']:.2f}% ({lados[1]}) ({a['extra_pp']:+.2f} p.p.)")
    novos = ", ".join(f"{n['origem']}: {n['eleitores']:,}".replace(",", ".") for n in a["novos_abstencionistas"])
    print(f"Quem votou ({lados[0]}) e se absteve ({lados[1]}) (estimado): {novos}")
    print("Ajuste (R² ponderado): " + ", ".join(f"{k} {x:.3f}" for k, x in r["r2"].items()))
    val = r.get("validacao")
    if val:
        print(f"Validação cruzada ({val['dobras']} dobras; blocos = locais, ou municípios): erro fora da amostra "
              f"{val['rmse_modelo_medio_pp']:.2f} p.p. × matriz única {val['rmse_matriz_unica_medio_pp']:.2f} × "
              f"swing uniforme {val['rmse_swing_medio_pp']:.2f} p.p.")
    print("\nInferência ECOLÓGICA: padrão médio entre unidades, não o voto de pessoas; o IC não inclui o viés de "
          "agregação" + (" (compare os níveis com --comparar-niveis)." if lados[0] == "1º turno" else "."))


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    cache = Path(a.cache_dir)
    try:
        if a.dados_1t or a.dados_2t:
            if not (a.dados_1t and a.dados_2t):
                raise ValueError("use --dados-1t e --dados-2t juntos")
            u = tr.unidades_divulgacao(Path(a.dados_1t), Path(a.dados_2t), a.cargo, a.uf)
            res = tr.analisar(u, n_boot=a.bootstrap)
        else:
            municipio = None
            if a.municipio:
                votos_mun = v.load_section_votes(a.ano, a.uf, tr.NOMES_CARGO.get(a.cargo, "presidente"), cache, False)
                municipio = int(a.municipio) if a.municipio.isdigit() else v.resolve_municipality(votos_mun, a.municipio)
            secoes, votos, nomes = tr.carregar_microdados(a.ano, a.uf, a.cargo, cache, municipio)
            if a.comparar_niveis:
                c = tr.comparar_niveis(secoes, votos, nomes, municipio)
                for nivel, d in c["niveis"].items():
                    print(f"\n{nivel}: {d['unidades']} unidades; maior diferença para as seções "
                          f"{d['max_dif_pp_vs_secao']:.1f} p.p.")
                    print(pl.DataFrame(d["matriz_pct"], schema=c["categorias_2t"], orient="row").with_columns(
                        pl.Series("origem", c["categorias_1t"])).select("origem", *c["categorias_2t"]))
                return 0
            res = tr.calcular(a.ano, a.uf, a.cargo, a.nivel, cache, municipio, a.bootstrap)
    except (v.TseDataError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    r = tr.resumo(res)
    imprimir(r)
    if a.saida:
        Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
        tr.para_planilha(r, res.por_unidade, Path(a.saida))
        print(f"\nplanilha: {a.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
