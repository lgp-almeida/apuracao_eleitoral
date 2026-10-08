import { describe, expect, it } from "vitest";
import { comDica } from "../src/componentes/dica";
import { svgAutonomo } from "../src/componentes/exportar";
import { graficoDispersao, marcaX, retaNoQuadro } from "../src/componentes/grafico/dispersao";
import { faixaY, graficoLinhas, maisPerto } from "../src/componentes/grafico/linhas";
import { espalhar, graficoSwing, graficoVariacao } from "../src/componentes/grafico/variacao";
import { formatoLocais, raioDoLocal } from "../src/componentes/mapa/camadas";
import { svg } from "../src/core/dom";

describe("auxiliares puros", () => {
  it("maisPerto e faixa do eixo y", () => {
    expect(maisPerto([0, 10, 20], 14)).toBe(1);
    expect(maisPerto([0, 10, 20], 16)).toBe(2);
    expect(faixaY([40, null, 60])).toEqual([37.6, 62.4]);
    expect(faixaY([0, 100])).toEqual([0, 100]);  // dentro de 0–100
    expect(faixaY([50, 50])).toEqual([49.5, 50.5]);  // folga mínima de 0,5
  });

  it("marcas do eixo x pelo tipo do indicador", () => {
    expect(marcaX("renda_media", 1500)).toBe("R$ 1.500");
    expect(marcaX("densidade", 12000)).toBe("12.000");
    expect(marcaX("moradores_domicilio", 2.5)).toBe("2,5");
    expect(marcaX("pct_superior", 30)).toBe("30%");
  });

  it("reta cortada ao quadro", () => {
    expect(retaNoQuadro(0, 1, [0, 10], [0, 5])).toEqual([0, 5]);
    expect(retaNoQuadro(50, 0, [0, 10], [0, 100])).toEqual([0, 10]);
    expect(retaNoQuadro(200, 1, [0, 10], [0, 100])).toBeNull();
  });

  it("espalhamento determinístico e limitado", () => {
    const ys = Array.from({ length: 50 }, (_, k) => espalhar(k));
    expect(Math.max(...ys.map(Math.abs))).toBeLessThanOrEqual(11 * 1.3 + 1e-9);
    expect(espalhar(7)).toBe(espalhar(7));
  });

  it("formato e raio dos locais", () => {
    expect(formatoLocais({ unidade: "p.p.", itens: [] })(-1.25)).toBe("−1,3 p.p.");
    expect(formatoLocais({ unidade: "%", itens: [{ valor: 0.5 }] as never })(0.123)).toBe("0,123%");
    expect(formatoLocais({ unidade: "%", itens: [{ valor: 50 }] as never })(12.34)).toBe("12,3%");
    expect(formatoLocais({ itens: [] })(1234.4)).toBe("1.234");
    expect(raioDoLocal(undefined)).toBe(2.5);
    expect(raioDoLocal(1e9)).toBe(12);
  });
});

describe("gráficos montados", () => {
  it("linhas: uma polilinha por série, rótulo na ponta = último valor existente, legenda e botões", () => {
    const n = graficoLinhas({
      xs: [0, 50, 100], xMin: 0, xMax: 100, xTicks: [0, 50, 100], xFmt: (t) => `${t}%`,
      series: [{ nome: "A", rotulo: "A (X)", valores: [10, 20, null] }, { nome: "B", rotulo: "B", valores: [30, 25, 28] }],
      dica: () => "t",
    });
    expect(n.querySelectorAll("polyline")).toHaveLength(2);
    const rotulos = [...n.querySelectorAll("text.rotulo")].map((t) => t.textContent);
    expect(rotulos.sort()).toEqual(["20,00%", "28,00%"]);
    expect(n.querySelector(".legenda-linha")?.textContent).toBe("A (X)B");
    expect([...n.querySelectorAll(".baixar-serie button")].map((b) => b.textContent)).toEqual(["SVG", "PNG"]);
  });

  it("dispersão, variação e swing: um círculo por ponto; texto dos dados como texto", () => {
    const nome = '<b>"Zé" & cia</b>';
    const disp = graficoDispersao({ pontos: [{ X: 1, Y: 10, BAIRRO: nome, VALIDOS: 5, RESIDUO: 1 },
      { X: 2, Y: 20, BAIRRO: "B", VALIDOS: 5, RESIDUO: -1 }], rotulo_x: "x", rotulo_y: "y", estatistica: { a: 0, b: 10 } },
    "pct", String, "Bairro");
    expect(disp.querySelectorAll("circle.ponto")).toHaveLength(2);
    expect(disp.querySelector("line.tendencia")).not.toBeNull();
    expect(disp.querySelector("b")).toBeNull();
    const serie = { partido: "PT", cor: "red", reta: { a: 0, b: 1 }, media: 1, ic_media: [0, 2] as [number, number],
      pontos: [{ A: 10, B: 12, DIF: 2, VALIDOS: 100, NM_MUNICIPIO: nome, DESTAQUE: true },
        { A: 20, B: 19, DIF: -1, VALIDOS: 50, NM_MUNICIPIO: "Y" }] };
    const d = { ano_a: 2022, ano_b: 2026, butler: null };
    expect(graficoVariacao(d, [serie], String).querySelectorAll("circle.ponto")).toHaveLength(2);
    const sw = graficoSwing(d, [serie], String);
    expect(sw.querySelectorAll("circle.ponto")).toHaveLength(2);
    expect(sw.querySelector("text.rotulo-mun")?.textContent).toBe(nome);  // destaque rotulado, como texto
  });
});

describe("exportar e dica", () => {
  it("SVG autônomo: sem camada de interação, com fundo e legenda dentro", () => {
    const g = svg("svg", { viewBox: "0 0 100 50" }, svg("line", { class: "guia" }), svg("rect", { class: "alvo" }),
      svg("polyline", { points: "0,0 10,10" }));
    const texto = svgAutonomo(g, [["#f00", "Série A"], ["#00f", "Série B"]]);
    expect(texto).toContain('viewBox="0 0 100 90"');  // 50 + 8 + 16 × 2
    expect(texto).toContain("Série A");
    expect(texto).not.toContain("guia");
    expect((texto.match(/<rect/g) ?? []).length).toBe(3);  // fundo + 2 amostras (o alvo saiu)
  });

  it("comDica: caixa com o gráfico e a dica escondida", () => {
    const g = svg("svg", { viewBox: "0 0 10 10" });
    const caixa = comDica(g, 10, 10, []);
    expect(caixa.className).toBe("serie-caixa");
    expect((caixa.querySelector(".dica") as HTMLElement).hidden).toBe(true);
  });
});
