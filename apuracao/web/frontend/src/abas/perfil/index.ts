/* Aba "Perfil × voto": correlação ECOLÓGICA (unidades, não pessoas) entre o voto num candidato/partido e o perfil
 * do eleitorado (TSE) ou dos moradores (Censo 2022), por bairro, local de votação ou área de ponderação.
 * Endereço: #perfil?ano=&turno=&cargo=&numero=|partido=&x=<indicador>|voto[&x_ano=&x_turno=&x_cargo=&x_numero=|x_partido=]
 *           [&municipio=<IBGE>]&min_validos=[&ponderar=true][&unidade=local|area][&reg=…] */
import { graficoDispersao } from "../../componentes/grafico/dispersao";
import { copiarLink } from "../../componentes/link";
import type { Contexto, ModuloAba } from "../../core/aba";
import { api } from "../../core/api";
import { el, ref } from "../../core/dom";
import { int } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import { desenharRegressao, fichasCorrelacao, tabelaCorrelacoes, tabelaResiduos } from "./desenhar";
import { ehUnidade, fmtX, nomeDaUnidade, REG_PADRAO } from "./formatos";
import type { CandidatoPerfil, Correlacao, Dispersao, InfoPerfil, PartidoPerfil, Regressao, Unidade } from "./tipos";

/** Lado da análise: "" = voto analisado (eixo Y); "x-" = voto em outra eleição no eixo X. */
type Lado = "" | "x-";
type Campo = HTMLInputElement & HTMLSelectElement;

/** Todos os ids "pf-…" que a aba usa (conferidos na montagem). */
const IDS = ["ano", "turno", "cargo", "tipo", "l-numero", "numero", "lista", "l-partido", "partido", "x", "x-ano",
  "x-turno", "x-cargo", "x-tipo", "l-x-numero", "x-numero", "x-lista", "l-x-partido", "x-partido", "unidade",
  "municipio", "min", "ponderar", "nota-area", "copiar", "copiar-msg", "msg", "fichas", "titulo-grafico", "grafico",
  "correlacoes", "acima", "abaixo", "reg-ind", "reg-btn", "reg-fichas", "reg"] as const;

export interface EstadoPerfil {
  /** Info da unidade atual e o cache por unidade. */
  info: InfoPerfil | null;
  infos: Partial<Record<Unidade, InfoPerfil>>;
  /** Listas de candidatos/partidos por ano, cargo, turno, município e unidade. */
  listas: Record<string, (CandidatoPerfil | PartidoPerfil)[]>;
  /** Indicadores marcados para a regressão (null = padrão). */
  reg: string[] | null;
  dados: Dispersao | null;
  /** A aba já abriu (pelo botão ou pelo endereço): nada de análise padrão por cima. */
  feito: boolean;
}

export function criarAbaPerfil(ctx: Contexto): ModuloAba & { estado: EstadoPerfil } {
  const estado: EstadoPerfil = { info: null, infos: {}, listas: {}, reg: null, dados: null, feito: false };
  const canal = new Canal();
  const cache = new Map<string, Campo>();
  for (const id of IDS) cache.set(id, ref<Campo>(`#pf-${id}`));
  const pf = (id: string): Campo => {
    const c = cache.get(id);
    if (!c) throw new Error(`campo desconhecido: pf-${id}`);
    return c;
  };
  const unidade = (): Unidade => { const u = pf("unidade").value; return ehUnidade(u) ? u : "bairro"; };
  const estadoInteiro = () => unidade() !== "bairro";
  const nome = (plural = true, maiuscula = false) => nomeDaUnidade(unidade(), plural, maiuscula);
  const mostrarX = (sim: boolean) => document.querySelectorAll<HTMLElement>(".pf-xv").forEach((e) => { e.hidden = !sim; });

  /** Info da unidade escolhida: municípios e indicadores mudam com ela. */
  async function carregarInfo(): Promise<InfoPerfil> {
    const u = unidade();
    const info = (estado.infos[u] ??= await api<InfoPerfil>(`api/perfil/info?unidade=${u}`));
    estado.info = info;
    pf("nota-area").hidden = u !== "area";
    const xAtual = pf("x").value, munAtual = pf("municipio").value;
    const grupos: Record<string, HTMLOptionElement[]> = {};
    for (const [k, i] of Object.entries(info.indicadores)) (grupos[i.fonte] ||= []).push(el("option", { value: k }, i.rotulo));
    pf("x").replaceChildren(...Object.entries(grupos).map(([f, ops]) => el("optgroup", { label: f }, ops)),
      el("optgroup", { label: "Outra eleição" }, el("option", { value: "voto" }, "Voto em outra eleição (transferência)")));
    if ([...pf("x").options].some((o) => o.value === xAtual)) pf("x").value = xAtual;
    pf("municipio").replaceChildren(el("option", { value: "" }, estadoInteiro() ? "Estado inteiro" : "Todos com bairros"),
      ...info.municipios.map((m) => el("option", { value: m.CD_MUN }, `${m.NM_MUN} (${m.BAIRROS} ${nome()})`)));
    if ([...pf("municipio").options].some((o) => o.value === munAtual)) pf("municipio").value = munAtual;
    const marcados = new Set(estado.reg || REG_PADRAO);
    pf("reg-ind").replaceChildren(...Object.entries(info.indicadores).map(([k, i]) => el("label", { class: "check" },
      el("input", { type: "checkbox", value: k, checked: marcados.has(k) || null }), ` ${i.rotulo}`)));
    return info;
  }

  async function iniciar(): Promise<void> {
    if (estado.info && estado.info.unidade === pf("unidade").value) return;
    const primeira = !estado.info;
    const info = await carregarInfo();
    if (!primeira) return;
    const anos = Object.keys(info.anos).sort((a, b) => Number(b) - Number(a));
    for (const sel of [pf("ano"), pf("x-ano")]) sel.replaceChildren(...anos.map((a) => el("option", { value: a }, a)));
    // padrão: a eleição mais recente com governador (2022), senão a mais recente
    const comGov = anos.find((a) => info.anos[a].includes(3));
    pf("ano").value = comGov ?? anos[0] ?? "";
    pf("x-ano").value = anos.find((a) => a !== pf("ano").value) ?? pf("ano").value;
    pf("x").value = "pct_superior";
  }

  function cargos(sel: Campo, ano: string, preferido: string | null = null): void {
    const info = estado.info;
    if (!info) return;
    const cs = info.anos[ano] || [];
    const alvo = String(preferido ?? sel.value);
    sel.replaceChildren(...cs.map((c) => el("option", { value: c }, info.cargos[c])));
    if (cs.map(String).includes(alvo)) sel.value = alvo;
    else if (cs.includes(3)) sel.value = "3";
  }

  const chaveLista = (tipo: string, ano: string, cargo: string, turno: string, mun: string) =>
    `${tipo}/${ano}/${cargo}/${turno}/${mun}/${pf("unidade").value}`;

  async function lista<T extends CandidatoPerfil | PartidoPerfil>(tipo: "candidatos" | "partidos", ano: string,
      cargo: string, turno: string): Promise<T[]> {
    const mun = tipo === "candidatos" ? pf("municipio").value : "";  // nº municipal muda de pessoa a cada município
    const chave = chaveLista(tipo, ano, cargo, turno, mun);
    if (!estado.listas[chave]) {
      try {
        estado.listas[chave] = await api(`api/perfil/${tipo}?ano=${ano}&cargo=${cargo}&turno=${turno}&unidade=${pf("unidade").value}` +
          (mun ? `&municipio=${mun}` : ""));
      } catch { estado.listas[chave] = []; }  // ex.: turno sem votos para o cargo
    }
    return estado.listas[chave] as T[];
  }

  /** Lista de candidatos (datalist) ou de partidos de um lado. */
  async function preencherAlvo(p: Lado): Promise<void> {
    const ano = pf(`${p}ano`).value, cargo = pf(`${p}cargo`).value, turno = pf(`${p}turno`).value;
    const partido = pf(`${p}tipo`).value === "partido";
    const ladoXOculto = Boolean(p) && pf("x").value !== "voto";
    pf(`l-${p}numero`).hidden = partido || ladoXOculto;
    pf(`l-${p}partido`).hidden = !partido || ladoXOculto;
    if (!ano || !cargo) return;
    if (partido) {
      const ps = await lista<PartidoPerfil>("partidos", ano, cargo, turno);
      const sel = pf(`${p}partido`);
      const atual = sel.value, siglaAtual = sel.selectedOptions[0]?.dataset.sigla;
      sel.replaceChildren(...ps.map((x) => el("option", { value: x.PARTIDO, "data-sigla": x.SIGLA ?? "" },
        `${x.PARTIDO}${x.SIGLA ? " " + x.SIGLA : ""} — ${int(x.VOTOS)} votos`)));
      // mantém a escolha ao trocar de ano só se for o MESMO partido: o nº é reaproveitado (14 = PTB em 2022,
      // MISSÃO em 2026); escolha vinda do endereço (sem sigla anterior) vale pelo nº
      if (ps.some((x) => String(x.PARTIDO) === atual && (siglaAtual === undefined || (x.SIGLA ?? "") === siglaAtual))) {
        sel.value = atual;
      }
    } else {
      const cs = await lista<CandidatoPerfil>("candidatos", ano, cargo, turno);
      pf(`${p}lista`).replaceChildren(...cs.map((c) => el("option", { value: String(c.NUMERO) }, c.NOME)));
      if (!pf(`${p}numero`).value && cs.length) pf(`${p}numero`).value = String(cs[0].NUMERO);
    }
  }

  /** Nº do candidato do lado: o digitado, ou o 1º da lista cujo nome contém o texto. */
  function numero(p: Lado): string {
    const t = pf(`${p}numero`).value.trim();
    if (/^\d+$/.test(t)) return t;
    const l = (estado.listas[chaveLista("candidatos", pf(`${p}ano`).value, pf(`${p}cargo`).value, pf(`${p}turno`).value,
      pf("municipio").value)] || []) as CandidatoPerfil[];
    const alvo = t.toUpperCase();
    const achado = alvo ? l.find((c) => (c.NOME || "").toUpperCase().includes(alvo)) : undefined;
    if (achado) { pf(`${p}numero`).value = String(achado.NUMERO); return String(achado.NUMERO); }
    return "";
  }

  async function ajustar(lado: "x" | "y" | null = null): Promise<void> {
    const xVoto = pf("x").value === "voto";
    mostrarX(xVoto);
    if (lado !== "x") { cargos(pf("cargo"), pf("ano").value); await preencherAlvo(""); }
    if (xVoto && lado !== "y") { cargos(pf("x-cargo"), pf("x-ano").value); await preencherAlvo("x-"); }
  }

  function escrever(): URLSearchParams {
    const q = new URLSearchParams({ ano: pf("ano").value, turno: pf("turno").value, cargo: pf("cargo").value });
    if (pf("tipo").value === "partido") q.set("partido", pf("partido").value);
    else q.set("numero", numero(""));
    q.set("x", pf("x").value);
    if (pf("x").value === "voto") {
      q.set("x_ano", pf("x-ano").value); q.set("x_turno", pf("x-turno").value); q.set("x_cargo", pf("x-cargo").value);
      if (pf("x-tipo").value === "partido") q.set("x_partido", pf("x-partido").value);
      else q.set("x_numero", numero("x-"));
    }
    if (estadoInteiro()) q.set("unidade", unidade());
    if (pf("municipio").value) q.set("municipio", pf("municipio").value);
    q.set("min_validos", pf("min").value || "0");
    if (pf("ponderar").checked) q.set("ponderar", "true");
    const reg = estado.reg || REG_PADRAO;
    if (reg.join(",") !== REG_PADRAO.join(",")) q.set("reg", reg.join(","));
    return q;
  }

  async function analisar(): Promise<void> {
    const msg = pf("msg");
    const limpar = () => ["fichas", "grafico", "correlacoes", "acima", "abaixo", "reg", "reg-fichas"].forEach((k) => pf(k).replaceChildren());
    ctx.gravarEndereco("perfil");
    const params = escrever();
    if (!params.get("numero") && !params.get("partido")) { limpar(); msg.textContent = "Escolha o candidato ou o partido."; return; }
    if (params.get("x") === "voto" && !params.get("x_numero") && !params.get("x_partido")) {
      limpar(); msg.textContent = "Escolha o candidato ou o partido da outra eleição (eixo X)."; return;
    }
    msg.textContent = "calculando… (a 1ª vez de um ano baixa o perfil do eleitorado do TSE)";
    const base = new URLSearchParams(params);
    for (const k of [...base.keys()]) if (k === "x" || k === "reg" || k.startsWith("x_")) base.delete(k);
    const reg = estado.reg || REG_PADRAO;
    const sinal = canal.novo();  // só a análise mais recente desenha (cliques rápidos não se atropelam)
    let d: Dispersao, c: { correlacoes: Correlacao[] }, rg: Regressao | { erro: string } | null;
    try {
      [d, c, rg] = await Promise.all([
        api<Dispersao>(`api/perfil/dispersao?${params}`, { sinal }),
        api<{ correlacoes: Correlacao[] }>(`api/perfil/correlacoes?${base}`, { sinal }),
        reg.length ? api<Regressao>(`api/perfil/regressao?${base}&indicadores=${reg.join(",")}`, { sinal })
          .catch((err: Error) => { if (cancelado(err)) throw err; return { erro: err.message }; })
          : Promise.resolve(null)]);
    } catch (e) {
      if (cancelado(e)) return;
      limpar(); estado.dados = null; msg.textContent = `Não foi possível analisar: ${(e as Error).message}`; return;
    }
    estado.dados = d;
    msg.textContent = d.estatistica.pearson === null ? `Sem ${nome()} suficientes (ou sem variação) para calcular a correlação.` : "";
    const xk = params.get("x");
    pf("fichas").replaceChildren(...fichasCorrelacao(d, xk, nome(true, true)));
    pf("titulo-grafico").textContent = `${d.rotulo_y} × ${d.rotulo_x}`;
    pf("grafico").replaceChildren(d.pontos.length ? graficoDispersao(d, xk, (v) => fmtX(xk, v), nome(false, true))
      : el("p", { class: "nota" }, `Nenhum ${nome(false)}.`));
    pf("correlacoes").replaceChildren(tabelaCorrelacoes(c.correlacoes, xk, nome(true, true), (indicador) => {
      pf("x").value = indicador; void ajustar("x"); void analisar();
    }));
    pf("acima").replaceChildren(tabelaResiduos(d.acima, xk, nome(false, true)));
    pf("abaixo").replaceChildren(tabelaResiduos(d.abaixo, xk, nome(false, true)));
    const regressao = desenharRegressao(rg, nome(true, true));
    pf("reg-fichas").replaceChildren(...regressao.fichas);
    pf("reg").replaceChildren(regressao.tabela);
  }

  async function aplicar(q: URLSearchParams): Promise<void> {
    estado.feito = true;  // o endereço manda; nada de análise padrão por cima
    ctx.mostrarAba("perfil");
    const u = q.get("unidade");
    pf("unidade").value = ehUnidade(u) ? u : "bairro";
    const reg = q.get("reg");
    if (reg) estado.reg = reg.split(",").filter(Boolean);
    await iniciar();
    const def = (id: string, k: string) => { const v = q.get(k); if (v !== null) pf(id).value = v; };
    def("ano", "ano"); def("turno", "turno");
    cargos(pf("cargo"), pf("ano").value, q.get("cargo"));
    pf("tipo").value = q.get("partido") ? "partido" : "numero";
    def("numero", "numero");
    def("x", "x"); def("x-ano", "x_ano"); def("x-turno", "x_turno");
    pf("x-tipo").value = q.get("x_partido") ? "partido" : "numero";
    def("x-numero", "x_numero");
    def("municipio", "municipio"); def("min", "min_validos");
    pf("ponderar").checked = q.get("ponderar") === "true";
    await preencherAlvo("");
    def("partido", "partido");
    if (pf("x").value === "voto") {
      mostrarX(true);
      cargos(pf("x-cargo"), pf("x-ano").value, q.get("x_cargo"));
      await preencherAlvo("x-");
      def("x-partido", "x_partido");
    } else mostrarX(false);
    await analisar();
  }

  // trocas no formulário
  const limparNumero = (p: Lado) => { pf(`${p}numero`).value = ""; };
  pf("ano").addEventListener("change", () => { limparNumero(""); void ajustar("y"); });
  pf("cargo").addEventListener("change", () => { limparNumero(""); void preencherAlvo(""); });
  pf("turno").addEventListener("change", () => { limparNumero(""); void preencherAlvo(""); });
  pf("tipo").addEventListener("change", () => void preencherAlvo(""));
  pf("x").addEventListener("change", () => void ajustar("x"));
  pf("x-ano").addEventListener("change", () => { limparNumero("x-"); void ajustar("x"); });
  pf("x-cargo").addEventListener("change", () => { limparNumero("x-"); void preencherAlvo("x-"); });
  pf("x-turno").addEventListener("change", () => { limparNumero("x-"); void preencherAlvo("x-"); });
  pf("x-tipo").addEventListener("change", () => void preencherAlvo("x-"));
  pf("municipio").addEventListener("change", () => void ajustar());
  pf("unidade").addEventListener("change", async () => { await carregarInfo(); await ajustar(); void analisar(); });
  pf("reg-btn").addEventListener("click", () => {
    estado.reg = [...pf("reg-ind").querySelectorAll<HTMLInputElement>("input:checked")].map((i) => i.value);
    void analisar();
  });
  ref("#form-perfil").addEventListener("submit", (e) => { e.preventDefault(); void analisar(); });
  pf("copiar").addEventListener("click", () => void copiarLink(ctx.endereco("perfil"), pf("copiar-msg")));

  return {
    id: "perfil",
    estado,
    escrever,
    aplicar,
    aoMostrar() {
      if (estado.feito) return;
      estado.feito = true;
      iniciar().then(() => ajustar()).then(analisar)
        .catch((e: Error) => { pf("msg").textContent = `Não foi possível abrir: ${e.message}`; });
    },
  };
}
