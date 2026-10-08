import { afterEach, describe, expect, it, vi } from "vitest";
import { celulaHistorico, descCandidato, fichasCandidato, textoCadeira } from "../src/abas/candidato/desenhar";
import { criarCandidatos, resolverNaLista } from "../src/dados/candidatos";

afterEach(() => vi.unstubAllGlobals());

const lista = [{ NUMERO: 13713, NOME_URNA: "Ana Souza", PARTIDO: "PT" }, { NUMERO: 22, NOME_URNA: "Zé da Silva", PARTIDO: "PL" }];

describe("lista de candidatos", () => {
  it("resolve nº digitado ou parte do nome", () => {
    expect(resolverNaLista(lista, " 22 ")).toBe(22);
    expect(resolverNaLista(lista, "souza")).toBe(13713);
    expect(resolverNaLista(lista, "ninguém")).toBeNull();
  });

  it("um pedido por cargo; limpar pede de novo; falha não fica no cache", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify(lista)));
    vi.stubGlobal("fetch", f);
    const c = criarCandidatos();
    await Promise.all([c.lista("7"), c.lista("7")]);
    expect(f).toHaveBeenCalledTimes(1);
    c.limpar();
    await c.lista("7");
    expect(f).toHaveBeenCalledTimes(2);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
    await expect(c.lista("3")).rejects.toThrow();
    vi.stubGlobal("fetch", f);
    expect(await c.resolver("3", "zé")).toBe(22);  // o 503 não ficou guardado
  });

  it("datalist com nº e nome; sem dados, fica como está", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(lista))));
    const dl = document.createElement("datalist");
    await criarCandidatos().preencher("7", dl);
    expect([...dl.querySelectorAll("option")].map((o) => [o.value, o.textContent])).toEqual([
      ["13713", "Ana Souza (PT)"], ["22", "Zé da Silva (PL)"]]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    await criarCandidatos().preencher("7", dl);
    expect(dl.children).toHaveLength(2);
  });
});

describe("desenho do candidato", () => {
  it("texto da cadeira: projeção, eleito, suplente e voto não válido", () => {
    expect(textoCadeira({ projecao: { status: "consolidado", freq: 0.97, votos_proj: 45000, pct_apurado: 40 },
      situacao: "", margem: null, agremiacao: "" })).toBe("Consolidado · eleito em 97% das simulações · 45.000 votos projetados (40,00% apurado)");
    expect(textoCadeira({ situacao: "Eleito por QP", margem: 1200, agremiacao: "PT" }))
      .toBe("Eleito por QP · 1.200 votos à frente do 1º suplente de PT");
    expect(textoCadeira({ situacao: "Suplente", margem: 300, agremiacao: "PL", ordem: 2 }))
      .toBe("Suplente (2º de PL) · faltam 300 votos para passar o último eleito da agremiação");
    expect(textoCadeira({ situacao: "Suplente", margem: null, agremiacao: "PL" })).toBe("Suplente · PL sem cadeira na projeção");
    expect(textoCadeira({ situacao: "Anulado", margem: null, agremiacao: "X" })).toBe("Anulado (votos não válidos para a vaga)");
  });

  it("fichas: destinação e Brasil só quando há; nome com HTML como texto", () => {
    const f = fichasCandidato({ candidato: { NUMERO: 1, NOME_URNA: "<b>X</b>", PARTIDO: "P", VOTOS: 10, PCT_VALIDOS: 1,
      DESTINACAO: "Válido" }, posicao_uf: 2, n_candidatos_uf: 10, municipios: [] }, "RJ");
    expect(f.querySelectorAll(".ficha")).toHaveLength(6);
    expect(f.querySelector("b")).toBeNull();
    expect(f.textContent).toContain("Votos (RJ)10");
  });

  it("células do histórico", () => {
    expect(celulaHistorico("VAR_VOTOS_PCT", 12.5)).toBe("+12,50%");
    expect(celulaHistorico("VAR_PCT_VALIDOS_PP", -1)).toBe("−1,00 p.p.");
    expect(celulaHistorico("VOTOS_2022", 1234)).toBe("1.234");
    expect(celulaHistorico("POSICAO_2026", null)).toBe("—");
    expect(celulaHistorico("POSICAO_2026", 3)).toBe("3º");
    expect(celulaHistorico("PCT_VALIDOS_2022", 4)).toBe("4,00%");
    expect(descCandidato({ NUMERO: 1, NOME_URNA: "A", PARTIDO: "P", CARGO: 7, VOTOS: 0, PCT_VALIDOS: null })).toBe("1 — A · P · 7");
  });
});
