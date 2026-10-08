/* Linhas com eixo x numérico (evolução na apuração); cada série pode ter os próprios x
 * (ex.: município × estado no tempo). Até 3 séries (cores --serie-1..3), rótulo direto na ponta. */
import { cor, el, svg } from "../../core/dom";
import { fmtPct, pct } from "../../core/formatos";
import type { ItemLegenda } from "../escalas";
import { botoesBaixar } from "../exportar";
import { amostra } from "../legenda";

export interface SerieLinha {
  nome: string;
  rotulo: string;
  valores: readonly (number | null)[];
  /** x próprios desta série (senão, os do gráfico). */
  xs?: readonly number[];
}

export interface OpcoesLinhas<S extends SerieLinha> {
  xs: readonly number[];
  xMin: number;
  xMax: number;
  xTicks: readonly number[];
  xFmt: (t: number) => string;
  series: readonly S[];
  /** Título da dica no índice k do x mais próximo (xv = x sob o mouse). */
  dica: (k: number, xv: number) => string;
  /** Linha de cada série na dica (padrão: "rótulo: %"). */
  dicaSerie?: (s: S, j: number) => string;
}

/** Índice do valor mais próximo de xv. */
export const maisPerto = (arr: readonly number[], xv: number): number =>
  arr.reduce((k, x, j) => (Math.abs(x - xv) < Math.abs(arr[k] - xv) ? j : k), 0);

/** Faixa do eixo y: dados ± 12% (mínimo 0,5 p.p.), dentro de 0–100. */
export function faixaY(valores: readonly (number | null)[]): [number, number] {
  const todos = valores.filter((v): v is number => v !== null);
  let yMin = Math.min(...todos), yMax = Math.max(...todos);
  const pad = Math.max((yMax - yMin) * 0.12, 0.5);
  yMin = Math.max(0, yMin - pad); yMax = Math.min(100, yMax + pad);
  return [yMin, yMax];
}

export function graficoLinhas<S extends SerieLinha>(o: OpcoesLinhas<S>): HTMLElement {
  const { xs, xMin, xMax, xTicks, xFmt, series, dica: textoDica, dicaSerie } = o;
  const W = 420, H = 170, m = { l: 40, r: 52, t: 10, b: 22 };
  const cores = ["--serie-1", "--serie-2", "--serie-3"].map(cor);
  const xsDe = (s: S) => s.xs || xs;
  const [yMin, yMax] = faixaY(series.flatMap((s) => s.valores));
  const X = (v: number) => m.l + ((W - m.l - m.r) * (v - xMin)) / (xMax - xMin || 1);
  const Y = (v: number) => m.t + (H - m.t - m.b) * (1 - (v - yMin) / (yMax - yMin || 1));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "serie", role: "img",
    "aria-label": `Evolução do % dos válidos: ${series.map((s) => s.nome).join(", ")}` });
  // grade e eixos (recessivos)
  for (const t of [0, 1, 2, 3].map((i) => yMin + ((yMax - yMin) * i) / 3)) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grade" }),
      svg("text", { x: m.l - 4, y: Y(t) + 3, class: "eixo", "text-anchor": "end" }, `${fmtPct.format(t)}%`));
  }
  for (const t of xTicks) g.append(svg("text", { x: X(t), y: H - 8, class: "eixo", "text-anchor": "middle" }, xFmt(t)));
  // linhas + ponto final
  const fim: { x: number; y: number; texto: string }[] = [];
  series.forEach((s, i) => {
    const sx = xsDe(s);
    const pts = s.valores.flatMap((v, k) => (v === null ? [] : [[X(sx[k]), Y(v), v] as const]));
    g.append(svg("polyline", { points: pts.map((p) => `${p[0]},${p[1]}`).join(" "), fill: "none", stroke: cores[i],
      "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const ult = pts.at(-1);
    if (ult) {  // último valor existente (um nulo no fim não vira "0,00%")
      g.append(svg("circle", { cx: ult[0], cy: ult[1], r: 4, fill: cores[i], stroke: cor("--superficie"), "stroke-width": 2 }));
      fim.push({ y: ult[1], x: ult[0], texto: `${fmtPct.format(ult[2])}%` });  // nome fica na legenda
    }
  });
  // rótulos diretos na ponta, afastados para não colidir (texto na cor de texto, não da série)
  fim.sort((a, b) => a.y - b.y);
  for (let k = 1; k < fim.length; k++) fim[k].y = Math.max(fim[k].y, fim[k - 1].y + 12);
  for (const f of fim) g.append(svg("text", { x: W - m.r + 8, y: f.y + 4, class: "rotulo" }, f.texto));
  // camada de interação: linha vertical + dica com todos os valores do ponto mais próximo
  const guia = svg("line", { y1: m.t, y2: H - m.b, class: "guia", visibility: "hidden" });
  const alvo = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  g.append(guia, alvo);
  const dica = el("div", { class: "dica", hidden: true });
  const caixa = el("div", { class: "serie-caixa" }, g, dica);
  alvo.addEventListener("mousemove", (ev) => {
    const r = g.getBoundingClientRect();
    const xv = xMin + (((ev.clientX - r.left) * (W / r.width) - m.l) / (W - m.l - m.r)) * (xMax - xMin);
    const base = xsDe(series[0]);
    const k = maisPerto(base, xv);
    guia.setAttribute("x1", String(X(base[k]))); guia.setAttribute("x2", String(X(base[k])));
    guia.setAttribute("visibility", "visible");
    dica.replaceChildren(el("strong", {}, textoDica(k, xv)),
      ...series.map((s, i) => {
        const j = s.xs ? maisPerto(s.xs, xv) : k;
        return el("div", {}, amostra(cores[i]), dicaSerie ? dicaSerie(s, j) : `${s.rotulo}: ${pct(s.valores[j])}`);
      }));
    dica.hidden = false;
    dica.style.left = `${Math.min((ev.clientX - r.left) + 12, r.width - 220)}px`;
  });
  alvo.addEventListener("mouseleave", () => { guia.setAttribute("visibility", "hidden"); dica.hidden = true; });
  const itensLeg = series.map((s, i): ItemLegenda => [cores[i], s.rotulo]);
  const legenda = el("div", { class: "legenda-linha" }, itensLeg.map(([c, t]) => el("span", {}, amostra(c), t)));
  return el("div", {}, caixa, legenda, botoesBaixar(g, itensLeg));
}
