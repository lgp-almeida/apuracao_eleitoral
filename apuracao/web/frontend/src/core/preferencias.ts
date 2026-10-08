/* Preferências do navegador (som, destaque…): o armazenamento pode faltar (navegação privada, bloqueio),
 * então ler devolve o padrão e gravar falha em silêncio. Nada que precise persistir de verdade fica aqui. */

function armazenamento(): Storage | null {
  try { return window.localStorage; } catch { return null; }
}

export function lerTexto(chave: string): string | null {
  try { return armazenamento()?.getItem(chave) ?? null; } catch { return null; }
}

export function gravarTexto(chave: string, valor: string): void {
  try { armazenamento()?.setItem(chave, valor); } catch { /* navegação privada */ }
}

/** Liga/desliga gravado como "1"/"0". */
export function lerPreferencia(chave: string, padrao: boolean): boolean {
  const v = lerTexto(chave);
  return v === null ? padrao : v === "1";
}

export function gravarPreferencia(chave: string, valor: boolean): void {
  gravarTexto(chave, valor ? "1" : "0");
}

/** JSON gravado; inválido ou ausente = null. */
export function lerJson<T>(chave: string): T | null {
  const v = lerTexto(chave);
  if (v === null) return null;
  try { return JSON.parse(v) as T; } catch { return null; }
}

export function gravarJson(chave: string, valor: unknown): void {
  gravarTexto(chave, JSON.stringify(valor));
}
