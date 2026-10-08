/* Dispersão do Perfil × voto: voto (% dos válidos) × indicador, reta de tendência e cor pelo resíduo. */
import { cor, el, svg } from "../../core/dom";
import { fmtInt, fmtPct, int, pct } from "../../core/formatos";
import { comDica } from "../dica";
import { type ItemLegenda, passos } from "../escalas";
import { botoesBaixar } from "../exportar";
import { legendaLinha } from "../legenda";

export interface PontoDispersao { X: number; Y: number; BAIRRO: string; VALIDOS: number; RESIDUO: number | null }
export interface DadosDispersao {
  pontos: readonly PontoDispersao[];
  rotulo_x: string;
  rotulo_y: string;
  estatistica: { a: number; b: number | null };
  ponderado?: boolean;
}

/** Rótulo curto da marca do eixo x pelo tipo do indicador. */
export function marcaX(xk: string | null | undefined, v: number): string {
  return xk && xk.startsWith("renda") ? `R$ ${fmtInt.format(v)}` : xk === "densidade" ? fmtInt.format(v)
    : xk === "moradores_domicilio" ? String(v).replace(".", ",") : `${fmtInt.format(v)}%`;
}

/** Segmento da reta y = a + b·x dentro do retângulo [xMin, xMax] × [yMin, yMax]; null se não cruza. */
export function retaNoQuadro(a: number, b: number, [xMin, xMax]: [number, number], [yMin, yMax]: [number, number]):
    [number, number] | null {
  let x1 = xMin, x2 = xMax;
  if (b !== 0) {
    const lim = [(yMin - a) / b, (yMax - a) / b].sort((p, q) => p - q);
    x1 = Math.max(x1, lim[0]); x2 = Math.min(x2, lim[1]);
  }
  return x2 > x1 ? [x1, x2] : null;
}

/**
 * @param xk chave do indicador do eixo x (formato das marcas)
 * @param fmtX formata um valor do indicador na dica
 * @param unidade "Bairro", "Local" ou "Área" (legenda)
 */
export function graficoDispersao(d: DadosDispersao, xk: string | null, fmtX: (v: number) => string, unidade: string): HTMLElement {
  const W = 640, H = 400, m = { l: 56, r: 16, t: 12, b: 46 };
  const xs = d.pontos.map((p) => p.X), ys = d.pontos.map((p) => p.Y);
  const pad = (a: number, b: number): [number, number] => [a - (b - a) * 0.04 || a - 1, b + (b - a) * 0.04 || b + 1];
  const [xMin, xMax] = pad(Math.min(...xs), Math.max(...xs));
  const [yMin, yMax] = pad(Math.max(0, Math.min(...ys)), Math.max(...ys));
  const X = (v: number) => m.l + ((W - m.l - m.r) * (v - xMin)) / (xMax - xMin);
  const Y = (v: number) => m.t + (H - m.t - m.b) * (1 - (v - yMin) / (yMax - yMin));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "dispersao", role: "img",
    "aria-label": `${d.rotulo_y} × ${d.rotulo_x}: ${d.pontos.length} bairros` });
  for (const t of passos(yMin, yMax)) {
    if (t < yMin || t > yMax) continue;
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grade" }),
      svg("text", { x: m.l - 6, y: Y(t) + 3, class: "eixo", "text-anchor": "end" }, `${fmtInt.format(t)}%`));
  }
  for (const t of passos(xMin, xMax, 6)) {
    if (t < xMin || t > xMax) continue;
    g.append(svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: "grade" }),
      svg("text", { x: X(t), y: H - m.b + 14, class: "eixo", "text-anchor": "middle" }, marcaX(xk, t)));
  }
  g.append(svg("text", { x: (m.l + W - m.r) / 2, y: H - 8, class: "titulo-eixo", "text-anchor": "middle" }, d.rotulo_x),
    svg("text", { x: 12, y: (m.t + H - m.b) / 2, class: "titulo-eixo", "text-anchor": "middle",
      transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, "Voto (% dos válidos)"));
  const e = d.estatistica;
  if (e.b !== null) {  // reta cortada à área do gráfico
    const seg = retaNoQuadro(e.a, e.b, [xMin, xMax], [yMin, yMax]);
    const yDe = (x: number) => e.a + (e.b ?? 0) * x;
    if (seg) g.append(svg("line", { x1: X(seg[0]), y1: Y(yDe(seg[0])), x2: X(seg[1]), y2: Y(yDe(seg[1])), class: "tendencia" }));
  }
  const cAcima = cor("--div-p2"), cAbaixo = cor("--div-n2");
  const alvos = d.pontos.map((p) => {
    const c = svg("circle", { cx: X(p.X), cy: Y(p.Y), r: 4, class: "ponto", fill: (p.RESIDUO ?? 0) >= 0 ? cAcima : cAbaixo });
    g.append(c);
    return { x: X(p.X), y: Y(p.Y), el: c, texto: () => [el("strong", {}, p.BAIRRO), el("div", {}, `Eixo X: ${fmtX(p.X)}`),
      el("div", {}, `Voto: ${pct(p.Y)} de ${int(p.VALIDOS)} válidos`),
      el("div", {}, `Resíduo: ${(p.RESIDUO ?? 0) >= 0 ? "+" : "−"}${fmtPct.format(Math.abs(p.RESIDUO ?? 0))} p.p.`)] };
  });
  const itensLeg: ItemLegenda[] = [[cAcima, `${unidade} acima da tendência`], [cAbaixo, `${unidade} abaixo da tendência`],
    [cor("--texto-2"), `Tendência (mínimos quadrados${d.ponderado ? ", ponderada" : ""})`]];
  return el("div", {}, comDica(g, W, H, alvos), legendaLinha(itensLeg), botoesBaixar(g, itensLeg));
}
