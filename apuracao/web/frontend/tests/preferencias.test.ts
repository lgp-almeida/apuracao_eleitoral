import { afterEach, describe, expect, it, vi } from "vitest";
import { gravarJson, gravarPreferencia, lerJson, lerPreferencia } from "../src/core/preferencias";

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe("preferências", () => {
  it("liga/desliga e JSON vão e voltam", () => {
    gravarPreferencia("som", false);
    expect(lerPreferencia("som", true)).toBe(false);
    gravarJson("destacar", ["PT", "PL"]);
    expect(lerJson("destacar")).toEqual(["PT", "PL"]);
  });

  it("ausente ou inválido devolve o padrão", () => {
    expect(lerPreferencia("nada", true)).toBe(true);
    localStorage.setItem("ruim", "{");
    expect(lerJson("ruim")).toBeNull();
  });

  it("armazenamento bloqueado não derruba a página", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("bloqueado"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("bloqueado"); });
    expect(lerPreferencia("som", true)).toBe(true);
    expect(() => gravarJson("x", 1)).not.toThrow();
  });
});
