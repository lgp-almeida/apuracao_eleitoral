"""Mapa por local de votação: um ponto por local (estado inteiro, coordenada do cadastro de eleitorado).

Cinco camadas, sobre os caches de `PerfilVotoLocal` (apuracao/perfil_local.py) — nada é recalculado:
  * "voto": as métricas do mapa por bairro (mais votado, % e votos de um candidato, brancos/nulos,
    abstenção/comparecimento), dos microdados por seção somados por local;
  * "perfil": um indicador do eleitorado (TSE do ano) ou do entorno (Censo 2022 por setor, raio de 800 m);
  * "residuo": o resíduo do Perfil × voto (p.p.) — quanto o candidato/partido foi melhor (+) ou pior (−)
    no local do que a reta voto × indicador prevê. É o "onde o voto foge do perfil";
  * "variacao" (rodada 46, TODO 17a): quanto a métrica mudou no local desde a eleição de referência (padrão: a
    geral anterior, ano − 4), em p.p. — % dos válidos do PARTIDO (pela entidade, `apuracao/partidos.py`: o nº de
    um candidato vale pelo partido dele; Flávio/PL 2026 × Bolsonaro/PL 2022), abstenção, comparecimento,
    brancos/nulos. Locais casados pela UNIDADE (município + zona + nº do local): local novo ou desativado sai;
  * "transferencia" (rodada 47, TODO 17b): o 1º → 2º turno por local (`transferencia.calcular`, nível local, estrato
    município): o peso dos eliminados no 1º turno e a abstenção extra (observados no local), o resíduo do 1º
    finalista (observado − previsto pela matriz) e o destino dos eliminados — ESTIMADO por município (o estrato):
    todos os locais de um município têm o mesmo valor. Inferência ECOLÓGICA (rodada 30).

Só com microdados (resultado final, por seção): o tempo real vai no máximo até o município.
"""

from __future__ import annotations

from typing import Any

import polars as pl

import votos_por_local_votacao as v
from apuracao import bairros as br
from apuracao import partidos as pt
from apuracao import perfil as pf

CAMADAS = {"voto": "Voto", "perfil": "Perfil do eleitorado", "residuo": "Resíduo do Perfil × voto",
           "variacao": "Variação desde a eleição anterior", "transferencia": "Destino dos eliminados (1º → 2º turno)"}
# métricas da camada "variacao" → métrica de `bairros.valor_por_bairro`/`metrica_participacao`
METRICAS_TRANSFERENCIA = {"eliminados_1t": "Eliminados no 1º turno (% do eleitorado)",
                          "elim_para_a": "Destino dos eliminados: % para o 1º finalista (estimado por município)",
                          "abst_extra": "Abstenção extra no 2º turno (p.p.)",
                          "residuo_a": "1º finalista: observado − previsto pela matriz (p.p.)"}
METRICAS_VARIACAO = {"pct_candidato": "partido", "abstencao_pct": "abstencao_pct",
                     "comparecimento_pct": "comparecimento_pct", "brancos_nulos_pct": "brancos_nulos",
                     "brancos_pct": "brancos", "nulos_pct": "nulos"}


def alvo(ano: int, cargo: int, turno: int, numero: int) -> pf.Alvo:
    """Em cargo proporcional, número de 2 dígitos = o PARTIDO (nominais + legenda); senão, o candidato."""
    if cargo in br.PROPORCIONAIS and 0 < numero < 100:
        return pf.Alvo(ano, cargo, turno, None, numero)
    return pf.Alvo(ano, cargo, turno, numero, None)


def _participacao(plocal: Any, ano: int, cargo: int, turno: int, metrica: str) -> pl.DataFrame:
    """CD_BAIRRO (= UNIDADE do local), VALOR, NUM, DEN — abstenção ou comparecimento por local."""
    det = plocal.b._carregar(("detalhe", ano), lambda: v.load_section_details(ano, plocal.b.uf, plocal.b.cache))
    pb = br.participacao_por_bairro(det, cargo, turno, plocal.locais(ano).select(
        v.LOCAL_KEY + [pl.col("UNIDADE").alias("CD_BAIRRO")]))
    if pb.is_empty():
        raise v.TseDataError(f"sem comparecimento de {br.CARGOS[cargo].title()} ({turno}º turno) em {ano}")
    return br.metrica_participacao(pb, metrica)


def variacao(plocal: Any, ano: int, ano_ref: int, cargo: int, turno: int, metrica: str,
             numero: int | None = None, municipio: int | None = None) -> tuple[pl.DataFrame, str]:
    """(CD_BAIRRO, VALOR = B − A em p.p., ANTES, DEPOIS; rótulo). `numero`: candidato ou partido (2 dígitos) em
    `ano`; vale o PARTIDO dele, e em `ano_ref` os nºs do mesmo partido (entidade). Partido sem correspondente
    na referência (novo) → ValueError: a variação não existe, não é "subiu do zero"."""
    if metrica not in METRICAS_VARIACAO:
        raise ValueError(f"variação por local: {', '.join(METRICAS_VARIACAO)}")
    m = METRICAS_VARIACAO[metrica]
    if m in br.PARTICIPACAO:
        a, b = (_participacao(plocal, x, cargo, turno, m) for x in (ano_ref, ano))
        rotulo = br.METRICAS[metrica]
    else:
        nums_a = nums_b = None
        rotulo = br.METRICAS[metrica]
        if m == "partido":
            if numero is None:
                raise ValueError("informe o número do candidato (ou 2 dígitos para o partido)")
            partido = numero if numero < 100 else int(str(numero)[:2])
            comp = plocal.comp
            nums_a, nums_b = comp.numeros_do_partido(partido, ano_ref, ano)
            if not nums_a:
                raise ValueError(f"o partido {comp.siglas(ano).get(partido, partido)} não tem correspondente em "
                                 f"{ano_ref} (partido novo): sem variação")
            sa, sb = comp.siglas(ano_ref), comp.siglas(ano)
            nome_b = sb.get(partido, str(partido))
            nome_a = " + ".join(sa.get(n, str(n)) for n in nums_a)
            rotulo = f"% dos válidos do {nome_b}" + (f" ({nome_a} em {ano_ref})" if pt.chave(nome_a) != pt.chave(nome_b) else "")
        a = br.valor_por_bairro(plocal._vb(ano_ref, cargo, turno), cargo, m, nums_a)
        b = br.valor_por_bairro(plocal._vb(ano, cargo, turno), cargo, m, nums_b)
    df = (a.select("CD_BAIRRO", pl.col("VALOR").alias("ANTES"))
          .join(b.select("CD_BAIRRO", pl.col("VALOR").alias("DEPOIS")), on="CD_BAIRRO", how="inner")
          .drop_nulls(["ANTES", "DEPOIS"])
          .with_columns((pl.col("DEPOIS") - pl.col("ANTES")).alias("VALOR")))
    if municipio is not None:
        df = df.filter(pf.municipio_do_bairro() == municipio)
    return df, f"Variação (p.p.) de {rotulo} — {br.CARGOS[cargo].title()}, {ano_ref} → {ano}"


def transferencia(plocal: Any, ano: int, cargo: int, metrica: str) -> tuple[pl.DataFrame, str, str, str, dict]:
    """(CD_BAIRRO, VALOR[, ANTES, DEPOIS]; rótulo; tipo; unidade; extra) da camada "transferencia"."""
    from apuracao import transferencia as tf
    if metrica not in METRICAS_TRANSFERENCIA:
        raise ValueError(f"transferência por local: {', '.join(METRICAS_TRANSFERENCIA)}")
    res = tf.calcular(ano, plocal.b.uf, cargo, "local", plocal.b.cache, n_boot=0)
    a = res.unidades.cat2[0]
    por = res.por_unidade.drop("UNIDADE").join(plocal.locais(ano).select(v.LOCAL_KEY + ["UNIDADE"]), on=v.LOCAL_KEY, how="inner")
    extra: dict[str, Any] = {"finalistas": res.unidades.cat2[:2]}
    col = {"eliminados_1t": "ELIMINADOS_1_PCT", "elim_para_a": f"ELIM_PARA_{a}_PCT", "abst_extra": "ABST_EXTRA_PP",
           "residuo_a": "RESIDUO_A_PP"}[metrica]
    sel = [pl.col("UNIDADE").alias("CD_BAIRRO"), pl.col(col).alias("VALOR")]
    if metrica == "abst_extra":
        sel += [pl.col("ABST_1_PCT").alias("ANTES"), pl.col("ABST_2_PCT").alias("DEPOIS")]
        extra.update(lados=["1º turno", "2º turno"], sentido="variacao")
    elif metrica == "residuo_a":
        sel += [pl.col(f"{a}_2_AJUSTE_PCT").alias("ANTES"), pl.col(f"{a}_2_PCT").alias("DEPOIS")]
        extra.update(lados=["previsto", "observado"], sentido="residuo")
    rotulo = METRICAS_TRANSFERENCIA[metrica].replace("o 1º finalista", a).replace("1º finalista", a)
    tipo = "divergente" if metrica in ("abst_extra", "residuo_a") else "sequencial"
    return (por.select(sel), f"{rotulo} — {br.CARGOS[cargo].title()} {ano}, 1º → 2º turno",
            tipo, "p.p." if tipo == "divergente" else "%", extra)


def pontos(plocal: Any, ano: int, camada: str, cargo: int = 3, turno: int = 1, metrica: str | None = None,
           numero: int | None = None, indicador: str | None = None, municipio: int | None = None,
           min_validos: int = 50, ano_ref: int | None = None) -> dict[str, Any]:
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
            df = _participacao(plocal, ano, cargo, turno, metrica).select("CD_BAIRRO", "VALOR")
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
    elif camada == "variacao":
        ano_ref = ano_ref or ano - 4
        if ano_ref >= ano:
            raise ValueError("a eleição de referência deve ser anterior")
        df, rotulo = variacao(plocal, ano, ano_ref, cargo, turno, metrica, numero, municipio)
        tipo, unidade = "divergente", "p.p."
        extra.update(ano_ref=ano_ref, lados=[str(ano_ref), str(ano)], sentido="variacao")
    elif camada == "transferencia":
        df, rotulo, tipo, unidade, mais = transferencia(plocal, ano, cargo, metrica)
        if municipio is not None:
            df = df.filter(pf.municipio_do_bairro() == municipio)
        extra.update(mais)
    else:
        if numero is None or indicador is None:
            raise ValueError("o resíduo precisa do número (candidato; 2 dígitos = partido) e do indicador")
        d = plocal.dispersao(alvo(ano, cargo, turno, numero), indicador, min_validos, False, municipio)
        df = d["pontos"].select("CD_BAIRRO", pl.col("RESIDUO").alias("VALOR"), pl.col("Y").alias("VOTO"),
                                pl.col("X").alias("INDICADOR"))
        est = d["estatistica"]
        rotulo, tipo, unidade = f"Resíduo (p.p.): {d['rotulo_y']} × {d['rotulo_x']}", "divergente", "p.p."
        extra["sentido"] = "residuo"
        extra.update(estatistica={k: est.get(k) for k in ("n", "pearson", "r2", "a", "b", "p")},
                     rotulo_x=d["rotulo_x"], rotulo_y=d["rotulo_y"], min_validos=min_validos)
    base = loc if municipio is None else loc.filter(pl.col("CD_MUN").cast(pl.Int64) == municipio)
    j = base.join(df.rename({"CD_BAIRRO": "UNIDADE"}), on="UNIDADE", how="inner").drop_nulls("VALOR")
    extras = [c for c in ("VOTO", "INDICADOR", "ROTULO", "ANTES", "DEPOIS") if c in j.columns]
    itens = [{"u": r["UNIDADE"], "lat": r["LAT"], "lon": r["LON"], "nome": r["NM_LOCAL_VOTACAO"], "mun": r["NM_MUN"],
              "zona": r["NR_ZONA"], "local": r["NR_LOCAL_VOTACAO"], "eleitores": r["QT_ELEITORES"],
              "valor": r["VALOR"], **{c.lower(): r[c] for c in extras}}
             for r in j.iter_rows(named=True)]
    return {"camada": camada, "tipo": tipo, "rotulo": rotulo, "unidade": unidade, "ano": ano, "itens": itens,
            "cobertura": {"locais": base.height, "com_valor": len(itens)}, **extra}
