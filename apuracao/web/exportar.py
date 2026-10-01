"""Mapa como arquivo (PNG, JPEG ou SVG), desenhado no servidor com matplotlib/geopandas.

A página manda as cores de cada polígono e a legenda EXATAMENTE como estão na tela (a
mesma classificação, escala fixa da linha do tempo, tema); o servidor só desenha, com
título, legenda e fonte no próprio arquivo — independente do mapa de fundo (OpenStreetMap).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # sem janela: roda dentro do servidor
matplotlib.rcParams["svg.fonttype"] = "none"  # SVG com texto de verdade (editável no Inkscape/Illustrator)
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

FORMATOS = {"png": "image/png", "jpeg": "image/jpeg", "svg": "image/svg+xml"}
_COR = re.compile(r"^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{3}$|^rgba?\([\d\s.,%]+\)$")
MAX_POLIGONOS, MAX_LEGENDA, MAX_TEXTO = 10_000, 30, 300


class PedidoInvalido(ValueError):
    """Dados do pedido de exportação fora do esperado (vira HTTP 400)."""


@dataclass
class PedidoMapa:
    formato: str
    titulo: str
    cores: dict[str, str]                       # id do polígono -> cor
    legenda: list[tuple[str, str]]              # (cor, texto)
    subtitulo: str = ""
    fonte: str = ""
    fundo: str = "#fcfcfb"
    texto: str = "#0b0b0b"
    sem_dado: str = "#f0efec"
    contorno: str = "#fcfcfb"
    dpi: int = 200
    extras: list[str] = field(default_factory=list)  # linhas de nota no rodapé


def _cor(valor: str, campo: str) -> str:
    v = (valor or "").strip()
    if not _COR.match(v):
        raise PedidoInvalido(f"cor inválida em {campo}: {valor!r}")
    return v


def _texto(valor: str, campo: str) -> str:
    v = str(valor or "")
    if len(v) > MAX_TEXTO:
        raise PedidoInvalido(f"{campo} longo demais")
    return v


def validar(p: PedidoMapa) -> PedidoMapa:
    if p.formato not in FORMATOS:
        raise PedidoInvalido(f"formato deve ser um de {sorted(FORMATOS)}")
    if len(p.cores) > MAX_POLIGONOS or len(p.legenda) > MAX_LEGENDA:
        raise PedidoInvalido("mapa grande demais para exportar")
    if not 50 <= p.dpi <= 600:
        raise PedidoInvalido("dpi deve estar entre 50 e 600")
    p.cores = {str(k): _cor(v, f"cores[{k}]") for k, v in p.cores.items()}
    p.legenda = [(_cor(c, "legenda"), _texto(t, "legenda")) for c, t in p.legenda]
    for campo in ("fundo", "texto", "sem_dado", "contorno"):
        setattr(p, campo, _cor(getattr(p, campo), campo))
    p.titulo, p.subtitulo, p.fonte = (_texto(p.titulo, "titulo"), _texto(p.subtitulo, "subtitulo"),
                                      _texto(p.fonte, "fonte"))
    p.extras = [_texto(x, "extras") for x in p.extras[:5]]
    return p


def renderizar(geo: dict, chave: str, pedido: PedidoMapa, contornos: dict | None = None) -> bytes:
    """`geo`: FeatureCollection dos polígonos coloridos; `chave`: propriedade com o id (ex.: codarea).
    `contornos` (opcional): outra FeatureCollection desenhada só em linha, por cima (ex.: municípios
    sobre os bairros)."""
    p = validar(pedido)
    gdf = gpd.GeoDataFrame.from_features(geo["features"], crs="EPSG:4326")
    if chave not in gdf.columns:
        raise PedidoInvalido(f"a malha não tem a propriedade {chave}")
    gdf["_cor"] = gdf[chave].astype(str).map(p.cores).fillna(p.sem_dado)

    fig = plt.figure(figsize=(12, 8.2), facecolor=p.fundo)
    ax = fig.add_axes((0.02, 0.08, 0.66, 0.80))
    ax.set_facecolor(p.fundo)
    if contornos is not None and not contornos.get("features"):
        contornos = None  # malha vazia (ex.: IBGE fora do ar): desenha sem contorno
    if (gdf.geom_type == "Point").all():
        # locais de votação: municípios por baixo, só os pontos que a página pintou, área ∝ eleitorado
        if contornos:
            gpd.GeoDataFrame.from_features(contornos["features"], crs="EPSG:4326").plot(
                ax=ax, color=p.sem_dado, edgecolor=p.texto, linewidth=0.3, alpha=0.6)
        gdf = gdf[gdf[chave].astype(str).isin(p.cores)]
        tam = (gdf["QT_ELEITORES"].fillna(0).clip(lower=0) ** 0.5 / 6).clip(2, 40) if "QT_ELEITORES" in gdf else 6
        gdf.plot(ax=ax, color=gdf["_cor"], markersize=tam, edgecolor=p.contorno, linewidth=0.2)
    else:
        gdf.plot(ax=ax, color=gdf["_cor"], edgecolor=p.contorno, linewidth=0.4)
        if contornos:
            gpd.GeoDataFrame.from_features(contornos["features"], crs="EPSG:4326").boundary.plot(
                ax=ax, color=p.texto, linewidth=0.5, alpha=0.6)
    ax.set_axis_off()
    ax.set_aspect("equal")

    fig.text(0.02, 0.955, p.titulo, fontsize=16, fontweight="bold", color=p.texto, va="top")
    if p.subtitulo:
        fig.text(0.02, 0.912, p.subtitulo, fontsize=11, color=p.texto, alpha=0.75, va="top")
    alcas = [Patch(facecolor=c, edgecolor=p.texto, linewidth=0.3, label=t) for c, t in p.legenda]
    if alcas:
        leg = fig.legend(handles=alcas, loc="upper left", bbox_to_anchor=(0.70, 0.86), frameon=False,
                         fontsize=10, labelcolor=p.texto, handlelength=1.2, handleheight=1.0)
        for t in leg.get_texts():  # rótulos longos não podem sair da figura
            if len(t.get_text()) > 46:
                t.set_text(t.get_text()[:45] + "…")
    rodape = [p.fonte] if p.fonte else []
    rodape += p.extras + [f"Gerado em {datetime.now():%d/%m/%Y %H:%M}"]
    fig.text(0.02, 0.025, " · ".join(rodape), fontsize=8, color=p.texto, alpha=0.7)

    buf = io.BytesIO()
    opcoes = {"format": p.formato, "facecolor": p.fundo}
    if p.formato != "svg":
        opcoes["dpi"] = p.dpi
    if p.formato == "jpeg":
        opcoes["pil_kwargs"] = {"quality": 92}
    fig.savefig(buf, **opcoes)
    plt.close(fig)
    return buf.getvalue()
