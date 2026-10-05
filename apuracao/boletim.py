"""Boletim da apuração para a equipe: um HTML autônomo (um arquivo, abre em qualquer navegador, sem
internet) e uma planilha, gerados a cada hora e na totalização final.

Os números vêm das MESMAS funções das rotas do site (`app.state.consultas`), com os mesmos caches:
o boletim nunca diverge da página. Quem não está no computador do site recebe o arquivo; não é
preciso abrir o site na rede (sem senha).

    b = Boletineiro(app.state.consultas, dados_dir / "boletins")
    b.verificar()        # gera o boletim da hora (uma vez por hora cheia) ou o final, se for a vez
    b.executar(parar)    # laço: verificar() a cada 30 s até `parar`
"""

from __future__ import annotations

import html
import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter

import votos_por_local_votacao as v
from apuracao.alertas import agora_brasilia
from apuracao.web.app import Consultas

logger = logging.getLogger("apuracao.boletim")

TOP_HTML = 8            # candidatos por cargo majoritário no HTML (a planilha leva todos os do painel)
TOP_MUNICIPIOS = 12     # linhas das tabelas de destaques por município no HTML
CARGOS_DESTAQUE = (3, 1, 5)  # destaques por município: o 1º destes cargos com apuração municipal
STATUS_PROJ = {"consolidado": "consolidado", "em disputa (dentro)": "em disputa", "em disputa (fora)": "em disputa"}


# --------------------------------------------------------------------------
# Conteúdo
# --------------------------------------------------------------------------
def montar(c: Consultas, gerado_em: datetime, titulo: str, final: bool = False,
           destacar: Iterable[str] = ()) -> dict[str, Any]:
    """Tudo o que o boletim mostra, já calculado (JSON-serializável). `destacar`: siglas de partidos e/ou
    federações cujos deputados saem com ★ nas listas de eleitos (rodada 31)."""
    st = c.status()
    coletor = st.get("coletor") or {}
    cartoes = []
    for cartao in c.painel()["cartoes"]:
        cartao = {k: val for k, val in cartao.items() if k != "serie"}
        # o painel traz a projeção e as cadeiras resumidas; o boletim quer as completas
        try:
            if "projecao" in cartao:
                cartao["projecao"] = c.projecao(cartao["cargo"])
            if "cadeiras" in cartao:
                cartao["cadeiras"] = c.cadeiras(cartao["cargo"])
        except (ValueError, v.TseDataError) as exc:
            logger.warning("boletim: %s sem projeção/cadeiras completas: %s", cartao["ds_cargo"], exc)
        cartoes.append(cartao)
    tot, cand = c.dados.tabela("totais"), c.dados.tabela("candidatos")
    ult = tot.filter(pl.col("ABRANGENCIA").is_in(["br", "uf"]))["DT_TOTALIZACAO"].max()
    return {
        "titulo": titulo, "final": final, "uf": c.uf, "gerado_em": gerado_em.isoformat(timespec="seconds"),
        "ultima_totalizacao": ult.isoformat() if ult else None,
        "ambiente": coletor.get("ambiente"), "ano": coletor.get("ano"), "turno": coletor.get("turno", 1),
        "erro_coletor": coletor.get("erro"), "cartoes": cartoes,
        "municipios": destaques(tot, cand, c.dados.tabela("municipios"), c.uf),
        "destacar": sorted(destacar),
    }


def destacado(k: dict[str, Any], destacar: set[str] | frozenset[str]) -> bool:
    """O candidato é de um partido escolhido, ou da federação escolhida (federação = todos os seus partidos)."""
    return bool(destacar) and (k.get("PARTIDO") in destacar or k.get("AGREMIACAO") in destacar)


def destaques(tot: pl.DataFrame, cand: pl.DataFrame, muns: pl.DataFrame, uf: str) -> dict[str, Any] | None:
    """Por município, no 1º cargo de `CARGOS_DESTAQUE` com apuração municipal: % apurado, líder e 2º,
    e onde o líder do estado não lidera. None se nenhum cargo tiver linhas municipais."""
    for cargo in CARGOS_DESTAQUE:
        t = tot.filter((pl.col("ABRANGENCIA") == "mun") & (pl.col("CARGO") == cargo))
        if not t.is_empty():
            break
    else:
        return None
    no_estado = cand.filter((pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == uf) & (pl.col("CARGO") == cargo)
                            ).sort("VOTOS", descending=True)
    lider_uf = no_estado.row(0, named=True) if no_estado.height and (no_estado["VOTOS"][0] or 0) > 0 else None
    ordem = (cand.filter((pl.col("ABRANGENCIA") == "mun") & (pl.col("CARGO") == cargo) & (pl.col("VOTOS") > 0))
             .sort(["CD_MUNICIPIO", "VOTOS"], descending=[False, True])
             .group_by("CD_MUNICIPIO", maintain_order=True)
             .agg(pl.col("NUMERO").first().alias("NUMERO_LIDER"), pl.col("NOME_URNA").first().alias("LIDER"),
                  pl.col("PARTIDO").first().alias("PARTIDO_LIDER"), pl.col("PCT_VALIDOS").first().alias("PCT_LIDER"),
                  pl.col("NOME_URNA").slice(1, 1).first().alias("SEGUNDO"),
                  pl.col("PCT_VALIDOS").slice(1, 1).first().alias("PCT_SEGUNDO")))
    tabela = (t.select("CD_MUNICIPIO", "ELEITORADO", "PCT_SECOES_TOTALIZADAS", "TOTALIZACAO_FINAL")
              .join(muns.select("CD_MUNICIPIO", "NM_MUNICIPIO"), on="CD_MUNICIPIO", how="left")
              .join(ordem, on="CD_MUNICIPIO", how="left")
              .with_columns((pl.col("PCT_LIDER") - pl.col("PCT_SEGUNDO").fill_null(0)).round(2).alias("VANTAGEM_PP"))
              .sort("ELEITORADO", descending=True, nulls_last=True))
    divergentes = (tabela.filter(pl.col("NUMERO_LIDER").is_not_null()
                                 & (pl.col("NUMERO_LIDER") != lider_uf["NUMERO"])) if lider_uf
                   else tabela.clear())
    pct = tabela["PCT_SECOES_TOTALIZADAS"].fill_null(0)
    return {
        "cargo": cargo, "ds_cargo": t["DS_CARGO"][0], "municipios": tabela.height,
        "totalizados": int((tabela["TOTALIZACAO_FINAL"].fill_null(False) | (pct >= 100)).sum()),
        "com_apuracao": int((pct > 0).sum()),
        "lider_estado": lider_uf["NOME_URNA"] if lider_uf else None,
        "n_divergentes": divergentes.height,
        "tabela": _linhas(tabela.drop("NUMERO_LIDER")),
        "divergentes": _linhas(divergentes.drop("NUMERO_LIDER")),
    }


def _linhas(df: pl.DataFrame) -> list[dict[str, Any]]:
    return [dict(r) for r in df.iter_rows(named=True)]


# --------------------------------------------------------------------------
# O que mudou desde o boletim anterior (rodada 33)
# --------------------------------------------------------------------------
def fotografia(b: dict[str, Any]) -> dict[str, Any]:
    """O essencial de um boletim para comparar com o próximo (gravado em <nome>.json ao lado do HTML)."""
    cargos: dict[str, Any] = {}
    for c in b["cartoes"]:
        t = c["totais"]
        item: dict[str, Any] = {"ds": f"{c['ds_cargo']} — {c['abrangencia']}", "pct": t.get("PCT_SECOES_TOTALIZADAS"),
                                "final": bool(t.get("TOTALIZACAO_FINAL"))}
        if not c["proporcional"]:
            k = c["candidatos"][0] if c["candidatos"] else None
            item["lider"] = {"numero": k["NUMERO"], "nome": k["NOME_URNA"], "pct": k["PCT_VALIDOS"]} if k else None
            situacao = (c.get("projecao") or {}).get("situacao")
            item["leitura"] = situacao.split(":")[0].strip() if situacao else None
        else:
            cad = c.get("cadeiras") or {}
            item["vagas"] = {a.get("NOME") or a["AGREMIACAO"]: a.get("VAGAS") or 0 for a in cad.get("agremiacoes", [])}
            item["eleitos"] = {str(e["NUMERO"]): f"{e['NOME']} ({e['PARTIDO']})" for e in cad.get("eleitos") or []}
            proj = cad.get("projecao") or {}
            item["consolidados"] = ({str(k["NUMERO"]): f"{k['NOME']} ({k['PARTIDO']})" for k in proj.get("candidatos", [])
                                     if k["STATUS"] == "consolidado"} if proj.get("ativa") else None)
        cargos[f"{c['cargo']}-{c['abrangencia']}"] = item
    return {"titulo": b["titulo"], "gerado_em": b["gerado_em"], "cargos": cargos}


def _lista(nomes: list[str], limite: int = 8) -> str:
    return ", ".join(nomes[:limite]) + (f" e mais {len(nomes) - limite}" if len(nomes) > limite else "")


def mudancas(ant: dict[str, Any], atual: dict[str, Any]) -> list[dict[str, str]]:
    """O que mudou entre duas fotografias: apuração, líder, leitura da projeção, cadeiras por partido,
    eleitos (entraram/saíram) e consolidados. Lista de {"cargo", "tipo", "texto"}, na ordem dos cartões."""
    saida: list[dict[str, str]] = []
    for chave, a in atual["cargos"].items():
        b = ant["cargos"].get(chave)
        if not b:
            continue

        def add(tipo: str, texto: str) -> None:
            saida.append({"cargo": a["ds"], "tipo": tipo, "texto": texto})

        if a.get("final") and not b.get("final"):
            add("apuracao", "totalização final")
        elif a.get("pct") is not None and a.get("pct") != b.get("pct"):
            add("apuracao", f"apuração: {_p(b.get('pct'))} → {_p(a.get('pct'))} das seções")
        if "lider" in a and a.get("lider") and b.get("lider") and a["lider"]["numero"] != b["lider"]["numero"]:
            add("lider", f"novo líder: {a['lider']['nome']} ({_p(a['lider']['pct'])}); antes {b['lider']['nome']}")
        if a.get("leitura") and b.get("leitura") and a["leitura"] != b["leitura"]:
            add("leitura", f"projeção: {a['leitura']} (antes: {b['leitura']})")
        if "vagas" in a and b.get("vagas") is not None:
            difs = [f"{nome} {b['vagas'].get(nome, 0)} → {v}" for nome, v in a["vagas"].items()
                    if v != b["vagas"].get(nome, 0)]
            difs += [f"{nome} {v} → 0" for nome, v in b["vagas"].items() if v and nome not in a["vagas"]]
            if difs:
                add("cadeiras", "cadeiras: " + "; ".join(difs))
            entraram = [n for k, n in a["eleitos"].items() if k not in b.get("eleitos", {})]
            sairam = [n for k, n in b.get("eleitos", {}).items() if k not in a["eleitos"]]
            if entraram:
                add("eleitos", f"entraram entre os eleitos: {_lista(entraram)}")
            if sairam:
                add("eleitos", f"saíram dos eleitos: {_lista(sairam)}")
            if a.get("consolidados") is not None and b.get("consolidados") is not None:
                novos = [n for k, n in a["consolidados"].items() if k not in b["consolidados"]]
                perdidos = [n for k, n in b["consolidados"].items() if k not in a["consolidados"]]
                if novos:
                    add("consolidados", f"{len(novos)} novo(s) consolidado(s): {_lista(novos)}")
                if perdidos:
                    add("consolidados", f"deixaram de ser consolidados: {_lista(perdidos)}")
    return _juntar_apuracao(saida)


def _juntar_apuracao(itens: list[dict[str, str]]) -> list[dict[str, str]]:
    """Cargos com o MESMO avanço da apuração numa linha só (a UF apura governador, senador e deputados
    juntos: 4 linhas iguais viravam ruído)."""
    grupos: dict[str, list[str]] = {}
    for m_ in itens:
        if m_["tipo"] == "apuracao":
            grupos.setdefault(m_["texto"], []).append(m_["cargo"])
    saida, feitos = [], set()
    for m_ in itens:
        if m_["tipo"] != "apuracao":
            saida.append(m_)
        elif m_["texto"] not in feitos:
            feitos.add(m_["texto"])
            cargos = grupos[m_["texto"]]
            sufixos = {c.rsplit(" — ", 1)[-1] for c in cargos}
            nome = (", ".join(c.rsplit(" — ", 1)[0] for c in cargos) + " — " + sufixos.pop()
                    if len(cargos) > 1 and len(sufixos) == 1 else ", ".join(cargos))
            saida.append({**m_, "cargo": nome})
    return saida


def fotografia_anterior(pasta: Path, antes_de: str | None = None) -> dict[str, Any] | None:
    """A fotografia do boletim mais recente gravado em `pasta` (opcionalmente anterior a `antes_de`)."""
    melhores = []
    for arq in pasta.glob("boletim_*.json") if pasta.exists() else []:
        try:
            f = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if antes_de is None or f.get("gerado_em", "") < antes_de:
            melhores.append(f)
    return max(melhores, key=lambda f: f.get("gerado_em", ""), default=None)


def mudancas_agora(c: Consultas, pasta: Path) -> dict[str, Any]:
    """Para o painel: o que mudou entre o último boletim e agora."""
    ant = fotografia_anterior(pasta)
    if ant is None:
        return {"anterior": None, "mudancas": []}
    atual = fotografia(montar(c, agora_brasilia(), "agora"))
    return {"anterior": {"titulo": ant["titulo"], "gerado_em": ant["gerado_em"]}, "mudancas": mudancas(ant, atual)}


def _html_mudancas(b: dict[str, Any]) -> str:
    ant = b.get("anterior")
    if not ant:
        return ""
    itens = b.get("mudancas") or []
    corpo = ("".join(f"<li><strong>{_e(m_['cargo'])}</strong>: {_e(m_['texto'])}</li>" for m_ in itens)
             or "<li>Nada mudou nos números do boletim.</li>")
    return (f'<section><h2>O que mudou desde o {_e(ant["titulo"].lower() if ant["titulo"].startswith("Boletim") else ant["titulo"])}'
            f' ({_hora(ant["gerado_em"])})</h2><ul class="mudancas">{corpo}</ul></section>')


# --------------------------------------------------------------------------
# HTML autônomo
# --------------------------------------------------------------------------
def _e(x: Any) -> str:
    """Todo texto vindo do TSE passa por aqui (há nomes com aspas e símbolos no simulado)."""
    return html.escape("" if x is None else str(x))


def _n(x: Any) -> str:
    return "—" if x is None else f"{int(round(x)):,}".replace(",", ".")


def _p(x: Any, casas: int = 2) -> str:
    return "—" if x is None else f"{x:.{casas}f}".replace(".", ",") + "%"


def _hora(iso: str | None) -> str:
    if not iso:
        return "—"
    t = datetime.fromisoformat(iso)
    return f"{t:%d/%m %H:%M}"


def _barra(pct: Any) -> str:
    largura = max(0.0, min(100.0, float(pct or 0)))
    return f'<span class="barra"><span style="width:{largura:.1f}%"></span></span>'


def _tabela(cabecalho: list[str], linhas: list[list[str]], numericas: set[int] = frozenset(),
            marcadas: list[bool] | None = None) -> str:
    """`linhas` já em HTML escapado; `numericas`: índices das colunas alinhadas à direita; `marcadas`: linhas
    com a classe "destaque"."""
    th = "".join(f'<th{" class=n" if i in numericas else ""}>{_e(h)}</th>' for i, h in enumerate(cabecalho))
    marcadas = marcadas or [False] * len(linhas)
    trs = "".join(("<tr class=destaque>" if m else "<tr>")
                  + "".join(f'<td{" class=n" if i in numericas else ""}>{c}</td>' for i, c in enumerate(l))
                  + "</tr>" for l, m in zip(linhas, marcadas))
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def _meta(t: dict[str, Any]) -> str:
    partes = [f"{_p(t.get('PCT_SECOES_TOTALIZADAS'))} das seções",
              f"comparecimento {_p(t.get('PCT_COMPARECIMENTO'))}", f"abstenção {_p(t.get('PCT_ABSTENCAO'))}",
              f"brancos {_p(t.get('PCT_BRANCOS'))}", f"nulos {_p(t.get('PCT_NULOS'))}",
              f"totalização {_hora(t.get('DT_TOTALIZACAO'))}"]
    if t.get("TOTALIZACAO_FINAL"):
        partes.insert(0, "<strong>totalização final</strong>")
    return '<p class="meta">' + " · ".join(partes) + "</p>"


def _html_majoritario(c: dict[str, Any]) -> str:
    proj = c.get("projecao")
    por_numero = {k["NUMERO"]: k for k in (proj or {}).get("candidatos", [])}
    cab = ["Nº", "Candidato", "Partido", "Votos", "% válidos", ""]
    if proj:
        cab += ["Projeção", "Faixa"]
    linhas = []
    for k in c["candidatos"][:TOP_HTML]:
        mostra_situacao = k.get("SITUACAO") and (k.get("ELEITO") or c["totais"].get("TOTALIZACAO_FINAL"))
        linha = [_e(k["NUMERO"]), _e(k["NOME_URNA"]) + (f' <span class="sit">{_e(k["SITUACAO"])}</span>'
                                                         if mostra_situacao else ""),
                 _e(k["PARTIDO"]), _n(k["VOTOS"]), _p(k["PCT_VALIDOS"]), _barra(k["PCT_VALIDOS"])]
        if proj:
            pk = por_numero.get(k["NUMERO"], {})
            linha += [_p(pk.get("PCT_PROJ"), 1), f'{_p(pk.get("MIN"), 1)} a {_p(pk.get("MAX"), 1)}' if pk else "—"]
        linhas.append(linha)
    corpo = [_meta(c["totais"])]
    if proj:
        corpo.append(f'<p class="leitura">Projeção ({_p(proj["pct_apurado"], 1)} do eleitorado apurado, '
                     f'margem ±{_p(proj["margem_pp"], 1).replace("%", " p.p.")}): <strong>{_e(proj["situacao"])}</strong></p>')
    corpo.append(_tabela(cab, linhas, {0, 3, 4, 6, 7}))
    if proj and proj.get("faltam"):
        corpo.append("<details><summary>Onde falta mais voto</summary>" + _tabela(
            ["Município", "% apurado", "Válidos que faltam"],
            [[_e(f["NM_MUNICIPIO"]), _p(f["PCT_APURADO"], 1), _n(f["VALIDOS_RESTANTES"])] for f in proj["faltam"]],
            {1, 2}) + "</details>")
    return "".join(corpo)


def _html_proporcional(c: dict[str, Any], destacar: frozenset[str] = frozenset()) -> str:
    cad = c.get("cadeiras")
    t = c["totais"]
    corpo = [_meta(t)]
    if not cad:
        return "".join(corpo) + '<p class="nota">Cadeiras indisponíveis neste boletim.</p>'
    corpo.append(f'<p class="meta">{cad["vagas"]} vagas · válidos {_n(cad["validos"])} · quociente eleitoral '
                 f'{_n(cad["qe"])} · fonte: {_e(cad["fonte"])}</p>')
    proj = cad.get("projecao")
    status: dict[int, str] = {}
    faixa: dict[str, tuple[int, int, int]] = {}
    if proj and proj.get("ativa"):
        status = {k["NUMERO"]: STATUS_PROJ.get(k["STATUS"], k["STATUS"]) for k in proj.get("candidatos", [])}
        faixa = {a["AGREMIACAO"]: (a["VAGAS"], a["VAGAS_MIN"], a["VAGAS_MAX"]) for a in proj["agremiacoes"]}
        corpo.append(f'<p class="leitura">Projeção das cadeiras ({proj["simulacoes"]} simulações sobre os votos '
                     f'projetados): <strong>{proj["consolidados"]} consolidados</strong>, '
                     f'{proj["em_disputa_dentro"] + proj["em_disputa_fora"]} em disputa por '
                     f'{cad["vagas"] - proj["consolidados"]} vagas. Consolidado = eleito em ≥ '
                     f'{proj["limiar"] * 100:.0f}% das simulações.</p>')
    elif proj:
        corpo.append(f'<p class="nota">A projeção das cadeiras começa a partir de {_p(proj["pct_minimo"], 0)} '
                     f'apurado (agora {_p(proj["pct_apurado"], 1)}).</p>')
    parcial = "" if t.get("TOTALIZACAO_FINAL") else " se a apuração acabasse agora"
    agr = [a for a in cad["agremiacoes"] if a.get("VAGAS") or faixa.get(a["AGREMIACAO"], (0, 0, 0))[2]]
    agr.sort(key=lambda a: (-(a.get("VAGAS") or 0), -(a.get("VOTOS") or 0)))
    cab = ["Agremiação", "Votos", "% dos válidos", "Cadeiras" + parcial]
    if faixa:
        cab += ["Projeção", "Faixa (p5–p95)"]
    linhas = []
    for a in agr:
        linha = [_e(a.get("NOME") or a["AGREMIACAO"]), _n(a["VOTOS"]),
                 _p(100 * a["VOTOS"] / cad["validos"] if cad["validos"] else None), _n(a.get("VAGAS"))]
        if faixa:
            f = faixa.get(a["AGREMIACAO"])
            linha += [_n(f[0]), f"{f[1]} a {f[2]}"] if f else ["0", "—"]
        linhas.append(linha)
    corpo.append("<h3>Cadeiras por partido ou federação</h3>" + _tabela(cab, linhas, {1, 2, 3, 4, 5}))
    eleitos = cad.get("eleitos") or []
    cab = ["Candidato", "Partido", "Votos", "Como"] + (["Projeção"] if status else [])
    estrela = lambda k: "★ " if destacado(k, destacar) else ""  # noqa: E731 (o destaque não depende só da cor)
    linhas = [[estrela(k) + _e(k["NOME"]), _e(k["PARTIDO"]), _n(k["VOTOS"]),
               _e(k["SITUACAO_PROJETADA"].replace("Eleito ", ""))]
              + ([_e(status.get(k["NUMERO"], "—"))] if status else []) for k in eleitos]
    n_dest = sum(destacado(k, destacar) for k in eleitos)
    corpo.append(f"<details{' open' if n_dest else ''}><summary>Eleitos{_e(parcial)} ({len(eleitos)}"
                 f"{f'; {n_dest} destacados' if destacar else ''})</summary>"
                 + _tabela(cab, linhas, {2}, [destacado(k, destacar) for k in eleitos]) + "</details>")
    fora = [k for k in (proj or {}).get("candidatos", []) if k["STATUS"] == "em disputa (fora)"] if status else []
    if fora:
        # "fora" é na distribuição PROJETADA: pode estar entre os eleitos da apuração parcial acima
        corpo.append(f"<details><summary>Fora na projeção, mas ainda em disputa ({len(fora)})</summary>" + _tabela(
            ["Candidato", "Partido", "Votos projetados", "Eleito nas simulações"],
            [[estrela(k) + _e(k["NOME"]), _e(k["PARTIDO"]), _n(k["VOTOS_PROJ"]), _p(100 * k["FREQ_ELEITO"], 0)]
             for k in fora], {2, 3}, [destacado(k, destacar) for k in fora]) + "</details>")
    conf = cad.get("conferencia_tse")
    if conf:
        corpo.append(f'<p class="nota">Conferência com o TSE: {conf["coincidentes"]} de {conf["eleitos_tse"]} eleitos '
                     f'coincidem ({conf["divergencias"]} divergências).</p>')
    return "".join(corpo)


def _html_municipios(d: dict[str, Any]) -> str:
    cab = ["Município", "Eleitorado", "% seções", "Líder", "%", "2º", "%", "Vantagem"]

    def linha(r: dict[str, Any]) -> list[str]:
        return [_e(r["NM_MUNICIPIO"]), _n(r["ELEITORADO"]), _p(r["PCT_SECOES_TOTALIZADAS"], 1),
                f'{_e(r["LIDER"] or "—")} <span class="sit">{_e(r["PARTIDO_LIDER"] or "")}</span>',
                _p(r["PCT_LIDER"], 1), _e(r["SEGUNDO"] or "—"), _p(r["PCT_SEGUNDO"], 1),
                _p(r["VANTAGEM_PP"], 1).replace("%", " p.p.")]

    resumo = (f'<p class="meta">{d["totalizados"]} de {d["municipios"]} municípios totalizados · '
              f'{d["com_apuracao"]} com apuração')
    if d["lider_estado"]:
        resumo += (f' · {_e(d["lider_estado"])} (líder no estado) não lidera em {d["n_divergentes"]} '
                   f'{"município" if d["n_divergentes"] == 1 else "municípios"}')
    corpo = [resumo + "</p>", "<h3>Maiores eleitorados</h3>",
             _tabela(cab, [linha(r) for r in d["tabela"][:TOP_MUNICIPIOS]], {1, 2, 4, 6, 7})]
    if d["divergentes"]:
        quantos = (f"os {TOP_MUNICIPIOS} maiores de {d['n_divergentes']}" if d["n_divergentes"] > TOP_MUNICIPIOS
                   else str(d["n_divergentes"]))
        corpo += [f"<h3>Onde o líder do estado não lidera ({quantos})</h3>",
                  _tabela(cab, [linha(r) for r in d["divergentes"][:TOP_MUNICIPIOS]], {1, 2, 4, 6, 7})]
    return "".join(corpo)


CSS = """
:root{--fundo:#fcfcfb;--sup:#ffffff;--tinta:#0b0b0b;--tinta2:#52514e;--linha:#e4e2dd;--barra:#2a6fdb;--trilho:#e9eef8;
--aviso-f:#fff4d6;--aviso-t:#5c4400;--destaque:#e3edfb}
@media (prefers-color-scheme:dark){:root{--fundo:#141413;--sup:#1d1d1b;--tinta:#f2f1ee;--tinta2:#b3b1ab;--linha:#34332f;
--barra:#6aa0f5;--trilho:#26303f;--aviso-f:#3a2f10;--aviso-t:#f4dc9a;--destaque:#1f3350}}
ul.mudancas{margin:.3rem 0;padding-left:1.2rem}ul.mudancas li{margin:.2rem 0}
tr.destaque td{background:var(--destaque);font-weight:600}tr.destaque td:first-child{box-shadow:inset 4px 0 0 var(--barra)}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--tinta);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}h1{font-size:1.5rem;margin:.2rem 0}
h2{font-size:1.15rem;margin:0 0 .3rem}h3{font-size:.95rem;margin:1rem 0 .3rem;color:var(--tinta2)}
section{background:var(--sup);border:1px solid var(--linha);border-radius:10px;padding:14px 16px;margin:14px 0}
.meta,.nota{color:var(--tinta2);margin:.2rem 0;font-size:.9rem}.leitura{margin:.5rem 0}
.aviso{background:var(--aviso-f);color:var(--aviso-t);border-radius:8px;padding:8px 12px;margin:10px 0}
.tabela{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem;margin:.3rem 0}
th,td{padding:4px 8px;border-bottom:1px solid var(--linha);text-align:left;white-space:nowrap}
th{color:var(--tinta2);font-weight:600}.n{text-align:right;font-variant-numeric:tabular-nums}
.sit{color:var(--tinta2);font-size:.8rem}
.barra{display:inline-block;width:90px;height:8px;border-radius:4px;background:var(--trilho);vertical-align:middle}
.barra span{display:block;height:100%;border-radius:4px;background:var(--barra)}
details{margin:.4rem 0}summary{cursor:pointer;color:var(--tinta2)}footer{color:var(--tinta2);font-size:.8rem;margin:20px 0}
@media print{details{display:block}details>*{display:block}section{break-inside:avoid}}
"""


def para_html(b: dict[str, Any]) -> str:
    """O boletim como um único arquivo HTML: CSS embutido, sem script e sem nada externo."""
    avisos = []
    if b["ambiente"] and b["ambiente"] != "oficial" and not b["ano"]:
        avisos.append(f"Ambiente <strong>{_e(b['ambiente'])}</strong>: números de TESTE, não são o resultado oficial.")
    if b["ano"]:
        avisos.append(f"Resultado da eleição de {_e(b['ano'])} (arquivo histórico), não da apuração em andamento.")
    if b["erro_coletor"]:
        avisos.append(f"Último erro do coletor: {_e(b['erro_coletor'])}")
    destacar = frozenset(b.get("destacar") or ())
    secoes = []
    for c in b["cartoes"]:
        corpo = _html_proporcional(c, destacar) if c["proporcional"] else _html_majoritario(c)
        secoes.append(f'<section><h2>{_e(c["ds_cargo"])} — {_e(c["abrangencia"])}</h2>'
                      f'<div class="tabela">{corpo}</div></section>')
    if b["municipios"]:
        d = b["municipios"]
        secoes.append(f'<section><h2>{_e(d["ds_cargo"])} por município</h2>'
                      f'<div class="tabela">{_html_municipios(d)}</div></section>')
    if not b["cartoes"]:
        secoes.append('<section><p class="nota">Ainda não há votos apurados.</p></section>')
    turno = f" · {b['turno']}º turno" if b.get("turno") else ""
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(b['titulo'])} — Apuração {_e(b['uf'])}</title><style>{CSS}</style></head>
<body><main>
<h1>{_e(b['titulo'])} — Apuração {_e(b['uf'])}</h1>
<p class="meta">Última totalização do TSE: {_hora(b['ultima_totalizacao'])} · boletim gerado em
{_hora(b['gerado_em'])}{turno}</p>
{"".join(f'<p class="aviso">{a}</p>' for a in avisos)}
{_html_mudancas(b)}
{f'<p class="meta">★ Destaque nas listas de eleitos: {_e(", ".join(sorted(destacar)))}</p>' if destacar else ""}
{"".join(secoes)}
<footer>Fonte: divulgação de resultados do TSE (resultados.tse.jus.br), totalização por município.
Projeção: em cada município, o que falta apurar segue o voto já apurado ali; a margem é o percentil 95
do erro medido na apuração de 2022 — é estimativa, não resultado. Cadeiras: quociente eleitoral,
quociente partidário e sobras em duas fases (art. 12-A da Res. TSE 23.677/2021), recalculadas a cada coleta.
Os números são os mesmos do site da apuração no momento da geração.</footer>
</main></body></html>
"""


# --------------------------------------------------------------------------
# Planilha
# --------------------------------------------------------------------------
def _aba(wb: xlsxwriter.Workbook, nome: str, colunas: list[tuple[str, str, str]], linhas: list[dict[str, Any]],
         formatos: dict[str, Any]) -> None:
    """`colunas`: (chave, título, formato: "txt" | "int" | "pct" | "var" (variação %, com sinal) | "pp" | "hora")."""
    ws = wb.add_worksheet(nome[:31])
    for j, (_, titulo, fmt) in enumerate(colunas):
        ws.write(0, j, titulo, formatos["cab"])
        ws.set_column(j, j, 12 if fmt != "txt" else 24)
    for i, r in enumerate(linhas, start=1):
        for j, (chave, _, fmt) in enumerate(colunas):
            val = r.get(chave)
            if val is None:
                continue
            if fmt in ("pct", "var"):
                ws.write_number(i, j, float(val) / 100, formatos[fmt])
            elif fmt == "pp":
                ws.write_number(i, j, float(val), formatos["pp"])
            elif fmt == "int":
                ws.write_number(i, j, float(val), formatos["int"])
            else:
                ws.write(i, j, val if isinstance(val, (int, float, bool)) else str(val))
    ws.freeze_panes(1, 0)
    if linhas:
        ws.autofilter(0, 0, len(linhas), len(colunas) - 1)


def _nome_aba(c: dict[str, Any], sufixo: str = "") -> str:
    curto = c["ds_cargo"].replace("Deputado", "Dep.").replace("Deputada", "Dep.")
    nome = f"{curto} {c['abrangencia']}{sufixo}"
    return "".join(ch for ch in nome if ch not in "[]:*?/\\")[:31]


def formatos_planilha(wb: xlsxwriter.Workbook) -> dict[str, Any]:
    return {"cab": wb.add_format({"bold": True, "bg_color": "#E9EEF8"}),
            "pct": wb.add_format({"num_format": "0.00%"}), "int": wb.add_format({"num_format": "#,##0"}),
            "var": wb.add_format({"num_format": "+0.0%;-0.0%;0.0%"}),
            "pp": wb.add_format({"num_format": '+0.00" p.p.";-0.00" p.p.";0.00" p.p."'})}


def para_planilha(b: dict[str, Any], destino: Path) -> None:
    wb = xlsxwriter.Workbook(str(destino))
    formatos = formatos_planilha(wb)
    destacar = frozenset(b.get("destacar") or ())
    resumo = [{"ITEM": "Boletim", "VALOR": b["titulo"]}, {"ITEM": "Gerado em", "VALOR": _hora(b["gerado_em"])},
              {"ITEM": "Última totalização do TSE", "VALOR": _hora(b["ultima_totalizacao"])},
              {"ITEM": "Ambiente", "VALOR": b["ambiente"] or ""}]
    por_cargo = []
    for c in b["cartoes"]:
        t = c["totais"]
        lider = c["candidatos"][0] if c["candidatos"] else {}
        proj = c.get("projecao") or {}
        cad = c.get("cadeiras") or {}
        por_cargo.append({"CARGO": c["ds_cargo"], "ABRANGENCIA": c["abrangencia"],
                          "PCT_SECOES": t.get("PCT_SECOES_TOTALIZADAS"), "FINAL": bool(t.get("TOTALIZACAO_FINAL")),
                          "ELEITORADO": t.get("ELEITORADO"), "PCT_COMPARECIMENTO": t.get("PCT_COMPARECIMENTO"),
                          "PCT_ABSTENCAO": t.get("PCT_ABSTENCAO"), "VALIDOS": t.get("VALIDOS"),
                          "PCT_BRANCOS": t.get("PCT_BRANCOS"), "PCT_NULOS": t.get("PCT_NULOS"),
                          "MAIS_VOTADO": lider.get("NOME_URNA"), "PCT_MAIS_VOTADO": lider.get("PCT_VALIDOS"),
                          "LEITURA_PROJECAO": proj.get("situacao"), "QE": cad.get("qe")})
    _aba(wb, "Resumo", [("ITEM", "Item", "txt"), ("VALOR", "Valor", "txt")], resumo, formatos)
    if b.get("anterior"):
        _aba(wb, "Mudanças", [("cargo", "Cargo", "txt"), ("texto", f"Desde o {b['anterior']['titulo']}", "txt")],
             b.get("mudancas") or [{"cargo": "—", "texto": "nada mudou"}], formatos)
    _aba(wb, "Cargos", [("CARGO", "Cargo", "txt"), ("ABRANGENCIA", "Abrangência", "txt"),
                        ("PCT_SECOES", "Seções totalizadas", "pct"), ("FINAL", "Totalização final", "txt"),
                        ("ELEITORADO", "Eleitorado", "int"), ("PCT_COMPARECIMENTO", "Comparecimento", "pct"),
                        ("PCT_ABSTENCAO", "Abstenção", "pct"), ("VALIDOS", "Válidos", "int"),
                        ("PCT_BRANCOS", "Brancos", "pct"), ("PCT_NULOS", "Nulos", "pct"),
                        ("MAIS_VOTADO", "Mais votado", "txt"), ("PCT_MAIS_VOTADO", "% do mais votado", "pct"),
                        ("LEITURA_PROJECAO", "Leitura da projeção", "txt"), ("QE", "Quociente eleitoral", "int")],
         por_cargo, formatos)
    for c in b["cartoes"]:
        if c["proporcional"]:
            _abas_proporcional(wb, c, formatos, destacar)
        else:
            proj = {k["NUMERO"]: k for k in (c.get("projecao") or {}).get("candidatos", [])}
            linhas = [{**k, **{f"P_{x}": proj.get(k["NUMERO"], {}).get(x) for x in ("PCT_PROJ", "MIN", "MAX")}}
                      for k in c["candidatos"]]
            _aba(wb, _nome_aba(c), [("NUMERO", "Número", "txt"), ("NOME_URNA", "Candidato", "txt"),
                                    ("PARTIDO", "Partido", "txt"), ("VOTOS", "Votos", "int"),
                                    ("PCT_VALIDOS", "% válidos", "pct"), ("SITUACAO", "Situação", "txt"),
                                    ("P_PCT_PROJ", "Projeção", "pct"), ("P_MIN", "Projeção mín.", "pct"),
                                    ("P_MAX", "Projeção máx.", "pct")], linhas, formatos)
    d = b["municipios"]
    if d:
        _aba(wb, f"Municípios {d['ds_cargo']}", [
            ("NM_MUNICIPIO", "Município", "txt"), ("CD_MUNICIPIO", "Código TSE", "txt"),
            ("ELEITORADO", "Eleitorado", "int"), ("PCT_SECOES_TOTALIZADAS", "Seções totalizadas", "pct"),
            ("TOTALIZACAO_FINAL", "Totalização final", "txt"), ("LIDER", "Líder", "txt"),
            ("PARTIDO_LIDER", "Partido do líder", "txt"), ("PCT_LIDER", "% do líder", "pct"),
            ("SEGUNDO", "2º", "txt"), ("PCT_SEGUNDO", "% do 2º", "pct"), ("VANTAGEM_PP", "Vantagem (p.p.)", "int")],
            d["tabela"], formatos)
    wb.close()


def _abas_proporcional(wb: xlsxwriter.Workbook, c: dict[str, Any], formatos: dict[str, Any],
                       destacar: frozenset[str] = frozenset()) -> None:
    cad = c.get("cadeiras")
    if not cad:
        return
    proj = cad.get("projecao") or {}
    faixa = {a["AGREMIACAO"]: a for a in proj.get("agremiacoes", [])}
    status = {k["NUMERO"]: k for k in proj.get("candidatos", [])}
    agr = [{**a, "P_VAGAS": faixa.get(a["AGREMIACAO"], {}).get("VAGAS"),
            "P_MIN": faixa.get(a["AGREMIACAO"], {}).get("VAGAS_MIN"), "P_MAX": faixa.get(a["AGREMIACAO"], {}).get("VAGAS_MAX"),
            "PCT": 100 * a["VOTOS"] / cad["validos"] if cad["validos"] else None} for a in cad["agremiacoes"]]
    _aba(wb, _nome_aba(c, " cadeiras"), [
        ("NOME", "Agremiação", "txt"), ("VOTOS", "Votos", "int"), ("PCT", "% dos válidos", "pct"),
        ("QP", "Quociente partidário", "int"), ("VAGAS_QP", "Vagas por QP", "int"),
        ("VAGAS_MEDIA", "Vagas por média", "int"), ("VAGAS", "Vagas (apuração atual)", "int"),
        ("P_VAGAS", "Vagas projetadas", "int"), ("P_MIN", "Faixa mín.", "int"), ("P_MAX", "Faixa máx.", "int")],
        agr, formatos)
    eleitos = [{**k, "DESTACADO": "Sim" if destacado(k, destacar) else "",
                "P_STATUS": status.get(k["NUMERO"], {}).get("STATUS"),
                "P_FREQ": 100 * status[k["NUMERO"]]["FREQ_ELEITO"] if k["NUMERO"] in status else None}
               for k in cad.get("eleitos") or []]
    _aba(wb, _nome_aba(c, " eleitos"), [
        ("NUMERO", "Número", "txt"), ("NOME", "Candidato", "txt"), ("PARTIDO", "Partido", "txt"),
        ("AGREMIACAO", "Agremiação", "txt"), ("VOTOS", "Votos", "int"), ("SITUACAO_PROJETADA", "Situação", "txt"),
        ("MARGEM", "Margem (votos)", "int"), ("P_STATUS", "Projeção", "txt"), ("P_FREQ", "Eleito nas simulações", "pct"),
        ("DESTACADO", "Destacado", "txt")],
        eleitos, formatos)
    if proj.get("candidatos"):
        _aba(wb, _nome_aba(c, " projeção"), [
            ("NUMERO", "Número", "txt"), ("NOME", "Candidato", "txt"), ("PARTIDO", "Partido", "txt"),
            ("AGREMIACAO", "Agremiação", "txt"), ("VOTOS_PROJ", "Votos projetados", "int"),
            ("FREQ_ELEITO", "Eleito nas simulações", "txt"), ("STATUS", "Situação", "txt"),
            ("DESTACADO", "Destacado", "txt")],
            [{**k, "FREQ_ELEITO": f"{100 * k['FREQ_ELEITO']:.0f}%", "DESTACADO": "Sim" if destacado(k, destacar) else ""}
             for k in proj["candidatos"]], formatos)


def planilha_eleitos(cadeiras: dict[str, Any], uf: str, destacar: Iterable[str] = (),
                     sobre: list[tuple[str, str]] = ()) -> bytes:
    """Planilha (em memória) das listas de eleitos projetados de um cargo de deputado — a mesma do boletim
    (abas cadeiras, eleitos e projeção), com a coluna "Destacado" e uma aba "Sobre". `cadeiras` é o JSON
    de GET /api/cadeiras (completo)."""
    import io
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    formatos = formatos_planilha(wb)
    destacar = frozenset(destacar)
    _aba(wb, "Sobre", [("ITEM", "Item", "txt"), ("VALOR", "Valor", "txt")],
         [{"ITEM": i, "VALOR": val} for i, val in sobre]
         + [{"ITEM": "Destaque", "VALOR": ", ".join(sorted(destacar)) or "nenhum"}], formatos)
    _abas_proporcional(wb, {"ds_cargo": cadeiras["ds_cargo"], "abrangencia": uf, "cadeiras": cadeiras}, formatos,
                       destacar)
    wb.close()
    return buf.getvalue()


# --------------------------------------------------------------------------
# Quando gerar
# --------------------------------------------------------------------------
def _gravar_atomico(destino: Path, escrever: Callable[[Path], None]) -> None:
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.stem}.", suffix=destino.suffix)
    os.close(fd)
    try:
        escrever(Path(tmp))
        os.chmod(tmp, 0o644)  # mkstemp cria 0600; o boletim é para ser lido e repassado
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Boletineiro:
    """Gera o boletim da hora (uma vez por intervalo de relógio: 18h00, 19h00…) enquanto a apuração
    anda, e o final quando todos os cargos da UF têm totalização final. Os arquivos gravados são a memória:
    reiniciar o processo não repete nem pula boletim."""

    def __init__(self, consultas: Consultas, destino: Path, intervalo_min: int = 60,
                 agora: Callable[[], datetime] = agora_brasilia, destacar: Iterable[str] = ()) -> None:
        if not 0 < intervalo_min <= 24 * 60:
            raise ValueError("intervalo_min deve estar entre 1 e 1440")
        self.consultas, self.destino, self.intervalo_min, self.agora = consultas, destino, intervalo_min, agora
        self.destacar = tuple(destacar)

    def situacao(self) -> str:
        """"sem dados", "andamento" ou "final": todos os cargos NA UF com totalização final. Presidente no
        Brasil não entra: o exterior termina horas depois (ensaio de 2022: RJ final às 00h19, Brasil em 99,94%);
        o boletim final mostra o % dele, e `gerar_boletim.py` faz outro quando ele terminar."""
        t = self.consultas.dados.tabela("totais").filter(
            (pl.col("ABRANGENCIA") == "uf") & (pl.col("UF") == self.consultas.uf))
        if t.is_empty() or not (t["PCT_SECOES_TOTALIZADAS"].fill_null(0) > 0).any():
            return "sem dados"
        return "final" if t["TOTALIZACAO_FINAL"].fill_null(False).all() else "andamento"

    def _horario(self, t: datetime) -> datetime:
        minutos = (t.hour * 60 + t.minute) // self.intervalo_min * self.intervalo_min
        return t.replace(hour=minutos // 60, minute=minutos % 60, second=0, microsecond=0)

    def verificar(self) -> list[Path]:
        """Gera o boletim se for a vez; devolve os arquivos gravados (vazio se não era a vez)."""
        sit = self.situacao()
        if sit == "sem dados":
            return []
        if sit == "final":
            if (self.destino / "boletim_final.html").exists():
                return []
            return self.gerar("boletim_final", "Boletim final", final=True)
        h = self._horario(self.agora())
        nome = f"boletim_{h:%Y-%m-%d_%Hh%M}"
        if (self.destino / f"{nome}.html").exists():
            return []
        return self.gerar(nome, f"Boletim das {h:%Hh%M}".replace("h00", "h"))

    def gerar(self, nome: str, titulo: str, final: bool = False) -> list[Path]:
        """Grava <nome>.html e <nome>.xlsx (e as cópias boletim_ultimo.*), de forma atômica."""
        self.destino.mkdir(parents=True, exist_ok=True)
        b = montar(self.consultas, self.agora(), titulo, final, self.destacar)
        foto = fotografia(b)
        ant = fotografia_anterior(self.destino, antes_de=b["gerado_em"])
        if ant:
            b["anterior"] = {"titulo": ant["titulo"], "gerado_em": ant["gerado_em"]}
            b["mudancas"] = mudancas(ant, foto)
        _gravar_atomico(self.destino / f"{nome}.json",
                        lambda p: p.write_text(json.dumps(foto, ensure_ascii=False, default=str), encoding="utf-8"))
        texto = para_html(b)
        arquivos = []
        # a planilha antes do HTML: o HTML existente é o que marca o boletim como feito
        for base in (nome, "boletim_ultimo"):
            xlsx, pagina = self.destino / f"{base}.xlsx", self.destino / f"{base}.html"
            _gravar_atomico(xlsx, lambda p: para_planilha(b, p))
            _gravar_atomico(pagina, lambda p: p.write_text(texto, encoding="utf-8"))
            arquivos += [pagina, xlsx]
        logger.info("%s gravado em %s", titulo, self.destino / f"{nome}.html")
        return arquivos[:2]

    def executar(self, parar: threading.Event, verificar_s: float = 30.0) -> None:
        """Laço até `parar`: um erro num boletim vai para o log e o próximo é tentado na volta seguinte."""
        while not parar.is_set():
            try:
                self.verificar()
            except Exception:  # o boletim nunca pode derrubar o site nem o coletor
                logger.exception("boletim falhou; nova tentativa em %.0f s", verificar_s)
            parar.wait(verificar_s)
