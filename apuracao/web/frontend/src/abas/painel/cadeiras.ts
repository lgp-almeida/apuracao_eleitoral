/* Cadeiras de deputado no painel (apuracao/cadeiras.py, projecao_cadeiras.py): barra por agremiação e lista de
 * eleitos sob demanda; com ≥ 30% apurado, as cadeiras sobre os votos PROJETADOS (faixa e consolidados × disputa). */
import { amostra } from "../../componentes/legenda";
import { api } from "../../core/api";
import { cor, el } from "../../core/dom";
import { fmtFreq, fmtInt, fmtPct, int, pct } from "../../core/formatos";
import { agremiacoesDestacadas, destacado } from "./destaque";
import type { Cadeiras, Eleito } from "./tipos";

export interface ContextoCadeiras {
  destacar: ReadonlySet<string>;
  /** Cargos com a lista aberta: reabre depois do redesenho de 60 s. */
  abertos: Set<number>;
}

const CURTO: Record<string, string> = { "consolidado": "consolidado", "em disputa (dentro)": "disputa, dentro", "em disputa (fora)": "disputa, fora" };

function botaoSalvarLista(cargo: number, destacar: ReadonlySet<string>): HTMLElement {
  const q = new URLSearchParams({ cargo: String(cargo) });
  if (destacar.size) q.set("destacar", [...destacar].join(","));
  return el("a", { class: "botao-salvar", href: `api/cadeiras/planilha?${q}`, download: "" }, "Salvar lista (.xlsx)");
}

/** <details> de uma lista: carrega ao abrir e conta os destacados quando a lista chega. */
function detalhesLista(cargo: number, resumo: string, conteudo: HTMLElement, carregar: () => Promise<number>, c: ContextoCadeiras): HTMLElement {
  const sumario = el("summary", {}, resumo);
  const det = el("details", {
    ontoggle: async (e: Event) => {
      const aberto = (e.target as HTMLDetailsElement).open;
      if (aberto) c.abertos.add(cargo); else c.abertos.delete(cargo);
      if (!aberto || conteudo.childElementCount) return;
      conteudo.textContent = "carregando…";
      try {
        const n = await carregar();
        if (c.destacar.size) sumario.textContent = `${resumo} — ${n} destacado(s)`;
      } catch (err) { conteudo.textContent = `não foi possível carregar: ${(err as Error).message}`; }
    },
  }, sumario, conteudo);
  if (c.abertos.has(cargo)) det.open = true;
  return det;
}

const aviso = (k: Cadeiras) => (k.consistente ? null : el("p", { class: "aviso" }, `Atenção: os votos das agremiações ` +
  `(${int(k.soma_agremiacoes)}) não somam os válidos (${int(k.validos)}); a projeção pode estar incompleta.`));

function cadeirasProjetadas(k: Cadeiras, c: ContextoCadeiras): HTMLElement[] {
  const p = k.projecao;
  if (!p) return [];
  const cFirme = cor("--seq-4"), cFaixa = cor("--seq-2");
  const max = Math.max(...p.agremiacoes.map((a) => a.VAGAS_MAX), 1);
  const agrDest = agremiacoesDestacadas(c.destacar, k);
  const linhas = p.agremiacoes.map((a) => el("div", { class: agrDest.has(a.AGREMIACAO) ? "cad-item destaque" : "cad-item",
    title: `${a.AGREMIACAO}: ${int(a.VOTOS)} votos projetados · ${a.VAGAS} cadeira(s) na projeção; de ${a.VAGAS_MIN} a ${a.VAGAS_MAX} em 90% das simulações` },
  el("span", { class: "nome" }, a.AGREMIACAO),
  el("span", { class: "cad-barra" },
    a.VAGAS_MIN ? el("span", { style: { width: `${(100 * a.VAGAS_MIN) / max}%`, background: cFirme } }) : null,
    a.VAGAS_MAX > a.VAGAS_MIN ? el("span", { style: { width: `${(100 * (a.VAGAS_MAX - a.VAGAS_MIN)) / max}%`, background: cFaixa } }) : null),
  el("span", { class: "num cad-faixa" }, a.VAGAS_MAX > a.VAGAS_MIN ? `${a.VAGAS} (${a.VAGAS_MIN}–${a.VAGAS_MAX})` : String(a.VAGAS))));
  const disputa = p.em_disputa_dentro + p.em_disputa_fora;
  const lista = el("div", { class: "cad-eleitos" });
  const dest = (x: Eleito) => destacado(c.destacar, x);
  const det = detalhesLista(k.cargo, `Ver consolidados e a disputa (${p.consolidados + disputa} candidatos)`, lista, async () => {
    const d = await api<{ projecao: { candidatos: Eleito[] } }>(`api/cadeiras?cargo=${k.cargo}`);
    const classe = (x: Eleito) => [x.STATUS === "consolidado" ? null : "cad-disputa", dest(x) ? "destaque" : null].filter(Boolean).join(" ") || null;
    lista.replaceChildren(el("table", {}, el("thead", {}, el("tr", {}, [["Candidato"], ["Votos proj."],
      ["Situação"], ["Sim.", `% das ${p.simulacoes} simulações em que se elege`]]
      .map(([t, dica], i) => el("th", { class: i === 1 || i === 3 ? "num" : null, title: dica }, t)))),
    el("tbody", {}, d.projecao.candidatos.map((x) => el("tr", { class: classe(x) },
      el("td", {}, `${dest(x) ? "★ " : ""}${x.NUMERO} ${x.NOME}`, el("br"), el("small", {}, `${x.PARTIDO} · ${x.AGREMIACAO}`)),
      el("td", { class: "num" }, int(x.VOTOS_PROJ)),
      el("td", {}, CURTO[x.STATUS ?? ""] || x.STATUS), el("td", { class: "num" }, fmtFreq(x.FREQ_ELEITO ?? 0)))))));
    return d.projecao.candidatos.filter(dest).length;
  }, c);
  return [
    el("h3", {}, `Cadeiras projetadas — ${k.vagas} vagas`),
    el("div", { class: "sub" }, `Projeção com ${pct(p.pct_apurado)} do eleitorado apurado · QE projetado ${int(p.qe)}`),
    el("p", { class: "proj-situacao" }, `${p.consolidados} eleitos consolidados · ${k.vagas - p.consolidados} vagas em disputa ` +
      `entre ${disputa} candidatos`),
    el("div", { class: "legenda-linha" },
      el("span", {}, amostra(cFirme), "Cadeiras firmes (mínimo)"),
      el("span", {}, amostra(cFaixa), "Podem vir (até o máximo)")),
    el("div", { class: "cad-lista", role: "list" }, linhas),
    aviso(k), det, botaoSalvarLista(k.cargo, c.destacar),
    el("p", { class: "nota" }, `Votos projetados por município e ${p.simulacoes} simulações com o erro medido na apuração de 2022. ` +
      `Consolidado = eleito em ≥ ${Math.round(100 * p.limiar)}% das simulações; faixa = 90% das simulações. Em 2022 (RJ), ` +
      "de ~640 consolidados ao longo da apuração só 1 não se elegeu, e as faixas cobriram 481 de 482 casos (calibração e teste " +
      "na mesma eleição)."),
  ].filter((n): n is HTMLElement => n !== null);
}

/** Cadeiras (deputados): barra empilhada QP + média por agremiação, eleitos sob demanda. */
export function blocoCadeiras(k: Cadeiras, c: ContextoCadeiras): HTMLElement[] {
  if (k.projecao && k.projecao.ativa) return cadeirasProjetadas(k, c);
  const cQp = cor("--serie-1"), cMedia = cor("--seq-2");
  const max = Math.max(...k.agremiacoes.map((a) => a.VAGAS), 1);
  const estagio = k.final ? "resultado final" : `projeção com ${pct(k.pct_secoes)} das seções — muda até o fim da apuração`;
  const confere = k.conferencia_tse ? ` · confere com o TSE: ${k.conferencia_tse.coincidentes} de ${k.conferencia_tse.eleitos_tse} eleitos` : "";
  const agrDest = agremiacoesDestacadas(c.destacar, k);
  const linhas = k.agremiacoes.map((a) => el("div", { class: agrDest.has(a.AGREMIACAO) ? "cad-item destaque" : "cad-item",
    title: `${a.NOME}: ${int(a.VOTOS)} votos (${fmtPct.format(a.PCT_QE)}% do QE) · ${a.VAGAS_QP} por QP + ${a.VAGAS_MEDIA} por média` },
  el("span", { class: "nome" }, a.NOME),
  el("span", { class: "cad-barra" },
    a.VAGAS_QP ? el("span", { style: { width: `${(100 * a.VAGAS_QP) / max}%`, background: cQp } }) : null,
    a.VAGAS_MEDIA ? el("span", { style: { width: `${(100 * a.VAGAS_MEDIA) / max}%`, background: cMedia } }) : null),
  el("span", { class: "num" }, String(a.VAGAS))));
  const eleitos = el("div", { class: "cad-eleitos" });
  const dest = (x: Eleito) => destacado(c.destacar, x);
  const det = detalhesLista(k.cargo, `Ver os ${k.vagas} eleitos projetados`, eleitos, async () => {
    const d = await api<{ eleitos: Eleito[] }>(`api/cadeiras?cargo=${k.cargo}`);
    const cab = [["Eleito"], ["Partido", "a federação aparece abaixo do partido"], ["Votos"],
      ["Via", "QP = quociente partidário; média = sobras"], ["Folga", "votos à frente do 1º suplente da mesma agremiação"]];
    eleitos.replaceChildren(el("table", {}, el("thead", {}, el("tr", {}, cab
      .map(([t, dica], i) => el("th", { class: i === 2 || i === 4 ? "num" : null, title: dica }, t)))),
    el("tbody", {}, d.eleitos.map((x) => el("tr", { class: dest(x) ? "destaque" : null },
      el("td", {}, `${dest(x) ? "★ " : ""}${x.NUMERO} ${x.NOME}`),
      el("td", {}, x.PARTIDO, x.AGREMIACAO !== x.PARTIDO ? [el("br"), el("small", {}, x.AGREMIACAO)] : null),
      el("td", { class: "num" }, int(x.VOTOS)), el("td", {}, x.SITUACAO_PROJETADA === "Eleito por QP" ? "QP" : "média"),
      el("td", { class: "num" }, x.MARGEM === null ? "—" : int(x.MARGEM)))))));
    return d.eleitos.filter(dest).length;
  }, c);
  return [
    el("h3", {}, `Cadeiras projetadas — ${k.vagas} vagas`),
    el("div", { class: "sub" }, `QE ${int(k.qe)} · ${k.eleitos_qp} por QP + ${k.eleitos_media} por média · ${estagio}${confere}`),
    el("div", { class: "legenda-linha" }, el("span", {}, amostra(cQp), "Quociente partidário (QP)"),
      el("span", {}, amostra(cMedia), "Sobras (maior média)")),
    el("div", { class: "cad-lista", role: "list" }, linhas),
    k.vagas_nao_preenchidas ? el("p", { class: "nota" }, `${k.vagas_nao_preenchidas} vaga(s) sem candidato apto na projeção.`) : null,
    aviso(k), det, botaoSalvarLista(k.cargo, c.destacar),
    k.projecao ? el("p", { class: "nota" }, `Distribuição sobre os votos PARCIAIS; a projeção de cadeiras começa com ` +
      `${fmtInt.format(k.projecao.pct_minimo)}% do eleitorado apurado (agora ${pct(k.projecao.pct_apurado)}).`) : null,
    el("p", { class: "nota" }, `Regra de 2026 (QE, QP com 10% do QE por candidato, sobras em 2 fases — art. 12-A). Fonte: ${k.fonte}.`),
  ].filter((n): n is HTMLElement => n !== null);
}
