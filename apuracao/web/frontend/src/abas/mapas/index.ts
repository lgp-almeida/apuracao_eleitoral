/* Aba "Mapas": por município (tempo real, com linha do tempo), por bairro (malha do IBGE), por local de votação
 * (pontos) e por área de ponderação; camadas voto, perfil, resíduo, variação e transferência nos dois últimos.
 * Endereço: #mapas?cargo=&metrica=&numero=&momento=<ISO>&locais=1[&detalhe=bairros|locais|areas&ano_bairros=]
 *           [&camada=&indicador=&transf=&municipio=<IBGE>] (sem `momento` = acompanha o mais recente) */
import * as L from "leaflet";
import { copiarLink } from "../../componentes/link";
import { criarCamadas, type DadosPoligonos, type Escala } from "../../componentes/mapa/camadas";
import { criarMapa, limparCamadas } from "../../componentes/mapa/criar";
import type { MapaApuracao } from "../../componentes/mapa/tipos";
import type { Contexto, ModuloAba } from "../../core/aba";
import { api } from "../../core/api";
import { el, refs } from "../../core/dom";
import { fmtVariacao } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import type { Candidatos } from "../../dados/candidatos";
import type { InfoPerfil } from "../perfil/tipos";
import { LinhaDoTempo, rotuloMomento } from "./linha-tempo";
import { criarLocaisSobrepostos } from "./locais-sobrepostos";
import { notaAreas, notaBairros, notaLinhaDoTempo, notaLocais } from "./notas";
import {
  type Camada, CAMADAS_AREA, consultaCamada, controles, type Detalhe, ehDetalhe, METRICAS_BAIRRO, metricaPadrao,
  metricasPermitidas,
} from "./regras";
import type { InfoBairros, MapaAreas, MapaBairros, MapaLocais } from "./tipos";

const SELETORES = {
  form: "#form-mapa", cargo: "#mapa-cargo", lCamada: "#mapa-l-camada", camada: "#mapa-camada", lMetrica: "#mapa-l-metrica",
  metrica: "#mapa-metrica", lIndicador: "#mapa-l-indicador", indicador: "#mapa-indicador", lTransf: "#mapa-l-transf",
  transf: "#mapa-transf", numero: "#mapa-numero", lista: "#mapa-lista", detalhe: "#mapa-detalhe", lAno: "#mapa-l-ano",
  ano: "#mapa-ano", lMunicipio: "#mapa-l-municipio", municipio: "#mapa-municipio", lLocais: "#mapa-l-locais",
  locais: "#mapa-locais", linhaTempo: "#linha-tempo", ltPlay: "#lt-play", ltRange: "#lt-range", ltRotulo: "#lt-rotulo",
  copiar: "#copiar-link", copiarMsg: "#copiar-msg", ltNota: "#lt-nota", notaBairros: "#bairros-nota",
  notaLocais: "#locais-nota", notaAreas: "#areas-nota", mapa: "#mapa", legenda: "#mapa-legenda",
} as const;

type Sel = HTMLSelectElement;
const temOpcao = (sel: Sel, v: string | null, habilitada = false): v is string =>
  v !== null && [...sel.options].some((o) => o.value === v && (!habilitada || !o.disabled));

export interface EstadoMapas {
  detalhe: Detalhe;
  mapa: MapaApuracao | null;
  lt: LinhaDoTempo;
  infoBairros: InfoBairros | null;
  /** Info do Perfil × voto por unidade (indicadores e municípios das camadas por local/área). */
  infos: Partial<Record<"local" | "area", InfoPerfil>>;
  indicadoresDe: "local" | "area" | null;
  /** Cargo do mapa por município, para voltar a ele depois dos microdados. */
  cargoMun: string | null;
}

export interface DependenciasMapas { candidatos: Candidatos }

export function criarAbaMapas(ctx: Contexto, deps: DependenciasMapas) {
  const estado: EstadoMapas = { detalhe: "municipios", mapa: null, lt: new LinhaDoTempo(), infoBairros: null, infos: {},
    indicadoresDe: null, cargoMun: null };
  const r = refs(SELETORES);
  const s = (k: keyof typeof SELETORES) => r[k] as Sel;
  const [cargo, camada, metrica, indicador, transf, detalhe, ano, municipio] =
    (["cargo", "camada", "metrica", "indicador", "transf", "detalhe", "ano", "municipio"] as const).map(s);
  const numero = r.numero as HTMLInputElement, locais = r.locais as HTMLInputElement, ltRange = r.ltRange as HTMLInputElement;
  const OPCOES_CARGO_MUN = [...cargo.options].map((o): [string, string] => [o.value, o.textContent ?? ""]);
  const { desenharMapa, desenharPontos } = criarCamadas({ malhas: ctx.malhas, fmtDif: fmtVariacao });
  const sobrepostos = criarLocaisSobrepostos(ctx.ano);
  const canal = new Canal();  // um pedido de mapa novo (qualquer detalhe) cancela o anterior
  const lt = estado.lt;
  const gravar = () => ctx.gravarEndereco("mapas");
  const camadaAtual = () => camada.value as Camada;

  function garantirMapa(): MapaApuracao {
    if (!estado.mapa) {
      estado.mapa = criarMapa(r.mapa);
      ctx.registrarMapa("mapa", estado.mapa);
    }
    return estado.mapa;
  }

  /** Erro: nada da consulta anterior fica na tela (nem vai para o arquivo exportado). */
  function falhou(mapa: MapaApuracao, nota: HTMLElement | null, e: unknown): void {
    limparCamadas(mapa);
    mapa._export = null;
    r.legenda.replaceChildren(el("p", {}, `Erro: ${(e as Error).message}`));
    if (nota) nota.textContent = "";
  }

  function preencherCargos(opcoes: readonly [string, string][], preferido: string | null | undefined): void {
    const atual = String(preferido ?? cargo.value);
    cargo.replaceChildren(...opcoes.map(([v, t]) => el("option", { value: v }, t)));
    cargo.value = opcoes.some(([v]) => v === atual) ? atual : (opcoes[0]?.[0] ?? "");
  }

  /** Indicadores e municípios da unidade ("local" ou "area": a área tem a religião e a amostra do Censo). */
  async function prepararLocais(unidade: "local" | "area"): Promise<void> {
    const info = (estado.infos[unidade] ??= await api<InfoPerfil>(`api/perfil/info?unidade=${unidade}`));
    if (estado.indicadoresDe === unidade) return;
    estado.indicadoresDe = unidade;
    const indAtual = indicador.value, munAtual = municipio.value;
    const grupos: Record<string, [string, string][]> = {};
    for (const [k, d] of Object.entries(info.indicadores)) (grupos[d.fonte] ||= []).push([k, d.rotulo]);
    indicador.replaceChildren(...Object.entries(grupos).map(([fonte, itens]) =>
      el("optgroup", { label: fonte }, ...itens.map(([k, t]) => el("option", { value: k }, t)))));
    if (temOpcao(indicador, indAtual)) indicador.value = indAtual;
    municipio.replaceChildren(el("option", { value: "" }, `Todo o estado (${ctx.uf()})`),
      ...info.municipios.map((m) => el("option", { value: m.CD_MUN }, m.NM_MUN)));
    if (temOpcao(municipio, munAtual)) municipio.value = munAtual;
  }

  function ajustarControles(): void {
    const d = estado.detalhe;
    for (const op of camada.options) op.disabled = d === "areas" && !CAMADAS_AREA.includes(op.value as Camada);
    if (camada.selectedOptions[0]?.disabled) camada.value = "voto";
    const c = controles(d, camadaAtual(), metrica.value);
    r.lCamada.hidden = !c.camada;
    r.lMunicipio.hidden = !c.municipio;
    r.lIndicador.hidden = !c.indicador;
    r.lTransf.hidden = !c.transf;
    r.lMetrica.hidden = !c.metrica;
    if (d === "locais" || d === "areas") {
      const permitidas = metricasPermitidas(d, camadaAtual()) ?? [];
      for (const op of metrica.options) op.disabled = !permitidas.includes(op.value);
      if (metrica.selectedOptions[0]?.disabled) metrica.value = metricaPadrao(camadaAtual());
    }
    const n = controles(d, camadaAtual(), metrica.value);  // a métrica pode ter mudado acima
    numero.disabled = !n.numero;
    numero.placeholder = n.placeholder;
  }

  /** Ajusta os controles ao detalhe; com microdados, anos e cargos vêm do cache do servidor. */
  async function prepararDetalhe(anoPreferido: string | null = null, cargoPreferido: string | null = null): Promise<void> {
    const novo: Detalhe = ehDetalhe(detalhe.value) ? detalhe.value : "municipios";
    const microdados = novo !== "municipios";
    if (estado.detalhe === "municipios" && microdados) estado.cargoMun = cargo.value;  // volta ao mesmo cargo depois
    estado.detalhe = novo;
    r.lAno.hidden = !microdados;
    r.notaBairros.hidden = novo !== "bairros";
    r.notaLocais.hidden = novo !== "locais";
    r.notaAreas.hidden = novo !== "areas";
    r.lLocais.hidden = novo === "locais";  // os pontos já são os locais
    if (novo === "locais" && locais.checked) { locais.checked = false; void alternarLocais(); }
    for (const op of metrica.options) op.disabled = microdados && !METRICAS_BAIRRO.includes(op.value);
    if (metrica.selectedOptions[0]?.disabled) metrica.value = "vencedor";
    if (novo === "locais" || novo === "areas") await prepararLocais(novo === "areas" ? "area" : "local");
    ajustarControles();
    if (!microdados) { preencherCargos(OPCOES_CARGO_MUN, cargoPreferido ?? estado.cargoMun); return; }
    r.linhaTempo.hidden = true;  // microdados = resultado final: sem linha do tempo
    r.ltNota.hidden = true;
    const info = (estado.infoBairros ??= await api<InfoBairros>("api/bairros/anos"));
    const anos = Object.keys(info.anos).map(Number);
    if (!anos.includes(ctx.ano())) anos.push(ctx.ano());  // o ano do site (2026: só após a publicação)
    anos.sort((a, b) => b - a);
    const padrao = info.anos[ctx.ano()] ? ctx.ano() : (anos.find((a) => info.anos[a]) ?? anos[0]);
    const pedido = String(anoPreferido ?? ano.value);
    const escolhido = anos.map(String).includes(pedido) ? pedido : String(padrao);
    ano.replaceChildren(...anos.map((a) => el("option", { value: a }, String(a))));
    ano.value = escolhido;
    const cargos = info.anos[escolhido] || [1, 3, 5, 6, 7];
    preencherCargos(cargos.map((c): [string, string] => [String(c), info.cargos[c]]), cargoPreferido);
  }

  async function carregarMomentos(): Promise<void> {
    if (estado.detalhe !== "municipios") return;  // microdados finais: sem linha do tempo
    let momentos: string[] = [];
    try { momentos = (await api<{ momentos: string[] }>(`api/mapa/momentos?cargo=${cargo.value}`)).momentos; } catch { /* sem série */ }
    lt.receber(momentos);
    r.linhaTempo.hidden = momentos.length < 2;
    r.ltNota.hidden = !r.linhaTempo.hidden;
    r.ltNota.textContent = notaLinhaDoTempo(momentos.length);
    ltRange.max = String(Math.max(0, momentos.length - 1));
    ltRange.value = String(lt.idx);
    if (momentos.length) r.ltRotulo.textContent = rotuloMomento(momentos, lt.idx);
  }

  async function atualizarMunicipios(c: string, sinal: AbortSignal): Promise<void> {
    const mapa = garantirMapa();
    let q = `api/mapa?cargo=${c}&metrica=${metrica.value}`;
    if (metrica.value.endsWith("_candidato")) {
      const n = await deps.candidatos.resolver(c, numero.value || "");
      if (n === null) { r.legenda.replaceChildren(el("p", {}, "Informe o número de um candidato.")); return; }
      q += `&numero=${n}`;
    }
    const chaveEscala = q;  // a escala do quadro "agora" vale para todos os quadros da mesma consulta
    const passado = lt.noPassado;
    try {
      if (passado && !lt.escalas[chaveEscala]) {  // escala ainda não calculada: pega do momento mais recente
        lt.escalas[chaveEscala] = await desenharMapa(mapa, await api<DadosPoligonos>(q, { sinal }), r.legenda);
      }
      const dados = await api<DadosPoligonos>(passado ? `${q}&momento=${encodeURIComponent(lt.atual ?? "")}` : q, { sinal });
      const esc = await desenharMapa(mapa, dados, r.legenda, "", passado ? (lt.escalas[chaveEscala] as Escala) : null);
      if (!passado) lt.escalas[chaveEscala] = esc;
      gravar();
    } catch (e) { if (!cancelado(e)) r.legenda.replaceChildren(el("p", {}, `Erro: ${(e as Error).message}`)); }
  }

  async function atualizarBairros(c: string, sinal: AbortSignal): Promise<void> {
    const mapa = garantirMapa();
    let q = `api/mapa/bairros?ano=${ano.value}&cargo=${c}&metrica=${metrica.value}&turno=${ctx.turno()}`;
    if (metrica.value.endsWith("_candidato")) {
      const n = numero.value.trim();
      if (!/^\d+$/.test(n)) { r.legenda.replaceChildren(el("p", {}, "Informe o número de um candidato.")); return; }
      q += `&numero=${n}`;
    }
    try {
      const dados = await api<MapaBairros>(q, { sinal });
      await desenharMapa(mapa, dados, r.legenda, "", null, "bairros");
      r.notaBairros.textContent = notaBairros(dados);
    } catch (e) {
      if (cancelado(e)) return;
      falhou(mapa, r.notaBairros, e);
    }
    gravar();
  }

  /** Mapa por local (pontos) ou por área (polígonos): mesma consulta de camada. */
  async function atualizarPontual(c: string, sinal: AbortSignal): Promise<void> {
    const mapa = garantirMapa();
    const areas = estado.detalhe === "areas";
    const nota = areas ? r.notaAreas : r.notaLocais;
    const q = consultaCamada({ ano: ano.value, camada: camadaAtual(), cargo: c, turno: ctx.turno(), metrica: metrica.value,
      numero: numero.value, indicador: indicador.value, transf: transf.value, municipio: municipio.value });
    if ("falta" in q) { r.legenda.replaceChildren(el("p", {}, q.falta)); return; }
    r.legenda.replaceChildren(el("p", { class: "nota" }, areas ? "carregando as áreas…" : "carregando os locais…"));
    try {
      if (areas) {
        const d = await api<MapaAreas>(`api/mapa/areas?${q}`, { sinal });
        await desenharMapa(mapa, d, r.legenda, d.unidade === "%" ? "%" : "", null, "areas");
        const mun = municipio.value;
        if (mun && mapa._camada) {  // enquadra o município escolhido (as demais áreas ficam "sem dado")
          const b = L.latLngBounds([]);
          (mapa._camada as L.GeoJSON).eachLayer((l) => {
            const camadaGeo = l as L.Polygon & { feature?: GeoJSON.Feature };
            if (String(camadaGeo.feature?.properties?.CD_MUN) === mun) b.extend(camadaGeo.getBounds());
          });
          if (b.isValid()) mapa.fitBounds(b, { padding: [10, 10] });
        }
        nota.textContent = notaAreas(d, camadaAtual());
      } else {
        const d = await api<MapaLocais>(`api/mapa/locais?${q}`, { sinal });
        await desenharPontos(mapa, d, r.legenda);
        nota.textContent = notaLocais(d, camadaAtual());
      }
    } catch (e) {
      if (cancelado(e)) return;
      falhou(mapa, nota, e);
    }
    gravar();
  }

  async function atualizar(): Promise<void> {
    garantirMapa();
    const sinal = canal.novo();
    const c = cargo.value;
    if (estado.detalhe === "locais" || estado.detalhe === "areas") return atualizarPontual(c, sinal);
    if (estado.detalhe === "bairros") return atualizarBairros(c, sinal);
    return atualizarMunicipios(c, sinal);
  }

  async function alternarLocais(): Promise<void> {
    const mapa = garantirMapa();
    gravar();
    await sobrepostos.mostrar(mapa, locais.checked);
  }

  function escrever(): URLSearchParams {
    const q = new URLSearchParams({ cargo: cargo.value, metrica: metrica.value });
    if (metrica.value.endsWith("_candidato") && numero.value.trim()) q.set("numero", numero.value.trim());
    const d = estado.detalhe;
    if (d !== "municipios") {
      q.set("detalhe", d);
      q.set("ano_bairros", ano.value);
      if (d === "locais" || d === "areas") {
        q.set("camada", camada.value);
        if (camada.value === "perfil" || camada.value === "residuo") q.set("indicador", indicador.value);
        if (camada.value === "transferencia") q.set("transf", transf.value);
        if (camada.value === "residuo" && numero.value.trim()) q.set("numero", numero.value.trim());
        if (municipio.value) q.set("municipio", municipio.value);
      }
    } else if (lt.noPassado && lt.atual) q.set("momento", lt.atual);
    if (locais.checked) q.set("locais", "1");
    return q;
  }

  async function aplicar(q: URLSearchParams): Promise<void> {
    const d = q.get("detalhe");
    detalhe.value = d === "bairros" || d === "locais" || d === "areas" ? d : "municipios";
    await prepararDetalhe(q.get("ano_bairros"), q.get("cargo"));  // cargos dependem do detalhe e do ano
    const m = q.get("metrica");
    if (temOpcao(metrica, m, true)) metrica.value = m;
    for (const [sel, k] of [[camada, "camada"], [indicador, "indicador"], [transf, "transf"], [municipio, "municipio"]] as const) {
      const v = q.get(k);
      if (temOpcao(sel, v)) sel.value = v;
    }
    ajustarControles();
    numero.value = q.get("numero") || "";
    // o momento vira índice só quando os momentos do cargo chegarem (carregarMomentos)
    lt.pedido = q.get("momento") || null;
    lt.irParaOFim();
    const ligar = q.get("locais") === "1";
    if (locais.checked !== ligar) { locais.checked = ligar; void alternarLocais(); }
    ctx.mostrarAba("mapas");
  }

  // trocas no formulário
  metrica.addEventListener("change", () => {
    if (!metrica.value.endsWith("_candidato")) numero.disabled = true;
    else { numero.disabled = false; void deps.candidatos.preencher(cargo.value, r.lista); }
    ajustarControles();
  });
  cargo.addEventListener("change", () => {
    deps.candidatos.limpar();
    lt.irParaOFim();  // novo cargo: começa no momento mais recente
    void carregarMomentos();
    if (!numero.disabled) void deps.candidatos.preencher(cargo.value, r.lista);
  });
  r.form.addEventListener("submit", (e) => { e.preventDefault(); void atualizar(); });
  locais.addEventListener("change", () => void alternarLocais());
  detalhe.addEventListener("change", async () => {
    await prepararDetalhe();
    if (detalhe.value === "municipios") await carregarMomentos();
    void atualizar();
  });
  ano.addEventListener("change", async () => { await prepararDetalhe(ano.value); void atualizar(); });
  camada.addEventListener("change", () => { ajustarControles(); void atualizar(); });
  indicador.addEventListener("change", () => void atualizar());
  transf.addEventListener("change", () => void atualizar());
  municipio.addEventListener("change", () => { if (estado.mapa) estado.mapa._enquadrado = false; void atualizar(); });
  ltRange.addEventListener("input", () => {
    lt.idx = Number(ltRange.value);
    if (lt.momentos.length) r.ltRotulo.textContent = rotuloMomento(lt.momentos, lt.idx);
    void atualizar();
  });
  r.ltPlay.addEventListener("click", () => {
    if (lt.timer) { lt.parar(); r.ltPlay.textContent = "▶"; return; }
    if (lt.noFim) lt.idx = 0;
    r.ltPlay.textContent = "⏸"; r.ltPlay.setAttribute("aria-label", "Pausar");
    const passo = async () => {
      ltRange.value = String(lt.idx);
      r.ltRotulo.textContent = rotuloMomento(lt.momentos, lt.idx);
      await atualizar();
      if (lt.noFim) { lt.parar(); r.ltPlay.textContent = "▶"; return; }
      lt.idx += 1;
    };
    void passo();
    lt.timer = setInterval(() => void passo(), 900);
  });
  r.copiar.addEventListener("click", () => void copiarLink(ctx.endereco("mapas"), r.copiarMsg));

  const modulo: ModuloAba = {
    id: "mapas",
    escrever,
    aplicar,
    aoMostrar() {
      garantirMapa();
      void carregarMomentos().then(atualizar);
    },
    /** Ciclo de 60 s: novos momentos; quem está vendo um momento passado (ou animando) não é atropelado. */
    async atualizar() {
      if (lt.timer || estado.detalhe !== "municipios") return;
      const noFim = lt.noFim;
      await carregarMomentos();
      if (noFim) await atualizar();
    },
  };
  return Object.assign(modulo, { estado });
}
