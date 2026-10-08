/* Escalas de cor dos mapas e marcas dos eixos. As cores são TOKENS do CSS (--mapa-1…, --div-…, --serie-…),
 * resolvidos por `resolver` (padrão: o valor atual na página) — nos testes, a identidade. */
import { cor } from "../core/dom";
import { decimal } from "../core/formatos";

export type Resolver = (token: string) => string;
/** Item de legenda: [cor, texto]. */
export type ItemLegenda = [string, string];

/** Intensidade: amarelo (menos) → vermelho (mais), mesma ordem nos dois temas (pedido do usuário, rodada 31). */
export const TOKENS_SEQ = ["--mapa-1", "--mapa-2", "--mapa-3", "--mapa-4", "--mapa-5"] as const;
/** Divergente: vermelho (redução) ↔ cinza ↔ azul (aumento). */
export const TOKENS_DIV = ["--div-n3", "--div-n2", "--div-n1", "--div-0", "--div-p1", "--div-p2", "--div-p3"] as const;
/** Categórico: no mapa todos os pares de cor se tocam — no máximo 3 cores + "Outros" (skill dataviz). */
export const TOKENS_CAT = ["--serie-1", "--serie-2", "--serie-3"] as const;

/** Quebras pelos quantis (n faixas → até n−1 quebras, sem repetição); ausentes são ignorados. */
export function quebrasQuantis(valores: readonly (number | null | undefined)[], n = 5): number[] {
  const v = valores.filter((x): x is number => x !== null && x !== undefined).sort((a, b) => a - b);
  if (!v.length) return [];
  const q: number[] = [];
  for (let i = 1; i < n; i++) q.push(v[Math.min(v.length - 1, Math.floor((i * v.length) / n))]);
  return [...new Set(q)];
}

/** Faixa de um valor (0…n−1) dadas as quebras: valor igual à quebra fica na faixa de baixo. */
export function faixa(valor: number, quebras: readonly number[], nFaixas: number = TOKENS_SEQ.length): number {
  let k = 0;
  while (k < quebras.length && valor > quebras[k]) k++;
  return Math.min(k, nFaixas - 1);
}

/** Escala sequencial (5 faixas) com legenda "a – b" entre mínimo, quebras e máximo. */
export function escalaSequencial(quebras: readonly number[], minimo: number, maximo: number,
    fmt: (x: number) => string, resolver: Resolver = cor) {
  const seq = TOKENS_SEQ.map(resolver);
  const lim = [minimo, ...quebras, maximo];
  return {
    corValor: (v: number) => seq[faixa(v, quebras, seq.length)],
    itensLegenda: lim.slice(0, -1).map((a, i): ItemLegenda => [seq[i], `${fmt(a)} – ${fmt(lim[i + 1])}`]),
  };
}

/** Índice (0…6) na escala divergente: |v| contra 3 limites; negativo à esquerda do centro (3). */
export function classeDivergente(v: number, lim: readonly [number, number, number]): number {
  const a = Math.abs(v);
  const k = a < lim[0] ? 0 : a < lim[1] ? 1 : a < lim[2] ? 2 : 3;
  return v < 0 ? 3 - k : 3 + k;
}

/** Limites divergentes pelos quantis 33/66/90% de |valor| (com milhares de unidades, o máximo seria um extremo). */
export function limitesPorQuantis(vals: readonly number[]): [number, number, number] {
  const abs = vals.map(Math.abs).sort((a, b) => a - b);
  const q = (f: number) => abs[Math.min(abs.length - 1, Math.floor(f * abs.length))] || 1e-9;
  return [q(0.33), q(0.66), q(0.9)];
}

/** Limites divergentes por fração do maior |valor| (comparação por município: < 10% do máximo = "sem variação"). */
export function limitesPorMaximo(vals: readonly number[]): [number, number, number] {
  const m = Math.max(...vals.map(Math.abs), 1e-9);
  return [m * 0.1, m / 3, (2 * m) / 3];
}

/**
 * Escala DIVERGENTE em p.p. (resíduo do Perfil × voto, variação desde a eleição anterior), comum aos pontos
 * (locais) e aos polígonos (áreas). `sentido` = "variacao" (subiu/caiu) ou outro (resíduo: maior/menor que o esperado).
 */
export function escalaDivergente(vals: readonly number[], sentido: string | undefined, resolver: Resolver = cor) {
  const lim = limitesPorQuantis(vals);
  const cores = TOKENS_DIV.map(resolver);
  const m = (x: number) => decimal(Math.abs(x), 1);
  const variacao = sentido === "variacao";
  const itensLegenda: ItemLegenda[] = [
    [cores[6], `${variacao ? "subiu" : "voto maior que o esperado:"} mais de ${m(lim[2])} p.p.`],
    [cores[5], `+${m(lim[1])} a +${m(lim[2])} p.p.`],
    [cores[4], `+${m(lim[0])} a +${m(lim[1])} p.p.`],
    [cores[3], `${variacao ? "estável" : "como esperado"} (±${m(lim[0])} p.p.)`],
    [cores[2], `−${m(lim[0])} a −${m(lim[1])} p.p.`],
    [cores[1], `−${m(lim[1])} a −${m(lim[2])} p.p.`],
    [cores[0], `${variacao ? "caiu" : "voto menor que o esperado:"} mais de ${m(lim[2])} p.p.`],
  ];
  return { corValor: (v: number) => cores[classeDivergente(v, lim)], itensLegenda };
}

/** Escala categórica: as 3 primeiras categorias com cor própria, o resto "Outros". */
export function escalaCategorica<C extends { NUMERO: number | string }>(categorias: readonly C[],
    rotulo: (c: C) => string, resolver: Resolver = cor) {
  const top = categorias.slice(0, TOKENS_CAT.length);
  const cores = TOKENS_CAT.map(resolver);
  const outros = resolver("--outros");
  const idx = new Map<unknown, number>(top.map((c, i) => [c.NUMERO, i]));
  return {
    corValor: (v: unknown) => { const i = idx.get(v); return i === undefined ? outros : cores[i]; },
    itensLegenda: [...top.map((c, i): ItemLegenda => [cores[i], rotulo(c)]), [outros, "Outros"] as ItemLegenda],
  };
}

/** Marcas "redondas" de eixo entre min e max (passos de 1, 2, 2,5, 5 × 10^k). */
export function passos(min: number, max: number, n = 5): number[] {
  const bruto = (max - min) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((p) => bruto <= p) ?? 10 * mag;
  const ts: number[] = [];
  for (let t = Math.ceil(min / passo) * passo; t <= max + passo * 1e-9; t += passo) ts.push(Number(t.toPrecision(12)));
  return ts;
}
