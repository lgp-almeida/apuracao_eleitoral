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


def test_rotas_pesadas_iguais_as_do_site() -> None:
    """core/api.ts dá tempo-limite longo às mesmas rotas que o site trata como pesadas (ROTAS_PESADAS)."""
    from apuracao.web.app import ROTAS_PESADAS

    texto = (FONTE / "src" / "core" / "api.ts").read_text(encoding="utf-8")
    bloco = re.search(r"export const ROTAS_PESADAS = \[(.*?)\] as const;", texto, re.S)
    assert bloco
    assert re.findall(r'"([^"]+)"', bloco.group(1)) == list(ROTAS_PESADAS)


def test_camadas_do_css_na_ordem_do_design_system() -> None:
    """A ordem das camadas decide quem vence (estilos/index.css); o build mantém só a ordem de 1ª aparição."""
    fonte = (FONTE / "src" / "estilos" / "index.css").read_text(encoding="utf-8")
    declarada = re.search(r"^@layer ([\w, ]+);", fonte, re.M)
    assert declarada
    esperada = [c.strip() for c in declarada.group(1).split(",")]
    (css,) = (STATIC / "assets").glob("index-*.css")
    vistas: list[str] = []
    for nome in re.findall(r"@layer ([\w-]+)\s*\{", css.read_text(encoding="utf-8")):
        if nome not in vistas:
            vistas.append(nome)
    assert vistas == esperada
