/* Botões das abas no padrão WAI-ARIA de abas: só a aba aberta entra no Tab; ←/→ (e Home/End) andam entre as
 * abas visíveis e as abrem. A aba Comparação pode estar escondida (sem eleição de referência). */
import { ehAba, type Aba } from "../core/rotas";

/** Índice da aba que a tecla escolhe entre `n` abas visíveis, a partir de `atual`; null = tecla de outra coisa. */
export function indiceDaTecla(tecla: string, atual: number, n: number): number | null {
  if (n === 0) return null;
  switch (tecla) {
    case "ArrowRight": return (atual + 1) % n;
    case "ArrowLeft": return (atual - 1 + n) % n;
    case "Home": return 0;
    case "End": return n - 1;
    default: return null;
  }
}

const botoes = (nav: HTMLElement): HTMLButtonElement[] => [...nav.querySelectorAll<HTMLButtonElement>("button[role=tab]")];

/** Marca a aba aberta (aria-selected) e deixa só ela no Tab. */
export function marcarAba(nav: HTMLElement, aba: Aba): void {
  for (const b of botoes(nav)) {
    const sel = b.dataset.aba === aba;
    b.setAttribute("aria-selected", String(sel));
    b.tabIndex = sel ? 0 : -1;
  }
}

export function ligarAbas(nav: HTMLElement, abrir: (aba: Aba) => void): void {
  nav.addEventListener("click", (ev) => {
    const b = (ev.target as Element).closest<HTMLButtonElement>("button[role=tab]");
    if (b && ehAba(b.dataset.aba)) abrir(b.dataset.aba);
  });
  nav.addEventListener("keydown", (ev) => {
    const visiveis = botoes(nav).filter((b) => !b.hidden);
    const i = indiceDaTecla(ev.key, visiveis.indexOf(document.activeElement as HTMLButtonElement), visiveis.length);
    const alvo = i === null ? undefined : visiveis[i];
    if (!alvo || !ehAba(alvo.dataset.aba)) return;
    ev.preventDefault();
    abrir(alvo.dataset.aba);
    alvo.focus();
  });
}
