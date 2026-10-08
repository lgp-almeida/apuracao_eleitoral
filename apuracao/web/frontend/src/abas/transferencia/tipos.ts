/* Respostas de /api/transferencia* (apuracao/web/app.py → apuracao/transferencia.py), campos usados pela página. */

export interface InfoTransferencia {
  anos: number[];
  /** Há 1º e 2º turno coletados nesta noite (fonte "tempo_real"). */
  tempo_real: boolean;
  /** Cargos com 2º turno por ano dos microdados. */
  cargos: Record<string, number[]>;
  cargos_tempo_real: number[];
}

export interface MunicipioTransferencia { CD_MUNICIPIO: number; NM_MUNICIPIO: string }

export interface Destino { destino: string; pct: number; baixo: number; alto: number; eleitores: number }
export interface LinhaMatriz { origem: string; pct_1t: number; eleitores_1t: number; destinos: Destino[] }

export type LinhaTabela = Record<string, string | number | null>;

export interface ResultadoTransferencia {
  descricao: string;
  nivel: "secao" | "local" | "municipio";
  unidades: number;
  n_estratos: number;
  estrato: "zona" | "municipio";
  categorias_1t: string[];
  categorias_2t: string[];
  celulas_no_limite: number;
  matriz: LinhaMatriz[];
  abstencao: {
    pct_1t: number;
    pct_2t: number;
    extra_pp: number;
    novos_abstencionistas: { origem: string; eleitores: number }[];
  };
  validacao: { rmse_modelo_medio_pp: number; rmse_swing_medio_pp: number } | null;
  estratos: LinhaTabela[];
  maior_abstencao_extra: LinhaTabela[];
  residuos_a: { acima: LinhaTabela[]; abaixo: LinhaTabela[] };
}
