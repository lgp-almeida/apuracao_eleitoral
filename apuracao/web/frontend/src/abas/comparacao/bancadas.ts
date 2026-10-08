/* Bloco "Bancadas × eleição anterior" da aba Comparação (TODO 15, rodada 45). Endereço: &banc=1&banc_cargo=7 */
import { ficha, tabelaOrdenavel } from "../../componentes/tabela";
import { api } from "../../core/api";
import { el, refs } from "../../core/dom";
import { int } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import type { Bancadas } from "./tipos";

const CARGOS = ["6", "7", "8"];
type Linha = Record<string, string | number | null>;
const texto = (x: Linha, k: string) => String(x[k] ?? "—");

export function desenharBancadas(d: Bancadas, cargo: string): HTMLElement[] {
  const r = d.resumo, a = d.ano, b = d.ano_ref;
  const fichas = el("div", { class: "fichas" },
    ficha(`Eleitos ${b} → ${a}`, `${int(r.eleitos_antes)} → ${int(r.eleitos_agora)}`),
    ficha("Reeleitos", int(r.reeleito)), ficha("Novatos", int(r.novato)),
    ficha("Já tinham concorrido", int(r["já concorreu, sem se eleger"])),
    ficha("Eleitos antes para outro cargo", int(r["eleito antes para outro cargo"])),
    ficha(`Eleitos em ${b} que saíram`, int(r.nao_reeleitos)));
  const sinal = (x: number) => (x > 0 ? `+${x}` : String(x));
  const tPart = tabelaOrdenavel<Linha>([["Partido", "PARTIDO"], [`Em ${b} como`, "ANTES_COMO"], [`Eleitos ${b}`, "ELEITOS_ANTES", true],
    [`Eleitos ${a}`, "ELEITOS_AGORA", true], ["Variação", "VARIACAO", true]], d.partidos,
  (x, k) => (k === "VARIACAO" ? sinal(Number(x[k])) : texto(x, k)));
  const tEl = tabelaOrdenavel<Linha>([["Eleito", "NOME_URNA"], ["Partido", "PARTIDO"], ["Votos", "VOTOS", true],
    ["Trajetória", "TRAJETORIA"], ["Detalhe", "DETALHE"]], d.eleitos, (x, k) => (k === "VOTOS" ? int(x[k] as number) : texto(x, k)));
  const tSa = tabelaOrdenavel<Linha>([[`Eleito em ${b}`, "NOME_URNA"], ["Partido", "PARTIDO_ANTES"], [`Votos ${b}`, "VOTOS_ANTES", true],
    [`Em ${a}`, "DESTINO"]], d.sairam, (x, k) => (k === "VOTOS_ANTES" ? int(x[k] as number) : texto(x, k)));
  return [fichas,
    el("a", { class: "botao-salvar", href: `api/bancadas/planilha?cargo=${cargo}`, download: "" }, "Salvar planilha (.xlsx)"),
    el("h3", { class: "sub" }, `Por partido — ${d.ds_cargo}`), el("div", { class: "tabela-rolagem" }, tPart),
    el("h3", { class: "sub" }, `Eleitos em ${a}`), el("div", { class: "tabela-rolagem" }, tEl),
    el("h3", { class: "sub" }, `Eleitos em ${b} que não voltaram ao cargo`), el("div", { class: "tabela-rolagem" }, tSa)];
}

/** @param gravar regrava o endereço da aba (abrir/fechar e o cargo vão para ele) */
export function criarBancadas(gravar: () => void) {
  const r = refs({ caixa: "#comp-bancadas", cargo: "#banc-cargo", resultado: "#banc-resultado" });
  const caixa = r.caixa as HTMLDetailsElement, cargo = r.cargo as HTMLSelectElement;
  const canal = new Canal();

  async function desenhar(): Promise<void> {
    if (!caixa.open) return;
    const c = cargo.value;
    const sinal = canal.novo();
    r.resultado.replaceChildren(el("p", { class: "nota" }, "Carregando…"));
    let d: Bancadas;
    try { d = await api(`api/bancadas?cargo=${c}`, { sinal }); } catch (e) {
      if (!cancelado(e)) r.resultado.replaceChildren(el("p", { class: "aviso" }, (e as Error).message));
      return;
    }
    r.resultado.replaceChildren(...desenharBancadas(d, c));
  }

  caixa.addEventListener("toggle", () => { gravar(); void desenhar(); });
  cargo.addEventListener("change", () => { gravar(); void desenhar(); });

  return {
    escrever(q: URLSearchParams): void {
      if (!caixa.open) return;
      q.set("banc", "1");
      q.set("banc_cargo", cargo.value);
    },
    aplicar(q: URLSearchParams): void {
      const c = q.get("banc_cargo");
      if (c && CARGOS.includes(c)) cargo.value = c;
      const abrir = q.get("banc") === "1";
      if (caixa.open !== abrir) caixa.open = abrir;  // o "toggle" desenha
      else if (abrir) void desenhar();
    },
  };
}
