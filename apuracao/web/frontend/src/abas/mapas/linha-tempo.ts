/* Linha do tempo do mapa por município: "como estava às HH:MM" (última totalização de cada município até o
 * momento; apuracao/divulgacao/serie.py). Estado puro + a barra (range, ▶, rótulo). */
import { hora } from "../../core/formatos";

/** Índice do último momento até `pedido` (ISO compara como texto); 0 se todos depois. */
export const indiceAte = (momentos: readonly string[], pedido: string): number =>
  Math.max(0, momentos.filter((m) => m <= pedido).length - 1);

export function rotuloMomento(momentos: readonly string[], idx: number): string {
  const ultimo = idx === momentos.length - 1;
  return `${hora(momentos[idx])}${ultimo ? " (mais recente)" : ""} · totalização ${idx + 1} de ${momentos.length}`;
}

export class LinhaDoTempo {
  momentos: string[] = [];
  idx = 0;
  /** Escala de cor do quadro "agora" por consulta: vale para todos os quadros (as cores não mudam de sentido). */
  escalas: Record<string, unknown> = {};
  /** Momento pedido pelo endereço, aplicado quando os momentos do cargo chegarem. */
  pedido: string | null = null;
  timer: ReturnType<typeof setInterval> | null = null;

  /** Acompanhando o mais recente (sem momento no endereço). */
  get noFim(): boolean { return this.idx >= this.momentos.length - 1; }
  /** Vendo um momento passado. */
  get noPassado(): boolean { return this.momentos.length > 1 && this.idx < this.momentos.length - 1; }
  get atual(): string | undefined { return this.momentos[this.idx]; }

  /** Recebe os momentos do cargo: quem acompanhava o fim continua no fim; o pedido do endereço vira índice. */
  receber(momentos: string[]): void {
    const noFim = this.noFim;
    this.momentos = momentos;
    if (noFim) this.idx = momentos.length - 1;
    if (this.pedido) { this.idx = indiceAte(momentos, this.pedido); this.pedido = null; }
  }

  /** Volta ao mais recente (outro cargo, endereço novo). */
  irParaOFim(): void { this.idx = Number.MAX_SAFE_INTEGER; }

  parar(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
