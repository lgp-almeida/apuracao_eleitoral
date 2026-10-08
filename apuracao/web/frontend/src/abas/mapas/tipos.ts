/* Respostas de /api/mapa*, /api/bairros/anos (apuracao/web/app.py, bairros.py, mapa_locais.py, areas_ponderacao.py). */
import type { DadosPoligonos, DadosPontos } from "../../componentes/mapa/camadas";

export interface InfoBairros { anos: Record<string, number[]>; cargos: Record<string, string> }

/** Reta voto × indicador das camadas de resíduo. */
export interface EstatisticaCamada { pearson: number | null; r2: number; n: number }

export interface MapaBairros extends DadosPoligonos {
  cobertura: { bairros: number; bairros_com_dado: number; locais_em_bairro: number };
}

export interface MapaLocais extends DadosPontos {
  cobertura: { locais: number; com_valor: number };
  estatistica?: EstatisticaCamada | null;
  min_validos?: number;
  ano: number;
  ano_ref?: number;
}

export interface MapaAreas extends DadosPoligonos {
  camada: string;
  unidade?: string;
  fonte_indicador?: string | null;
  cobertura: { areas: number; areas_com_dado: number; areas_cv_fragil?: number | null; areas_cv_cautela?: number | null };
  estatistica?: EstatisticaCamada | null;
  min_validos?: number;
  ano?: number;
  ano_ref?: number;
}
