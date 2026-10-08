/* Formatos e vocabulário do Perfil × voto. */
import { decimal, fmtInt, pct, VAZIO } from "../../core/formatos";
import type { Unidade } from "./tipos";

/** Indicadores do eixo X que não são %: o resto é percentual. */
const INDICADOR_FMT: Record<string, (v: number) => string> = {
  renda_media: (v) => `R$ ${fmtInt.format(Math.round(v))}`,
  renda_mediana: (v) => `R$ ${fmtInt.format(Math.round(v))}`,
  densidade: (v) => `${fmtInt.format(Math.round(v))}/km²`,
  moradores_domicilio: (v) => decimal(v, 2),
};

/** Valor de um indicador no seu formato (renda em R$, densidade por km², o resto em %). */
export const fmtX = (k: string | null | undefined, v: number | null | undefined): string =>
  (v === null || v === undefined ? VAZIO : ((k && INDICADOR_FMT[k]) || pct)(v));

/** Unidade de +1 no eixo X, para a inclinação. */
export const unidadeDoX = (xk: string | null): string =>
  (xk === "voto" || !xk || !INDICADOR_FMT[xk] ? "p.p." : xk.startsWith("renda") ? "R$" : "unidade");

/** Força da correlação pelo |r| (faixas usuais). */
export function forca(r: number | null | undefined): string {
  const a = Math.abs(r ?? 0);
  return a < 0.1 ? "desprezível" : a < 0.3 ? "fraca" : a < 0.5 ? "moderada" : a < 0.7 ? "forte" : "muito forte";
}

/** Indicadores da regressão quando o endereço não diz quais. */
export const REG_PADRAO: readonly string[] = ["pct_superior", "renda_media", "pct_pretos_pardos", "pct_60_mais"];

/** Unidade de análise: bairro (malha de bairros), local de votação ou área de ponderação (estas duas: estado inteiro). */
export const UNIDADES: Readonly<Record<Unidade, readonly [string, string]>> = {
  bairro: ["bairro", "bairros"], local: ["local", "locais"], area: ["área", "áreas"],
};

export const ehUnidade = (x: unknown): x is Unidade => typeof x === "string" && x in UNIDADES;

/** Nome da unidade, no singular ou plural, opcionalmente com maiúscula. */
export function nomeDaUnidade(u: Unidade, plural = true, maiuscula = false): string {
  const n = UNIDADES[u][plural ? 1 : 0];
  return maiuscula ? n.replace(/^./, (c) => c.toUpperCase()) : n;
}
