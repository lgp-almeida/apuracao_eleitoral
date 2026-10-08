/* "Copiar link": o endereço completo da página com o #aba?… atual. */

/** Copia; sem permissão de área de transferência, mostra o link para copiar à mão. A mensagem some em 4 s. */
export async function copiarLink(hash: string, msg: HTMLElement): Promise<void> {
  const url = `${location.origin}${location.pathname}${hash}`;
  try { await navigator.clipboard.writeText(url); msg.textContent = " copiado."; }
  catch { msg.textContent = ` ${url}`; }
  setTimeout(() => { msg.textContent = ""; }, 4000);
}
