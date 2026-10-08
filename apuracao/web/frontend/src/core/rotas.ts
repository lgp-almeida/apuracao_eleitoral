/* Endereços das abas (#<aba>?<parâmetros>), sem DOM. O endereço guarda todo o estado visível de cada aba
 * (ver CLAUDE.md, "Endereços do site"); aqui só a forma: ler e escrever, inclusive o formato antigo
 * #candidato/<cargo>/<número>[/<município>]. */

export const ABAS = ["painel", "candidato", "mapas", "comparacao", "perfil", "transferencia"] as const;
export type Aba = (typeof ABAS)[number];

export const ehAba = (x: unknown): x is Aba => typeof x === "string" && (ABAS as readonly string[]).includes(x);

export interface Endereco {
  /** null = endereço vazio ou de aba desconhecida (não muda nada). */
  aba: Aba | null;
  params: URLSearchParams;
}

/** "#mapas?cargo=3" → { aba: "mapas", params: cargo=3 }. Só o 1º "?" separa (um "?" no valor fica no valor). */
export function lerEndereco(hash: string): Endereco {
  const texto = hash.replace(/^#/, "");
  const i = texto.indexOf("?");
  const caminho = i < 0 ? texto : texto.slice(0, i);
  const params = new URLSearchParams(i < 0 ? "" : texto.slice(i + 1));
  const [nome, ...resto] = caminho.split("/");
  const aba = ehAba(nome) ? nome : null;
  // formato antigo: #candidato/<cargo>/<número>[/<município>] (só quando não há parâmetros)
  if (aba === "candidato" && resto.length >= 2 && resto[0] && resto[1] && i < 0) {
    params.set("cargo", resto[0]);
    params.set("numero", resto[1]);
    if (resto[2]) params.set("municipio", resto[2]);
  }
  return { aba, params };
}

/** Aba do endereço (o que vem antes de "?" ou "/"), ou null. */
export const abaDoEndereco = (hash: string): Aba | null => {
  const nome = hash.replace(/^#/, "").split(/[?/]/)[0];
  return ehAba(nome) ? nome : null;
};

/** { aba, params } → "#aba" ou "#aba?…" (sem "?" sobrando quando não há parâmetros). */
export function escreverEndereco(aba: Aba, params?: URLSearchParams): string {
  const q = params?.toString() ?? "";
  return q ? `#${aba}?${q}` : `#${aba}`;
}
