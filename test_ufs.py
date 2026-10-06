"""Pastas de dados por UF e lista das UFs (rodada 39) — offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apuracao import ufs


def _pasta(p: Path, uf: str | None) -> Path:
    p.mkdir(parents=True)
    if uf:
        (p / "status.json").write_text(json.dumps({"uf": uf}))
    return p


def test_dir_uf_pasta_nova_e_legado(tmp_path: Path) -> None:
    base = tmp_path / "oficial"
    assert ufs.dir_uf(base, "sp") == tmp_path / "oficial_SP"  # nada existe: pasta nova
    assert ufs.dir_uf(base, "RJ") == tmp_path / "oficial_RJ"
    _pasta(base, "RJ")  # pasta antiga, do RJ
    assert ufs.dir_uf(base, "RJ") == base
    assert ufs.dir_uf(base, "SP") == tmp_path / "oficial_SP"  # nunca a pasta do RJ para outra UF
    _pasta(tmp_path / "oficial_RJ", "RJ")  # a pasta nova, se existir, vence
    assert ufs.dir_uf(base, "RJ") == tmp_path / "oficial_RJ"


def test_dir_uf_pasta_antiga_de_outra_uf(tmp_path: Path) -> None:
    base = _pasta(tmp_path / "historico_2022_t1", "SP")
    assert ufs.dir_uf(base, "RJ") == tmp_path / "historico_2022_t1_RJ"
    assert ufs.uf_da_pasta(base) == "SP" and ufs.uf_da_pasta(tmp_path / "nada") is None


def test_lista() -> None:
    todas = ufs.lista("todas")
    assert len(todas) == 27 and todas[0] == "AC" and "DF" in todas
    assert ufs.lista(["TODAS"]) == todas
    assert ufs.lista(["sp", "MG", "sp", " "]) == ["SP", "MG"]
    with pytest.raises(ValueError, match="XX"):
        ufs.lista(["SP", "XX"])
