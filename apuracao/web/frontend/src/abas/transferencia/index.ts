/* Aba "1º → 2º turno": matriz da inferência ecológica (apuracao/transferencia.py) — para onde foi cada grupo
 * do 1º turno. Endereço: #transferencia?fonte=microdados|tempo_real&ano=&cargo=&nivel=secao|local|municipio[&municipio=<TSE>] */
import { copiarLink } from "../../componentes/link";
import type { Contexto, ModuloAba } from "../../core/aba";
import { api } from "../../core/api";
import { nomeCargo } from "../../core/cargos";
import { el, refs } from "../../core/dom";
import { Canal, cancelado } from "../../core/pedidos";
import { desenharTransferencia } from "./desenhar";
import type { InfoTransferencia, MunicipioTransferencia, ResultadoTransferencia } from "./tipos";

const SELETORES = {
  fonte: "#tf-fonte", ano: "#tf-ano", cargo: "#tf-cargo", nivel: "#tf-nivel", municipio: "#tf-municipio",
  form: "#form-tf", link: "#tf-link", linkMsg: "#tf-link-msg", msg: "#tf-msg", resultado: "#tf-resultado",
} as const;

/** Valor existe entre as opções (habilitadas) do seletor. */
const temOpcao = (sel: HTMLSelectElement, v: string | null): v is string =>
  v !== null && [...sel.options].some((o) => o.value === v && !o.disabled);

export interface EstadoTransferencia {
  info: InfoTransferencia | null;
  /** Carga inicial (uma só, mesmo com pedidos simultâneos). */
  pronto: Promise<void> | null;
}

export function criarAbaTransferencia(ctx: Contexto): ModuloAba & { estado: EstadoTransferencia } {
  const estado: EstadoTransferencia = { info: null, pronto: null };
  const canal = new Canal();
  const r = refs(SELETORES);
  const fonte = r.fonte as HTMLSelectElement, ano = r.ano as HTMLSelectElement, cargo = r.cargo as HTMLSelectElement;
  const nivel = r.nivel as HTMLSelectElement, municipio = r.municipio as HTMLSelectElement;

  function iniciar(): Promise<void> {
    estado.pronto ??= (async () => {
      const info = await api<InfoTransferencia>("api/transferencia/info");
      estado.info = info;
      ano.replaceChildren(...info.anos.slice().reverse().map((a) => el("option", { value: a }, a)));
      const opTempoReal = fonte.querySelector<HTMLOptionElement>('[value="tempo_real"]');
      if (opTempoReal) opTempoReal.disabled = !info.tempo_real;
      if (info.tempo_real) fonte.value = "tempo_real";  // noite do 2º turno: é o que existe
      for (const s of [fonte, ano, cargo]) s.addEventListener("change", () => void ajustar());
      r.form.addEventListener("submit", (e) => { e.preventDefault(); void calcular(); });
      r.link.addEventListener("click", () => void copiarLink(ctx.endereco("transferencia"), r.linkMsg));
      await ajustar();
    })();
    return estado.pronto;
  }

  /** Cargos da fonte/ano e municípios do cargo; `pedido` = valores a escolher, se existirem. */
  async function ajustar(pedido: { cargo?: string | null; municipio?: string | null } = {}): Promise<void> {
    const info = estado.info;
    if (!info) return;
    const tempoReal = fonte.value === "tempo_real";
    document.querySelectorAll<HTMLElement>(".tf-md").forEach((l) => { l.hidden = tempoReal; });
    const cargos = tempoReal ? info.cargos_tempo_real : (info.cargos[ano.value] || []);
    const antes = pedido.cargo || cargo.value;
    cargo.replaceChildren(...cargos.map((c) => el("option", { value: c }, nomeCargo(c))));
    if (cargos.map(String).includes(String(antes))) cargo.value = String(antes);
    if (tempoReal) return;
    const prefeito = cargo.value === "11";
    let muns: MunicipioTransferencia[] = [];
    try { muns = await api(`api/transferencia/municipios?ano=${ano.value}&cargo=${cargo.value}`); }
    catch (e) { r.msg.textContent = `Sem a lista de municípios: ${(e as Error).message}`; }
    municipio.replaceChildren(...(prefeito ? [] : [el("option", { value: "" }, `Todo o estado (${ctx.uf()})`)]),
      ...muns.map((m) => el("option", { value: m.CD_MUNICIPIO }, m.NM_MUNICIPIO)));
    const mun = pedido.municipio ?? "";
    if ([...municipio.options].some((o) => o.value === String(mun))) municipio.value = String(mun);
  }

  function escrever(): URLSearchParams {
    const q = new URLSearchParams({ fonte: fonte.value, cargo: cargo.value });
    if (q.get("fonte") === "microdados") {
      q.set("ano", ano.value);
      q.set("nivel", nivel.value);
      if (municipio.value) q.set("municipio", municipio.value);
    }
    return q;
  }

  async function calcular(): Promise<void> {
    if (!cargo.value) { r.msg.textContent = "Nenhum cargo com 2º turno nesta fonte."; return; }
    r.msg.textContent = "Calculando… a 1ª vez lê os microdados e roda o bootstrap (10 a 30 s).";
    ctx.gravarEndereco("transferencia");
    const sinal = canal.novo();  // um cálculo novo cancela o anterior: só o último desenha
    let res: ResultadoTransferencia;
    try { res = await api(`api/transferencia?${escrever()}`, { sinal }); } catch (e) {
      if (cancelado(e)) return;
      r.msg.textContent = `Não foi possível calcular: ${(e as Error).message}`;
      r.resultado.replaceChildren();
      return;
    }
    r.msg.textContent = "";
    r.resultado.replaceChildren(...desenharTransferencia(res));
  }

  async function aplicar(q: URLSearchParams): Promise<void> {
    ctx.mostrarAba("transferencia");
    await iniciar();
    for (const [sel, chave] of [[fonte, "fonte"], [ano, "ano"], [nivel, "nivel"]] as const) {
      const v = q.get(chave);
      if (temOpcao(sel, v)) sel.value = v;
    }
    await ajustar({ cargo: q.get("cargo"), municipio: q.get("municipio") });
    await calcular();
  }

  let aberta = false;
  return {
    id: "transferencia",
    estado,
    escrever,
    aplicar,
    aoMostrar() {
      if (aberta) return;
      aberta = true;
      iniciar().catch((e: Error) => { r.msg.textContent = `Não foi possível abrir: ${e.message}`; });
    },
  };
}
