/* Linha de metadados de um bloco (seções, hora, FINAL, vagas…): um elemento por item, sem "·" entre eles. Cada
 * item quebra linha inteiro, então nunca sobra um separador solto no começo da linha. */
import { el, type Filho } from "../core/dom";

export function metadados(...itens: Filho[]): HTMLElement {
  return el("div", { class: "sub metadados" },
    itens.filter((i) => i !== null && i !== undefined && i !== false && i !== "").map((i) => el("span", {}, i)));
}
