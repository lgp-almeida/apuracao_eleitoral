"""Fixtures offline no layout real do TSE para os testes do pacote `apuracao`.

Cenário (Rio de Janeiro, zona 4; Niterói só para provar que a chave inclui o município):

  local 1015  PEDRO II   seções 10,11,12 (+13 agregada à 12)  igual em 2024 e 2026 -> MANTIDO
  local 1023  ESCOLA X   2024: seções 20,21 / 2026: só 20, renomeado, ~500 m ao sul,
                         bairro LAPA -> CENTRO, eleitorado 350 -> 150 (-57 %)
  local 1031  CIEP       só em 2024 (seção 30)                      -> DESATIVADO_EM_2026
  local 1040  CRECHE     só em 2026: seção 21 (veio do 1023) e 22 (nova, remanejada do 1031),
                         sem coordenadas                            -> NOVO_EM_2026
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import requests

VS_HEADER = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NR_TURNO", "SG_UF", "SG_UE", "NM_UE",
    "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "DS_CARGO",
    "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO", "SQ_CANDIDATO",
    "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO",
]
# cabeçalho copiado de eleitorado_local_votacao_2026_RJ.csv (igual ao de 2024)
EL_HEADER = [
    "DT_GERACAO", "HH_GERACAO", "AA_ELEICAO", "DT_ELEICAO", "DS_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO",
    "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_TIPO_SECAO_AGREGADA", "DS_TIPO_SECAO_AGREGADA",
    "NR_SECAO_PRINCIPAL", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "CD_TIPO_LOCAL", "DS_TIPO_LOCAL",
    "DS_ENDERECO", "NM_BAIRRO", "NR_CEP", "NR_TELEFONE_LOCAL", "NR_LATITUDE", "NR_LONGITUDE",
    "CD_SITU_LOCAL_VOTACAO", "DS_SITU_LOCAL_VOTACAO", "CD_SITU_ZONA", "DS_SITU_ZONA", "CD_SITU_SECAO",
    "DS_SITU_SECAO", "CD_SITU_LOCALIDADE", "DS_SITU_LOCALIDADE", "CD_SITU_SECAO_ACESSIBILIDADE",
    "DS_SITU_SECAO_ACESSIBILIDADE", "QT_ELEITOR_SECAO", "QT_ELEITOR_ELEICAO_FEDERAL",
    "QT_ELEITOR_ELEICAO_ESTADUAL", "QT_ELEITOR_ELEICAO_MUNICIPAL", "NR_LOCAL_VOTACAO_ORIGINAL",
    "NM_LOCAL_VOTACAO_ORIGINAL", "DS_ENDERECO_LOCVT_ORIGINAL",
]

# subconjunto do cabeçalho de detalhe_votacao_secao_<ano>_<UF|BRASIL>.csv (aptos/comparecimento por seção e cargo)
DET_HEADER = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO",
    "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "DS_CARGO", "QT_APTOS", "QT_COMPARECIMENTO",
    "QT_ABSTENCOES", "NR_LOCAL_VOTACAO",
]

RIO, NIT, SAO = (60011, "RIO DE JANEIRO"), (58653, "NITERÓI"), (71072, "SÃO PAULO")
VEREADOR = "VEREADOR"
CAND = 55555

# (muni, zona, local, nome do local, seção, votável, nome, votos)
VOTES_2024 = [
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 10, CAND, "FULANA DE TAL", 5),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 10, 22222, "BELTRANO", 40),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 10, 55, "PSD", 3),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 10, 95, "VOTO BRANCO", 7),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 10, 96, "VOTO NULO", 9),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 11, 22222, "BELTRANO", 30),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 11, 96, "VOTO NULO", 4),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 12, CAND, "FULANA DE TAL", 8),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 12, 22222, "BELTRANO", 50),
    (RIO, 4, 1015, "COLÉGIO PEDRO II", 12, 55, "PSD", 2),
    (RIO, 4, 1023, "ESCOLA X", 20, CAND, "FULANA DE TAL", 11),
    (RIO, 4, 1023, "ESCOLA X", 20, 22222, "BELTRANO", 20),
    (RIO, 4, 1023, "ESCOLA X", 21, CAND, "FULANA DE TAL", 4),
    (RIO, 4, 1023, "ESCOLA X", 21, 22222, "BELTRANO", 6),
    (RIO, 4, 1031, "CIEP", 30, CAND, "FULANA DE TAL", 1),
    (RIO, 4, 1031, "CIEP", 30, 22222, "BELTRANO", 9),
    # mesmo número em outro município = outra pessoa (eleição municipal)
    (NIT, 71, 1015, "COLÉGIO PEDRO II - NITERÓI", 50, CAND, "OUTRA PESSOA", 100),
    (NIT, 71, 1015, "COLÉGIO PEDRO II - NITERÓI", 50, 45, "PSDB", 45),
]

# suplementar posterior no MESMO arquivo e nas mesmas seções (como Três Rios em 2024): precisa ser descartada
VOTES_2024_SUPLEMENTAR = [(RIO, 4, 1015, "COLÉGIO PEDRO II", 10, CAND, "FULANA DE TAL", 1000)]

# detalhe por seção (vereador 2024, 1º turno): (muni, zona, local, seção, aptos, comparecimento)
# bairro A (local 1015): 920 aptos, 750 compareceram; bairro B (1023 + 1031): 450 aptos, 310 compareceram
DET_2024 = [
    (RIO, 4, 1015, 10, 300, 250), (RIO, 4, 1015, 11, 280, 200), (RIO, 4, 1015, 12, 340, 300),
    (RIO, 4, 1023, 20, 200, 150), (RIO, 4, 1023, 21, 150, 100), (RIO, 4, 1031, 30, 100, 60),
    (NIT, 71, 1015, 50, 310, 200),
]

# perfil do eleitorado por seção: (muni, zona, seção, local, gênero, faixa etária, escolaridade, eleitores)
# gênero 2 = masc., 4 = fem.; escolaridade 1/3 = sem fundamental completo, 6 = médio, 8 = superior completo
# bairro A (1015): 180 eleitores, 100 com superior, 50 sem fundamental, 30 de 16–24, 50 com 60+, 130 mulheres
# bairro B (1023 + 1031): 110 eleitores, 10 com superior, 100 sem fundamental, 10 de 16–24, 20 com 60+, 20 mulheres
PERFIL_2024 = [
    (RIO, 4, 10, 1015, 4, 2529, 8, 100), (RIO, 4, 10, 1015, 2, 6064, 3, 50), (RIO, 4, 11, 1015, 4, 1800, 6, 30),
    (RIO, 4, 20, 1023, 2, 4044, 3, 80), (RIO, 4, 20, 1023, 4, 7074, 1, 20), (RIO, 4, 30, 1031, 2, 2124, 8, 10),
    (NIT, 71, 50, 1015, 4, 3034, 8, 40),
]
PERFIL_HEADER = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
    "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "CD_GENERO", "DS_GENERO", "CD_ESTADO_CIVIL", "DS_ESTADO_CIVIL",
    "CD_FAIXA_ETARIA", "DS_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE", "DS_GRAU_ESCOLARIDADE", "CD_RACA_COR", "DS_RACA_COR",
    "QT_ELEITORES_PERFIL", "QT_ELEITORES_BIOMETRIA",
]
# Censo 2022 por bairro (IBGE): renda (V06004 média, V06006 mediana), básico (V0001 pessoas, AREA_KM2,
# V0005 moradores/domicílio) e cor ou raça (V01317 branca, V01318 preta, V01319 amarela, V01320 parda, V01321 indígena)
CENSO_RENDA = [("3304557001", "Centro Sintético", "8000,50", "6000"), ("3304557002", "Lapa Sintética", "2000", "1500"),
               ("3550308001", "Sé (SP)", "9999", "9999")]
CENSO_BASICO = [("3304557001", "Centro Sintético", "2,0", "10000", "2,5"), ("3304557002", "Lapa Sintética", "0,5", "5000", "3,1"),
                ("3550308001", "Sé (SP)", "1", "1", "1")]
CENSO_COR = [("3304557001", "Centro Sintético", "600", "100", "0", "300", "0"),
             ("3304557002", "Lapa Sintética", "X", "X", "X", "X", "X")]  # sigilo do IBGE
# demografia: V01006 moradores, V01008 mulheres, V01031–V01033 (0 a 14), V01034–V01035 (15 a 24), V01040–V01041 (60+)
CENSO_DEMOGRAFIA_COLS = ["V01006", "V01008", "V01031", "V01032", "V01033", "V01034", "V01035", "V01040", "V01041"]
CENSO_DEMOGRAFIA = [("3304557001", "Centro Sintético", "1000", "550", "50", "50", "50", "60", "40", "150", "100"),
                    ("3304557002", "Lapa Sintética", "800", "400", "X", "X", "X", "100", "60", "40", "40"),  # sigilo em 0–14
                    ("3550308001", "Sé (SP)", "1", "1", "0", "0", "0", "0", "0", "1", "0")]

# (muni, zona, seção, principal, local, nome, endereço, bairro, lat, lon, eleitores, local_original)
EL_2024 = [
    (RIO, 4, 10, -1, 1015, "COLÉGIO PEDRO II", "AV. MARECHAL FLORIANO, 80", "CENTRO", "-22.9035", "-43.1790", 300, 1015),
    (RIO, 4, 11, -1, 1015, "COLÉGIO PEDRO II", "AV. MARECHAL FLORIANO, 80", "CENTRO", "-22.9035", "-43.1790", 280, 1015),
    (RIO, 4, 12, -1, 1015, "COLÉGIO PEDRO II", "AV. MARECHAL FLORIANO, 80", "CENTRO", "-22.9035", "-43.1790", 250, 1015),
    (RIO, 4, 13, 12, 1015, "COLÉGIO PEDRO II", "AV. MARECHAL FLORIANO, 80", "CENTRO", "-22.9035", "-43.1790", 90, 1015),
    (RIO, 4, 20, -1, 1023, "ESCOLA X", "RUA DO LAVRADIO, 12", "LAPA", "-22.9130", "-43.1800", 200, 1023),
    (RIO, 4, 21, -1, 1023, "ESCOLA X", "RUA DO LAVRADIO, 12", "LAPA", "-22.9130", "-43.1800", 150, 1023),
    (RIO, 4, 30, -1, 1031, "CIEP", "RUA Y, 1", "CENTRO", "-22.9200", "-43.1900", 100, 1031),
    (NIT, 71, 50, -1, 1015, "COLÉGIO PEDRO II - NITERÓI", "RUA X, 1", "CENTRO", "-22.89", "-43.12", 310, 1015),
    (SAO, 1, 1, -1, 1001, "ESCOLA SP", "RUA SP", "SÉ", "-23.55", "-46.63", 999, 1001),
]
EL_2026 = [
    (RIO, 4, 10, -1, 1015, "COLEGIO PEDRO II", "AV MARECHAL FLORIANO 80", "Centro", "-22,9035", "-43,1790", 310, 1015),
    (RIO, 4, 11, -1, 1015, "COLEGIO PEDRO II", "AV MARECHAL FLORIANO 80", "Centro", "-22,9035", "-43,1790", 290, 1015),
    (RIO, 4, 12, -1, 1015, "COLEGIO PEDRO II", "AV MARECHAL FLORIANO 80", "Centro", "-22,9035", "-43,1790", 260, 1015),
    (RIO, 4, 13, 12, 1015, "COLEGIO PEDRO II", "AV MARECHAL FLORIANO 80", "Centro", "-22,9035", "-43,1790", 95, 1015),
    (RIO, 4, 20, -1, 1023, "ESCOLA X RENOVADA", "RUA DO LAVRADIO, 12", "CENTRO", "-22,9175", "-43,1800", 150, 1023),
    (RIO, 4, 21, -1, 1040, "CRECHE NOVA", "RUA Z, 5", "LAPA", "-1", "-1", 160, 1040),
    (RIO, 4, 22, -1, 1040, "CRECHE NOVA", "RUA Z, 5", "LAPA", "-1", "-1", 100, 1031),
    (NIT, 71, 50, -1, 1015, "COLÉGIO PEDRO II - NITERÓI", "RUA X, 1", "CENTRO", "-22,89", "-43,12", 320, 1015),
]

TRE_JSON = [
    {"ZONA_ELEITORAL": 4, "NOME_LOCAL": "COLÉGIO PEDRO II", "ENDERECO_LOCAL": "AV MARECHAL FLORIANO 80",
     "BAIRRO_LOCAL": "CENTRO", "MUNICIPIO_LOCAL": "RIO DE JANEIRO", "SECOES_INSTALADAS": "10, 11, 12, 13"},
    {"ZONA_ELEITORAL": 4, "NOME_LOCAL": "ESCOLA X RENOVADA", "ENDERECO_LOCAL": "RUA DO LAVRADIO, 12",
     "BAIRRO_LOCAL": "CENTRO", "MUNICIPIO_LOCAL": "RIO DE JANEIRO", "SECOES_INSTALADAS": "20, 99"},
]


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("latin-1")


def _el_rows(data: list[tuple], year: int, uf_of: dict[int, str]) -> list[list]:
    rows = []
    for (cd, nm), z, sec, princ, loc, nml, end, bairro, lat, lon, qt, orig in data:
        tipo = ("2", "Agregada") if princ != -1 else ("1", "Principal")
        rows.append([
            "29/09/2026", "06:28:09", year, "04/10/2026", "1º Turno", 1, uf_of[cd], str(cd), nm, z, sec,
            tipo[0], tipo[1], princ, loc, nml, 1, "Convencional", end, bairro, "20000000", "-1", lat, lon,
            1, "ATIVO", -1, "ATIVO", 1, "ATIVO", 1, "Ativo", "1", "Com acessibilidade", qt, qt, qt, 0,
            orig, nml, end,
        ])
    return rows


def write_cache(root: Path) -> Path:
    uf_of = {RIO[0]: "RJ", NIT[0]: "RJ", SAO[0]: "SP"}
    vrows = [
        ["29/09/2026", "00:00:00", 2024, tipo, 1, "RJ", str(cd), nm, cd, nm, z, sec, 13, VEREADOR, nr, nome, q, loc,
         "#NULO#" if nr < 100 else 190000000001, nml, "ENDERECO"]
        for tipo, linhas in ((2, VOTES_2024), (1, VOTES_2024_SUPLEMENTAR))
        for (cd, nm), z, loc, nml, sec, nr, nome, q in linhas
    ]
    with zipfile.ZipFile(root / "votacao_secao_2024_RJ.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("votacao_secao_2024_RJ.csv", _csv(VS_HEADER, vrows))
        zf.writestr("leiame.pdf", b"%PDF-fake")

    # detalhe por seção: o CSV _BRASIL (todas as UFs e cargos) é o usado; o _RJ fica incompleto de propósito
    def det(tipo: int, turno: int, cargo: int, ds: str, linhas: list, uf: str = "RJ") -> list[list]:
        return [["29/09/2026", "00:00:00", 2024, tipo, turno, uf, cd, nm, z, sec, cargo, ds, apt, comp, apt - comp, loc]
                for (cd, nm), z, loc, sec, apt, comp in linhas]
    brasil = (det(2, 1, 13, "Vereador", DET_2024)
              + det(1, 1, 13, "Vereador", [(RIO, 4, 1015, 10, 300, 0)])          # suplementar: descartar
              + det(2, 2, 11, "Prefeito", [(RIO, 4, 1015, 10, 300, 200)])        # 2º turno de prefeito
              + det(2, 1, 13, "Vereador", [(SAO, 1, 1001, 1, 999, 1)], uf="SP"))  # outra UF
    with zipfile.ZipFile(root / "detalhe_votacao_secao_2024.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("detalhe_votacao_secao_2024_RJ.csv", _csv(DET_HEADER, brasil[:1]))
        zf.writestr("detalhe_votacao_secao_2024_BRASIL.csv", _csv(DET_HEADER, brasil))
        zf.writestr("leiame.pdf", b"%PDF-fake")

    # perfil do eleitorado por seção: 2024 (QT_ELEITORES_PERFIL) e 2026 (a contagem vira QT_ELEITORES)
    for ano, linhas in ((2024, PERFIL_2024), (2026, PERFIL_2024[:3])):
        header = PERFIL_HEADER if ano == 2024 else [("QT_ELEITORES" if c == "QT_ELEITORES_PERFIL" else c)
                                                    for c in PERFIL_HEADER]
        prow = [["29/09/2026", "00:00:00", ano, "RJ", cd, nm, z, sec, loc, "LOCAL", gen, "X", 1, "SOLTEIRO",
                 faixa, "faixa", esc, "esc", -3, "#NE", qt, qt] for (cd, nm), z, sec, loc, gen, faixa, esc, qt in linhas]
        with zipfile.ZipFile(root / f"perfil_eleitor_secao_{ano}_RJ.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"perfil_eleitor_secao_{ano}_RJ.csv", _csv(header, prow))

    # Censo 2022 por bairro, com os nomes de arquivo do IBGE (versões conhecidas em apuracao.ibge.FONTES)
    censo = root / "ibge_censo2022"
    censo.mkdir(exist_ok=True)
    for nome, header, linhas in (
        ("Agregados_por_bairros_renda_responsavel_BR_20260508_csv", ["CD_BAIRRO", "NM_BAIRRO", "V06004", "V06006"],
         CENSO_RENDA),
        ("Agregados_por_bairros_basico_BR_20260520", ["CD_BAIRRO", "NM_BAIRRO", "AREA_KM2", "v0001", "v0005"], CENSO_BASICO),
        ("Agregados_por_bairros_cor_ou_raca_BR", ["CD_BAIRRO", "NM_BAIRRO", "V01317", "V01318", "V01319", "V01320",
                                                  "V01321"], CENSO_COR),
        ("Agregados_por_bairros_demografia_BR", ["CD_BAIRRO", "NM_BAIRRO", *CENSO_DEMOGRAFIA_COLS], CENSO_DEMOGRAFIA),
    ):
        with zipfile.ZipFile(censo / f"{nome}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(nome.removesuffix("_csv") + ".csv", _csv(header, [list(x) for x in linhas]))

    # 2024: CSV nacional único, com linha de 2º turno que precisa ser ignorada
    rows24 = _el_rows(EL_2024, 2024, uf_of)
    t2 = list(rows24[0])
    t2[EL_HEADER.index("NR_TURNO")], t2[EL_HEADER.index("QT_ELEITOR_SECAO")] = 2, 9999
    with zipfile.ZipFile(root / "eleitorado_local_votacao_2024.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("eleitorado_local_votacao_2024.csv", _csv(EL_HEADER, rows24 + [t2]))
        zf.writestr("leiame.pdf", b"%PDF-fake")

    # 2026: um CSV por UF + BRASIL, como no arquivo real
    rows26 = _el_rows(EL_2026, 2026, uf_of)
    with zipfile.ZipFile(root / "eleitorado_local_votacao_2026.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("eleitorado_local_votacao_2026_RJ.csv", _csv(EL_HEADER, rows26))
        zf.writestr("eleitorado_local_votacao_2026_BRASIL.csv", _csv(EL_HEADER, rows26))
        zf.writestr("leiame.pdf", b"%PDF-fake")

    (root / "consulta_de_locais_de_votacao_2026-09-29.json").write_text(
        json.dumps(TRE_JSON, ensure_ascii=False), encoding="utf-8")
    return root


@pytest.fixture()
def tse_cache(tmp_path: Path) -> Path:
    return write_cache(tmp_path)


def download_sem_rede(mp: pytest.MonkeyPatch) -> None:
    """`v.download` só serve o que está no cache; o resto é 404 (ex.: microdados de 2026), sem ir à rede."""
    import votos_por_local_votacao as v

    original = v.download

    def falso(spec, cache_dir: Path, verify_sha512: bool = False) -> Path:
        if (cache_dir / spec.zip_name).exists():
            return original(spec, cache_dir, verify_sha512)
        raise v.TseDataError(f"404 em {spec.url} (teste offline)")

    mp.setattr(v, "download", falso)

    from apuracao import ibge

    listar = ibge.listar

    def sem_indice(url: str, sessao=requests) -> list[str]:
        if sessao is requests:  # rede de verdade; sessões falsas (test_ibge) seguem normalmente
            raise requests.ConnectionError(f"índice {url} (teste offline)")
        return listar(url, sessao)

    mp.setattr(ibge, "listar", sem_indice)  # sem o índice do IBGE, `ibge.caminho` tenta a versão conhecida


# --------------------------------------------------------------------------
# Divulgação em tempo real: TSE falso servindo recortes reais do simulado 2026
# --------------------------------------------------------------------------
DIVULGACAO_FIXTURES = Path(__file__).parent / "tests" / "fixtures" / "divulgacao"


class FakeResponse:
    def __init__(self, status: int, body: str = "", ctype: str = "application/json", etag: str | None = None):
        self.status_code, self.text = status, body
        self.headers = {"Content-Type": ctype, **({"ETag": etag} if etag else {})}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeTSE:
    """Imita resultados-sim.tse.jus.br: ETag/304, 404 e página HTML no lugar de JSON.

    Arquivos municipais que não estão nos recortes são gerados a partir do arquivo da UF
    do mesmo cargo (tpabr=mu, cdabr=<município>); dep. federal reaproveita o estadual.
    `totalizar(eleicao, municipio)` avança o dt/ht de um município no EA15 (nova totalização).
    `falhas[<arquivo>]` = "rede" ou um código HTTP: o próximo pedido desse arquivo falha assim (uma vez).
    """

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.pedidos: list[str] = []
        self.html = False
        self.falhas: dict[str, str | int] = {}
        self._docs: dict[str, dict] = {p.name: json.loads(p.read_text(encoding="utf-8"))
                                       for p in DIVULGACAO_FIXTURES.glob("*.json")}

    def totalizar(self, eleicao: int, municipio: int, ht: str = "23:59:59", publicar: bool = True) -> None:
        """Nova totalização do município no EA15. `publicar`: os EA20 do município passam a ter sido gerados
        nessa hora (dg/hg); False imita o TSE de 04/10/2026, que anunciava antes de publicar o EA20 novo."""
        ab = self._docs[f"rj-e0{eleicao}-ab.json"]
        for a in ab["abr"]:
            if a["cdabr"] == f"{municipio:05d}":
                a["ht"] = ht
                dia = a.get("dt")
        ab["dg"], ab["hg"] = dia or ab.get("dg"), max(ab.get("hg", ht), ht)  # o EA15 é regerado ao anunciar
        if publicar:
            self.publicar(eleicao, municipio, ht, dia)

    def publicar(self, eleicao: int, municipio: int, hg: str, dg: str | None = None) -> None:
        """EA20 do município "gerados" pelo TSE em dg/hg (o conteúdo não muda)."""
        for cargo in ((1,) if eleicao == 21270 else (3, 5, 6, 7)):
            nome = f"rj{municipio:05d}-c{cargo:04d}-e0{eleicao}-u.json"
            doc = self._doc(nome)
            if doc is None:
                continue
            self._docs[nome] = doc  # passa a ser um documento próprio, alterável
            doc["hg"] = hg
            if dg:
                doc["dg"] = dg

    def avancar_uf(self, eleicao: int, ht: str, pct_secoes: float, fator_primeiro: float) -> None:
        """Nova totalização da UF: hora, % de seções e votos do 1º candidato de cada arquivo da UF."""
        for a in self._docs[f"rj-e0{eleicao}-ab.json"]["abr"]:
            if a["tpabr"] == "uf":
                a["ht"] = ht
        for nome, doc in self._docs.items():
            if nome.startswith("rj-c") and nome.endswith(f"-e0{eleicao}-u.json"):
                doc["ht"] = doc["hg"] = ht
                doc["s"]["pst"] = doc["s"]["pstn"] = f"{pct_secoes:.2f}".replace(".", ",")
                doc["tf"] = "s" if pct_secoes >= 100 else "n"  # apuração em andamento não é totalização final
                cand = doc["carg"][0]["agr"][0]["par"][0]["cand"][0]
                cand["vap"] = str(int(int(cand["vap"]) * fator_primeiro))
                cand["pvapn"] = cand["pvap"] = f"{float(cand['pvapn'].replace(',', '.')) * fator_primeiro:.4f}".replace(".", ",")

    def avancar_municipio(self, eleicao: int, municipio: int, ht: str, pct_secoes: float, votos: dict[int, int],
                          cargos: tuple[int, ...] = (3,)) -> None:
        """Nova totalização de um município: hora no EA15 e, nos arquivos do município, % de
        seções e votos dos candidatos indicados (número -> votos; 0 remove o voto)."""
        self.totalizar(eleicao, municipio, ht)
        for cargo in cargos:
            nome = f"rj{municipio:05d}-c{cargo:04d}-e0{eleicao}-u.json"
            doc = self._doc(nome)
            self._docs[nome] = doc  # passa a ser um documento próprio, alterável
            doc["ht"] = ht
            doc["s"]["pst"] = doc["s"]["pstn"] = f"{pct_secoes:.2f}".replace(".", ",")
            doc["tf"] = "s" if pct_secoes >= 100 else "n"
            for a in doc["carg"][0]["agr"]:
                for p in a["par"]:
                    for c in p["cand"]:
                        if int(c["n"]) in votos:
                            c["vap"] = str(votos[int(c["n"])])
                            c["pvapn"] = c["pvap"] = "1,0"

    def _doc(self, nome: str) -> dict | None:
        if nome in self._docs:
            return self._docs[nome]
        m = re.fullmatch(r"(rj)(\d{5})?-c(\d{4})-e(\d{6})-u\.json", nome)
        if not m:
            return None
        uf, mun, cargo, ele = m.groups()
        base = self._docs.get(f"rj-c{cargo}-e{ele}-u.json") or self._docs.get(f"rj-c0007-e{ele}-u.json")
        if base is None:
            return None
        doc = copy.deepcopy(base)
        if mun:
            doc.update(tpabr="mu", cdabr=mun)
        nomes = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual"}
        for c in doc["carg"]:
            if c["cd"] != str(int(cargo)):  # gerado a partir de outro cargo: acerta código e nome
                c["cd"] = str(int(cargo))
                c["nmn"] = c["nmm"] = nomes.get(int(cargo), c.get("nmn"))
        return doc

    def get(self, url: str, headers: dict | None = None, timeout: float = 0) -> FakeResponse:
        self.pedidos.append(url)
        falha = self.falhas.pop(url.rsplit("/", 1)[-1], None)
        if falha == "rede":
            raise requests.ConnectionError(f"falha simulada em {url}")
        if falha is not None:
            return FakeResponse(int(falha), "<html>erro</html>", "text/html")
        if self.html:
            return FakeResponse(200, "<!DOCTYPE html><html>nova versão em breve</html>", "text/html")
        doc = self._doc(url.rsplit("/", 1)[-1])
        if doc is None:
            return FakeResponse(404, "<html>404</html>", "text/html")
        body = json.dumps(doc, ensure_ascii=False)
        etag = '"' + hashlib.md5(body.encode()).hexdigest() + '"'
        if headers and headers.get("If-None-Match") == etag:
            return FakeResponse(304, "", etag=etag)
        return FakeResponse(200, body, etag=etag)


@pytest.fixture()
def fake_tse() -> FakeTSE:
    return FakeTSE()


# --------------------------------------------------------------------------
# Bairros sintéticos (formato da malha do IBGE já simplificada pelo apuracao.bairros)
# --------------------------------------------------------------------------
# A contém o local 1015 (Pedro II); B contém 1023 (Escola X) e 1031 (CIEP). Niterói fica de fora.
BAIRRO_A, BAIRRO_B = "3304557001", "3304557002"


def _caixa(lat0: float, lat1: float, lon0: float, lon1: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


def escrever_bairros(cache: Path) -> Path:
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"CD_BAIRRO": BAIRRO_A, "NM_BAIRRO": "Centro Sintético", "CD_MUN": 3304557,
                                           "NM_MUN": "Rio de Janeiro"}, "geometry": _caixa(-22.910, -22.900, -43.185, -43.175)},
        {"type": "Feature", "properties": {"CD_BAIRRO": BAIRRO_B, "NM_BAIRRO": "Lapa Sintética", "CD_MUN": 3304557,
                                           "NM_MUN": "Rio de Janeiro"}, "geometry": _caixa(-22.925, -22.911, -43.195, -43.175)},
    ]}
    destino = cache / "malhas" / "bairros_RJ.geojson"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(geo, ensure_ascii=False))
    return destino


# --------------------------------------------------------------------------
# Setores censitários sintéticos (perfil por local de votação)
# --------------------------------------------------------------------------
# Um setor quadrado (~200 m) centrado em cada local de 2024 com coordenada, mais um setor rural afastado
# em Niterói. Renda: Pedro II rico, Escola X médio, CIEP pobre; cor do CIEP sob sigilo; Escola X é favela.
SETORES = [  # (CD_SETOR, CD_MUN, lat, lon, tipo, área km², pop, moradores/dom, domicílios, resp, renda média, renda mediana, cor…)
    ("330455705000001", 3304557, -22.9035, -43.1790, 0, 0.04, 1000, 2.5, 400, 400, 8000.0, 6000.0, (600, 100, 0, 300, 0)),
    ("330455705000002", 3304557, -22.9130, -43.1800, 1, 0.04, 2000, 3.0, 660, 600, 2000.0, 1500.0, (400, 600, 0, 1000, 0)),
    # centro ~100 m ao norte do CIEP (o quadrado ainda contém o local): num raio minúsculo só o "contém" o alcança
    ("330455705000003", 3304557, -22.9191, -43.1900, 0, 0.04, 800, 3.2, 250, 250, 1200.0, 1000.0, (None, None, None, None, None)),
    ("330330205000001", 3303302, -22.8900, -43.1200, 0, 0.04, 500, 2.8, 180, 180, 5000.0, 4000.0, (300, 50, 0, 150, 0)),
    # rural com sigilo PARCIAL (pretos = "X"): tem de sair inteiro da conta de cor, não só a coluna com X
    ("330330205000099", 3303302, -22.9500, -43.0000, 0, 5.00, 50, 3.5, 15, 15, 900.0, 800.0, (20, None, 0, 20, 0)),
]


# sexo e idade por setor: (moradores, mulheres, 0 a 14, 15 a 24, 60 ou mais); o do CIEP sob sigilo
DEMOGRAFIA_SETORES = {"330455705000001": (1000, 520, 100, 150, 300), "330455705000002": (2000, 1000, 600, 400, 100),
                      "330455705000003": (None, None, None, None, None), "330330205000001": (500, 260, 50, 50, 150),
                      "330330205000099": (50, 25, 10, 5, 10)}


# catálogo de contagens (apuracao.censo, rodada 49): N = fração × D, D = 100 em todo indicador; o setor do CIEP
# tem sigilo SÓ na alfabetização. CD_BAIRRO = o bairro da malha sintética em que o centro do setor cai
CATALOGO_SETORES = {"330455705000001": (0.9, BAIRRO_A), "330455705000002": (0.5, BAIRRO_B),
                    "330455705000003": (0.2, BAIRRO_B), "330330205000001": (0.6, None), "330330205000099": (0.1, None)}
# áreas de ponderação sintéticas: Pedro II sozinho na área 001 do Rio; Escola X e CIEP na 002; Niterói numa só
AREA_RIO_1, AREA_RIO_2, AREA_NIT = "3304557001", "3304557002", "3303302001"
AREAS_SETORES = {"330455705000001": AREA_RIO_1, "330455705000002": AREA_RIO_2, "330455705000003": AREA_RIO_2,
                 "330330205000001": AREA_NIT, "330330205000099": AREA_NIT}


def escrever_areas(cache: Path) -> None:
    """ap_composicao.parquet e ap_amostra.parquet (o que `areas_ponderacao` gravaria)."""
    import polars as pl

    from apuracao import areas_ponderacao as ap
    pasta = cache / "ibge_censo2022"
    pasta.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"CD_SETOR": list(AREAS_SETORES), "CD_AP": list(AREAS_SETORES.values()),
                  "CD_MUN": [int(a[:7]) for a in AREAS_SETORES.values()]}).write_parquet(pasta / "ap_composicao.parquet")
    # % de evangélicos: 10 (Rio 1), 40 (Rio 2), 25 (Niterói); os demais indicadores da amostra = 50
    evang = {AREA_RIO_1: 10.0, AREA_RIO_2: 40.0, AREA_NIT: 25.0}
    # contagem estimada (o numerador) de cada indicador da amostra: dá o erro amostral; a área 001 do Rio tem só
    # 50 evangélicos estimados → CV acima de 30% pela tabela abaixo (estimativa pouco confiável)
    contagem = {AREA_RIO_1: 50.0, AREA_RIO_2: 4000.0, AREA_NIT: 2500.0}
    linhas = [{"CD_AP": a, "CD_MUN": int(a[:7]), "NM_MUN": "Rio de Janeiro" if a.startswith("3304557") else "Niterói",
               "NM_AP": f"Área {a[-3:]}", **{k: (evang[a] if k == "pct_evangelicos" else 50.0) for k in ap.AMOSTRA},
               **{f"N_{k}": contagem[a] for k, it in ap.AMOSTRA.items() if it.denominador is not None}}
              for a in evang]
    pl.DataFrame(linhas).write_parquet(pasta / "ap_amostra.parquet")
    # CV (%) pelo tamanho da estimativa, como na planilha do IBGE (RJ): ~ 400 / √tamanho
    pl.DataFrame({"UF": ["RJ"] * 3, "TAMANHO": [100.0, 1000.0, 10000.0], "CV": [40.0, 12.65, 4.0]}).write_parquet(
        pasta / "ap_cv.parquet")


def escrever_setores(cache: Path) -> None:
    """censo_setores_RJ.parquet (o que `perfil_local.setores` gravaria), a malha em shapefile (para o
    método "contém") e o mapa TSE → IBGE dos municípios (para `perfil_local.locais`)."""
    import geopandas as gpd
    import polars as pl

    from apuracao.censo import INDICADORES as INDICADORES_CATALOGO
    from shapely.geometry import box

    pasta = cache / "ibge_censo2022"
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = []
    for cd, mun, lat, lon, tipo, area, pop, mor, dom, resp, rm, rmed, cor in SETORES:
        linhas.append({"CD_SETOR": cd, "CD_MUN": mun, "LON": lon, "LAT": lat, "TIPO": tipo, "AREA_KM2": area,
                       "POP": float(pop), "MORADORES_DOM": mor, "DOMICILIOS": float(dom), "RESP": float(resp),
                       "RENDA_MEDIA": rm, "RENDA_MEDIANA": rmed,
                       **{k: (None if x is None else float(x)) for k, x in zip(("BRANCOS", "PRETOS", "AMARELOS", "PARDOS",
                                                                                "INDIGENAS"), cor)},
                       **{k: (None if x is None else float(x)) for k, x in zip(
                           ("MORADORES_DEM", "MULHERES", "IDADE_0_14", "IDADE_15_24", "IDADE_60_MAIS"), DEMOGRAFIA_SETORES[cd])},
                       "CD_BAIRRO": CATALOGO_SETORES[cd][1],
                       **{f"{x}_{k}": (None if cd == "330455705000003" and k == "pct_alfabetizados"
                                       else (100.0 * CATALOGO_SETORES[cd][0] if x == "N" else 100.0))
                          for k in INDICADORES_CATALOGO for x in ("N", "D")}})
    pl.DataFrame(linhas, schema_overrides={"CD_BAIRRO": pl.String}).write_parquet(pasta / "censo_setores_RJ.parquet")
    d = 0.001  # ~110 m para cada lado
    g = gpd.GeoDataFrame({"CD_SETOR": [x[0] for x in SETORES]},
                         geometry=[box(x[3] - d, x[2] - d, x[3] + d, x[2] + d) for x in SETORES], crs="EPSG:4326")
    tmp = pasta / "shp_tmp"
    tmp.mkdir(exist_ok=True)
    g.to_file(tmp / "RJ_setores_CD2022.shp")
    with zipfile.ZipFile(pasta / "RJ_setores_CD2022.zip", "w") as z:
        for f in tmp.iterdir():
            z.write(f, f.name)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    pl.DataFrame({"UF": ["RJ", "RJ"], "CD_MUNICIPIO": [60011, 58653], "CD_MUNICIPIO_IBGE": [3304557, 3303302],
                  "NM_MUNICIPIO": ["Rio de Janeiro", "Niterói"], "CAPITAL": [True, False], "ZONAS": ["4", "71"]}
                 ).write_parquet(cache / "municipios_tse_ibge.parquet")


# --------------------------------------------------------------------------
# Testes de navegador (marca e2e): um servidor por sessão, Chrome via Playwright
# --------------------------------------------------------------------------
E2E_IBGE = {60011: 3304557, 58653: 3303302, 58009: 3304151}
E2E_T = ("2026-09-29T17:10:00", "2026-09-29T17:30:00", "2026-09-29T18:00:00")
NOME_COM_HTML = '<b id="injetado">CANDIDATO HTML</b>'


@pytest.fixture(scope="session")
def site(tmp_path_factory: pytest.TempPathFactory):
    """Site no ar numa porta livre. Dados 2026 do TSE falso com 4 totalizações do cargo de governador
    (UF e municípios avançando), referência 2022 sintética, malha e cadastro de eleitorado sintéticos."""
    import socket
    import threading
    import time

    import polars as pl
    import uvicorn

    from apuracao import historico as h
    from apuracao.divulgacao.cliente import ClienteDivulgacao, LimitadorTaxa
    from apuracao.divulgacao.coletor import Coletor
    from apuracao.web.app import create_app
    from test_historico import NIT, RIO, VOTOS_BR, VOTOS_UF, _cand, _detalhe, _votos

    raiz = tmp_path_factory.mktemp("e2e")
    cache = raiz / "cache"
    cache.mkdir()
    write_cache(cache)
    (cache / "malhas").mkdir()
    malha = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": str(c)},
         "geometry": {"type": "Polygon", "coordinates": [[[-43 - i, -22], [-43.5 - i, -22], [-43.5 - i, -22.5],
                                                           [-43 - i, -22]]]}}
        for i, c in enumerate(E2E_IBGE.values())]}
    (cache / "malhas" / "municipios_RJ.geojson").write_text(json.dumps(malha))
    ufs = {"type": "FeatureCollection", "features": [  # RJ e SP (o EA14 da fixture tem as duas)
        {"type": "Feature", "properties": {"codarea": c},
         "geometry": {"type": "Polygon", "coordinates": [[[x, -22], [x - 2, -22], [x - 2, -24], [x, -22]]]}}
        for c, x in (("33", -41), ("35", -45))]}
    (cache / "malhas" / "ufs_BR.geojson").write_text(json.dumps(ufs))
    escrever_bairros(cache)
    escrever_setores(cache)
    escrever_areas(cache)

    fake = FakeTSE()
    gov = fake._doc("rj-c0003-e021272-u.json")["carg"][0]
    gov["agr"][-1]["par"][0]["cand"][0]["nmu"] = NOME_COM_HTML  # o painel precisa mostrar como texto
    numero = int(fake._doc("rj60011-c0003-e021272-u.json")["carg"][0]["agr"][0]["par"][0]["cand"][0]["n"])
    dados = raiz / "dados"
    col = Coletor(ClienteDivulgacao("simulado", sessao=fake, limitador=LimitadorTaxa(1e9)), dados)
    col.ciclo()
    for ht, mun, pct, fator in ((E2E_T[0], RIO, 20.0, 1.10), (E2E_T[1], NIT, 40.0, 0.95), (E2E_T[2], RIO, 80.0, 1.05)):
        fake.avancar_uf(21272, ht[11:], pct, fator)
        fake.avancar_municipio(21272, mun, ht[11:], pct, {numero: int(pct * 100)})
        col.ciclo()

    from apuracao import bairros as br
    sem_rede = pytest.MonkeyPatch()  # siglas dos partidos sem baixar o cadastro de candidatos do TSE
    sem_rede.setattr(br.ComparacaoBairros, "siglas", lambda self, ano: {55: "PSD", 22: "PL"})
    download_sem_rede(sem_rede)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(h, "load_detalhe", lambda ano, c: _detalhe())
        mp.setattr(h, "load_candidatos", lambda ano, c: _cand())
        mp.setattr(h, "load_votos", lambda ano, uf, c: (_votos(VOTOS_UF), _votos(VOTOS_BR)))
        mp.setattr(h, "fonte_padrao", lambda ano, uf, c: "secao")  # os votos acima são da fonte "secao"
        mp.setattr(h, "municipios_tse_ibge", lambda uf, c: pl.DataFrame(
            {"UF": ["RJ", "RJ"], "CD_MUNICIPIO": [RIO, NIT], "CD_MUNICIPIO_IBGE": [E2E_IBGE[RIO], E2E_IBGE[NIT]],
             "NM_MUNICIPIO": ["RIO DE JANEIRO", "NITERÓI"], "CAPITAL": [True, False], "ZONAS": ["4,5", "71"]}))
        h.importar(2022, "RJ", 1, raiz, raiz / "ref")

    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        porta = sk.getsockname()[1]
    app = create_app(dados, "RJ", cache, referencia=raiz / "ref")
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.05)
    yield {"url": f"http://127.0.0.1:{porta}/", "numero": numero, "app": app, "dados": dados, "cache": cache,
           "ref": raiz / "ref"}
    servidor.should_exit = True
    thread.join(timeout=5)
    sem_rede.undo()


@pytest.fixture(scope="session")
def site_multi(site: dict, tmp_path_factory: pytest.TempPathFactory):
    """Site com várias UFs (rodada 39) sobre os dados da fixture `site`: RJ e uma cópia como "AC" (os arquivos
    servem ao roteamento e ao seletor), mais SP sem dados."""
    import shutil
    import socket
    import threading
    import time

    import uvicorn

    from apuracao.web.app import create_app
    from apuracao.web.multi import EntradaUF, create_multi_app

    raiz = tmp_path_factory.mktemp("multi")
    shutil.copytree(site["dados"], raiz / "oficial_AC")
    entradas = [EntradaUF("RJ", site["dados"], site["ref"]), EntradaUF("AC", raiz / "oficial_AC"),
                EntradaUF("SP", raiz / "oficial_SP")]
    app = create_multi_app(entradas, "RJ", lambda e: create_app(e.dados, e.uf, site["cache"], referencia=e.referencia))
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        porta = sk.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.05)
    yield {"url": f"http://127.0.0.1:{porta}/", "numero": site["numero"]}
    servidor.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def navegador():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # noqa: BLE001 - sem Chrome instalado: pula, não falha
            pytest.skip(f"Chrome indisponível para os testes de navegador: {exc}")
        yield b
        b.close()


def _nova_pagina(navegador, **contexto):
    ctx = navegador.new_context(permissions=["clipboard-read", "clipboard-write"], **contexto)
    pg = ctx.new_page()
    pg.route("**/tile.openstreetmap.org/**", lambda r: r.abort())  # sem internet nos testes
    pg.set_default_timeout(10_000)
    return ctx, pg


@pytest.fixture()
def pagina(navegador, site):
    ctx, pg = _nova_pagina(navegador, viewport={"width": 1400, "height": 1000})
    yield pg
    ctx.close()


@pytest.fixture()
def nova_pagina(navegador, site):
    """Fábrica de páginas com opções de contexto (ex.: color_scheme="dark")."""
    abertos = []

    def criar(**contexto):
        ctx, pg = _nova_pagina(navegador, **contexto)
        abertos.append(ctx)
        return pg

    yield criar
    for ctx in abertos:
        ctx.close()


def abrir(pg, site: dict, hash_: str = "") -> None:
    pg.goto(site["url"] + hash_)


def endereco(pg) -> tuple[str, dict[str, str]]:
    """(aba, parâmetros) do endereço atual."""
    from urllib.parse import parse_qs
    caminho, _, q = pg.evaluate("location.hash").lstrip("#").partition("?")
    return caminho, {k: v[0] for k, v in parse_qs(q).items()}


def esperar_endereco(pg, condicao: str) -> None:
    pg.wait_for_function(f"() => {{ const h = decodeURIComponent(location.hash); return {condicao}; }}")


@pytest.fixture(autouse=True)
def _sem_pausa_entre_retomadas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Download que cai é continuado depois de uma pausa (rodada 58); nos testes, sem esperar."""
    from apuracao import microdados

    monkeypatch.setattr(microdados, "PAUSA_RETOMADA_S", 0.0)
