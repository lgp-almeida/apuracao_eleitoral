import { describe, expect, it, vi } from "vitest";
import { ficha, ordemInicial, ordenar, tabelaOrdenavel } from "../src/componentes/tabela";

type Linha = { NOME: string; VOTOS: number | null };
const linhas: Linha[] = [{ NOME: "Ângela", VOTOS: 10 }, { NOME: "bruno", VOTOS: 30 }, { NOME: "Zé", VOTOS: null }];
const colunas = [["Nome", "NOME"], ["Votos", "VOTOS", true]] as const;

describe("ordenação", () => {
  it("ordem inicial do endereço, ou 2ª coluna decrescente", () => {
    expect(ordemInicial(colunas, "NOME-asc")).toEqual({ k: "NOME", desc: false });
    expect(ordemInicial(colunas, "XYZ-asc")).toEqual({ k: "VOTOS", desc: true });
    expect(ordemInicial(colunas, null)).toEqual({ k: "VOTOS", desc: true });
  });

  it("texto em pt-BR (acento e caixa) e números como números", () => {
    expect(ordenar(linhas, { k: "NOME", desc: false }).map((l) => l.NOME)).toEqual(["Ângela", "bruno", "Zé"]);
    expect(ordenar([{ V: 10 }, { V: 9 }, { V: 100 }], { k: "V", desc: true }).map((l) => l.V)).toEqual([100, 10, 9]);
  });
});

describe("tabelaOrdenavel", () => {
  it("clique no cabeçalho alterna a ordem e avisa", () => {
    const aoOrdenar = vi.fn();
    const t = tabelaOrdenavel(colunas, linhas, (r, k) => String(r[k] ?? "—"), null, { ordem: "NOME-asc", aoOrdenar });
    const primeira = () => t.querySelector("tbody tr td")?.textContent;
    expect(primeira()).toBe("Ângela");
    t.querySelectorAll("th")[0].click();
    expect(primeira()).toBe("Zé");
    expect(aoOrdenar).toHaveBeenLastCalledWith("NOME-desc");
    t.querySelectorAll("th")[1].click();
    expect(aoOrdenar).toHaveBeenLastCalledWith("VOTOS-desc");
    expect(t.querySelectorAll("td.num")).toHaveLength(3);
  });

  it("linha clicável chama aoClicar com a linha", () => {
    const aoClicar = vi.fn();
    const t = tabelaOrdenavel(colunas, linhas, (r, k) => String(r[k]), aoClicar);
    (t.querySelector("tbody tr") as HTMLElement).click();
    expect(aoClicar).toHaveBeenCalledWith(linhas[1]);  // 2ª coluna decrescente: 30 votos primeiro
  });

  it("ficha: rótulo e valor", () => {
    expect(ficha("Votos", "1.234").textContent).toBe("Votos1.234");
  });
});
