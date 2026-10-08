/* Legendas: amostra de cor + texto. Em linha (gráficos, mapa por UF) ou em bloco com título (mapas). */
import { el } from "../core/dom";
import type { ItemLegenda } from "./escalas";

export const amostra = (c: string, redonda = false): HTMLElement =>
  el("span", { class: redonda ? "amostra redonda" : "amostra", style: { background: c } });

export function legendaLinha(itens: readonly ItemLegenda[]): HTMLElement {
  return el("div", { class: "legenda-linha" }, itens.map(([c, t]) => el("span", {}, amostra(c), t)));
}

/** Conteúdo da legenda de um mapa: título, itens e notas (ex.: aviso de erro amostral). */
export function legendaMapa(titulo: string, itens: readonly ItemLegenda[],
    opcoes: { redonda?: boolean; notas?: readonly (HTMLElement | null)[] } = {}): HTMLElement[] {
  return [el("h4", {}, titulo), ...itens.map(([c, t]) => el("div", {}, amostra(c, opcoes.redonda), t)),
    ...(opcoes.notas ?? []).filter((n): n is HTMLElement => n !== null)];
}
