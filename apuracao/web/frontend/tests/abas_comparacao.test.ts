import { describe, expect, it } from "vitest";
import { desenharBancadas } from "../src/abas/comparacao/bancadas";
import { anosBairros, escolhaInicial, rotuloEntidade, rotuloPartidoBairros } from "../src/abas/comparacao/formatos";
import type { Variacao } from "../src/abas/comparacao/tipos";
import { desenharVariacao, linhasPorMunicipio } from "../src/abas/comparacao/variacao";
import { fmtVariacao } from "../src/core/formatos";

describe("formatos da comparação", () => {
  it("variação com sinal em p.p. ou %; zero sem sinal", () => {
    expect(fmtVariacao(1.234, "pp")).toBe("+1,23 p.p.");
    expect(fmtVariacao(-12.5, "var_pct")).toBe("−12,50%");
    expect(fmtVariacao(0, "pp")).toBe("0,00 p.p.");
    expect(fmtVariacao(null, "pp")).toBe("—");
  });

  it("partido pela entidade: renomeado, só num ano, igual", () => {
    expect(rotuloEntidade({ PARTIDO: "PRD", NOS_DOIS: true, SIGLAS_A: "PTB + PATRIOTA" }, 2022, 2026)).toBe("PRD (PTB + PATRIOTA em 2022)");
    expect(rotuloEntidade({ PARTIDO: "MISSÃO", NOS_DOIS: false, VOTOS_A: 0 }, 2022, 2026)).toBe("MISSÃO (só 2026)");
    expect(rotuloEntidade({ PARTIDO: "PT", NOS_DOIS: true, SIGLA_A: "PT" }, 2022, 2026)).toBe("PT");
    expect(rotuloPartidoBairros({ PARTIDO: 65, NOS_DOIS: true, SIGLA_A: "PC do B", SIGLA_B: "PCDOB" }, 2022, 2024))
      .toBe("65 PCDOB (PC do B em 2022)");
    expect(rotuloPartidoBairros({ PARTIDO: 14, NOS_DOIS: false, VOTOS_A: 10, SIGLA_A: "PTB" }, 2022, 2026)).toBe("14 PTB (só 2022)");
  });

  it("anos da comparação por bairro: união ordenada, sem repetição", () => {
    expect(anosBairros(["2022", "2024"], [2024, 2026], 2026)).toEqual([2022, 2024, 2026]);
  });

  it("escolha inicial da variação: pedida > anterior > padrão do cargo > 2 primeiros nos dois anos", () => {
    const ps = [{ PARTIDO: "PL", NOS_DOIS: true }, { PARTIDO: "NOVO2026", NOS_DOIS: false }, { PARTIDO: "PT", NOS_DOIS: true },
      { PARTIDO: "PSB", NOS_DOIS: true }];
    expect(escolhaInicial(ps, "1", ["PSB"], ["PL"])).toEqual(["PSB"]);
    expect(escolhaInicial(ps, "1", null, ["PL"])).toEqual(["PL"]);
    expect(escolhaInicial(ps, "1", null, null)).toEqual(["PT", "PL"]);
    expect(escolhaInicial(ps, "3", null, null)).toEqual(["PL", "PT"]);
  });
});

describe("desenho da comparação", () => {
  it("bancadas: fichas, link da planilha e três tabelas", () => {
    const n = desenharBancadas({ ano: 2026, ano_ref: 2022, ds_cargo: "Deputado Estadual",
      resumo: { eleitos_antes: 70, eleitos_agora: 70, reeleito: 40, novato: 20, "já concorreu, sem se eleger": 5,
        "eleito antes para outro cargo": 5, nao_reeleitos: 30 },
      partidos: [{ PARTIDO: "PL", ANTES_COMO: "PL", ELEITOS_ANTES: 10, ELEITOS_AGORA: 13, VARIACAO: 3 }],
      eleitos: [{ NOME_URNA: "<b>X</b>", PARTIDO: "PL", VOTOS: 1000, TRAJETORIA: "reeleito", DETALHE: null }],
      sairam: [] }, "7");
    const raiz = document.createElement("div"); raiz.replaceChildren(...n);
    expect(raiz.querySelectorAll(".ficha")).toHaveLength(6);
    expect(raiz.querySelector("a.botao-salvar")?.getAttribute("href")).toBe("api/bancadas/planilha?cargo=7");
    expect(raiz.querySelectorAll("table")).toHaveLength(3);
    expect(raiz.textContent).toContain("+3");
    expect(raiz.querySelector("b")).toBeNull();
  });

  const variacao: Variacao = {
    ano_a: 2022, ano_b: 2026, ponderado: false,
    partidos: [{ partido: "PT", media: 1, ic_media: [0, 2], dp: 1.5, leitura: "subiu", uf: { A: 40, B: 42, DIF: 2 },
      reta: { a: 1, b: 1, ic_b: [0.9, 1.1], p_b1: 0.5, pearson: 0.9 },
      pontos: [{ CD_MUNICIPIO: 1, NM_MUNICIPIO: "A", A: 40, B: 42, DIF: 2, VALIDOS: 100 },
        { CD_MUNICIPIO: 2, NM_MUNICIPIO: "B", A: 30, B: 29, DIF: -1, VALIDOS: 50 }] }],
    butler: { de: "PT", para: "PL", uf: 1, media: 0.5, ic_media: [0, 1], pontos: [{ CD_MUNICIPIO: 1, NM_MUNICIPIO: "A", VALOR: 0.7 }] },
  };

  it("tabela por município junta partidos e Butler", () => {
    expect(linhasPorMunicipio(variacao)).toEqual([
      { NM_MUNICIPIO: "A", PT_A: 40, PT_B: 42, PT_DIF: 2, BUTLER: 0.7 },
      { NM_MUNICIPIO: "B", PT_A: 30, PT_B: 29, PT_DIF: -1 }]);
  });

  it("variação: fichas, leitura, dois gráficos e a tabela", () => {
    const raiz = document.createElement("div"); raiz.replaceChildren(...desenharVariacao(variacao));
    expect(raiz.querySelectorAll(".ficha")).toHaveLength(4);  // 3 do partido + Butler
    expect(raiz.querySelector(".var-leitura")?.textContent).toBe("PT: subiu");
    expect(raiz.querySelectorAll("svg")).toHaveLength(2);
    expect(raiz.querySelectorAll("table tbody tr")).toHaveLength(2);
  });
});
