/* Bloco "Resultado por município × eleição anterior" da aba Candidato (rodada 37): o mesmo candidato pelo nome civil,
 * em qualquer cargo; homônimo indicado à mão. Endereço: &hist=1[&hist_cargo=&hist_numero=] */
import { tabelaOrdenavel, type Coluna } from "../../componentes/tabela";
import { api } from "../../core/api";
import { el, refs } from "../../core/dom";
import { int } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import { celulaHistorico, descCandidato, fichasHistorico } from "./desenhar";
import type { Historico, LinhaHistorico } from "./tipos";

const CAMPOS = [["hist_cargo", "cargo"], ["hist_numero", "numero"]] as const;

export interface DependenciasHistorico {
  /** Candidato consultado (cargo e nº), ou null. */
  candidato(): { cargo: string; numero: string } | null;
  uf(): string;
  gravar(): void;
}

export function criarHistorico(deps: DependenciasHistorico) {
  const r = refs({ caixa: "#caixa-historico", form: "#form-historico", cargo: "#hist-cargo", numero: "#hist-numero",
    resultado: "#hist-resultado" });
  const caixa = r.caixa as HTMLDetailsElement;
  const campos = { cargo: r.cargo as HTMLSelectElement, numero: r.numero as HTMLInputElement };
  const canal = new Canal();
  let emCurso: string | null = null;
  let mostrado: string | null = null;

  function params(): URLSearchParams | null {
    const c = deps.candidato();
    if (!c) return null;
    const q = new URLSearchParams({ cargo: c.cargo, numero: c.numero });
    const nr = campos.numero.value.trim();
    if (nr) { q.set("numero_ref", nr); if (campos.cargo.value) q.set("cargo_ref", campos.cargo.value); }
    return q;
  }

  async function carregar(): Promise<void> {
    if (!caixa.open) return;
    const q = params();
    if (!q) { r.resultado.replaceChildren(el("p", { class: "nota" }, "Consulte um candidato acima.")); return; }
    const pedido = q.toString();
    if (emCurso === pedido) return;  // o mesmo pedido já está a caminho (a navegação dispara 2×)
    emCurso = pedido;
    const sinal = canal.novo();  // outro candidato pedido enquanto este carregava: só o último desenha
    // recarga do mesmo pedido: o que está na tela fica até chegar o novo (sem piscar "Carregando…")
    if (mostrado !== pedido) r.resultado.replaceChildren(el("p", { class: "nota" }, "Carregando…"));
    let d: Historico;
    try { d = await api(`api/candidato/historico?${q}`, { sinal }); } catch (e) {
      if (cancelado(e)) return;
      emCurso = mostrado = null;
      r.resultado.replaceChildren(el("p", { class: "aviso" }, (e as Error).message));
      return;
    }
    emCurso = null;
    mostrado = pedido;
    const [a, b] = d.sufixos;
    const notas = d.notas.map((n) => el("p", { class: "nota" }, n));
    const opcoes = d.opcoes.length ? el("ul", {}, d.opcoes.map((o) => el("li", {}, `${descCandidato(o)} (${int(o.VOTOS)} votos) `,
      el("button", { type: "button", class: "link", onclick: () => {
        campos.cargo.value = String(o.CARGO);
        campos.numero.value = String(o.NUMERO);
        deps.gravar(); void carregar();
      } }, "usar este")))) : null;
    const salvar = el("a", { class: "botao-salvar", href: `api/candidato/historico/planilha?${q}`, download: "" },
      "Salvar planilha (.xlsx)");
    const cab: Coluna<LinhaHistorico>[] = [["Município", "NM_MUNICIPIO"], [`Votos ${a}`, `VOTOS_${a}`, true],
      [`% válidos ${a}`, `PCT_VALIDOS_${a}`, true], [`Posição ${a}`, `POSICAO_${a}`, true], [`Votos ${b}`, `VOTOS_${b}`, true],
      [`% válidos ${b}`, `PCT_VALIDOS_${b}`, true], [`Posição ${b}`, `POSICAO_${b}`, true],
      ["Variação dos votos", "VAR_VOTOS_PCT", true], ["Variação % válidos", "VAR_PCT_VALIDOS_PP", true],
      ["Seções totalizadas", "PCT_SECOES_TOTALIZADAS", true]];
    const tabela = tabelaOrdenavel(cab, d.linhas.filter((l) => l.ABRANGENCIA === "mun"), (l, k) => celulaHistorico(k, l[k]));
    r.resultado.replaceChildren(...[fichasHistorico(d, deps.uf()), ...notas, opcoes, salvar,
      el("div", { class: "tabela-rolagem" }, tabela)].filter((n): n is HTMLElement => n !== null));
  }

  r.form.addEventListener("submit", (e) => { e.preventDefault(); deps.gravar(); void carregar(); });
  caixa.addEventListener("toggle", () => { deps.gravar(); void carregar(); });

  return {
    carregar,
    /** Outro candidato: a indicação de homônimo era do anterior. */
    esquecerIndicacao(): void { campos.cargo.value = ""; campos.numero.value = ""; },
    escrever(q: URLSearchParams): void {
      if (!caixa.open) return;
      q.set("hist", "1");
      for (const [k, c] of CAMPOS) { const v = campos[c].value.trim(); if (v) q.set(k, v); }
    },
    aplicar(q: URLSearchParams): void {
      for (const [k, c] of CAMPOS) campos[c].value = q.get(k) ?? "";
      const abrir = q.get("hist") === "1";
      if (caixa.open !== abrir) caixa.open = abrir;  // o "toggle" carrega
      else void carregar();
    },
  };
}
