/* Malhas do site (/geo/*.geojson), baixadas uma vez por página. Falha não fica no cache. */
import type { Geo, Malhas } from "../componentes/mapa/tipos";
import { api } from "../core/api";

export function criarMalhas(): Malhas {
  const cache: Record<string, Promise<Geo> | undefined> = {};
  const malha = (rota: string) => (): Promise<Geo> => {
    const p = (cache[rota] ??= api<Geo>(rota));
    p.catch(() => { if (cache[rota] === p) cache[rota] = undefined; });
    return p;
  };
  return { municipios: malha("geo/municipios.geojson"), bairros: malha("geo/bairros.geojson"), areas: malha("geo/areas.geojson") };
}
