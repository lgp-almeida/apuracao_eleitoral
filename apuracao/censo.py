"""Indicadores de CONTAGEM do universo do Censo 2022 por setor censitário (rodada 49).

Cada indicador é 100 × Σ numerador ÷ Σ denominador, com as colunas tiradas dos agregados por setor do IBGE
(catálogo de arquivos em `apuracao.ibge.FONTES`). O mesmo catálogo vale para as três unidades do Perfil × voto:
bairro (setores do bairro, pela malha), local de votação (setores ligados ao local) e área de ponderação
(setores da área). O setor guarda o numerador e o denominador (N_<chave>, D_<chave>), não o percentual:
somar percentuais de setores de tamanhos diferentes seria errado.

Sigilo ("X" do IBGE) é por indicador: um "X" em qualquer coluna dele tira o setor da conta DAQUELE indicador
(N e D nulos); nunca vale zero. A conta dos outros indicadores do mesmo setor não muda.

Sem I/O: quem lê os CSV é `perfil_local.setores`.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class Indicador:
    rotulo: str
    numerador: tuple[tuple[str, str], ...]    # (fonte do ibge.FONTES, coluna)
    denominador: tuple[tuple[str, str], ...]
    unidade: str                              # o que se conta: "moradores", "domicílios"…


_ALF, _D1, _D2 = "setores_alfabetizacao", "setores_domicilio1", "setores_domicilio2"
_PAR, _ENT, _BAS = "setores_parentesco", "setores_entorno", "setores_basico"
_DPPO = ((_D1, "V00001"),)  # domicílios particulares permanentes ocupados (o denominador do domicílio)


def _de(fonte: str, *colunas: str) -> tuple[tuple[str, str], ...]:
    return tuple((fonte, c) for c in colunas)


# entorno (moradores em domicílios do setor escolhido para o entorno): "sim" ÷ ("sim" + "não"), sem o "não
# declarado"; setor fora da pesquisa do entorno não tem as colunas preenchidas e fica nulo
INDICADORES: dict[str, Indicador] = {
    # escolaridade e moradia
    "pct_alfabetizados": Indicador("% de alfabetizados (15 anos ou mais)", _de(_ALF, "V00900"),
                                   _de(_ALF, "V00900", "V00901"), "moradores"),
    "pct_apartamentos": Indicador("% de domicílios em apartamento", _de(_D1, "V00049"), _DPPO, "domicílios"),
    "pct_unipessoais": Indicador("% de domicílios com um só morador", _de(_D1, "V00017"), _DPPO, "domicílios"),
    "pct_resp_mulher": Indicador("% de domicílios chefiados por mulher", _de(_PAR, "V01063"), _de(_PAR, "V01042"),
                                 "domicílios"),
    # saneamento
    "pct_agua_rede": Indicador("% de domicílios com água da rede geral", _de(_D2, "V00111"), _DPPO, "domicílios"),
    "pct_esgoto_rede": Indicador("% de domicílios com esgoto na rede (geral, pluvial ou fossa ligada)",
                                 _de(_D2, "V00309", "V00310"), _DPPO, "domicílios"),
    "pct_lixo_coletado": Indicador("% de domicílios com lixo coletado", _de(_D2, "V00397", "V00398"), _DPPO,
                                   "domicílios"),
    "pct_sem_banheiro": Indicador("% de domicílios sem banheiro nem sanitário", _de(_D2, "V00238"), _DPPO,
                                  "domicílios"),
    # entorno urbanístico
    "pct_rua_pavimentada": Indicador("% de moradores em rua pavimentada", _de(_ENT, "V05206"),
                                     _de(_ENT, "V05206", "V05207"), "moradores"),
    "pct_iluminacao": Indicador("% de moradores em rua com iluminação pública", _de(_ENT, "V05212"),
                                _de(_ENT, "V05212", "V05213"), "moradores"),
    "pct_calcada": Indicador("% de moradores em rua com calçada", _de(_ENT, "V05221"),
                             _de(_ENT, "V05221", "V05222"), "moradores"),
    "pct_ponto_onibus": Indicador("% de moradores em rua com ponto de ônibus", _de(_ENT, "V05215"),
                                  _de(_ENT, "V05215", "V05216"), "moradores"),
    "pct_arborizacao": Indicador("% de moradores em rua com árvores", _de(_ENT, "V05231", "V05232", "V05233"),
                                 _de(_ENT, "V05230", "V05231", "V05232", "V05233"), "moradores"),
    # povos e comunidades tradicionais
    "pct_indigenas": Indicador("% de pessoas indígenas", _de("setores_indigenas", "V01690"), _de(_BAS, "V0001"),
                               "moradores"),
    "pct_quilombolas": Indicador("% de pessoas quilombolas", _de("setores_quilombolas", "V03196"),
                                 _de(_BAS, "V0001"), "moradores"),
}
ROTULOS = {k: i.rotulo for k, i in INDICADORES.items()}
FONTES_ROTULO = {k: f"IBGE — Censo 2022 ({i.unidade})" for k, i in INDICADORES.items()}
COLUNAS = [c for k in INDICADORES for c in (f"N_{k}", f"D_{k}")]  # o que `perfil_local.setores` grava


def colunas_por_fonte() -> dict[str, list[str]]:
    """Fonte do IBGE → colunas que o catálogo lê dela (ordenadas, sem repetição)."""
    out: dict[str, set[str]] = {}
    for ind in INDICADORES.values():
        for fonte, col in (*ind.numerador, *ind.denominador):
            out.setdefault(fonte, set()).add(col)
    return {f: sorted(c) for f, c in out.items()}


def _num(col: str) -> pl.Expr:
    """Contagem do IBGE em texto; "X" (sigilo), "." e vazio → nulo."""
    return pl.col(col).cast(pl.String).str.strip_chars().str.replace(",", ".").cast(pl.Float64, strict=False)


def _soma(cols: tuple[tuple[str, str], ...]) -> pl.Expr:
    return sum((_num(c) for _, c in cols), pl.lit(0.0))  # `+` propaga o nulo (sum_horizontal o trataria como 0)


def contagens(brutos: pl.DataFrame) -> pl.DataFrame:
    """CD_SETOR + colunas brutas do IBGE (nomes V…) → CD_SETOR + N_<chave>/D_<chave>. Coluna que falta no
    quadro (fonte que o setor não tem, ex.: entorno fora da pesquisa) conta como sigilo: nulo."""
    tem = set(brutos.columns)
    exprs = []
    for k, ind in INDICADORES.items():
        if all(c in tem for _, c in (*ind.numerador, *ind.denominador)):
            n, d = _soma(ind.numerador), _soma(ind.denominador)
            ok = n.is_not_null() & d.is_not_null()
            exprs += [pl.when(ok).then(n).alias(f"N_{k}"), pl.when(ok).then(d).alias(f"D_{k}")]
        else:
            exprs += [pl.lit(None, pl.Float64).alias(f"N_{k}"), pl.lit(None, pl.Float64).alias(f"D_{k}")]
    return brutos.select("CD_SETOR", *exprs)


def taxa(chave: str) -> pl.Expr:
    """Expressão de agregação (dentro de `group_by(...).agg`): 100 × ΣN ÷ ΣD dos setores com dado; sem dado
    ou denominador zero → nulo."""
    n, d = pl.col(f"N_{chave}"), pl.col(f"D_{chave}")
    ok = n.is_not_null() & d.is_not_null()
    den = d.filter(ok).sum()
    return pl.when(den > 0).then(100 * n.filter(ok).sum() / den).alias(chave)


def taxas(setores: pl.DataFrame, por: str) -> pl.DataFrame:
    """Os indicadores do catálogo por unidade (`por` = coluna da unidade nos setores); só os que têm N/D."""
    ks = [k for k in INDICADORES if f"N_{k}" in setores.columns and f"D_{k}" in setores.columns]
    return setores.filter(pl.col(por).is_not_null()).group_by(por).agg(*[taxa(k) for k in ks])
