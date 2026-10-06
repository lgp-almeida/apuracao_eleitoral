"""O mesmo partido em eleições diferentes (rodada 41): número reaproveitado, troca de sigla, fusões."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from apuracao import partidos as pt

M2022 = {14: "PTB", 19: "PODE", 20: "PSC", 51: "PATRIOTA", 65: "PC do B", 77: "SOLIDARIEDADE", 90: "PROS",
         33: "PMN", 22: "PL"}
M2026 = {14: "MISSÃO", 20: "PODE", 25: "PRD", 65: "PCDOB", 77: "SOLIDARIEDADE", 33: "MOBILIZA", 22: "PL"}


def test_correspondencia_2022_2026() -> None:
    c = pt.correspondencia(M2022, M2026, 2022, 2026)
    assert c[25] == [14, 51]          # PRD = PTB + PATRIOTA
    assert c[20] == [19, 20]          # Podemos (19 em 2022) incorporou o PSC (20) e ficou com o 20
    assert c[77] == [77, 90]          # Solidariedade incorporou o PROS
    assert c[65] == [65] and c[33] == [33] and c[22] == [22]  # sigla nova (PCDOB, MOBILIZA) e a mesma (PL)
    assert c[14] == []                # MISSÃO reaproveitou o 14: sem antecessor
    assert pt.sem_sucessor(M2022, M2026, 2022, 2026) == []
    assert pt.correspondencia(M2022, M2022, 2022, 2022)[14] == [14]  # mesmo ano: ele mesmo
    with pytest.raises(ValueError):
        pt.correspondencia(M2026, M2022, 2026, 2022)


def test_evento_so_vale_no_intervalo() -> None:
    assert pt.descendente("PTB", 2018, 2022) == "PTB"     # a fusão do PRD é de 2023
    assert pt.descendente("PTB", 2018, 2026) == "PRD"
    assert pt.descendente("PRP", 2014, 2026) == "PRD"     # PRP → PATRIOTA (2019) → PRD (2023)
    assert pt.chave("PC do B") == pt.chave("PCDOB")


def test_conferir_acusa_o_que_a_tabela_nao_explica() -> None:
    assert pt.conferir({2022: M2022, 2026: M2026}) == []
    avisos = pt.conferir({2022: {**M2022, 40: "PSB"}, 2026: {**M2026, 99: "NOVATO"}})
    assert any("PSB (40) não tem sucessor" in a for a in avisos)
    assert any("NOVATO (99) aparece em 2026 sem antecessor" in a for a in avisos)


def test_rotulo_e_federacao() -> None:
    assert pt.rotulo(["PTB", "PATRIOTA"], 2022) == "PTB + PATRIOTA em 2022"
    assert pt.rotulo([], 2022) == "sem antecessor em 2022"
    assert pt.normalizar_federacao("13-PT/65-PC do B/43-PV") == "PT/PC do B/PV"
    assert pt.normalizar_federacao("PSOL/REDE") == "PSOL/REDE" and pt.normalizar_federacao(None) is None


@pytest.mark.skipif(not all((Path("cache_tse") / f"consulta_cand_{a}.zip").exists() for a in (2014, 2018, 2022, 2026)),
                    reason="cadastros reais de candidatos fora do cache")
def test_tabela_explica_os_cadastros_reais() -> None:
    """Contra os consulta_cand de 2014/2018/2022/2026: toda troca de nº/sigla tem evento em EVENTOS ou NOVOS.
    Se falhar depois de um cadastro novo, registre o partido novo/fusão/renomeação em apuracao/partidos.py."""
    from apuracao import historico as h
    mapas = {}
    for ano in (2014, 2018, 2022, 2026):
        c = h.load_candidatos(ano, Path("cache_tse"))
        mapas[ano] = dict(c.select(pl.col("NR_PARTIDO").cast(pl.Int64, strict=False), "SG_PARTIDO")
                          .drop_nulls().unique("NR_PARTIDO", keep="first").iter_rows())
    assert pt.conferir(mapas) == []
