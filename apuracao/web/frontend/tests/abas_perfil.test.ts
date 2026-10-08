import { describe, expect, it, vi } from "vitest";
import { desenharRegressao, fichasCorrelacao, tabelaCorrelacoes, tabelaResiduos } from "../src/abas/perfil/desenhar";
import { ehUnidade, fmtX, forca, nomeDaUnidade, unidadeDoX } from "../src/abas/perfil/formatos";
import type { Dispersao } from "../src/abas/perfil/tipos";

describe("formatos do perfil", () => {
  it("indicador no seu formato", () => {
    expect(fmtX("renda_media", 1500.4)).toBe("R$ 1.500");
    expect(fmtX("densidade", 12000)).toBe("12.000/km²");
    expect(fmtX("moradores_domicilio", 2.5)).toBe("2,50");
    expect(fmtX("pct_superior", 30)).toBe("30,00%");
    expect(fmtX("pct_superior", null)).toBe("—");
  });

  it("força da correlação e unidade da inclinação", () => {
    expect([0.05, -0.2, 0.4, -0.6, 0.9, null].map(forca)).toEqual(["desprezível", "fraca", "moderada", "forte", "muito forte", "desprezível"]);
    expect(unidadeDoX("voto")).toBe("p.p.");
    expect(unidadeDoX("renda_media")).toBe("R$");
    expect(unidadeDoX("densidade")).toBe("unidade");
    expect(unidadeDoX("pct_superior")).toBe("p.p.");
  });

  it("unidades de análise", () => {
    expect(nomeDaUnidade("area", false, true)).toBe("Área");
    expect(nomeDaUnidade("local")).toBe("locais");
    expect(ehUnidade("bairro")).toBe(true);
    expect(ehUnidade("setor")).toBe(false);
  });
});

describe("desenho do perfil", () => {
  const d: Dispersao = {
    pontos: [], rotulo_x: "x", rotulo_y: "y", ponderado: true, acima: [], abaixo: [],
    estatistica: { n: 92, n_efetivo: 7.4, pearson: 0.58, ic95: [0.4, 0.7], spearman: 0.5, p: 0.0001, r2: 0.3364, a: 1, b: 0.1234 },
  };

  it("fichas da correlação", () => {
    const t = fichasCorrelacao(d, "renda_media", "Bairros").map((f) => f.textContent);
    expect(t[0]).toBe("Bairros na análise92 (n efetivo 7)");
    expect(t[1]).toBe("Pearson r+0,58 (forte)");
    expect(t[4]).toBe("p-valor (r ≠ 0)< 0,001");
    expect(t[6]).toBe("Inclinação (+1 R$ no eixo X)+0,123 p.p.");
  });

  it("correlações: indicador atual marcado e clique escolhe", () => {
    const escolher = vi.fn();
    const tab = tabelaCorrelacoes([
      { indicador: "renda_media", rotulo: "Renda", pearson: 0.5, spearman: 0.4, ic95: null, n: 10, fonte: "IBGE (Censo)" },
      { indicador: "pct_mulheres", rotulo: "Mulheres", pearson: -0.1, spearman: null, ic95: [-0.3, 0.1], n: 10, fonte: "TSE" },
    ], "renda_media", "Bairros", escolher);
    expect(tab.querySelector("tr.selecionado")?.getAttribute("data-indicador")).toBe("renda_media");
    (tab.querySelectorAll("tbody tr")[1] as HTMLElement).click();
    expect(escolher).toHaveBeenCalledWith("pct_mulheres");
    expect(tab.querySelectorAll("tbody td")[5].textContent).toBe("IBGE");
  });

  it("resíduos com sinal e nome como texto", () => {
    const tab = tabelaResiduos([{ BAIRRO: "<b>Centro</b>", X: 1500, Y: 40, VALIDOS: 10, RESIDUO: -2.5 }], "renda_media", "Bairro");
    expect(tab.querySelector("tbody td")?.textContent).toBe("<b>Centro</b>");
    expect(tab.querySelectorAll("tbody td")[3].textContent).toBe("−2,50 p.p.");
  });

  it("regressão: sem indicador, com erro e com VIF alto", () => {
    expect(desenharRegressao(null, "Bairros").tabela.textContent).toBe("Marque ao menos um indicador.");
    expect(desenharRegressao({ erro: "colinear" }, "Bairros").tabela.textContent).toBe("Regressão indisponível: colinear");
    const r = desenharRegressao({ n: 50, r2: 0.4, r2_ajustado: 0.35, coeficientes: [{ indicador: "renda_media", rotulo: "Renda",
      efeito_pp_por_dp: 3.2, ic95: [1, 5.4], p: 0.01, vif: 6.25, r_simples: 0.5, dp_indicador: 800 }] }, "Bairros");
    expect(r.fichas).toHaveLength(3);
    expect(r.tabela.querySelector("tr.cad-disputa")).not.toBeNull();
    expect(r.tabela.querySelectorAll("tbody td")[4].textContent).toBe("6,3");
  });
});
