import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api, baixar, enviar, ErroApi, ROTAS_PESADAS, TEMPO_LIMITE_MS, TEMPO_LIMITE_PESADO_MS, tempoLimitePara,
} from "../src/core/api";

const json = (corpo: unknown, status = 200, cab: Record<string, string> = {}) =>
  new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json", ...cab } });

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("tempo-limite por rota", () => {
  it("rotas pesadas (com ou sem ./, consulta ou subcaminho) ganham o limite longo", () => {
    expect(tempoLimitePara("api/painel")).toBe(TEMPO_LIMITE_MS);
    expect(tempoLimitePara("api/mapa/locais?ano=2022")).toBe(TEMPO_LIMITE_PESADO_MS);
    expect(tempoLimitePara("./api/transferencia/info")).toBe(TEMPO_LIMITE_PESADO_MS);
    expect(tempoLimitePara("/geo/bairros.geojson")).toBe(TEMPO_LIMITE_PESADO_MS);
    expect(tempoLimitePara("api/perfilx")).toBe(TEMPO_LIMITE_MS);  // prefixo de palavra não basta
    expect(ROTAS_PESADAS.every((r) => r.startsWith("/"))).toBe(true);
  });
});

describe("api", () => {
  it("GET sem cache e devolve o JSON", async () => {
    const f = vi.fn(async (_rota: string, _init: RequestInit) => json({ ok: 1 }));
    vi.stubGlobal("fetch", f);
    expect(await api("api/status")).toEqual({ ok: 1 });
    expect(f.mock.calls[0][0]).toBe("api/status");
    expect(f.mock.calls[0][1].cache).toBe("no-store");
  });

  it("erro HTTP leva o detail do FastAPI e o status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "cargo inválido" }, 400)));
    const e = await api("api/x").catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErroApi);
    expect((e as ErroApi).message).toBe("cargo inválido");
    expect((e as ErroApi).status).toBe(400);
  });

  it("erro sem JSON leva o status como mensagem", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 502 })));
    await expect(api("api/x")).rejects.toThrow("502");
  });

  it("tempo-limite vira ErroApi legível", async () => {
    vi.stubGlobal("fetch", vi.fn((_: string, init: RequestInit) => new Promise((_r, rej) => {
      init.signal?.addEventListener("abort", () => rej(init.signal?.reason));
    })));
    const e = await api("api/x", { tempoLimite: 20 }).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErroApi);
    expect((e as ErroApi).status).toBeNull();
    expect((e as ErroApi).message).toMatch(/não respondeu/);
  });

  it("cancelamento chega como AbortError (não é erro do site)", async () => {
    vi.stubGlobal("fetch", vi.fn((_: string, init: RequestInit) => new Promise((_r, rej) => {
      init.signal?.addEventListener("abort", () => rej(init.signal?.reason));
    })));
    const c = new AbortController();
    const p = api("api/x", { sinal: c.signal });
    c.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("enviar e baixar", () => {
  it("POST com corpo JSON", async () => {
    const f = vi.fn(async (_rota: string, _init: RequestInit) => json({ interesse: [1] }));
    vi.stubGlobal("fetch", f);
    expect(await enviar("api/alertas/interesse", { cargo: 7 })).toEqual({ interesse: [1] });
    const init = f.mock.calls[0][1];
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"cargo":7}');
  });

  it("nome do arquivo vem do Content-Disposition, senão o padrão", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("x", { headers: { "Content-Disposition": 'attachment; filename="m.png"' } })));
    expect((await baixar("api/exportar/mapa", "mapa.svg")).nome).toBe("m.png");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("x")));
    const r = await baixar("api/planilha", "planilha.xlsx");
    expect(r.nome).toBe("planilha.xlsx");
    expect(await r.blob.text()).toBe("x");
  });
});
