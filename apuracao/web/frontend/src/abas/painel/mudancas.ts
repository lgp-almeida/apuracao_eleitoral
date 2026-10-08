/* "O que mudou" desde o último boletim (rodada 33): GET /api/mudancas compara o último boletim com agora. */
import { api } from "../../core/api";
import { el, refs } from "../../core/dom";
import type { Mudancas } from "./tipos";

/** "O que mudou desde o boletim das 20h (20:00)". */
export function tituloMudancas(anterior: NonNullable<Mudancas["anterior"]>): string {
  const quando = new Date(anterior.gerado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const t = anterior.titulo.startsWith("Boletim") ? anterior.titulo.toLowerCase() : anterior.titulo;
  return `O que mudou desde o ${t} (${quando})`;
}

export function criarMudancas() {
  const r = refs({ caixa: "#mudancas", titulo: "#mudancas-titulo", lista: "#mudancas-lista" });
  return async function atualizar(): Promise<void> {
    let m: Mudancas;
    try { m = await api("api/mudancas"); } catch { return; }
    r.caixa.hidden = !m.anterior;
    if (!m.anterior) return;
    r.titulo.textContent = tituloMudancas(m.anterior);
    r.lista.replaceChildren(...(m.mudancas.length
      ? m.mudancas.map((x) => el("li", {}, el("strong", {}, x.cargo), `: ${x.texto}`))
      : [el("li", {}, "Nada mudou nos números do boletim.")]));
  };
}
