/* Criação dos mapas Leaflet da página. */
import * as L from "leaflet";
import type { MapaApuracao } from "./tipos";

export interface OpcoesMapa {
  centro?: [number, number];
  zoom?: number;
  /** Fundo do OpenStreetMap, esmaecido (padrão: sim). */
  ladrilhos?: boolean;
  zoomSnap?: number;
}

/** Zoom máximo de todo mapa. Sem ele, um mapa sem ladrilhos não tem limite e o fitBounds num contêiner de
 * tamanho 0 dá zoom infinito: coordenadas NaN até recarregar a página (achado no ensaio da rodada 69). */
export const ZOOM_MAXIMO = 18;

/** O contêiner tem tamanho (não está numa aba, cartão ou bloco escondido nem fora do documento). */
const visivel = (mapa: MapaApuracao): boolean => {
  const c = mapa.getContainer();
  return c.isConnected && c.clientWidth > 0 && c.clientHeight > 0;
};

export function criarMapa(div: HTMLElement, opcoes: OpcoesMapa = {}): MapaApuracao {
  const { centro = [-22.25, -42.6], zoom = 8, ladrilhos = true, zoomSnap } = opcoes;
  // quem pediu menos movimento ao sistema (prefers-reduced-motion) não vê zoom nem esmaecimento animados
  const animar = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const m = L.map(div, {
    preferCanvas: true, zoomAnimation: animar, fadeAnimation: animar, markerZoomAnimation: animar, maxZoom: ZOOM_MAXIMO,
    ...(zoomSnap ? { zoomSnap } : {}),
  }).setView(centro, zoom) as MapaApuracao;
  if (ladrilhos) {
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: ZOOM_MAXIMO, attribution: "© OpenStreetMap", opacity: 0.35,
    }).addTo(m);
  }
  // numa aba escondida o mapa nasce com tamanho 0; quando o contêiner muda de tamanho (aba aberta, bloco
  // movido, janela), o Leaflet recalcula — no lugar dos antigos setTimeout(invalidateSize, 50)
  if (typeof ResizeObserver !== "undefined") {
    const obs = new ResizeObserver(() => {
      m.invalidateSize();
      const p = m._enquadrarPendente;
      if (p && visivel(m)) { m._enquadrarPendente = null; m.fitBounds(p.limites, { padding: p.padding }); }
    });
    obs.observe(div);
    m.on("unload", () => obs.disconnect());
  }
  return m;
}

/** Remove a camada e os contornos desenhados antes. */
export function limparCamadas(mapa: MapaApuracao): void {
  if (mapa._camada) { mapa.removeLayer(mapa._camada); mapa._camada = null; }
  if (mapa._contornos) { mapa.removeLayer(mapa._contornos); mapa._contornos = null; }
}

/** Enquadra só na 1ª vez (a atualização automática não pode desfazer o zoom do usuário). Com o mapa escondido,
 * o enquadramento espera ele aparecer (o ResizeObserver de criarMapa o faz). */
export function enquadrarUmaVez(mapa: MapaApuracao, limites: L.LatLngBounds, padding: L.PointExpression = [10, 10]): void {
  if (mapa._enquadrado || !limites.isValid()) return;
  mapa._enquadrado = true;
  if (visivel(mapa)) mapa.fitBounds(limites, { padding });
  else mapa._enquadrarPendente = { limites, padding };
}
