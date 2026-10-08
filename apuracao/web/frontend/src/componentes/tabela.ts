/* Tabela ordenável por clique no cabeçalho, e a ficha (rótulo + valor) dos resumos. */
import { el, type Filho } from "../core/dom";

/** [rótulo, chave, numérica?] */
export type Coluna<L> = readonly [string, keyof L & string, boolean?];

export interface OpcoesTabela {
  /** Ordem inicial "COLUNA-desc" | "COLUNA-asc" (coluna desconhecida = 2ª coluna, decrescente). */
  ordem?: string | null;
  /** Avisa cada troca de ordem ("COLUNA-desc"), para o endereço. */
  aoOrdenar?: (ordem: string) => void;
}

export interface Ordem { k: string; desc: boolean }

/** Ordem inicial a partir do texto "COLUNA-dir". */
export function ordemInicial(colunas: readonly Coluna<never>[] | readonly (readonly [string, string, boolean?])[],
    texto: string | null | undefined): Ordem {
  const [k0, dir0] = (texto || "").split("-");
  return colunas.some(([, k]) => k === k0) ? { k: k0, desc: dir0 !== "asc" } : { k: colunas[1][1], desc: true };
}

/** Números como números; o resto como texto em pt-BR; ausente = "". */
export function ordenar<L extends Record<string, unknown>>(linhas: readonly L[], { k, desc }: Ordem): L[] {
  return [...linhas].sort((a, b) => {
    const x = a[k], y = b[k];
    const r = typeof x === "number" && typeof y === "number" ? x - y
      : String(x ?? "").localeCompare(String(y ?? ""), "pt-BR");
    return desc ? -r : r;
  });
}

export function tabelaOrdenavel<L extends Record<string, unknown>>(colunas: readonly Coluna<L>[], linhas: readonly L[],
    formatar: (linha: L, chave: keyof L & string) => Filho, aoClicar: ((linha: L) => void) | null = null,
    opcoes: OpcoesTabela = {}): HTMLTableElement {
  let ordem = ordemInicial(colunas, opcoes.ordem);
  const corpo = el("tbody");
  const render = () => {
    corpo.replaceChildren(...ordenar(linhas, ordem).map((r) => el("tr", {
      class: aoClicar ? "clicavel" : null, onclick: aoClicar ? () => aoClicar(r) : null },
    colunas.map(([, k, n]) => el("td", { class: n ? "num" : null }, formatar(r, k))))));
  };
  const cab = el("tr", {}, colunas.map(([rot, k, n]) => el("th", {
    class: n ? "num" : null, scope: "col",
    onclick: () => {
      ordem = { k, desc: ordem.k === k ? !ordem.desc : true };
      render();
      opcoes.aoOrdenar?.(`${ordem.k}-${ordem.desc ? "desc" : "asc"}`);
    },
  }, rot)));
  render();
  return el("table", {}, el("thead", {}, cab), corpo);
}

export function ficha(rot: Filho, val: Filho): HTMLElement {
  return el("div", { class: "ficha" }, el("div", { class: "rot" }, rot), el("div", { class: "val" }, val));
}
