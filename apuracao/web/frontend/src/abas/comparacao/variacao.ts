/* Bloco "Variação por partido" da aba Comparação: dispersão A × B por município (diagonal = sem mudança),
 * distribuição da variação e estatística (apuracao/comparacao.py: variacao_partidos).
 * Endereço: &var=1&var_partidos=PT,PL[&var_ponderar=1] (só na comparação por município) */
import { graficoSwing, graficoVariacao } from "../../componentes/grafico/variacao";
import { ficha, tabelaOrdenavel, type Coluna } from "../../componentes/tabela";
import { api } from "../../core/api";
import { cor, el, refs } from "../../core/dom";
import { fmtNum, fmtP, fmtVariacao, pct } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import { escolhaInicial, MAX_VAR, rotuloEntidade } from "./formatos";
import type { PartidoEntidade, Variacao } from "./tipos";

const CORES_VAR = ["--serie-1", "--serie-2", "--serie-3"];  // ordem fixa da escolha (dataviz)
const pp = (v: number | null | undefined) => fmtVariacao(v, "pp");
type Linha = Record<string, string | number | null>;

/** Tabela por município: A, B e variação de cada partido (+ Butler). */
export function linhasPorMunicipio(d: Variacao): Linha[] {
  const linhas: Record<string, Linha> = {};
  d.partidos.forEach((p) => p.pontos.forEach((r) => {
    const l = (linhas[r.CD_MUNICIPIO] ||= { NM_MUNICIPIO: r.NM_MUNICIPIO });
    Object.assign(l, { [`${p.partido}_A`]: r.A, [`${p.partido}_B`]: r.B, [`${p.partido}_DIF`]: r.DIF });
  }));
  d.butler?.pontos.forEach((r) => { if (linhas[r.CD_MUNICIPIO]) linhas[r.CD_MUNICIPIO].BUTLER = r.VALOR; });
  return Object.values(linhas);
}

export function desenharVariacao(d: Variacao): HTMLElement[] {
  const series = d.partidos.map((p, i) => ({ ...p, cor: cor(CORES_VAR[i]) }));
  const fichas = el("div", { class: "fichas" }, ...series.flatMap((p) => [
    ficha(`${p.partido} no estado`, p.uf ? `${pct(p.uf.A)} → ${pct(p.uf.B)} (${pp(p.uf.DIF)})` : "—"),
    ficha(`${p.partido}: variação média por município${d.ponderado ? " (ponderada)" : ""}`,
      `${pp(p.media)} · IC 95% ${pp(p.ic_media[0])} a ${pp(p.ic_media[1])} · DP ${fmtNum(p.dp)}`),
    ficha(`${p.partido}: inclinação b (${d.ano_b} = a + b·${d.ano_a})`, p.reta.b === null ? "—"
      : `${fmtNum(p.reta.b, 3)}${p.reta.ic_b ? ` · IC 95% ${fmtNum(p.reta.ic_b[0], 3)} a ${fmtNum(p.reta.ic_b[1], 3)}` : ""}` +
        ` · p(b = 1) ${fmtP(p.reta.p_b1)} · r ${fmtNum(p.reta.pearson, 3)}`),
  ]), d.butler ? ficha(`Swing de Butler ${d.butler.de} → ${d.butler.para}`,
    `estado ${pp(d.butler.uf)} · média por município ${pp(d.butler.media)} ` +
    `(IC 95% ${pp(d.butler.ic_media[0])} a ${pp(d.butler.ic_media[1])})`) : null);
  const leituras = series.map((p) => el("p", { class: "nota var-leitura" }, el("strong", {}, `${p.partido}: `), p.leitura));
  const cab: Coluna<Linha>[] = [["Município", "NM_MUNICIPIO"], ...series.flatMap((p): Coluna<Linha>[] => [
    [`${p.partido} ${d.ano_a}`, `${p.partido}_A`, true], [`${p.partido} ${d.ano_b}`, `${p.partido}_B`, true],
    [`${p.partido} variação`, `${p.partido}_DIF`, true]])];
  if (d.butler) cab.push([`Butler ${d.butler.de} → ${d.butler.para}`, "BUTLER", true]);
  const tabela = tabelaOrdenavel(cab, linhasPorMunicipio(d), (r, k) =>
    k === "NM_MUNICIPIO" ? String(r[k]) : k.endsWith("_DIF") || k === "BUTLER" ? pp(r[k] as number) : pct(r[k] as number));
  return [fichas, ...leituras,
    el("h3", { class: "sub" }, `% dos válidos em ${d.ano_a} × ${d.ano_b} por município`), graficoVariacao(d, series, pp),
    el("h3", { class: "sub" }, `Variação por município (p.p.) — média e intervalo de 95%`), graficoSwing(d, series, pp),
    el("h3", { class: "sub" }, "Tabela"), el("div", { class: "tabela-rolagem" }, tabela)];
}

export interface DependenciasVariacao {
  cargo(): string;
  anos(): [number, number];
  /** Comparação por bairro: o bloco some. */
  porBairro(): boolean;
  gravar(): void;
}

export function criarVariacao(deps: DependenciasVariacao) {
  const r = refs({ caixa: "#comp-variacao", form: "#form-var", partidos: "#var-partidos", ponderar: "#var-ponderar",
    resultado: "#var-resultado" });
  const caixa = r.caixa as HTMLDetailsElement, ponderar = r.ponderar as HTMLInputElement;
  const canal = new Canal();
  /** Partidos na ordem da escolha (o 1º e o 2º definem o sentido do swing de Butler), não na da lista. */
  let ordem: string[] = [];
  let cargoDaLista: string | null = null;
  /** Escolha pedida pelo endereço, aplicada na próxima montagem da lista. */
  let pedida: string[] | null = null;
  let emCurso: string | null = null;
  let mostrado: string | null = null;

  const caixas = () => [...r.partidos.querySelectorAll<HTMLInputElement>("input")];

  function partidos(): string[] {
    const marcados = new Set(caixas().filter((i) => i.checked).map((i) => i.value));
    ordem = ordem.filter((p) => marcados.has(p));
    for (const p of marcados) if (!ordem.includes(p)) ordem.push(p);
    return [...ordem];
  }

  function limitar(): void {
    const n = partidos().length;
    caixas().forEach((i) => { i.disabled = !i.checked && n >= MAX_VAR; });
  }

  async function preparar(): Promise<void> {
    const cargo = deps.cargo();
    let ps: PartidoEntidade[];
    try { ps = await api(`api/comparacao/partidos?cargo=${cargo}`); } catch (e) {
      r.partidos.replaceChildren(el("span", { class: "nota" }, (e as Error).message)); return;
    }
    const marcados = new Set(escolhaInicial(ps, cargo, pedida, cargoDaLista === cargo ? partidos() : null));
    pedida = null;
    cargoDaLista = cargo;
    ordem = [...marcados];
    const [a, b] = deps.anos();
    r.partidos.replaceChildren(...ps.map((x) => el("label", {}, el("input", { type: "checkbox", value: x.PARTIDO,
      checked: marcados.has(String(x.PARTIDO)), onchange: () => { limitar(); deps.gravar(); } }),
    rotuloEntidade(x, a, b))));
    limitar();
  }

  async function desenhar(): Promise<void> {
    if (!caixa.open || deps.porBairro()) return;
    const ps = partidos();
    if (!ps.length) { r.resultado.replaceChildren(el("p", { class: "nota" }, "Escolha de 1 a 3 partidos.")); return; }
    const q = new URLSearchParams({ cargo: deps.cargo(), partidos: ps.join(",") });
    if (ponderar.checked) q.set("ponderar", "true");
    const pedido = q.toString();
    if (emCurso === pedido) return;  // o mesmo pedido já está a caminho (a navegação dispara 2×)
    emCurso = pedido;
    const sinal = canal.novo();
    if (mostrado !== pedido) r.resultado.replaceChildren(el("p", { class: "nota" }, "Calculando…"));
    let d: Variacao;
    try { d = await api(`api/comparacao/variacao?${q}`, { sinal }); } catch (e) {
      if (cancelado(e)) return;
      emCurso = mostrado = null;
      r.resultado.replaceChildren(el("p", { class: "aviso" }, (e as Error).message));
      return;
    }
    emCurso = null;
    mostrado = pedido;
    r.resultado.replaceChildren(...desenharVariacao(d));
  }

  caixa.addEventListener("toggle", async () => {
    if (caixa.open) await preparar();
    deps.gravar();
    if (caixa.open) void desenhar();
  });
  r.form.addEventListener("submit", (e) => { e.preventDefault(); deps.gravar(); void desenhar(); });
  ponderar.addEventListener("change", () => { deps.gravar(); void desenhar(); });

  return {
    partidos,
    /** Cargo ou detalhe mudou: o bloco some na comparação por bairro; aberto, refaz a lista e o gráfico. */
    ajustar(): void {
      const bairro = deps.porBairro();
      caixa.hidden = bairro;
      if (caixa.open && !bairro) void preparar().then(() => { deps.gravar(); void desenhar(); });
    },
    escrever(q: URLSearchParams): void {
      if (!caixa.open || deps.porBairro()) return;
      q.set("var", "1");
      const ps = partidos();
      if (ps.length) q.set("var_partidos", ps.join(","));
      if (ponderar.checked) q.set("var_ponderar", "1");
    },
    async aplicar(q: URLSearchParams): Promise<void> {
      ponderar.checked = q.get("var_ponderar") === "1";
      const abrir = q.get("var") === "1" && !deps.porBairro();
      const lista = q.get("var_partidos");
      pedida = abrir && lista ? lista.split(",").slice(0, MAX_VAR) : null;
      if (caixa.open !== abrir) caixa.open = abrir;  // o "toggle" prepara e desenha
      else if (abrir) { await preparar(); await desenhar(); }
    },
  };
}
