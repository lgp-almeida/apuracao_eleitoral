/* Formatação de números e datas para a página (pt-BR). Ausente (null/undefined) vira "—". */

export type Talvez = number | null | undefined;
export const VAZIO = "—";

export const fmtInt = new Intl.NumberFormat("pt-BR");
export const fmtPct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const ausente = (v: unknown): v is null | undefined => v === null || v === undefined;
/** Casas decimais fixas com vírgula (sem separador de milhar), ex.: decimal(1.5, 2) = "1,50". */
export const decimal = (v: number, casas: number): string => v.toFixed(casas).replace(".", ",");

/** Inteiro com separador de milhar. */
export const int = (v: Talvez): string => (ausente(v) ? VAZIO : fmtInt.format(v));
/** Percentual com 2 casas. */
export const pct = (v: Talvez): string => (ausente(v) ? VAZIO : fmtPct.format(v) + "%");
/** Percentual com 1 casa. */
export const p1 = (v: Talvez): string => (ausente(v) ? VAZIO : `${decimal(v, 1)}%`);
/** Número com casas fixas. */
export const fmtNum = (v: Talvez, casas = 2): string => (ausente(v) ? VAZIO : decimal(v, casas));
/** Data e hora curtas, no fuso do navegador. */
export const hora = (iso: string | null | undefined): string =>
  (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" }) : VAZIO);
/** Variação em pontos percentuais, sempre com sinal (− tipográfico). */
export const fmtPP = (x: number): string => `${x >= 0 ? "+" : "−"}${decimal(Math.abs(x), 1)} p.p.`;
/** Frequência (0–1) como % inteiro. */
export const fmtFreq = (f: number): string => `${Math.round(100 * f)}%`;
/** Coeficiente de correlação com sinal e 2 casas. */
export const fmtR = (r: Talvez): string => (ausente(r) ? VAZIO : (r >= 0 ? "+" : "−") + decimal(Math.abs(r), 2));
/** Valor-p com 3 casas; abaixo de 0,001 vira "< 0,001". */
export const fmtP = (p: Talvez): string => (ausente(p) ? VAZIO : p < 0.001 ? "< 0,001" : decimal(p, 3));
/** Contagem arredondada; de 10 mil em diante, em milhares ("12 mil"). */
export const mil = (n: number): string =>
  (n >= 10_000 ? `${fmtInt.format(Math.round(n / 1000))} mil` : fmtInt.format(Math.round(n)));
