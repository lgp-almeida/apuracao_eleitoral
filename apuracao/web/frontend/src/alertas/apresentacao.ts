/* Como cada alerta aparece: ícone + rótulo (nunca só a cor), som por nível e o título da aba do navegador. */
import { el } from "../core/dom";
import type { Alerta, Nivel } from "./tipos";

export const NIVEL: Readonly<Record<Nivel, { icone: string; rotulo: string; fixo: boolean }>> = {
  critico: { icone: "✖", rotulo: "Crítico", fixo: true },
  aviso: { icone: "⚠", rotulo: "Atenção", fixo: true },
  noticia: { icone: "ℹ", rotulo: "Novidade", fixo: false },
  ok: { icone: "✓", rotulo: "Resolvido", fixo: false },
};

const ORDEM: readonly Nivel[] = ["critico", "aviso", "noticia", "ok"];

/** O nível mais grave de uma lista (o som que toca). */
export const maisGrave = (niveis: readonly Nivel[]): Nivel | undefined =>
  [...niveis].sort((x, y) => ORDEM.indexOf(x) - ORDEM.indexOf(y))[0];

/** Notas do bipe (Hz) por nível. */
export const notasDoSom = (nivel: Nivel): number[] =>
  (nivel === "critico" ? [880, 660, 880, 660] : nivel === "aviso" ? [740, 740] : [660]);

/** Título da aba do navegador: "⚠ " com condição grave, "(n) " com alertas não vistos. */
export function tituloComAlertas(titulo: string, grave: boolean, naoVistos: number): string {
  const base = titulo.replace(/^(⚠ )?(\(\d+\) )?/, "");
  return `${grave ? "⚠ " : ""}${naoVistos ? `(${naoVistos}) ` : ""}${base}`;
}

export function cartaoAlerta(a: Alerta, fechar: (() => void) | null = null): HTMLElement {
  const n = NIVEL[a.nivel] || NIVEL.noticia;
  const quando = (a.momento || a.desde || "").slice(11, 16);
  return el("div", { class: `alerta ${a.nivel}`, "data-chave": a.chave },
    el("span", { class: "icone", "aria-hidden": "true" }, n.icone),
    el("div", { class: "corpo" },
      el("div", { class: "rotulo" }, `${n.rotulo}${quando ? " · " + quando : ""}`),
      el("div", { class: "titulo" }, a.titulo),
      a.detalhe ? el("div", { class: "detalhe" }, a.detalhe) : null),
    fechar ? el("button", { type: "button", class: "fechar", "aria-label": "Dispensar", onclick: fechar }, "×") : null);
}
