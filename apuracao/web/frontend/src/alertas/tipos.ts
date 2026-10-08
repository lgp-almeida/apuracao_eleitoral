/* /api/alertas e /api/alertas/interesse (apuracao/alertas.py). */

export type Nivel = "critico" | "aviso" | "noticia" | "ok";

export interface Alerta {
  chave?: string;
  nivel: Nivel;
  titulo: string;
  detalhe?: string | null;
  /** Hora do evento (ISO) ou desde quando a condição vale. */
  momento?: string | null;
  desde?: string | null;
}

/** Deputado acompanhado (situação na projeção de cadeiras). */
export interface Interesse { cargo: number; numero: number; nome: string; situacao?: string | null }

export interface RespostaAlertas { ultimo_id: number; ativos: Alerta[]; alertas: Alerta[]; interesse: Interesse[] }
