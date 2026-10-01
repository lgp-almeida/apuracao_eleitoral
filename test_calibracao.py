"""Constantes calibradas com apurações reais — o ÚNICO teste a atualizar ao recalibrar.

Estes valores vêm de `validar_projecao.py` (apuração de 2022 reconstituída seção a seção). Ao recalibrar
(docs/RECALIBRAR_MARGENS.md), cole as tabelas PROPOSTAS no código e aqui, e registre a rodada. Os demais
testes leem as constantes do código e não precisam mudar.
"""

from __future__ import annotations

import polars as pl

from apuracao import projecao as pj
from apuracao import projecao_cadeiras as pc

CALIBRADO_COM = "2022"  # eleições usadas (atualizar junto com as tabelas)
MARGEM_PP = [(10, 8.07), (20, 4.51), (30, 3.78), (40, 3.10), (50, 2.67), (60, 2.07), (70, 1.55), (80, 1.17),
             (90, 0.82), (100, 0.43)]
SIGMA = [(10, 0.142, 0.425), (20, 0.130, 0.338), (30, 0.126, 0.289), (40, 0.109, 0.239), (50, 0.086, 0.194),
         (60, 0.072, 0.145), (70, 0.059, 0.131), (80, 0.038, 0.093), (90, 0.022, 0.052), (100, 0.012, 0.025)]


def test_constantes_calibradas() -> None:
    assert pj.MARGEM_PP == MARGEM_PP, f"MARGEM_PP mudou: recalibrado com {CALIBRADO_COM}? atualize este teste e a rodada"
    assert pc.SIGMA == SIGMA, f"SIGMA mudou: recalibrado com {CALIBRADO_COM}? atualize este teste e a rodada"


def test_formato_das_tabelas() -> None:
    """Qualquer calibração precisa cobrir (0, 100] e nunca crescer com a apuração."""
    for tab in (pj.MARGEM_PP, [(lim, a) for lim, a, _ in pc.SIGMA], [(lim, c) for lim, _, c in pc.SIGMA]):
        limites = [lim for lim, _ in tab]
        valores = [x for _, x in tab]
        assert limites == sorted(limites) and limites[-1] == 100 and limites[0] > 0
        assert valores == sorted(valores, reverse=True) and all(x > 0 for x in valores)
    assert all(c > a for _, a, c in pc.SIGMA)  # candidato erra mais que agremiação


def test_saida_pronta_para_colar() -> None:
    texto = pj.formatar_tabela("MARGEM_PP", pj.MARGEM_PP)
    ns: dict = {}
    exec(texto, ns)  # o que o validar_projecao imprime é Python válido e igual à constante
    assert ns["MARGEM_PP"] == pj.MARGEM_PP
    exec(pj.formatar_tabela("SIGMA", pc.SIGMA), ns)
    assert ns["SIGMA"] == pc.SIGMA


def test_calibrar_margem_com_dois_anos_junta_os_erros() -> None:
    e22 = pl.DataFrame({"PCT_APURADO": [5.0] * 20, "ERRO_PROJECAO": [1.0] * 20})
    e26 = pl.DataFrame({"PCT_APURADO": [5.0] * 20, "ERRO_PROJECAO": [3.0] * 20})
    so22 = dict(pj.calibrar(e22, faixas=[10, 100]))
    juntos = dict(pj.calibrar(pl.concat([e22, e26]), faixas=[10, 100]))
    assert so22[10] == 1.0 and juntos[10] == 3.0  # o p95 conjunto cobre o ano mais difícil
    assert pj.cobertura(e26, [(10, 1.0), (100, 0.1)]) == 0.0 and pj.cobertura(e26, [(10, 3.0), (100, 0.1)]) == 1.0
