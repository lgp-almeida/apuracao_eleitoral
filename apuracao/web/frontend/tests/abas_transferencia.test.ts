import { describe, expect, it } from "vitest";
import { desenharTransferencia, formatarCelula, leituraFragil } from "../src/abas/transferencia/desenhar";
import type { ResultadoTransferencia } from "../src/abas/transferencia/tipos";

const destino = (destino: string, pct: number) => ({ destino, pct, baixo: pct - 1, alto: pct + 1, eleitores: 1000 * pct });

function resultado(extra: Partial<ResultadoTransferencia> = {}): ResultadoTransferencia {
  const cat2 = ["ANA (P1)", "BIA (P2)", "Branco/nulo", "Abstenção"];
  return {
    descricao: "Governador 2022, por local", nivel: "local", unidades: 1234, n_estratos: 1, estrato: "municipio",
    categorias_1t: ["ANA (P1)", "BIA (P2)", '<i>"CAIO"</i> (P3)'], categorias_2t: cat2, celulas_no_limite: 1,
    matriz: [{ origem: '<i>"CAIO"</i> (P3)', pct_1t: 20, eleitores_1t: 50_000,
      destinos: [destino(cat2[0], 50), destino(cat2[1], 30), destino(cat2[2], 0.01), destino(cat2[3], 19.99)] }],
    abstencao: { pct_1t: 20, pct_2t: 22.5, extra_pp: 2.5, novos_abstencionistas: [{ origem: "CAIO", eleitores: 12_000 }] },
    validacao: { rmse_modelo_medio_pp: 1.54, rmse_swing_medio_pp: 1.86 },
    estratos: [], maior_abstencao_extra: [{ NOME: "X", NM_MUNICIPIO: "Y", ABST_1_PCT: 10, ABST_2_PCT: 12, ABST_EXTRA_PP: 2 }],
    residuos_a: { acima: [], abaixo: [] },
    ...extra,
  };
}

describe("transferência", () => {
  it("células: p.p. com sinal, % com 1 casa, inteiros e texto", () => {
    expect(formatarCelula("ABST_EXTRA_PP", 2.25)).toBe("+2,3");
    expect(formatarCelula("ABST_EXTRA_PP", -1)).toBe("-1,0");
    expect(formatarCelula("ABST_1_PCT", 10)).toBe("10,0%");
    expect(formatarCelula("ELIMINADOS_1T", 12345)).toBe("12.345");
    expect(formatarCelula("NOME", "Niterói")).toBe("Niterói");
    expect(formatarCelula("NOME", null)).toBe("—");
  });

  it("leitura frágil: município como unidade ou 6+ células no limite", () => {
    expect(leituraFragil({ nivel: "local", celulas_no_limite: 5 })).toBe(false);
    expect(leituraFragil({ nivel: "local", celulas_no_limite: 6 })).toBe(true);
    expect(leituraFragil({ nivel: "municipio", celulas_no_limite: 0 })).toBe(true);
  });

  it("desenho: legenda, uma barra por origem, segmentos desprezíveis omitidos, nome do TSE como texto", () => {
    const raiz = document.createElement("div");
    raiz.replaceChildren(...desenharTransferencia(resultado()));
    expect([...raiz.querySelectorAll(".tf-legenda span")].map((s) => s.textContent)).toEqual(["ANA (P1)", "BIA (P2)", "Branco/nulo", "Abstenção"]);
    expect(raiz.querySelectorAll(".tf-linha")).toHaveLength(1);
    expect(raiz.querySelectorAll(".tf-barra div")).toHaveLength(3);  // 0,01% não vira segmento
    expect(raiz.querySelector(".tf-barra")?.getAttribute("aria-label")).toContain('<i>"CAIO"</i> (P3)');
    expect(raiz.querySelector("i")).toBeNull();
    expect(raiz.querySelector(".aviso")).toBeNull();
    expect(raiz.querySelector(".fichas")?.textContent).toContain("Erro fora da amostra");
  });

  it("aviso de leitura frágil e sem validação", () => {
    const raiz = document.createElement("div");
    raiz.replaceChildren(...desenharTransferencia(resultado({ nivel: "municipio", validacao: null })));
    expect(raiz.querySelector(".aviso")?.textContent).toMatch(/^Leitura frágil: com municípios/);
    expect(raiz.querySelector(".fichas")?.textContent).not.toContain("Erro fora da amostra");
  });
});
