/* Respostas de /api/comparacao*, /api/bancadas (apuracao/comparacao.py, bancadas.py), campos usados pela página. */
import type { DadosDivergente } from "../../componentes/mapa/camadas";
import type { DadosVariacao, SerieVariacao } from "../../componentes/grafico/variacao";

export interface InfoComparacao {
  disponivel: boolean;
  ano_a: number;
  ano_b: number;
  cargos: number[];
}

export interface InfoBairros {
  /** Cargos com votos por ano (microdados). */
  anos_votos: Record<string, number[]>;
  anos_cadastro: number[];
  cargos: Record<string, string>;
}

/** Partido ligado entre dois anos pela entidade (apuracao/partidos.py). */
export interface PartidoEntidade {
  PARTIDO: string | number;
  NOS_DOIS: boolean;
  VOTOS_A?: number | null;
  SIGLA_A?: string | null;
  SIGLA_B?: string | null;
  SIGLAS_A?: string | null;
  SIGLAS_B?: string | null;
}

export type LinhaComparacao = { NM_MUNICIPIO: string; VALOR_A: number | null; VALOR_B: number | null; DIF: number | null };

export interface ResultadoComparacao extends DadosDivergente {
  municipios: LinhaComparacao[];
  uf?: { VALOR_A?: number | null; VALOR_B?: number | null; DIF?: number | null } | null;
}

export interface Bancadas {
  ano: number;
  ano_ref: number;
  ds_cargo: string;
  resumo: Record<string, number>;
  partidos: Record<string, string | number | null>[];
  eleitos: Record<string, string | number | null>[];
  sairam: Record<string, string | number | null>[];
}

export interface PartidoVariacao extends Omit<SerieVariacao, "cor" | "pontos" | "reta"> {
  pontos: (SerieVariacao["pontos"][number] & { CD_MUNICIPIO: number })[];
  reta: SerieVariacao["reta"] & { ic_b?: [number, number] | null; p_b1: number | null; pearson: number | null };
  uf?: { A: number; B: number; DIF: number } | null;
  dp: number | null;
  leitura: string;
}

export interface Variacao extends Omit<DadosVariacao, "butler"> {
  partidos: PartidoVariacao[];
  butler?: (Omit<NonNullable<DadosVariacao["butler"]>, "pontos"> & { uf: number;
    pontos: { VALOR: number; NM_MUNICIPIO: string; CD_MUNICIPIO: number }[] }) | null;
}
