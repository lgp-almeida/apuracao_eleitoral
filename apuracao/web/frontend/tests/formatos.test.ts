import { describe, expect, it } from "vitest";
import { decimal, fmtFreq, fmtNum, fmtP, fmtPP, fmtR, hora, int, mil, p1, pct, VAZIO } from "../src/core/formatos";

describe("formatos", () => {
  it("ausente vira travessão em todos os formatadores que aceitam ausência", () => {
    for (const f of [int, pct, p1, fmtNum, fmtR, fmtP]) {
      expect(f(null)).toBe(VAZIO);
      expect(f(undefined)).toBe(VAZIO);
    }
    expect(hora(null)).toBe(VAZIO);
    expect(hora("")).toBe(VAZIO);
  });

  it("zero não é ausente", () => {
    expect(int(0)).toBe("0");
    expect(pct(0)).toBe("0,00%");
    expect(fmtNum(0)).toBe("0,00");
  });

  it("separador de milhar e vírgula decimal do pt-BR", () => {
    expect(int(1234567)).toBe("1.234.567");
    expect(pct(48.4321)).toBe("48,43%");
    expect(p1(50.96)).toBe("51,0%");
    expect(decimal(1.5, 2)).toBe("1,50");
    expect(fmtNum(3.14159, 3)).toBe("3,142");
  });

  it("p.p. e correlação levam sinal, com o menos tipográfico", () => {
    expect(fmtPP(2.25)).toBe("+2,3 p.p.");
    expect(fmtPP(-0.04)).toBe("−0,0 p.p.");
    expect(fmtPP(0)).toBe("+0,0 p.p.");
    expect(fmtR(0.456)).toBe("+0,46");
    expect(fmtR(-0.456)).toBe("−0,46");
  });

  it("valor-p muito pequeno vira limite", () => {
    expect(fmtP(0.0004)).toBe("< 0,001");
    expect(fmtP(0.0123)).toBe("0,012");
  });

  it("milhares a partir de 10 mil", () => {
    expect(mil(9_999.4)).toBe("9.999");
    expect(mil(12_345)).toBe("12 mil");
    expect(mil(1_234_567)).toBe("1.235 mil");
    expect(fmtFreq(0.954)).toBe("95%");
  });

  it("hora curta no formato brasileiro", () => {
    expect(hora("2026-10-04T20:15:30")).toMatch(/^04\/10\/2026,? 20:15:30$/);
  });
});
