/* Apuração 2026 — página do site local.
 * Todo texto vindo dos dados entra por textContent (o TSE testa nomes com aspas e símbolos). */
"use strict";

const REFRESH_MS = 60_000;
const fmtInt = new Intl.NumberFormat("pt-BR");
const fmtPct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const estado = { aba: "painel", uf: "", ano: 2026, candidatosCache: {}, geo: null, mapa: null, mini: null,
  destacar: new Set(), destacarDefinido: false, cadAbertos: new Set(), painel: null };

// ---------------------------------------------------------------- utilitários
function el(tag, attrs = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") {  // "--x": propriedade personalizada (Object.assign não as aplica)
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith("--")) n.style.setProperty(prop, val); else n.style[prop] = val;
      }
    }
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return n;
}
const cor = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
const int = (v) => (v === null || v === undefined ? "—" : fmtInt.format(v));
const pct = (v) => (v === null || v === undefined ? "—" : fmtPct.format(v) + "%");
const hora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" }) : "—");

async function api(caminho) {
  const r = await fetch(caminho, { cache: "no-store" });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* resposta sem JSON */ }
    throw new Error(msg);
  }
  return r.json();
}

// ---------------------------------------------------------------- abas
document.querySelectorAll(".abas button").forEach((b) =>
  b.addEventListener("click", () => mostrarAba(b.dataset.aba)));

function mostrarAba(aba) {
  estado.aba = aba;
  const atual = location.hash.replace(/^#/, "").split(/[?/]/)[0];
  if (atual !== aba && ["mapas", "candidato", "comparacao", "perfil", "transferencia", "painel"].includes(atual)) {
    history.replaceState(null, "", aba === "painel" ? enderecoPainel() : `#${aba}`);
  } else if (aba === "painel" && estado.destacar.size) history.replaceState(null, "", enderecoPainel());
  document.querySelectorAll(".abas button").forEach((b) => b.setAttribute("aria-selected", b.dataset.aba === aba));
  document.querySelectorAll(".aba").forEach((s) => (s.hidden = s.id !== `aba-${aba}`));
  if (aba === "mapas") {
    garantirMapa(); setTimeout(() => estado.mapa.invalidateSize(), 50);
    carregarMomentos().then(atualizarMapa);
  }
  if (aba === "candidato" && estado.mini) setTimeout(() => estado.mini.invalidateSize(), 50);
  if (aba === "comparacao") {
    if (!estado.compMapa) estado.compMapa = novoMapa(document.getElementById("comp-mapa"));
    setTimeout(() => estado.compMapa.invalidateSize(), 50);
    if (!estado.compFeito) { estado.compFeito = true; atualizarComparacao(); }
  }
  if (aba === "transferencia" && !tf.feito) {
    tf.feito = true;
    iniciarTransferencia().catch((e) => { tfq("msg").textContent = `Não foi possível abrir: ${e.message}`; });
  }
  if (aba === "perfil" && !estado.pf.feito) {
    estado.pf.feito = true;
    iniciarPerfil().then(() => ajustarPerfil()).then(analisarPerfil)
      .catch((e) => { pf("msg").textContent = `Não foi possível abrir: ${e.message}`; });
  }
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
  const q = new URLSearchParams(enderecoPainel().split("?")[1] || "");
  if (ligar) q.set("tv", "1");
  history.replaceState(null, "", `#painel${q.toString() ? "?" + q : ""}`);
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
    try { localStorage.setItem("destacar", JSON.stringify([...estado.destacar])); } catch (_) { /* navegação privada */ }
    if (estado.aba === "painel") history.replaceState(null, "", enderecoPainel());
  }
  desenharPainel();
}

function enderecoPainel() {
  const q = new URLSearchParams();
  if (estado.destacar.size) q.set("destacar", [...estado.destacar].join(","));
  if (estado.tv?.ativo) q.set("tv", "1");
  return q.toString() ? `#painel?${q}` : "#painel";
}

function destaqueInicial(padrao) {  // endereço > navegador > --destacar do site (sem reescrever o endereço)
  if (estado.destacarDefinido) return;
  const [aba, params] = decodeURIComponent(location.hash.replace(/^#/, "")).split("?");
  const doEndereco = aba === "painel" && params ? new URLSearchParams(params).get("destacar") : null;
  if (doEndereco !== null) { definirDestaque(doEndereco.split(","), false); return; }
  let salvo = null;
  try { salvo = JSON.parse(localStorage.getItem("destacar") || "null"); } catch (_) { /* sem armazenamento */ }
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

const STATUS_CAD = { "consolidado": "Consolidado", "em disputa (dentro)": "Em disputa — hoje dentro",
  "em disputa (fora)": "Em disputa — hoje fora" };
const fmtFreq = (f) => `${Math.round(100 * f)}%`;

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
  if (estado.brasilMapa) setTimeout(() => estado.brasilMapa.invalidateSize(), 50);
  return estado.brasilBloco;
}

// dica flutuante (position: fixed, presa à janela): para conteúdo maior que o mapa
function mostrarDica(conteudo, ev) {
  if (!estado.dica) { estado.dica = el("div", { class: "dica-flutuante", role: "tooltip" }); document.body.append(estado.dica); }
  estado.dica.replaceChildren(conteudo);
  estado.dica.hidden = false;
  if (ev) posicionarDica(ev);
}
function posicionarDica(ev) {
  const d = estado.dica;
  if (!d || d.hidden || !ev) return;
  const m = 14, w = d.offsetWidth, h = d.offsetHeight;
  let x = ev.clientX + m, y = ev.clientY + m;
  if (x + w > window.innerWidth - 4) x = Math.max(4, ev.clientX - m - w);
  if (y + h > window.innerHeight - 4) y = Math.max(4, window.innerHeight - h - 4);
  d.style.left = `${x}px`; d.style.top = `${y}px`;
}
function esconderDica() { if (estado.dica) estado.dica.hidden = true; }

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
      estado.brasilMapa = L.map(bloco.querySelector("#brasil-mapa"), { preferCanvas: true, zoomSnap: 0.25 });
      estado.brasilMapa.setView([-15, -54], 3);
    }
    const mapa = estado.brasilMapa;
    if (mapa._camada) mapa.removeLayer(mapa._camada);
    mapa._camada = L.geoJSON(estado.brasilGeo, {
      style: (ft) => ({ fillColor: corDe(porIbge.get(ft.properties.codarea)), fillOpacity: 0.85,
        color: cor("--superficie"), weight: 1 }),
      onEachFeature: (ft, layer) => {
        const u = porIbge.get(ft.properties.codarea);
        // hint fora do mapa (a tabela é mais alta que o mapa, que corta o tooltip do Leaflet)
        layer.on("mouseover", (e) => { mostrarDica(dicaUf(u, ft.properties.codarea, valor), e.originalEvent);
          layer.setStyle({ weight: 3, color: cor("--texto") }); });
        layer.on("mousemove", (e) => posicionarDica(e.originalEvent));
        layer.on("mouseout", () => { esconderDica(); layer.setStyle({ weight: 1, color: cor("--superficie") }); });
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
const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...filhos) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  for (const f of filhos) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
}

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

// linhas com eixo x numérico; cada série pode ter seus próprios x (ex.: município × estado no tempo)
function graficoLinhas({ xs, xMin, xMax, xTicks, xFmt, series, dica: textoDica, dicaSerie }) {
  const W = 420, H = 170, m = { l: 40, r: 52, t: 10, b: 22 };
  const cores = ["--serie-1", "--serie-2", "--serie-3"].map(cor);
  const xsDe = (s) => s.xs || xs;
  const todos = series.flatMap((s) => s.valores).filter((v) => v !== null);
  let yMin = Math.min(...todos), yMax = Math.max(...todos);
  const pad = Math.max((yMax - yMin) * 0.12, 0.5);
  yMin = Math.max(0, yMin - pad); yMax = Math.min(100, yMax + pad);
  const X = (v) => m.l + ((W - m.l - m.r) * (v - xMin)) / (xMax - xMin || 1);
  const Y = (v) => m.t + (H - m.t - m.b) * (1 - (v - yMin) / (yMax - yMin || 1));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "serie", role: "img",
    "aria-label": `Evolução do % dos válidos: ${series.map((s) => s.nome).join(", ")}` });
  // grade e eixos (recessivos)
  const ticksY = [0, 1, 2, 3].map((i) => yMin + ((yMax - yMin) * i) / 3);
  for (const t of ticksY) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grade" }),
      svg("text", { x: m.l - 4, y: Y(t) + 3, class: "eixo", "text-anchor": "end" }, `${fmtPct.format(t)}%`));
  }
  for (const t of xTicks) {
    g.append(svg("text", { x: X(t), y: H - 8, class: "eixo", "text-anchor": "middle" }, xFmt(t)));
  }
  // linhas + ponto final
  const fim = [];
  series.forEach((s, i) => {
    const sx = xsDe(s);
    const pts = s.valores.map((v, k) => (v === null ? null : [X(sx[k]), Y(v)])).filter(Boolean);
    g.append(svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: cores[i],
      "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const ult = pts[pts.length - 1];
    if (ult) {
      g.append(svg("circle", { cx: ult[0], cy: ult[1], r: 4, fill: cores[i], stroke: cor("--superficie"), "stroke-width": 2 }));
      fim.push({ y: ult[1], x: ult[0], i, texto: `${fmtPct.format(s.valores.at(-1))}%` });  // nome fica na legenda
    }
  });
  // rótulos diretos na ponta, afastados para não colidir (texto na cor de texto, não da série)
  fim.sort((a, b) => a.y - b.y);
  for (let k = 1; k < fim.length; k++) fim[k].y = Math.max(fim[k].y, fim[k - 1].y + 12);
  for (const f of fim) g.append(svg("text", { x: W - m.r + 8, y: f.y + 4, class: "rotulo" }, f.texto));
  // camada de interação: linha vertical + dica com todos os valores do ponto mais próximo
  const guia = svg("line", { y1: m.t, y2: H - m.b, class: "guia", visibility: "hidden" });
  const alvo = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  g.append(guia, alvo);
  const dica = el("div", { class: "dica", hidden: true });
  const caixa = el("div", { class: "serie-caixa" }, g, dica);
  const perto = (arr, xv) => arr.reduce((k, x, j) => (Math.abs(x - xv) < Math.abs(arr[k] - xv) ? j : k), 0);
  alvo.addEventListener("mousemove", (ev) => {
    const r = g.getBoundingClientRect();
    const xv = xMin + (((ev.clientX - r.left) * (W / r.width) - m.l) / (W - m.l - m.r)) * (xMax - xMin);
    const base = xsDe(series[0]);
    const k = perto(base, xv);
    guia.setAttribute("x1", X(base[k])); guia.setAttribute("x2", X(base[k])); guia.setAttribute("visibility", "visible");
    dica.replaceChildren(el("strong", {}, textoDica(k, xv)),
      ...series.map((s, i) => {
        const j = s.xs ? perto(s.xs, xv) : k;
        return el("div", {}, el("span", { class: "amostra", style: { background: cores[i] } }),
          dicaSerie ? dicaSerie(s, j) : `${s.rotulo}: ${pct(s.valores[j])}`);
      }));
    dica.hidden = false;
    dica.style.left = `${Math.min((ev.clientX - r.left) + 12, r.width - 220)}px`;
  });
  alvo.addEventListener("mouseleave", () => { guia.setAttribute("visibility", "hidden"); dica.hidden = true; });
  const legenda = el("div", { class: "legenda-linha" }, series.map((s, i) => el("span", {},
    el("span", { class: "amostra", style: { background: cores[i] } }), s.rotulo)));
  const itensLeg = series.map((s, i) => [cores[i], s.rotulo]);
  const baixar = el("div", { class: "nota baixar-serie" }, "Baixar gráfico: ",
    el("button", { type: "button", class: "link", onclick: () => baixarGrafico(g, itensLeg, "svg") }, "SVG"), " ",
    el("button", { type: "button", class: "link", onclick: () => baixarGrafico(g, itensLeg, "png") }, "PNG"));
  return el("div", {}, caixa, legenda, baixar);
}

// ---------------------------------------------------------------- exportar gráficos e mapas
function salvarBlob(blob, nome) {
  const a = el("a", { href: URL.createObjectURL(blob), download: nome });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}

// SVG autônomo: estilos calculados embutidos (as classes usam variáveis CSS), sem a camada de
// interação, com fundo e legenda desenhados dentro do próprio SVG
function svgAutonomo(g, itensLeg) {
  const clone = g.cloneNode(true);
  const orig = g.querySelectorAll("*"), cop = clone.querySelectorAll("*");
  orig.forEach((o, i) => {
    const cs = getComputedStyle(o);
    for (const p of ["fill", "stroke", "stroke-width", "font-size", "font-family", "opacity"]) {
      const val = cs.getPropertyValue(p);
      if (val) cop[i].style.setProperty(p, val);
    }
  });
  clone.querySelectorAll("line.guia, rect").forEach((e) => e.remove());
  const [x0, y0, w, h] = g.getAttribute("viewBox").split(" ").map(Number);
  const altura = h + 8 + 16 * itensLeg.length;
  clone.setAttribute("viewBox", `${x0} ${y0} ${w} ${altura}`);
  clone.setAttribute("xmlns", SVG);
  clone.setAttribute("width", String(w * 2)); clone.setAttribute("height", String(altura * 2));
  clone.insertBefore(svg("rect", { x: x0, y: y0, width: w, height: altura, fill: cor("--superficie") }), clone.firstChild);
  itensLeg.forEach(([c, t], i) => {
    const y = h + 8 + 16 * i;
    clone.append(svg("rect", { x: 40, y, width: 10, height: 10, rx: 2, fill: c }),
      svg("text", { x: 56, y: y + 9, "font-size": 11, fill: cor("--texto-2"), "font-family": "system-ui, sans-serif" }, t));
  });
  return new XMLSerializer().serializeToString(clone);
}

async function baixarGrafico(g, itensLeg, formato) {
  const texto = svgAutonomo(g, itensLeg);
  const nome = `grafico_apuracao_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}`;
  if (formato === "svg") { salvarBlob(new Blob([texto], { type: "image/svg+xml" }), `${nome}.svg`); return; }
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(texto)}`;
  await img.decode();
  const canvas = el("canvas", { width: img.naturalWidth * 1.5, height: img.naturalHeight * 1.5 });
  canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((b) => salvarBlob(b, `${nome}.png`), "image/png");
}

async function baixarMapa(qual, formato, msg) {
  const m = estado[qual];
  if (!m || !m._export) { msg.textContent = " desenhe o mapa primeiro."; return; }
  const aba = qual === "mapa" ? "mapas" : "comparacao";
  const cargoSel = document.getElementById(qual === "mapa" ? "mapa-cargo" : "comp-cargo");
  const amb = document.getElementById("ambiente").textContent;
  const corpo = {
    formato, camada: m._export.camada, titulo: m._export.titulo, ano: m._export.ano ?? null,
    subtitulo: m._export.camada === "locais" ? `${estado.uf} · locais de votação (cadastro de ${m._export.ano}); área do ponto ∝ eleitorado`
      : m._export.subtitulo ? `${m._export.subtitulo} — ${estado.uf} · bairros do IBGE`
      : `${cargoSel.selectedOptions[0]?.textContent || ""} — ${estado.uf} · ${amb}`,
    nome: `mapa ${aba} ${m._export.titulo}`, cores: m._export.cores, legenda: m._export.legenda,
    fundo: cor("--superficie"), texto: cor("--texto"), sem_dado: cor("--sem-dado"), contorno: cor("--superficie"),
    extras: [`Link: ${location.origin}${location.pathname}${location.hash}`],
  };
  msg.textContent = " gerando…";
  try {
    const r = await fetch("api/exportar/mapa", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo) });
    if (!r.ok) { msg.textContent = ` erro: ${(await r.json()).detail}`; return; }
    const nome = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || `mapa.${formato}`;
    salvarBlob(await r.blob(), nome);
    msg.textContent = " arquivo gerado.";
  } catch (e) { msg.textContent = ` erro: ${e.message}`; }
  setTimeout(() => { msg.textContent = ""; }, 5000);
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

// ---------------------------------------------------------------- candidatos (busca)
async function listaCandidatos(cargo) {
  if (!estado.candidatosCache[cargo]) estado.candidatosCache[cargo] = await api(`api/candidatos?cargo=${cargo}`);
  return estado.candidatosCache[cargo];
}

async function preencherLista(cargo, datalistId) {
  try {
    const lista = await listaCandidatos(cargo);
    document.getElementById(datalistId).replaceChildren(
      ...lista.map((c) => el("option", { value: c.NUMERO }, `${c.NOME_URNA} (${c.PARTIDO})`)));
  } catch (_) { /* sem dados ainda */ }
}

async function resolverNumero(cargo, texto) {
  const t = texto.trim();
  if (/^\d+$/.test(t)) return Number(t);
  const alvo = t.toUpperCase();
  const achado = (await listaCandidatos(cargo)).find((c) => (c.NOME_URNA || "").toUpperCase().includes(alvo));
  return achado ? achado.NUMERO : null;
}

// ---------------------------------------------------------------- aba candidato
const formCand = document.getElementById("form-candidato");
document.getElementById("cand-cargo").addEventListener("change", (e) => {
  estado.candidatosCache = {};
  preencherLista(e.target.value, "cand-lista");
});
formCand.addEventListener("submit", async (e) => {
  e.preventDefault();
  const cargo = document.getElementById("cand-cargo").value;
  const numero = await resolverNumero(cargo, document.getElementById("cand-numero").value);
  const out = document.getElementById("cand-resultado");
  if (numero === null) { out.replaceChildren(el("p", { class: "aviso" }, "Candidato não encontrado.")); return; }
  consultarCandidato(cargo, numero);
});

function textoCadeira(k) {
  if (k.projecao) {
    const pr = k.projecao;
    return `${STATUS_CAD[pr.status] || "Fora da disputa"} · eleito em ${fmtFreq(pr.freq)} das simulações · ` +
      `${int(pr.votos_proj)} votos projetados (${pct(pr.pct_apurado)} apurado)`;
  }
  if (k.situacao.startsWith("Eleito")) {
    return `${k.situacao}${k.margem !== null ? ` · ${int(k.margem)} votos à frente do 1º suplente de ${k.agremiacao}` : ""}`;
  }
  if (k.situacao === "Suplente") {
    return k.margem !== null
      ? `Suplente (${k.ordem}º de ${k.agremiacao}) · faltam ${int(k.margem)} votos para passar o último eleito da agremiação`
      : `Suplente · ${k.agremiacao} sem cadeira na projeção`;
  }
  return `${k.situacao} (votos não válidos para a vaga)`;
}

async function consultarCandidato(cargo, numero, municipio = null, ordem = null) {
  mostrarAba("candidato");
  if (estado.cand && (estado.cand.cargo !== String(cargo) || estado.cand.numero !== String(numero))) {
    for (const [, id] of CAMPOS_HISTORICO) document.getElementById(id).value = "";  // indicação era do anterior
  }
  estado.cand = { cargo: String(cargo), numero: String(numero), municipio: municipio ?? null, ordem };
  carregarHistorico();
  document.getElementById("cand-cargo").value = String(cargo);
  document.getElementById("cand-numero").value = String(numero);
  document.getElementById("pl-numero").value = String(numero);
  const out = document.getElementById("cand-resultado");
  let d;
  try { d = await api(`api/candidato?cargo=${cargo}&numero=${numero}`); } catch (e) {
    out.replaceChildren(el("p", { class: "aviso" }, e.message)); return;
  }
  const c = d.candidato;
  const fichas = el("div", { class: "fichas" },
    ficha("Candidato", `${c.NUMERO} — ${c.NOME_URNA}`), ficha("Partido", `${c.PARTIDO}${c.FEDERACAO ? " · " + c.FEDERACAO : ""}`),
    ficha(`Votos (${estado.uf})`, int(c.VOTOS)), ficha("% dos válidos", pct(c.PCT_VALIDOS)),
    ficha("Posição", `${d.posicao_uf}º de ${int(d.n_candidatos_uf)}`), ficha("Situação", c.SITUACAO || "—"),
    c.DESTINACAO && c.DESTINACAO !== "Válido" ? ficha("Destinação dos votos", c.DESTINACAO) : null,
    d.brasil ? ficha("Votos (Brasil)", `${int(d.brasil.VOTOS)} · ${pct(d.brasil.PCT_VALIDOS)}`) : null,
    c.VICES ? ficha("Vice / suplentes", c.VICES) : null,
    d.cadeira ? ficha("Projeção de cadeira", textoCadeira(d.cadeira)) : null);
  const cab = [["Município", "NM_MUNICIPIO"], ["Votos", "VOTOS", true], ["% válidos", "PCT_VALIDOS", true],
    ["Posição", "POSICAO_MUN", true], ["Seções totalizadas", "PCT_SECOES_TOTALIZADAS", true]];
  const tabela = tabelaOrdenavel(cab, d.municipios, (r, k) =>
    k === "VOTOS" ? int(r[k]) : k.startsWith("PCT") ? pct(r[k]) : k === "POSICAO_MUN" ? `${r[k]}º` : r[k],
  (r) => mostrarEvolucao(cargo, numero, r.CD_MUNICIPIO),
  { ordem, aoOrdenar: (o) => { estado.cand.ordem = o; gravarEnderecoCandidato(); } });
  const miniDiv = el("div", { id: "mini-mapa", class: "mapa mini" });
  const legenda = el("aside", { class: "legenda" });
  const selMun = el("select", { id: "evol-mun", onchange: (e) => mostrarEvolucao(cargo, numero, Number(e.target.value)) },
    d.municipios.map((mu) => el("option", { value: mu.CD_MUNICIPIO }, mu.NM_MUNICIPIO)));
  estado.nomesMun = Object.fromEntries(d.municipios.map((mu) => [mu.CD_MUNICIPIO, mu.NM_MUNICIPIO]));
  const msgLink = el("span", { "aria-live": "polite" });
  const evol = el("section", { class: "caixa" },
    el("p", { class: "nota" }, el("button", { type: "button", class: "link",
      onclick: () => copiarLink(enderecoCandidato(), msgLink) }, "Copiar link desta consulta"), msgLink),
    el("h3", {}, "Evolução na apuração — % dos válidos do candidato no município e no estado"),
    el("div", { class: "filtros" }, el("label", {}, "Município (ou clique numa linha da tabela)", selMun)),
    el("div", { id: "evol-grafico" }));
  out.replaceChildren(...[fichas, botaoAcompanhar(cargo, c.NUMERO), evol, el("div", { class: "cand-duplo" },
    el("div", { class: "tabela-rolagem" }, tabela), el("div", {}, miniDiv, legenda))].filter(Boolean));
  if (d.municipios.length) mostrarEvolucao(cargo, numero, municipio ?? d.municipios[0].CD_MUNICIPIO);
  if (estado.mini) { estado.mini.remove(); estado.mini = null; }
  estado.mini = novoMapa(miniDiv);
  const itens = {};
  d.municipios.forEach((m) => { itens[m.CD_MUNICIPIO_IBGE] = { valor: m.PCT_VALIDOS, municipio: m.NM_MUNICIPIO }; });
  await desenharMapa(estado.mini, { tipo: "sequencial", rotulo: `% dos válidos — ${c.NOME_URNA}`, itens }, legenda, "%");
}

async function mostrarEvolucao(cargo, numero, municipio) {
  const alvo = document.getElementById("evol-grafico");
  if (!alvo) return;
  document.getElementById("evol-mun").value = String(municipio);
  if (estado.cand) { estado.cand.municipio = municipio; gravarEnderecoCandidato(); }
  let d;
  try { d = await api(`api/candidato/serie?cargo=${cargo}&numero=${numero}&municipio=${municipio}`); } catch (e) {
    alvo.replaceChildren(el("p", { class: "nota" }, `Erro: ${e.message}`)); return;
  }
  const nomeDe = (s) => (s.abrangencia === "mun" ? estado.nomesMun[s.municipio] || `município ${s.municipio}`
    : s.abrangencia === "br" ? "Brasil" : estado.uf);
  const com = d.series.filter((s) => s.pontos.length);
  const maxPts = Math.max(0, ...com.map((s) => s.pontos.length));
  if (maxPts < 2) {
    alvo.replaceChildren(el("p", { class: "nota" },
      `A evolução aparece a partir da 2ª totalização (${maxPts} registrada${maxPts === 1 ? "" : "s"} até agora).`));
    return;
  }
  const t = (iso) => new Date(iso).getTime();
  const todosX = com.flatMap((s) => s.pontos.map((p) => t(p.dt)));
  const xMin = Math.min(...todosX), xMax = Math.max(...todosX);
  const hm = (ms) => new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  alvo.replaceChildren(graficoLinhas({
    xMin, xMax, xTicks: [0, 1, 2, 3].map((i) => xMin + ((xMax - xMin) * i) / 3), xFmt: hm,
    series: com.map((s) => ({ nome: nomeDe(s), rotulo: nomeDe(s), xs: s.pontos.map((p) => t(p.dt)),
      valores: s.pontos.map((p) => p.pct), pontos: s.pontos })),
    dica: (k, xv) => `por volta de ${hm(xv)}`,
    dicaSerie: (s, j) => `${s.nome}: ${pct(s.valores[j])} · ${int(s.pontos[j].votos)} votos · ` +
      `${pct(s.pontos[j].pct_secoes)} das seções (${hm(s.xs[j])})`,
  }));
}

function ficha(rot, val) { return el("div", { class: "ficha" }, el("div", { class: "rot" }, rot), el("div", { class: "val" }, val)); }

// `opcoes.ordem`: "COLUNA-desc" | "COLUNA-asc" inicial; `opcoes.aoOrdenar(texto)` avisa cada troca de ordem
function tabelaOrdenavel(colunas, linhas, formatar, aoClicar = null, opcoes = {}) {
  const [k0, dir0] = (opcoes.ordem || "").split("-");
  let ordem = colunas.some(([, k]) => k === k0) ? { k: k0, desc: dir0 !== "asc" } : { k: colunas[1][1], desc: true };
  const corpo = el("tbody");
  const render = () => {
    const ls = [...linhas].sort((a, b) => {
      const x = a[ordem.k], y = b[ordem.k];
      const r = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "pt-BR");
      return ordem.desc ? -r : r;
    });
    corpo.replaceChildren(...ls.map((r) => el("tr", { class: aoClicar ? "clicavel" : null, onclick: aoClicar ? () => aoClicar(r) : null },
      colunas.map(([, k, n]) => el("td", { class: n ? "num" : null }, formatar(r, k))))));
  };
  const cab = el("tr", {}, colunas.map(([rot, k, n]) => el("th", {
    class: n ? "num" : null, scope: "col",
    onclick: () => {
      ordem = { k, desc: ordem.k === k ? !ordem.desc : true };
      render();
      if (opcoes.aoOrdenar) opcoes.aoOrdenar(`${ordem.k}-${ordem.desc ? "desc" : "asc"}`);
    },
  }, rot)));
  render();
  return el("table", {}, el("thead", {}, cab), corpo);
}

// ---------------------------------------------------------------- resultado por município × eleição anterior
const CAMPOS_HISTORICO = [["hist_cargo", "hist-cargo"], ["hist_numero", "hist-numero"]];
const CRITERIO_HIST = {
  "nome completo": "mesmo nome civil completo", "indicado": "indicado à mão",
  "ambíguo": "há homônimos — escolha abaixo", "não concorreu": "não encontrado pelo nome completo",
  "sem referência": "site sem eleição de referência (--comparar-com)",
};

function paramsHistorico() {
  const c = estado.cand;
  if (!c) return null;
  const q = new URLSearchParams({ cargo: c.cargo, numero: c.numero });
  const nr = document.getElementById("hist-numero").value.trim();
  const cr = document.getElementById("hist-cargo").value;
  if (nr) { q.set("numero_ref", nr); if (cr) q.set("cargo_ref", cr); }
  return q;
}

function descCandidato(c) {
  return `${c.NUMERO} — ${c.NOME_URNA} · ${c.PARTIDO}${c.FEDERACAO ? " · " + c.FEDERACAO : ""} · ${c.DS_CARGO || c.CARGO}`;
}

async function carregarHistorico() {
  const out = document.getElementById("hist-resultado");
  if (!document.getElementById("caixa-historico").open) return;
  const q = paramsHistorico();
  if (!q) { out.replaceChildren(el("p", { class: "nota" }, "Consulte um candidato acima.")); return; }
  if (estado.histEmCurso === q.toString()) return;  // o mesmo pedido já está a caminho (navegação dispara 2×)
  const pedido = (estado.histPedido = estado.histEmCurso = q.toString());
  // recarga do mesmo pedido: o que está na tela fica até chegar o novo (sem piscar "Carregando…")
  if (estado.histMostrado !== pedido) out.replaceChildren(el("p", { class: "nota" }, "Carregando…"));
  let d;
  try { d = await api(`api/candidato/historico?${q}`); } catch (e) {
    if (estado.histPedido === pedido) {
      estado.histEmCurso = estado.histMostrado = null;
      out.replaceChildren(el("p", { class: "aviso" }, e.message));
    }
    return;
  }
  if (estado.histPedido !== pedido) return;  // outro candidato pedido enquanto este carregava
  estado.histEmCurso = null;
  estado.histMostrado = pedido;
  const [a, b] = d.sufixos, anoRef = d.ano_ref ?? "anterior";
  const uf = d.linhas.find((r) => r.ABRANGENCIA === "uf") || {};
  const at = d.atual, an = d.anterior;
  const fichas = el("div", { class: "fichas" },
    ficha(`Em ${d.ano}`, descCandidato(at)), ficha(`Votos ${d.ano} (${estado.uf})`, `${int(at.VOTOS)} · ${pct(at.PCT_VALIDOS)}`),
    ficha(`Em ${anoRef}`, an ? descCandidato(an) : "—"),
    an ? ficha(`Votos ${anoRef} (${estado.uf})`, `${int(an.VOTOS)} · ${pct(an.PCT_VALIDOS)} · ${an.SITUACAO || "—"}`) : null,
    an ? ficha("Variação no estado", `${fmtComp(uf.VAR_VOTOS_PCT, "var_pct")} votos · ` +
      `${fmtComp(uf.VAR_PCT_VALIDOS_PP, "pp")}`) : null,
    ficha("Identificação", CRITERIO_HIST[d.criterio] || d.criterio));
  const notas = d.notas.map((n) => el("p", { class: "nota" }, n));
  const opcoes = d.opcoes.length ? el("ul", {}, d.opcoes.map((o) => el("li", {}, `${descCandidato(o)} (${int(o.VOTOS)} votos) `,
    el("button", { type: "button", class: "link", onclick: () => {
      document.getElementById("hist-cargo").value = String(o.CARGO);
      document.getElementById("hist-numero").value = String(o.NUMERO);
      gravarEnderecoCandidato(); carregarHistorico();
    } }, "usar este")))) : null;
  const salvar = el("a", { class: "botao-salvar", href: `api/candidato/historico/planilha?${q}`, download: "" },
    "Salvar planilha (.xlsx)");
  const cab = [["Município", "NM_MUNICIPIO"], [`Votos ${a}`, `VOTOS_${a}`, true], [`% válidos ${a}`, `PCT_VALIDOS_${a}`, true],
    [`Posição ${a}`, `POSICAO_${a}`, true], [`Votos ${b}`, `VOTOS_${b}`, true], [`% válidos ${b}`, `PCT_VALIDOS_${b}`, true],
    [`Posição ${b}`, `POSICAO_${b}`, true], ["Variação dos votos", "VAR_VOTOS_PCT", true],
    ["Variação % válidos", "VAR_PCT_VALIDOS_PP", true], ["Seções totalizadas", "PCT_SECOES_TOTALIZADAS", true]];
  const tabela = tabelaOrdenavel(cab, d.linhas.filter((r) => r.ABRANGENCIA === "mun"), (r, k) => {
    const x = r[k];
    if (k === "VAR_VOTOS_PCT") return fmtComp(x, "var_pct");
    if (k === "VAR_PCT_VALIDOS_PP") return fmtComp(x, "pp");
    if (k.startsWith("VOTOS_")) return int(x);
    if (k.startsWith("POSICAO_")) return x === null || x === undefined ? "—" : `${x}º`;
    if (k.startsWith("PCT")) return pct(x);
    return x;
  });
  out.replaceChildren(...[fichas, ...notas, opcoes, salvar, el("div", { class: "tabela-rolagem" }, tabela)].filter(Boolean));
}

function aplicarHistorico(q) {
  const caixa = document.getElementById("caixa-historico");
  for (const [k, id] of CAMPOS_HISTORICO) document.getElementById(id).value = q.get(k) ?? "";
  if (caixa.open !== (q.get("hist") === "1")) caixa.open = q.get("hist") === "1";  // o "toggle" carrega
  else carregarHistorico();
}

document.getElementById("form-historico").addEventListener("submit", (e) => {
  e.preventDefault(); gravarEnderecoCandidato(); carregarHistorico();
});
document.getElementById("caixa-historico").addEventListener("toggle", () => { gravarEnderecoCandidato(); carregarHistorico(); });

// ---------------------------------------------------------------- planilha histórica
document.getElementById("form-planilha").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = new URLSearchParams({
    ano: document.getElementById("pl-ano").value, cargo: document.getElementById("pl-cargo").value,
    numero: document.getElementById("pl-numero").value,
  });
  const mun = document.getElementById("pl-municipio").value.trim();
  const cmp = document.getElementById("pl-comparar").value.trim();
  if (mun) q.set("municipio", mun);
  if (cmp) q.set("comparar_com", cmp);
  const msg = document.getElementById("pl-msg");
  msg.textContent = "Gerando planilha…";
  try {
    const r = await fetch(`api/planilha?${q}`);
    if (!r.ok) { msg.textContent = `Erro: ${(await r.json()).detail}`; return; }
    const blob = await r.blob();
    const a = el("a", { href: URL.createObjectURL(blob), download: `planilha_${q.get("numero")}_${q.get("ano")}.xlsx` });
    document.body.append(a); a.click(); a.remove();
    msg.textContent = "Planilha gerada.";
  } catch (err) { msg.textContent = `Erro: ${err.message}`; }
});

// ---------------------------------------------------------------- mapas
function novoMapa(div) {
  const m = L.map(div, { preferCanvas: true }).setView([-22.25, -42.6], 8);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "© OpenStreetMap", opacity: 0.35,
  }).addTo(m);
  return m;
}

function garantirMapa() {
  if (!estado.mapa) estado.mapa = novoMapa(document.getElementById("mapa"));
}

async function malha() {
  if (!estado.geo) estado.geo = await api("geo/municipios.geojson");
  return estado.geo;
}

function quebrasQuantis(valores, n = 5) {
  const v = [...valores].filter((x) => x !== null && x !== undefined).sort((a, b) => a - b);
  if (!v.length) return [];
  const q = [];
  for (let i = 1; i < n; i++) q.push(v[Math.min(v.length - 1, Math.floor((i * v.length) / n))]);
  return [...new Set(q)];
}

// `escala` (opcional) fixa as faixas de cor entre quadros da linha do tempo; a função devolve a escala usada
async function desenharMapa(mapa, dados, legendaEl, sufixo = "", escala = null, camada = "municipios") {
  const geo = camada === "bairros" ? await malhaBairros() : await malha();
  const idDe = (ft) => (camada === "bairros" ? ft.properties.CD_BAIRRO : ft.properties.codarea);
  if (mapa._camada) mapa.removeLayer(mapa._camada);
  if (mapa._contornos) { mapa.removeLayer(mapa._contornos); mapa._contornos = null; }
  const seq = ["--mapa-1", "--mapa-2", "--mapa-3", "--mapa-4", "--mapa-5"].map(cor);  // amarelo (menos) -> vermelho (mais)
  const semDado = cor("--sem-dado");
  const ehPct = sufixo === "%" || (dados.metrica && dados.metrica !== "votos_candidato");
  // percentuais pequenos (ex.: deputado com 0,05%) precisam de mais casas para as faixas não se repetirem
  const vals = Object.values(dados.itens).map((i) => i.valor).filter((x) => x !== null && x !== undefined);
  const casas = ehPct && vals.length && Math.max(...vals) < 1 ? 3 : 2;
  const fmtPctN = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const fmt = (x) => (x === null || x === undefined ? "—" : ehPct ? fmtPctN.format(x) + "%" : int(x));
  let corDe, itensLegenda;
  if (dados.tipo === "categorico") {
    // no mapa todos os pares de cor se tocam: só 3 cores categóricas; o resto vira "Outros"
    const top = (dados.categorias || []).slice(0, 3);
    const cores = ["--serie-1", "--serie-2", "--serie-3"].map(cor);
    const idx = new Map(top.map((c, i) => [c.NUMERO, i]));
    corDe = (it) => (it ? (idx.has(it.valor) ? cores[idx.get(it.valor)] : cor("--outros")) : semDado);
    itensLegenda = [...top.map((c, i) => [cores[i], `${c.NUMERO} ${c.NOME_URNA} (${c.PARTIDO})`]), [cor("--outros"), "Outros"]];
  } else {
    const valores = Object.values(dados.itens).map((i) => i.valor);
    if (!escala) {
      const vv = valores.filter((x) => x !== null && x !== undefined);
      escala = dados.metrica === "secoes_totalizadas_pct" ? { qb: [20, 40, 60, 80], minimo: 0, maximo: 100 }
        : { qb: quebrasQuantis(vv), minimo: Math.min(...vv), maximo: Math.max(...vv) };
    }
    const qb = escala.qb;
    corDe = (it) => {
      if (!it || it.valor === null || it.valor === undefined) return semDado;
      let k = 0;
      while (k < qb.length && it.valor > qb[k]) k++;
      return seq[Math.min(k, seq.length - 1)];
    };
    const lim = [escala.minimo, ...qb, escala.maximo];
    itensLegenda = lim.slice(0, -1).map((a, i) => [seq[i], `${fmt(a)} – ${fmt(lim[i + 1])}`]);
  }
  itensLegenda.push([semDado, "sem dado"]);
  const f = (it) => (!it ? "sem dado" : dados.tipo === "categorico" ? it.rotulo : fmt(it.valor));
  const coresExport = {};
  mapa._camada = L.geoJSON(geo, {
    style: (ft) => {
      const c = corDe(dados.itens[idDe(ft)]);
      coresExport[idDe(ft)] = c;
      return { fillColor: c, fillOpacity: 0.85, color: cor("--superficie"), weight: camada === "bairros" ? 0.5 : 1 };
    },
    onEachFeature: (ft, layer) => {
      const it = dados.itens[idDe(ft)];
      const nome = it ? it.municipio
        : camada === "bairros" ? `${ft.properties.NM_BAIRRO} — ${ft.properties.NM_MUN}` : ft.properties.codarea;
      layer.bindTooltip(() => { const d = el("div", {}, el("strong", {}, nome), el("br"), f(it)); return d; }, { sticky: true });
      layer.on("mouseover", () => layer.setStyle({ weight: 3, color: cor("--texto") }));
      layer.on("mouseout", () => layer.setStyle({ weight: camada === "bairros" ? 0.5 : 1, color: cor("--superficie") }));
    },
  }).addTo(mapa);
  if (camada === "bairros") {  // contorno dos municípios por cima: situa os bairros e os municípios sem malha
    mapa._contornos = L.geoJSON(await malha(), {
      interactive: false, style: { fill: false, color: cor("--texto"), weight: 0.8, opacity: 0.45 },
    }).addTo(mapa);
  }
  if (!mapa._enquadrado) {  // só na 1ª vez: a atualização automática não pode desfazer o zoom do usuário
    mapa.fitBounds(mapa._camada.getBounds(), { padding: [10, 10] });
    mapa._enquadrado = true;
  }
  const titulo = dados.momento ? `${dados.rotulo} — às ${hora(dados.momento)}` : dados.rotulo;
  mapa._export = { camada, cores: coresExport, legenda: itensLegenda, titulo };
  legendaEl.replaceChildren(el("h4", {}, titulo),
    ...itensLegenda.map(([c, t]) => el("div", {}, el("span", { class: "amostra", style: { background: c } }), t)));
  return escala;
}

const metricaSel = document.getElementById("mapa-metrica");
const numeroMapa = document.getElementById("mapa-numero");
metricaSel.addEventListener("change", () => {
  numeroMapa.disabled = !metricaSel.value.endsWith("_candidato");
  if (!numeroMapa.disabled) preencherLista(document.getElementById("mapa-cargo").value, "mapa-lista");
});
document.getElementById("mapa-cargo").addEventListener("change", (e) => {
  estado.candidatosCache = {};
  estado.lt.idx = Number.MAX_SAFE_INTEGER;  // novo cargo: começa no momento mais recente
  carregarMomentos();
  if (!numeroMapa.disabled) preencherLista(e.target.value, "mapa-lista");
});
document.getElementById("form-mapa").addEventListener("submit", (e) => { e.preventDefault(); atualizarMapa(); });
document.getElementById("mapa-locais").addEventListener("change", alternarLocais);

async function atualizarMapa() {
  garantirMapa();
  const cargo = document.getElementById("mapa-cargo").value;
  const metrica = metricaSel.value;
  const legenda = document.getElementById("mapa-legenda");
  // por local, cada camada valida o que precisa (a métrica escondida não vale nas camadas sem ela)
  if (estado.detalhe === "locais") { await atualizarMapaLocais(cargo, legenda); return; }
  let q = `api/mapa?cargo=${cargo}&metrica=${metrica}`;
  let numero = null;
  if (metrica.endsWith("_candidato")) {
    numero = /^\d+$/.test(numeroMapa.value.trim()) ? Number(numeroMapa.value.trim())
      : estado.detalhe !== "municipios" ? null : await resolverNumero(cargo, numeroMapa.value || "");
    if (numero === null) { legenda.replaceChildren(el("p", {}, "Informe o número de um candidato.")); return; }
    q += `&numero=${numero}`;
  }
  if (estado.detalhe === "bairros") { await atualizarMapaBairros(cargo, metrica, numero, legenda); return; }
  const lt = estado.lt;
  const noPassado = lt.momentos.length > 1 && lt.idx < lt.momentos.length - 1;
  const chaveEscala = q;  // a escala do quadro "agora" vale para todos os quadros da mesma consulta
  try {
    if (noPassado && !lt.escalas[chaveEscala]) {  // escala ainda não calculada: pega do momento mais recente
      lt.escalas[chaveEscala] = await desenharMapa(estado.mapa, await api(q), legenda);
    }
    const dados = await api(noPassado ? `${q}&momento=${encodeURIComponent(lt.momentos[lt.idx])}` : q);
    const esc = await desenharMapa(estado.mapa, dados, legenda, "", noPassado ? lt.escalas[chaveEscala] : null);
    if (!noPassado) lt.escalas[chaveEscala] = esc;
    gravarEnderecoMapa();
  } catch (e) { legenda.replaceChildren(el("p", {}, `Erro: ${e.message}`)); }
}

// ---------------------------------------------------------------- endereço da aba Candidato
// #candidato?cargo=7&numero=13713&municipio=60011&ordem=VOTOS-desc (formato antigo /cargo/número/município aceito)
// campos da planilha histórica no endereço (prefixo pl_), só com o bloco aberto (pl=1); idem o resultado
// por município × eleição anterior (hist=1, hist_cargo, hist_numero)
const CAMPOS_PLANILHA = [["pl_ano", "pl-ano"], ["pl_cargo", "pl-cargo"], ["pl_numero", "pl-numero"],
  ["pl_municipio", "pl-municipio"], ["pl_comparar", "pl-comparar"]];

function enderecoCandidato() {
  const c = estado.cand;
  const q = new URLSearchParams(c ? { cargo: c.cargo, numero: c.numero } : {});
  if (c && c.municipio !== null && c.municipio !== undefined) q.set("municipio", String(c.municipio));
  if (c && c.ordem) q.set("ordem", c.ordem);
  if (document.getElementById("caixa-historico").open) {
    q.set("hist", "1");
    for (const [k, id] of CAMPOS_HISTORICO) {
      const v = document.getElementById(id).value.trim();
      if (v) q.set(k, v);
    }
  }
  if (document.getElementById("caixa-planilha").open) {
    q.set("pl", "1");
    for (const [k, id] of CAMPOS_PLANILHA) {
      const v = document.getElementById(id).value.trim();
      if (v) q.set(k, v);
    }
  }
  const s = q.toString();
  return s ? `#candidato?${s}` : "#candidato";
}

function aplicarPlanilha(q) {
  const caixa = document.getElementById("caixa-planilha");
  caixa.open = q.get("pl") === "1";
  if (!caixa.open) return;
  for (const [k, id] of CAMPOS_PLANILHA) {
    const campo = document.getElementById(id), v = q.get(k);
    if (v === null) continue;
    if (campo.tagName === "SELECT" && ![...campo.options].some((o) => o.value === v)) continue;  // valor desconhecido
    campo.value = v;
  }
}

// mudanças no formulário da planilha e abrir/fechar o bloco também vão para o endereço
document.getElementById("caixa-planilha").addEventListener("toggle", () => gravarEnderecoCandidato());
for (const [, id] of CAMPOS_PLANILHA) {
  document.getElementById(id).addEventListener("change", () => gravarEnderecoCandidato());
}

function gravarEnderecoCandidato() {
  if (estado.aba !== "candidato") return;
  const alvo = enderecoCandidato();
  if (location.hash !== alvo) history.replaceState(null, "", alvo);
}

async function copiarLink(hash, msg) {
  const url = `${location.origin}${location.pathname}${hash}`;
  try { await navigator.clipboard.writeText(url); msg.textContent = " copiado."; }
  catch (_) { msg.textContent = ` ${url}`; }  // sem permissão de área de transferência: mostra o link
  setTimeout(() => { msg.textContent = ""; }, 4000);
}

// ---------------------------------------------------------------- mapa por bairro (malha do IBGE + microdados)
const detalheSel = document.getElementById("mapa-detalhe");
const anoBairrosSel = document.getElementById("mapa-ano");
const cargoMapa = document.getElementById("mapa-cargo");
const OPCOES_CARGO_MUN = [...cargoMapa.options].map((o) => [o.value, o.textContent]);
const METRICAS_BAIRRO = ["vencedor", "pct_candidato", "votos_candidato", "brancos_nulos_pct", "brancos_pct",
  "nulos_pct", "abstencao_pct", "comparecimento_pct"];
estado.detalhe = "municipios";

async function malhaBairros() {
  if (!estado.geoBairros) estado.geoBairros = await api("geo/bairros.geojson");
  return estado.geoBairros;
}

function preencherCargos(opcoes, preferido) {
  const atual = String(preferido ?? cargoMapa.value);
  cargoMapa.replaceChildren(...opcoes.map(([val, t]) => el("option", { value: val }, t)));
  cargoMapa.value = opcoes.some(([val]) => val === atual) ? atual : (opcoes[0]?.[0] ?? "");
}

// ajusta os controles ao detalhe escolhido; no modo bairros, anos e cargos vêm dos microdados no cache
async function prepararDetalhe(anoPreferido = null, cargoPreferido = null) {
  const bairros = detalheSel.value !== "municipios";  // bairros ou locais: microdados (anos e cargos do cache)
  const locais = detalheSel.value === "locais";
  if (estado.detalhe === "municipios" && bairros) estado.cargoMun = cargoMapa.value;  // volta ao mesmo cargo depois
  estado.detalhe = detalheSel.value;
  document.getElementById("mapa-l-ano").hidden = !bairros;
  document.getElementById("bairros-nota").hidden = detalheSel.value !== "bairros";
  document.getElementById("locais-nota").hidden = !locais;
  document.getElementById("mapa-l-locais").hidden = locais;  // os pontos já são os locais
  if (locais && document.getElementById("mapa-locais").checked) {
    document.getElementById("mapa-locais").checked = false;
    alternarLocais({ target: document.getElementById("mapa-locais") });
  }
  for (const op of metricaSel.options) op.disabled = bairros && !METRICAS_BAIRRO.includes(op.value);
  if (metricaSel.selectedOptions[0]?.disabled) metricaSel.value = "vencedor";
  if (locais) await prepararLocais();
  ajustarControlesLocais();
  if (!bairros) { preencherCargos(OPCOES_CARGO_MUN, cargoPreferido ?? estado.cargoMun); return; }
  document.getElementById("linha-tempo").hidden = true;  // microdados = resultado final: sem linha do tempo
  document.getElementById("lt-nota").hidden = true;
  if (!estado.bairrosInfo) estado.bairrosInfo = await api("api/bairros/anos");
  const info = estado.bairrosInfo;
  const anos = Object.keys(info.anos).map(Number);
  if (!anos.includes(estado.ano)) anos.push(estado.ano);  // o ano do site (2026: só após a publicação)
  anos.sort((a, b) => b - a);
  const padrao = info.anos[estado.ano] ? estado.ano : (anos.find((a) => info.anos[a]) ?? anos[0]);
  const escolhido = anos.map(String).includes(String(anoPreferido ?? anoBairrosSel.value))
    ? String(anoPreferido ?? anoBairrosSel.value) : String(padrao);
  anoBairrosSel.replaceChildren(...anos.map((a) => el("option", { value: a }, String(a))));
  anoBairrosSel.value = escolhido;
  const cargos = info.anos[escolhido] || [1, 3, 5, 6, 7];
  preencherCargos(cargos.map((c) => [String(c), info.cargos[c]]), cargoPreferido);
}

async function atualizarMapaBairros(cargo, metrica, numero, legenda) {
  const nota = document.getElementById("bairros-nota");
  let q = `api/mapa/bairros?ano=${anoBairrosSel.value}&cargo=${cargo}&metrica=${metrica}&turno=${estado.turno || 1}`;
  if (numero !== null) q += `&numero=${numero}`;
  try {
    const dados = await api(q);
    await desenharMapa(estado.mapa, dados, legenda, "", null, "bairros");
    const c = dados.cobertura;
    nota.textContent = `Bairros do IBGE (Censo 2022): ${int(c.bairros_com_dado)} de ${int(c.bairros)} bairros têm local ` +
      `de votação (${int(c.locais_em_bairro)} locais). Municípios sem malha de bairros aparecem só com o contorno. ` +
      "Cada local é contado no bairro que contém sua coordenada.";
  } catch (e) {
    if (estado.mapa._camada) { estado.mapa.removeLayer(estado.mapa._camada); estado.mapa._camada = null; }
    if (estado.mapa._contornos) { estado.mapa.removeLayer(estado.mapa._contornos); estado.mapa._contornos = null; }
    estado.mapa._export = null;
    legenda.replaceChildren(el("p", {}, `Erro: ${e.message}`));
    nota.textContent = "";
  }
  gravarEnderecoMapa();
}

detalheSel.addEventListener("change", async () => {
  await prepararDetalhe();
  if (detalheSel.value === "municipios") await carregarMomentos();
  atualizarMapa();
});
anoBairrosSel.addEventListener("change", async () => { await prepararDetalhe(anoBairrosSel.value); atualizarMapa(); });

// ---------------------------------------------------------------- mapa por local de votação (rodada 32)
// Um ponto por local (microdados): voto, perfil do eleitorado, resíduo do Perfil × voto ou variação desde a eleição
// anterior (rodada 46: partido pela entidade, abstenção, brancos/nulos) ou destino dos eliminados no 2º turno
// (rodada 47: microdados dos dois turnos). Área do ponto ∝ eleitorado.
const METRICAS_VARIACAO = ["pct_candidato", "abstencao_pct", "comparecimento_pct", "brancos_nulos_pct", "brancos_pct", "nulos_pct"];
const camadaSel = document.getElementById("mapa-camada");
const indicadorSel = document.getElementById("mapa-indicador");
const transfSel = document.getElementById("mapa-transf");
const municipioLocSel = document.getElementById("mapa-municipio");

async function prepararLocais() {
  if (estado.locaisInfo) return;
  estado.locaisInfo = await api("api/perfil/info?unidade=local");
  const info = estado.locaisInfo;
  const grupos = {};
  for (const [k, d] of Object.entries(info.indicadores)) (grupos[d.fonte] = grupos[d.fonte] || []).push([k, d.rotulo]);
  indicadorSel.replaceChildren(...Object.entries(grupos).map(([fonte, itens]) =>
    el("optgroup", { label: fonte }, ...itens.map(([k, r]) => el("option", { value: k }, r)))));
  municipioLocSel.replaceChildren(el("option", { value: "" }, `Todo o estado (${estado.uf})`),
    ...info.municipios.map((m) => el("option", { value: m.CD_MUN }, m.NM_MUN)));
}

function ajustarControlesLocais() {
  const locais = estado.detalhe === "locais";
  const camada = camadaSel.value;
  document.getElementById("mapa-l-camada").hidden = !locais;
  document.getElementById("mapa-l-municipio").hidden = !locais;
  const comMetrica = ["voto", "variacao"].includes(camada);
  document.getElementById("mapa-l-indicador").hidden = !locais || comMetrica || camada === "transferencia";
  document.getElementById("mapa-l-transf").hidden = !locais || camada !== "transferencia";
  document.getElementById("mapa-l-metrica").hidden = locais && !comMetrica;
  if (locais) {
    const permitidas = camada === "variacao" ? METRICAS_VARIACAO : METRICAS_BAIRRO;
    for (const op of metricaSel.options) op.disabled = !permitidas.includes(op.value);
    if (metricaSel.selectedOptions[0]?.disabled) metricaSel.value = camada === "variacao" ? "pct_candidato" : "vencedor";
  }
  numeroMapa.disabled = locais ? !(camada === "residuo" || (comMetrica && metricaSel.value.endsWith("_candidato")))
    : !metricaSel.value.endsWith("_candidato");
  numeroMapa.placeholder = !locais ? "número" : camada === "residuo" ? "número (2 dígitos = partido)"
    : camada === "variacao" ? "número (vale o partido)" : "número";
}
camadaSel.addEventListener("change", () => { ajustarControlesLocais(); atualizarMapa(); });
indicadorSel.addEventListener("change", () => atualizarMapa());
transfSel.addEventListener("change", () => atualizarMapa());
municipioLocSel.addEventListener("change", () => { if (estado.mapa) estado.mapa._enquadrado = false; atualizarMapa(); });
metricaSel.addEventListener("change", ajustarControlesLocais);

async function atualizarMapaLocais(cargo, legenda) {
  const nota = document.getElementById("locais-nota");
  const camada = camadaSel.value;
  const q = new URLSearchParams({ ano: anoBairrosSel.value, camada, cargo, turno: estado.turno || 1 });
  const num = numeroMapa.value.trim();
  if (camada === "voto" || camada === "variacao") {
    q.set("metrica", metricaSel.value);
    if (metricaSel.value.endsWith("_candidato")) {
      if (!/^\d+$/.test(num)) {
        legenda.replaceChildren(el("p", {}, camada === "variacao" ? "Informe o número de um candidato ou partido (vale o partido)."
          : "Informe o número de um candidato.")); return;
      }
      q.set("numero", num);
    }
  } else if (camada === "transferencia") {
    q.set("metrica", transfSel.value);
    q.set("turno", "2");
  } else {
    q.set("indicador", indicadorSel.value);
    if (camada === "residuo") {
      if (!/^\d+$/.test(num)) {
        legenda.replaceChildren(el("p", {}, "Informe o número do candidato (ou 2 dígitos para o partido).")); return;
      }
      q.set("numero", num);
    }
  }
  if (municipioLocSel.value) q.set("municipio", municipioLocSel.value);
  legenda.replaceChildren(el("p", { class: "nota" }, "carregando os locais…"));
  try {
    const d = await api(`api/mapa/locais?${q}`);
    await desenharPontos(estado.mapa, d, legenda);
    const c = d.cobertura;
    const est = d.estatistica;
    nota.textContent = `${int(c.com_valor)} de ${int(c.locais)} locais com valor (coordenada do cadastro de eleitorado ` +
      `de ${d.ano}); a área do ponto é proporcional ao eleitorado do local.` +
      (est && est.pearson !== null ? ` Reta voto × indicador: r = ${est.pearson.toFixed(2).replace(".", ",")}, ` +
        `R² = ${est.r2.toFixed(2).replace(".", ",")}, ${int(est.n)} locais com ≥ ${int(d.min_validos)} votos válidos. ` +
        "Azul: o voto foi MAIOR que o esperado pelo indicador; vermelho: menor. Correlação ecológica." : "") +
      (camada === "variacao" ? ` Só os locais presentes em ${d.ano_ref} e ${d.ano} (mesmo município, zona e nº do local); ` +
        "partido pela entidade (fusões e trocas de nº). Azul: subiu; vermelho: caiu." : "") +
      (camada === "transferencia" ? " Inferência ecológica (padrão médio, não o voto de pessoas): o destino dos " +
        "eliminados é estimado por município (todos os locais do município têm o mesmo valor); eliminados, abstenção " +
        "extra e o resíduo são de cada local." : "") +
      (!d.itens.length && camada === "residuo" ? ` Nenhum local com ${int(d.min_validos)} votos válidos ou mais ` +
        "para o resíduo (ele só usa locais com votos suficientes)." : "");
  } catch (e) {
    for (const k of ["_camada", "_contornos"]) if (estado.mapa[k]) { estado.mapa.removeLayer(estado.mapa[k]); estado.mapa[k] = null; }
    estado.mapa._export = null;
    legenda.replaceChildren(el("p", {}, `Erro: ${e.message}`));
    nota.textContent = "";
  }
  gravarEnderecoMapa();
}

function formatoLocais(d) {
  if (d.unidade === "p.p.") return (x) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(1).replace(".", ",")} p.p.`;
  if (d.unidade === "%") {
    const vals = d.itens.map((i) => i.valor);
    const casas = vals.length && Math.max(...vals) < 1 ? 3 : 1;
    return (x) => `${x.toFixed(casas).replace(".", ",")}%`;
  }
  return (x) => int(Math.round(x));
}

async function desenharPontos(mapa, d, legendaEl) {
  for (const k of ["_camada", "_contornos"]) if (mapa[k]) { mapa.removeLayer(mapa[k]); mapa[k] = null; }
  const fmt = formatoLocais(d);
  let corDe, itensLegenda;
  const vals = d.itens.map((i) => i.valor);
  if (d.tipo === "categorico") {
    const top = (d.categorias || []).slice(0, 3);
    const cores = ["--serie-1", "--serie-2", "--serie-3"].map(cor);
    const idx = new Map(top.map((c, i) => [c.NUMERO, i]));
    corDe = (v) => (idx.has(v) ? cores[idx.get(v)] : cor("--outros"));
    itensLegenda = [...top.map((c, i) => [cores[i], `${c.NUMERO} ${c.NOME_URNA}`]), [cor("--outros"), "Outros"]];
  } else if (d.tipo === "divergente") {
    // faixas pelos quantis de |resíduo| (5 mil pontos: o máximo seria um ponto extremo)
    const abs = vals.map(Math.abs).sort((a, b) => a - b);
    const q = (f) => abs[Math.min(abs.length - 1, Math.floor(f * abs.length))] || 1e-9;
    const lim = [q(0.33), q(0.66), q(0.9)];
    const cores = ["--div-n3", "--div-n2", "--div-n1", "--div-0", "--div-p1", "--div-p2", "--div-p3"].map(cor);
    corDe = (v) => { const a = Math.abs(v); const k = a < lim[0] ? 0 : a < lim[1] ? 1 : a < lim[2] ? 2 : 3; return cores[v < 0 ? 3 - k : 3 + k]; };
    const m = (x) => Math.abs(x).toFixed(1).replace(".", ",");
    const variacao = d.sentido === "variacao";
    itensLegenda = [[cores[6], `${variacao ? "subiu" : "voto maior que o esperado:"} mais de ${m(lim[2])} p.p.`],
      [cores[5], `+${m(lim[1])} a +${m(lim[2])} p.p.`],
      [cores[4], `+${m(lim[0])} a +${m(lim[1])} p.p.`], [cores[3], `${variacao ? "estável" : "como esperado"} (±${m(lim[0])} p.p.)`],
      [cores[2], `−${m(lim[0])} a −${m(lim[1])} p.p.`], [cores[1], `−${m(lim[1])} a −${m(lim[2])} p.p.`],
      [cores[0], `${variacao ? "caiu" : "voto menor que o esperado:"} mais de ${m(lim[2])} p.p.`]];
  } else {
    const seq = ["--mapa-1", "--mapa-2", "--mapa-3", "--mapa-4", "--mapa-5"].map(cor);  // amarelo (menos) -> vermelho (mais)
    const qb = quebrasQuantis(vals);
    corDe = (v) => { let k = 0; while (k < qb.length && v > qb[k]) k++; return seq[Math.min(k, seq.length - 1)]; };
    const lim = [Math.min(...vals), ...qb, Math.max(...vals)];
    itensLegenda = lim.slice(0, -1).map((a, i) => [seq[i], `${fmt(a)} – ${fmt(lim[i + 1])}`]);
  }
  mapa._contornos = L.geoJSON(await malha(), {  // municípios por baixo: situa os pontos
    interactive: false, style: { fill: false, color: cor("--texto"), weight: 0.6, opacity: 0.35 },
  }).addTo(mapa);
  const renderer = L.canvas({ padding: 0.5 });
  const coresExport = {};
  const raio = (e) => Math.max(2.5, Math.min(12, Math.sqrt(e || 0) / 9));
  // os maiores primeiro: os pequenos ficam por cima e continuam clicáveis
  const pontos = [...d.itens].sort((a, b) => (b.eleitores || 0) - (a.eleitores || 0));
  mapa._camada = L.layerGroup(pontos.map((it) => {
    const c = corDe(it.valor);
    coresExport[it.u] = c;
    const mk = L.circleMarker([it.lat, it.lon], { renderer, radius: raio(it.eleitores), color: cor("--superficie"),
      weight: 0.8, fillColor: c, fillOpacity: 0.92 });
    mk.bindTooltip(() => el("div", {}, el("strong", {}, it.nome), el("br"), `${it.mun} · zona ${it.zona}, local ${it.local}`, el("br"),
      d.tipo === "categorico" ? (it.rotulo || String(it.valor)) : fmt(it.valor),
      d.lados && it.antes != null ? [el("br"), `${d.lados[0]}: ${it.antes.toFixed(2).replace(".", ",")}% → ${d.lados[1]}: ${it.depois.toFixed(2).replace(".", ",")}%`]
        : d.tipo === "divergente" ? [el("br"), `voto ${it.voto.toFixed(2).replace(".", ",")}% · indicador ${int(Math.round(it.indicador * 100) / 100)}`] : null,
      el("br"), `${int(it.eleitores)} eleitores`), { sticky: true });
    return mk;
  })).addTo(mapa);
  if (!mapa._enquadrado && pontos.length) {
    mapa.fitBounds(L.latLngBounds(pontos.map((it) => [it.lat, it.lon])), { padding: [10, 10] });
    mapa._enquadrado = true;
  }
  mapa._export = { camada: "locais", ano: d.ano, cores: coresExport, legenda: itensLegenda, titulo: d.rotulo };
  legendaEl.replaceChildren(el("h4", {}, d.rotulo),
    ...itensLegenda.map(([c, t]) => el("div", {}, el("span", { class: "amostra redonda", style: { background: c } }), t)),
    el("p", { class: "nota" }, "Área do ponto ∝ eleitorado do local."));
}

// ---------------------------------------------------------------- endereço do mapa
// #mapas?cargo=3&metrica=pct_candidato&numero=68&momento=2026-09-29T18:30:00&locais=1
// (sem `momento` = acompanha o mais recente). replaceState: não enche o histórico nem dispara hashchange.
function enderecoMapa() {
  const q = new URLSearchParams({ cargo: document.getElementById("mapa-cargo").value, metrica: metricaSel.value });
  if (metricaSel.value.endsWith("_candidato") && numeroMapa.value.trim()) q.set("numero", numeroMapa.value.trim());
  const lt = estado.lt;
  if (estado.detalhe !== "municipios") {
    q.set("detalhe", estado.detalhe);
    q.set("ano_bairros", anoBairrosSel.value);
    if (estado.detalhe === "locais") {
      q.set("camada", camadaSel.value);
      if (["perfil", "residuo"].includes(camadaSel.value)) q.set("indicador", indicadorSel.value);
      if (camadaSel.value === "transferencia") q.set("transf", transfSel.value);
      if (camadaSel.value === "residuo" && numeroMapa.value.trim()) q.set("numero", numeroMapa.value.trim());
      if (municipioLocSel.value) q.set("municipio", municipioLocSel.value);
    }
  } else if (lt.momentos.length > 1 && lt.idx < lt.momentos.length - 1) q.set("momento", lt.momentos[lt.idx]);
  if (document.getElementById("mapa-locais").checked) q.set("locais", "1");
  return `#mapas?${q}`;
}

function gravarEnderecoMapa() {
  if (estado.aba !== "mapas") return;
  const alvo = enderecoMapa();
  if (location.hash !== alvo) history.replaceState(null, "", alvo);
}

async function aplicarEnderecoMapa(params) {
  const q = new URLSearchParams(params);
  const metrica = q.get("metrica");
  detalheSel.value = ["bairros", "locais"].includes(q.get("detalhe")) ? q.get("detalhe") : "municipios";
  await prepararDetalhe(q.get("ano_bairros"), q.get("cargo"));  // cargos dependem do detalhe e do ano
  if (metrica && [...metricaSel.options].some((o) => o.value === metrica && !o.disabled)) metricaSel.value = metrica;
  const temOpcao = (sel, val) => val !== null && [...sel.options].some((o) => o.value === val);
  if (temOpcao(camadaSel, q.get("camada"))) camadaSel.value = q.get("camada");
  if (temOpcao(indicadorSel, q.get("indicador"))) indicadorSel.value = q.get("indicador");
  if (temOpcao(transfSel, q.get("transf"))) transfSel.value = q.get("transf");
  if (temOpcao(municipioLocSel, q.get("municipio"))) municipioLocSel.value = q.get("municipio");
  ajustarControlesLocais();
  numeroMapa.value = q.get("numero") || "";
  // o momento vira índice só quando os momentos do cargo chegarem (carregarMomentos)
  estado.lt.pedido = q.get("momento") || null;
  estado.lt.idx = Number.MAX_SAFE_INTEGER;
  const locais = document.getElementById("mapa-locais");
  if (locais.checked !== (q.get("locais") === "1")) {
    locais.checked = q.get("locais") === "1";
    alternarLocais({ target: locais });
  }
}

document.getElementById("copiar-link").addEventListener("click",
  () => copiarLink(enderecoMapa(), document.getElementById("copiar-msg")));

// ---------------------------------------------------------------- linha do tempo do mapa
estado.lt = { momentos: [], idx: 0, escalas: {}, timer: null };
const ltRange = document.getElementById("lt-range");
const ltPlay = document.getElementById("lt-play");

async function carregarMomentos() {
  const lt = estado.lt;
  if (estado.detalhe !== "municipios") return;  // bairros/locais: microdados finais, sem linha do tempo
  const noFim = lt.idx >= lt.momentos.length - 1;
  try { lt.momentos = (await api(`api/mapa/momentos?cargo=${document.getElementById("mapa-cargo").value}`)).momentos; }
  catch (_) { lt.momentos = []; }
  const barra = document.getElementById("linha-tempo"), nota = document.getElementById("lt-nota");
  barra.hidden = lt.momentos.length < 2;
  nota.hidden = !barra.hidden;
  nota.textContent = `Linha do tempo: aparece a partir da 2ª totalização municipal ` +
    `(${lt.momentos.length} registrada${lt.momentos.length === 1 ? "" : "s"} para este cargo).`;
  ltRange.max = String(Math.max(0, lt.momentos.length - 1));
  if (noFim) lt.idx = lt.momentos.length - 1;  // acompanhando o "agora": continua no fim
  if (lt.pedido) {  // momento vindo do endereço: última totalização até aquela hora (ISO compara como texto)
    const ate = lt.momentos.filter((mm) => mm <= lt.pedido).length - 1;
    lt.idx = Math.max(0, ate);
    lt.pedido = null;
  }
  ltRange.value = String(lt.idx);
  rotuloMomento();
}

function rotuloMomento() {
  const lt = estado.lt;
  if (!lt.momentos.length) return;
  const ultimo = lt.idx === lt.momentos.length - 1;
  document.getElementById("lt-rotulo").textContent =
    `${hora(lt.momentos[lt.idx])}${ultimo ? " (mais recente)" : ""} · totalização ${lt.idx + 1} de ${lt.momentos.length}`;
}

ltRange.addEventListener("input", () => { estado.lt.idx = Number(ltRange.value); rotuloMomento(); atualizarMapa(); });
ltPlay.addEventListener("click", () => {
  const lt = estado.lt;
  if (lt.timer) { clearInterval(lt.timer); lt.timer = null; ltPlay.textContent = "▶"; return; }
  if (lt.idx >= lt.momentos.length - 1) lt.idx = 0;
  ltPlay.textContent = "⏸"; ltPlay.setAttribute("aria-label", "Pausar");
  const passo = async () => {
    ltRange.value = String(lt.idx); rotuloMomento(); await atualizarMapa();
    if (lt.idx >= lt.momentos.length - 1) { clearInterval(lt.timer); lt.timer = null; ltPlay.textContent = "▶"; return; }
    lt.idx += 1;
  };
  passo();
  lt.timer = setInterval(passo, 900);
});

async function alternarLocais(e) {
  garantirMapa();
  gravarEnderecoMapa();
  if (!e.target.checked) { if (estado.camadaLocais) estado.mapa.removeLayer(estado.camadaLocais); return; }
  if (!estado.camadaLocais) {
    const geo = await api(`geo/locais.geojson?ano=${estado.ano}`);
    const renderer = L.canvas({ padding: 0.5 });
    estado.camadaLocais = L.geoJSON(geo, {
      pointToLayer: (ft, ll) => L.circleMarker(ll, {
        renderer, radius: Math.max(2, Math.sqrt(ft.properties.eleitores || 0) / 12),
        color: cor("--texto"), weight: 0.5, fillColor: cor("--serie-2"), fillOpacity: 0.7,
      }),
      onEachFeature: (ft, layer) => layer.bindPopup(() => {
        const p = ft.properties;
        return el("div", {}, el("strong", {}, p.nome), el("br"), `${p.bairro || ""} — ${p.municipio}`, el("br"),
          `Zona ${p.zona}, local ${p.local} · ${int(p.eleitores)} eleitores em ${p.secoes} seções (${estado.ano})`);
      }),
    });
  }
  estado.camadaLocais.addTo(estado.mapa);
}

// ---------------------------------------------------------------- ciclo de atualização
async function tick() {
  await atualizarStatus();
  if (estado.aba === "painel") { await atualizarPainel(); atualizarMudancas(); }
  if (estado.aba === "mapas" && !estado.lt.timer && estado.detalhe === "municipios") {
    const noFim = estado.lt.idx >= estado.lt.momentos.length - 1;
    await carregarMomentos();
    if (noFim) await atualizarMapa();  // quem está vendo um momento passado não é atropelado
  }
}
// ---------------------------------------------------------------- comparação entre eleições
const NOMES_CARGO = { 1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual",
  11: "Prefeito" };
const compMetrica = document.getElementById("comp-metrica");
const compCargo = document.getElementById("comp-cargo");

async function iniciarComparacao() {
  let info;
  try { info = await api("api/comparacao/info"); } catch (_) { return; }
  if (!info.disponivel) return;
  estado.comp = info;
  document.getElementById("botao-comparacao").hidden = false;
  document.getElementById("botao-comparacao").textContent = `Comparação ${info.ano_a} × ${info.ano_b}`;
  document.getElementById("comp-rot-a").textContent = `Nº em ${info.ano_a}`;
  document.getElementById("comp-rot-b").textContent = `Nº em ${info.ano_b}`;
  compCargo.replaceChildren(...info.cargos.filter((c) => NOMES_CARGO[c]).map((c) =>
    el("option", { value: c, selected: c === 3 }, NOMES_CARGO[c])));
}

compMetrica.addEventListener("change", ajustarCamposComp);
compCargo.addEventListener("change", ajustarCamposComp);
document.getElementById("form-comp").addEventListener("submit", (e) => { e.preventDefault(); atualizarComparacao(); });

async function ajustarCamposComp() {
  const m = compMetrica.value;
  document.getElementById("comp-l-partido").hidden = m !== "partido";
  document.getElementById("comp-l-na").hidden = document.getElementById("comp-l-nb").hidden = m !== "candidato";
  const bairros = estado.compDetalhe === "bairros";
  const [a, b] = bairros ? [compAnoA.value, compAnoB.value] : [estado.comp.ano_a, estado.comp.ano_b];
  document.getElementById("comp-rot-a").textContent = `Nº em ${a}`;
  document.getElementById("comp-rot-b").textContent = `Nº em ${b}`;
  if (m !== "partido") return;
  const sel = document.getElementById("comp-partido");
  if (!bairros) {
    const ps = await api(`api/comparacao/partidos?cargo=${compCargo.value}`);
    sel.replaceChildren(...ps.map((p) => el("option", { value: p.PARTIDO }, rotuloEntidade(p, a, b))));
    return;
  }
  // bairros: partido pelo NÚMERO do ano mais recente, ligado pela entidade (o 14 de 2026 não é o de 2022)
  const ps = await api(`api/comparacao/bairros/partidos?ano_a=${a}&cargo_a=${compCargoA.value}` +
    `&ano_b=${b}&cargo_b=${compCargoB.value}&turno=${estado.turno || 1}`);
  sel.replaceChildren(...ps.map((p) => {
    const sigla = p.SIGLA_A && p.SIGLA_B && p.SIGLA_A !== p.SIGLA_B ? `${p.SIGLA_B} (${p.SIGLA_A} em ${a})` : (p.SIGLA_A || p.SIGLA_B || "");
    return el("option", { value: p.PARTIDO },
      `${p.PARTIDO} ${sigla}${p.NOS_DOIS ? "" : p.VOTOS_A ? ` (só ${a})` : ` (só ${b})`}`);
  }));
}

// ---------------------------------------------------------------- comparação por bairro
const compDetalhe = document.getElementById("comp-detalhe");
const compAnoA = document.getElementById("comp-ano-a"), compAnoB = document.getElementById("comp-ano-b");
const compCargoA = document.getElementById("comp-cargo-a"), compCargoB = document.getElementById("comp-cargo-b");
const METRICAS_COMP_BAIRRO = ["abstencao", "comparecimento", "brancos_nulos", "brancos", "nulos", "eleitorado", "partido",
  "candidato"];
estado.compDetalhe = "municipios";

function cargosDoAno(sel, ano, preferido = null) {
  const info = estado.compBairrosInfo;
  const cs = info.anos_votos[ano] || [1, 3, 5, 6, 7];  // ano sem votos (ex.: 2026): só "eleitorado" terá dado
  const alvo = String(preferido ?? sel.value);
  sel.replaceChildren(...cs.map((c) => el("option", { value: c }, info.cargos[c])));
  sel.value = cs.map(String).includes(alvo) ? alvo : String(cs[0]);
}

async function prepararCompDetalhe(pref = {}) {
  const bairros = compDetalhe.value === "bairros";
  estado.compDetalhe = compDetalhe.value;
  document.getElementById("comp-l-cargo").hidden = bairros;
  document.querySelectorAll(".comp-bairro").forEach((e) => { e.hidden = !bairros; });
  document.getElementById("comp-bairros-nota").hidden = !bairros;
  for (const op of compMetrica.options) op.disabled = bairros && !METRICAS_COMP_BAIRRO.includes(op.value);
  if (compMetrica.selectedOptions[0]?.disabled) compMetrica.value = "brancos_nulos";
  if (bairros) {
    if (!estado.compBairrosInfo) estado.compBairrosInfo = await api("api/comparacao/bairros/info");
    const info = estado.compBairrosInfo;
    const anos = [...new Set([...Object.keys(info.anos_votos).map(Number), ...info.anos_cadastro, estado.comp.ano_b])]
      .sort((x, y) => x - y);
    const preencher = (sel, padrao, preferido) => {
      const alvo = String(preferido ?? sel.value ?? "");
      sel.replaceChildren(...anos.map((a) => el("option", { value: a }, String(a))));
      sel.value = anos.map(String).includes(alvo) ? alvo : String(padrao);
    };
    preencher(compAnoA, anos.includes(estado.comp.ano_a) ? estado.comp.ano_a : anos[0], pref.ano_a);
    preencher(compAnoB, anos.includes(estado.comp.ano_b) ? estado.comp.ano_b : anos.at(-1), pref.ano_b);
    cargosDoAno(compCargoA, compAnoA.value, pref.cargo_a ?? compCargo.value);
    cargosDoAno(compCargoB, compAnoB.value, pref.cargo_b ?? compCargo.value);
  }
  await ajustarCamposComp();
}

compDetalhe.addEventListener("change", async () => { await prepararCompDetalhe(); atualizarComparacao(); });
compAnoA.addEventListener("change", () => { cargosDoAno(compCargoA, compAnoA.value); ajustarCamposComp(); });
compAnoB.addEventListener("change", () => { cargosDoAno(compCargoB, compAnoB.value); ajustarCamposComp(); });
compCargoA.addEventListener("change", ajustarCamposComp);
compCargoB.addEventListener("change", ajustarCamposComp);

// rótulo de um partido ligado entre dois anos pela entidade (rodada 41): "PRD (PTB + PATRIOTA em 2022)",
// "PCDOB (PC do B em 2022)", "MISSÃO (só 2026: sem antecessor)"
function rotuloEntidade(p, a, b) {
  const siglaA = p.SIGLAS_A ?? p.SIGLA_A, siglaB = p.SIGLAS_B ?? p.SIGLA_B;
  if (!p.NOS_DOIS) return `${p.PARTIDO}${p.VOTOS_A ? ` (só ${a})` : ` (só ${b})`}`;
  return siglaA && siglaA !== p.PARTIDO ? `${p.PARTIDO} (${siglaA} em ${a})` : String(p.PARTIDO);
}

function fmtComp(v, unidade) {
  if (v === null || v === undefined) return "—";
  const s = fmtPct.format(Math.abs(v));
  const sinal = v > 0 ? "+" : v < 0 ? "−" : "";
  return unidade === "var_pct" ? `${sinal}${s}%` : `${sinal}${s} p.p.`;
}

async function atualizarComparacao() {
  if (!estado.comp) return;
  if (!estado.compMapa) estado.compMapa = novoMapa(document.getElementById("comp-mapa"));
  const m = compMetrica.value;
  const bairros = estado.compDetalhe === "bairros";
  const q = new URLSearchParams(bairros
    ? { ano_a: compAnoA.value, cargo_a: compCargoA.value, ano_b: compAnoB.value, cargo_b: compCargoB.value,
        metrica: m, turno: estado.turno || 1 }
    : { cargo: compCargo.value, metrica: m });
  if (m === "partido") q.set("partido", document.getElementById("comp-partido").value);
  if (m === "candidato") {
    q.set("numero_a", document.getElementById("comp-num-a").value);
    q.set("numero_b", document.getElementById("comp-num-b").value);
  }
  const legenda = document.getElementById("comp-legenda");
  let d;
  try { d = await api(`api/comparacao${bairros ? "/bairros" : ""}?${q}`); } catch (e) {
    const mp = estado.compMapa;  // nada desenhado de consulta anterior pode ficar na tela (nem ir para o arquivo)
    if (mp._camada) { mp.removeLayer(mp._camada); mp._camada = null; }
    if (mp._contornos) { mp.removeLayer(mp._contornos); mp._contornos = null; }
    mp._export = null;
    document.getElementById("comp-fichas").replaceChildren();
    document.getElementById("comp-tabela").replaceChildren();
    legenda.replaceChildren(el("p", {}, `Erro: ${e.message}`));
    gravarEnderecoComp();
    return;
  }
  if (bairros) {
    document.getElementById("comp-bairros-nota").textContent = `${d.subtitulo ? d.subtitulo + " · " : ""}` +
      "área = bairros do IBGE que têm local de votação; cada local conta no bairro que contém sua coordenada.";
  }
  const valorAno = (v) => (v === null || v === undefined ? "—" : d.unidade === "var_pct" ? int(v) : pct(v));
  const u = d.uf || {};
  const area = bairros ? "área dos bairros" : estado.uf;
  document.getElementById("comp-titulo-tabela").textContent =
    `Por ${bairros ? "bairro" : "município"} (clique no cabeçalho para ordenar)`;
  document.getElementById("comp-fichas").replaceChildren(
    ficha(`${d.rotulo} — ${area} ${d.ano_a}`, valorAno(u.VALOR_A)),
    ficha(`${area} ${d.ano_b}`, valorAno(u.VALOR_B)),
    ficha(bairros ? "Diferença na área dos bairros" : "Diferença no estado", fmtComp(u.DIF, d.unidade)));
  await desenharDivergente(estado.compMapa, d, legenda, d.camada || "municipios");
  const cab = [[bairros ? "Bairro — município" : "Município", "NM_MUNICIPIO"], [String(d.ano_a), "VALOR_A", true], [String(d.ano_b), "VALOR_B", true],
    ["Diferença", "DIF", true]];
  document.getElementById("comp-tabela").replaceChildren(tabelaOrdenavel(cab, d.municipios, (r, k) =>
    k === "DIF" ? fmtComp(r[k], d.unidade) : k === "NM_MUNICIPIO" ? r[k] : valorAno(r[k]), null,
  { ordem: estado.compOrdem, aoOrdenar: (o) => { estado.compOrdem = o; gravarEnderecoComp(); } }));
  gravarEnderecoComp();
}

// ---------------------------------------------------------------- endereço da aba Comparação
// #comparacao?cargo=7&metrica=partido&partido=PL&ordem=DIF-desc
// #comparacao?cargo=3&metrica=candidato&numero_a=22&numero_b=22
function enderecoComp() {
  const m = compMetrica.value;
  const q = new URLSearchParams({ cargo: compCargo.value, metrica: m });
  if (m === "partido" && document.getElementById("comp-partido").value) q.set("partido", document.getElementById("comp-partido").value);
  if (m === "candidato") {
    for (const [k, id] of [["numero_a", "comp-num-a"], ["numero_b", "comp-num-b"]]) {
      const v = document.getElementById(id).value.trim();
      if (v) q.set(k, v);
    }
  }
  if (estado.compDetalhe === "bairros") {
    q.set("detalhe", "bairros");
    for (const [k, sel] of [["ano_a", compAnoA], ["cargo_a", compCargoA], ["ano_b", compAnoB], ["cargo_b", compCargoB]]) {
      q.set(k, sel.value);
    }
  }
  if (estado.compOrdem) q.set("ordem", estado.compOrdem);
  if (bancCaixa.open) {
    q.set("banc", "1");
    q.set("banc_cargo", document.getElementById("banc-cargo").value);
  }
  if (varCaixa.open && estado.compDetalhe !== "bairros") {
    q.set("var", "1");
    const ps = partidosVar();
    if (ps.length) q.set("var_partidos", ps.join(","));
    if (document.getElementById("var-ponderar").checked) q.set("var_ponderar", "1");
  }
  return `#comparacao?${q}`;
}

function gravarEnderecoComp() {
  if (estado.aba !== "comparacao") return;
  const alvo = enderecoComp();
  if (location.hash !== alvo) history.replaceState(null, "", alvo);
}

async function aplicarEnderecoComp(params) {
  if (!estado.comp) return;  // sem eleição de referência: a aba nem existe
  const q = new URLSearchParams(params);
  const temOpcao = (sel, v) => v !== null && [...sel.options].some((o) => o.value === v);
  if (temOpcao(compCargo, q.get("cargo"))) compCargo.value = q.get("cargo");
  compDetalhe.value = q.get("detalhe") === "bairros" ? "bairros" : "municipios";
  await prepararCompDetalhe({ ano_a: q.get("ano_a"), cargo_a: q.get("cargo_a"), ano_b: q.get("ano_b"),
                              cargo_b: q.get("cargo_b") });
  const metrica = q.get("metrica");
  if (metrica && [...compMetrica.options].some((o) => o.value === metrica && !o.disabled)) compMetrica.value = metrica;
  await ajustarCamposComp();  // carrega a lista de partidos do cargo antes de escolher o partido
  const partido = document.getElementById("comp-partido");
  if (temOpcao(partido, q.get("partido"))) partido.value = q.get("partido");
  document.getElementById("comp-num-a").value = q.get("numero_a") || "";
  document.getElementById("comp-num-b").value = q.get("numero_b") || "";
  estado.compOrdem = q.get("ordem");
  estado.compFeito = true;  // mostrarAba não deve disparar a consulta padrão
  mostrarAba("comparacao");
  await atualizarComparacao();
  if (["6", "7", "8"].includes(q.get("banc_cargo"))) document.getElementById("banc-cargo").value = q.get("banc_cargo");
  const abrirBanc = q.get("banc") === "1";
  if (bancCaixa.open !== abrirBanc) bancCaixa.open = abrirBanc;  // o "toggle" desenha
  else if (abrirBanc) desenharBancadas();
  document.getElementById("var-ponderar").checked = q.get("var_ponderar") === "1";
  const abrir = q.get("var") === "1" && estado.compDetalhe !== "bairros";
  estado.varEscolha = abrir && q.get("var_partidos") ? q.get("var_partidos").split(",").slice(0, MAX_VAR) : null;
  if (varCaixa.open !== abrir) varCaixa.open = abrir;  // o "toggle" prepara e desenha
  else if (abrir) await prepararVar().then(desenharVar);
}

document.getElementById("comp-copiar").addEventListener("click",
  () => copiarLink(enderecoComp(), document.getElementById("comp-copiar-msg")));

// ---------------------------------------------------------------- bancadas × eleição anterior (aba Comparação)
// Endereço: &banc=1&banc_cargo=7 (TODO 15, rodada 45)
const bancCaixa = document.getElementById("comp-bancadas");

async function desenharBancadas() {
  const out = document.getElementById("banc-resultado");
  if (!bancCaixa.open) return;
  const cargo = document.getElementById("banc-cargo").value;
  const pedido = (estado.bancPedido = cargo);
  out.replaceChildren(el("p", { class: "nota" }, "Carregando…"));
  let d;
  try { d = await api(`api/bancadas?cargo=${cargo}`); } catch (e) {
    if (estado.bancPedido === pedido) out.replaceChildren(el("p", { class: "aviso" }, e.message));
    return;
  }
  if (estado.bancPedido !== pedido) return;
  const r = d.resumo, a = d.ano, b = d.ano_ref;
  const fichas = el("div", { class: "fichas" },
    ficha(`Eleitos ${b} → ${a}`, `${int(r.eleitos_antes)} → ${int(r.eleitos_agora)}`),
    ficha("Reeleitos", int(r.reeleito)), ficha("Novatos", int(r.novato)),
    ficha("Já tinham concorrido", int(r["já concorreu, sem se eleger"])),
    ficha("Eleitos antes para outro cargo", int(r["eleito antes para outro cargo"])),
    ficha(`Eleitos em ${b} que saíram`, int(r.nao_reeleitos)));
  const sinal = (x) => (x > 0 ? `+${x}` : String(x));
  const tPart = tabelaOrdenavel([["Partido", "PARTIDO"], [`Em ${b} como`, "ANTES_COMO"], [`Eleitos ${b}`, "ELEITOS_ANTES", true],
    [`Eleitos ${a}`, "ELEITOS_AGORA", true], ["Variação", "VARIACAO", true]], d.partidos,
  (x, k) => (k === "VARIACAO" ? sinal(x[k]) : x[k] ?? "—"));
  const tEl = tabelaOrdenavel([["Eleito", "NOME_URNA"], ["Partido", "PARTIDO"], ["Votos", "VOTOS", true],
    ["Trajetória", "TRAJETORIA"], ["Detalhe", "DETALHE"]], d.eleitos, (x, k) => (k === "VOTOS" ? int(x[k]) : x[k] ?? "—"));
  const tSa = tabelaOrdenavel([[`Eleito em ${b}`, "NOME_URNA"], ["Partido", "PARTIDO_ANTES"], [`Votos ${b}`, "VOTOS_ANTES", true],
    [`Em ${a}`, "DESTINO"]], d.sairam, (x, k) => (k === "VOTOS_ANTES" ? int(x[k]) : x[k] ?? "—"));
  out.replaceChildren(fichas,
    el("a", { class: "botao-salvar", href: `api/bancadas/planilha?cargo=${cargo}`, download: "" }, "Salvar planilha (.xlsx)"),
    el("h3", { class: "sub" }, `Por partido — ${d.ds_cargo}`), el("div", { class: "tabela-rolagem" }, tPart),
    el("h3", { class: "sub" }, `Eleitos em ${a}`), el("div", { class: "tabela-rolagem" }, tEl),
    el("h3", { class: "sub" }, `Eleitos em ${b} que não voltaram ao cargo`), el("div", { class: "tabela-rolagem" }, tSa));
}

bancCaixa.addEventListener("toggle", () => { gravarEnderecoComp(); desenharBancadas(); });
document.getElementById("banc-cargo").addEventListener("change", () => { gravarEnderecoComp(); desenharBancadas(); });

// ---------------------------------------------------------------- variação por partido (aba Comparação)
// Dispersão A × B por município (diagonal = sem mudança), distribuição da variação e estatística
// (apuracao/comparacao.py: variacao_partidos). Endereço: &var=1&var_partidos=PT,PL[&var_ponderar=1]
const MAX_VAR = 3;
const CORES_VAR = ["--serie-1", "--serie-2", "--serie-3"];  // ordem fixa da escolha (dataviz)
const PADRAO_VAR = { 1: ["PT", "PL"] };
const varCaixa = document.getElementById("comp-variacao");
const fmtNum = (v, casas = 2) => (v === null || v === undefined ? "—" : v.toFixed(casas).replace(".", ","));

// na ordem em que foram escolhidos (o 1º e o 2º definem o sentido do swing de Butler), não na da lista
function partidosVar() {
  const marcados = new Set([...document.querySelectorAll("#var-partidos input:checked")].map((i) => i.value));
  estado.varOrdem = (estado.varOrdem || []).filter((p) => marcados.has(p));
  for (const p of marcados) if (!estado.varOrdem.includes(p)) estado.varOrdem.push(p);
  return [...estado.varOrdem];
}

function limitarVar() {
  const n = partidosVar().length;
  document.querySelectorAll("#var-partidos input").forEach((i) => { i.disabled = !i.checked && n >= MAX_VAR; });
}

async function prepararVar(escolhidos = null) {
  const caixa = document.getElementById("var-partidos");
  const cargo = compCargo.value;
  let ps;
  try { ps = await api(`api/comparacao/partidos?cargo=${cargo}`); } catch (e) {
    caixa.replaceChildren(el("span", { class: "nota" }, e.message)); return;
  }
  escolhidos = escolhidos ?? estado.varEscolha;
  estado.varEscolha = null;
  const marcados = new Set(escolhidos ?? (estado.varCargo === cargo ? partidosVar() : null)
    ?? PADRAO_VAR[cargo]?.filter((p) => ps.some((x) => x.PARTIDO === p && x.NOS_DOIS))
    ?? ps.filter((x) => x.NOS_DOIS).slice(0, 2).map((x) => x.PARTIDO));
  estado.varCargo = cargo;
  estado.varOrdem = [...marcados];
  caixa.replaceChildren(...ps.map((x) => el("label", {}, el("input", { type: "checkbox", value: x.PARTIDO,
    checked: marcados.has(x.PARTIDO), onchange: () => { limitarVar(); gravarEnderecoComp(); } }),
  rotuloEntidade(x, estado.comp.ano_a, estado.comp.ano_b))));
  limitarVar();
}

async function desenharVar() {
  const out = document.getElementById("var-resultado");
  if (!varCaixa.open || estado.compDetalhe === "bairros") return;
  const ps = partidosVar();
  if (!ps.length) { out.replaceChildren(el("p", { class: "nota" }, "Escolha de 1 a 3 partidos.")); return; }
  const q = new URLSearchParams({ cargo: compCargo.value, partidos: ps.join(",") });
  if (document.getElementById("var-ponderar").checked) q.set("ponderar", "true");
  if (estado.varEmCurso === q.toString()) return;  // o mesmo pedido já está a caminho
  const pedido = (estado.varPedido = estado.varEmCurso = q.toString());
  if (estado.varMostrado !== pedido) out.replaceChildren(el("p", { class: "nota" }, "Calculando…"));
  let d;
  try { d = await api(`api/comparacao/variacao?${q}`); } catch (e) {
    if (estado.varPedido === pedido) {
      estado.varEmCurso = estado.varMostrado = null;
      out.replaceChildren(el("p", { class: "aviso" }, e.message));
    }
    return;
  }
  if (estado.varPedido !== pedido) return;
  estado.varEmCurso = null;
  estado.varMostrado = pedido;
  const series = d.partidos.map((p, i) => ({ ...p, cor: cor(CORES_VAR[i]) }));
  const fichas = el("div", { class: "fichas" }, ...series.flatMap((p) => [
    ficha(`${p.partido} no estado`, p.uf ? `${pct(p.uf.A)} → ${pct(p.uf.B)} (${fmtComp(p.uf.DIF, "pp")})` : "—"),
    ficha(`${p.partido}: variação média por município${d.ponderado ? " (ponderada)" : ""}`,
      `${fmtComp(p.media, "pp")} · IC 95% ${fmtComp(p.ic_media[0], "pp")} a ${fmtComp(p.ic_media[1], "pp")} · DP ${fmtNum(p.dp)}`),
    ficha(`${p.partido}: inclinação b (${d.ano_b} = a + b·${d.ano_a})`, p.reta.b === null ? "—"
      : `${fmtNum(p.reta.b, 3)}${p.reta.ic_b ? ` · IC 95% ${fmtNum(p.reta.ic_b[0], 3)} a ${fmtNum(p.reta.ic_b[1], 3)}` : ""}` +
        ` · p(b = 1) ${fmtP(p.reta.p_b1)} · r ${fmtNum(p.reta.pearson, 3)}`),
  ]), d.butler ? ficha(`Swing de Butler ${d.butler.de} → ${d.butler.para}`,
    `estado ${fmtComp(d.butler.uf, "pp")} · média por município ${fmtComp(d.butler.media, "pp")} ` +
    `(IC 95% ${fmtComp(d.butler.ic_media[0], "pp")} a ${fmtComp(d.butler.ic_media[1], "pp")})`) : null);
  const leituras = series.map((p) => el("p", { class: "nota var-leitura" }, el("strong", {}, `${p.partido}: `), p.leitura));
  const cab = [["Município", "NM_MUNICIPIO"], ...series.flatMap((p) => [[`${p.partido} ${d.ano_a}`, `${p.partido}_A`, true],
    [`${p.partido} ${d.ano_b}`, `${p.partido}_B`, true], [`${p.partido} variação`, `${p.partido}_DIF`, true]])];
  if (d.butler) cab.push([`Butler ${d.butler.de} → ${d.butler.para}`, "BUTLER", true]);
  const linhas = {};
  series.forEach((p) => p.pontos.forEach((r) => {
    const l = (linhas[r.CD_MUNICIPIO] ||= { NM_MUNICIPIO: r.NM_MUNICIPIO });
    Object.assign(l, { [`${p.partido}_A`]: r.A, [`${p.partido}_B`]: r.B, [`${p.partido}_DIF`]: r.DIF });
  }));
  if (d.butler) d.butler.pontos.forEach((r) => { if (linhas[r.CD_MUNICIPIO]) linhas[r.CD_MUNICIPIO].BUTLER = r.VALOR; });
  const tabela = tabelaOrdenavel(cab, Object.values(linhas), (r, k) =>
    k === "NM_MUNICIPIO" ? r[k] : k.endsWith("_DIF") || k === "BUTLER" ? fmtComp(r[k], "pp") : pct(r[k]));
  out.replaceChildren(fichas, ...leituras,
    el("h3", { class: "sub" }, `% dos válidos em ${d.ano_a} × ${d.ano_b} por município`), graficoVariacao(d, series),
    el("h3", { class: "sub" }, `Variação por município (p.p.) — média e intervalo de 95%`), graficoSwing(d, series),
    el("h3", { class: "sub" }, "Tabela"), el("div", { class: "tabela-rolagem" }, tabela));
}

function botoesBaixar(g, itensLeg) {
  return el("div", { class: "nota baixar-serie" }, "Baixar gráfico: ",
    el("button", { type: "button", class: "link", onclick: () => baixarGrafico(g, itensLeg, "svg") }, "SVG"), " ",
    el("button", { type: "button", class: "link", onclick: () => baixarGrafico(g, itensLeg, "png") }, "PNG"));
}

function legendaLinha(itensLeg) {
  return el("div", { class: "legenda-linha" }, itensLeg.map(([c, t]) => el("span", {},
    el("span", { class: "amostra", style: { background: c } }), t)));
}

// dica do ponto mais próximo do mouse (alvo maior que o ponto); `alvos`: [{x, y, el, texto: () => [nós]}]
function comDica(g, W, H, alvos) {
  const dica = el("div", { class: "dica", hidden: true });
  let ativo = null;
  g.addEventListener("mousemove", (ev) => {
    const r = g.getBoundingClientRect();
    const mx = (ev.clientX - r.left) * (W / r.width), my = (ev.clientY - r.top) * (H / r.height);
    let k = -1, melhor = 14 ** 2;
    alvos.forEach((a, i) => { const dd = (a.x - mx) ** 2 + (a.y - my) ** 2; if (dd < melhor) { melhor = dd; k = i; } });
    if (ativo) ativo.classList.remove("ativo");
    if (k < 0) { dica.hidden = true; ativo = null; return; }
    ativo = alvos[k].el; ativo.classList.add("ativo");
    dica.replaceChildren(...alvos[k].texto());
    dica.hidden = false;
    dica.style.left = `${Math.min(ev.clientX - r.left + 12, r.width - 230)}px`;
    dica.style.top = `${Math.max(4, ev.clientY - r.top - 80)}px`;
  });
  g.addEventListener("mouseleave", () => { dica.hidden = true; if (ativo) ativo.classList.remove("ativo"); ativo = null; });
  return el("div", { class: "serie-caixa" }, g, dica);
}

function graficoVariacao(d, series) {
  const W = 640, H = 480, m = { l: 52, r: 40, t: 12, b: 46 };
  const todos = series.flatMap((p) => p.pontos.flatMap((r) => [r.A, r.B]));
  const passo = 5;
  const lo = Math.max(0, Math.floor(Math.min(...todos) / passo) * passo);
  const hi = Math.min(100, Math.ceil(Math.max(...todos) / passo) * passo);
  const X = (v) => m.l + ((W - m.l - m.r) * (v - lo)) / (hi - lo);
  const Y = (v) => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "dispersao", role: "img",
    "aria-label": `% dos válidos em ${d.ano_a} × ${d.ano_b} por município: ${series.map((p) => p.partido).join(", ")}` });
  for (const t of passos(lo, hi, 8)) {
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grade" }),
      svg("text", { x: m.l - 6, y: Y(t) + 3, class: "eixo", "text-anchor": "end" }, `${fmtInt.format(t)}%`),
      svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: "grade" }),
      svg("text", { x: X(t), y: H - m.b + 14, class: "eixo", "text-anchor": "middle" }, `${fmtInt.format(t)}%`));
  }
  g.append(svg("line", { x1: X(lo), y1: Y(lo), x2: X(hi), y2: Y(hi), class: "diagonal" }),
    svg("text", { x: (m.l + W - m.r) / 2, y: H - 8, class: "titulo-eixo", "text-anchor": "middle" }, `% dos válidos em ${d.ano_a}`),
    svg("text", { x: 12, y: (m.t + H - m.b) / 2, class: "titulo-eixo", "text-anchor": "middle",
      transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, `% dos válidos em ${d.ano_b}`));
  const vmax = Math.max(...series.flatMap((p) => p.pontos.map((r) => r.VALIDOS)));
  const raio = (v) => 4 + 14 * Math.sqrt(v / vmax);  // área ∝ válidos; mínimo de 8 px de diâmetro
  const pontos = series.flatMap((p) => p.pontos.map((r) => ({ p, r })))
    .sort((a, b) => b.r.VALIDOS - a.r.VALIDOS);  // grandes atrás, pequenos na frente
  const alvos = pontos.map(({ p, r }) => {
    const c = svg("circle", { cx: X(r.A), cy: Y(r.B), r: raio(r.VALIDOS), class: "ponto", fill: p.cor });
    g.append(c);
    return { x: X(r.A), y: Y(r.B), el: c, texto: () => [el("strong", {}, r.NM_MUNICIPIO),
      el("div", {}, el("span", { class: "amostra", style: { background: p.cor } }), p.partido),
      el("div", {}, `${d.ano_a}: ${pct(r.A)} · ${d.ano_b}: ${pct(r.B)}`),
      el("div", {}, `Variação: ${fmtComp(r.DIF, "pp")} · ${int(r.VALIDOS)} válidos em ${d.ano_b}`)] };
  });
  series.forEach((p) => {  // reta de cada partido no intervalo dos seus pontos + rótulo direto na ponta
    const e = p.reta;
    if (e.b === null) return;
    const xs = p.pontos.map((r) => r.A);
    const x1 = Math.min(...xs), x2 = Math.max(...xs);
    g.append(svg("line", { x1: X(x1), y1: Y(e.a + e.b * x1), x2: X(x2), y2: Y(e.a + e.b * x2), class: "reta", stroke: p.cor }),
      svg("text", { x: Math.min(X(x2) + 4, W - m.r + 2), y: Y(e.a + e.b * x2) + 4, class: "rotulo" }, p.partido));
  });
  const itensLeg = [...series.map((p) => [p.cor, `${p.partido} (reta: tendência${d.ponderado ? " ponderada" : ""})`]),
    [cor("--texto-2"), "Diagonal: sem mudança (acima = ganhou, abaixo = perdeu)"]];
  return el("div", {}, comDica(g, W, H, alvos), legendaLinha(itensLeg),
    el("p", { class: "nota" }, `Área do ponto ∝ votos válidos em ${d.ano_b}.`), botoesBaixar(g, itensLeg));
}

function graficoSwing(d, series) {
  const linhas = series.map((p) => ({ nome: p.partido, cor: p.cor, media: p.media, ic: p.ic_media,
    pontos: p.pontos.map((r) => ({ v: r.DIF, nome: r.NM_MUNICIPIO, destaque: r.DESTAQUE, A: r.A, B: r.B })) }));
  if (d.butler) {
    linhas.push({ nome: `Butler ${d.butler.de}→${d.butler.para}`, cor: cor("--texto-2"), media: d.butler.media,
      ic: d.butler.ic_media, pontos: d.butler.pontos.map((r) => ({ v: r.VALOR, nome: r.NM_MUNICIPIO })) });
  }
  const faixa = 70, W = 640, m = { l: 110, r: 16, t: 8, b: 40 };
  const H = m.t + m.b + faixa * linhas.length;
  const vs = linhas.flatMap((l) => l.pontos.map((p) => p.v));
  const lim = Math.max(1, ...vs.map(Math.abs)) * 1.05;
  const X = (v) => m.l + ((W - m.l - m.r) * (v + lim)) / (2 * lim);
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "dispersao", role: "img",
    "aria-label": `Variação por município em pontos percentuais: ${linhas.map((l) => l.nome).join(", ")}` });
  for (const t of passos(-lim, lim, 8)) {
    g.append(svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: t === 0 ? "zero" : "grade" }),
      svg("text", { x: X(t), y: H - m.b + 14, class: "eixo", "text-anchor": "middle" },
        `${t > 0 ? "+" : t < 0 ? "−" : ""}${fmtInt.format(Math.abs(t))}`));
  }
  g.append(svg("text", { x: (m.l + W - m.r) / 2, y: H - 8, class: "titulo-eixo", "text-anchor": "middle" },
    `Variação de ${d.ano_a} para ${d.ano_b} (p.p.)`));
  const alvos = [];
  linhas.forEach((l, i) => {
    const y0 = m.t + faixa * i + faixa / 2;
    g.append(svg("text", { x: m.l - 8, y: y0 + 4, class: "rotulo", "text-anchor": "end" }, l.nome));
    // espalhamento vertical determinístico (pela ordem), para os pontos não se sobreporem todos
    l.pontos.forEach((p, k) => {
      const y = y0 + (((k * 7919) % 23) - 11) * 1.3;
      const c = svg("circle", { cx: X(p.v), cy: y, r: 4, class: "ponto", fill: l.cor });
      g.append(c);
      alvos.push({ x: X(p.v), y, el: c, texto: () => [el("strong", {}, p.nome), el("div", {}, l.nome),
        el("div", {}, `Variação: ${fmtComp(p.v, "pp")}`),
        p.A !== undefined ? el("div", {}, `${d.ano_a}: ${pct(p.A)} → ${d.ano_b}: ${pct(p.B)}`) : null].filter(Boolean) });
    });
    g.append(svg("line", { x1: X(l.ic[0]), x2: X(l.ic[1]), y1: y0, y2: y0, class: "ic", stroke: l.cor }),
      svg("line", { x1: X(l.media), x2: X(l.media), y1: y0 - 20, y2: y0 + 20, class: "media" }));
    // rótulos dos destaques acima ou abaixo da faixa, onde couberem sem encostar no anterior (senão, só na dica)
    const fim = [-Infinity, -Infinity];
    l.pontos.filter((p) => p.destaque).sort((a, b) => a.v - b.v).forEach((p) => {
      const meia = (p.nome.length * 5.6) / 2 + 4;
      const x = Math.min(Math.max(X(p.v), m.l + meia), W - m.r - meia);
      const lado = [0, 1].find((k) => x - meia > fim[k]);
      if (lado === undefined) return;
      fim[lado] = x + meia;
      g.append(svg("text", { x, y: lado ? y0 + 30 : y0 - 23, class: "rotulo-mun", "text-anchor": "middle" }, p.nome));
    });
  });
  const itensLeg = [...linhas.map((l) => [l.cor, `${l.nome}: um ponto por município`]),
    [cor("--texto"), `Traço: média${d.ponderado ? " ponderada" : ""}; faixa: intervalo de 95% (bootstrap)`]];
  return el("div", {}, comDica(g, W, H, alvos), legendaLinha(itensLeg), botoesBaixar(g, itensLeg));
}

function ajustarVar() {
  const bairros = estado.compDetalhe === "bairros";
  varCaixa.hidden = bairros;
  if (varCaixa.open && !bairros) prepararVar().then(() => { gravarEnderecoComp(); desenharVar(); });
}

varCaixa.addEventListener("toggle", async () => {
  if (varCaixa.open) await prepararVar();
  gravarEnderecoComp();
  if (varCaixa.open) desenharVar();
});
document.getElementById("form-var").addEventListener("submit", (e) => { e.preventDefault(); gravarEnderecoComp(); desenharVar(); });
document.getElementById("var-ponderar").addEventListener("change", () => { gravarEnderecoComp(); desenharVar(); });
compCargo.addEventListener("change", ajustarVar);
compDetalhe.addEventListener("change", ajustarVar);


async function desenharDivergente(mapa, d, legendaEl, camada = "municipios") {
  const geo = camada === "bairros" ? await malhaBairros() : await malha();
  const idDe = (ft) => (camada === "bairros" ? ft.properties.CD_BAIRRO : ft.properties.codarea);
  if (mapa._camada) mapa.removeLayer(mapa._camada);
  if (mapa._contornos) { mapa.removeLayer(mapa._contornos); mapa._contornos = null; }
  const difs = Object.values(d.itens).map((i) => i.valor).filter((x) => x !== null && x !== undefined);
  const m = Math.max(...difs.map(Math.abs), 1e-9);
  const lim = [m * 0.1, m / 3, (2 * m) / 3];  // |dif| < 10% do máximo = "sem variação relevante"
  const nomes = ["--div-n3", "--div-n2", "--div-n1", "--div-0", "--div-p1", "--div-p2", "--div-p3"];
  const cores = nomes.map(cor);
  const classe = (v) => {
    const a = Math.abs(v);
    const k = a < lim[0] ? 0 : a < lim[1] ? 1 : a < lim[2] ? 2 : 3;
    return v < 0 ? 3 - k : 3 + k;
  };
  const semDado = cor("--sem-dado");
  const coresExport = {};
  mapa._camada = L.geoJSON(geo, {
    style: (ft) => {
      const it = d.itens[idDe(ft)];
      const fill = !it || it.valor === null || it.valor === undefined ? semDado : cores[classe(it.valor)];
      coresExport[idDe(ft)] = fill;
      return { fillColor: fill, fillOpacity: 0.9, color: cor("--superficie"), weight: camada === "bairros" ? 0.5 : 1 };
    },
    onEachFeature: (ft, layer) => {
      const it = d.itens[idDe(ft)];
      const nome = it ? it.municipio
        : camada === "bairros" ? `${ft.properties.NM_BAIRRO} — ${ft.properties.NM_MUN}` : ft.properties.codarea;
      layer.bindTooltip(() => el("div", {}, el("strong", {}, nome), el("br"),
        it ? `${d.ano_a}: ${d.unidade === "var_pct" ? int(it.a) : pct(it.a)} · ${d.ano_b}: ${d.unidade === "var_pct" ? int(it.b) : pct(it.b)}` : "sem dado",
        el("br"), it ? `diferença: ${fmtComp(it.valor, d.unidade)}` : ""), { sticky: true });
      layer.on("mouseover", () => layer.setStyle({ weight: 3, color: cor("--texto") }));
      layer.on("mouseout", () => layer.setStyle({ weight: 1, color: cor("--superficie") }));
    },
  }).addTo(mapa);
  if (camada === "bairros") {
    mapa._contornos = L.geoJSON(await malha(), {
      interactive: false, style: { fill: false, color: cor("--texto"), weight: 0.8, opacity: 0.45 },
    }).addTo(mapa);
  }
  if (!mapa._enquadrado) { mapa.fitBounds(mapa._camada.getBounds(), { padding: [10, 10] }); mapa._enquadrado = true; }
  const mag = (v) => fmtComp(v, d.unidade).replace(/^[+−]/, "");  // magnitude, sem sinal
  const itens = [
    [cores[6], `aumento maior que ${mag(lim[2])}`], [cores[5], `aumento de ${mag(lim[1])} a ${mag(lim[2])}`],
    [cores[4], `aumento de ${mag(lim[0])} a ${mag(lim[1])}`], [cores[3], `variação menor que ±${mag(lim[0])}`],
    [cores[2], `redução de ${mag(lim[0])} a ${mag(lim[1])}`], [cores[1], `redução de ${mag(lim[1])} a ${mag(lim[2])}`],
    [cores[0], `redução maior que ${mag(lim[2])}`], [semDado, "sem dado"],
  ];
  mapa._export = { camada, cores: coresExport, legenda: itens, titulo: `${d.rotulo}: ${d.ano_b} − ${d.ano_a}`,
    subtitulo: d.subtitulo || null };
  legendaEl.replaceChildren(el("h4", {}, `${d.rotulo}: ${d.ano_b} − ${d.ano_a}`),
    ...itens.map(([c, t]) => el("div", {}, el("span", { class: "amostra", style: { background: c } }), t)));
}

// endereços diretos: #mapas[?cargo=&metrica=&numero=&momento=&locais=1], #comparacao,
// #candidato?cargo=&numero=[&municipio=&ordem=COLUNA-desc|asc][&pl=1&pl_ano=&pl_cargo=&pl_numero=&pl_municipio=&pl_comparar=]
// (e o antigo #candidato/<cargo>/<número>[/<município>]),
// #comparacao?cargo=&metrica=[&partido=|&numero_a=&numero_b=][&ordem=]
// ---------------------------------------------------------------- perfil × voto (por bairro)
const pf = (id) => document.getElementById(`pf-${id}`);
estado.pf = { info: null, listas: {}, feito: false, dados: null, pedido: 0 };

const REG_PADRAO = ["pct_superior", "renda_media", "pct_pretos_pardos", "pct_60_mais"];
const ehLocal = () => pf("unidade").value === "local";
const nomeUnidade = (plural = true) => (ehLocal() ? (plural ? "locais" : "local") : (plural ? "bairros" : "bairro"));

// info da unidade escolhida (bairro ou local): municípios e indicadores mudam com ela
async function carregarInfoPerfil() {
  const u = pf("unidade").value;
  estado.pf.infos ||= {};
  if (!estado.pf.infos[u]) estado.pf.infos[u] = await api(`api/perfil/info?unidade=${u}`);
  estado.pf.info = estado.pf.infos[u];
  const info = estado.pf.info;
  const xAtual = pf("x").value, munAtual = pf("municipio").value;
  const grupos = {};
  for (const [k, i] of Object.entries(info.indicadores)) (grupos[i.fonte] ||= []).push(el("option", { value: k }, i.rotulo));
  pf("x").replaceChildren(...Object.entries(grupos).map(([f, ops]) => el("optgroup", { label: f }, ops)),
    el("optgroup", { label: "Outra eleição" }, el("option", { value: "voto" }, "Voto em outra eleição (transferência)")));
  if ([...pf("x").options].some((o) => o.value === xAtual)) pf("x").value = xAtual;
  pf("municipio").replaceChildren(el("option", { value: "" }, ehLocal() ? "Estado inteiro" : "Todos com bairros"),
    ...info.municipios.map((m) => el("option", { value: m.CD_MUN }, `${m.NM_MUN} (${m.BAIRROS} ${nomeUnidade()})`)));
  if ([...pf("municipio").options].some((o) => o.value === munAtual)) pf("municipio").value = munAtual;
  const marcados = new Set(estado.pf.reg || REG_PADRAO);
  pf("reg-ind").replaceChildren(...Object.entries(info.indicadores).map(([k, i]) => el("label", { class: "check" },
    el("input", { type: "checkbox", value: k, checked: marcados.has(k) || null }), ` ${i.rotulo}`)));
  return info;
}

async function iniciarPerfil() {
  if (estado.pf.info && estado.pf.info.unidade === pf("unidade").value) return;
  const primeira = !estado.pf.info;
  const info = await carregarInfoPerfil();
  if (!primeira) return;
  const anos = Object.keys(info.anos).sort((a, b) => b - a);
  for (const sel of [pf("ano"), pf("x-ano")]) sel.replaceChildren(...anos.map((a) => el("option", { value: a }, a)));
  // padrão: a eleição mais recente com governador (2022), senão a mais recente
  const comGov = anos.find((a) => info.anos[a].includes(3));
  pf("ano").value = comGov ?? anos[0] ?? "";
  pf("x-ano").value = anos.find((a) => a !== pf("ano").value) ?? pf("ano").value;
  pf("x").value = "pct_superior";
}

function cargosPerfil(sel, ano, preferido = null) {
  const info = estado.pf.info;
  const cs = info.anos[ano] || [];
  const alvo = String(preferido ?? sel.value);
  sel.replaceChildren(...cs.map((c) => el("option", { value: c }, info.cargos[c])));
  if (cs.map(String).includes(alvo)) sel.value = alvo;
  else if (cs.includes(3)) sel.value = "3";
}

async function listaPerfil(tipo, ano, cargo, turno) {
  const mun = tipo === "candidatos" ? pf("municipio").value : "";  // nº municipal muda de pessoa a cada município
  const u = pf("unidade").value;
  const chave = `${tipo}/${ano}/${cargo}/${turno}/${mun}/${u}`;
  if (!estado.pf.listas[chave]) {
    try {
      estado.pf.listas[chave] = await api(`api/perfil/${tipo}?ano=${ano}&cargo=${cargo}&turno=${turno}&unidade=${u}` +
        (mun ? `&municipio=${mun}` : ""));
    }
    catch (_) { estado.pf.listas[chave] = []; }  // ex.: turno sem votos para o cargo
  }
  return estado.pf.listas[chave];
}

// preenche a lista de candidatos (datalist) e de partidos de um lado (Y: prefixo "", X: prefixo "x-")
async function preencherAlvo(p) {
  const ano = pf(`${p}ano`).value, cargo = pf(`${p}cargo`).value, turno = pf(`${p}turno`).value;
  const partido = pf(`${p}tipo`).value === "partido";
  document.getElementById(`pf-l-${p}numero`).hidden = partido || (p && pf("x").value !== "voto");
  document.getElementById(`pf-l-${p}partido`).hidden = !partido || (p && pf("x").value !== "voto");
  if (!ano || !cargo) return;
  if (partido) {
    const ps = await listaPerfil("partidos", ano, cargo, turno);
    const atual = pf(`${p}partido`).value, siglaAtual = pf(`${p}partido`).selectedOptions[0]?.dataset.sigla;
    pf(`${p}partido`).replaceChildren(...ps.map((x) => el("option", { value: x.PARTIDO, "data-sigla": x.SIGLA ?? "" },
      `${x.PARTIDO}${x.SIGLA ? " " + x.SIGLA : ""} — ${int(x.VOTOS)} votos`)));
    // mantém a escolha ao trocar de ano só se for o MESMO partido: o nº é reaproveitado (14 = PTB em 2022,
    // MISSÃO em 2026); escolha vinda do endereço (sem sigla anterior) vale pelo nº
    if (ps.some((x) => String(x.PARTIDO) === atual && (siglaAtual === undefined || (x.SIGLA ?? "") === siglaAtual))) {
      pf(`${p}partido`).value = atual;
    }
  } else {
    const cs = await listaPerfil("candidatos", ano, cargo, turno);
    pf(`${p}lista`).replaceChildren(...cs.map((c) => el("option", { value: String(c.NUMERO) }, c.NOME)));
    if (!pf(`${p}numero`).value && cs.length) pf(`${p}numero`).value = String(cs[0].NUMERO);
  }
}

function numeroPerfil(p) {
  const t = pf(`${p}numero`).value.trim();
  if (/^\d+$/.test(t)) return t;
  const lista = estado.pf.listas[`candidatos/${pf(`${p}ano`).value}/${pf(`${p}cargo`).value}/${pf(`${p}turno`).value}/` +
    `${pf("municipio").value}/${pf("unidade").value}`] || [];
  const alvo = t.toUpperCase();
  const achado = alvo && lista.find((c) => (c.NOME || "").toUpperCase().includes(alvo));
  if (achado) { pf(`${p}numero`).value = String(achado.NUMERO); return String(achado.NUMERO); }
  return "";
}

async function ajustarPerfil(lado = null) {
  const xVoto = pf("x").value === "voto";
  document.querySelectorAll(".pf-xv").forEach((e) => { e.hidden = !xVoto; });
  if (lado !== "x") { cargosPerfil(pf("cargo"), pf("ano").value); await preencherAlvo(""); }
  if (xVoto && lado !== "y") { cargosPerfil(pf("x-cargo"), pf("x-ano").value); await preencherAlvo("x-"); }
}

pf("ano").addEventListener("change", () => { pf("numero").value = ""; ajustarPerfil("y"); });
pf("cargo").addEventListener("change", () => { pf("numero").value = ""; preencherAlvo(""); });
pf("turno").addEventListener("change", () => { pf("numero").value = ""; preencherAlvo(""); });
pf("tipo").addEventListener("change", () => preencherAlvo(""));
pf("x").addEventListener("change", () => ajustarPerfil("x"));
pf("x-ano").addEventListener("change", () => { pf("x-numero").value = ""; ajustarPerfil("x"); });
pf("x-cargo").addEventListener("change", () => { pf("x-numero").value = ""; preencherAlvo("x-"); });
pf("x-turno").addEventListener("change", () => { pf("x-numero").value = ""; preencherAlvo("x-"); });
pf("x-tipo").addEventListener("change", () => preencherAlvo("x-"));
pf("municipio").addEventListener("change", () => ajustarPerfil());
pf("unidade").addEventListener("change", async () => {
  await carregarInfoPerfil(); await ajustarPerfil(); analisarPerfil();
});
pf("reg-btn").addEventListener("click", () => {
  estado.pf.reg = [...pf("reg-ind").querySelectorAll("input:checked")].map((i) => i.value);
  analisarPerfil();
});
document.getElementById("form-perfil").addEventListener("submit", (e) => { e.preventDefault(); analisarPerfil(); });
pf("copiar").addEventListener("click", () => copiarLink(`#perfil?${enderecoPerfil()}`, pf("copiar-msg")));

function enderecoPerfil() {
  const q = new URLSearchParams({ ano: pf("ano").value, turno: pf("turno").value, cargo: pf("cargo").value });
  if (pf("tipo").value === "partido") q.set("partido", pf("partido").value);
  else q.set("numero", numeroPerfil(""));
  q.set("x", pf("x").value);
  if (pf("x").value === "voto") {
    q.set("x_ano", pf("x-ano").value); q.set("x_turno", pf("x-turno").value); q.set("x_cargo", pf("x-cargo").value);
    if (pf("x-tipo").value === "partido") q.set("x_partido", pf("x-partido").value);
    else q.set("x_numero", numeroPerfil("x-"));
  }
  if (ehLocal()) q.set("unidade", "local");
  if (pf("municipio").value) q.set("municipio", pf("municipio").value);
  q.set("min_validos", pf("min").value || "0");
  if (pf("ponderar").checked) q.set("ponderar", "true");
  const reg = estado.pf.reg || REG_PADRAO;
  if (reg.join(",") !== REG_PADRAO.join(",")) q.set("reg", reg.join(","));
  return q.toString();
}

async function aplicarEnderecoPerfil(params) {
  estado.pf.feito = true;  // o endereço manda; nada de análise padrão por cima
  mostrarAba("perfil");
  const q = new URLSearchParams(params);
  pf("unidade").value = q.get("unidade") === "local" ? "local" : "bairro";
  if (q.get("reg")) estado.pf.reg = q.get("reg").split(",").filter(Boolean);
  await iniciarPerfil();
  const def = (id, k) => { if (q.get(k) !== null) pf(id).value = q.get(k); };
  def("ano", "ano"); def("turno", "turno");
  cargosPerfil(pf("cargo"), pf("ano").value, q.get("cargo"));
  pf("tipo").value = q.get("partido") ? "partido" : "numero";
  def("numero", "numero");
  def("x", "x"); def("x-ano", "x_ano"); def("x-turno", "x_turno");
  pf("x-tipo").value = q.get("x_partido") ? "partido" : "numero";
  def("x-numero", "x_numero");
  def("municipio", "municipio"); def("min", "min_validos");
  pf("ponderar").checked = q.get("ponderar") === "true";
  await preencherAlvo("");
  if (q.get("partido")) pf("partido").value = q.get("partido");
  if (pf("x").value === "voto") {
    document.querySelectorAll(".pf-xv").forEach((e) => { e.hidden = false; });
    cargosPerfil(pf("x-cargo"), pf("x-ano").value, q.get("x_cargo"));
    await preencherAlvo("x-");
    if (q.get("x_partido")) pf("x-partido").value = q.get("x_partido");
  } else document.querySelectorAll(".pf-xv").forEach((e) => { e.hidden = true; });
  await analisarPerfil();
}

const INDICADOR_FMT = {
  renda_media: (v) => `R$ ${fmtInt.format(Math.round(v))}`, renda_mediana: (v) => `R$ ${fmtInt.format(Math.round(v))}`,
  densidade: (v) => `${fmtInt.format(Math.round(v))}/km²`, moradores_domicilio: (v) => v.toFixed(2).replace(".", ","),
};
const fmtX = (k, v) => (v === null || v === undefined ? "—" : (INDICADOR_FMT[k] || pct)(v));
const fmtR = (r) => (r === null || r === undefined ? "—" : (r >= 0 ? "+" : "−") + Math.abs(r).toFixed(2).replace(".", ","));
function forca(r) {
  const a = Math.abs(r ?? 0);
  return a < 0.1 ? "desprezível" : a < 0.3 ? "fraca" : a < 0.5 ? "moderada" : a < 0.7 ? "forte" : "muito forte";
}
const fmtP = (p) => (p === null || p === undefined ? "—" : p < 0.001 ? "< 0,001" : p.toFixed(3).replace(".", ","));

async function analisarPerfil() {
  const msg = pf("msg");
  const limpar = () => ["fichas", "grafico", "correlacoes", "acima", "abaixo", "reg", "reg-fichas"].forEach((k) => pf(k).replaceChildren());
  const q = enderecoPerfil();
  history.replaceState(null, "", `#perfil?${q}`);
  const params = new URLSearchParams(q);
  if (!params.get("numero") && !params.get("partido")) { limpar(); msg.textContent = "Escolha o candidato ou o partido."; return; }
  if (params.get("x") === "voto" && !params.get("x_numero") && !params.get("x_partido")) {
    limpar(); msg.textContent = "Escolha o candidato ou o partido da outra eleição (eixo X)."; return;
  }
  msg.textContent = "calculando… (a 1ª vez de um ano baixa o perfil do eleitorado do TSE)";
  const base = new URLSearchParams(q); base.delete("x"); for (const k of [...base.keys()]) if (k.startsWith("x_")) base.delete(k);
  base.delete("reg");
  const reg = estado.pf.reg || REG_PADRAO;
  let d, c, rg;
  const pedido = ++estado.pf.pedido;  // só a análise mais recente desenha (cliques rápidos não se atropelam)
  try {
    [d, c, rg] = await Promise.all([api(`api/perfil/dispersao?${q}`), api(`api/perfil/correlacoes?${base}`),
      reg.length ? api(`api/perfil/regressao?${base}&indicadores=${reg.join(",")}`).catch((err) => ({ erro: err.message }))
        : Promise.resolve(null)]);
  } catch (e) {
    if (pedido !== estado.pf.pedido) return;
    limpar(); estado.pf.dados = null; msg.textContent = `Não foi possível analisar: ${e.message}`; return;
  }
  if (pedido !== estado.pf.pedido) return;
  estado.pf.dados = d;
  const e = d.estatistica;
  msg.textContent = e.pearson === null ? `Sem ${nomeUnidade()} suficientes (ou sem variação) para calcular a correlação.` : "";
  const xk = params.get("x");
  const unidadeX = xk === "voto" || !INDICADOR_FMT[xk] ? "p.p." : xk.startsWith("renda") ? "R$" : "unidade";
  pf("fichas").replaceChildren(
    ficha(`${ehLocal() ? "Locais" : "Bairros"} na análise`, int(e.n) + (d.ponderado ? ` (n efetivo ${int(Math.round(e.n_efetivo || 0))})` : "")),
    ficha("Pearson r", e.pearson === null ? "—" : `${fmtR(e.pearson)} (${forca(e.pearson)})`),
    ficha("IC 95% de r", e.ic95 ? `${fmtR(e.ic95[0])} a ${fmtR(e.ic95[1])}` : "—"),
    ficha("Spearman ρ", fmtR(e.spearman)),
    ficha("p-valor (r ≠ 0)", fmtP(e.p)),
    ficha("R²", e.r2 === null ? "—" : fmtPct.format(100 * e.r2) + "%"),
    ficha(`Inclinação (+1 ${unidadeX} no eixo X)`, e.b === null ? "—" :
      `${e.b >= 0 ? "+" : "−"}${Math.abs(e.b).toLocaleString("pt-BR", { maximumSignificantDigits: 3 })} p.p.`),
  );
  pf("titulo-grafico").textContent = `${d.rotulo_y} × ${d.rotulo_x}`;
  pf("grafico").replaceChildren(d.pontos.length ? graficoDispersao(d, xk) : el("p", { class: "nota" }, `Nenhum ${nomeUnidade(false)}.`));
  // correlações: da mais forte para a mais fraca; clicar usa o indicador no eixo X
  const linhas = c.correlacoes.map((k) => el("tr", {
    class: `clicavel${k.indicador === xk ? " selecionado" : ""}`, "data-indicador": k.indicador,
    onclick: () => { pf("x").value = k.indicador; ajustarPerfil("x"); analisarPerfil(); },
  }, el("td", {}, k.rotulo), el("td", { class: "num" }, fmtR(k.pearson)), el("td", { class: "num" }, fmtR(k.spearman)),
    el("td", { class: "num" }, k.ic95 ? `${fmtR(k.ic95[0])} a ${fmtR(k.ic95[1])}` : "—"), el("td", { class: "num" }, int(k.n)),
    el("td", { title: k.fonte }, k.fonte.startsWith("TSE") ? "TSE" : "IBGE")));
  pf("correlacoes").replaceChildren(el("table", {}, el("thead", {}, el("tr", {},
    ["Indicador", "r", "ρ", "IC 95% (r)", ehLocal() ? "Locais" : "Bairros", "Fonte"].map((t, i) => el("th", { class: i && i < 5 ? "num" : null }, t)))),
  el("tbody", {}, linhas)));
  const tab = (rows) => el("table", {}, el("thead", {}, el("tr", {}, [ehLocal() ? "Local" : "Bairro", "Eixo X", "Voto", "Resíduo"].map((t, i) =>
    el("th", { class: i ? "num" : null }, t)))), el("tbody", {}, rows.map((r) => el("tr", {},
    el("td", {}, r.BAIRRO), el("td", { class: "num" }, fmtX(xk, r.X)), el("td", { class: "num" }, pct(r.Y)),
    el("td", { class: "num" }, `${r.RESIDUO >= 0 ? "+" : "−"}${fmtPct.format(Math.abs(r.RESIDUO))} p.p.`)))));
  pf("acima").replaceChildren(tab(d.acima));
  pf("abaixo").replaceChildren(tab(d.abaixo));
  desenharRegressao(rg);
}

function desenharRegressao(rg) {
  if (!rg) { pf("reg").replaceChildren(el("p", { class: "nota" }, "Marque ao menos um indicador.")); pf("reg-fichas").replaceChildren(); return; }
  if (rg.erro) { pf("reg").replaceChildren(el("p", { class: "nota" }, `Regressão indisponível: ${rg.erro}`)); pf("reg-fichas").replaceChildren(); return; }
  pf("reg-fichas").replaceChildren(ficha(`${ehLocal() ? "Locais" : "Bairros"}`, int(rg.n)),
    ficha("R² (juntos)", fmtPct.format(100 * rg.r2) + "%"), ficha("R² ajustado", fmtPct.format(100 * rg.r2_ajustado) + "%"));
  const sinal = (x) => `${x >= 0 ? "+" : "−"}${fmtPct.format(Math.abs(x))}`;
  pf("reg").replaceChildren(el("table", {}, el("thead", {}, el("tr", {},
    ["Indicador", "Efeito (p.p. por +1 dp)", "IC 95%", "p", "VIF", "r simples", "1 dp ="].map((t, i) =>
      el("th", { class: i ? "num" : null }, t)))),
  el("tbody", {}, rg.coeficientes.map((k) => el("tr", { class: k.vif > 5 ? "cad-disputa" : null,
    title: k.vif > 5 ? "VIF > 5: anda junto com outro indicador; efeito individual instável" : null },
  el("td", {}, k.rotulo), el("td", { class: "num" }, `${sinal(k.efeito_pp_por_dp)} p.p.`),
  el("td", { class: "num" }, `${sinal(k.ic95[0])} a ${sinal(k.ic95[1])}`), el("td", { class: "num" }, fmtP(k.p)),
  el("td", { class: "num" }, k.vif.toFixed(1).replace(".", ",")), el("td", { class: "num" }, fmtR(k.r_simples)),
  el("td", { class: "num" }, fmtX(k.indicador, k.dp_indicador)))))));
}

function passos(min, max, n = 5) {  // marcas "redondas" do eixo
  const bruto = (max - min) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((p) => bruto <= p);
  const ts = [];
  for (let t = Math.ceil(min / passo) * passo; t <= max + passo * 1e-9; t += passo) ts.push(Number(t.toPrecision(12)));
  return ts;
}

function graficoDispersao(d, xk) {
  const W = 640, H = 400, m = { l: 56, r: 16, t: 12, b: 46 };
  const xs = d.pontos.map((p) => p.X), ys = d.pontos.map((p) => p.Y);
  const pad = (a, b) => [a - (b - a) * 0.04 || a - 1, b + (b - a) * 0.04 || b + 1];
  const [xMin, xMax] = pad(Math.min(...xs), Math.max(...xs));
  const [yMin, yMax] = pad(Math.max(0, Math.min(...ys)), Math.max(...ys));
  const X = (v) => m.l + ((W - m.l - m.r) * (v - xMin)) / (xMax - xMin);
  const Y = (v) => m.t + (H - m.t - m.b) * (1 - (v - yMin) / (yMax - yMin));
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "dispersao", role: "img",
    "aria-label": `${d.rotulo_y} × ${d.rotulo_x}: ${d.pontos.length} bairros` });
  for (const t of passos(yMin, yMax)) {
    if (t < yMin || t > yMax) continue;
    g.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grade" }),
      svg("text", { x: m.l - 6, y: Y(t) + 3, class: "eixo", "text-anchor": "end" }, `${fmtInt.format(t)}%`));
  }
  const curto = (v) => (xk && xk.startsWith("renda") ? `R$ ${fmtInt.format(v)}` : xk === "densidade" ? fmtInt.format(v)
    : xk === "moradores_domicilio" ? String(v).replace(".", ",") : `${fmtInt.format(v)}%`);
  for (const t of passos(xMin, xMax, 6)) {
    if (t < xMin || t > xMax) continue;
    g.append(svg("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, class: "grade" }),
      svg("text", { x: X(t), y: H - m.b + 14, class: "eixo", "text-anchor": "middle" }, curto(t)));
  }
  g.append(svg("text", { x: (m.l + W - m.r) / 2, y: H - 8, class: "titulo-eixo", "text-anchor": "middle" }, d.rotulo_x),
    svg("text", { x: 12, y: (m.t + H - m.b) / 2, class: "titulo-eixo", "text-anchor": "middle",
      transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, "Voto (% dos válidos)"));
  const e = d.estatistica;
  if (e.b !== null) {  // reta cortada à área do gráfico
    let x1 = xMin, x2 = xMax;
    const yDe = (x) => e.a + e.b * x, xDe = (y) => (y - e.a) / e.b;
    if (e.b !== 0) {
      const lim = [xDe(yMin), xDe(yMax)].sort((a, b) => a - b);
      x1 = Math.max(x1, lim[0]); x2 = Math.min(x2, lim[1]);
    }
    if (x2 > x1) g.append(svg("line", { x1: X(x1), y1: Y(yDe(x1)), x2: X(x2), y2: Y(yDe(x2)), class: "tendencia" }));
  }
  const cAcima = cor("--div-p2"), cAbaixo = cor("--div-n2");
  const pts = d.pontos.map((p) => svg("circle", { cx: X(p.X), cy: Y(p.Y), r: 4, class: "ponto",
    fill: (p.RESIDUO ?? 0) >= 0 ? cAcima : cAbaixo }));
  g.append(...pts);
  const dica = el("div", { class: "dica", hidden: true });
  const caixa = el("div", { class: "serie-caixa" }, g, dica);
  let ativo = null;
  g.addEventListener("mousemove", (ev) => {
    const r = g.getBoundingClientRect();
    const mx = (ev.clientX - r.left) * (W / r.width), my = (ev.clientY - r.top) * (H / r.height);
    let k = -1, melhor = 14 ** 2;  // alvo de 14 unidades: maior que o ponto
    d.pontos.forEach((p, i) => { const dd = (X(p.X) - mx) ** 2 + (Y(p.Y) - my) ** 2; if (dd < melhor) { melhor = dd; k = i; } });
    if (ativo) ativo.classList.remove("ativo");
    if (k < 0) { dica.hidden = true; ativo = null; return; }
    ativo = pts[k]; ativo.classList.add("ativo");
    const p = d.pontos[k];
    dica.replaceChildren(el("strong", {}, p.BAIRRO), el("div", {}, `Eixo X: ${fmtX(xk, p.X)}`),
      el("div", {}, `Voto: ${pct(p.Y)} de ${int(p.VALIDOS)} válidos`),
      el("div", {}, `Resíduo: ${p.RESIDUO >= 0 ? "+" : "−"}${fmtPct.format(Math.abs(p.RESIDUO ?? 0))} p.p.`));
    dica.hidden = false;
    dica.style.left = `${Math.min(ev.clientX - r.left + 12, r.width - 220)}px`;
    dica.style.top = `${Math.max(4, ev.clientY - r.top - 70)}px`;
  });
  g.addEventListener("mouseleave", () => { dica.hidden = true; if (ativo) ativo.classList.remove("ativo"); ativo = null; });
  const u = ehLocal() ? "Local" : "Bairro";
  const itensLeg = [[cAcima, `${u} acima da tendência`], [cAbaixo, `${u} abaixo da tendência`],
    [cor("--texto-2"), `Tendência (mínimos quadrados${d.ponderado ? ", ponderada" : ""})`]];
  const legenda = el("div", { class: "legenda-linha" }, itensLeg.map(([c, t]) => el("span", {},
    el("span", { class: "amostra", style: { background: c } }), t)));
  const baixar = el("div", { class: "nota baixar-serie" }, "Baixar gráfico: ",
    el("button", { type: "button", class: "link", onclick: () => baixarGrafico(g, itensLeg, "svg") }, "SVG"), " ",
    el("button", { type: "button", class: "link", onclick: () => baixarGrafico(g, itensLeg, "png") }, "PNG"));
  return el("div", {}, caixa, legenda, baixar);
}

// ---------------------------------------------------------------- transferência 1º → 2º turno
// Matriz da inferência ecológica (apuracao/transferencia.py): para onde foi cada grupo do 1º turno.
// Endereço: #transferencia?fonte=microdados|tempo_real&ano=&cargo=&nivel=secao|local|municipio[&municipio=<TSE>]
const tf = { feito: false, info: null, pronto: null, ultimo: null };
const tfq = (id) => document.getElementById(`tf-${id}`);
const CORES_2T = ["--serie-1", "--serie-2", "--outros", "--texto-2"];  // finalista A, B, branco/nulo, abstenção
const TINTA_2T = ["#fff", "#fff", "var(--texto)", "var(--superficie)"];
const NOME_NIVEL = { secao: "seção", local: "local de votação", municipio: "município" };
const mil = (n) => (n >= 10_000 ? `${fmtInt.format(Math.round(n / 1000))} mil` : fmtInt.format(Math.round(n)));
const p1 = (v) => (v === null || v === undefined ? "—" : `${v.toFixed(1).replace(".", ",")}%`);

function iniciarTransferencia() {
  tf.pronto = tf.pronto || (async () => {
    tf.info = await api("api/transferencia/info");
    tfq("ano").replaceChildren(...tf.info.anos.slice().reverse().map((a) => el("option", { value: a }, a)));
    const opTR = tfq("fonte").querySelector('[value="tempo_real"]');
    opTR.disabled = !tf.info.tempo_real;
    if (tf.info.tempo_real) tfq("fonte").value = "tempo_real";  // noite do 2º turno: é o que existe
    for (const id of ["fonte", "ano", "cargo"]) tfq(id).addEventListener("change", () => ajustarTf());
    document.getElementById("form-tf").addEventListener("submit", (e) => { e.preventDefault(); calcularTf(); });
    tfq("link").addEventListener("click", () => copiarLink(enderecoTf(), tfq("link-msg")));
    await ajustarTf();
  })();
  return tf.pronto;
}

async function ajustarTf(pedido = {}) {
  const tempoReal = tfq("fonte").value === "tempo_real";
  document.querySelectorAll(".tf-md").forEach((l) => { l.hidden = tempoReal; });
  const cargos = tempoReal ? tf.info.cargos_tempo_real : (tf.info.cargos[tfq("ano").value] || []);
  const antes = pedido.cargo || tfq("cargo").value;
  tfq("cargo").replaceChildren(...cargos.map((c) => el("option", { value: c }, NOMES_CARGO[c] || c)));
  if (cargos.map(String).includes(String(antes))) tfq("cargo").value = String(antes);
  if (tempoReal) return;
  const prefeito = tfq("cargo").value === "11";
  let muns = [];
  try { muns = await api(`api/transferencia/municipios?ano=${tfq("ano").value}&cargo=${tfq("cargo").value}`); }
  catch (e) { tfq("msg").textContent = `Sem a lista de municípios: ${e.message}`; }
  tfq("municipio").replaceChildren(...(prefeito ? [] : [el("option", { value: "" }, `Todo o estado (${estado.uf})`)]),
    ...muns.map((m) => el("option", { value: m.CD_MUNICIPIO }, m.NM_MUNICIPIO)));
  const mun = pedido.municipio ?? "";
  if ([...tfq("municipio").options].some((o) => o.value === String(mun))) tfq("municipio").value = String(mun);
}

function parametrosTf() {
  const q = new URLSearchParams({ fonte: tfq("fonte").value, cargo: tfq("cargo").value });
  if (q.get("fonte") === "microdados") {
    q.set("ano", tfq("ano").value);
    q.set("nivel", tfq("nivel").value);
    if (tfq("municipio").value) q.set("municipio", tfq("municipio").value);
  }
  return q;
}
const enderecoTf = () => `#transferencia?${parametrosTf()}`;

async function aplicarEnderecoTf(params) {
  await iniciarTransferencia();
  const q = new URLSearchParams(params);
  const temOpcao = (sel, v) => v !== null && [...sel.options].some((o) => o.value === v && !o.disabled);
  if (temOpcao(tfq("fonte"), q.get("fonte"))) tfq("fonte").value = q.get("fonte");
  if (temOpcao(tfq("ano"), q.get("ano"))) tfq("ano").value = q.get("ano");
  if (temOpcao(tfq("nivel"), q.get("nivel"))) tfq("nivel").value = q.get("nivel");
  await ajustarTf({ cargo: q.get("cargo"), municipio: q.get("municipio") });
  await calcularTf();
}

async function calcularTf() {
  const q = parametrosTf();
  const out = tfq("resultado");
  if (!tfq("cargo").value) { tfq("msg").textContent = "Nenhum cargo com 2º turno nesta fonte."; return; }
  tfq("msg").textContent = "Calculando… a 1ª vez lê os microdados e roda o bootstrap (10 a 30 s).";
  history.replaceState(null, "", enderecoTf());
  const pedido = q.toString();
  tf.ultimo = pedido;
  let r;
  try { r = await api(`api/transferencia?${pedido}`); } catch (e) {
    if (tf.ultimo === pedido) { tfq("msg").textContent = `Não foi possível calcular: ${e.message}`; out.replaceChildren(); }
    return;
  }
  if (tf.ultimo !== pedido) return;  // outro pedido foi feito enquanto este calculava
  tfq("msg").textContent = "";
  desenharTf(r);
}

function desenharTf(r) {
  const out = tfq("resultado");
  const cat2 = r.categorias_2t;
  const cor = (j) => `var(${CORES_2T[j]})`;
  const val = r.validacao;
  const ab = r.abstencao;
  const fichas = el("div", { class: "fichas" },
    ficha("Unidades", `${fmtInt.format(r.unidades)} (${NOME_NIVEL[r.nivel]})`),
    ficha("Regiões com matriz própria", r.n_estratos > 1 ? `${r.n_estratos} (${r.estrato === "zona" ? "zonas" : "municípios"})` : "uma só"),
    ficha("Abstenção 1º → 2º turno", `${p1(ab.pct_1t)} → ${p1(ab.pct_2t)} (${ab.extra_pp >= 0 ? "+" : ""}${ab.extra_pp.toFixed(2).replace(".", ",")} p.p.)`),
    val ? ficha("Erro fora da amostra", `${val.rmse_modelo_medio_pp.toFixed(2).replace(".", ",")} p.p. (swing uniforme ${val.rmse_swing_medio_pp.toFixed(2).replace(".", ",")})`) : null,
    ficha("Células no limite (0% ou 100%)", `${r.celulas_no_limite} de ${r.categorias_1t.length * cat2.length}`));
  const legenda = el("div", { class: "tf-legenda" },
    ...cat2.map((c, j) => el("span", { style: { "--cor": cor(j) } }, c)));
  const barras = r.matriz.map((m) => el("div", { class: "tf-linha" },
    el("div", { class: "rot" }, m.origem, el("small", {}, `${p1(m.pct_1t)} do eleitorado · ${mil(m.eleitores_1t)}`)),
    el("div", { class: "tf-barra", role: "img",
      "aria-label": `${m.origem}: ` + m.destinos.map((d) => `${d.destino} ${p1(d.pct)}`).join(", ") },
      ...m.destinos.map((d, j) => d.pct < 0.05 ? null : el("div", {
        style: { width: `${d.pct}%`, "--cor": cor(j), "--tinta": TINTA_2T[j] },
        title: `${m.origem} → ${d.destino}: ${p1(d.pct)} (IC 95% ${p1(d.baixo)} a ${p1(d.alto)}); ≈ ${mil(d.eleitores)} eleitores`,
      }, d.pct >= 7 ? p1(d.pct) : "")))));
  const matriz = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "1º turno"), el("th", { class: "n" }, "Eleitores"),
      ...cat2.map((c) => el("th", { class: "n" }, c)))),
    el("tbody", {}, ...r.matriz.map((m) => el("tr", {}, el("td", {}, m.origem), el("td", { class: "n" }, int(m.eleitores_1t)),
      ...m.destinos.map((d) => el("td", { class: "n", title: `≈ ${int(d.eleitores)} eleitores` },
        p1(d.pct), el("br"), el("small", { class: "nota" }, `${p1(d.baixo)}–${p1(d.alto)}`)))))));
  const tabela = (titulo, cols, linhas, fmt) => el("div", {}, el("h3", {}, titulo),
    el("div", { class: "tabela-rolagem" }, el("table", {},
      el("thead", {}, el("tr", {}, ...cols.map(([rot, , num]) => el("th", { class: num ? "n" : null }, rot)))),
      el("tbody", {}, ...linhas.map((l) => el("tr", {}, ...cols.map(([, k, num]) =>
        el("td", { class: num ? "n" : null }, fmt(k, l[k])))))))));
  const fmt = (k, v) => (typeof v === "number" ? (k.endsWith("_PP") ? `${v >= 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")}`
    : k.endsWith("_PCT") ? p1(v) : int(v)) : v ?? "—");
  const [a, b] = cat2;
  const estratos = r.n_estratos > 1 ? tabela(`Votos dos eliminados, por ${r.estrato === "zona" ? "zona" : "município"} (maiores eleitorados)`,
    [["Região", "ESTRATO"], ["Eliminados no 1º", "ELIMINADOS_1T", true],
      ...cat2.map((c) => [`→ ${c}`, `ELIM_PARA_${c}_PCT`, true])], r.estratos, fmt) : null;
  const nome = r.nivel === "municipio" ? "Município" : "Unidade";
  const abst = tabela("Maior abstenção extra (p.p. do eleitorado)", [[nome, "NOME"], ["Município", "NM_MUNICIPIO"],
    ["1º turno", "ABST_1_PCT", true], ["2º turno", "ABST_2_PCT", true], ["Extra", "ABST_EXTRA_PP", true]],
  r.maior_abstencao_extra, fmt);
  const res = (titulo, linhas) => tabela(titulo, [[nome, "NOME"], ["Município", "NM_MUNICIPIO"],
    ["Observado", `${a}_2_PCT`, true], ["Previsto", `${a}_2_AJUSTE_PCT`, true], ["Diferença (p.p.)", "RESIDUO_A_PP", true]],
  linhas, fmt);
  const novos = ab.novos_abstencionistas.filter((n) => n.eleitores > 0)
    .map((n) => `${n.origem}: ${mil(n.eleitores)}`).join(" · ");
  const fragil = r.nivel === "municipio" || r.celulas_no_limite >= 6;
  out.replaceChildren(
    el("h3", {}, `Para onde foi cada grupo do 1º turno — ${r.descricao}`),
    fragil ? el("p", { class: "aviso" }, "Leitura frágil: ",
      r.nivel === "municipio" ? "com municípios como unidades o viés de agregação é grande (em 2022, no RJ, o destino "
        + "dos eliminados por município diferiu em até 22 p.p. do estimado por seção). Use como indicação; a estimativa "
        + "boa vem com os microdados (seção ou local), dias depois do 2º turno. "
        : "",
      `${r.celulas_no_limite} células ficaram em 0% ou 100% (a restrição segurou valores impossíveis).`) : null,
    fichas, legenda, el("div", {}, ...barras),
    el("p", { class: "nota" }, "Passe o mouse numa barra para o intervalo de 95% e o número de eleitores. ",
      `Votaram no 1º turno e se abstiveram no 2º (estimado): ${novos || "—"}.`),
    el("details", { class: "caixa" }, el("summary", {}, "Matriz completa, com intervalos de 95%"),
      el("div", { class: "tabela-rolagem" }, matriz)),
    el("div", { class: "tf-tabelas" }, estratos, abst,
      res(`Onde ${a} foi melhor do que a matriz prevê`, r.residuos_a.acima),
      res(`Onde ${a} foi pior do que a matriz prevê`, r.residuos_a.abaixo)));
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

function lerPreferencia(chave, padrao) {
  try { const v = localStorage.getItem(chave); return v === null ? padrao : v === "1"; } catch (_) { return padrao; }
}
function gravarPreferencia(chave, valor) {
  try { localStorage.setItem(chave, valor ? "1" : "0"); } catch (_) { /* navegação privada */ }
}

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
    tocar(r.alertas.map((a) => a.nivel).sort((x, y) => ordem.indexOf(x) - ordem.indexOf(y))[0]);
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
  const r = await fetch("api/alertas/interesse", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cargo: Number(cargo), numero: Number(numero), acompanhar: sim }) });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* sem JSON */ }
    throw new Error(msg);
  }
  alertas.interesse = (await r.json()).interesse;
  desenharAlertas();
  return alertas.interesse;
}

function seguindo(cargo, numero) {
  return alertas.interesse.some((i) => i.cargo === Number(cargo) && i.numero === Number(numero));
}

// o rótulo vem sempre do estado dos alertas: o candidato pode ser redesenhado (ex.: abrirPorHash inicial)
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
  copiarLink(enderecoPainel(), document.getElementById("destaque-link-msg")));

(function iniciarAlertas() {
  const som = document.getElementById("alertas-som");
  som.checked = lerPreferencia("alertas-som", true);
  som.addEventListener("change", () => { gravarPreferencia("alertas-som", som.checked); if (som.checked) tocar("ok"); });
  document.getElementById("botao-alertas").addEventListener("click", () =>
    abrirPainelAlertas(document.getElementById("painel-alertas").hidden));
  document.getElementById("fechar-alertas").addEventListener("click", () => abrirPainelAlertas(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") abrirPainelAlertas(false); });
  // o navegador só libera o áudio depois de uma interação: o 1º clique prepara o contexto
  document.addEventListener("click", () => {
    try { alertas.audio = alertas.audio || new AudioContext(); if (alertas.audio.state === "suspended") alertas.audio.resume(); } catch (_) { /* */ }
  }, { once: true });
  atualizarAlertas();
  setInterval(atualizarAlertas, ALERTAS_MS);
})();

function abrirPorHash() {
  const [caminho, params] = location.hash.replace(/^#/, "").split("?");
  const [aba, cargo, numero, mun] = caminho.split("/");
  if (aba === "mapas" && params) { aplicarEnderecoMapa(params).then(() => mostrarAba("mapas")); return; }
  if (aba === "comparacao" && params) { aplicarEnderecoComp(params); return; }
  if (aba === "perfil" && params) { aplicarEnderecoPerfil(params); return; }
  if (aba === "painel" && params) {
    const q = new URLSearchParams(params);
    if (q.get("destacar") !== null) definirDestaque(q.get("destacar").split(","), true);
    mostrarAba("painel");
    if (q.get("tv") === "1") modoTv(true);
    return;
  }
  if (aba === "transferencia" && params) { mostrarAba("transferencia"); aplicarEnderecoTf(params); return; }
  if (aba === "candidato" && params) {
    const q = new URLSearchParams(params);
    if (q.get("cargo") && q.get("numero")) {
      // a consulta preenche o nº da planilha com o do candidato; o endereço vem depois e prevalece
      consultarCandidato(q.get("cargo"), Number(q.get("numero")),
        q.get("municipio") ? Number(q.get("municipio")) : null, q.get("ordem"))
        .then(() => { aplicarPlanilha(q); aplicarHistorico(q); gravarEnderecoCandidato(); });
    } else {
      mostrarAba("candidato");
      aplicarPlanilha(q);
      aplicarHistorico(q);
    }
    return;
  }
  if (aba === "candidato" && cargo && numero) consultarCandidato(cargo, Number(numero), mun ? Number(mun) : null);
  else if (["painel", "candidato", "mapas", "comparacao", "perfil", "transferencia"].includes(aba)) mostrarAba(aba);
}
window.addEventListener("hashchange", abrirPorHash);

// ---------------------------------------------------------------- seletor de UF (site com várias UFs)
// O site de várias UFs monta cada uma em /<uf>/ e lista as disponíveis em /ufs.json; no site de uma UF
// esse arquivo não existe e o seletor fica escondido. Trocar de UF mantém a aba e o endereço (#…).
async function iniciarSeletorUf() {
  let d;
  try {
    const r = await fetch("../ufs.json", { cache: "no-store" });
    if (!r.ok) return;
    d = await r.json();
  } catch (_) { return; }
  const atual = location.pathname.split("/").filter(Boolean).at(-1)?.toUpperCase();
  const sel = document.getElementById("seletor-uf");
  sel.replaceChildren(...d.ufs.map((u) => el("option", { value: u.uf, disabled: !u.disponivel, selected: u.uf === atual },
    `${u.uf} — ${u.nome}${u.disponivel ? "" : " (sem dados)"}`)));
  sel.addEventListener("change", () => { location.href = `../${sel.value.toLowerCase()}/${location.hash}`; });
  document.getElementById("seletor-uf-rotulo").hidden = false;
}
iniciarSeletorUf();

iniciarComparacao().then(tick).then(abrirPorHash);
preencherLista(document.getElementById("cand-cargo").value, "cand-lista");
setInterval(tick, REFRESH_MS);
