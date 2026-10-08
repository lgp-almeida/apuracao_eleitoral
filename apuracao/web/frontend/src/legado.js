/* Apuração 2026 — página do site local (código anterior à refatoração, migrado aos poucos para módulos).
 * Todo texto vindo dos dados entra por textContent (o TSE testa nomes com aspas e símbolos). */
import * as L from "leaflet";
import { criarAbaCandidato } from "./abas/candidato/index.ts";
import { criarAbaComparacao } from "./abas/comparacao/index.ts";
import { criarAbaMapas } from "./abas/mapas/index.ts";
import { criarAbaPerfil } from "./abas/perfil/index.ts";
import { criarAbaTransferencia } from "./abas/transferencia/index.ts";
import { dicaFlutuante } from "./componentes/dica.ts";
import { quebrasQuantis } from "./componentes/escalas.ts";
import { graficoLinhas } from "./componentes/grafico/linhas.ts";
import { copiarLink } from "./componentes/link.ts";
import { criarMapa } from "./componentes/mapa/criar.ts";
import { exportarMapa } from "./componentes/mapa/exportar.ts";
import { tabelaOrdenavel } from "./componentes/tabela.ts";
import { repetir } from "./core/agendador.ts";
import { api, enviar } from "./core/api.ts";
import { NOMES_CARGO } from "./core/cargos.ts";
import { cor, el } from "./core/dom.ts";
import { fmtFreq, fmtInt, fmtPct, hora, int, pct } from "./core/formatos.ts";
import { gravarJson, gravarPreferencia, lerJson, lerPreferencia } from "./core/preferencias.ts";
import { Roteador } from "./core/roteador.ts";
import { lerEndereco } from "./core/rotas.ts";
import { criarCandidatos } from "./dados/candidatos.ts";
import { criarMalhas } from "./dados/malhas.ts";

const REFRESH_MS = 60_000;
const estado = { aba: "painel", uf: "", ano: 2026, mapa: null,
  destacar: new Set(), destacarDefinido: false, cadAbertos: new Set(), painel: null };
// endereço de cada aba: tabela no fim do arquivo (roteador.registrar)
const roteador = new Roteador(mostrarAba, () => estado.aba);
// abas já migradas para abas/<aba>/ (registradas no fim do arquivo)
const candidatos = criarCandidatos();  // listas de candidatos por cargo: abas Candidato e Mapas
const malhas = criarMalhas();  // municípios, bairros e áreas de ponderação, uma vez por página
const modulos = new Map();
const contexto = { uf: () => estado.uf, turno: () => estado.turno || 1, ano: () => estado.ano, mostrarAba,
  gravarEndereco: (a) => roteador.gravar(a), endereco: (a) => roteador.endereco(a), malhas,
  registrarMapa: (nome, mapa) => { estado[nome] = mapa; } };

// ---------------------------------------------------------------- abas
document.querySelectorAll(".abas button").forEach((b) =>
  b.addEventListener("click", () => mostrarAba(b.dataset.aba)));

function mostrarAba(aba) {
  estado.aba = aba;
  roteador.aoMostrar(aba);
  document.querySelectorAll(".abas button").forEach((b) => b.setAttribute("aria-selected", b.dataset.aba === aba));
  document.querySelectorAll(".aba").forEach((s) => (s.hidden = s.id !== `aba-${aba}`));
  modulos.get(aba)?.aoMostrar?.();
}

// ---------------------------------------------------------------- status
async function atualizarStatus() {
  const box = document.getElementById("situacao");
  try {
    const s = await api("api/status");
    estado.uf = s.uf;
    estado.turno = s.coletor.turno || 1;
    estado.ultimoBoletim = s.ultimo_boletim;
    estado.ultimaColeta = s.coletor.ultimo_ciclo_fim || s.coletor.ultimo_ciclo_inicio;
    destaqueInicial(s.destacar_padrao);
    estado.ano = s.coletor.ano || 2026;  // resultados históricos (importar_resultado_historico.py) trazem o ano
    document.getElementById("titulo").textContent = `Apuração ${estado.ano} — ${s.uf}`;
    document.title = `Apuração ${estado.ano} — ${s.uf}`;
    if (typeof atualizarTituloAlertas === "function") atualizarTituloAlertas();
    document.getElementById("rotulo-locais").textContent = ` Locais de votação ${estado.ano}`;
    const amb = s.coletor.ambiente || "?";
    const selo = document.getElementById("ambiente");
    selo.textContent = amb === "oficial" ? "OFICIAL" : `ambiente: ${amb}`;
    selo.className = "selo" + (amb === "oficial" ? " oficial" : "");
    const partes = s.progresso.map((p) =>
      `${p.ABRANGENCIA === "br" ? "Brasil" : p.UF} (eleição ${p.ELEICAO}): ${pct(p.PCT_SECOES_TOTALIZADAS)} das seções` +
      (p.TOTALIZACAO_FINAL ? " — final" : ""));
    limitarCargos(s.cargos || []);
    const quando = s.coletor.ano ? "Importado em" : "Última coleta";
    box.replaceChildren(...[
      el("div", {}, partes.join(" · ") || "sem dados de apuração"),
      el("div", {}, `${quando}: ${hora(s.coletor.ultimo_ciclo_fim || s.coletor.ultimo_ciclo_inicio)}`),
      s.coletor.erro ? el("div", { class: "erro" }, "⚠ ", s.coletor.erro) : null,
    ].filter(Boolean));
    document.getElementById("painel-vazio").hidden = s.tem_dados;
  } catch (e) {
    box.replaceChildren(el("div", { class: "erro" }, `⚠ servidor indisponível: ${e.message}`));
  }
}

// só os cargos presentes nos dados (ex.: 2º turno de 2022 no RJ só tem presidente)
function limitarCargos(cargos) {
  if (!cargos.length) return;
  for (const id of ["cand-cargo", "mapa-cargo"]) {
    const sel = document.getElementById(id);
    for (const op of sel.options) op.hidden = op.disabled = !cargos.includes(Number(op.value));
    if (sel.selectedOptions[0]?.disabled) {
      sel.value = String(cargos.find((c) => [...sel.options].some((o) => o.value === String(c))));
      sel.dispatchEvent(new Event("change"));
    }
  }
}

// ---------------------------------------------------------------- painel
async function atualizarPainel() {
  let dados;
  try { dados = await api("api/painel"); } catch (e) { return; }
  estado.painel = dados;
  desenharPainel();
  atualizarBrasil();
}

function desenharPainel() {
  if (!estado.painel) return;
  const grade = document.getElementById("cartoes");
  grade.replaceChildren(...estado.painel.cartoes.map(cartao));
  opcoesDestaque(estado.painel.cartoes);
  aplicarTv();
}

// ---------------------------------------------------------------- o que mudou desde o último boletim (rodada 33)
async function atualizarMudancas() {
  let r;
  try { r = await api("api/mudancas"); } catch (_) { return; }
  const caixa = document.getElementById("mudancas");
  caixa.hidden = !r.anterior;
  if (!r.anterior) return;
  const quando = new Date(r.anterior.gerado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  document.getElementById("mudancas-titulo").textContent =
    `O que mudou desde o ${r.anterior.titulo.startsWith("Boletim") ? r.anterior.titulo.toLowerCase() : r.anterior.titulo} (${quando})`;
  document.getElementById("mudancas-lista").replaceChildren(...(r.mudancas.length
    ? r.mudancas.map((m) => el("li", {}, el("strong", {}, m.cargo), `: ${m.texto}`))
    : [el("li", {}, "Nada mudou nos números do boletim.")]));
}

// ---------------------------------------------------------------- modo TV (rodada 33)
// #painel?tv=1: tela cheia, um cargo por vez (troca a cada 20 s), alertas e "o que mudou" visíveis.
// Esc sai; ←/→ navegam; espaço pausa.
const TV_MS = 20_000;
estado.tv = { ativo: false, idx: 0, pausado: false, timer: null };

function aplicarTv() {
  const tv = estado.tv;
  const cartoes = [...document.querySelectorAll("#cartoes .cartao")];
  cartoes.forEach((c, i) => c.classList.toggle("tv-atual", tv.ativo && i === tv.idx % Math.max(cartoes.length, 1)));
  const barra = document.getElementById("tv-barra");
  barra.hidden = !tv.ativo;
  if (!tv.ativo || !cartoes.length) return;
  const atual = estado.painel?.cartoes[tv.idx % cartoes.length];
  const bol = estado.ultimoBoletim;
  barra.replaceChildren(
    el("span", {}, el("strong", {}, atual ? `${atual.ds_cargo} — ${atual.abrangencia}` : ""),
      ` (${(tv.idx % cartoes.length) + 1} de ${cartoes.length})${tv.pausado ? " · pausado" : ""}`),
    el("span", {}, `Última coleta: ${hora(estado.ultimaColeta)}`),
    el("span", {}, bol ? `Último boletim: ${bol.titulo} (${hora(bol.gerado_em)})` : "Sem boletim ainda"),
    el("span", {}, "Esc sai · ←/→ navega · espaço pausa"));
}

function modoTv(ligar) {
  const tv = estado.tv;
  tv.ativo = ligar;
  document.body.classList.toggle("modo-tv", ligar);
  clearInterval(tv.timer);
  tv.timer = ligar ? setInterval(() => { if (!tv.pausado) { tv.idx += 1; aplicarTv(); } }, TV_MS) : null;
  if (ligar && estado.aba !== "painel") mostrarAba("painel");
  if (ligar && document.documentElement.requestFullscreen && !document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => { /* sem gesto do usuário: segue sem tela cheia */ });
  }
  if (!ligar && document.fullscreenElement) document.exitFullscreen().catch(() => {});
  roteador.gravar("painel");  // tv=1 entra (ou sai) do endereço
  aplicarTv();
}

document.getElementById("botao-tv").addEventListener("click", () => modoTv(true));
document.addEventListener("keydown", (e) => {
  const tv = estado.tv;
  if (!tv.ativo) return;
  if (e.key === "Escape") modoTv(false);
  else if (e.key === "ArrowRight") { tv.idx += 1; aplicarTv(); }
  else if (e.key === "ArrowLeft") { tv.idx = Math.max(0, tv.idx - 1); aplicarTv(); }
  else if (e.key === " ") { e.preventDefault(); tv.pausado = !tv.pausado; aplicarTv(); }
});
document.addEventListener("fullscreenchange", () => {  // saiu da tela cheia pelo navegador: sai do modo TV
  if (!document.fullscreenElement && estado.tv.ativo && estado.tv.telaCheia) modoTv(false);
  estado.tv.telaCheia = Boolean(document.fullscreenElement);
});

// ---------------------------------------------------------------- destaque de partidos/federações (rodada 31)
// Um candidato é destacado se o PARTIDO ou a AGREMIACAO (federação = todos os seus partidos) foi escolhido.
// A escolha vale para as listas de eleitos dos dois cargos, fica no navegador e no endereço #painel?destacar=.
const destacado = (x) => estado.destacar.has(x.PARTIDO) || estado.destacar.has(x.AGREMIACAO);

function definirDestaque(lista, gravar = true) {
  estado.destacar = new Set(lista.filter(Boolean));
  estado.destacarDefinido = true;
  if (gravar) {  // escolha do usuário: fica no navegador e no endereço
    gravarJson("destacar", [...estado.destacar]);
    roteador.gravar("painel");
  }
  desenharPainel();
}

function parametrosPainel() {
  const q = new URLSearchParams();
  if (estado.destacar.size) q.set("destacar", [...estado.destacar].join(","));
  if (estado.tv?.ativo) q.set("tv", "1");
  return q;
}

function aplicarEnderecoPainel(q) {
  if (q.get("destacar") !== null) definirDestaque(q.get("destacar").split(","), true);
  mostrarAba("painel");
  if (q.get("tv") === "1") modoTv(true);
}

function destaqueInicial(padrao) {  // endereço > navegador > --destacar do site (sem reescrever o endereço)
  if (estado.destacarDefinido) return;
  const { aba, params } = lerEndereco(location.hash);
  const doEndereco = aba === "painel" ? params.get("destacar") : null;
  if (doEndereco !== null) { definirDestaque(doEndereco.split(","), false); return; }
  const salvo = lerJson("destacar");
  definirDestaque(Array.isArray(salvo) ? salvo : (padrao || []), false);
}

function opcoesDestaque(cartoes) {
  const caixa = document.getElementById("destaque");
  const comp = new Map();
  for (const c of cartoes) for (const a of c.cadeiras?.composicao || []) if (!comp.has(a.AGREMIACAO)) comp.set(a.AGREMIACAO, a.PARTIDOS);
  caixa.hidden = !comp.size;
  document.getElementById("destaque-resumo").textContent =
    estado.destacar.size ? `(${[...estado.destacar].join(", ")})` : "(nenhum)";
  const marca = (valor, rotulo) => el("label", {}, el("input", { type: "checkbox", value: valor,
    checked: estado.destacar.has(valor), onchange: (e) => {
      const novo = new Set(estado.destacar);
      if (e.target.checked) novo.add(valor); else novo.delete(valor);
      definirDestaque([...novo]);
    } }), rotulo);
  const itens = [...comp].map(([ag, partidos]) => (partidos.length > 1 || partidos[0] !== ag
    ? el("fieldset", {}, el("legend", {}, "Federação"), marca(ag, ag), ...partidos.map((pt) => marca(pt, pt)))
    : marca(ag, ag)));
  const alvo = document.getElementById("destaque-opcoes");
  const foco = document.activeElement?.value;  // redesenho a cada 60 s: mantém o foco do teclado
  alvo.replaceChildren(...itens);
  if (foco) alvo.querySelector(`input[value="${CSS.escape(foco)}"]`)?.focus();
}

function botaoSalvarLista(cargo) {
  const q = new URLSearchParams({ cargo });
  if (estado.destacar.size) q.set("destacar", [...estado.destacar].join(","));
  return el("a", { class: "botao-salvar", href: `api/cadeiras/planilha?${q}`, download: "" }, "Salvar lista (.xlsx)");
}

// <details> das listas: reabre depois do redesenho de 60 s e conta os destacados quando a lista chega
function detalhesLista(cargo, resumo, conteudo, carregar) {
  const sumario = el("summary", {}, resumo);
  const det = el("details", {
    ontoggle: async (e) => {
      if (e.target.open) estado.cadAbertos.add(cargo); else estado.cadAbertos.delete(cargo);
      if (!e.target.open || conteudo.childElementCount) return;
      conteudo.textContent = "carregando…";
      try {
        const n = await carregar();
        if (estado.destacar.size) sumario.textContent = `${resumo} — ${n} destacado(s)`;
      } catch (err) { conteudo.textContent = `não foi possível carregar: ${err.message}`; }
    },
  }, sumario, conteudo);
  if (estado.cadAbertos.has(cargo)) det.open = true;
  return det;
}

// projeção do resultado final (majoritários): faixa da margem, ponto na projeção, traço no parcial
function blocoProjecao(p) {
  const cProj = cor("--seq-5"), cFaixa = cor("--seq-2"), cParcial = cor("--texto");
  const topo = Math.min(100, Math.max(...p.candidatos.map((x) => x.MAX || 0), p.cargo === 3 ? 52 : 0) * 1.05 || 1);
  const x = (v) => `${Math.max(0, Math.min(100, (100 * (v || 0)) / topo))}%`;
  const linhas = p.candidatos.map((k) => el("div", { class: "proj-item",
    title: `${k.NOME_URNA}: parcial ${pct(k.PCT_ATUAL)} · projeção ${pct(k.PCT_PROJ)} (${pct(k.MIN)} a ${pct(k.MAX)})` },
  el("span", { class: "nome" }, `${k.NUMERO} ${k.NOME_URNA}`),
  el("span", { class: "proj-trilho" },
    p.cargo === 3 ? el("span", { class: "proj-50", style: { left: x(50) } }) : null,
    el("span", { class: "proj-faixa", style: { left: x(k.MIN), width: `calc(${x(k.MAX)} - ${x(k.MIN)})`, background: cFaixa } }),
    el("span", { class: "proj-parcial", style: { left: x(k.PCT_ATUAL), background: cParcial } }),
    el("span", { class: "proj-ponto", style: { left: x(k.PCT_PROJ), background: cProj } })),
  el("span", { class: "num" }, pct(k.PCT_PROJ))));
  const faltam = el("div", { class: "cad-eleitos" });
  const det = el("details", {
    ontoggle: async (e) => {
      if (!e.target.open || faltam.childElementCount) return;
      faltam.textContent = "carregando…";
      try {
        const d = await api(`api/projecao?cargo=${p.cargo}`);
        faltam.replaceChildren(el("table", {}, el("thead", {}, el("tr", {}, ["Município", "Eleitorado apurado", "Válidos que faltam (est.)"]
          .map((t, i) => el("th", { class: i ? "num" : null }, t)))),
        el("tbody", {}, d.faltam.map((m) => el("tr", {}, el("td", {}, m.NM_MUNICIPIO || String(m.CD_MUNICIPIO)),
          el("td", { class: "num" }, pct(m.PCT_APURADO)), el("td", { class: "num" }, int(m.VALIDOS_RESTANTES)))))));
      } catch (err) { faltam.textContent = `não foi possível carregar: ${err.message}`; }
    },
  }, el("summary", {}, "Onde faltam votos"), faltam);
  return [
    el("h3", {}, "Projeção do resultado final"),
    el("div", { class: "sub" }, `${pct(p.pct_apurado)} do eleitorado apurado · margem ±${fmtPct.format(p.margem_pp ?? 0)} p.p. ` +
      `(erro de 95% das projeções na apuração de 2022) · ${p.municipios_sem_apuracao} município(s) ainda sem apuração`),
    el("p", { class: "proj-situacao" }, p.situacao),
    el("div", { class: "legenda-linha" },
      el("span", {}, el("span", { class: "amostra", style: { background: cProj } }), "Projeção"),
      el("span", {}, el("span", { class: "amostra", style: { background: cFaixa } }), "Margem"),
      el("span", {}, el("span", { class: "amostra", style: { background: cParcial, width: "3px" } }), "Parcial agora"),
      p.cargo === 3 ? el("span", {}, "┆ 50% dos válidos") : null),
    el("div", { class: "proj-lista" }, linhas),
    det,
    el("p", { class: "nota" }, "Cada município completa o que falta com o voto já apurado nele. No RJ em 2022, até ~40% " +
      "apurado a projeção errou mais que o parcial (a capital apura por zonas); daí em diante, errou menos. A margem cobre os dois."),
  ];
}


// cadeiras sobre os votos PROJETADOS (a partir de 30% apurado): faixa de cadeiras e eleitos consolidados × em disputa
// agremiações com algum escolhido: a própria (partido ou federação) ou um partido da federação
function agremiacoesDestacadas(k) {
  return new Set((k.composicao || []).filter((a) => estado.destacar.has(a.AGREMIACAO)
    || a.PARTIDOS.some((pt) => estado.destacar.has(pt))).map((a) => a.AGREMIACAO));
}

function blocoCadeirasProjetadas(k) {
  const p = k.projecao;
  const cFirme = cor("--seq-4"), cFaixa = cor("--seq-2");
  const max = Math.max(...p.agremiacoes.map((a) => a.VAGAS_MAX), 1);
  const agrDest = agremiacoesDestacadas(k);
  const linhas = p.agremiacoes.map((a) => el("div", { class: agrDest.has(a.AGREMIACAO) ? "cad-item destaque" : "cad-item",
    title: `${a.AGREMIACAO}: ${int(a.VOTOS)} votos projetados · ${a.VAGAS} cadeira(s) na projeção; de ${a.VAGAS_MIN} a ${a.VAGAS_MAX} em 90% das simulações` },
  el("span", { class: "nome" }, a.AGREMIACAO),
  el("span", { class: "cad-barra" },
    a.VAGAS_MIN ? el("span", { style: { width: `${(100 * a.VAGAS_MIN) / max}%`, background: cFirme } }) : null,
    a.VAGAS_MAX > a.VAGAS_MIN ? el("span", { style: { width: `${(100 * (a.VAGAS_MAX - a.VAGAS_MIN)) / max}%`, background: cFaixa } }) : null),
  el("span", { class: "num cad-faixa" }, a.VAGAS_MAX > a.VAGAS_MIN ? `${a.VAGAS} (${a.VAGAS_MIN}–${a.VAGAS_MAX})` : String(a.VAGAS))));
  const disputa = p.em_disputa_dentro + p.em_disputa_fora;
  const lista = el("div", { class: "cad-eleitos" });
  const det = detalhesLista(k.cargo, `Ver consolidados e a disputa (${p.consolidados + disputa} candidatos)`, lista, async () => {
    const d = await api(`api/cadeiras?cargo=${k.cargo}`);
    const curto = { "consolidado": "consolidado", "em disputa (dentro)": "disputa, dentro", "em disputa (fora)": "disputa, fora" };
    const classe = (x) => [x.STATUS === "consolidado" ? null : "cad-disputa", destacado(x) ? "destaque" : null].filter(Boolean).join(" ") || null;
    lista.replaceChildren(el("table", {}, el("thead", {}, el("tr", {}, [["Candidato"], ["Votos proj."],
      ["Situação"], ["Sim.", `% das ${p.simulacoes} simulações em que se elege`]]
      .map(([t, dica], i) => el("th", { class: i === 1 || i === 3 ? "num" : null, title: dica }, t)))),
    el("tbody", {}, d.projecao.candidatos.map((x) => el("tr", { class: classe(x) },
      el("td", {}, `${destacado(x) ? "★ " : ""}${x.NUMERO} ${x.NOME}`, el("br"), el("small", {}, `${x.PARTIDO} · ${x.AGREMIACAO}`)),
      el("td", { class: "num" }, int(x.VOTOS_PROJ)),
      el("td", {}, curto[x.STATUS] || x.STATUS), el("td", { class: "num" }, fmtFreq(x.FREQ_ELEITO)))))));
    return d.projecao.candidatos.filter(destacado).length;
  });
  return [
    el("h3", {}, `Cadeiras projetadas — ${k.vagas} vagas`),
    el("div", { class: "sub" }, `Projeção com ${pct(p.pct_apurado)} do eleitorado apurado · QE projetado ${int(p.qe)}`),
    el("p", { class: "proj-situacao" }, `${p.consolidados} eleitos consolidados · ${k.vagas - p.consolidados} vagas em disputa ` +
      `entre ${disputa} candidatos`),
    el("div", { class: "legenda-linha" },
      el("span", {}, el("span", { class: "amostra", style: { background: cFirme } }), "Cadeiras firmes (mínimo)"),
      el("span", {}, el("span", { class: "amostra", style: { background: cFaixa } }), "Podem vir (até o máximo)")),
    el("div", { class: "cad-lista", role: "list" }, linhas),
    k.consistente ? null : el("p", { class: "aviso" }, `Atenção: os votos das agremiações (${int(k.soma_agremiacoes)}) ` +
      `não somam os válidos (${int(k.validos)}); a projeção pode estar incompleta.`),
    det, botaoSalvarLista(k.cargo),
    el("p", { class: "nota" }, `Votos projetados por município e ${p.simulacoes} simulações com o erro medido na apuração de 2022. ` +
      `Consolidado = eleito em ≥ ${Math.round(100 * p.limiar)}% das simulações; faixa = 90% das simulações. Em 2022 (RJ), ` +
      "de ~640 consolidados ao longo da apuração só 1 não se elegeu, e as faixas cobriram 481 de 482 casos (calibração e teste " +
      "na mesma eleição)."),
  ].filter(Boolean);
}

// cadeiras (deputados): barra empilhada QP + média por agremiação, eleitos sob demanda
function blocoCadeiras(k) {
  if (k.projecao && k.projecao.ativa) return blocoCadeirasProjetadas(k);
  const cQp = cor("--serie-1"), cMedia = cor("--seq-2");
  const max = Math.max(...k.agremiacoes.map((a) => a.VAGAS), 1);
  const estagio = k.final ? "resultado final" : `projeção com ${pct(k.pct_secoes)} das seções — muda até o fim da apuração`;
  const confere = k.conferencia_tse ? ` · confere com o TSE: ${k.conferencia_tse.coincidentes} de ${k.conferencia_tse.eleitos_tse} eleitos` : "";
  const agrDest = agremiacoesDestacadas(k);
  const linhas = k.agremiacoes.map((a) => el("div", { class: agrDest.has(a.AGREMIACAO) ? "cad-item destaque" : "cad-item",
    title: `${a.NOME}: ${int(a.VOTOS)} votos (${fmtPct.format(a.PCT_QE)}% do QE) · ${a.VAGAS_QP} por QP + ${a.VAGAS_MEDIA} por média` },
    el("span", { class: "nome" }, a.NOME),
    el("span", { class: "cad-barra" },
      a.VAGAS_QP ? el("span", { style: { width: `${(100 * a.VAGAS_QP) / max}%`, background: cQp } }) : null,
      a.VAGAS_MEDIA ? el("span", { style: { width: `${(100 * a.VAGAS_MEDIA) / max}%`, background: cMedia } }) : null),
    el("span", { class: "num" }, String(a.VAGAS))));
  const eleitos = el("div", { class: "cad-eleitos" });
  const det = detalhesLista(k.cargo, `Ver os ${k.vagas} eleitos projetados`, eleitos, async () => {
    const d = await api(`api/cadeiras?cargo=${k.cargo}`);
    const cab = [["Eleito"], ["Partido", "a federação aparece abaixo do partido"], ["Votos"],
      ["Via", "QP = quociente partidário; média = sobras"], ["Folga", "votos à frente do 1º suplente da mesma agremiação"]];
    eleitos.replaceChildren(el("table", {}, el("thead", {}, el("tr", {}, cab
      .map(([t, dica], i) => el("th", { class: i === 2 || i === 4 ? "num" : null, title: dica }, t)))),
    el("tbody", {}, d.eleitos.map((x) => el("tr", { class: destacado(x) ? "destaque" : null },
      el("td", {}, `${destacado(x) ? "★ " : ""}${x.NUMERO} ${x.NOME}`),
      el("td", {}, x.PARTIDO, x.AGREMIACAO !== x.PARTIDO ? [el("br"), el("small", {}, x.AGREMIACAO)] : null),
      el("td", { class: "num" }, int(x.VOTOS)), el("td", {}, x.SITUACAO_PROJETADA === "Eleito por QP" ? "QP" : "média"),
      el("td", { class: "num" }, x.MARGEM === null ? "—" : int(x.MARGEM)))))));
    return d.eleitos.filter(destacado).length;
  });
  return [
    el("h3", {}, `Cadeiras projetadas — ${k.vagas} vagas`),
    el("div", { class: "sub" }, `QE ${int(k.qe)} · ${k.eleitos_qp} por QP + ${k.eleitos_media} por média · ${estagio}${confere}`),
    el("div", { class: "legenda-linha" }, el("span", {}, el("span", { class: "amostra", style: { background: cQp } }), "Quociente partidário (QP)"),
      el("span", {}, el("span", { class: "amostra", style: { background: cMedia } }), "Sobras (maior média)")),
    el("div", { class: "cad-lista", role: "list" }, linhas),
    k.vagas_nao_preenchidas ? el("p", { class: "nota" }, `${k.vagas_nao_preenchidas} vaga(s) sem candidato apto na projeção.`) : null,
    k.consistente ? null : el("p", { class: "aviso" }, `Atenção: os votos das agremiações (${int(k.soma_agremiacoes)}) ` +
      `não somam os válidos (${int(k.validos)}); a projeção pode estar incompleta.`),
    det, botaoSalvarLista(k.cargo),
    k.projecao ? el("p", { class: "nota" }, `Distribuição sobre os votos PARCIAIS; a projeção de cadeiras começa com ` +
      `${fmtInt.format(k.projecao.pct_minimo)}% do eleitorado apurado (agora ${pct(k.projecao.pct_apurado)}).`) : null,
    el("p", { class: "nota" }, `Regra de 2026 (QE, QP com 10% do QE por candidato, sobras em 2 fases — art. 12-A). Fonte: ${k.fonte}.`),
  ].filter(Boolean);
}

function composicao(segmentos, total) {
  const barras = segmentos.filter((s) => s.valor > 0).map((s) =>
    el("div", { style: { width: `${(100 * s.valor) / total}%`, background: s.cor }, title: `${s.rotulo}: ${int(s.valor)}` }));
  const legenda = segmentos.map((s) =>
    el("span", {}, el("span", { class: "amostra", style: { background: s.cor } }),
      `${s.rotulo} ${int(s.valor)} (${pct((100 * s.valor) / total)})`));
  return [el("div", { class: "composicao", role: "img", "aria-label": legenda.map((l) => l.textContent).join("; ") }, barras),
    el("div", { class: "legenda-linha" }, legenda)];
}

function cartao(c) {
  const t = c.totais;
  const comp = (t.COMPARECIMENTO || 0) + (t.ABSTENCAO || 0);
  const votos = (t.VALIDOS || 0) + (t.BRANCOS || 0) + (t.NULOS || 0) + (t.ANULADOS_SUB_JUDICE || 0);
  const maxPct = Math.max(...c.candidatos.map((x) => x.PCT_VALIDOS || 0), 0.0001);
  const vagas = t.VAGAS ? ` · ${t.VAGAS} vaga${t.VAGAS > 1 ? "s" : ""}` : "";
  const filhos = [
    el("div", {}, el("h2", {}, `${c.ds_cargo} — ${c.abrangencia}`),
      el("div", { class: "sub" }, `Seções totalizadas ${pct(t.PCT_SECOES_TOTALIZADAS)} (${int(t.SECOES_TOTALIZADAS)} de ${int(t.SECOES_TOTAL)})` +
        ` · totalização ${hora(t.DT_TOTALIZACAO)}${t.TOTALIZACAO_FINAL ? " · FINAL" : ""}${vagas}`)),
    el("div", { class: "progresso", role: "progressbar", "aria-valuenow": t.PCT_SECOES_TOTALIZADAS || 0, "aria-valuemin": 0, "aria-valuemax": 100 },
      el("div", { style: { width: `${t.PCT_SECOES_TOTALIZADAS || 0}%` } })),
    el("h3", {}, `Eleitorado ${int(t.ELEITORADO)}`),
    ...(comp ? composicao([
      { rotulo: "Comparecimento", valor: t.COMPARECIMENTO || 0, cor: cor("--serie-1") },
      { rotulo: "Abstenção", valor: t.ABSTENCAO || 0, cor: cor("--outros") },
    ], comp) : []),
    el("h3", {}, "Votos"),
    ...(votos ? composicao([
      { rotulo: "Válidos", valor: t.VALIDOS || 0, cor: cor("--serie-1") },
      { rotulo: "Brancos", valor: t.BRANCOS || 0, cor: cor("--serie-2") },
      { rotulo: "Nulos", valor: t.NULOS || 0, cor: cor("--serie-3") },
      { rotulo: "Anulados sub judice", valor: t.ANULADOS_SUB_JUDICE || 0, cor: cor("--serie-4") },
    ], votos) : []),
    ...blocoSerie(c.serie, c.proporcional),
    el("h3", {}, c.proporcional ? `Mais votados (${c.candidatos.length} de ${int(c.n_candidatos)})` : "Candidatos"),
    el("div", { class: "lista" }, c.candidatos.map((x, i) => linhaCandidato(i + 1, x, maxPct, c.cargo))),
  ];
  if (c.partidos && c.partidos.length) {
    const maxP = Math.max(...c.partidos.map((p) => p.PCT_VALIDOS || 0), 0.0001);
    filhos.push(el("h3", {}, "Partidos (nominais + legenda)"),
      el("div", { class: "lista" }, c.partidos.map((p, i) => el("div", { class: "item" },
        el("span", { class: "pos" }, i + 1),
        el("span", { class: "nome" }, p.PARTIDO, p.FEDERACAO ? el("small", {}, ` · ${p.FEDERACAO}`) : null),
        el("span", { class: "barra" }, el("div", { style: { width: `${(100 * (p.PCT_VALIDOS || 0)) / maxP}%` } })),
        el("span", { class: "num" }, int(p.VOTOS_TOTAL)),
        el("span", { class: "sit" }, p.VAGAS_AGREMIACAO ? `${p.VAGAS_AGREMIACAO} vaga(s)` : pct(p.PCT_VALIDOS))))));
  }
  if (c.projecao) filhos.splice(filhos.length - 2, 0, ...blocoProjecao(c.projecao));
  if (c.cadeiras) filhos.push(...blocoCadeiras(c.cadeiras));
  if (c.cargo === 1 && c.abrangencia === "BRASIL") filhos.push(blocoBrasil());
  return el("article", { class: "cartao" }, filhos);
}

// ---------------------------------------------------------------- presidente por UF (cartão Brasil, rodada 35)
// O bloco é UM nó persistente, movido para o cartão a cada redesenho: o mapa do Leaflet sobrevive à troca.
function blocoBrasil() {
  if (!estado.brasilBloco) {
    const sel = el("select", { id: "brasil-metrica", "aria-label": "Métrica do mapa por estado",
      onchange: () => desenharBrasil() }, el("option", { value: "lider" }, "Quem lidera"));
    estado.brasilBloco = el("div", { class: "brasil-ufs", hidden: true },
      el("h3", {}, "Por estado"),
      el("label", { class: "nota" }, "Mapa: ", sel),
      el("div", { id: "brasil-mapa", class: "mapa brasil" }),
      el("div", { id: "brasil-legenda", class: "legenda-linha" }),
      el("div", { id: "brasil-tabela", class: "tabela-rolagem brasil" }),
      el("p", { class: "nota" }, "Resultado do TSE em cada UF (o exterior só na tabela). Sem projeção nacional."));
  }
  return estado.brasilBloco;
}


// hint de uma UF: apuração, todos os candidatos (% dos válidos) e brancos, nulos e abstenção
function dicaUf(u, codigo, valor) {
  if (!u) return el("div", {}, el("strong", {}, codigo), el("br"), "sem dado");
  const cab = el("div", {}, el("strong", {}, u.nome), " · ", `${pct(u.pct_secoes)} apurado`,
    u.hora ? ` · totalização ${hora(u.hora)}` : null, u.final ? " · FINAL" : null);
  if (!u.primeiro) return el("div", {}, cab, el("div", { class: "nota" }, "sem apuração"));
  const linha = (rotulo, p, n, classe = null) => el("tr", { class: classe },
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

async function atualizarBrasil() {
  if (!estado.brasilBloco) return;  // sem cartão Brasil (ex.: eleição sem presidente)
  try { estado.brasil = await api("api/presidente/ufs"); } catch (e) { return; }
  if (!estado.brasilGeo) {
    try { estado.brasilGeo = await api("geo/ufs.geojson"); } catch (e) { estado.brasilGeo = null; }
  }
  desenharBrasil();
}

function desenharBrasil() {
  const d = estado.brasil, bloco = estado.brasilBloco;
  if (!d || !bloco) return;
  bloco.hidden = !d.ufs.length;
  if (!d.ufs.length) return;
  const sel = bloco.querySelector("#brasil-metrica");
  const escolhido = sel.value;
  sel.replaceChildren(el("option", { value: "lider" }, "Quem lidera"),
    ...d.candidatos.map((c) => el("option", { value: String(c.NUMERO) }, `% de ${c.NUMERO} ${c.NOME_URNA}`)));
  sel.value = [...sel.options].some((o) => o.value === escolhido) ? escolhido : "lider";
  const nome = (x) => (x ? `${x.numero} ${x.nome}` : "—");
  const cores = ["--serie-1", "--serie-2", "--serie-3"].map(cor);
  const idx = new Map(d.candidatos.map((c, i) => [c.NUMERO, i]));
  const semDado = cor("--sem-dado");
  let corDe, legenda, valor;
  if (sel.value === "lider") {
    corDe = (u) => (!u || !u.primeiro ? semDado : idx.has(u.primeiro.numero) ? cores[idx.get(u.primeiro.numero)] : cor("--outros"));
    legenda = [...d.candidatos.map((c, i) => [cores[i], `${c.NUMERO} ${c.NOME_URNA} (${c.PARTIDO})`]), [cor("--outros"), "Outros"]];
    valor = (u) => (u.primeiro ? `lidera: ${nome(u.primeiro)} (${pct(u.primeiro.pct)})` : "sem apuração");
  } else {
    const seq = ["--mapa-1", "--mapa-2", "--mapa-3", "--mapa-4", "--mapa-5"].map(cor);
    const v = (u) => (u && u.primeiro ? u.pct[sel.value] ?? null : null);
    const vals = d.ufs.filter((u) => u.uf !== "ZZ").map(v).filter((x) => x !== null);
    const qb = quebrasQuantis(vals);
    corDe = (u) => {
      const x = v(u);
      if (x === null) return semDado;
      let k = 0;
      while (k < qb.length && x > qb[k]) k++;
      return seq[Math.min(k, seq.length - 1)];
    };
    const lim = vals.length ? [Math.min(...vals), ...qb, Math.max(...vals)] : [];
    legenda = lim.slice(0, -1).map((a, i) => [seq[i], `${pct(a)} – ${pct(lim[i + 1])}`]);
    valor = (u) => `${sel.selectedOptions[0].textContent}: ${pct(v(u))}`;
  }
  legenda.push([semDado, "sem apuração"]);
  bloco.querySelector("#brasil-legenda").replaceChildren(...legenda.map(([c, t]) =>
    el("span", {}, el("span", { class: "amostra", style: { background: c } }), t)));
  const porIbge = new Map(d.ufs.filter((u) => u.cd_ibge).map((u) => [String(u.cd_ibge), u]));
  if (estado.brasilGeo) {
    if (!estado.brasilMapa) {
      estado.brasilMapa = criarMapa(bloco.querySelector("#brasil-mapa"),
        { centro: [-15, -54], zoom: 3, ladrilhos: false, zoomSnap: 0.25 });
    }
    const mapa = estado.brasilMapa;
    if (mapa._camada) mapa.removeLayer(mapa._camada);
    mapa._camada = L.geoJSON(estado.brasilGeo, {
      style: (ft) => ({ fillColor: corDe(porIbge.get(ft.properties.codarea)), fillOpacity: 0.85,
        color: cor("--superficie"), weight: 1 }),
      onEachFeature: (ft, layer) => {
        const u = porIbge.get(ft.properties.codarea);
        // hint fora do mapa (a tabela é mais alta que o mapa, que corta o tooltip do Leaflet)
        layer.on("mouseover", (e) => { dicaFlutuante.mostrar(dicaUf(u, ft.properties.codarea, valor), e.originalEvent);
          layer.setStyle({ weight: 3, color: cor("--texto") }); });
        layer.on("mousemove", (e) => dicaFlutuante.posicionar(e.originalEvent));
        layer.on("mouseout", () => { dicaFlutuante.esconder(); layer.setStyle({ weight: 1, color: cor("--superficie") }); });
      },
    }).addTo(mapa);
    if (!mapa._enquadrado) { mapa.fitBounds(mapa._camada.getBounds(), { padding: [4, 4] }); mapa._enquadrado = true; }
  }
  bloco.querySelector("#brasil-mapa").hidden = !estado.brasilGeo;
  const linhas = d.ufs.map((u) => ({ ...u, ordem: u.uf === "ZZ" ? "ZZZ" : u.nome, lider: nome(u.primeiro),
    pct1: u.primeiro ? u.primeiro.pct : null, vice: nome(u.segundo), pct2: u.segundo ? u.segundo.pct : null }));
  const formatar = (r, k) => (["pct_secoes", "pct1", "pct2"].includes(k) ? pct(r[k])
    : k === "diferenca_pp" ? (r[k] === null ? "—" : `${fmtPct.format(r[k])} p.p.`)
    : k === "ordem" ? `${r.nome}${r.final ? " ✓" : ""}` : r[k] ?? "—");
  const tab = bloco.querySelector("#brasil-tabela");
  tab.replaceChildren(tabelaOrdenavel([["UF", "ordem"], ["Apurado", "pct_secoes", true], ["1º", "lider"],
    ["%", "pct1", true], ["2º", "vice"], ["%", "pct2", true], ["Diferença", "diferenca_pp", true]], linhas, formatar,
  null, { ordem: estado.brasilOrdem || "ordem-asc", aoOrdenar: (o) => { estado.brasilOrdem = o; } }));
}

// votos de candidatura sub judice entram nos votos do candidato, mas não nos válidos
const destinacao = (x) => (x.DESTINACAO && x.DESTINACAO !== "Válido" ? ` · ${x.DESTINACAO}` : "");

// ---------------------------------------------------------------- série temporal da apuração
function blocoSerie(serie, proporcional) {
  const titulo = el("h3", {}, `Evolução na apuração — % dos válidos dos 3 ${proporcional ? "partidos" : "candidatos"} ` +
    "mais votados × % das seções totalizadas");
  if (!serie || serie.pontos.length < 2) {
    const n = serie ? serie.pontos.length : 0;
    return [titulo, el("p", { class: "nota" },
      `A série aparece a partir da 2ª totalização (${n} registrada${n === 1 ? "" : "s"} até agora).`)];
  }
  return [titulo, graficoSerie(serie)];
}

function graficoSerie(serie) {  // painel: x = % de seções totalizadas
  return graficoLinhas({
    xs: serie.pontos.map((p) => p.pct_secoes ?? 0), xMin: 0, xMax: 100, xTicks: [0, 25, 50, 75, 100], xFmt: (t) => `${t}%`,
    series: serie.series.map((s) => ({ nome: s.NOME, rotulo: `${s.CHAVE !== s.NOME ? s.CHAVE + " " : ""}${s.NOME}` +
      `${s.CHAVE !== s.NOME ? ` (${s.PARTIDO})` : ""}`, valores: s.valores })),
    dica: (k) => `${hora(serie.pontos[k].dt)} · ${pct(serie.pontos[k].pct_secoes)} das seções`,
  });
}

// ---------------------------------------------------------------- exportar mapas (desenhados no servidor)
function baixarMapa(qual, formato, msg) {
  const cargoSel = document.getElementById(qual === "mapa" ? "mapa-cargo" : "comp-cargo");
  return exportarMapa(estado[qual], formato, msg, { aba: qual === "mapa" ? "mapas" : "comparacao", uf: estado.uf,
    cargo: cargoSel.selectedOptions[0]?.textContent || "", ambiente: document.getElementById("ambiente").textContent,
    link: `${location.origin}${location.pathname}${location.hash}` });
}

document.querySelectorAll(".baixar-mapa").forEach((b) => b.addEventListener("click",
  () => baixarMapa(b.dataset.mapa, b.dataset.formato, b.parentElement.querySelector(".baixar-msg"))));

function linhaCandidato(pos, x, maxPct, cargo) {
  return el("div", {
    class: "item" + (x.ELEITO ? " destaque" : ""),
    title: `${x.NOME_URNA} (${x.PARTIDO}) — ${int(x.VOTOS)} votos, ${pct(x.PCT_VALIDOS)} — ${x.SITUACAO || ""}${destinacao(x)}`,
    ondblclick: () => consultarCandidato(cargo, x.NUMERO),
  },
    el("span", { class: "pos" }, pos),
    el("span", { class: "nome" }, `${x.NUMERO} ${x.NOME_URNA} `, el("small", {}, x.PARTIDO)),
    el("span", { class: "barra" }, el("div", { style: { width: `${(100 * (x.PCT_VALIDOS || 0)) / maxPct}%` } })),
    el("span", { class: "num" }, pct(x.PCT_VALIDOS)),
    el("span", { class: "sit" }, (x.SITUACAO || "") + destinacao(x)));
}

// ---------------------------------------------------------------- candidatos (abas/candidato; lista em dados/candidatos.ts)
const consultarCandidato = (...args) => abaCandidato.consultar(...args);

// ---------------------------------------------------------------- ciclo de atualização
async function tick() {
  await atualizarStatus();
  if (estado.aba === "painel") { await atualizarPainel(); atualizarMudancas(); }
  await modulos.get(estado.aba)?.atualizar?.();
}
// ---------------------------------------------------------------- alertas da noite
// O servidor verifica a cada 15 s (apuracao/alertas.py); a página consulta /api/alertas?desde=<último id>.
// Condições ativas (coletor parado, bloqueio…) ficam na faixa do topo; alertas novos viram avisos com som.
const ALERTAS_MS = 15_000;
const NIVEL = {
  critico: { icone: "✖", rotulo: "Crítico", fixo: true },
  aviso: { icone: "⚠", rotulo: "Atenção", fixo: true },
  noticia: { icone: "ℹ", rotulo: "Novidade", fixo: false },
  ok: { icone: "✓", rotulo: "Resolvido", fixo: false },
};
const alertas = { ultimo: null, historico: [], ativos: [], naoVistos: 0, audio: null, interesse: [] };

function cartaoAlerta(a, fechar = null) {
  const n = NIVEL[a.nivel] || NIVEL.noticia;
  const quando = (a.momento || a.desde || "").slice(11, 16);
  return el("div", { class: `alerta ${a.nivel}`, "data-chave": a.chave },
    el("span", { class: "icone", "aria-hidden": "true" }, n.icone),
    el("div", { class: "corpo" },
      el("div", { class: "rotulo" }, `${n.rotulo}${quando ? " · " + quando : ""}`),
      el("div", { class: "titulo" }, a.titulo),
      a.detalhe ? el("div", { class: "detalhe" }, a.detalhe) : null),
    fechar ? el("button", { type: "button", class: "fechar", "aria-label": "Dispensar", onclick: fechar }, "×") : null);
}

// som: um bipe por nível (WebAudio, sem arquivo); o navegador só libera o áudio depois de um clique na página
function tocar(nivel) {
  if (!document.getElementById("alertas-som").checked) return;
  try {
    alertas.audio = alertas.audio || new AudioContext();
    if (alertas.audio.state === "suspended") alertas.audio.resume();
    const notas = nivel === "critico" ? [880, 660, 880, 660] : nivel === "aviso" ? [740, 740] : [660];
    notas.forEach((f, i) => {
      const o = alertas.audio.createOscillator(), g = alertas.audio.createGain(), t = alertas.audio.currentTime + i * 0.22;
      o.frequency.value = f; o.type = "sine";
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
      o.connect(g).connect(alertas.audio.destination); o.start(t); o.stop(t + 0.2);
    });
  } catch (_) { /* navegador sem WebAudio: fica só o destaque */ }
}

function mostrarAviso(a) {
  const caixa = document.getElementById("avisos");
  const cartao = cartaoAlerta(a, () => cartao.remove());
  caixa.prepend(cartao);
  while (caixa.children.length > 5) caixa.lastChild.remove();
  if (!(NIVEL[a.nivel] || NIVEL.noticia).fixo) setTimeout(() => cartao.remove(), 30_000);
}

function desenharAlertas() {
  const faixa = document.getElementById("faixa-alertas");
  faixa.replaceChildren(...alertas.ativos.map((a) => cartaoAlerta(a)));
  faixa.hidden = !alertas.ativos.length;
  const botao = document.getElementById("botao-alertas");
  botao.classList.toggle("tem-ativos", alertas.ativos.some((a) => a.nivel === "critico"));
  const cont = document.getElementById("alertas-contagem");
  cont.textContent = String(alertas.naoVistos);
  cont.hidden = !alertas.naoVistos;
  document.getElementById("alertas-historico").replaceChildren(
    ...alertas.historico.slice().reverse().map((a) => el("li", {}, cartaoAlerta(a))));
  document.getElementById("alertas-interesse").replaceChildren(...(alertas.interesse.length ? alertas.interesse.map((i) =>
    el("div", { class: "interesse-linha" },
      el("span", {}, `${NOMES_CARGO[i.cargo] || i.cargo}: ${i.nome}`),
      el("span", { class: "sit" }, i.situacao || "aguardando 30% apurado"),
      el("button", { type: "button", class: "link", onclick: () => acompanhar(i.cargo, i.numero, false) }, "remover")))
    : [el("p", { class: "nota" }, "Nenhum.")]));
  atualizarTituloAlertas();
  rotularAcompanhar();
}

function atualizarTituloAlertas() {
  const base = document.title.replace(/^(⚠ )?(\(\d+\) )?/, "");
  const grave = alertas.ativos.some((a) => a.nivel === "critico" || a.nivel === "aviso");
  document.title = `${grave ? "⚠ " : ""}${alertas.naoVistos ? `(${alertas.naoVistos}) ` : ""}${base}`;
}

async function atualizarAlertas() {
  let r;
  try { r = await api(`api/alertas?desde=${alertas.ultimo ?? 0}`); } catch (_) { return; }
  const primeira = alertas.ultimo === null;
  alertas.ultimo = r.ultimo_id;
  alertas.ativos = r.ativos;
  alertas.interesse = r.interesse;
  alertas.historico = alertas.historico.concat(r.alertas).slice(-200);
  if (!primeira && r.alertas.length) {  // o que já existia ao abrir a página vai só para o histórico
    const painelAberto = !document.getElementById("painel-alertas").hidden;
    if (!painelAberto) alertas.naoVistos += r.alertas.length;
    r.alertas.forEach(mostrarAviso);
    const ordem = ["critico", "aviso", "noticia", "ok"];
    window.__apuracao.tocar(r.alertas.map((a) => a.nivel).sort((x, y) => ordem.indexOf(x) - ordem.indexOf(y))[0]);
  }
  desenharAlertas();
}

function abrirPainelAlertas(abrir) {
  const painel = document.getElementById("painel-alertas");
  painel.hidden = !abrir;
  document.getElementById("botao-alertas").setAttribute("aria-expanded", String(abrir));
  if (abrir) {  // os avisos estão no histórico: saem para não cobrir o painel (no celular, ocupam a tela)
    document.getElementById("avisos").replaceChildren();
    alertas.naoVistos = 0; desenharAlertas(); document.getElementById("fechar-alertas").focus();
  }
}

async function acompanhar(cargo, numero, sim) {
  const r = await enviar("api/alertas/interesse", { cargo: Number(cargo), numero: Number(numero), acompanhar: sim });
  alertas.interesse = r.interesse;
  desenharAlertas();
  return alertas.interesse;
}

function seguindo(cargo, numero) {
  return alertas.interesse.some((i) => i.cargo === Number(cargo) && i.numero === Number(numero));
}

// o rótulo vem sempre do estado dos alertas: o candidato pode ser redesenhado (ex.: a abertura do endereço na carga)
// enquanto o pedido ainda está em curso, e o botão novo precisa refletir a resposta
function rotularAcompanhar() {
  const b = document.getElementById("botao-acompanhar");
  if (b) b.textContent = seguindo(b.dataset.cargo, b.dataset.numero) ? "Deixar de acompanhar" : "Acompanhar nos alertas";
}

function botaoAcompanhar(cargo, numero) {
  if (![6, 7, 8].includes(Number(cargo)) || estado.ano !== 2026) return null;
  const msg = el("span", { class: "nota", "aria-live": "polite" });
  const b = el("button", { type: "button", id: "botao-acompanhar", "data-cargo": cargo, "data-numero": numero });
  b.addEventListener("click", async () => {
    try {
      await acompanhar(cargo, numero, !seguindo(cargo, numero));
      msg.textContent = seguindo(cargo, numero) ? " Você será avisado." : "";
    } catch (e) { msg.textContent = ` ${e.message}`; }
  });
  queueMicrotask(rotularAcompanhar);
  return el("p", { class: "nota" }, b, msg);
}

document.getElementById("destaque-limpar").addEventListener("click", () => definirDestaque([]));
document.getElementById("destaque-link").addEventListener("click", () =>
  copiarLink(roteador.endereco("painel"), document.getElementById("destaque-link-msg")));

// Ponto de acesso dos testes e2e: no script clássico estes nomes eram globais; no módulo, não.
window.__apuracao = { estado, alertas, tocar, api, desenharPainel, atualizarPainel, atualizarAlertas,
  consultarCandidato, partidosVar: () => abaComparacao.partidosVar(),
  get abas() { return Object.fromEntries(modulos); } };

(function iniciarAlertas() {
  const som = document.getElementById("alertas-som");
  som.checked = lerPreferencia("alertas-som", true);
  som.addEventListener("change", () => { gravarPreferencia("alertas-som", som.checked); if (som.checked) window.__apuracao.tocar("ok"); });
  document.getElementById("botao-alertas").addEventListener("click", () =>
    abrirPainelAlertas(document.getElementById("painel-alertas").hidden));
  document.getElementById("fechar-alertas").addEventListener("click", () => abrirPainelAlertas(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") abrirPainelAlertas(false); });
  // o navegador só libera o áudio depois de uma interação: o 1º clique prepara o contexto
  document.addEventListener("click", () => {
    try { alertas.audio = alertas.audio || new AudioContext(); if (alertas.audio.state === "suspended") alertas.audio.resume(); } catch (_) { /* */ }
  }, { once: true });
  repetir(atualizarAlertas, ALERTAS_MS).agora();  // continua com a aba escondida: é quando o som importa
})();

// ---------------------------------------------------------------- endereços das abas (tabela única)
function registrarModulo(m) { modulos.set(m.id, m); return m; }
const abaComparacao = registrarModulo(criarAbaComparacao(contexto));
const abaCandidato = registrarModulo(criarAbaCandidato(contexto, { candidatos, botaoAcompanhar }));
const abaMapas = registrarModulo(criarAbaMapas(contexto, { candidatos }));
// escrever: estado da aba → parâmetros (gravar e "Copiar link"); aplicar: parâmetros → estado (abre a aba)
roteador
  .registrar("painel", { escrever: parametrosPainel, aplicar: aplicarEnderecoPainel, enderecoAoMostrar: true })
  .registrar("candidato", abaCandidato)
  .registrar("mapas", abaMapas)
  .registrar("comparacao", abaComparacao)
  .registrar("perfil", registrarModulo(criarAbaPerfil(contexto)))
  .registrar("transferencia", registrarModulo(criarAbaTransferencia(contexto)));
window.addEventListener("hashchange", () => roteador.abrir());

// ---------------------------------------------------------------- seletor de UF (site com várias UFs)
// O site de várias UFs monta cada uma em /<uf>/ e lista as disponíveis em /ufs.json; no site de uma UF
// esse arquivo não existe e o seletor fica escondido. Trocar de UF mantém a aba e o endereço (#…).
async function iniciarSeletorUf() {
  let d;
  try { d = await api("../ufs.json"); } catch (_) { return; }  // site de uma UF: não há ufs.json
  const atual = location.pathname.split("/").filter(Boolean).at(-1)?.toUpperCase();
  const sel = document.getElementById("seletor-uf");
  sel.replaceChildren(...d.ufs.map((u) => el("option", { value: u.uf, disabled: !u.disponivel, selected: u.uf === atual },
    `${u.uf} — ${u.nome}${u.disponivel ? "" : " (sem dados)"}`)));
  sel.addEventListener("change", () => { location.href = `../${sel.value.toLowerCase()}/${location.hash}`; });
  document.getElementById("seletor-uf-rotulo").hidden = false;
}
iniciarSeletorUf();

// o ciclo de 60 s nunca roda duas vezes ao mesmo tempo; com a aba escondida espera a volta
const ciclo = repetir(tick, REFRESH_MS, { pausarOculto: true });
abaComparacao.preparar().then(() => ciclo.agora()).then(() => roteador.abrir());
void abaCandidato.preparar();
