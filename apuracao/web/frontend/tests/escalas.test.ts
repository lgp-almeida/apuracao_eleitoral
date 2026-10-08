import { describe, expect, it } from "vitest";
import {
  classeDivergente, escalaCategorica, escalaDivergente, escalaSequencial, faixa, limitesPorMaximo, limitesPorQuantis,
  passos, quebrasQuantis, TOKENS_DIV, TOKENS_SEQ,
} from "../src/componentes/escalas";

const id = (t: string) => t;  // resolver identidade: a "cor" é o próprio token

describe("quebrasQuantis", () => {
  it("quintis sem repetição; ausentes ignorados; vazio = sem quebras", () => {
    expect(quebrasQuantis([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])).toEqual([3, 5, 7, 9]);
    expect(quebrasQuantis([5, null, 5, undefined, 5])).toEqual([5]);
    expect(quebrasQuantis([])).toEqual([]);
  });
});

describe("faixa e escala sequencial", () => {
  it("valor igual à quebra fica na faixa de baixo; acima da última, na última", () => {
    const qb = [3, 5, 7, 9];
    expect([0, 3, 3.1, 9, 100].map((v) => faixa(v, qb))).toEqual([0, 0, 1, 3, 4]);
    expect(faixa(100, [1], 2)).toBe(1);
  });

  it("legenda de mínimo a máximo e cores na ordem amarelo → vermelho", () => {
    const esc = escalaSequencial([20, 40, 60, 80], 0, 100, String, id);
    expect(esc.itensLegenda).toEqual([
      ["--mapa-1", "0 – 20"], ["--mapa-2", "20 – 40"], ["--mapa-3", "40 – 60"], ["--mapa-4", "60 – 80"], ["--mapa-5", "80 – 100"]]);
    expect(esc.corValor(85)).toBe(TOKENS_SEQ[4]);
  });
});

describe("divergente", () => {
  it("negativo à esquerda, positivo à direita, centro para |v| pequeno", () => {
    const lim: [number, number, number] = [1, 2, 3];
    expect([-5, -2.5, -1.5, -0.5, 0, 0.5, 1.5, 2.5, 5].map((v) => classeDivergente(v, lim)))
      .toEqual([0, 1, 2, 3, 3, 3, 4, 5, 6]);
  });

  it("limites por quantis de |v| e por fração do máximo", () => {
    expect(limitesPorMaximo([-6, 3])).toEqual([0.6000000000000001, 2, 4]);
    expect(limitesPorQuantis([])).toEqual([1e-9, 1e-9, 1e-9]);  // sem dados: não divide por zero
    const lim = limitesPorQuantis([-10, -1, 0, 1, 2, 3, 4, 5, 6, 7]);
    expect(lim[0]).toBeLessThan(lim[1]);
    expect(lim[1]).toBeLessThan(lim[2]);
  });

  it("legenda diz subiu/caiu na variação e maior/menor que o esperado no resíduo", () => {
    const vals = [-3, -1, 0, 1, 3];
    const v = escalaDivergente(vals, "variacao", id).itensLegenda.map(([, t]) => t);
    expect(v[0]).toMatch(/^subiu mais de/);
    expect(v[3]).toMatch(/^estável/);
    expect(v[6]).toMatch(/^caiu mais de/);
    const r = escalaDivergente(vals, "residuo", id).itensLegenda.map(([, t]) => t);
    expect(r[0]).toMatch(/^voto maior que o esperado/);
    expect(escalaDivergente(vals, "variacao", id).itensLegenda.map(([c]) => c)).toEqual([...TOKENS_DIV].reverse());
  });
});

describe("categórica", () => {
  it("3 cores e o resto em Outros", () => {
    const cats = [1, 2, 3, 4].map((n) => ({ NUMERO: n, NOME_URNA: `C${n}` }));
    const esc = escalaCategorica(cats, (c) => c.NOME_URNA, id);
    expect(esc.itensLegenda).toEqual([["--serie-1", "C1"], ["--serie-2", "C2"], ["--serie-3", "C3"], ["--outros", "Outros"]]);
    expect(esc.corValor(2)).toBe("--serie-2");
    expect(esc.corValor(4)).toBe("--outros");
  });
});

describe("passos", () => {
  it("marcas redondas dentro do intervalo", () => {
    expect(passos(0, 100)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(passos(0, 1, 4)).toEqual([0, 0.25, 0.5, 0.75, 1]);
    expect(passos(-12, 12, 8)).toEqual([-10, -5, 0, 5, 10]);  // passo bruto 3 → 5
    expect(passos(5, 5)).toEqual([5]);  // intervalo nulo não trava
  });
});
