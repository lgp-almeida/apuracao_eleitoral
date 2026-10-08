import { describe, expect, it } from "vitest";
import { Canal, cancelado } from "../src/core/pedidos";

describe("Canal", () => {
  it("cada pedido novo cancela o anterior", () => {
    const c = new Canal();
    const a = c.novo();
    const b = c.novo();
    expect(a.aborted).toBe(true);
    expect(b.aborted).toBe(false);
    c.cancelar();
    expect(b.aborted).toBe(true);
  });

  it("reconhece o erro de cancelamento", () => {
    const c = new AbortController(); c.abort();
    expect(cancelado(c.signal.reason)).toBe(true);
    expect(cancelado(new Error("x"))).toBe(false);
  });
});
