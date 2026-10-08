/* Resultado do Perfil × voto: fichas da correlação, tabela de correlações, resíduos e regressão. */
import { ficha } from "../../componentes/tabela";
import { el } from "../../core/dom";
import { decimal, fmtP, fmtPct, fmtR, int, pct } from "../../core/formatos";
import type { PontoDispersao } from "../../componentes/grafico/dispersao";
import { forca, fmtX, unidadeDoX } from "./formatos";
import type { Correlacao, Dispersao, Regressao } from "./tipos";

/** ±x,xx (2 casas, menos tipográfico). */
const sinal = (x: number) => `${x >= 0 ? "+" : "−"}${fmtPct.format(Math.abs(x))}`;

export function fichasCorrelacao(d: Dispersao, xk: string | null, unidades: string): HTMLElement[] {
  const e = d.estatistica;
  return [
    ficha(`${unidades} na análise`, int(e.n) + (d.ponderado ? ` (n efetivo ${int(Math.round(e.n_efetivo || 0))})` : "")),
    ficha("Pearson r", e.pearson === null ? "—" : `${fmtR(e.pearson)} (${forca(e.pearson)})`),
    ficha("IC 95% de r", e.ic95 ? `${fmtR(e.ic95[0])} a ${fmtR(e.ic95[1])}` : "—"),
    ficha("Spearman ρ", fmtR(e.spearman)),
    ficha("p-valor (r ≠ 0)", fmtP(e.p)),
    ficha("R²", e.r2 === null ? "—" : fmtPct.format(100 * e.r2) + "%"),
    ficha(`Inclinação (+1 ${unidadeDoX(xk)} no eixo X)`, e.b === null ? "—" :
      `${e.b >= 0 ? "+" : "−"}${Math.abs(e.b).toLocaleString("pt-BR", { maximumSignificantDigits: 3 })} p.p.`),
  ];
}

/** Correlações da mais forte para a mais fraca; clicar numa linha põe o indicador no eixo X. */
export function tabelaCorrelacoes(cs: readonly Correlacao[], xk: string | null, unidades: string,
    aoEscolher: (indicador: string) => void): HTMLElement {
  const linhas = cs.map((k) => el("tr", {
    class: `clicavel${k.indicador === xk ? " selecionado" : ""}`, "data-indicador": k.indicador,
    onclick: () => aoEscolher(k.indicador),
  }, el("td", {}, k.rotulo), el("td", { class: "num" }, fmtR(k.pearson)), el("td", { class: "num" }, fmtR(k.spearman)),
  el("td", { class: "num" }, k.ic95 ? `${fmtR(k.ic95[0])} a ${fmtR(k.ic95[1])}` : "—"), el("td", { class: "num" }, int(k.n)),
  el("td", { title: k.fonte }, k.fonte.startsWith("TSE") ? "TSE" : "IBGE")));
  return el("table", {}, el("thead", {}, el("tr", {},
    ["Indicador", "r", "ρ", "IC 95% (r)", unidades, "Fonte"].map((t, i) => el("th", { class: i && i < 5 ? "num" : null }, t)))),
  el("tbody", {}, linhas));
}

/** Unidades acima ou abaixo da tendência. */
export function tabelaResiduos(linhas: readonly PontoDispersao[], xk: string | null, unidade: string): HTMLElement {
  return el("table", {}, el("thead", {}, el("tr", {}, [unidade, "Eixo X", "Voto", "Resíduo"].map((t, i) =>
    el("th", { class: i ? "num" : null }, t)))), el("tbody", {}, linhas.map((r) => el("tr", {},
    el("td", {}, r.BAIRRO), el("td", { class: "num" }, fmtX(xk, r.X)), el("td", { class: "num" }, pct(r.Y)),
    el("td", { class: "num" }, `${sinal(r.RESIDUO ?? 0)} p.p.`)))));
}

/** Regressão com vários indicadores: fichas e tabela, ou o motivo de não haver. */
export function desenharRegressao(rg: Regressao | { erro: string } | null, unidades: string):
    { fichas: HTMLElement[]; tabela: HTMLElement } {
  if (!rg) return { fichas: [], tabela: el("p", { class: "nota" }, "Marque ao menos um indicador.") };
  if ("erro" in rg) return { fichas: [], tabela: el("p", { class: "nota" }, `Regressão indisponível: ${rg.erro}`) };
  const fichas = [ficha(unidades, int(rg.n)),
    ficha("R² (juntos)", fmtPct.format(100 * rg.r2) + "%"), ficha("R² ajustado", fmtPct.format(100 * rg.r2_ajustado) + "%")];
  const tabela = el("table", {}, el("thead", {}, el("tr", {},
    ["Indicador", "Efeito (p.p. por +1 dp)", "IC 95%", "p", "VIF", "r simples", "1 dp ="].map((t, i) =>
      el("th", { class: i ? "num" : null }, t)))),
  el("tbody", {}, rg.coeficientes.map((k) => el("tr", { class: k.vif > 5 ? "cad-disputa" : null,
    title: k.vif > 5 ? "VIF > 5: anda junto com outro indicador; efeito individual instável" : null },
  el("td", {}, k.rotulo), el("td", { class: "num" }, `${sinal(k.efeito_pp_por_dp)} p.p.`),
  el("td", { class: "num" }, `${sinal(k.ic95[0])} a ${sinal(k.ic95[1])}`), el("td", { class: "num" }, fmtP(k.p)),
  el("td", { class: "num" }, decimal(k.vif, 1)), el("td", { class: "num" }, fmtR(k.r_simples)),
  el("td", { class: "num" }, fmtX(k.indicador, k.dp_indicador))))));
  return { fichas, tabela };
}
