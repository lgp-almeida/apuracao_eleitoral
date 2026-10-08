/* Presidente por UF no cartão Brasil (rodada 35): mapa (quem lidera ou % de um candidato) e tabela. O bloco é UM
 * nó persistente, devolvido ao cartão a cada redesenho: o mapa do Leaflet sobrevive à troca. A dica de cada UF
 * fica fora do mapa (dicaFlutuante), porque a tabela da dica é mais alta que o mapa, que cortaria o tooltip. */
import * as L from "leaflet";
import { dicaFlutuante } from "../../componentes/dica";
import { escalaSequencial, quebrasQuantis, type ItemLegenda, TOKENS_CAT } from "../../componentes/escalas";
import { legendaLinha } from "../../componentes/legenda";
import { criarMapa, enquadrarUmaVez } from "../../componentes/mapa/criar";
import type { MapaApuracao } from "../../componentes/mapa/tipos";
import { tabelaOrdenavel } from "../../componentes/tabela";
import { api } from "../../core/api";
import { cor, el } from "../../core/dom";
import { fmtPct, hora, int, pct } from "../../core/formatos";
import type { PresidenteUfs, UfPresidente } from "./tipos";

/** Dica de uma UF: apuração, todos os candidatos (% dos válidos), brancos, nulos e abstenção. */
export function dicaUf(u: UfPresidente | undefined, codigo: string, valor: (u: UfPresidente) => string): HTMLElement {
  if (!u) return el("div", {}, el("strong", {}, codigo), el("br"), "sem dado");
  const cab = el("div", {}, el("strong", {}, u.nome), " · ", `${pct(u.pct_secoes)} apurado`,
    u.hora ? ` · totalização ${hora(u.hora)}` : null, u.final ? " · FINAL" : null);
  if (!u.primeiro) return el("div", {}, cab, el("div", { class: "nota" }, "sem apuração"));
  const linha = (rotulo: string, p: number | null, n: number, classe: string | null = null) => el("tr", { class: classe },
    el("td", { class: "nome" }, rotulo), el("td", { class: "num" }, pct(p)), el("td", { class: "num" }, int(n)));
  return el("div", {}, cab, el("div", {}, valor(u)),
    el("table", { class: "tabela-dica" },
      el("thead", {}, el("tr", {}, el("th", {}, "Candidato"), el("th", { class: "num" }, "% válidos"),
        el("th", { class: "num" }, "Votos"))),
      el("tbody", {}, u.candidatos.map((c, i) => linha(`${c.numero} ${c.nome}`, c.pct, c.votos, i === 0 ? "lider" : null))),
      el("tbody", { class: "nao-validos" },
        linha("Brancos", u.pct_brancos, u.brancos), linha("Nulos", u.pct_nulos, u.nulos),
        linha("Abstenção", u.pct_abstencao, u.abstencao))),
    el("div", { class: "nota" }, "Brancos e nulos: % do total de votos; abstenção: % do eleitorado."));
}

type LinhaUf = UfPresidente & { ordem: string; lider: string; pct1: number | null; vice: string; pct2: number | null };

export interface EstadoBrasil {
  dados: PresidenteUfs | null;
  geo: GeoJSON.FeatureCollection | null;
  mapa: MapaApuracao | null;
  ordem: string;
}

/** @param registrarMapa torna o mapa conhecido pelo nome "brasilMapa" (testes e2e) */
export function criarBrasil(registrarMapa: (m: MapaApuracao) => void) {
  const estado: EstadoBrasil = { dados: null, geo: null, mapa: null, ordem: "ordem-asc" };
  let bloco: HTMLElement | null = null;
  const nome = (x: UfPresidente["primeiro"]) => (x ? `${x.numero} ${x.nome}` : "—");

  function desenhar(): void {
    const d = estado.dados;
    if (!d || !bloco) return;
    bloco.hidden = !d.ufs.length;
    if (!d.ufs.length) return;
    const sel = bloco.querySelector<HTMLSelectElement>("#brasil-metrica");
    if (!sel) return;
    const escolhido = sel.value;
    sel.replaceChildren(el("option", { value: "lider" }, "Quem lidera"),
      ...d.candidatos.map((c) => el("option", { value: String(c.NUMERO) }, `% de ${c.NUMERO} ${c.NOME_URNA}`)));
    sel.value = [...sel.options].some((o) => o.value === escolhido) ? escolhido : "lider";
    const semDado = cor("--sem-dado");
    let corDe: (u: UfPresidente | undefined) => string;
    let legenda: ItemLegenda[];
    let valor: (u: UfPresidente) => string;
    if (sel.value === "lider") {
      const cores = TOKENS_CAT.map(cor), outros = cor("--outros");
      const idx = new Map(d.candidatos.map((c, i) => [c.NUMERO, i]));
      corDe = (u) => { if (!u || !u.primeiro) return semDado; const i = idx.get(u.primeiro.numero); return i === undefined ? outros : cores[i]; };
      legenda = [...d.candidatos.map((c, i): ItemLegenda => [cores[i], `${c.NUMERO} ${c.NOME_URNA} (${c.PARTIDO})`]), [outros, "Outros"]];
      valor = (u) => (u.primeiro ? `lidera: ${nome(u.primeiro)} (${pct(u.primeiro.pct)})` : "sem apuração");
    } else {
      const v = (u: UfPresidente | undefined) => (u && u.primeiro ? u.pct[sel.value] ?? null : null);
      const vals = d.ufs.filter((u) => u.uf !== "ZZ").map(v).filter((x): x is number => x !== null);
      const esc = escalaSequencial(quebrasQuantis(vals), Math.min(...vals), Math.max(...vals), pct);
      corDe = (u) => { const x = v(u); return x === null ? semDado : esc.corValor(x); };
      legenda = vals.length ? esc.itensLegenda : [];
      valor = (u) => `${sel.selectedOptions[0]?.textContent ?? ""}: ${pct(v(u))}`;
    }
    legenda.push([semDado, "sem apuração"]);
    bloco.querySelector("#brasil-legenda")?.replaceChildren(...legendaLinha(legenda).children);
    const porIbge = new Map(d.ufs.filter((u) => u.cd_ibge).map((u) => [String(u.cd_ibge), u]));
    const divMapa = bloco.querySelector<HTMLElement>("#brasil-mapa");
    if (estado.geo && divMapa) {
      if (!estado.mapa) {
        estado.mapa = criarMapa(divMapa, { centro: [-15, -54], zoom: 3, ladrilhos: false, zoomSnap: 0.25 });
        registrarMapa(estado.mapa);
      }
      const mapa = estado.mapa;
      if (mapa._camada) mapa.removeLayer(mapa._camada);
      const codigo = (ft: GeoJSON.Feature) => String((ft.properties as { codarea: string }).codarea);
      const camada = L.geoJSON(estado.geo, {
        style: (ft) => ({ fillColor: corDe(ft ? porIbge.get(codigo(ft)) : undefined), fillOpacity: 0.85, color: cor("--superficie"), weight: 1 }),
        onEachFeature: (ft, layer) => {
          const u = porIbge.get(codigo(ft));
          const caminho = layer as L.Path;
          caminho.on("mouseover", (e: L.LeafletMouseEvent) => {
            dicaFlutuante.mostrar(dicaUf(u, codigo(ft), valor), e.originalEvent);
            caminho.setStyle({ weight: 3, color: cor("--texto") });
          });
          caminho.on("mousemove", (e: L.LeafletMouseEvent) => dicaFlutuante.posicionar(e.originalEvent));
          caminho.on("mouseout", () => { dicaFlutuante.esconder(); caminho.setStyle({ weight: 1, color: cor("--superficie") }); });
        },
      }).addTo(mapa);
      mapa._camada = camada;
      enquadrarUmaVez(mapa, camada.getBounds(), [4, 4]);
    }
    if (divMapa) divMapa.hidden = !estado.geo;
    const linhas: LinhaUf[] = d.ufs.map((u) => ({ ...u, ordem: u.uf === "ZZ" ? "ZZZ" : u.nome, lider: nome(u.primeiro),
      pct1: u.primeiro ? u.primeiro.pct : null, vice: nome(u.segundo), pct2: u.segundo ? u.segundo.pct : null }));
    const formatar = (r: LinhaUf, k: keyof LinhaUf & string) => (k === "pct_secoes" || k === "pct1" || k === "pct2" ? pct(r[k])
      : k === "diferenca_pp" ? (r[k] === null ? "—" : `${fmtPct.format(r[k])} p.p.`)
        : k === "ordem" ? `${r.nome}${r.final ? " ✓" : ""}` : String(r[k] ?? "—"));
    bloco.querySelector("#brasil-tabela")?.replaceChildren(tabelaOrdenavel<LinhaUf>([["UF", "ordem"], ["Apurado", "pct_secoes", true],
      ["1º", "lider"], ["%", "pct1", true], ["2º", "vice"], ["%", "pct2", true], ["Diferença", "diferenca_pp", true]], linhas, formatar,
    null, { ordem: estado.ordem, aoOrdenar: (o) => { estado.ordem = o; } }));
  }

  return {
    estado,
    /** O bloco (criado uma vez) para pôr no cartão Presidente — BRASIL. */
    bloco(): HTMLElement {
      if (!bloco) {
        const sel = el("select", { id: "brasil-metrica", "aria-label": "Métrica do mapa por estado", onchange: () => desenhar() },
          el("option", { value: "lider" }, "Quem lidera"));
        bloco = el("div", { class: "brasil-ufs", hidden: true },
          el("h3", {}, "Por estado"),
          el("label", { class: "nota" }, "Mapa: ", sel),
          el("div", { id: "brasil-mapa", class: "mapa brasil" }),
          el("div", { id: "brasil-legenda", class: "legenda-linha" }),
          el("div", { id: "brasil-tabela", class: "tabela-rolagem brasil" }),
          el("p", { class: "nota" }, "Resultado do TSE em cada UF (o exterior só na tabela). Sem projeção nacional."));
      }
      return bloco;
    },
    async atualizar(): Promise<void> {
      if (!bloco) return;  // sem cartão Brasil (ex.: eleição sem presidente)
      try { estado.dados = await api<PresidenteUfs>("api/presidente/ufs"); } catch { return; }
      if (!estado.geo) {
        try { estado.geo = await api<GeoJSON.FeatureCollection>("geo/ufs.geojson"); } catch { estado.geo = null; }
      }
      desenhar();
    },
  };
}
