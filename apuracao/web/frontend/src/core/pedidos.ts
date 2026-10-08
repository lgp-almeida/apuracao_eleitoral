/* Uma resposta velha nunca desenha por cima de uma nova: cada pedido de um canal cancela o anterior. */

export class Canal {
  private atual: AbortController | null = null;

  /** Cancela o pedido em curso e devolve o sinal do novo (passe-o em api(…, { sinal })). */
  novo(): AbortSignal {
    this.atual?.abort();
    this.atual = new AbortController();
    return this.atual.signal;
  }

  cancelar(): void {
    this.atual?.abort();
    this.atual = null;
  }
}

/** O erro é o cancelamento de um pedido (não é falha: um pedido mais novo tomou o lugar). */
export const cancelado = (e: unknown): boolean => e instanceof DOMException && e.name === "AbortError";
