import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { repetir } from "../src/core/agendador";

let oculto = false;
beforeEach(() => {
  vi.useFakeTimers();
  oculto = false;
  Object.defineProperty(document, "hidden", { configurable: true, get: () => oculto });
});
afterEach(() => vi.useRealTimers());

const mudarVisibilidade = (h: boolean) => { oculto = h; document.dispatchEvent(new Event("visibilitychange")); };

describe("repetir", () => {
  it("não sobrepõe: enquanto uma execução dura, os passos seguintes são pulados", async () => {
    let fim: () => void = () => undefined;
    const tarefa = vi.fn(() => new Promise<void>((r) => { fim = r; }));
    const rep = repetir(tarefa, 100);
    await vi.advanceTimersByTimeAsync(350);
    expect(tarefa).toHaveBeenCalledTimes(1);
    fim();
    await vi.advanceTimersByTimeAsync(100);
    expect(tarefa).toHaveBeenCalledTimes(2);
    rep.parar();
  });

  it("agora() durante uma execução espera a mesma execução", async () => {
    let fim: () => void = () => undefined;
    const tarefa = vi.fn(() => new Promise<void>((r) => { fim = r; }));
    const rep = repetir(tarefa, 1000);
    const a = rep.agora(); const b = rep.agora();
    fim(); await a; await b;
    expect(tarefa).toHaveBeenCalledTimes(1);
    rep.parar();
  });

  it("erro na tarefa não para a repetição", async () => {
    const erros: unknown[] = [];
    const tarefa = vi.fn(() => { throw new Error("falhou"); });
    const rep = repetir(tarefa, 100, { aoErrar: (e) => erros.push(e) });
    await vi.advanceTimersByTimeAsync(300);
    expect(tarefa).toHaveBeenCalledTimes(3);
    expect(erros).toHaveLength(3);
    rep.parar();
  });

  it("com pausarOculto, não roda escondida e roda uma vez ao voltar", async () => {
    const tarefa = vi.fn();
    const rep = repetir(tarefa, 100, { pausarOculto: true });
    mudarVisibilidade(true);
    await vi.advanceTimersByTimeAsync(500);
    expect(tarefa).not.toHaveBeenCalled();
    mudarVisibilidade(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(tarefa).toHaveBeenCalledTimes(1);
    rep.parar();
  });

  it("sem pausarOculto, roda mesmo escondida (alertas)", async () => {
    const tarefa = vi.fn();
    const rep = repetir(tarefa, 100);
    mudarVisibilidade(true);
    await vi.advanceTimersByTimeAsync(200);
    expect(tarefa).toHaveBeenCalledTimes(2);
    rep.parar();
  });

  it("parar() encerra", async () => {
    const tarefa = vi.fn();
    repetir(tarefa, 100).parar();
    await vi.advanceTimersByTimeAsync(500);
    expect(tarefa).not.toHaveBeenCalled();
  });
});
