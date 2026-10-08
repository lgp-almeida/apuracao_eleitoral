/* Respostas de /api/painel, /api/cadeiras, /api/projecao, /api/presidente/ufs e /api/mudancas (apuracao/web/app.py),
 * campos usados pela página. */

export interface Totais {
  ELEITORADO?: number; COMPARECIMENTO?: number; ABSTENCAO?: number; VALIDOS?: number; BRANCOS?: number; NULOS?: number;
  ANULADOS_SUB_JUDICE?: number; PCT_SECOES_TOTALIZADAS?: number | null; SECOES_TOTALIZADAS?: number; SECOES_TOTAL?: number;
  DT_TOTALIZACAO?: string | null; TOTALIZACAO_FINAL?: boolean; VAGAS?: number;
}

export interface CandidatoPainel {
  NUMERO: number; NOME_URNA: string; PARTIDO: string; VOTOS: number; PCT_VALIDOS: number | null;
  ELEITO?: boolean; SITUACAO?: string | null; DESTINACAO?: string | null;
}

export interface PartidoPainel {
  PARTIDO: string; FEDERACAO?: string | null; VOTOS_TOTAL: number; PCT_VALIDOS: number | null; VAGAS_AGREMIACAO?: number | null;
}

export interface SeriePainel {
  pontos: { dt: string; pct_secoes: number | null }[];
  series: { NOME: string; CHAVE: string; PARTIDO?: string; valores: (number | null)[] }[];
}

export interface Projecao {
  cargo: number;
  pct_apurado: number;
  margem_pp: number | null;
  municipios_sem_apuracao: number;
  situacao: string;
  candidatos: { NUMERO: number; NOME_URNA: string; PCT_ATUAL: number | null; PCT_PROJ: number | null; MIN: number | null; MAX: number | null }[];
}

/** Agremiação (partido ou federação) e os partidos dela. */
export interface Composicao { AGREMIACAO: string; PARTIDOS: string[] }

export interface Cadeiras {
  cargo: number;
  vagas: number;
  composicao?: Composicao[];
  consistente: boolean;
  soma_agremiacoes: number;
  validos: number;
  final?: boolean;
  pct_secoes?: number | null;
  qe: number;
  eleitos_qp: number;
  eleitos_media: number;
  fonte: string;
  vagas_nao_preenchidas?: number;
  conferencia_tse?: { coincidentes: number; eleitos_tse: number } | null;
  agremiacoes: { NOME: string; AGREMIACAO: string; VOTOS: number; PCT_QE: number; VAGAS: number; VAGAS_QP: number; VAGAS_MEDIA: number }[];
  projecao?: {
    ativa: boolean; pct_apurado: number; pct_minimo: number; qe: number; simulacoes: number; limiar: number;
    consolidados: number; em_disputa_dentro: number; em_disputa_fora: number;
    agremiacoes: { AGREMIACAO: string; VOTOS: number; VAGAS: number; VAGAS_MIN: number; VAGAS_MAX: number }[];
  } | null;
}

export interface Cartao {
  cargo: number;
  ds_cargo: string;
  abrangencia: string;
  proporcional: boolean;
  totais: Totais;
  candidatos: CandidatoPainel[];
  n_candidatos: number;
  partidos?: PartidoPainel[];
  serie?: SeriePainel | null;
  projecao?: Projecao | null;
  cadeiras?: Cadeiras | null;
}

export interface Painel { cartoes: Cartao[] }

/** Candidato das listas de eleitos (/api/cadeiras). */
export interface Eleito {
  NUMERO: number; NOME: string; PARTIDO: string; AGREMIACAO: string; VOTOS: number; MARGEM: number | null;
  SITUACAO_PROJETADA?: string; VOTOS_PROJ?: number; STATUS?: string; FREQ_ELEITO?: number;
}

export type UfPresidente = {
  uf: string; nome: string; cd_ibge?: string | number | null; pct_secoes: number | null; hora?: string | null; final?: boolean;
  primeiro?: { numero: number; nome: string; pct: number | null } | null;
  segundo?: { numero: number; nome: string; pct: number | null } | null;
  diferenca_pp: number | null;
  pct: Record<string, number | null>;
  candidatos: { numero: number; nome: string; pct: number | null; votos: number }[];
  pct_brancos: number | null; brancos: number; pct_nulos: number | null; nulos: number;
  pct_abstencao: number | null; abstencao: number;
};

export interface PresidenteUfs { ufs: UfPresidente[]; candidatos: { NUMERO: number; NOME_URNA: string; PARTIDO: string }[] }

export interface Mudancas {
  anterior: { titulo: string; gerado_em: string } | null;
  mudancas: { cargo: string; texto: string }[];
}
