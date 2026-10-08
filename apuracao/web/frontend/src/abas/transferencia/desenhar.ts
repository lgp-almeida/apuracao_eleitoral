/* Resultado da transferência 1º → 2º turno: fichas, barras (para onde foi cada grupo), matriz com IC e tabelas. */
import { ficha } from "../../componentes/tabela";
import { el } from "../../core/dom";
import { decimal, fmtInt, int, mil, p1 } from "../../core/formatos";
import type { LinhaTabela, ResultadoTransferencia } from "./tipos";

/** Cores das categorias do 2º turno: finalista A, B, branco/nulo, abstenção; e a tinta do texto sobre cada uma. */
const CORES_2T = ["--serie-1", "--serie-2", "--outros", "--texto-2"];
const TINTA_2T = ["#fff", "#fff", "var(--texto)", "var(--superficie)"];
const NOME_NIVEL = { secao: "seção", local: "local de votação", municipio: "município" } as const;
const corCategoria = (j: number) => `var(${CORES_2T[j]})`;

/** Valor de célula das tabelas: _PP com sinal, _PCT em %, número inteiro, texto como veio. */
export function formatarCelula(k: string, v: string | number | null | undefined): string {
  if (typeof v !== "number") return v ?? "—";
  if (k.endsWith("_PP")) return `${v >= 0 ? "+" : ""}${decimal(v, 1)}`;
  return k.endsWith("_PCT") ? p1(v) : int(v);
}

/** Leitura frágil: municípios como unidade (viés de agregação) ou muitas células no limite 0%/100%. */
export const leituraFragil = (r: Pick<ResultadoTransferencia, "nivel" | "celulas_no_limite">): boolean =>
  r.nivel === "municipio" || r.celulas_no_limite >= 6;

type ColunaTf = readonly [string, string, boolean?];

function tabela(titulo: string, cols: readonly ColunaTf[], linhas: readonly LinhaTabela[]): HTMLElement {
  return el("div", {}, el("h3", {}, titulo),
    el("div", { class: "tabela-rolagem" }, el("table", {},
      el("thead", {}, el("tr", {}, ...cols.map(([rot, , num]) => el("th", { class: num ? "n" : null }, rot)))),
      el("tbody", {}, ...linhas.map((l) => el("tr", {}, ...cols.map(([, k, num]) =>
        el("td", { class: num ? "n" : null }, formatarCelula(k, l[k])))))))));
}

export function desenharTransferencia(r: ResultadoTransferencia): HTMLElement[] {
  const cat2 = r.categorias_2t;
  const val = r.validacao;
  const ab = r.abstencao;
  const fichas = el("div", { class: "fichas" },
    ficha("Unidades", `${fmtInt.format(r.unidades)} (${NOME_NIVEL[r.nivel]})`),
    ficha("Regiões com matriz própria", r.n_estratos > 1 ? `${r.n_estratos} (${r.estrato === "zona" ? "zonas" : "municípios"})` : "uma só"),
    ficha("Abstenção 1º → 2º turno", `${p1(ab.pct_1t)} → ${p1(ab.pct_2t)} (${ab.extra_pp >= 0 ? "+" : ""}${decimal(ab.extra_pp, 2)} p.p.)`),
    val ? ficha("Erro fora da amostra", `${decimal(val.rmse_modelo_medio_pp, 2)} p.p. (swing uniforme ${decimal(val.rmse_swing_medio_pp, 2)})`) : null,
    ficha("Células no limite (0% ou 100%)", `${r.celulas_no_limite} de ${r.categorias_1t.length * cat2.length}`));
  const legenda = el("div", { class: "tf-legenda" },
    ...cat2.map((c, j) => el("span", { style: { "--cor": corCategoria(j) } }, c)));
  const barras = r.matriz.map((m) => el("div", { class: "tf-linha" },
    el("div", { class: "rot" }, m.origem, el("small", {}, `${p1(m.pct_1t)} do eleitorado · ${mil(m.eleitores_1t)}`)),
    el("div", { class: "tf-barra", role: "img",
      "aria-label": `${m.origem}: ` + m.destinos.map((d) => `${d.destino} ${p1(d.pct)}`).join(", ") },
    ...m.destinos.map((d, j) => d.pct < 0.05 ? null : el("div", {
      style: { width: `${d.pct}%`, "--cor": corCategoria(j), "--tinta": TINTA_2T[j] },
      title: `${m.origem} → ${d.destino}: ${p1(d.pct)} (IC 95% ${p1(d.baixo)} a ${p1(d.alto)}); ≈ ${mil(d.eleitores)} eleitores`,
    }, d.pct >= 7 ? p1(d.pct) : "")))));
  const matriz = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "1º turno"), el("th", { class: "n" }, "Eleitores"),
      ...cat2.map((c) => el("th", { class: "n" }, c)))),
    el("tbody", {}, ...r.matriz.map((m) => el("tr", {}, el("td", {}, m.origem), el("td", { class: "n" }, int(m.eleitores_1t)),
      ...m.destinos.map((d) => el("td", { class: "n", title: `≈ ${int(d.eleitores)} eleitores` },
        p1(d.pct), el("br"), el("small", { class: "nota" }, `${p1(d.baixo)}–${p1(d.alto)}`)))))));
  const [a] = cat2;
  const porRegiao = r.estrato === "zona" ? "zona" : "município";
  const estratos = r.n_estratos > 1 ? tabela(`Votos dos eliminados, por ${porRegiao} (maiores eleitorados)`,
    [["Região", "ESTRATO"], ["Eliminados no 1º", "ELIMINADOS_1T", true],
      ...cat2.map((c): ColunaTf => [`→ ${c}`, `ELIM_PARA_${c}_PCT`, true])], r.estratos) : null;
  const nome = r.nivel === "municipio" ? "Município" : "Unidade";
  const abst = tabela("Maior abstenção extra (p.p. do eleitorado)", [[nome, "NOME"], ["Município", "NM_MUNICIPIO"],
    ["1º turno", "ABST_1_PCT", true], ["2º turno", "ABST_2_PCT", true], ["Extra", "ABST_EXTRA_PP", true]],
  r.maior_abstencao_extra);
  const res = (titulo: string, linhas: readonly LinhaTabela[]) => tabela(titulo, [[nome, "NOME"], ["Município", "NM_MUNICIPIO"],
    ["Observado", `${a}_2_PCT`, true], ["Previsto", `${a}_2_AJUSTE_PCT`, true], ["Diferença (p.p.)", "RESIDUO_A_PP", true]],
  linhas);
  const novos = ab.novos_abstencionistas.filter((n) => n.eleitores > 0)
    .map((n) => `${n.origem}: ${mil(n.eleitores)}`).join(" · ");
  const partes: (HTMLElement | null)[] = [
    el("h3", {}, `Para onde foi cada grupo do 1º turno — ${r.descricao}`),
    leituraFragil(r) ? el("p", { class: "aviso" }, "Leitura frágil: ",
      r.nivel === "municipio" ? "com municípios como unidades o viés de agregação é grande (em 2022, no RJ, o destino "
        + "dos eliminados por município diferiu em até 22 p.p. do estimado por seção). Use como indicação; a estimativa "
        + "boa vem com os microdados (seção ou local), dias depois do 2º turno. "
        : "",
      `${r.celulas_no_limite} células ficaram em 0% ou 100% (a restrição segurou valores impossíveis).`) : null,
    fichas, legenda, el("div", {}, ...barras),
    el("p", { class: "nota" }, "Passe o mouse numa barra para o intervalo de 95% e o número de eleitores. ",
      `Votaram no 1º turno e se abstiveram no 2º (estimado): ${novos || "—"}.`),
    el("details", { class: "caixa" }, el("summary", {}, "Matriz completa, com intervalos de 95%"),
      el("div", { class: "tabela-rolagem" }, matriz)),
    el("div", { class: "tf-tabelas" }, estratos, abst,
      res(`Onde ${a} foi melhor do que a matriz prevê`, r.residuos_a.acima),
      res(`Onde ${a} foi pior do que a matriz prevê`, r.residuos_a.abaixo)),
  ];
  return partes.filter((n): n is HTMLElement => n !== null);
}
