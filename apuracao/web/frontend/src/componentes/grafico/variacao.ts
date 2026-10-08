/* Variação por partido entre duas eleições (aba Comparação): dispersão A × B por município com a diagonal
 * "sem mudança" e a reta de cada partido; e o swing (variação em p.p., um ponto por município, média + IC). */
import { cor, el, svg } from "../../core/dom";
import { fmtInt, int, pct } from "../../core/formatos";
import { comDica, type AlvoDica } from "../dica";
import { type ItemLegenda, passos } from "../escalas";
import { botoesBaixar } from "../exportar";
import { amostra, legendaLinha } from "../legenda";

export interface PontoVariacao { A: number; B: number; DIF: number; VALIDOS: number; NM_MUNICIPIO: string; DESTAQUE?: boolean }
export interface SerieVariacao {
  partido: string;
  cor: string;
  pontos: readonly PontoVariacao[];
  reta: { a: number; b: number | null };
  media: number;
  ic_media: [number, number];
}
export interface DadosVariacao {
  ano_a: number | string;
  ano_b: number | string;
  ponderado?: boolean;
  butler?: { de: string; para: string; media: number; ic_media: [number, number];
    pontos: readonly { VALOR: number; NM_MUNICIPIO: string }[] } | null;
}
/** Formata uma variação em p.p. com sinal (fmtComp da comparação). */
export type FmtDif = (v: number) => string;

export function graficoVariacao(d: DadosVariacao, series: readonly SerieVariacao[], fmtDif: FmtDif): HTMLElement {
  const W = 640, H = 480, m = { l: 52, r: 40, t: 12, b: 46 };
  const todos = series.flatMap((p) => p.pontos.flatMap((r) => [r.A, r.B]));
  const passo = 5;
  const lo = Math.max(0, Math.floor(Math.min(...todos) / passo) * passo);
  const hi = Math.min(100, Math.ceil(Math.max(...todos) / passo) * passo);
  const X = (v: number) => m.l + ((W - m.l - m.r) * (v - lo)) / (hi - lo);
  const Y = (v: number) => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "dispersao", role: "img",
    "aria-label": `% dos válidos em ${d.ano_a} × ${d.ano_b} por município: ${series.map((p) => p.partido).join(", ")}` });
  for (const t of passos(lo, hi, 8)) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grade" }),
      svg("text", { x: m.l - 6, y: Y(t) + 3, class: "eixo", "text-anchor": "end" }, `${fmtInt.format(t)}%`),
      svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: "grade" }),
      svg("text", { x: X(t), y: H - m.b + 14, class: "eixo", "text-anchor": "middle" }, `${fmtInt.format(t)}%`));
  }
  g.append(svg("line", { x1: X(lo), y1: Y(lo), x2: X(hi), y2: Y(hi), class: "diagonal" }),
    svg("text", { x: (m.l + W - m.r) / 2, y: H - 8, class: "titulo-eixo", "text-anchor": "middle" }, `% dos válidos em ${d.ano_a}`),
    svg("text", { x: 12, y: (m.t + H - m.b) / 2, class: "titulo-eixo", "text-anchor": "middle",
      transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, `% dos válidos em ${d.ano_b}`));
  const vmax = Math.max(...series.flatMap((p) => p.pontos.map((r) => r.VALIDOS)));
  const raio = (v: number) => 4 + 14 * Math.sqrt(v / vmax);  // área ∝ válidos; mínimo de 8 px de diâmetro
  const pontos = series.flatMap((p) => p.pontos.map((r) => ({ p, r })))
    .sort((a, b) => b.r.VALIDOS - a.r.VALIDOS);  // grandes atrás, pequenos na frente
  const alvos: AlvoDica[] = pontos.map(({ p, r }) => {
    const c = svg("circle", { cx: X(r.A), cy: Y(r.B), r: raio(r.VALIDOS), class: "ponto", fill: p.cor });
    g.append(c);
    return { x: X(r.A), y: Y(r.B), el: c, texto: () => [el("strong", {}, r.NM_MUNICIPIO),
      el("div", {}, amostra(p.cor), p.partido),
      el("div", {}, `${d.ano_a}: ${pct(r.A)} · ${d.ano_b}: ${pct(r.B)}`),
      el("div", {}, `Variação: ${fmtDif(r.DIF)} · ${int(r.VALIDOS)} válidos em ${d.ano_b}`)] };
  });
  series.forEach((p) => {  // reta de cada partido no intervalo dos seus pontos + rótulo direto na ponta
    const e = p.reta;
    if (e.b === null) return;
    const b = e.b;
    const xs = p.pontos.map((r) => r.A);
    const x1 = Math.min(...xs), x2 = Math.max(...xs);
    g.append(svg("line", { x1: X(x1), y1: Y(e.a + b * x1), x2: X(x2), y2: Y(e.a + b * x2), class: "reta", stroke: p.cor }),
      svg("text", { x: Math.min(X(x2) + 4, W - m.r + 2), y: Y(e.a + b * x2) + 4, class: "rotulo" }, p.partido));
  });
  const itensLeg: ItemLegenda[] = [...series.map((p): ItemLegenda => [p.cor, `${p.partido} (reta: tendência${d.ponderado ? " ponderada" : ""})`]),
    [cor("--texto-2"), "Diagonal: sem mudança (acima = ganhou, abaixo = perdeu)"]];
  return el("div", {}, comDica(g, W, H, alvos), legendaLinha(itensLeg),
    el("p", { class: "nota" }, `Área do ponto ∝ votos válidos em ${d.ano_b}.`), botoesBaixar(g, itensLeg));
}

/** Deslocamento vertical determinístico (pela ordem) do k-ésimo ponto na faixa, para não se sobreporem todos. */
export const espalhar = (k: number): number => (((k * 7919) % 23) - 11) * 1.3;

export function graficoSwing(d: DadosVariacao, series: readonly SerieVariacao[], fmtDif: FmtDif): HTMLElement {
  interface Linha { nome: string; cor: string; media: number; ic: [number, number];
    pontos: { v: number; nome: string; destaque?: boolean; A?: number; B?: number }[] }
  const linhas: Linha[] = series.map((p) => ({ nome: p.partido, cor: p.cor, media: p.media, ic: p.ic_media,
    pontos: p.pontos.map((r) => ({ v: r.DIF, nome: r.NM_MUNICIPIO, destaque: r.DESTAQUE, A: r.A, B: r.B })) }));
  if (d.butler) {
    linhas.push({ nome: `Butler ${d.butler.de}→${d.butler.para}`, cor: cor("--texto-2"), media: d.butler.media,
      ic: d.butler.ic_media, pontos: d.butler.pontos.map((r) => ({ v: r.VALOR, nome: r.NM_MUNICIPIO })) });
  }
  const faixa = 70, W = 640, m = { l: 110, r: 16, t: 8, b: 40 };
  const H = m.t + m.b + faixa * linhas.length;
  const vs = linhas.flatMap((l) => l.pontos.map((p) => p.v));
  const lim = Math.max(1, ...vs.map(Math.abs)) * 1.05;
  const X = (v: number) => m.l + ((W - m.l - m.r) * (v + lim)) / (2 * lim);
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "dispersao", role: "img",
    "aria-label": `Variação por município em pontos percentuais: ${linhas.map((l) => l.nome).join(", ")}` });
  for (const t of passos(-lim, lim, 8)) {
    g.append(svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: t === 0 ? "zero" : "grade" }),
      svg("text", { x: X(t), y: H - m.b + 14, class: "eixo", "text-anchor": "middle" },
        `${t > 0 ? "+" : t < 0 ? "−" : ""}${fmtInt.format(Math.abs(t))}`));
  }
  g.append(svg("text", { x: (m.l + W - m.r) / 2, y: H - 8, class: "titulo-eixo", "text-anchor": "middle" },
    `Variação de ${d.ano_a} para ${d.ano_b} (p.p.)`));
  const alvos: AlvoDica[] = [];
  linhas.forEach((l, i) => {
    const y0 = m.t + faixa * i + faixa / 2;
    g.append(svg("text", { x: m.l - 8, y: y0 + 4, class: "rotulo", "text-anchor": "end" }, l.nome));
    l.pontos.forEach((p, k) => {
      const y = y0 + espalhar(k);
      const c = svg("circle", { cx: X(p.v), cy: y, r: 4, class: "ponto", fill: l.cor });
      g.append(c);
      alvos.push({ x: X(p.v), y, el: c, texto: () => [el("strong", {}, p.nome), el("div", {}, l.nome),
        el("div", {}, `Variação: ${fmtDif(p.v)}`),
        ...(p.A !== undefined && p.B !== undefined ? [el("div", {}, `${d.ano_a}: ${pct(p.A)} → ${d.ano_b}: ${pct(p.B)}`)] : [])] });
    });
    g.append(svg("line", { x1: X(l.ic[0]), x2: X(l.ic[1]), y1: y0, y2: y0, class: "ic", stroke: l.cor }),
      svg("line", { x1: X(l.media), x2: X(l.media), y1: y0 - 20, y2: y0 + 20, class: "media" }));
    // rótulos dos destaques acima ou abaixo da faixa, onde couberem sem encostar no anterior (senão, só na dica)
    const fim = [-Infinity, -Infinity];
    l.pontos.filter((p) => p.destaque).sort((a, b) => a.v - b.v).forEach((p) => {
      const meia = (p.nome.length * 5.6) / 2 + 4;
      const x = Math.min(Math.max(X(p.v), m.l + meia), W - m.r - meia);
      const lado = [0, 1].find((k) => x - meia > fim[k]);
      if (lado === undefined) return;
      fim[lado] = x + meia;
      g.append(svg("text", { x, y: lado ? y0 + 30 : y0 - 23, class: "rotulo-mun", "text-anchor": "middle" }, p.nome));
    });
  });
  const itensLeg: ItemLegenda[] = [...linhas.map((l): ItemLegenda => [l.cor, `${l.nome}: um ponto por município`]),
    [cor("--texto"), `Traço: média${d.ponderado ? " ponderada" : ""}; faixa: intervalo de 95% (bootstrap)`]];
  return el("div", {}, comDica(g, W, H, alvos), legendaLinha(itensLeg), botoesBaixar(g, itensLeg));
}
