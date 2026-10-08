/* Tipos comuns dos mapas. As propriedades com "_" ficam no próprio mapa do Leaflet porque os testes e2e e a
 * exportação as leem (__apuracao.estado.mapa._camada / ._export). */
import type * as L from "leaflet";
import type { ItemLegenda } from "../escalas";

/** O que a exportação no servidor precisa para redesenhar o mapa com as cores da página. */
export interface ExportacaoMapa {
  camada: string;
  cores: Record<string, string>;
  legenda: ItemLegenda[];
  titulo: string;
  extras?: string[];
  subtitulo?: string | null;
  ano?: number | null;
}

export type MapaApuracao = L.Map & {
  _camada?: L.GeoJSON | L.LayerGroup | null;
  _contornos?: L.Layer | null;
  /** Já enquadrado uma vez: a atualização automática não desfaz o zoom do usuário. */
  _enquadrado?: boolean;
  _export?: ExportacaoMapa | null;
};

export type Geo = GeoJSON.FeatureCollection;

/** Malhas do site (com cache de quem as fornece). */
export interface Malhas {
  municipios(): Promise<Geo>;
  bairros(): Promise<Geo>;
  areas(): Promise<Geo>;
}

/** Categoria do mapa "quem lidera". */
export interface Categoria { NUMERO: number | string; NOME_URNA: string; PARTIDO?: string }
