/* Candidato: fichas da consulta, texto da cadeira e o resultado × eleição anterior. */
import { ficha } from "../../componentes/tabela";
import { STATUS_CAD } from "../../core/cadeiras";
import { el } from "../../core/dom";
import { fmtFreq, fmtVariacao, int, pct } from "../../core/formatos";
import type { Cadeira, CandidatoHistorico, ConsultaCandidato, Historico, LinhaHistorico } from "./tipos";

/** Situação da cadeira em uma linha: projeção, eleito (com folga), suplente (com o que falta) ou voto não válido. */
export function textoCadeira(k: Cadeira): string {
  if (k.projecao) {
    const pr = k.projecao;
    return `${STATUS_CAD[pr.status] || "Fora da disputa"} · eleito em ${fmtFreq(pr.freq)} das simulações · ` +
      `${int(pr.votos_proj)} votos projetados (${pct(pr.pct_apurado)} apurado)`;
  }
  if (k.situacao.startsWith("Eleito")) {
    return `${k.situacao}${k.margem !== null ? ` · ${int(k.margem)} votos à frente do 1º suplente de ${k.agremiacao}` : ""}`;
  }
  if (k.situacao === "Suplente") {
    return k.margem !== null
      ? `Suplente (${k.ordem}º de ${k.agremiacao}) · faltam ${int(k.margem)} votos para passar o último eleito da agremiação`
      : `Suplente · ${k.agremiacao} sem cadeira na projeção`;
  }
  return `${k.situacao} (votos não válidos para a vaga)`;
}

export function fichasCandidato(d: ConsultaCandidato, uf: string): HTMLElement {
  const c = d.candidato;
  return el("div", { class: "fichas" },
    ficha("Candidato", `${c.NUMERO} — ${c.NOME_URNA}`), ficha("Partido", `${c.PARTIDO}${c.FEDERACAO ? " · " + c.FEDERACAO : ""}`),
    ficha(`Votos (${uf})`, int(c.VOTOS)), ficha("% dos válidos", pct(c.PCT_VALIDOS)),
    ficha("Posição", `${d.posicao_uf}º de ${int(d.n_candidatos_uf)}`), ficha("Situação", c.SITUACAO || "—"),
    c.DESTINACAO && c.DESTINACAO !== "Válido" ? ficha("Destinação dos votos", c.DESTINACAO) : null,
    d.brasil ? ficha("Votos (Brasil)", `${int(d.brasil.VOTOS)} · ${pct(d.brasil.PCT_VALIDOS)}`) : null,
    c.VICES ? ficha("Vice / suplentes", c.VICES) : null,
    d.cadeira ? ficha("Projeção de cadeira", textoCadeira(d.cadeira)) : null);
}

/** Como o histórico identificou o candidato na eleição de referência. */
export const CRITERIO_HIST: Readonly<Record<string, string>> = {
  "nome completo": "mesmo nome civil completo", "indicado": "indicado à mão",
  "ambíguo": "há homônimos — escolha abaixo", "não concorreu": "não encontrado pelo nome completo",
  "sem referência": "site sem eleição de referência (--comparar-com)",
};

export const descCandidato = (c: CandidatoHistorico): string =>
  `${c.NUMERO} — ${c.NOME_URNA} · ${c.PARTIDO}${c.FEDERACAO ? " · " + c.FEDERACAO : ""} · ${c.DS_CARGO || c.CARGO}`;

export function fichasHistorico(d: Historico, uf: string): HTMLElement {
  const anoRef = d.ano_ref ?? "anterior";
  const total = d.linhas.find((r) => r.ABRANGENCIA === "uf") || ({} as LinhaHistorico);
  const at = d.atual, an = d.anterior;
  return el("div", { class: "fichas" },
    ficha(`Em ${d.ano}`, descCandidato(at)), ficha(`Votos ${d.ano} (${uf})`, `${int(at.VOTOS)} · ${pct(at.PCT_VALIDOS)}`),
    ficha(`Em ${anoRef}`, an ? descCandidato(an) : "—"),
    an ? ficha(`Votos ${anoRef} (${uf})`, `${int(an.VOTOS)} · ${pct(an.PCT_VALIDOS)} · ${an.SITUACAO || "—"}`) : null,
    an ? ficha("Variação no estado", `${fmtVariacao(total.VAR_VOTOS_PCT as number, "var_pct")} votos · ` +
      `${fmtVariacao(total.VAR_PCT_VALIDOS_PP as number, "pp")}`) : null,
    ficha("Identificação", CRITERIO_HIST[d.criterio] || d.criterio));
}

/** Célula da tabela por município × eleição anterior. */
export function celulaHistorico(k: string, x: string | number | null | undefined): string {
  if (k === "VAR_VOTOS_PCT") return fmtVariacao(x as number, "var_pct");
  if (k === "VAR_PCT_VALIDOS_PP") return fmtVariacao(x as number, "pp");
  if (k.startsWith("VOTOS_")) return int(x as number);
  if (k.startsWith("POSICAO_")) return x === null || x === undefined ? "—" : `${x}º`;
  if (k.startsWith("PCT")) return pct(x as number);
  return String(x ?? "");
}
