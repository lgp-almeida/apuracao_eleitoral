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
