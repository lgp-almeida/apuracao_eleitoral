/* Modo TV (rodada 33), #painel?tv=1: tela cheia, um cargo por vez (troca a cada 20 s), alertas e "o que mudou"
 * visíveis. Esc sai; ←/→ navegam; espaço pausa. */
import { el, ref } from "../../core/dom";
import { hora } from "../../core/formatos";

export const TV_MS = 20_000;

export interface EstadoTv { ativo: boolean; idx: number; pausado: boolean; telaCheia: boolean }

export interface ContextoTv {
  /** Título do cartão de índice i (cargo — abrangência). */
  tituloCartao(i: number): string | null;
  /** Coleta e boletim mais recentes (do /api/status). */
  situacao(): { ultimaColeta: string | null; ultimoBoletim: { titulo: string; gerado_em: string } | null };
  /** Mostra o painel (o modo TV só existe nele). */
  mostrarPainel(): void;
  gravarEndereco(): void;
}

/** Índice do cartão em destaque (dá a volta). */
export const cartaoDaVez = (idx: number, n: number): number => idx % Math.max(n, 1);

export function criarModoTv(ctx: ContextoTv) {
  const estado: EstadoTv = { ativo: false, idx: 0, pausado: false, telaCheia: false };
  const barra = ref("#tv-barra");
  let timer: ReturnType<typeof setInterval> | null = null;

  function aplicar(): void {
    const cartoes = [...document.querySelectorAll("#cartoes .cartao")];
    const vez = cartaoDaVez(estado.idx, cartoes.length);
    cartoes.forEach((c, i) => c.classList.toggle("tv-atual", estado.ativo && i === vez));
    barra.hidden = !estado.ativo;
    if (!estado.ativo || !cartoes.length) return;
    const { ultimaColeta, ultimoBoletim: bol } = ctx.situacao();
    barra.replaceChildren(
      el("span", {}, el("strong", {}, ctx.tituloCartao(vez) ?? ""),
        ` (${vez + 1} de ${cartoes.length})${estado.pausado ? " · pausado" : ""}`),
      el("span", {}, `Última coleta: ${hora(ultimaColeta)}`),
      el("span", {}, bol ? `Último boletim: ${bol.titulo} (${hora(bol.gerado_em)})` : "Sem boletim ainda"),
      el("span", {}, "Esc sai · ←/→ navega · espaço pausa"));
  }

  function ligar(sim: boolean): void {
    estado.ativo = sim;
    document.body.classList.toggle("modo-tv", sim);
    if (timer) clearInterval(timer);
    timer = sim ? setInterval(() => { if (!estado.pausado) { estado.idx += 1; aplicar(); } }, TV_MS) : null;
    if (sim) ctx.mostrarPainel();
    if (sim && document.documentElement.requestFullscreen && !document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => { /* sem gesto do usuário: segue sem tela cheia */ });
    }
    if (!sim && document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
    ctx.gravarEndereco();  // tv=1 entra (ou sai) do endereço
    aplicar();
  }

  ref("#botao-tv").addEventListener("click", () => ligar(true));
  document.addEventListener("keydown", (e) => {
    if (!estado.ativo) return;
    if (e.key === "Escape") ligar(false);
    else if (e.key === "ArrowRight") { estado.idx += 1; aplicar(); }
    else if (e.key === "ArrowLeft") { estado.idx = Math.max(0, estado.idx - 1); aplicar(); }
    else if (e.key === " ") { e.preventDefault(); estado.pausado = !estado.pausado; aplicar(); }
  });
  document.addEventListener("fullscreenchange", () => {  // saiu da tela cheia pelo navegador: sai do modo TV
    if (!document.fullscreenElement && estado.ativo && estado.telaCheia) ligar(false);
    estado.telaCheia = Boolean(document.fullscreenElement);
  });

  return { estado, ligar, aplicar };
}
