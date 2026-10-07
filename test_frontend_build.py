"""O build versionado em apuracao/web/static/ corresponde à fonte em apuracao/web/frontend/ (sem Node).

O build grava em static/build.json a impressão digital da fonte (frontend/construcao.ts); este teste refaz a
mesma conta. Se falhar: `cd apuracao/web/frontend && npm ci && npm run build` e inclua static/ no commit.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

WEB = Path(__file__).parent / "apuracao" / "web"
FONTE = WEB / "frontend"
STATIC = WEB / "static"


def _lista_da_construcao(nome: str) -> list[str]:
    """Lê ARQUIVOS_RAIZ/PASTAS do próprio construcao.ts: uma regra só, nos dois lados."""
    texto = (FONTE / "construcao.ts").read_text(encoding="utf-8")
    bloco = re.search(rf"export const {nome} = \[(.*?)\];", texto, re.S)
    assert bloco, nome
    return re.findall(r'"([^"]+)"', bloco.group(1))


def _impressao() -> dict[str, object]:
    arquivos = list(_lista_da_construcao("ARQUIVOS_RAIZ"))
    for pasta in _lista_da_construcao("PASTAS"):
        arquivos += [p.relative_to(FONTE).as_posix() for p in (FONTE / pasta).rglob("*") if p.is_file()]
    h = hashlib.sha256()
    for caminho in sorted(arquivos):
        h.update(caminho.encode() + b"\0" + (FONTE / caminho).read_bytes() + b"\0")
    return {"sha256": h.hexdigest(), "arquivos": len(arquivos)}


def test_build_corresponde_a_fonte() -> None:
    gravado = json.loads((STATIC / "build.json").read_text(encoding="utf-8"))
    assert gravado == _impressao(), "fonte do front-end mudou sem build novo: rode `npm run build` em frontend/"


def test_pagina_do_build_usa_caminhos_relativos() -> None:
    """O site de várias UFs monta cada uma em /<uf>/: caminho absoluto quebraria a página fora da raiz."""
    pagina = (STATIC / "index.html").read_text(encoding="utf-8")
    referencias = re.findall(r'(?:src|href)="([^"#]+)"', pagina)
    assert referencias and all(r.startswith("./assets/") for r in referencias), referencias
    for r in referencias:
        assert (STATIC / r).is_file(), r
