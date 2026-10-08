/* Cartão de um cargo no painel: totalização, eleitorado e votos, série, candidatos, partidos, projeção e cadeiras. */
import { graficoLinhas } from "../../componentes/grafico/linhas";
import { amostra } from "../../componentes/legenda";
import { cor, el } from "../../core/dom";
import { hora, int, pct } from "../../core/formatos";
import { blocoCadeiras, type ContextoCadeiras } from "./cadeiras";
import { blocoProjecao } from "./projecao";
import type { CandidatoPainel, Cartao, SeriePainel } from "./tipos";

/** Votos de candidatura sub judice entram nos votos do candidato, mas não nos válidos. */
export const destinacao = (x: Pick<CandidatoPainel, "DESTINACAO">): string =>
  (x.DESTINACAO && x.DESTINACAO !== "Válido" ? ` · ${x.DESTINACAO}` : "");

interface Segmento { rotulo: string; valor: number; cor: string }

/** Barra de composição (comparecimento × abstenção; válidos × brancos × nulos…) com legenda. */
export function composicao(segmentos: readonly Segmento[], total: number): HTMLElement[] {
  const barras = segmentos.filter((s) => s.valor > 0).map((s) =>
    el("div", { style: { width: `${(100 * s.valor) / total}%`, background: s.cor }, title: `${s.rotulo}: ${int(s.valor)}` }));
  const legenda = segmentos.map((s) => el("span", {}, amostra(s.cor), `${s.rotulo} ${int(s.valor)} (${pct((100 * s.valor) / total)})`));
  return [el("div", { class: "composicao", role: "img", "aria-label": legenda.map((l) => l.textContent).join("; ") }, barras),
    el("div", { class: "legenda-linha" }, legenda)];
}

/** Evolução na apuração: % dos válidos dos 3 mais votados × % das seções totalizadas. */
export function blocoSerie(serie: SeriePainel | null | undefined, proporcional: boolean): HTMLElement[] {
  const titulo = el("h3", {}, `Evolução na apuração — % dos válidos dos 3 ${proporcional ? "partidos" : "candidatos"} ` +
    "mais votados × % das seções totalizadas");
  if (!serie || serie.pontos.length < 2) {
    const n = serie ? serie.pontos.length : 0;
    return [titulo, el("p", { class: "nota" }, `A série aparece a partir da 2ª totalização (${n} registrada${n === 1 ? "" : "s"} até agora).`)];
  }
  return [titulo, graficoLinhas({
    xs: serie.pontos.map((p) => p.pct_secoes ?? 0), xMin: 0, xMax: 100, xTicks: [0, 25, 50, 75, 100], xFmt: (t) => `${t}%`,
    series: serie.series.map((s) => ({ nome: s.NOME, rotulo: `${s.CHAVE !== s.NOME ? s.CHAVE + " " : ""}${s.NOME}` +
      `${s.CHAVE !== s.NOME ? ` (${s.PARTIDO})` : ""}`, valores: s.valores })),
    dica: (k) => `${hora(serie.pontos[k].dt)} · ${pct(serie.pontos[k].pct_secoes)} das seções`,
  })];
}

export interface ContextoCartao extends ContextoCadeiras {
  /** Duplo clique num candidato abre a aba Candidato. */
  consultarCandidato(cargo: number, numero: number): void;
  /** Bloco "Por estado" (só no cartão Presidente — BRASIL). */
  blocoBrasil(): HTMLElement;
}

function linhaCandidato(pos: number, x: CandidatoPainel, maxPct: number, cargo: number, c: ContextoCartao): HTMLElement {
  return el("div", {
    class: "item" + (x.ELEITO ? " destaque" : ""),
    title: `${x.NOME_URNA} (${x.PARTIDO}) — ${int(x.VOTOS)} votos, ${pct(x.PCT_VALIDOS)} — ${x.SITUACAO || ""}${destinacao(x)}`,
    ondblclick: () => c.consultarCandidato(cargo, x.NUMERO),
  },
  el("span", { class: "pos" }, pos),
  el("span", { class: "nome" }, `${x.NUMERO} ${x.NOME_URNA} `, el("small", {}, x.PARTIDO)),
  el("span", { class: "barra" }, el("div", { style: { width: `${(100 * (x.PCT_VALIDOS || 0)) / maxPct}%` } })),
  el("span", { class: "num" }, pct(x.PCT_VALIDOS)),
  el("span", { class: "sit" }, (x.SITUACAO || "") + destinacao(x)));
}

export function cartao(c: Cartao, ctx: ContextoCartao): HTMLElement {
  const t = c.totais;
  const comp = (t.COMPARECIMENTO || 0) + (t.ABSTENCAO || 0);
  const votos = (t.VALIDOS || 0) + (t.BRANCOS || 0) + (t.NULOS || 0) + (t.ANULADOS_SUB_JUDICE || 0);
  const maxPct = Math.max(...c.candidatos.map((x) => x.PCT_VALIDOS || 0), 0.0001);
  const vagas = t.VAGAS ? ` · ${t.VAGAS} vaga${t.VAGAS > 1 ? "s" : ""}` : "";
  const filhos: HTMLElement[] = [
    el("div", {}, el("h2", {}, `${c.ds_cargo} — ${c.abrangencia}`),
      el("div", { class: "sub" }, `Seções totalizadas ${pct(t.PCT_SECOES_TOTALIZADAS)} (${int(t.SECOES_TOTALIZADAS)} de ${int(t.SECOES_TOTAL)})` +
        ` · totalização ${hora(t.DT_TOTALIZACAO)}${t.TOTALIZACAO_FINAL ? " · FINAL" : ""}${vagas}`)),
    el("div", { class: "progresso", role: "progressbar", "aria-valuenow": t.PCT_SECOES_TOTALIZADAS || 0, "aria-valuemin": 0, "aria-valuemax": 100 },
      el("div", { style: { width: `${t.PCT_SECOES_TOTALIZADAS || 0}%` } })),
    el("h3", {}, `Eleitorado ${int(t.ELEITORADO)}`),
    ...(comp ? composicao([
      { rotulo: "Comparecimento", valor: t.COMPARECIMENTO || 0, cor: cor("--serie-1") },
      { rotulo: "Abstenção", valor: t.ABSTENCAO || 0, cor: cor("--outros") },
    ], comp) : []),
    el("h3", {}, "Votos"),
    ...(votos ? composicao([
      { rotulo: "Válidos", valor: t.VALIDOS || 0, cor: cor("--serie-1") },
      { rotulo: "Brancos", valor: t.BRANCOS || 0, cor: cor("--serie-2") },
      { rotulo: "Nulos", valor: t.NULOS || 0, cor: cor("--serie-3") },
      { rotulo: "Anulados sub judice", valor: t.ANULADOS_SUB_JUDICE || 0, cor: cor("--serie-4") },
    ], votos) : []),
    ...blocoSerie(c.serie, c.proporcional),
    el("h3", {}, c.proporcional ? `Mais votados (${c.candidatos.length} de ${int(c.n_candidatos)})` : "Candidatos"),
    el("div", { class: "lista" }, c.candidatos.map((x, i) => linhaCandidato(i + 1, x, maxPct, c.cargo, ctx))),
  ];
  if (c.partidos && c.partidos.length) {
    const maxP = Math.max(...c.partidos.map((p) => p.PCT_VALIDOS || 0), 0.0001);
    filhos.push(el("h3", {}, "Partidos (nominais + legenda)"),
      el("div", { class: "lista" }, c.partidos.map((p, i) => el("div", { class: "item" },
        el("span", { class: "pos" }, i + 1),
        el("span", { class: "nome" }, p.PARTIDO, p.FEDERACAO ? el("small", {}, ` · ${p.FEDERACAO}`) : null),
        el("span", { class: "barra" }, el("div", { style: { width: `${(100 * (p.PCT_VALIDOS || 0)) / maxP}%` } })),
        el("span", { class: "num" }, int(p.VOTOS_TOTAL)),
        el("span", { class: "sit" }, p.VAGAS_AGREMIACAO ? `${p.VAGAS_AGREMIACAO} vaga(s)` : pct(p.PCT_VALIDOS))))));
  }
  if (c.projecao) filhos.splice(filhos.length - 2, 0, ...blocoProjecao(c.projecao));
  if (c.cadeiras) filhos.push(...blocoCadeiras(c.cadeiras, ctx));
  if (c.cargo === 1 && c.abrangencia === "BRASIL") filhos.push(ctx.blocoBrasil());
  return el("article", { class: "cartao" }, filhos);
}
