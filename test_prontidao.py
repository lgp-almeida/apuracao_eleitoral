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
