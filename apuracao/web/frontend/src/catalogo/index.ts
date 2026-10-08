/* Catálogo do design system (catalogo.html, só no `npm run dev`): cada componente com dados de exemplo, desenhado
 * pelas MESMAS funções da página. Sem ?tema= mostra os dois temas lado a lado (um iframe cada: as cores dos
 * gráficos são lidas do <html> na hora de desenhar, então cada tema precisa da sua página). */
import "../pagina/tema";
import "@fontsource-variable/public-sans/wght.css";
import "../estilos/index.css";
import "./catalogo.css";
import { cartao } from "../abas/painel/cartao";
import type { Cartao } from "../abas/painel/tipos";
import { cartaoAlerta } from "../alertas/apresentacao";
import type { Nivel } from "../alertas/tipos";
import { TOKENS_DIV, TOKENS_SEQ } from "../componentes/escalas";
import { graficoDispersao } from "../componentes/grafico/dispersao";
import { graficoLinhas } from "../componentes/grafico/linhas";
import { legendaLinha, legendaMapa } from "../componentes/legenda";
import { ficha, tabelaOrdenavel } from "../componentes/tabela";
import { cor, el, ref, type Filho } from "../core/dom";
import { int, pct } from "../core/formatos";
import { desenharRegua } from "../pagina/regua";

const raiz = ref("#catalogo");
const tema = new URLSearchParams(location.search).get("tema");

const secao = (titulo: string, ...filhos: Filho[]) => el("section", { class: "cat-secao" }, el("h2", {}, titulo), filhos);
const sub = (titulo: string) => el("h3", {}, titulo);
const linha = (...filhos: Filho[]) => el("div", { class: "cat-linha" }, filhos);
const amostraCor = (token: string) => el("div", { class: "cat-cor" },
  el("div", { style: { background: `var(${token})` } }), token, el("br"), cor(token));

function cores(): HTMLElement {
  const grupos: [string, readonly string[]][] = [
    ["Superfície e texto", ["--plano", "--superficie", "--texto", "--texto-2", "--mudo", "--grade", "--eixo"]],
    ["Séries (categórico: no máximo 3 + Outros)", ["--serie-1", "--serie-2", "--serie-3", "--serie-4", "--outros", "--sem-dado"]],
    ["Status (sempre com ícone e rótulo)", ["--st-critico", "--st-aviso", "--st-noticia", "--st-ok", "--bom"]],
    ["Mapa de intensidade (YlOrRd, mesma ordem nos dois temas)", TOKENS_SEQ],
    ["Divergente", TOKENS_DIV],
    ["Sequencial azul (barras de projeção e cadeiras)", ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"]],
  ];
  return secao("Cor", grupos.map(([t, tokens]) => [sub(t), linha(tokens.map(amostraCor))]));
}

function tipoEspacoForma(): HTMLElement {
  const tamanhos = ["--fs-5", "--fs-4", "--fs-3", "--fs-2", "--fs-1"];
  return secao("Tipo, espaço e forma",
    sub("Escala de tipo (Public Sans; pesos 400 e 600; números tabulares)"),
    tamanhos.map((t) => el("div", { style: { fontSize: `var(${t})` } }, `${t} · 1.234.567 votos · 45,27% · 21:34`)),
    el("div", { style: { fontSize: "var(--fs-2)", fontWeight: "600" } }, "Peso 600 · 111.111 × 999.999"),
    sub("Espaço"),
    ["--esp-1", "--esp-2", "--esp-3", "--esp-4", "--esp-5", "--esp-6"].map((t) =>
      linha(el("code", { style: { width: "64px" } }, t), el("div", { class: "cat-esp", style: { width: `var(${t})` } }))),
    sub("Raio: controle, caixa, selo"),
    linha(["--raio-controle", "--raio-caixa", "--raio-selo"].map((t) =>
      el("div", {}, el("div", { class: "cat-raio", style: { borderRadius: `var(${t})` } }), el("code", {}, t)))));
}

function cabecalho(): HTMLElement {
  const regua = el("div", { class: "regua", role: "progressbar" });
  const trilho = el("div", { class: "regua-trilho" }, el("div", { class: "regua-feito" }));
  desenharRegua(regua, trilho, { uf: "RJ", pct: 63.4, hora: new Date().toISOString(), final: false });
  const abas = el("nav", { class: "abas", role: "tablist" }, ["Painel", "Candidato", "Mapas"].map((t, i) =>
    el("button", { type: "button", role: "tab", "aria-selected": String(i === 0) }, t)));
  return secao("Cabeçalho e régua de apuração",
    el("div", { class: "cat-topo" },
      el("div", { class: "marca" }, el("h1", {}, "Apuração 2026 — RJ"), el("span", { class: "selo oficial" }, "OFICIAL"),
        el("span", { class: "selo" }, "ambiente: simulado")),
      regua, abas, trilho));
}

function controles(): HTMLElement {
  const sel = el("select", {}, el("option", {}, "Governador"), el("option", {}, "Senador"));
  return secao("Controles",
    el("form", { class: "filtros", onsubmit: (e: Event) => e.preventDefault() },
      el("label", {}, "Cargo", sel),
      el("label", {}, "Número ou nome", el("input", { placeholder: "ex.: 13713" })),
      el("fieldset", { class: "grupo" }, el("legend", {}, "Grupo"),
        el("label", {}, "Ano", el("select", {}, el("option", {}, "2026"))),
        el("label", { class: "check" }, el("input", { type: "checkbox", checked: true }), "Ponderar")),
      el("button", { type: "submit" }, "Atualizar mapa")),
    linha(el("button", { type: "button", class: "botao" }, "Acompanhar nos alertas"),
      el("button", { type: "button", class: "link" }, "Copiar link"),
      el("button", { type: "button", class: "link" }, "Baixar PNG")));
}

const EXEMPLO: Cartao = {
  cargo: 3, ds_cargo: "Governador", abrangencia: "RJ", proporcional: false, n_candidatos: 4,
  totais: { ELEITORADO: 12_842_517, COMPARECIMENTO: 9_845_867, ABSTENCAO: 2_996_650, VALIDOS: 8_394_627, BRANCOS: 501_537,
    NULOS: 675_292, PCT_SECOES_TOTALIZADAS: 63.4, SECOES_TOTALIZADAS: 23_890, SECOES_TOTAL: 37_675, DT_TOTALIZACAO: null },
  candidatos: [
    { NUMERO: 22, NOME_URNA: "CANDIDATA COM NOME BEM LONGO", PARTIDO: "AAA", VOTOS: 4_130_000, PCT_VALIDOS: 49.2, ELEITO: true, SITUACAO: "2º turno" },
    { NUMERO: 55, NOME_URNA: '"Zé" <b>da Silva</b>', PARTIDO: "BBB", VOTOS: 3_590_000, PCT_VALIDOS: 42.8, SITUACAO: "2º turno" },
    { NUMERO: 10, NOME_URNA: "TERCEIRO", PARTIDO: "CCC", VOTOS: 266_000, PCT_VALIDOS: 3.2, SITUACAO: "Não eleito" },
    { NUMERO: 50, NOME_URNA: "QUARTO", PARTIDO: "DDD", VOTOS: 227_000, PCT_VALIDOS: 2.7, SITUACAO: "Não eleito" }],
  serie: { pontos: [10, 25, 40, 63.4].map((p, i) => ({ dt: `2026-10-04T19:${10 + i}:00`, pct_secoes: p })),
    series: [{ NOME: "A", CHAVE: "22", PARTIDO: "AAA", valores: [44, 47, 48.5, 49.2] }, { NOME: "B", CHAVE: "55", PARTIDO: "BBB", valores: [47, 44.5, 43, 42.8] },
      { NOME: "C", CHAVE: "10", PARTIDO: "CCC", valores: [4, 3.6, 3.3, 3.2] }] },
};

function caixas(): HTMLElement {
  const ctx = { destacar: new Set<string>(), abertos: new Set<number>(), consultarCandidato: () => undefined,
    blocoBrasil: () => el("div") };
  return secao("Superfícies",
    el("div", { class: "aviso" }, "Aviso: ainda não há resultados coletados."),
    el("details", { class: "caixa", open: true }, el("summary", {}, "Caixa recolhível"), el("p", { class: "nota" }, "Nota em texto de apoio.")),
    sub("Fichas"),
    el("div", { class: "fichas" }, ficha("Votos", int(1_043_551)), ficha("% dos válidos", pct(12.34)), ficha("Situação", "Eleito por QP")),
    sub("Cartão do painel (o texto do TSE entra como texto)"),
    el("div", { class: "cat-largura" }, cartao(EXEMPLO, ctx)));
}

function tabelasEGraficos(): HTMLElement {
  type L = { NOME: string; VOTOS: number; PCT: number };
  const linhas: L[] = [{ NOME: "Niterói", VOTOS: 123_456, PCT: 45.67 }, { NOME: "Maricá", VOTOS: 45_678, PCT: 51.2 },
    { NOME: "São Gonçalo", VOTOS: 234_567, PCT: 39.01 }];
  const tabela = tabelaOrdenavel<L>([["Município", "NOME"], ["Votos", "VOTOS", true], ["%", "PCT", true]], linhas,
    (r, k) => (k === "NOME" ? r.NOME : k === "VOTOS" ? int(r.VOTOS) : pct(r.PCT)), () => undefined);
  const pontos = Array.from({ length: 40 }, (_, i) => {
    const x = 5 + ((i * 37) % 60);
    return { X: x, Y: 20 + 0.5 * x + (((i * 53) % 21) - 10), BAIRRO: `Bairro ${i + 1}`, VALIDOS: 1000 + i * 50, RESIDUO: 0 };
  });
  return secao("Tabelas e gráficos",
    el("div", { class: "tabela-rolagem cat-largura" }, tabela),
    sub("Linhas"),
    el("div", { class: "cat-largura" }, graficoLinhas({
      xs: [10, 25, 40, 63.4], xMin: 0, xMax: 100, xTicks: [0, 25, 50, 75, 100], xFmt: (t) => `${t}%`,
      series: [{ nome: "A", rotulo: "22 A (AAA)", valores: [44, 47, 48.5, 49.2] }, { nome: "B", rotulo: "55 B (BBB)", valores: [47, 44.5, 43, 42.8] }],
      dica: (k) => `${[10, 25, 40, 63.4][k]}% das seções` })),
    sub("Dispersão"),
    el("div", { class: "cat-largura" }, graficoDispersao({ pontos, rotulo_x: "Renda (R$)", rotulo_y: "% dos válidos",
      estatistica: { a: 20, b: 0.5 } }, "pct", (v) => `${v}%`, "Bairro")),
    sub("Barras e legendas"),
    el("div", { class: "cat-largura" },
      el("div", { class: "progresso" }, el("div", { style: { width: "63%" } })),
      el("div", { class: "composicao", style: { marginTop: "8px" } },
        ["--serie-1", "--serie-2", "--serie-3"].map((t, i) => el("div", { style: { width: `${[70, 20, 10][i]}%`, background: `var(${t})` } }))),
      legendaLinha([[cor("--serie-1"), "Válidos"], [cor("--serie-2"), "Brancos"], [cor("--serie-3"), "Nulos"]])),
    el("div", { class: "legenda", style: { maxWidth: "260px", marginTop: "12px" } },
      legendaMapa("Abstenção (%)", TOKENS_SEQ.map((t, i) => [cor(t), `${15 + 3 * i}% – ${18 + 3 * i}%`]))));
}

function alertas(): HTMLElement {
  const niveis: Nivel[] = ["critico", "aviso", "noticia", "ok"];
  return secao("Alertas", el("div", { class: "cat-largura", style: { display: "grid", gap: "8px" } },
    niveis.map((n) => cartaoAlerta({ nivel: n, titulo: `Alerta de nível ${n}`, detalhe: "Detalhe do que houve e do que fazer.",
      momento: new Date().toISOString() }, n === "critico" ? () => undefined : null))));
}

if (tema === null) {
  raiz.className = "cat-lados";
  raiz.replaceChildren(...["claro", "escuro"].map((t) =>
    el("iframe", { src: `catalogo.html?tema=${t}`, title: `Catálogo, tema ${t}` })));
} else {
  raiz.replaceChildren(el("h1", {}, `Catálogo — tema ${tema}`), cores(), tipoEspacoForma(), cabecalho(), controles(),
    caixas(), tabelasEGraficos(), alertas());
}
