/* Projeção do resultado final dos majoritários (apuracao/projecao.py): faixa da margem, ponto na projeção, traço
 * no parcial, e a lista de onde faltam votos (sob demanda). */
import { amostra } from "../../componentes/legenda";
import { api } from "../../core/api";
import { cor, el } from "../../core/dom";
import { fmtPct, int, pct } from "../../core/formatos";
import type { Projecao } from "./tipos";

/** Posição (%) no trilho: 0 a `topo`. */
export const posicao = (v: number | null | undefined, topo: number): string =>
  `${Math.max(0, Math.min(100, (100 * (v || 0)) / topo))}%`;

/** Fim do trilho: o maior máximo (Governador: pelo menos 52%, para a linha dos 50% caber), com folga de 5%. */
export const topoDoTrilho = (p: Pick<Projecao, "candidatos" | "cargo">): number =>
  Math.min(100, Math.max(...p.candidatos.map((x) => x.MAX || 0), p.cargo === 3 ? 52 : 0) * 1.05 || 1);

export function blocoProjecao(p: Projecao): HTMLElement[] {
  const cProj = cor("--seq-5"), cFaixa = cor("--seq-2"), cParcial = cor("--texto");
  const topo = topoDoTrilho(p);
  const x = (v: number | null | undefined) => posicao(v, topo);
  const linhas = p.candidatos.map((k) => el("div", { class: "proj-item",
    title: `${k.NOME_URNA}: parcial ${pct(k.PCT_ATUAL)} · projeção ${pct(k.PCT_PROJ)} (${pct(k.MIN)} a ${pct(k.MAX)})` },
  el("span", { class: "nome" }, `${k.NUMERO} ${k.NOME_URNA}`),
  el("span", { class: "proj-trilho" },
    p.cargo === 3 ? el("span", { class: "proj-50", style: { left: x(50) } }) : null,
    el("span", { class: "proj-faixa", style: { left: x(k.MIN), width: `calc(${x(k.MAX)} - ${x(k.MIN)})`, background: cFaixa } }),
    el("span", { class: "proj-parcial", style: { left: x(k.PCT_ATUAL), background: cParcial } }),
    el("span", { class: "proj-ponto", style: { left: x(k.PCT_PROJ), background: cProj } })),
  el("span", { class: "num" }, pct(k.PCT_PROJ))));
  const faltam = el("div", { class: "cad-eleitos" });
  const det = el("details", {
    ontoggle: async (e: Event) => {
      if (!(e.target as HTMLDetailsElement).open || faltam.childElementCount) return;
      faltam.textContent = "carregando…";
      try {
        const d = await api<{ faltam: { NM_MUNICIPIO?: string; CD_MUNICIPIO: number; PCT_APURADO: number | null; VALIDOS_RESTANTES: number }[] }>(
          `api/projecao?cargo=${p.cargo}`);
        faltam.replaceChildren(el("table", {}, el("thead", {}, el("tr", {}, ["Município", "Eleitorado apurado", "Válidos que faltam (est.)"]
          .map((t, i) => el("th", { class: i ? "num" : null }, t)))),
        el("tbody", {}, d.faltam.map((m) => el("tr", {}, el("td", {}, m.NM_MUNICIPIO || String(m.CD_MUNICIPIO)),
          el("td", { class: "num" }, pct(m.PCT_APURADO)), el("td", { class: "num" }, int(m.VALIDOS_RESTANTES)))))));
      } catch (err) { faltam.textContent = `não foi possível carregar: ${(err as Error).message}`; }
    },
  }, el("summary", {}, "Onde faltam votos"), faltam);
  const parcial = amostra(cParcial);
  parcial.style.width = "3px";
  return [
    el("h3", {}, "Projeção do resultado final"),
    el("div", { class: "sub" }, `${pct(p.pct_apurado)} do eleitorado apurado · margem ±${fmtPct.format(p.margem_pp ?? 0)} p.p. ` +
      `(erro de 95% das projeções na apuração de 2022) · ${p.municipios_sem_apuracao} município(s) ainda sem apuração`),
    el("p", { class: "proj-situacao" }, p.situacao),
    el("div", { class: "legenda-linha" },
      el("span", {}, amostra(cProj), "Projeção"),
      el("span", {}, amostra(cFaixa), "Margem"),
      el("span", {}, parcial, "Parcial agora"),
      p.cargo === 3 ? el("span", {}, "┆ 50% dos válidos") : null),
    el("div", { class: "proj-lista" }, linhas),
    det,
    el("p", { class: "nota" }, "Cada município completa o que falta com o voto já apurado nele. No RJ em 2022, até ~40% " +
      "apurado a projeção errou mais que o parcial (a capital apura por zonas); daí em diante, errou menos. A margem cobre os dois."),
  ];
}
