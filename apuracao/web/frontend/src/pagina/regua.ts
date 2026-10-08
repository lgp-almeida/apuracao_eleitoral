/* Régua de apuração: a assinatura da página, sob o cabeçalho, em todas as abas e no modo TV. Mostra o % das
 * seções totalizadas na UF e a hora da última totalização, com os números que /api/status já traz. */
import { el } from "../core/dom";
import { decimal } from "../core/formatos";
import type { Status } from "./situacao";

export interface DadosRegua { uf: string; pct: number; hora: string | null; final: boolean }

/** Linhas da UF (presidente e cargos estaduais têm eleições diferentes): o MENOR % (as urnas são as mesmas; na
 * dúvida, o mais atrasado), a hora mais recente e "final" só com todas finais. Sem linha da UF = sem régua. */
export function dadosRegua(s: Pick<Status, "uf" | "progresso">): DadosRegua | null {
  const linhas = s.progresso.filter((p) => p.ABRANGENCIA === "uf" && p.PCT_SECOES_TOTALIZADAS !== null);
  if (!linhas.length) return null;
  const horas = linhas.map((p) => p.DT_TOTALIZACAO).filter((h): h is string => !!h).sort();
  return {
    uf: s.uf || (linhas[0]?.UF ?? ""),
    pct: Math.min(...linhas.map((p) => p.PCT_SECOES_TOTALIZADAS as number)),
    hora: horas.at(-1) ?? null,
    final: linhas.every((p) => p.TOTALIZACAO_FINAL),
  };
}

/** "22:22" no dia de hoje; "04/10 22:22" em outro dia (a hora do TSE é a de Brasília, sem fuso). */
export function horaCurta(iso: string, hoje: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hm = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === hoje.toDateString() ? hm
    : `${d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${hm}`;
}

export function desenharRegua(raiz: HTMLElement, trilho: HTMLElement, d: DadosRegua | null): void {
  raiz.hidden = trilho.hidden = !d;
  if (!d) return;
  const pct = `${decimal(d.pct, 1)}%`;
  raiz.setAttribute("aria-valuenow", String(d.pct));
  raiz.setAttribute("aria-valuetext", `${pct} das seções totalizadas em ${d.uf}`);
  raiz.replaceChildren(...[
    el("span", { class: "regua-pct" }, pct),
    el("span", { class: "regua-uf" }, `das seções em ${d.uf}`),
    d.hora ? el("span", { class: "regua-hora" }, `totalização ${horaCurta(d.hora)}`) : null,
    d.final ? el("span", { class: "regua-final" }, "✓ final") : null,
  ].filter((n) => n !== null));
  (trilho.firstElementChild as HTMLElement).style.width = `${Math.max(0, Math.min(100, d.pct))}%`;
}
