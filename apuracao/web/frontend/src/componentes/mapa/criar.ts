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

export function criarMapa(div: HTMLElement, opcoes: OpcoesMapa = {}): MapaApuracao {
  const { centro = [-22.25, -42.6], zoom = 8, ladrilhos = true, zoomSnap } = opcoes;
  const m = L.map(div, { preferCanvas: true, ...(zoomSnap ? { zoomSnap } : {}) }).setView(centro, zoom) as MapaApuracao;
  if (ladrilhos) {
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: "© OpenStreetMap", opacity: 0.35,
    }).addTo(m);
  }
  // numa aba escondida o mapa nasce com tamanho 0; quando o contêiner muda de tamanho (aba aberta, bloco
  // movido, janela), o Leaflet recalcula — no lugar dos antigos setTimeout(invalidateSize, 50)
  if (typeof ResizeObserver !== "undefined") {
    const obs = new ResizeObserver(() => m.invalidateSize());
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

/** Enquadra só na 1ª vez (a atualização automática não pode desfazer o zoom do usuário). */
export function enquadrarUmaVez(mapa: MapaApuracao, limites: L.LatLngBounds): void {
  if (mapa._enquadrado || !limites.isValid()) return;
  mapa.fitBounds(limites, { padding: [10, 10] });
  mapa._enquadrado = true;
}
