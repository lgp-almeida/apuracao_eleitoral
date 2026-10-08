/* Pedidos ao site Python: tempo-limite, cancelamento e erro com a mensagem do servidor (`detail` do FastAPI). */

/** Rotas que podem demorar (conversão de microdados, malhas, inferência). Espelho de ROTAS_PESADAS em
 * apuracao/web/app.py — test_frontend_build.py confere que as duas listas são iguais. */
export const ROTAS_PESADAS = [
  "/api/planilha", "/api/mapa/bairros", "/api/mapa/areas", "/api/comparacao/bairros", "/api/perfil",
  "/api/exportar", "/geo/locais.geojson", "/geo/bairros.geojson", "/geo/areas.geojson", "/api/transferencia",
  "/api/mapa/locais",
] as const;

export const TEMPO_LIMITE_MS = 60_000;
export const TEMPO_LIMITE_PESADO_MS = 600_000;

/** Erro de um pedido: status HTTP (null = sem resposta) e a mensagem do servidor quando houver. */
export class ErroApi extends Error {
  constructor(message: string, readonly status: number | null) {
    super(message);
    this.name = "ErroApi";
  }
}

export interface OpcoesPedido {
  /** Cancela o pedido (ex.: Canal.novo()); o cancelamento chega como DOMException "AbortError". */
  sinal?: AbortSignal;
  /** Em ms; null = sem limite. Padrão: pelo tipo da rota (tempoLimitePara). */
  tempoLimite?: number | null;
}

/** "api/x?y", "./api/x" ou "/api/x" → "/api/x" (as rotas da página são relativas: site de várias UFs). */
const normalizar = (rota: string): string => "/" + rota.replace(/^\.?\//, "").split("?")[0];

export const tempoLimitePara = (rota: string): number => {
  const r = normalizar(rota);
  return ROTAS_PESADAS.some((p) => r === p || r.startsWith(p + "/") || r.startsWith(p + "?"))
    ? TEMPO_LIMITE_PESADO_MS : TEMPO_LIMITE_MS;
};

async function mensagemDoServidor(r: Response): Promise<string> {
  try {
    const d: unknown = await r.json();
    if (d && typeof d === "object" && "detail" in d && d.detail) return String(d.detail);
  } catch { /* resposta sem JSON */ }
  return String(r.status);
}

/** fetch com tempo-limite e erro uniforme; devolve a resposta já conferida (2xx). */
export async function pedir(rota: string, init: RequestInit = {}, opcoes: OpcoesPedido = {}): Promise<Response> {
  const limite = opcoes.tempoLimite === undefined ? tempoLimitePara(rota) : opcoes.tempoLimite;
  const sinais = [opcoes.sinal, limite === null ? undefined : AbortSignal.timeout(limite)]
    .filter((s): s is AbortSignal => s !== undefined);
  let r: Response;
  try {
    r = await fetch(rota, { cache: "no-store", ...init, signal: sinais.length ? AbortSignal.any(sinais) : undefined });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") {
      throw new ErroApi(`o site não respondeu em ${Math.round((limite ?? 0) / 1000)} s`, null);
    }
    throw e;  // cancelamento (AbortError) ou rede: quem pediu decide
  }
  if (!r.ok) throw new ErroApi(await mensagemDoServidor(r), r.status);
  return r;
}

/** GET de JSON. */
export async function api<T = unknown>(rota: string, opcoes: OpcoesPedido = {}): Promise<T> {
  return (await pedir(rota, {}, opcoes)).json() as Promise<T>;
}

/** POST de JSON, resposta em JSON. */
export async function enviar<T = unknown>(rota: string, corpo: unknown, opcoes: OpcoesPedido = {}): Promise<T> {
  const init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) };
  return (await pedir(rota, init, opcoes)).json() as Promise<T>;
}

/** Arquivo gerado pelo servidor: conteúdo e o nome do Content-Disposition (ou o padrão). */
export async function baixar(rota: string, padrao: string, init: RequestInit = {}, opcoes: OpcoesPedido = {}):
    Promise<{ blob: Blob; nome: string }> {
  const r = await pedir(rota, init, opcoes);
  const nome = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || padrao;
  return { blob: await r.blob(), nome };
}
