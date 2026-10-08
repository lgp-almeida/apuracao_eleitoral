/* Aba "Candidato": total na UF, ficha da cadeira, tabela por município, mini mapa, evolução na apuração e os
 * blocos de histórico e de planilha.
 * Endereço: #candidato?cargo=&numero=&municipio=&ordem=COLUNA-desc|asc[&hist=1…][&pl=1…]
 * (antigo #candidato/<cargo>/<número>[/<município>] aceito pelo roteador). */
import { graficoLinhas, type SerieLinha } from "../../componentes/grafico/linhas";
import { copiarLink } from "../../componentes/link";
import { criarCamadas } from "../../componentes/mapa/camadas";
import { criarMapa } from "../../componentes/mapa/criar";
import type { MapaApuracao } from "../../componentes/mapa/tipos";
import { tabelaOrdenavel, type Coluna } from "../../componentes/tabela";
import type { Contexto, ModuloAba } from "../../core/aba";
import { api } from "../../core/api";
import { el, refs } from "../../core/dom";
import { fmtVariacao, int, pct } from "../../core/formatos";
import { Canal, cancelado } from "../../core/pedidos";
import type { Candidatos } from "../../dados/candidatos";
import { fichasCandidato } from "./desenhar";
import { criarHistorico } from "./historico";
import { criarPlanilha } from "./planilha";
import type { ConsultaCandidato, MunicipioCandidato, PontoSerie, SerieCandidato } from "./tipos";

export interface ConsultaAtual { cargo: string; numero: string; municipio: number | null; ordem: string | null }

export interface DependenciasCandidato {
  candidatos: Candidatos;
  /** Botão "Acompanhar" dos alertas (deputados na noite), ou null quando não se aplica. */
  botaoAcompanhar(cargo: string, numero: number): HTMLElement | null;
}

export interface EstadoCandidato {
  cand: ConsultaAtual | null;
  nomesMun: Record<string, string>;
  mini: MapaApuracao | null;
}

const hm = (ms: number) => new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

export function criarAbaCandidato(ctx: Contexto, deps: DependenciasCandidato) {
  const estado: EstadoCandidato = { cand: null, nomesMun: {}, mini: null };
  const r = refs({ form: "#form-candidato", cargo: "#cand-cargo", numero: "#cand-numero", lista: "#cand-lista",
    resultado: "#cand-resultado" });
  const cargoSel = r.cargo as HTMLSelectElement, numeroIn = r.numero as HTMLInputElement;
  const { desenharMapa } = criarCamadas({ malhas: ctx.malhas, fmtDif: fmtVariacao });
  const canal = new Canal(), canalSerie = new Canal();
  const gravar = () => ctx.gravarEndereco("candidato");
  const historico = criarHistorico({ candidato: () => estado.cand, uf: ctx.uf, gravar });
  const planilha = criarPlanilha(gravar);

  async function mostrarEvolucao(cargo: string, numero: number, municipio: number): Promise<void> {
    const alvo = document.getElementById("evol-grafico");
    const sel = document.getElementById("evol-mun") as HTMLSelectElement | null;
    if (!alvo || !sel) return;
    sel.value = String(municipio);
    if (estado.cand) { estado.cand.municipio = municipio; gravar(); }
    const sinal = canalSerie.novo();
    let d: { series: SerieCandidato[] };
    try { d = await api(`api/candidato/serie?cargo=${cargo}&numero=${numero}&municipio=${municipio}`, { sinal }); } catch (e) {
      if (!cancelado(e)) alvo.replaceChildren(el("p", { class: "nota" }, `Erro: ${(e as Error).message}`));
      return;
    }
    const nomeDe = (s: SerieCandidato) => (s.abrangencia === "mun" ? estado.nomesMun[String(s.municipio)] || `município ${s.municipio}`
      : s.abrangencia === "br" ? "Brasil" : ctx.uf());
    const com = d.series.filter((s) => s.pontos.length);
    const maxPts = Math.max(0, ...com.map((s) => s.pontos.length));
    if (maxPts < 2) {
      alvo.replaceChildren(el("p", { class: "nota" },
        `A evolução aparece a partir da 2ª totalização (${maxPts} registrada${maxPts === 1 ? "" : "s"} até agora).`));
      return;
    }
    const t = (iso: string) => new Date(iso).getTime();
    const todosX = com.flatMap((s) => s.pontos.map((p) => t(p.dt)));
    const xMin = Math.min(...todosX), xMax = Math.max(...todosX);
    type Serie = SerieLinha & { xs: number[]; pontos: PontoSerie[] };
    alvo.replaceChildren(graficoLinhas<Serie>({
      xs: [], xMin, xMax, xTicks: [0, 1, 2, 3].map((i) => xMin + ((xMax - xMin) * i) / 3), xFmt: hm,
      series: com.map((s) => ({ nome: nomeDe(s), rotulo: nomeDe(s), xs: s.pontos.map((p) => t(p.dt)),
        valores: s.pontos.map((p) => p.pct), pontos: s.pontos })),
      dica: (_k, xv) => `por volta de ${hm(xv)}`,
      dicaSerie: (s, j) => `${s.nome}: ${pct(s.valores[j])} · ${int(s.pontos[j].votos)} votos · ` +
        `${pct(s.pontos[j].pct_secoes)} das seções (${hm(s.xs[j])})`,
    }));
  }

  async function consultar(cargo: string | number, numero: number, municipio: number | null = null,
      ordem: string | null = null): Promise<void> {
    ctx.mostrarAba("candidato");
    const c = estado.cand;
    if (c && (c.cargo !== String(cargo) || c.numero !== String(numero))) historico.esquecerIndicacao();
    estado.cand = { cargo: String(cargo), numero: String(numero), municipio: municipio ?? null, ordem };
    void historico.carregar();
    cargoSel.value = String(cargo);
    numeroIn.value = String(numero);
    planilha.usarNumero(String(numero));
    const sinal = canal.novo();  // a consulta mais recente é a que desenha
    let d: ConsultaCandidato;
    try { d = await api(`api/candidato?cargo=${cargo}&numero=${numero}`, { sinal }); } catch (e) {
      if (!cancelado(e)) r.resultado.replaceChildren(el("p", { class: "aviso" }, (e as Error).message));
      return;
    }
    const cargoTxt = String(cargo);
    const cab: Coluna<MunicipioCandidato>[] = [["Município", "NM_MUNICIPIO"], ["Votos", "VOTOS", true],
      ["% válidos", "PCT_VALIDOS", true], ["Posição", "POSICAO_MUN", true], ["Seções totalizadas", "PCT_SECOES_TOTALIZADAS", true]];
    const tabela = tabelaOrdenavel(cab, d.municipios, (l, k) =>
      k === "VOTOS" ? int(l[k]) : k === "PCT_VALIDOS" || k === "PCT_SECOES_TOTALIZADAS" ? pct(l[k])
        : k === "POSICAO_MUN" ? `${l[k]}º` : String(l[k]),
    (l) => void mostrarEvolucao(cargoTxt, numero, l.CD_MUNICIPIO),
    { ordem, aoOrdenar: (o) => { if (estado.cand) estado.cand.ordem = o; gravar(); } });
    const miniDiv = el("div", { id: "mini-mapa", class: "mapa mini" });
    const legenda = el("aside", { class: "legenda" });
    const selMun = el("select", { id: "evol-mun",
      onchange: (e: Event) => void mostrarEvolucao(cargoTxt, numero, Number((e.target as HTMLSelectElement).value)) },
    d.municipios.map((mu) => el("option", { value: mu.CD_MUNICIPIO }, mu.NM_MUNICIPIO)));
    estado.nomesMun = Object.fromEntries(d.municipios.map((mu) => [String(mu.CD_MUNICIPIO), mu.NM_MUNICIPIO]));
    const msgLink = el("span", { "aria-live": "polite" });
    const evol = el("section", { class: "caixa" },
      el("p", { class: "nota" }, el("button", { type: "button", class: "link",
        onclick: () => void copiarLink(ctx.endereco("candidato"), msgLink) }, "Copiar link desta consulta"), msgLink),
      el("h3", {}, "Evolução na apuração — % dos válidos do candidato no município e no estado"),
      el("div", { class: "filtros" }, el("label", {}, "Município (ou clique numa linha da tabela)", selMun)),
      el("div", { id: "evol-grafico" }));
    r.resultado.replaceChildren(...[fichasCandidato(d, ctx.uf()), deps.botaoAcompanhar(cargoTxt, d.candidato.NUMERO), evol,
      el("div", { class: "cand-duplo" }, el("div", { class: "tabela-rolagem" }, tabela), el("div", {}, miniDiv, legenda))]
      .filter((n): n is HTMLElement => n !== null));
    if (d.municipios.length) void mostrarEvolucao(cargoTxt, numero, municipio ?? d.municipios[0].CD_MUNICIPIO);
    estado.mini?.remove();
    estado.mini = criarMapa(miniDiv);
    const itens = Object.fromEntries(d.municipios.map((m) => [String(m.CD_MUNICIPIO_IBGE),
      { valor: m.PCT_VALIDOS, municipio: m.NM_MUNICIPIO }]));
    await desenharMapa(estado.mini, { tipo: "sequencial", rotulo: `% dos válidos — ${d.candidato.NOME_URNA}`, itens }, legenda, "%");
  }

  function escrever(): URLSearchParams {
    const c = estado.cand;
    const q = new URLSearchParams(c ? { cargo: c.cargo, numero: c.numero } : {});
    if (c && c.municipio !== null && c.municipio !== undefined) q.set("municipio", String(c.municipio));
    if (c && c.ordem) q.set("ordem", c.ordem);
    historico.escrever(q);
    planilha.escrever(q);
    return q;
  }

  function aplicar(q: URLSearchParams): void {
    const cargo = q.get("cargo"), numero = q.get("numero");
    if (cargo && numero) {
      // a consulta preenche o nº da planilha com o do candidato; o endereço vem depois e prevalece
      const mun = q.get("municipio");
      void consultar(cargo, Number(numero), mun ? Number(mun) : null, q.get("ordem"))
        .then(() => { planilha.aplicar(q); historico.aplicar(q); gravar(); });
    } else {
      ctx.mostrarAba("candidato");
      planilha.aplicar(q);
      historico.aplicar(q);
    }
  }

  cargoSel.addEventListener("change", () => { deps.candidatos.limpar(); void deps.candidatos.preencher(cargoSel.value, r.lista); });
  r.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const cargo = cargoSel.value;
    const numero = await deps.candidatos.resolver(cargo, numeroIn.value);
    if (numero === null) { r.resultado.replaceChildren(el("p", { class: "aviso" }, "Candidato não encontrado.")); return; }
    void consultar(cargo, numero);
  });

  const modulo: ModuloAba = {
    id: "candidato",
    escrever,
    aplicar,
    preparar: () => deps.candidatos.preencher(cargoSel.value, r.lista),
  };
  return Object.assign(modulo, { estado, consultar });
}
