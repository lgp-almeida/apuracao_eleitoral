/* Aba "Comparação" entre duas eleições (apuracao/comparacao.py): por município (tempo real × referência) ou por
 * bairro (ano e cargo livres dos dois lados), mapa divergente e tabela; blocos de bancadas e de variação por partido.
 * Endereço: #comparacao?cargo=&metrica=[&partido=|&numero_a=&numero_b=][&ordem=][&var=1&var_partidos=PT,PL&var_ponderar=1]
 *           [&banc=1&banc_cargo=7][&detalhe=bairros&ano_a=&cargo_a=&ano_b=&cargo_b=] */
import { copiarLink } from "../../componentes/link";
import { criarCamadas } from "../../componentes/mapa/camadas";
import { criarMapa, limparCamadas } from "../../componentes/mapa/criar";
import type { MapaApuracao } from "../../componentes/mapa/tipos";
import { ficha, tabelaOrdenavel, type Coluna } from "../../componentes/tabela";
import type { Contexto, ModuloAba } from "../../core/aba";
import { api } from "../../core/api";
import { NOMES_CARGO } from "../../core/cargos";
import { el, refs } from "../../core/dom";
import { fmtVariacao, int, pct } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import { criarBancadas } from "./bancadas";
import { anosBairros, METRICAS_BAIRRO, rotuloEntidade, rotuloPartidoBairros } from "./formatos";
import type { InfoBairros, InfoComparacao, LinhaComparacao, PartidoEntidade, ResultadoComparacao } from "./tipos";
import { criarVariacao } from "./variacao";

const SELETORES = {
  botao: "#botao-comparacao", form: "#form-comp", detalhe: "#comp-detalhe", lCargo: "#comp-l-cargo", cargo: "#comp-cargo",
  anoA: "#comp-ano-a", cargoA: "#comp-cargo-a", anoB: "#comp-ano-b", cargoB: "#comp-cargo-b", metrica: "#comp-metrica",
  lPartido: "#comp-l-partido", partido: "#comp-partido", lNa: "#comp-l-na", rotA: "#comp-rot-a", numA: "#comp-num-a",
  lNb: "#comp-l-nb", rotB: "#comp-rot-b", numB: "#comp-num-b", copiar: "#comp-copiar", copiarMsg: "#comp-copiar-msg",
  notaBairros: "#comp-bairros-nota", fichas: "#comp-fichas", mapa: "#comp-mapa", legenda: "#comp-legenda",
  tituloTabela: "#comp-titulo-tabela", tabela: "#comp-tabela",
} as const;

type Sel = HTMLSelectElement;
const temOpcao = (sel: Sel, v: string | null, habilitada = false): v is string =>
  v !== null && [...sel.options].some((o) => o.value === v && (!habilitada || !o.disabled));

export interface EstadoComparacao {
  /** null = site sem eleição de referência: a aba nem aparece. */
  info: InfoComparacao | null;
  infoBairros: InfoBairros | null;
  detalhe: "municipios" | "bairros";
  /** Ordem da tabela ("COLUNA-desc"), vai para o endereço. */
  ordem: string | null;
  mapa: MapaApuracao | null;
  /** Já houve consulta (pelo botão ou pelo endereço): mostrar a aba não refaz a padrão. */
  feito: boolean;
}

export function criarAbaComparacao(ctx: Contexto) {
  const estado: EstadoComparacao = { info: null, infoBairros: null, detalhe: "municipios", ordem: null, mapa: null, feito: false };
  const r = refs(SELETORES);
  const s = (k: keyof typeof SELETORES) => r[k] as Sel;
  const [cargo, metrica, detalhe, anoA, anoB, cargoA, cargoB, partido] =
    (["cargo", "metrica", "detalhe", "anoA", "anoB", "cargoA", "cargoB", "partido"] as const).map(s);
  const numA = r.numA as HTMLInputElement, numB = r.numB as HTMLInputElement;
  const { desenharDivergente } = criarCamadas({ malhas: ctx.malhas, fmtDif: fmtVariacao });
  const canal = new Canal();
  const gravar = () => ctx.gravarEndereco("comparacao");
  const porBairro = () => estado.detalhe === "bairros";
  const bancadas = criarBancadas(gravar);
  const variacao = criarVariacao({
    cargo: () => cargo.value, porBairro, gravar,
    anos: () => [estado.info?.ano_a ?? 0, estado.info?.ano_b ?? 0],
  });

  function garantirMapa(): MapaApuracao {
    if (!estado.mapa) {
      estado.mapa = criarMapa(r.mapa);
      ctx.registrarMapa("compMapa", estado.mapa);
    }
    return estado.mapa;
  }

  /** Há eleição de referência? Mostra o botão da aba com os dois anos. */
  async function preparar(): Promise<void> {
    let info: InfoComparacao;
    try { info = await api("api/comparacao/info"); } catch { return; }
    if (!info.disponivel) return;
    estado.info = info;
    r.botao.hidden = false;
    r.botao.textContent = `Comparação ${info.ano_a} × ${info.ano_b}`;
    r.rotA.textContent = `Nº em ${info.ano_a}`;
    r.rotB.textContent = `Nº em ${info.ano_b}`;
    cargo.replaceChildren(...info.cargos.filter((c) => NOMES_CARGO[c]).map((c) =>
      el("option", { value: c, selected: c === 3 }, NOMES_CARGO[c])));
  }

  /** Campos que dependem da métrica (partido, nºs) e a lista de partidos do cargo ou dos dois anos. */
  async function ajustarCampos(): Promise<void> {
    const info = estado.info;
    if (!info) return;
    const m = metrica.value;
    r.lPartido.hidden = m !== "partido";
    r.lNa.hidden = r.lNb.hidden = m !== "candidato";
    const bairros = porBairro();
    const [a, b] = bairros ? [anoA.value, anoB.value] : [info.ano_a, info.ano_b];
    r.rotA.textContent = `Nº em ${a}`;
    r.rotB.textContent = `Nº em ${b}`;
    if (m !== "partido") return;
    if (!bairros) {
      const ps = await api<PartidoEntidade[]>(`api/comparacao/partidos?cargo=${cargo.value}`);
      partido.replaceChildren(...ps.map((p) => el("option", { value: p.PARTIDO }, rotuloEntidade(p, a, b))));
      return;
    }
    // bairros: partido pelo NÚMERO do ano mais recente, ligado pela entidade (o 14 de 2026 não é o de 2022)
    const ps = await api<PartidoEntidade[]>(`api/comparacao/bairros/partidos?ano_a=${a}&cargo_a=${cargoA.value}` +
      `&ano_b=${b}&cargo_b=${cargoB.value}&turno=${ctx.turno()}`);
    partido.replaceChildren(...ps.map((p) => el("option", { value: p.PARTIDO }, rotuloPartidoBairros(p, a, b))));
  }

  function cargosDoAno(sel: Sel, ano: string, preferido: string | null = null): void {
    const info = estado.infoBairros;
    if (!info) return;
    const cs = info.anos_votos[ano] || [1, 3, 5, 6, 7];  // ano sem votos (ex.: 2026): só "eleitorado" terá dado
    const alvo = String(preferido ?? sel.value);
    sel.replaceChildren(...cs.map((c) => el("option", { value: c }, info.cargos[c])));
    sel.value = cs.map(String).includes(alvo) ? alvo : String(cs[0]);
  }

  /** Municípios × bairros: campos de cada lado, métricas possíveis e anos/cargos da comparação por bairro. */
  async function prepararDetalhe(pref: Record<string, string | null> = {}): Promise<void> {
    const info = estado.info;
    if (!info) return;
    const bairros = detalhe.value === "bairros";
    estado.detalhe = bairros ? "bairros" : "municipios";
    r.lCargo.hidden = bairros;
    document.querySelectorAll<HTMLElement>(".comp-bairro").forEach((e) => { e.hidden = !bairros; });
    r.notaBairros.hidden = !bairros;
    for (const op of metrica.options) op.disabled = bairros && !METRICAS_BAIRRO.includes(op.value);
    if (metrica.selectedOptions[0]?.disabled) metrica.value = "brancos_nulos";
    if (bairros) {
      const ib = (estado.infoBairros ??= await api<InfoBairros>("api/comparacao/bairros/info"));
      const anos = anosBairros(Object.keys(ib.anos_votos), ib.anos_cadastro, info.ano_b);
      const preencher = (sel: Sel, padrao: number | undefined, preferido: string | null | undefined) => {
        const alvo = String(preferido ?? sel.value ?? "");
        sel.replaceChildren(...anos.map((a) => el("option", { value: a }, String(a))));
        sel.value = anos.map(String).includes(alvo) ? alvo : String(padrao);
      };
      preencher(anoA, anos.includes(info.ano_a) ? info.ano_a : anos[0], pref.ano_a);
      preencher(anoB, anos.includes(info.ano_b) ? info.ano_b : anos.at(-1), pref.ano_b);
      cargosDoAno(cargoA, anoA.value, pref.cargo_a ?? cargo.value);
      cargosDoAno(cargoB, anoB.value, pref.cargo_b ?? cargo.value);
    }
    await ajustarCampos();
  }

  async function atualizar(): Promise<void> {
    if (!estado.info) return;
    const mapa = garantirMapa();
    const m = metrica.value;
    const bairros = porBairro();
    const q = new URLSearchParams(bairros
      ? { ano_a: anoA.value, cargo_a: cargoA.value, ano_b: anoB.value, cargo_b: cargoB.value, metrica: m, turno: String(ctx.turno()) }
      : { cargo: cargo.value, metrica: m });
    if (m === "partido") q.set("partido", partido.value);
    if (m === "candidato") { q.set("numero_a", numA.value); q.set("numero_b", numB.value); }
    const sinal = canal.novo();
    let d: ResultadoComparacao;
    try { d = await api(`api/comparacao${bairros ? "/bairros" : ""}?${q}`, { sinal }); } catch (e) {
      if (cancelado(e)) return;
      limparCamadas(mapa);  // nada desenhado de consulta anterior pode ficar na tela (nem ir para o arquivo)
      mapa._export = null;
      r.fichas.replaceChildren();
      r.tabela.replaceChildren();
      r.legenda.replaceChildren(el("p", {}, `Erro: ${(e as Error).message}`));
      gravar();
      return;
    }
    if (bairros) {
      r.notaBairros.textContent = `${d.subtitulo ? d.subtitulo + " · " : ""}` +
        "área = bairros do IBGE que têm local de votação; cada local conta no bairro que contém sua coordenada.";
    }
    const valorAno = (v: number | null | undefined) => (v === null || v === undefined ? "—" : d.unidade === "var_pct" ? int(v) : pct(v));
    const u = d.uf || {};
    const area = bairros ? "área dos bairros" : ctx.uf();
    r.tituloTabela.textContent = `Por ${bairros ? "bairro" : "município"} (clique no cabeçalho para ordenar)`;
    r.fichas.replaceChildren(
      ficha(`${d.rotulo} — ${area} ${d.ano_a}`, valorAno(u.VALOR_A)),
      ficha(`${area} ${d.ano_b}`, valorAno(u.VALOR_B)),
      ficha(bairros ? "Diferença na área dos bairros" : "Diferença no estado", fmtVariacao(u.DIF, d.unidade)));
    await desenharDivergente(mapa, d, r.legenda, d.camada || "municipios");
    const cab: Coluna<LinhaComparacao>[] = [[bairros ? "Bairro — município" : "Município", "NM_MUNICIPIO"],
      [String(d.ano_a), "VALOR_A", true], [String(d.ano_b), "VALOR_B", true], ["Diferença", "DIF", true]];
    r.tabela.replaceChildren(tabelaOrdenavel(cab, d.municipios, (l, k) =>
      k === "DIF" ? fmtVariacao(l[k], d.unidade) : k === "NM_MUNICIPIO" ? l[k] : valorAno(l[k]), null,
    { ordem: estado.ordem, aoOrdenar: (o) => { estado.ordem = o; gravar(); } }));
    gravar();
  }

  function escrever(): URLSearchParams {
    const m = metrica.value;
    const q = new URLSearchParams({ cargo: cargo.value, metrica: m });
    if (m === "partido" && partido.value) q.set("partido", partido.value);
    if (m === "candidato") {
      for (const [k, campo] of [["numero_a", numA], ["numero_b", numB]] as const) {
        const v = campo.value.trim();
        if (v) q.set(k, v);
      }
    }
    if (porBairro()) {
      q.set("detalhe", "bairros");
      for (const [k, sel] of [["ano_a", anoA], ["cargo_a", cargoA], ["ano_b", anoB], ["cargo_b", cargoB]] as const) q.set(k, sel.value);
    }
    if (estado.ordem) q.set("ordem", estado.ordem);
    bancadas.escrever(q);
    variacao.escrever(q);
    return q;
  }

  async function aplicar(q: URLSearchParams): Promise<void> {
    if (!estado.info) return;  // sem eleição de referência: a aba nem existe
    const c = q.get("cargo");
    if (temOpcao(cargo, c)) cargo.value = c;
    detalhe.value = q.get("detalhe") === "bairros" ? "bairros" : "municipios";
    await prepararDetalhe({ ano_a: q.get("ano_a"), cargo_a: q.get("cargo_a"), ano_b: q.get("ano_b"), cargo_b: q.get("cargo_b") });
    const m = q.get("metrica");
    if (temOpcao(metrica, m, true)) metrica.value = m;
    await ajustarCampos();  // carrega a lista de partidos do cargo antes de escolher o partido
    const p = q.get("partido");
    if (temOpcao(partido, p)) partido.value = p;
    numA.value = q.get("numero_a") || "";
    numB.value = q.get("numero_b") || "";
    estado.ordem = q.get("ordem");
    estado.feito = true;  // mostrar a aba não deve disparar a consulta padrão
    ctx.mostrarAba("comparacao");
    await atualizar();
    bancadas.aplicar(q);
    await variacao.aplicar(q);
  }

  // trocas no formulário
  metrica.addEventListener("change", () => void ajustarCampos());
  cargo.addEventListener("change", () => { void ajustarCampos(); variacao.ajustar(); });
  r.form.addEventListener("submit", (e) => { e.preventDefault(); void atualizar(); });
  detalhe.addEventListener("change", async () => { await prepararDetalhe(); variacao.ajustar(); void atualizar(); });
  anoA.addEventListener("change", () => { cargosDoAno(cargoA, anoA.value); void ajustarCampos(); });
  anoB.addEventListener("change", () => { cargosDoAno(cargoB, anoB.value); void ajustarCampos(); });
  cargoA.addEventListener("change", () => void ajustarCampos());
  cargoB.addEventListener("change", () => void ajustarCampos());
  r.copiar.addEventListener("click", () => void copiarLink(ctx.endereco("comparacao"), r.copiarMsg));

  const modulo: ModuloAba = {
    id: "comparacao",
    preparar,
    escrever,
    aplicar,
    aoMostrar() {
      garantirMapa();
      if (estado.feito) return;
      estado.feito = true;
      void atualizar();
    },
  };
  return Object.assign(modulo, { estado, partidosVar: variacao.partidos });
}
