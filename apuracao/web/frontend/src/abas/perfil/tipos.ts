/* Respostas de /api/perfil/* (apuracao/perfil.py, perfil_local.py, areas_ponderacao.py), campos usados pela página. */
import type { DadosDispersao, PontoDispersao } from "../../componentes/grafico/dispersao";

export type Unidade = "bairro" | "local" | "area";

export interface InfoPerfil {
  unidade: Unidade;
  indicadores: Record<string, { rotulo: string; fonte: string }>;
  municipios: { CD_MUN: number; NM_MUN: string; BAIRROS: number }[];
  /** Cargos com votos por ano. */
  anos: Record<string, number[]>;
  cargos: Record<string, string>;
}

export interface CandidatoPerfil { NUMERO: number; NOME: string }
export interface PartidoPerfil { PARTIDO: number; SIGLA?: string | null; VOTOS: number }

export interface Estatistica {
  n: number;
  n_efetivo?: number | null;
  pearson: number | null;
  ic95: [number, number] | null;
  spearman: number | null;
  p: number | null;
  r2: number | null;
  a: number;
  b: number | null;
}

export interface Dispersao extends DadosDispersao {
  estatistica: Estatistica;
  ponderado?: boolean;
  acima: PontoDispersao[];
  abaixo: PontoDispersao[];
}

export interface Correlacao {
  indicador: string;
  rotulo: string;
  pearson: number | null;
  spearman: number | null;
  ic95: [number, number] | null;
  n: number;
  fonte: string;
}

export interface Coeficiente {
  indicador: string;
  rotulo: string;
  efeito_pp_por_dp: number;
  ic95: [number, number];
  p: number | null;
  vif: number;
  r_simples: number | null;
  dp_indicador: number | null;
}

export interface Regressao { n: number; r2: number; r2_ajustado: number; coeficientes: Coeficiente[] }
