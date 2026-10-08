/* Dicas. Duas formas, uma por situação:
 * - dicaFlutuante: presa à janela (position: fixed), para conteúdo maior que o mapa (o tooltip do Leaflet
 *   seria cortado pelo mapa — rodada 35);
 * - comDica: dentro de um gráfico SVG, a do ponto mais próximo do mouse (alvo maior que o ponto). */
import { el } from "../core/dom";

let flutuante: HTMLElement | null = null;

function posicionar(ev: MouseEvent): void {
  const d = flutuante;
  if (!d || d.hidden) return;
  const m = 14, w = d.offsetWidth, h = d.offsetHeight;
  let x = ev.clientX + m, y = ev.clientY + m;
  if (x + w > window.innerWidth - 4) x = Math.max(4, ev.clientX - m - w);
  if (y + h > window.innerHeight - 4) y = Math.max(4, window.innerHeight - h - 4);
  d.style.left = `${x}px`; d.style.top = `${y}px`;
}

export const dicaFlutuante = {
  mostrar(conteudo: Node, ev?: MouseEvent): void {
    if (!flutuante) {
      flutuante = el("div", { class: "dica-flutuante", role: "tooltip" });
      document.body.append(flutuante);
    }
    flutuante.replaceChildren(conteudo);
    flutuante.hidden = false;
    if (ev) posicionar(ev);
  },
  posicionar(ev?: MouseEvent): void { if (ev) posicionar(ev); },
  esconder(): void { if (flutuante) flutuante.hidden = true; },
};

export interface AlvoDica {
  /** Posição do ponto em unidades do viewBox. */
  x: number;
  y: number;
  /** Marca que ganha a classe "ativo" enquanto a dica é dela. */
  el: Element;
  texto: () => (Node | string)[];
}

/** Envolve o SVG (viewBox W × H) numa caixa com a dica do ponto mais próximo (até 14 unidades). */
export function comDica(g: SVGSVGElement, W: number, H: number, alvos: readonly AlvoDica[]): HTMLElement {
  const dica = el("div", { class: "dica", hidden: true });
  let ativo: Element | null = null;
  const soltar = () => { if (ativo) ativo.classList.remove("ativo"); ativo = null; };
  g.addEventListener("mousemove", (ev) => {
    const r = g.getBoundingClientRect();
    const mx = (ev.clientX - r.left) * (W / r.width), my = (ev.clientY - r.top) * (H / r.height);
    let k = -1, melhor = 14 ** 2;
    alvos.forEach((a, i) => { const dd = (a.x - mx) ** 2 + (a.y - my) ** 2; if (dd < melhor) { melhor = dd; k = i; } });
    soltar();
    if (k < 0) { dica.hidden = true; return; }
    ativo = alvos[k].el; ativo.classList.add("ativo");
    dica.replaceChildren(...alvos[k].texto());
    dica.hidden = false;
    dica.style.left = `${Math.min(ev.clientX - r.left + 12, r.width - 230)}px`;
    dica.style.top = `${Math.max(4, ev.clientY - r.top - 80)}px`;
  });
  g.addEventListener("mouseleave", () => { dica.hidden = true; soltar(); });
  return el("div", { class: "serie-caixa" }, g, dica);
}
