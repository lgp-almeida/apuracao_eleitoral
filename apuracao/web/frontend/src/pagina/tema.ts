/* Tema da página: segue o sistema ou é forçado (claro/escuro) por ?tema= no endereço (TV em quiosque) ou pela
 * escolha gravada neste navegador. Vira data-tema no <html> (tokens.css). Importado antes de tudo no main.ts,
 * para os mapas e gráficos lerem as cores certas já no primeiro desenho. */
import { lerTexto, gravarTexto } from "../core/preferencias";

export type Tema = "claro" | "escuro";
export const CHAVE_TEMA = "apuracao.tema";

const ehTema = (v: string | null | undefined): v is Tema => v === "claro" || v === "escuro";

/** O endereço (?tema=) vence a escolha gravada; "sistema" ou nada = segue o sistema (null). */
export function escolherTema(doEndereco: string | null, gravado: string | null): Tema | null {
  if (doEndereco !== null) return ehTema(doEndereco) ? doEndereco : null;
  return ehTema(gravado) ? gravado : null;
}

export function aplicarTema(tema: Tema | null, raiz: HTMLElement = document.documentElement): void {
  if (tema) raiz.dataset.tema = tema; else delete raiz.dataset.tema;
}

/** Tema escolhido no seletor do cabeçalho. As cores dos mapas e gráficos são lidas na hora de desenhar, então a
 * página recarrega: todo o estado visível das abas está no endereço e volta igual. */
export function ligarSeletorTema(sel: HTMLSelectElement, recarregar: () => void = () => location.reload()): void {
  sel.value = document.documentElement.dataset.tema ?? "";
  sel.addEventListener("change", () => {
    gravarTexto(CHAVE_TEMA, sel.value);
    const url = new URL(location.href);
    if (url.searchParams.has("tema")) {  // o ?tema= do endereço venceria a escolha
      url.searchParams.delete("tema");
      history.replaceState(history.state, "", url);
    }
    aplicarTema(ehTema(sel.value) ? sel.value : null);
    recarregar();
  });
}

aplicarTema(escolherTema(new URLSearchParams(location.search).get("tema"), lerTexto(CHAVE_TEMA)));
