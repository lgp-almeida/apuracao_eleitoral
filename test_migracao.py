"""Migração de votos entre eleições por local (apuracao/migracao.py), com dados sintéticos sem I/O."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from apuracao import migracao as mg
from apuracao import transferencia as tf

# lado A (2022): PL, PT, branco/nulo, abstenção; lado B (2026): PL, PT, NOVO, branco/nulo, abstenção
MATRIZ = np.array([
    [0.90, 0.02, 0.03, 0.01, 0.04],   # PL 2022
    [0.03, 0.85, 0.04, 0.02, 0.06],   # PT 2022
    [0.05, 0.05, 0.10, 0.70, 0.10],   # branco/nulo
    [0.05, 0.05, 0.02, 0.03, 0.85],   # abstenção
])


def _lados(n_locais: int = 80, semente: int = 3):
    rng = np.random.default_rng(semente)
    loc_a, loc_b, vot_a, vot_b = [], [], [], []
    for i in range(n_locais):
        chave = {"CD_MUNICIPIO": 100 + i % 2, "NR_ZONA": 1 + i % 4, "NR_LOCAL_VOTACAO": 1000 + i}
        nome = {"NM_MUNICIPIO": f"M{i % 2}", "NM_LOCAL_VOTACAO": f"Escola {i}"}
        aptos = int(rng.integers(500, 3000))
        x = rng.dirichlet([5, 3, 0.6, 2.5])   # PL à frente de PT nos dois anos (ordem das categorias)
        q_a = np.round(aptos * x).astype(int)
        q_b = np.round(aptos * (x @ MATRIZ)).astype(int)
        aptos_b = aptos
        if i == 0:                      # eleitorado triplicou: remanejamento grande, sai da conta
            aptos_b = 3 * aptos
        loc_a.append({**chave, **nome, "APTOS": aptos})
        if i != 1:                      # local 1 foi desativado em B
            loc_b.append({**chave, **nome, "APTOS": aptos_b})
        for nr, q in zip((22, 13, 95), q_a[:3]):
            vot_a.append({**chave, "NR_VOTAVEL": nr, "QT_VOTOS": int(q)})
        for nr, q in zip((22, 13, 30, 96), q_b[:4]):
            vot_b.append({**chave, "NR_VOTAVEL": nr, "QT_VOTOS": int(q)})
    loc_b.append({"CD_MUNICIPIO": 100, "NR_ZONA": 1, "NR_LOCAL_VOTACAO": 9999, "NM_MUNICIPIO": "M0",
                  "NM_LOCAL_VOTACAO": "Local novo", "APTOS": 800})   # local novo em B: não entra
    cand_a = {22: ("BOLSO (PL) 2022", "PL"), 13: ("LULA (PT) 2022", "PT")}
    cand_b = {22: ("FLAVIO (PL) 2026", "PL"), 13: ("LULA (PT) 2026", "PT"), 30: ("NOVATO (NOVO) 2026", "NOVO")}
    tipos = {"CD_MUNICIPIO": pl.Int64, "NR_ZONA": pl.Int64, "NR_LOCAL_VOTACAO": pl.Int64}
    return ((pl.DataFrame(loc_a).cast(tipos), pl.DataFrame(vot_a).cast(tipos), cand_a),
            (pl.DataFrame(loc_b).cast(tipos), pl.DataFrame(vot_b).cast(tipos), cand_b))


def test_montar_casa_locais_e_filtra_eleitorado():
    a, b = _lados()
    u = mg.montar(2022, a, 2026, b)
    # 80 locais em A; o 1 sumiu em B, o 0 mudou demais, o novo de B não está em A
    assert u.tabela.height == 78
    assert u.cat1 == ["BOLSO (PL) 2022", "LULA (PT) 2022", tf.BRANCO_NULO, tf.ABSTENCAO]   # sem "Outros" vazio
    assert u.cat2 == ["FLAVIO (PL) 2026", "LULA (PT) 2026", "NOVATO (NOVO) 2026", tf.BRANCO_NULO, tf.ABSTENCAO]
    assert not {"100-1-1000", "101-2-1001", "100-1-9999"} & set(u.tabela["UNIDADE"].to_list())


def test_mapa_swing_pelo_partido():
    a, b = _lados()
    u = mg.montar(2022, a, 2026, b)
    # FLAVIO ↔ BOLSO (PL), LULA ↔ LULA (PT), NOVO sem correspondente e sem "Outros" em A → 1ª categoria
    assert u.mapa_swing == [0, 1, 0, 2, 3]


def test_montar_por_municipio():
    a, b = _lados()
    u = mg.montar(2022, a, 2026, b, municipio=101)
    assert set(u.tabela["CD_MUNICIPIO"].to_list()) == {101}


def test_analisar_recupera_a_matriz():
    a, b = _lados(n_locais=160)
    res = tf.analisar(mg.montar(2022, a, 2026, b), n_boot=0, estrato=None)
    assert np.abs(res.matriz - MATRIZ).max() < 0.03
    v = res.validacao
    assert v["rmse_modelo_medio_pp"] <= v["rmse_swing_medio_pp"]


def test_calcular_recusa_senador(tmp_path):
    with pytest.raises(ValueError, match="Senador"):
        mg.calcular(2022, 2026, "RJ", 5, tmp_path)


# --------------------------------------------------------------------------- camada "variacao" do mapa por local (17a)
class _Comp:
    """Partidos: PL (22) nos dois anos; PRD (25) em 2026 = PTB (14) + PATRIOTA (51) em 2022; MISSÃO (14) novo."""

    def siglas(self, ano: int) -> dict[int, str]:
        return {22: "PL", 14: "PTB", 51: "PATRIOTA"} if ano == 2022 else {22: "PL", 25: "PRD", 14: "MISSÃO"}

    def numeros_do_partido(self, partido: int, ano_a: int, ano_b: int) -> tuple[list[int], list[int]]:
        return {22: ([22], [22]), 25: ([14, 51], [25]), 14: ([], [14])}[partido]


class _Plocal:
    U1, U2, U3 = "3304557000401015", "3304557000401023", "3303302007101015"

    def __init__(self) -> None:
        self.comp = _Comp()

    def _vb(self, ano: int, cargo: int, turno: int) -> pl.DataFrame:
        if ano == 2022:   # U3 só em 2022 (local desativado)
            linhas = [(self.U1, 22, 40), (self.U1, 14, 10), (self.U1, 51, 10), (self.U1, 13, 40), (self.U1, 95, 10),
                      (self.U2, 22, 20), (self.U2, 13, 80), (self.U3, 22, 50), (self.U3, 13, 50)]
        else:
            linhas = [(self.U1, 22, 50), (self.U1, 25, 10), (self.U1, 13, 35), (self.U1, 14, 5), (self.U1, 96, 20),
                      (self.U2, 22, 30), (self.U2, 13, 70)]
        return pl.DataFrame(linhas, schema={"CD_BAIRRO": pl.String, "NR_VOTAVEL": pl.Int64, "QT_VOTOS": pl.Int64},
                            orient="row").with_columns(pl.lit("x").alias("NM_VOTAVEL"))

    def locais(self, ano: int) -> pl.DataFrame:
        return pl.DataFrame({"UNIDADE": [self.U1, self.U2], "LAT": [-22.9, -22.95], "LON": [-43.2, -43.25],
                             "NM_LOCAL_VOTACAO": ["A", "B"], "NM_MUN": ["RIO", "RIO"], "CD_MUN": ["3304557"] * 2,
                             "NR_ZONA": [4, 4], "NR_LOCAL_VOTACAO": [1015, 1023], "QT_ELEITORES": [150, 120]})


def test_variacao_do_partido_por_local():
    from apuracao import mapa_locais as ml
    d = ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="pct_candidato", numero=22)
    assert d["tipo"] == "divergente" and d["unidade"] == "p.p." and d["ano_ref"] == 2022
    pts = {p["u"]: p for p in d["itens"]}
    assert set(pts) == {_Plocal.U1, _Plocal.U2}   # U3 só existe em 2022
    assert pts[_Plocal.U1]["antes"] == pytest.approx(40) and pts[_Plocal.U1]["depois"] == pytest.approx(50)
    assert pts[_Plocal.U2]["valor"] == pytest.approx(10)
    assert "PL" in d["rotulo"] and "2022 → 2026" in d["rotulo"]


def test_variacao_soma_os_antecessores_e_recusa_partido_novo():
    from apuracao import mapa_locais as ml
    d = ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="pct_candidato", numero=25)
    u1 = {p["u"]: p for p in d["itens"]}[_Plocal.U1]
    assert u1["antes"] == pytest.approx(20) and u1["depois"] == pytest.approx(10)   # PTB + PATRIOTA → PRD
    assert "PTB + PATRIOTA em 2022" in d["rotulo"]
    with pytest.raises(ValueError, match="partido novo"):
        ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="pct_candidato", numero=14)


def test_variacao_de_brancos_nulos_e_pedidos_invalidos():
    from apuracao import mapa_locais as ml
    d = ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="brancos_nulos_pct")
    u1 = {p["u"]: p for p in d["itens"]}[_Plocal.U1]
    assert u1["antes"] == pytest.approx(100 * 10 / 110) and u1["depois"] == pytest.approx(100 * 20 / 120)   # % do total
    with pytest.raises(ValueError):
        ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="vencedor")
    with pytest.raises(ValueError):
        ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="pct_candidato")   # sem número
    with pytest.raises(ValueError):
        ml.pontos(_Plocal(), 2026, "variacao", cargo=1, metrica="brancos_nulos_pct", ano_ref=2026)


# --------------------------------------------------------------------------- camada "transferencia" (17b, rodada 47)
def test_camada_destino_dos_eliminados(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from types import SimpleNamespace

    from apuracao import mapa_locais as ml
    pedidos = []
    por = pl.DataFrame({"UNIDADE": ["100-4-1015", "100-4-1023"], "CD_MUNICIPIO": [100, 100], "NR_ZONA": [4, 4],
                        "NR_LOCAL_VOTACAO": [1015, 1023], "ELIMINADOS_1_PCT": [6.0, 9.0],
                        "ELIM_PARA_A (X)_PCT": [40.0, 40.0], "ABST_1_PCT": [20.0, 22.0], "ABST_2_PCT": [21.0, 21.5],
                        "ABST_EXTRA_PP": [1.0, -0.5], "A (X)_2_PCT": [50.0, 45.0], "A (X)_2_AJUSTE_PCT": [48.0, 46.0],
                        "RESIDUO_A_PP": [2.0, -1.0]})

    def calcular(ano, uf, cargo, nivel, cache, municipio=None, n_boot=200):
        pedidos.append((ano, uf, cargo, nivel, n_boot))
        return SimpleNamespace(unidades=SimpleNamespace(cat2=["A (X)", "B (Y)", tf.BRANCO_NULO, tf.ABSTENCAO]),
                               por_unidade=por)
    monkeypatch.setattr(tf, "calcular", calcular)
    plocal = _Plocal()
    plocal.b = SimpleNamespace(uf="RJ", cache=tmp_path)
    plocal.locais = lambda ano: _Plocal.locais(plocal, ano).with_columns(
        pl.Series("CD_MUNICIPIO", [100, 100]), pl.Series("NR_ZONA", [4, 4]))

    d = ml.pontos(plocal, 2022, "transferencia", cargo=1, turno=2, metrica="elim_para_a")
    assert pedidos == [(2022, "RJ", 1, "local", 0)]
    assert d["tipo"] == "sequencial" and d["unidade"] == "%" and "A (X)" in d["rotulo"]
    assert {p["u"]: p["valor"] for p in d["itens"]} == {_Plocal.U1: 40.0, _Plocal.U2: 40.0}   # valor do município
    a = ml.pontos(plocal, 2022, "transferencia", cargo=1, turno=2, metrica="abst_extra")
    assert a["tipo"] == "divergente" and a["lados"] == ["1º turno", "2º turno"] and a["sentido"] == "variacao"
    u1 = {p["u"]: p for p in a["itens"]}[_Plocal.U1]
    assert (u1["valor"], u1["antes"], u1["depois"]) == (1.0, 20.0, 21.0)
    r = ml.pontos(plocal, 2022, "transferencia", cargo=1, turno=2, metrica="residuo_a")
    assert r["sentido"] == "residuo" and {p["u"]: p["depois"] for p in r["itens"]}[_Plocal.U2] == 45.0
    with pytest.raises(ValueError):
        ml.pontos(plocal, 2022, "transferencia", cargo=1, turno=2, metrica="vencedor")
