"""Reconstitui a apuração seção a seção (hora da 1ª totalização de cada seção) e mede o erro da
projeção e do parcial frente ao final. Gera as calibrações `MARGEM_PP` (apuracao/projecao.py) e
`SIGMA` (apuracao/projecao_cadeiras.py), já no formato de colar no código, e as valida — com as
constantes ATUAIS e com as PROPOSTAS. Guia completo: docs/RECALIBRAR_MARGENS.md.

    python validar_projecao.py                            # majoritários, 2022 (Presidente 27 UFs; Gov/Sen nas UFs com votacao_secao no cache)
    python validar_projecao.py --anos 2022 2026           # 2022 + 2026 juntos (depois da publicação de 2026)
    python validar_projecao.py --deputados --anos 2022 2026
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import cadeiras as cd
from apuracao import projecao as pj
from apuracao import projecao_cadeiras as pc

UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()


def rodar(ano: int, cache: Path, ufs: list[str], turnos: tuple[int, ...] = (1, 2)) -> pl.DataFrame:
    """Erros da projeção e do parcial. Presidente nas UFs pedidas; Governador (1º e 2º turno) e Senador (1º) nas
    UFs cujo votacao_secao do ano está no cache (rodada 44: antes, só o RJ). Turno sem seções (ex.: 2026 antes do
    2º turno; Governador do RJ em 2022, sem 2º turno) é pulado."""
    det = pj.detalhe_nacional(ano, cache)
    br = v.load_section_votes(ano, "BR", "presidente", cache, False)  # arquivo nacional (todas as UFs)
    casos = [(uf, 1, "PRESIDENTE", t, None) for uf in ufs for t in turnos]
    for uf in ufs:
        if (cache / f"votacao_secao_{ano}_{uf}.zip").exists():
            est = v.load_section_votes(ano, uf, "governador", cache, False)
            casos += [(uf, 3, "GOVERNADOR", t, est) for t in turnos] + [(uf, 5, "SENADOR", 1, est)]
    partes = []
    for uf, cargo, nome, turno, votes in casos:
        s = pj.secoes_com_hora(ano, uf, cargo, turno, cache, det)
        if s.drop_nulls("T").is_empty():
            continue
        vo = pj.votos_por_secao(br if votes is None else votes, uf, nome, turno)
        if vo.is_empty():
            continue
        partes.append(pj.backtest(s, vo).with_columns(
            pl.lit(uf).alias("UF"), pl.lit(nome).alias("CARGO"), pl.lit(turno).alias("TURNO")))
        logging.info("%s %s %s %sº turno: %d seções", ano, uf, nome, turno, s.height)
    return pl.concat(partes)


def entrada_oficial(ano: int, cargo: int, cache: Path, uf: str = "RJ") -> tuple:
    """Votos e eleitos oficiais para as cadeiras: os microdados oficiais (`cd.entrada_munzona`) ou, enquanto o TSE
    não publica o votacao_partido_munzona do ano (2026 em 06/10), o resultado importado com a destinação oficial
    (`historico_<ano>_t1`, rodada 40: as mesmas cadeiras da noite, 46/46 e 70/70)."""
    try:
        return cd.entrada_munzona(ano, uf, cargo, cache)
    except (v.TseDataError, requests.RequestException) as exc:
        from apuracao.ufs import dir_uf
        pasta = dir_uf(Path(f"dados_2026/historico_{ano}_t1"), uf) / "ultimo"
        if not (pasta / "candidatos.parquet").exists():
            raise
        logging.warning("%s: sem os microdados oficiais das cadeiras (%s); uso %s", ano, exc, pasta)
        tot, cand, part = (pl.read_parquet(pasta / f"{n}.parquet") for n in ("totais", "candidatos", "partidos"))
        agr, c, vagas, validos = cd.entrada_divulgacao(tot, cand, part, cargo, uf)
        return agr, c.drop("DESEMPATE").with_columns(pl.col("SITUACAO_TSE").str.to_uppercase()), vagas, validos


def deputados(anos: list[int], cache: Path) -> None:
    """σ do log-erro dos votos projetados (agremiações e candidatos com ≥ 10% do QE), proposta de
    `SIGMA` com todos os anos e validação de consolidados × em disputa e das faixas de cadeiras,
    ano a ano, com o σ ATUAL (para 2026 é o teste fora da amostra) e com o PROPOSTO."""
    erros, casos = [], []
    for ano in anos:
        votes = v.load_section_votes(ano, "RJ", "deputado estadual", cache, False)
        for cargo, nome in ((7, "DEPUTADO ESTADUAL"), (6, "DEPUTADO FEDERAL")):
            agr, cand, vagas, validos = entrada_oficial(ano, cargo, cache)
            secoes = pj.secoes_com_hora(ano, "RJ", cargo, 1, cache)
            va_s, vc_s = pc.votos_secao_deputado(votes, cand, nome)
            erros.append(pc.calibrar_sigma(secoes, va_s, vc_s, [5] + list(range(10, 100, 5)),
                                           0.1 * cd.quociente_eleitoral(validos, vagas)).with_columns(pl.lit(ano).alias("ANO")))
            casos.append((ano, nome, agr, cand, vagas, validos, secoes, va_s, vc_s))
    e = pl.concat(erros)
    proposta = pc.calibrar_tabela_sigma(e)
    linhas = []
    for ano, nome, agr, cand, vagas, validos, secoes, va_s, vc_s in casos:
        oficiais = set(cand.filter(pl.col("SITUACAO_TSE").str.starts_with("ELEITO"))["NUMERO"])
        of_vagas = dict(cd.distribuir(agr, cand, vagas, validos).agremiacoes.select("AGREMIACAO", "VAGAS").iter_rows())
        info = cand.select("AGREMIACAO", "NUMERO", "NOME", "VALIDO").with_columns(pl.lit(None, pl.Int64).alias("DESEMPATE"))
        for pct, t in pc.momentos(secoes, list(range(10, 100, 10))):
            estado = pc.estado_em(secoes, va_s, vc_s, t)
            for rotulo, tab in (("atual", None), ("proposta", proposta)):
                p = pc.projetar_cadeiras(*estado, info, vagas, tabela_sigma=tab)
                st = p.candidatos.select("NUMERO", "STATUS")
                cons = set(st.filter(pl.col("STATUS") == "consolidado")["NUMERO"])
                disp = set(st.filter(pl.col("STATUS").str.starts_with("em disputa"))["NUMERO"])
                ag = p.agremiacoes.to_dicts()
                linhas.append({"ANO": ano, "CARGO": nome, "PCT": pct, "SIGMA": rotulo, "CONSOLIDADOS": len(cons),
                               "CONSOLIDADOS_ERRADOS": len(cons - oficiais), "EM_DISPUTA": len(disp),
                               "ELEITOS_FORA_DAS_DUAS": len(oficiais - cons - disp),
                               "FAIXAS_QUE_NAO_COBREM": sum(not (r["VAGAS_MIN"] <= of_vagas.get(r["AGREMIACAO"], 0) <= r["VAGAS_MAX"])
                                                            for r in ag)})
    r = pl.DataFrame(linhas)
    with pl.Config(tbl_rows=200, tbl_cols=20, tbl_width_chars=200):
        faixa = (pl.col("PCT") // 10 * 10).clip(upper_bound=90).alias("FAIXA")
        print("\nσ DO LOG-ERRO POR ANO E FAIXA")
        print(e.with_columns(faixa).group_by("ANO", "TIPO", "FAIXA").agg(pl.col("LOG_ERRO").std().round(3))
              .pivot(on="TIPO", index=["ANO", "FAIXA"], values="LOG_ERRO").sort("ANO", "FAIXA"))
        print("\nVALIDAÇÃO (σ atual × proposto), por ano e cargo")
        print(r.group_by("ANO", "CARGO", "SIGMA").agg(pl.col("CONSOLIDADOS", "CONSOLIDADOS_ERRADOS", "EM_DISPUTA",
                                                              "ELEITOS_FORA_DAS_DUAS", "FAIXAS_QUE_NAO_COBREM").sum())
              .sort("ANO", "CARGO", "SIGMA"))
    print("\nATUAL:    ", pj.formatar_tabela("SIGMA", pc.SIGMA))
    print("PROPOSTA: ", pj.formatar_tabela("SIGMA", proposta))
    print("iguais" if [tuple(x) for x in proposta] == [tuple(x) for x in pc.SIGMA] else "DIFERENTES — ver docs/RECALIBRAR_MARGENS.md")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--anos", type=int, nargs="+", default=[2022], help="eleições a usar (juntas)")
    ap.add_argument("--ano", type=int, help="(antigo) um só ano; equivale a --anos ANO")
    ap.add_argument("--cache-dir", type=Path, default=Path("cache_tse"))
    ap.add_argument("--ufs", nargs="+", default=UFS)
    ap.add_argument("--turnos", type=int, nargs="+", default=[1, 2], choices=[1, 2])
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--deputados", action="store_true", help="calibra/valida a projeção das cadeiras (RJ)")
    a = ap.parse_args()
    anos = [a.ano] if a.ano else a.anos
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.deputados:
        deputados(anos, a.cache_dir)
        return
    erros = pl.concat([rodar(ano, a.cache_dir, a.ufs, tuple(a.turnos)).with_columns(pl.lit(ano).alias("ANO"))
                       for ano in anos])
    if a.saida:
        a.saida.parent.mkdir(parents=True, exist_ok=True)
        erros.write_parquet(a.saida)
    faixa = (pl.col("PCT_APURADO") // 10 * 10).clip(upper_bound=90).alias("FAIXA")
    grupos = [erros.with_columns(pl.lit("todas").alias("GRUPO"))]
    grupos.append(erros.filter(pl.col("UF") == "RJ").with_columns(pl.lit("RJ").alias("GRUPO")))
    q = pl.concat(grupos).with_columns(faixa).group_by("ANO", "GRUPO", "FAIXA").agg(
        pl.len().alias("N"), pl.col("ERRO_PARCIAL").mean().round(2).alias("PARCIAL_MEDIO"),
        pl.col("ERRO_PROJECAO").mean().round(2).alias("PROJ_MEDIO"),
        pl.col("ERRO_PARCIAL").quantile(0.95).round(2).alias("PARCIAL_P95"),
        pl.col("ERRO_PROJECAO").quantile(0.95).round(2).alias("PROJ_P95"),
        pl.col("ERRO_PROJECAO").max().round(2).alias("PROJ_MAX")).sort("ANO", "GRUPO", "FAIXA")
    proposta = pj.calibrar(erros)
    with pl.Config(tbl_rows=200):
        print(q)
        # o 2º turno (2 candidatos) erra diferente do 1º? (rodada 44: decide se precisa de margem própria)
        por_turno = (erros.with_columns(faixa).group_by("TURNO", "FAIXA")
                     .agg(pl.len().alias("N"), pl.col("ERRO_PROJECAO").quantile(0.95).round(2).alias("PROJ_P95"),
                          pl.col("ERRO_PARCIAL").quantile(0.95).round(2).alias("PARCIAL_P95"))
                     .pivot(on="TURNO", index="FAIXA", values=["N", "PROJ_P95", "PARCIAL_P95"]).sort("FAIXA"))
        print("\nPOR TURNO (p95 do erro, em p.p.)")
        print(por_turno)
        print("\nPOR CARGO E TURNO (p95 do erro da projeção com 30% ou mais apurado)")
        print(erros.filter(pl.col("PCT_APURADO") >= 30).group_by("ANO", "CARGO", "TURNO")
              .agg(pl.len().alias("N"), pl.col("ERRO_PROJECAO").quantile(0.95).round(2).alias("PROJ_P95"),
                   pl.col("ERRO_PARCIAL").quantile(0.95).round(2).alias("PARCIAL_P95")).sort("ANO", "CARGO", "TURNO"))
    for t in sorted(erros["TURNO"].unique().to_list()):
        x = erros.filter(pl.col("TURNO") == t)
        print(f"  {t}º turno: cobertura atual {pj.cobertura(x):.3f} · proposta conjunta {pj.cobertura(x, proposta):.3f}"
              f" · proposta só do turno: {pj.formatar_tabela(f'MARGEM_PP_{t}T', pj.calibrar(x))}")
    print("\nCOBERTURA (fração das projeções dentro da margem; alvo ≈ 0,95)")
    for ano in anos:
        x = erros.filter(pl.col("ANO") == ano)
        rj = x.filter(pl.col("UF") == "RJ")
        print(f"  {ano}: atual {pj.cobertura(x):.3f} · proposta {pj.cobertura(x, proposta):.3f}"
              f"  | só RJ: atual {pj.cobertura(rj):.3f} · proposta {pj.cobertura(rj, proposta):.3f}")
    # uma tabela por turno (rodada 44): MARGEM_PP (1º) e MARGEM_PP_2T (2º)
    for t, nome, atual in ((1, "MARGEM_PP", pj.MARGEM_PP), (2, "MARGEM_PP_2T", pj.MARGEM_PP_2T)):
        x = erros.filter(pl.col("TURNO") == t)
        if x.is_empty():
            continue
        prop = pj.calibrar(x)
        print(f"\n{t}º TURNO — cobertura: atual {pj.cobertura(x, atual):.3f} · proposta {pj.cobertura(x, prop):.3f}")
        print("ATUAL:    ", pj.formatar_tabela(nome, atual))
        print("PROPOSTA: ", pj.formatar_tabela(nome, prop))
        print("iguais" if prop == atual else "DIFERENTES — ver docs/RECALIBRAR_MARGENS.md")


if __name__ == "__main__":
    main()
