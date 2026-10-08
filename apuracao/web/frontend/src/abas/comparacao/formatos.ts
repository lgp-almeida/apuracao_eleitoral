/* Vocabulário da comparação entre eleições. */
import type { PartidoEntidade } from "./tipos";

/**
 * Rótulo de um partido ligado entre dois anos pela entidade (rodada 41): "PRD (PTB + PATRIOTA em 2022)",
 * "PCDOB (PC do B em 2022)", "MISSÃO (só 2026)".
 */
export function rotuloEntidade(p: PartidoEntidade, a: number | string, b: number | string): string {
  const siglaA = p.SIGLAS_A ?? p.SIGLA_A;
  if (!p.NOS_DOIS) return `${p.PARTIDO}${p.VOTOS_A ? ` (só ${a})` : ` (só ${b})`}`;
  return siglaA && siglaA !== p.PARTIDO ? `${p.PARTIDO} (${siglaA} em ${a})` : String(p.PARTIDO);
}

/** Rótulo do partido na comparação por bairro: nº do ano mais recente, sigla de cada ano quando mudou. */
export function rotuloPartidoBairros(p: PartidoEntidade, a: number | string, b: number | string): string {
  const sigla = p.SIGLA_A && p.SIGLA_B && p.SIGLA_A !== p.SIGLA_B ? `${p.SIGLA_B} (${p.SIGLA_A} em ${a})`
    : (p.SIGLA_A || p.SIGLA_B || "");
  return `${p.PARTIDO} ${sigla}${p.NOS_DOIS ? "" : p.VOTOS_A ? ` (só ${a})` : ` (só ${b})`}`;
}

/** Métricas que a comparação por bairro calcula (as demais ficam desabilitadas). */
export const METRICAS_BAIRRO: readonly string[] = ["abstencao", "comparecimento", "brancos_nulos", "brancos", "nulos",
  "eleitorado", "partido", "candidato"];

/** Anos para os seletores da comparação por bairro: com votos, com cadastro e o da eleição atual. */
export function anosBairros(anosVotos: readonly (string | number)[], anosCadastro: readonly number[], anoAtual: number): number[] {
  return [...new Set([...anosVotos.map(Number), ...anosCadastro, anoAtual])].sort((x, y) => x - y);
}

/** Até 3 partidos na variação; padrão por cargo quando o endereço não diz. */
export const MAX_VAR = 3;
export const PADRAO_VAR: Readonly<Record<string, readonly string[]>> = { 1: ["PT", "PL"] };

/** Escolha inicial dos partidos da variação: pedida > a anterior do mesmo cargo > padrão do cargo > 2 primeiros nos dois anos. */
export function escolhaInicial(ps: readonly PartidoEntidade[], cargo: string, pedidos: readonly string[] | null,
    anterior: readonly string[] | null): string[] {
  const nosDois = (p: string) => ps.some((x) => String(x.PARTIDO) === p && x.NOS_DOIS);
  return [...(pedidos ?? anterior ?? PADRAO_VAR[cargo]?.filter(nosDois)
    ?? ps.filter((x) => x.NOS_DOIS).slice(0, 2).map((x) => String(x.PARTIDO)))];
}
