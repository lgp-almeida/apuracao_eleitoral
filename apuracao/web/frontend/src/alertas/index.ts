/* Alertas da noite (apuracao/alertas.py; o servidor verifica a cada 15 s). A página pede /api/alertas?desde=<último id>:
 * condições ativas (coletor parado, bloqueio…) ficam na faixa do topo; alertas novos viram avisos, com som.
 * O que já existia ao abrir a página vai só para o histórico. Os alertas continuam com a aba escondida. */
import { api, enviar } from "../core/api";
import { NOMES_CARGO } from "../core/cargos";
import { el, refs } from "../core/dom";
import { gravarPreferencia, lerPreferencia } from "../core/preferencias";
import { cartaoAlerta, maisGrave, NIVEL, notasDoSom, tituloComAlertas } from "./apresentacao";
import type { Alerta, Interesse, Nivel, RespostaAlertas } from "./tipos";

export const ALERTAS_MS = 15_000;

export interface EstadoAlertas {
  ultimo: number | null;
  historico: Alerta[];
  ativos: Alerta[];
  naoVistos: number;
  interesse: Interesse[];
}

/** @param ano ano da eleição do site: "Acompanhar" só vale na noite de 2026 */
export function criarAlertas(ano: () => number) {
  const r = refs({ som: "#alertas-som", botao: "#botao-alertas", painel: "#painel-alertas", fechar: "#fechar-alertas",
    faixa: "#faixa-alertas", contagem: "#alertas-contagem", historico: "#alertas-historico", interesse: "#alertas-interesse",
    avisos: "#avisos" });
  const som = r.som as HTMLInputElement;
  const estado: EstadoAlertas = { ultimo: null, historico: [], ativos: [], naoVistos: 0, interesse: [] };
  let audio: AudioContext | null = null;

  /** Bipe por nível (WebAudio, sem arquivo); o navegador só libera o áudio depois de um clique na página. */
  function bipe(nivel: Nivel): void {
    if (!som.checked) return;
    try {
      audio ??= new AudioContext();
      if (audio.state === "suspended") void audio.resume();
      const ctx = audio;
      notasDoSom(nivel).forEach((f, i) => {
        const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + i * 0.22;
        o.frequency.value = f; o.type = "sine";
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
        o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + 0.2);
      });
    } catch { /* navegador sem WebAudio: fica só o destaque */ }
  }

  const seguindo = (cargo: number | string, numero: number | string) =>
    estado.interesse.some((i) => i.cargo === Number(cargo) && i.numero === Number(numero));

  /** O rótulo vem sempre do estado: o candidato pode ser redesenhado enquanto o pedido ainda está em curso. */
  function rotularAcompanhar(): void {
    const b = document.getElementById("botao-acompanhar");
    if (b) b.textContent = seguindo(b.dataset.cargo ?? "", b.dataset.numero ?? "") ? "Deixar de acompanhar" : "Acompanhar nos alertas";
  }

  function atualizarTitulo(): void {
    const grave = estado.ativos.some((a) => a.nivel === "critico" || a.nivel === "aviso");
    document.title = tituloComAlertas(document.title, grave, estado.naoVistos);
  }

  function desenhar(): void {
    r.faixa.replaceChildren(...estado.ativos.map((a) => cartaoAlerta(a)));
    r.faixa.hidden = !estado.ativos.length;
    r.botao.classList.toggle("tem-ativos", estado.ativos.some((a) => a.nivel === "critico"));
    r.contagem.textContent = String(estado.naoVistos);
    r.contagem.hidden = !estado.naoVistos;
    r.historico.replaceChildren(...estado.historico.slice().reverse().map((a) => el("li", {}, cartaoAlerta(a))));
    r.interesse.replaceChildren(...(estado.interesse.length ? estado.interesse.map((i) =>
      el("div", { class: "interesse-linha" },
        el("span", {}, `${NOMES_CARGO[i.cargo] || i.cargo}: ${i.nome}`),
        el("span", { class: "sit" }, i.situacao || "aguardando 30% apurado"),
        el("button", { type: "button", class: "link", onclick: () => void acompanhar(i.cargo, i.numero, false) }, "remover")))
      : [el("p", { class: "nota" }, "Nenhum.")]));
    atualizarTitulo();
    rotularAcompanhar();
  }

  function mostrarAviso(a: Alerta): void {
    const cartao = cartaoAlerta(a, () => cartao.remove());
    r.avisos.prepend(cartao);
    while (r.avisos.children.length > 5) r.avisos.lastElementChild?.remove();
    if (!(NIVEL[a.nivel] || NIVEL.noticia).fixo) setTimeout(() => cartao.remove(), 30_000);
  }

  const central = {
    estado,
    /** Toca o som de um nível; substituível (testes e2e). */
    tocar: bipe as (nivel: Nivel) => void,
    atualizarTitulo,

    async atualizar(): Promise<void> {
      let resp: RespostaAlertas;
      try { resp = await api(`api/alertas?desde=${estado.ultimo ?? 0}`); } catch { return; }
      const primeira = estado.ultimo === null;
      estado.ultimo = resp.ultimo_id;
      estado.ativos = resp.ativos;
      estado.interesse = resp.interesse;
      estado.historico = estado.historico.concat(resp.alertas).slice(-200);
      if (!primeira && resp.alertas.length) {  // o que já existia ao abrir a página vai só para o histórico
        if (r.painel.hidden) estado.naoVistos += resp.alertas.length;
        resp.alertas.forEach(mostrarAviso);
        const nivel = maisGrave(resp.alertas.map((a) => a.nivel));
        if (nivel) central.tocar(nivel);
      }
      desenhar();
    },

    abrirPainel(abrir: boolean): void {
      r.painel.hidden = !abrir;
      r.botao.setAttribute("aria-expanded", String(abrir));
      if (abrir) {  // os avisos estão no histórico: saem para não cobrir o painel (no celular, ocupam a tela)
        r.avisos.replaceChildren();
        estado.naoVistos = 0; desenhar(); r.fechar.focus();
      }
    },

    /** "Acompanhar nos alertas" de um deputado (aba Candidato), ou null quando não se aplica. */
    botaoAcompanhar(cargo: number | string, numero: number): HTMLElement | null {
      if (![6, 7, 8].includes(Number(cargo)) || ano() !== 2026) return null;
      const msg = el("span", { class: "nota", "aria-live": "polite" });
      const b = el("button", { type: "button", id: "botao-acompanhar", "data-cargo": cargo, "data-numero": numero });
      b.addEventListener("click", async () => {
        try {
          await acompanhar(cargo, numero, !seguindo(cargo, numero));
          msg.textContent = seguindo(cargo, numero) ? " Você será avisado." : "";
        } catch (e) { msg.textContent = ` ${(e as Error).message}`; }
      });
      queueMicrotask(rotularAcompanhar);
      return el("p", { class: "nota" }, b, msg);
    },
  };

  async function acompanhar(cargo: number | string, numero: number | string, sim: boolean): Promise<Interesse[]> {
    const resp = await enviar<{ interesse: Interesse[] }>("api/alertas/interesse",
      { cargo: Number(cargo), numero: Number(numero), acompanhar: sim });
    estado.interesse = resp.interesse;
    desenhar();
    return estado.interesse;
  }

  som.checked = lerPreferencia("alertas-som", true);
  som.addEventListener("change", () => { gravarPreferencia("alertas-som", som.checked); if (som.checked) central.tocar("ok"); });
  r.botao.addEventListener("click", () => central.abrirPainel(r.painel.hidden !== false));
  r.fechar.addEventListener("click", () => central.abrirPainel(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") central.abrirPainel(false); });
  // o navegador só libera o áudio depois de uma interação: o 1º clique prepara o contexto
  document.addEventListener("click", () => {
    try { audio ??= new AudioContext(); if (audio.state === "suspended") void audio.resume(); } catch { /* sem WebAudio */ }
  }, { once: true });

  return central;
}

export type CentralAlertas = ReturnType<typeof criarAlertas>;
