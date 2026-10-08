/* Regras dos controles da aba Mapas (sem DOM): que campos aparecem e que métricas valem em cada detalhe e camada. */

export type Detalhe = "municipios" | "bairros" | "locais" | "areas";
export type Camada = "voto" | "perfil" | "residuo" | "variacao" | "transferencia";

export const ehDetalhe = (x: unknown): x is Detalhe =>
  x === "municipios" || x === "bairros" || x === "locais" || x === "areas";

/** Métricas com microdados (bairro, local, área): as do tempo real que não existem lá ficam desabilitadas. */
export const METRICAS_BAIRRO: readonly string[] = ["vencedor", "pct_candidato", "votos_candidato", "brancos_nulos_pct",
  "brancos_pct", "nulos_pct", "abstencao_pct", "comparecimento_pct"];
/** Métricas da camada "variação desde a eleição anterior". */
export const METRICAS_VARIACAO: readonly string[] = ["pct_candidato", "abstencao_pct", "comparecimento_pct",
  "brancos_nulos_pct", "brancos_pct", "nulos_pct"];
/** Camadas por área de ponderação (todas as do mapa por local). */
export const CAMADAS_AREA: readonly Camada[] = ["voto", "perfil", "residuo", "variacao", "transferencia"];

const porCandidato = (metrica: string) => metrica.endsWith("_candidato");

/** Métricas permitidas no detalhe/camada (null = todas). */
export function metricasPermitidas(detalhe: Detalhe, camada: Camada): readonly string[] | null {
  if (detalhe === "locais" || detalhe === "areas") return camada === "variacao" ? METRICAS_VARIACAO : METRICAS_BAIRRO;
  return detalhe === "bairros" ? METRICAS_BAIRRO : null;
}

/** Métrica a usar quando a escolhida não vale mais. */
export const metricaPadrao = (camada: Camada): string => (camada === "variacao" ? "pct_candidato" : "vencedor");

export interface Controles {
  camada: boolean;
  municipio: boolean;
  indicador: boolean;
  transf: boolean;
  metrica: boolean;
  /** O campo do nº do candidato aceita digitação. */
  numero: boolean;
  placeholder: string;
}

/** Que controles aparecem (e se o nº vale) para detalhe, camada e métrica. */
export function controles(detalhe: Detalhe, camada: Camada, metrica: string): Controles {
  const pontual = detalhe === "locais" || detalhe === "areas";  // os dois usam camada/indicador/município
  const comMetrica = camada === "voto" || camada === "variacao";
  return {
    camada: pontual,
    municipio: pontual,
    indicador: pontual && !comMetrica && camada !== "transferencia",
    transf: pontual && camada === "transferencia",
    metrica: !pontual || comMetrica,
    numero: pontual ? camada === "residuo" || (comMetrica && porCandidato(metrica)) : porCandidato(metrica),
    placeholder: !pontual ? "número" : camada === "residuo" ? "número (2 dígitos = partido)"
      : camada === "variacao" ? "número (vale o partido)" : "número",
  };
}

/**
 * Parâmetros da camada (mapa por local e por área) ou o aviso do que falta.
 * @param numero texto do campo do nº
 */
export function consultaCamada(p: { ano: string; camada: Camada; cargo: string; turno: number; metrica: string;
    numero: string; indicador: string; transf: string; municipio: string }): URLSearchParams | { falta: string } {
  const q = new URLSearchParams({ ano: p.ano, camada: p.camada, cargo: p.cargo, turno: String(p.turno) });
  const num = p.numero.trim();
  if (p.camada === "voto" || p.camada === "variacao") {
    q.set("metrica", p.metrica);
    if (porCandidato(p.metrica)) {
      if (!/^\d+$/.test(num)) {
        return { falta: p.camada === "variacao" ? "Informe o número de um candidato ou partido (vale o partido)."
          : "Informe o número de um candidato." };
      }
      q.set("numero", num);
    }
  } else if (p.camada === "transferencia") {
    q.set("metrica", p.transf);
    q.set("turno", "2");
  } else {
    q.set("indicador", p.indicador);
    if (p.camada === "residuo") {
      if (!/^\d+$/.test(num)) return { falta: "Informe o número do candidato (ou 2 dígitos para o partido)." };
      q.set("numero", num);
    }
  }
  if (p.municipio) q.set("municipio", p.municipio);
  return q;
}
