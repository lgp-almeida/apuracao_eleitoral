/* Exportar gráficos no navegador (SVG e PNG). Mapas são desenhados no servidor (POST api/exportar/mapa). */
import { cor, el, svg, SVG } from "../core/dom";
import type { ItemLegenda } from "./escalas";

export function salvarBlob(blob: Blob, nome: string): void {
  const a = el("a", { href: URL.createObjectURL(blob), download: nome });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

const ESTILOS_EMBUTIDOS = ["fill", "stroke", "stroke-width", "font-size", "font-family", "opacity"];

/** SVG autônomo: estilos calculados embutidos (as classes usam variáveis CSS), sem a camada de interação,
 * com fundo e legenda desenhados dentro do próprio SVG. */
export function svgAutonomo(g: SVGSVGElement, itensLeg: readonly ItemLegenda[]): string {
  const clone = g.cloneNode(true) as SVGSVGElement;
  const orig = g.querySelectorAll<SVGElement>("*"), cop = clone.querySelectorAll<SVGElement>("*");
  orig.forEach((o, i) => {
    const cs = getComputedStyle(o);
    for (const p of ESTILOS_EMBUTIDOS) {
      const val = cs.getPropertyValue(p);
      if (val) cop[i].style.setProperty(p, val);
    }
  });
  clone.querySelectorAll("line.guia, rect").forEach((e) => e.remove());
  const [x0, y0, w, h] = (g.getAttribute("viewBox") ?? "0 0 0 0").split(" ").map(Number);
  const altura = h + 8 + 16 * itensLeg.length;
  clone.setAttribute("viewBox", `${x0} ${y0} ${w} ${altura}`);
  clone.setAttribute("xmlns", SVG);
  clone.setAttribute("width", String(w * 2)); clone.setAttribute("height", String(altura * 2));
  clone.insertBefore(svg("rect", { x: x0, y: y0, width: w, height: altura, fill: cor("--superficie") }), clone.firstChild);
  itensLeg.forEach(([c, t], i) => {
    const y = h + 8 + 16 * i;
    clone.append(svg("rect", { x: 40, y, width: 10, height: 10, rx: 2, fill: c }),
      svg("text", { x: 56, y: y + 9, "font-size": 11, fill: cor("--texto-2"), "font-family": "system-ui, sans-serif" }, t));
  });
  return new XMLSerializer().serializeToString(clone);
}

export async function baixarGrafico(g: SVGSVGElement, itensLeg: readonly ItemLegenda[], formato: "svg" | "png"): Promise<void> {
  const texto = svgAutonomo(g, itensLeg);
  const nome = `grafico_apuracao_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}`;
  if (formato === "svg") { salvarBlob(new Blob([texto], { type: "image/svg+xml" }), `${nome}.svg`); return; }
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(texto)}`;
  await img.decode();
  const canvas = el("canvas", { width: img.naturalWidth * 1.5, height: img.naturalHeight * 1.5 });
  canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((b) => { if (b) salvarBlob(b, `${nome}.png`); }, "image/png");
}

/** "Baixar gráfico: SVG PNG" sob um gráfico. */
export function botoesBaixar(g: SVGSVGElement, itensLeg: readonly ItemLegenda[]): HTMLElement {
  const botao = (formato: "svg" | "png") => el("button", { type: "button", class: "link",
    onclick: () => baixarGrafico(g, itensLeg, formato) }, formato.toUpperCase());
  return el("div", { class: "nota baixar-serie" }, "Baixar gráfico: ", botao("svg"), " ", botao("png"));
}
