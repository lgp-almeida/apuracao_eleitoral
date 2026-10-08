/* Construção de DOM sem HTML em texto: todo conteúdo entra como nó ou por textContent
 * (o TSE testa nomes com aspas e símbolos — nunca innerHTML; o lint proíbe). */

export const SVG = "http://www.w3.org/2000/svg";

/** Valor de atributo: null/undefined/false = omitido; true = atributo vazio; "on…" = ouvinte. */
export type Atributos = Record<string, unknown>;
/** Filho: nó, texto (inclusive número) ou nada; listas são achatadas. */
export type Filho = Node | string | number | null | undefined | false | readonly Filho[];

function anexar(n: Node & ParentNode, filhos: readonly Filho[]): void {
  for (const f of filhos.flat(Infinity as 1) as Filho[]) {
    if (f === null || f === undefined || f === false) continue;
    n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
}

/** Elemento HTML com atributos, estilo (inclusive propriedades personalizadas "--x"), ouvintes e filhos. */
export function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs?: Atributos, ...filhos: Filho[]): HTMLElementTagNameMap[K];
export function el(tag: string, attrs?: Atributos, ...filhos: Filho[]): HTMLElement;
export function el(tag: string, attrs: Atributos = {}, ...filhos: Filho[]): HTMLElement {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = String(v);
    else if (k === "style") {  // "--x": propriedade personalizada (Object.assign não as aplica)
      for (const [prop, val] of Object.entries(v as Record<string, string>)) {
        if (prop.startsWith("--")) n.style.setProperty(prop, val);
        else (n.style as unknown as Record<string, string>)[prop] = val;
      }
    } else if (k.startsWith("on")) n.addEventListener(k.slice(2), v as EventListener);
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  anexar(n, filhos);
  return n;
}

/** Elemento SVG: atributos sempre como texto; filhos como em el(). */
export function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs?: Atributos, ...filhos: Filho[]): SVGElementTagNameMap[K];
export function svg(tag: string, attrs: Atributos = {}, ...filhos: Filho[]): SVGElement {
  const n = document.createElementNS(SVG, tag) as SVGElement;
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  anexar(n, filhos);
  return n;
}

/** Valor atual de um token de cor do CSS (ex.: cor("--serie-1")). */
export const cor = (nome: string): string =>
  getComputedStyle(document.documentElement).getPropertyValue(nome).trim();

/** Busca obrigatória: um seletor sem elemento é erro de programação, avisado já na montagem da aba. */
export function ref<T extends Element = HTMLElement>(seletor: string, raiz: ParentNode = document): T {
  const n = raiz.querySelector<T>(seletor);
  if (!n) throw new Error(`elemento ausente na página: ${seletor}`);
  return n;
}

/** Várias buscas obrigatórias de uma vez; o erro lista TODOS os seletores sem elemento. */
export function refs<M extends Record<string, string>>(seletores: M, raiz: ParentNode = document): { [K in keyof M]: HTMLElement } {
  const faltam: string[] = [];
  const saida: Record<string, HTMLElement> = {};
  for (const [chave, seletor] of Object.entries(seletores)) {
    const n = raiz.querySelector<HTMLElement>(seletor);
    if (n) saida[chave] = n; else faltam.push(seletor);
  }
  if (faltam.length) throw new Error(`elementos ausentes na página: ${faltam.join(", ")}`);
  return saida as { [K in keyof M]: HTMLElement };
}
