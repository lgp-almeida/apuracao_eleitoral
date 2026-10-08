/* As três camadas dos mapas: polígonos coloridos (município, bairro, área de ponderação), pontos (locais de
 * votação, área ∝ eleitorado) e divergente da comparação entre eleições. Todas gravam no mapa `_camada`,
 * `_contornos` e `_export` (cores e legenda para a exportação no servidor) e desenham a legenda. */
import * as L from "leaflet";
import { cor, el, type Filho } from "../../core/dom";
import { decimal, fmtPP, hora, int, pct } from "../../core/formatos";
import {
  classeDivergente, escalaCategorica, escalaDivergente, escalaSequencial, type ItemLegenda, limitesPorMaximo,
  quebrasQuantis, TOKENS_DIV,
} from "../escalas";
import { legendaMapa } from "../legenda";
import { enquadrarUmaVez, limparCamadas } from "./criar";
import type { Categoria, Geo, MapaApuracao, Malhas } from "./tipos";

export type CamadaPoligonos = "municipios" | "bairros" | "areas";

export interface ItemPoligono {
  valor: number | null;
  municipio?: string;
  rotulo?: string;
  antes?: number | null;
  depois?: number | null;
  voto?: number | null;
  indicador?: number;
  cv?: number | null;
}

export interface DadosPoligonos {
  tipo?: string;
  rotulo: string;
  itens: Record<string, ItemPoligono>;
  metrica?: string;
  categorias?: readonly Categoria[];
  momento?: string | null;
  sentido?: string;
  lados?: [string, string];
  cv_limites?: [number, number];
}

/** Faixas fixas entre quadros da linha do tempo. */
export interface Escala { qb: number[]; minimo: number; maximo: number }

export interface ItemPonto {
  u: string;
  lat: number;
  lon: number;
  valor: number;
  eleitores?: number;
  nome: string;
  mun: string;
  zona: number | string;
  local: number | string;
  rotulo?: string;
  antes?: number | null;
  depois?: number | null;
  voto?: number;
  indicador?: number;
}

export interface DadosPontos {
  tipo?: string;
  rotulo: string;
  itens: readonly ItemPonto[];
  unidade?: string;
  ano?: number;
  categorias?: readonly Categoria[];
  sentido?: string;
  lados?: [string, string];
}

export interface DadosDivergente {
  rotulo: string;
  itens: Record<string, { valor: number | null; municipio?: string; a?: number; b?: number }>;
  ano_a: number | string;
  ano_b: number | string;
  unidade: string;
  camada?: string;
  subtitulo?: string | null;
}

const ausente = (x: unknown): x is null | undefined => x === null || x === undefined;
const pct2 = (x: number) => `${decimal(x, 2)}%`;

/** Formato dos valores do mapa por local: p.p. com sinal, % (3 casas se tudo < 1%) ou inteiro. */
export function formatoLocais(d: Pick<DadosPontos, "unidade" | "itens">): (x: number) => string {
  if (d.unidade === "p.p.") return fmtPP;
  if (d.unidade === "%") {
    const vals = d.itens.map((i) => i.valor);
    const casas = vals.length && Math.max(...vals) < 1 ? 3 : 1;
    return (x) => `${decimal(x, casas)}%`;
  }
  return (x) => int(Math.round(x));
}

/** Raio do ponto: área ∝ eleitorado, entre 2,5 e 12 px. */
export const raioDoLocal = (eleitores: number | undefined): number => Math.max(2.5, Math.min(12, Math.sqrt(eleitores || 0) / 9));

export interface Dependencias {
  malhas: Malhas;
  /** Variação com sinal na unidade da comparação ("pp" → p.p., "var_pct" → %). */
  fmtDif: (v: number | null | undefined, unidade: string) => string;
}

export function criarCamadas({ malhas, fmtDif }: Dependencias) {
  const contornoMunicipal = async (mapa: MapaApuracao, peso: number, opacidade: number) => {
    mapa._contornos = L.geoJSON(await malhas.municipios(), {
      interactive: false, style: { fill: false, color: cor("--texto"), weight: peso, opacity: opacidade },
    }).addTo(mapa);
  };

  /**
   * Polígonos coloridos (categórico, sequencial ou divergente). `escala` (opcional) fixa as faixas de cor entre
   * quadros da linha do tempo; devolve a escala usada.
   */
  async function desenharMapa(mapa: MapaApuracao, dados: DadosPoligonos, legendaEl: HTMLElement, sufixo = "",
      escala: Escala | null = null, camada: CamadaPoligonos = "municipios"): Promise<Escala | null> {
    const poligonos = camada === "bairros" || camada === "areas";  // malhas finas: borda fina e contorno municipal
    const geo: Geo = camada === "bairros" ? await malhas.bairros() : camada === "areas" ? await malhas.areas()
      : await malhas.municipios();
    const props = (ft: GeoJSON.Feature) => (ft.properties ?? {}) as Record<string, string>;
    const idDe = (ft: GeoJSON.Feature) => (camada === "bairros" ? props(ft).CD_BAIRRO : camada === "areas" ? props(ft).CD_AP
      : props(ft).codarea);
    limparCamadas(mapa);
    const semDado = cor("--sem-dado");
    const ehPct = sufixo === "%" || Boolean(dados.metrica && dados.metrica !== "votos_candidato");
    // percentuais pequenos (ex.: deputado com 0,05%) precisam de mais casas para as faixas não se repetirem
    const vals = Object.values(dados.itens).map((i) => i.valor).filter((x): x is number => !ausente(x));
    const casas = ehPct && vals.length && Math.max(...vals) < 1 ? 3 : 2;
    const fmtPctN = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
    const fmt = (x: number | null | undefined) => (ausente(x) ? "—" : ehPct ? fmtPctN.format(x) + "%" : int(x));
    let corDe: (it: ItemPoligono | undefined) => string;
    let itensLegenda: ItemLegenda[];
    if (dados.tipo === "categorico") {
      const esc = escalaCategorica(dados.categorias ?? [], (c) => `${c.NUMERO} ${c.NOME_URNA} (${c.PARTIDO})`);
      corDe = (it) => (it ? esc.corValor(it.valor) : semDado);
      itensLegenda = esc.itensLegenda;
    } else if (dados.tipo === "divergente") {  // resíduo e variação (p.p.) por área de ponderação
      const esc = escalaDivergente(vals, dados.sentido);
      corDe = (it) => (!it || ausente(it.valor) ? semDado : esc.corValor(it.valor));
      itensLegenda = [...esc.itensLegenda];
    } else {
      if (!escala) {
        escala = dados.metrica === "secoes_totalizadas_pct" ? { qb: [20, 40, 60, 80], minimo: 0, maximo: 100 }
          : { qb: quebrasQuantis(vals), minimo: Math.min(...vals), maximo: Math.max(...vals) };
      }
      const esc = escalaSequencial(escala.qb, escala.minimo, escala.maximo, fmt);
      corDe = (it) => (!it || ausente(it.valor) ? semDado : esc.corValor(it.valor));
      itensLegenda = esc.itensLegenda;
    }
    itensLegenda.push([semDado, "sem dado"]);
    const f = (it: ItemPoligono | undefined) => (!it ? "sem dado" : dados.tipo === "categorico" ? (it.rotulo ?? "")
      : dados.tipo === "divergente" ? (ausente(it.valor) ? "—" : fmtPP(it.valor)) : fmt(it.valor));
    const detalhe = (it: ItemPoligono | undefined): Filho => (!it ? null  // dica das camadas divergentes: os dois lados da conta
      : dados.lados && !ausente(it.antes) && !ausente(it.depois)
        ? [el("br"), `${dados.lados[0]}: ${pct2(it.antes)} → ${dados.lados[1]}: ${pct2(it.depois)}`]
        : dados.tipo === "divergente" && !ausente(it.voto)
          ? [el("br"), `voto ${pct2(it.voto)} · indicador ${int(Math.round((it.indicador ?? 0) * 100) / 100)}`]
          : null);
    const coresExport: Record<string, string> = {};
    // erro amostral (indicadores da amostra do Censo por área): CV acima do limite = estimativa pouco confiável,
    // mais clara e com borda tracejada; a dica dá o CV e a faixa do IBGE
    const [cvCautela, cvFragil] = dados.cv_limites || [Infinity, Infinity];
    const fragil = (it: ItemPoligono | undefined) => Boolean(it && !ausente(it.cv) && it.cv > cvFragil);
    const faixaCv = (x: number) => (x > cvFragil ? "pouco confiável" : x > cvCautela ? "use com cautela" : "boa precisão");
    const estilo = (ft: GeoJSON.Feature): L.PathOptions => (fragil(dados.itens[idDe(ft)])
      ? { fillOpacity: 0.35, color: cor("--texto"), weight: 1, dashArray: "4 3" }
      : { fillOpacity: 0.85, color: cor("--superficie"), weight: poligonos ? 0.5 : 1, dashArray: undefined });
    const camadaGeo = L.geoJSON(geo, {
      style: (ft) => {
        if (!ft) return {};
        const c = corDe(dados.itens[idDe(ft)]);
        coresExport[idDe(ft)] = c;
        return { fillColor: c, ...estilo(ft) };
      },
      onEachFeature: (ft, layer) => {
        const it = dados.itens[idDe(ft)];
        const p = props(ft);
        const nome = it ? it.municipio
          : camada === "bairros" ? `${p.NM_BAIRRO} — ${p.NM_MUN}`
            : camada === "areas" ? `${p.NM_AP} — ${p.NM_MUN}` : p.codarea;
        const cv = it && !ausente(it.cv) ? [el("br"), `CV ${decimal(it.cv, 1)}% — ${faixaCv(it.cv)}`] : null;
        const caminho = layer as L.Path;
        caminho.bindTooltip(() => el("div", {}, el("strong", {}, nome), el("br"), f(it), detalhe(it), cv), { sticky: true });
        caminho.on("mouseover", () => caminho.setStyle({ weight: 3, color: cor("--texto") }));
        caminho.on("mouseout", () => caminho.setStyle(estilo(ft)));
      },
    }).addTo(mapa);
    mapa._camada = camadaGeo;
    // contorno dos municípios por cima: situa bairros/áreas e os municípios sem malha de bairros
    if (poligonos) await contornoMunicipal(mapa, 0.8, 0.45);
    enquadrarUmaVez(mapa, camadaGeo.getBounds());
    const titulo = dados.momento ? `${dados.rotulo} — às ${hora(dados.momento)}` : dados.rotulo;
    const nFrageis = Object.values(dados.itens).filter(fragil).length;
    const avisoCv = dados.cv_limites ? `Borda tracejada e cor mais clara: estimativa pouco confiável (CV acima de ` +
      `${cvFragil}%; ${int(nFrageis)} áreas). Entre ${cvCautela}% e ${cvFragil}%: use com cautela (o CV está na dica).` : null;
    mapa._export = { camada, cores: coresExport, legenda: itensLegenda, titulo, extras: avisoCv ? [avisoCv] : [] };
    legendaEl.replaceChildren(...legendaMapa(titulo, itensLegenda,
      { notas: [avisoCv ? el("p", { class: "nota cv-aviso" }, avisoCv) : null] }));
    return escala;
  }

  /** Um ponto por local de votação (área ∝ eleitorado), sobre o contorno dos municípios. */
  async function desenharPontos(mapa: MapaApuracao, d: DadosPontos, legendaEl: HTMLElement): Promise<void> {
    limparCamadas(mapa);
    const fmt = formatoLocais(d);
    const vals = d.itens.map((i) => i.valor);
    let corDe: (v: number) => string;
    let itensLegenda: ItemLegenda[];
    if (d.tipo === "categorico") {
      ({ corValor: corDe, itensLegenda } = escalaCategorica(d.categorias ?? [], (c) => `${c.NUMERO} ${c.NOME_URNA}`));
    } else if (d.tipo === "divergente") {
      ({ corValor: corDe, itensLegenda } = escalaDivergente(vals, d.sentido));
    } else {
      ({ corValor: corDe, itensLegenda } = escalaSequencial(quebrasQuantis(vals), Math.min(...vals), Math.max(...vals), fmt));
    }
    await contornoMunicipal(mapa, 0.6, 0.35);  // municípios por baixo: situa os pontos
    const renderer = L.canvas({ padding: 0.5 });
    const coresExport: Record<string, string> = {};
    // os maiores primeiro: os pequenos ficam por cima e continuam clicáveis
    const pontos = [...d.itens].sort((a, b) => (b.eleitores || 0) - (a.eleitores || 0));
    mapa._camada = L.layerGroup(pontos.map((it) => {
      const c = corDe(it.valor);
      coresExport[it.u] = c;
      const mk = L.circleMarker([it.lat, it.lon], { renderer, radius: raioDoLocal(it.eleitores), color: cor("--superficie"),
        weight: 0.8, fillColor: c, fillOpacity: 0.92 });
      mk.bindTooltip(() => el("div", {}, el("strong", {}, it.nome), el("br"), `${it.mun} · zona ${it.zona}, local ${it.local}`, el("br"),
        d.tipo === "categorico" ? (it.rotulo || String(it.valor)) : fmt(it.valor),
        d.lados && !ausente(it.antes) && !ausente(it.depois) ? [el("br"), `${d.lados[0]}: ${pct2(it.antes)} → ${d.lados[1]}: ${pct2(it.depois)}`]
          : d.tipo === "divergente" && !ausente(it.voto) ? [el("br"), `voto ${pct2(it.voto)} · indicador ${int(Math.round((it.indicador ?? 0) * 100) / 100)}`]
            : null,
        el("br"), `${int(it.eleitores)} eleitores`), { sticky: true });
      return mk;
    })).addTo(mapa);
    if (pontos.length) enquadrarUmaVez(mapa, L.latLngBounds(pontos.map((it) => [it.lat, it.lon])));
    mapa._export = { camada: "locais", ano: d.ano, cores: coresExport, legenda: itensLegenda, titulo: d.rotulo };
    legendaEl.replaceChildren(...legendaMapa(d.rotulo, itensLegenda,
      { redonda: true, notas: [el("p", { class: "nota" }, "Área do ponto ∝ eleitorado do local.")] }));
  }

  /** Comparação entre eleições por município ou bairro: diferença B − A em 7 faixas divergentes. */
  async function desenharDivergente(mapa: MapaApuracao, d: DadosDivergente, legendaEl: HTMLElement,
      camada = "municipios"): Promise<void> {
    const bairros = camada === "bairros";
    const geo = bairros ? await malhas.bairros() : await malhas.municipios();
    const props = (ft: GeoJSON.Feature) => (ft.properties ?? {}) as Record<string, string>;
    const idDe = (ft: GeoJSON.Feature) => (bairros ? props(ft).CD_BAIRRO : props(ft).codarea);
    limparCamadas(mapa);
    const difs = Object.values(d.itens).map((i) => i.valor).filter((x): x is number => !ausente(x));
    const lim = limitesPorMaximo(difs);  // |dif| < 10% do máximo = "sem variação relevante"
    const cores = TOKENS_DIV.map(cor);
    const semDado = cor("--sem-dado");
    const peso = bairros ? 0.5 : 1;
    const coresExport: Record<string, string> = {};
    const lado = (v: number | undefined) => (d.unidade === "var_pct" ? int(v) : pct(v));
    mapa._camada = L.geoJSON(geo, {
      style: (ft) => {
        if (!ft) return {};
        const it = d.itens[idDe(ft)];
        const fill = !it || ausente(it.valor) ? semDado : cores[classeDivergente(it.valor, lim)];
        coresExport[idDe(ft)] = fill;
        return { fillColor: fill, fillOpacity: 0.9, color: cor("--superficie"), weight: peso };
      },
      onEachFeature: (ft, layer) => {
        const it = d.itens[idDe(ft)];
        const p = props(ft);
        const nome = it ? it.municipio : bairros ? `${p.NM_BAIRRO} — ${p.NM_MUN}` : p.codarea;
        const caminho = layer as L.Path;
        caminho.bindTooltip(() => el("div", {}, el("strong", {}, nome), el("br"),
          it ? `${d.ano_a}: ${lado(it.a)} · ${d.ano_b}: ${lado(it.b)}` : "sem dado",
          el("br"), it ? `diferença: ${fmtDif(it.valor, d.unidade)}` : ""), { sticky: true });
        caminho.on("mouseover", () => caminho.setStyle({ weight: 3, color: cor("--texto") }));
        caminho.on("mouseout", () => caminho.setStyle({ weight: peso, color: cor("--superficie") }));
      },
    }).addTo(mapa);
    if (bairros) await contornoMunicipal(mapa, 0.8, 0.45);
    enquadrarUmaVez(mapa, (mapa._camada as L.GeoJSON).getBounds());
    const mag = (v: number) => fmtDif(v, d.unidade).replace(/^[+−]/, "");  // magnitude, sem sinal
    const itens: ItemLegenda[] = [
      [cores[6], `aumento maior que ${mag(lim[2])}`], [cores[5], `aumento de ${mag(lim[1])} a ${mag(lim[2])}`],
      [cores[4], `aumento de ${mag(lim[0])} a ${mag(lim[1])}`], [cores[3], `variação menor que ±${mag(lim[0])}`],
      [cores[2], `redução de ${mag(lim[0])} a ${mag(lim[1])}`], [cores[1], `redução de ${mag(lim[1])} a ${mag(lim[2])}`],
      [cores[0], `redução maior que ${mag(lim[2])}`], [semDado, "sem dado"],
    ];
    const titulo = `${d.rotulo}: ${d.ano_b} − ${d.ano_a}`;
    mapa._export = { camada, cores: coresExport, legenda: itens, titulo, subtitulo: d.subtitulo || null };
    legendaEl.replaceChildren(...legendaMapa(titulo, itens));
  }

  return { desenharMapa, desenharPontos, desenharDivergente };
}

