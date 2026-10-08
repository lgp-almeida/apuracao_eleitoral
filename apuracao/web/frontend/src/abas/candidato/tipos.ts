/* Respostas de /api/candidato* (apuracao/web/app.py, comparacao.historico_candidato), campos usados pela página. */

export interface Candidato {
  NUMERO: number;
  NOME_URNA: string;
  PARTIDO: string;
  FEDERACAO?: string | null;
  VOTOS: number;
  PCT_VALIDOS: number | null;
  SITUACAO?: string | null;
  DESTINACAO?: string | null;
  VICES?: string | null;
}

export type MunicipioCandidato = {
  CD_MUNICIPIO: number;
  CD_MUNICIPIO_IBGE: number | string;
  NM_MUNICIPIO: string;
  VOTOS: number;
  PCT_VALIDOS: number | null;
  POSICAO_MUN: number;
  PCT_SECOES_TOTALIZADAS: number | null;
};

/** Cadeira de deputado: projeção (simulações) ou a situação na totalização atual. */
export interface Cadeira {
  projecao?: { status: string; freq: number; votos_proj: number; pct_apurado: number } | null;
  situacao: string;
  margem: number | null;
  agremiacao: string;
  ordem?: number;
}

export interface ConsultaCandidato {
  candidato: Candidato;
  posicao_uf: number;
  n_candidatos_uf: number;
  brasil?: { VOTOS: number; PCT_VALIDOS: number | null } | null;
  cadeira?: Cadeira | null;
  municipios: MunicipioCandidato[];
}

export interface PontoSerie { dt: string; pct: number | null; votos: number; pct_secoes: number | null }
export interface SerieCandidato { abrangencia: "mun" | "uf" | "br"; municipio?: number; pontos: PontoSerie[] }

export interface CandidatoHistorico {
  NUMERO: number;
  NOME_URNA: string;
  PARTIDO: string;
  FEDERACAO?: string | null;
  DS_CARGO?: string | null;
  CARGO: number | string;
  VOTOS: number;
  PCT_VALIDOS: number | null;
  SITUACAO?: string | null;
}

export type LinhaHistorico = Record<string, string | number | null>;

export interface Historico {
  ano: number;
  ano_ref?: number | null;
  sufixos: [string, string];
  criterio: string;
  atual: CandidatoHistorico;
  anterior: CandidatoHistorico | null;
  notas: string[];
  opcoes: CandidatoHistorico[];
  linhas: LinhaHistorico[];
}
