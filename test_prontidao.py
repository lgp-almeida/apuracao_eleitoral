"""verificar_prontidao.py: conferência das versões fixadas — offline."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

from verificar_prontidao import versoes_fixadas


def test_versoes_fixadas(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("# comentário\npolars==1.44.2  # nota\nnumpy==2.5.1\nausente==1.0\nsem-pin>=2\n", encoding="utf-8")

    def instalada(pacote: str) -> str:
        if pacote == "ausente":
            raise metadata.PackageNotFoundError(pacote)
        return {"polars": "1.44.2", "numpy": "2.6.0"}[pacote]

    ((sit, item, detalhe),) = versoes_fixadas(req, instalada)
    assert sit == "AVISO" and detalhe.startswith("numpy 2.6.0 (fixada 2.5.1)")
    ((sit, _, _),) = versoes_fixadas(Path("requirements.txt"))  # o venv do projeto bate com o arquivo
    assert sit == "OK"


def test_prontidao_ve_as_eleicoes_que_o_coletor_usaria(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rodada 36: com o ele-c.json oficial de 04/10/2026 (2024 primeiro, 2026 por último) o coletor acha
    Governador e Presidente; com um arquivo só de 2024, a prontidão avisa."""
    import json
    from pathlib import Path
    import verificar_prontidao as vp
    from apuracao.divulgacao.cliente import Resposta
    dados = json.loads(Path("tests/fixtures/divulgacao/ele-c-oficial-2026-10-02.json").read_text(encoding="utf-8"))

    def servir(conteudo):
        def get_json(self, caminho):
            return Resposta(caminho, conteudo, None, True) if caminho.endswith("ele-c.json") else None
        return get_json

    monkeypatch.setattr(vp.ClienteDivulgacao, "get_json", servir(dados))
    r = vp._ambiente("oficial")
    assert r[0][0] == "OK" and "ele2026" in r[0][2]
    assert not any("eleições que o coletor usaria" in x[1] for x in r)
    so_2024 = {**dados, "pl": [p for p in dados["pl"] if p["c"] == "ele2024"]}
    monkeypatch.setattr(vp.ClienteDivulgacao, "get_json", servir(so_2024))
    alerta = [x for x in vp._ambiente("oficial") if "eleições que o coletor usaria" in x[1]]
    assert alerta and alerta[0][0] == "AVISO" and "Presidente" in alerta[0][2]


def test_segundo_turno_por_uf(tmp_path: Path) -> None:
    """Rodada 43: UFs com 2º turno para Governador (do resultado do 1º turno), pasta do 2º turno, referência de
    2022 do 2º turno e pasta do 1º turno — sem rede."""
    import json

    import polars as pl

    import verificar_prontidao as vp

    def resultado(pasta: Path, situacao: str) -> None:
        (pasta / "ultimo").mkdir(parents=True)
        pl.DataFrame({"CARGO": [3], "ABRANGENCIA": ["uf"], "SITUACAO": [situacao]}).write_parquet(
            pasta / "ultimo" / "candidatos.parquet")
        pl.DataFrame({"CARGO": [3]}).write_parquet(pasta / "ultimo" / "totais.parquet")
        (pasta / "status.json").write_text(json.dumps({"ambiente": "oficial", "uf": pasta.name[-2:]}))

    resultado(tmp_path / "oficial_ES", "2º turno")
    resultado(tmp_path / "oficial_SP", "Eleito")
    resultado(tmp_path / "historico_2022_t2_ES", "Eleito")
    assert vp.ufs_com_segundo_turno(tmp_path / "oficial", ["ES", "SP", "MG"]) == ["ES"]
    linhas = {item: (sit, det) for sit, item, det in vp._segundo_turno(["ES", "SP"], tmp_path)}
    assert linhas["2º turno para Governador"][0] == "OK" and "ES" in linhas["2º turno para Governador"][1]
    assert linhas["ES: dados do 2º turno"][0] == "OK" and "vazio" in linhas["ES: dados do 2º turno"][1]
    assert linhas["ES: 2022 do 2º turno (Comparação)"][0] == "OK"
    assert linhas["SP: 2022 do 2º turno (Comparação)"][0] == "AVISO"   # falta importar
    resultado(tmp_path / "oficial_t2_SP", "Eleito")
    (tmp_path / "oficial_t2_SP" / "status.json").write_text(json.dumps({"ambiente": "simulado"}))
    linhas = {item: (sit, det) for sit, item, det in vp._segundo_turno(["SP"], tmp_path)}
    assert linhas["SP: dados do 2º turno"][0] == "FALHA"  # pasta da noite com dados de outro ambiente


def test_relogio_usa_o_oficial_e_cai_no_simulado(monkeypatch) -> None:
    """07/10/2026: o simulado saiu do ar (o nome nem resolvia) e a checagem do relógio só olhava para ele."""
    from datetime import datetime, timezone
    from email.utils import format_datetime

    import requests

    import verificar_prontidao as vp

    pedidos: list[str] = []

    class Resp:
        headers = {"Date": format_datetime(datetime.now(timezone.utc), usegmt=True)}

    def get(url, **kw):
        pedidos.append(url)
        if "resultados-sim" in url or fora_do_ar:
            raise requests.ConnectionError("Name or service not known")
        return Resp()
    monkeypatch.setattr(vp.requests, "get", get)
    fora_do_ar = False
    ((sit, _, detalhe),) = vp._relogio()
    assert sit == "OK" and len(pedidos) == 1 and "resultados.tse.jus.br" in pedidos[0]
    fora_do_ar = True
    ((sit, _, detalhe),) = vp._relogio()
    assert sit == "AVISO" and "oficial: ConnectionError" in detalhe and "simulado: ConnectionError" in detalhe
