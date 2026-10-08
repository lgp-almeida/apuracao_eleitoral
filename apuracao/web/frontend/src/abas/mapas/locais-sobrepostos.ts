/* "Locais de votação" sobre o mapa: um ponto por local do cadastro do ano do site, com popup. */
import * as L from "leaflet";
import type { MapaApuracao } from "../../componentes/mapa/tipos";
import { api } from "../../core/api";
import { cor, el } from "../../core/dom";
import { int } from "../../core/formatos";

interface PropriedadesLocal {
  nome: string; bairro?: string | null; municipio: string; zona: number; local: number; eleitores: number; secoes: number;
}

export function criarLocaisSobrepostos(ano: () => number) {
  let camada: L.GeoJSON | null = null;
  return {
    async mostrar(mapa: MapaApuracao, ligado: boolean): Promise<void> {
      if (!ligado) { if (camada) mapa.removeLayer(camada); return; }
      if (!camada) {
        const geo = await api<GeoJSON.FeatureCollection>(`geo/locais.geojson?ano=${ano()}`);
        const renderer = L.canvas({ padding: 0.5 });
        camada = L.geoJSON(geo, {
          pointToLayer: (ft, ll) => L.circleMarker(ll, {
            renderer, radius: Math.max(2, Math.sqrt((ft.properties as PropriedadesLocal).eleitores || 0) / 12),
            color: cor("--texto"), weight: 0.5, fillColor: cor("--serie-2"), fillOpacity: 0.7,
          }),
          onEachFeature: (ft, layer) => layer.bindPopup(() => {
            const p = ft.properties as PropriedadesLocal;
            return el("div", {}, el("strong", {}, p.nome), el("br"), `${p.bairro || ""} — ${p.municipio}`, el("br"),
              `Zona ${p.zona}, local ${p.local} · ${int(p.eleitores)} eleitores em ${p.secoes} seções (${ano()})`);
          }),
        });
      }
      camada.addTo(mapa);
    },
  };
}
