"""Mapa por local de votação: um ponto por local (estado inteiro, coordenada do cadastro de eleitorado).

Três camadas, todas sobre os caches de `PerfilVotoLocal` (apuracao/perfil_local.py) — nada é recalculado:
  * "voto": as métricas do mapa por bairro (mais votado, % e votos de um candidato, brancos/nulos,
    abstenção/comparecimento), dos microdados por seção somados por local;
  * "perfil": um indicador do eleitorado (TSE do ano) ou do entorno (Censo 2022 por setor, raio de 800 m);
  * "residuo": o resíduo do Perfil × voto (p.p.) — quanto o candidato/partido foi melhor (+) ou pior (−)
    no local do que a reta voto × indicador prevê. É o "onde o voto foge do perfil".

Só com microdados (resultado final, por seção): o tempo real vai no máximo até o município.
"""

from __future__ import annotations

from typing import Any

import polars as pl

import votos_por_local_votacao as v
from apuracao import bairros as br
from apuracao import perfil as pf

CAMADAS = {"voto": "Voto", "perfil": "Perfil do eleitorado", "residuo": "Resíduo do Perfil × voto"}


def alvo(ano: int, cargo: int, turno: int, numero: int) -> pf.Alvo:
    """Em cargo proporcional, número de 2 dígitos = o PARTIDO (nominais + legenda); senão, o candidato."""
    if cargo in br.PROPORCIONAIS and 0 < numero < 100:
        return pf.Alvo(ano, cargo, turno, None, numero)
    return pf.Alvo(ano, cargo, turno, numero, None)


def pontos(plocal: Any, ano: int, camada: str, cargo: int = 3, turno: int = 1, metrica: str | None = None,
           numero: int | None = None, indicador: str | None = None, municipio: int | None = None,
           min_validos: int = 50) -> dict[str, Any]:
    """Os pontos do mapa. `municipio`: código IBGE (como no Perfil × voto por local). Levanta ValueError
    (pedido inválido) ou TseDataError (microdados ausentes)."""
    if camada not in CAMADAS:
        raise ValueError(f"camada deve ser uma de {sorted(CAMADAS)}")
    loc = plocal.locais(ano)
    extra: dict[str, Any] = {}
    if camada == "voto":
        if metrica not in br.METRICAS:
            raise ValueError(f"métrica indisponível por local: {metrica}. Use: {', '.join(br.METRICAS)}")
        if metrica in br.PARTICIPACAO:
            det = plocal.b._carregar(("detalhe", ano), lambda: v.load_section_details(ano, plocal.b.uf, plocal.b.cache))
            pb = br.participacao_por_bairro(det, cargo, turno, loc.select(v.LOCAL_KEY + [pl.col("UNIDADE").alias("CD_BAIRRO")]))
            if pb.is_empty():
                raise v.TseDataError(f"sem comparecimento de {br.CARGOS[cargo].title()} ({turno}º turno) em {ano}")
            df = br.metrica_participacao(pb, metrica).select("CD_BAIRRO", "VALOR")
            rotulo = f"{br.METRICAS[metrica]} — {br.CARGOS[cargo].title()} {ano}"
        else:
            vb = plocal._vb(ano, cargo, turno)
            if municipio is not None:
                vb = vb.filter(pf.municipio_do_bairro() == municipio)
            df = br.metrica(vb, cargo, metrica, numero)
            rotulo = f"{br.METRICAS[metrica].replace('bairro', 'local')} — {br.CARGOS[cargo].title()} {ano}"
            if numero is not None and metrica in ("pct_candidato", "votos_candidato"):
                nome = vb.filter(pl.col("NR_VOTAVEL") == numero)["NM_VOTAVEL"].head(1).to_list()
                rotulo = f"{br.METRICAS[metrica]} — nº {numero}{' ' + nome[0] if nome else ''} ({br.CARGOS[cargo].title()} {ano})"
            if metrica == "vencedor":
                extra["categorias"] = br.categorias(vb, cargo)
        tipo = "categorico" if metrica == "vencedor" else "sequencial"
        unidade = "%" if metrica.endswith("_pct") or metrica == "pct_candidato" else ""
    elif camada == "perfil":
        indicadores = plocal.indicadores()
        if indicador not in indicadores:
            raise ValueError(f"indicador desconhecido: {indicador}")
        df = plocal.indicador(indicador, ano).select("CD_BAIRRO", pl.col("X").alias("VALOR"))
        rotulo, tipo = f"{indicadores[indicador]['rotulo']} — {ano}", "sequencial"
        unidade = "%" if indicador.startswith("pct_") else ""
        extra["fonte_indicador"] = indicadores[indicador].get("fonte")
    else:
        if numero is None or indicador is None:
            raise ValueError("o resíduo precisa do número (candidato; 2 dígitos = partido) e do indicador")
        d = plocal.dispersao(alvo(ano, cargo, turno, numero), indicador, min_validos, False, municipio)
        df = d["pontos"].select("CD_BAIRRO", pl.col("RESIDUO").alias("VALOR"), pl.col("Y").alias("VOTO"),
                                pl.col("X").alias("INDICADOR"))
        est = d["estatistica"]
        rotulo, tipo, unidade = f"Resíduo (p.p.): {d['rotulo_y']} × {d['rotulo_x']}", "divergente", "p.p."
        extra.update(estatistica={k: est.get(k) for k in ("n", "pearson", "r2", "a", "b", "p")},
                     rotulo_x=d["rotulo_x"], rotulo_y=d["rotulo_y"], min_validos=min_validos)
    base = loc if municipio is None else loc.filter(pl.col("CD_MUN").cast(pl.Int64) == municipio)
    j = base.join(df.rename({"CD_BAIRRO": "UNIDADE"}), on="UNIDADE", how="inner").drop_nulls("VALOR")
    extras = [c for c in ("VOTO", "INDICADOR", "ROTULO") if c in j.columns]
    itens = [{"u": r["UNIDADE"], "lat": r["LAT"], "lon": r["LON"], "nome": r["NM_LOCAL_VOTACAO"], "mun": r["NM_MUN"],
              "zona": r["NR_ZONA"], "local": r["NR_LOCAL_VOTACAO"], "eleitores": r["QT_ELEITORES"],
              "valor": r["VALOR"], **{c.lower(): r[c] for c in extras}}
             for r in j.iter_rows(named=True)]
    return {"camada": camada, "tipo": tipo, "rotulo": rotulo, "unidade": unidade, "ano": ano, "itens": itens,
            "cobertura": {"locais": base.height, "com_valor": len(itens)}, **extra}
