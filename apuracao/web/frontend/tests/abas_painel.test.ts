import { afterEach, describe, expect, it, vi } from "vitest";
import { blocoCadeiras } from "../src/abas/painel/cadeiras";
import { blocoSerie, cartao, composicao, destinacao } from "../src/abas/painel/cartao";
import { agremiacoesDestacadas, composicoes, destacado } from "../src/abas/painel/destaque";
import { dicaUf } from "../src/abas/painel/brasil";
import { posicao, topoDoTrilho } from "../src/abas/painel/projecao";
import type { Cadeiras, Cartao, UfPresidente } from "../src/abas/painel/tipos";
import { cartaoDaVez } from "../src/abas/painel/tv";
import { tituloMudancas } from "../src/abas/painel/mudancas";
import { cartaoAlerta, maisGrave, notasDoSom, tituloComAlertas } from "../src/alertas/apresentacao";
import { itensProgresso, limitarCargos } from "../src/pagina/situacao";
import { el } from "../src/core/dom";
import { metadados } from "../src/componentes/metadados";

afterEach(() => vi.unstubAllGlobals());

describe("destaque", () => {
  const dest = new Set(["PT", "FED"]);
  it("candidato destacado pelo partido ou pela agremiação", () => {
    expect(destacado(dest, { PARTIDO: "PT", AGREMIACAO: "X" })).toBe(true);
    expect(destacado(dest, { PARTIDO: "PV", AGREMIACAO: "FED" })).toBe(true);
    expect(destacado(dest, { PARTIDO: "PL", AGREMIACAO: "PL" })).toBe(false);
  });
  it("agremiação destacada pela própria ou por um partido dela; composições sem repetir", () => {
    const k = { composicao: [{ AGREMIACAO: "FED PT/PV", PARTIDOS: ["PT", "PV"] }, { AGREMIACAO: "PL", PARTIDOS: ["PL"] }] };
    expect([...agremiacoesDestacadas(new Set(["PV"]), k)]).toEqual(["FED PT/PV"]);
    const c = { cadeiras: k } as unknown as Cartao;
    expect([...composicoes([c, c]).keys()]).toEqual(["FED PT/PV", "PL"]);
  });
});

describe("cartão", () => {
  const base: Cartao = {
    cargo: 3, ds_cargo: "Governador", abrangencia: "RJ", proporcional: false, n_candidatos: 2,
    totais: { ELEITORADO: 100, COMPARECIMENTO: 80, ABSTENCAO: 20, VALIDOS: 70, BRANCOS: 5, NULOS: 5,
      PCT_SECOES_TOTALIZADAS: 50, SECOES_TOTALIZADAS: 5, SECOES_TOTAL: 10, DT_TOTALIZACAO: null },
    candidatos: [{ NUMERO: 22, NOME_URNA: '<b>"Zé"</b>', PARTIDO: "PL", VOTOS: 40, PCT_VALIDOS: 57.1, ELEITO: true, DESTINACAO: "Anulado sub judice" },
      { NUMERO: 13, NOME_URNA: "Ana", PARTIDO: "PT", VOTOS: 30, PCT_VALIDOS: 42.9 }],
  };
  const ctx = { destacar: new Set<string>(), abertos: new Set<number>(), consultarCandidato: vi.fn(), blocoBrasil: () => document.createElement("div") };

  it("composições, lista de candidatos e duplo clique", () => {
    const n = cartao(base, ctx);
    expect(n.querySelectorAll(".composicao")).toHaveLength(2);
    expect(n.querySelectorAll(".lista .item")).toHaveLength(2);
    expect(n.querySelector("b")).toBeNull();
    expect(n.querySelector(".item.destaque .sit")?.textContent).toBe(" · Anulado sub judice");
    n.querySelector(".item")?.dispatchEvent(new MouseEvent("dblclick"));
    expect(ctx.consultarCandidato).toHaveBeenCalledWith(3, 22);
    expect(n.textContent).toContain("A série aparece a partir da 2ª totalização (0 registradas até agora).");
  });

  it("bloco Brasil só no Presidente — BRASIL", () => {
    const bloco = document.createElement("div"); bloco.className = "brasil-ufs";
    const n = cartao({ ...base, cargo: 1, abrangencia: "BRASIL" }, { ...ctx, blocoBrasil: () => bloco });
    expect(n.querySelector(".brasil-ufs")).toBe(bloco);
  });

  it("auxiliares", () => {
    expect(destinacao({ DESTINACAO: "Válido" })).toBe("");
    const [barra, leg] = composicao([{ rotulo: "A", valor: 1, cor: "red" }, { rotulo: "B", valor: 0, cor: "blue" }], 1);
    expect(barra.children).toHaveLength(1);  // segmento zero não vira barra, mas fica na legenda
    expect(leg.textContent).toBe("A 1 (100,00%)B 0 (0,00%)");
    expect(blocoSerie(null, true)[0].textContent).toContain("3 partidos");
  });
});

describe("cadeiras e projeção", () => {
  const k: Cadeiras = { cargo: 7, vagas: 70, consistente: false, soma_agremiacoes: 99, validos: 100, final: true, qe: 1000,
    eleitos_qp: 60, eleitos_media: 10, fonte: "TSE", composicao: [{ AGREMIACAO: "PL", PARTIDOS: ["PL"] }],
    agremiacoes: [{ NOME: "PL", AGREMIACAO: "PL", VOTOS: 10, PCT_QE: 10, VAGAS: 2, VAGAS_QP: 1, VAGAS_MEDIA: 1 }] };

  it("barra por agremiação, destaque, aviso de inconsistência e link da planilha com o destaque", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ eleitos: [] }))));  // a lista aberta carrega
    const n = blocoCadeiras(k, { destacar: new Set(["PL"]), abertos: new Set([7]) });
    const raiz = document.createElement("div"); raiz.replaceChildren(...n);
    expect(raiz.querySelector(".cad-item.destaque")).not.toBeNull();
    expect(raiz.querySelector(".aviso")?.textContent).toContain("não somam os válidos");
    expect(raiz.querySelector("a.botao-salvar")?.getAttribute("href")).toBe("api/cadeiras/planilha?cargo=7&destacar=PL");
    expect((raiz.querySelector("details") as HTMLDetailsElement).open).toBe(true);  // estava aberta antes do redesenho
  });

  it("trilho da projeção", () => {
    expect(topoDoTrilho({ cargo: 3, candidatos: [{ MAX: 40 } as never] })).toBeCloseTo(54.6);
    expect(topoDoTrilho({ cargo: 1, candidatos: [{ MAX: 40 } as never] })).toBeCloseTo(42);
    expect(posicao(50, 100)).toBe("50%");
    expect(posicao(200, 100)).toBe("100%");
    expect(posicao(null, 100)).toBe("0%");
  });
});

describe("Brasil, TV, mudanças", () => {
  it("dica da UF: sem dado, sem apuração e completa", () => {
    expect(dicaUf(undefined, "35", () => "").textContent).toBe("35sem dado");
    const u = { uf: "SP", nome: "São Paulo", pct_secoes: 50, primeiro: null } as unknown as UfPresidente;
    expect(dicaUf(u, "35", () => "").textContent).toContain("sem apuração");
    const c = { ...u, primeiro: { numero: 13, nome: "A", pct: 50 }, candidatos: [{ numero: 13, nome: "A", pct: 50, votos: 10 }],
      pct_brancos: 1, brancos: 1, pct_nulos: 1, nulos: 1, pct_abstencao: 20, abstencao: 5 } as unknown as UfPresidente;
    const d = dicaUf(c, "35", () => "lidera: 13 A");
    expect(d.querySelectorAll("tbody tr")).toHaveLength(4);
    expect(d.querySelector("tr.lider")?.textContent).toContain("13 A");
  });

  it("cartão da vez dá a volta; título das mudanças", () => {
    expect([0, 4, 5, 11].map((i) => cartaoDaVez(i, 5))).toEqual([0, 4, 0, 1]);
    expect(cartaoDaVez(3, 0)).toBe(0);
    expect(tituloMudancas({ titulo: "Boletim das 20h", gerado_em: "2026-10-04T20:00:00" }))
      .toMatch(/^O que mudou desde o boletim das 20h \(20:00\)$/);
  });
});

describe("alertas e cabeçalho", () => {
  it("nível mais grave, notas do som e título da aba", () => {
    expect(maisGrave(["ok", "aviso", "noticia"])).toBe("aviso");
    expect(maisGrave([])).toBeUndefined();
    expect(notasDoSom("critico")).toHaveLength(4);
    expect(tituloComAlertas("⚠ (3) Apuração 2026 — RJ", false, 0)).toBe("Apuração 2026 — RJ");
    expect(tituloComAlertas("Apuração 2026 — RJ", true, 2)).toBe("⚠ (2) Apuração 2026 — RJ");
  });

  it("cartão do alerta: ícone, rótulo com a hora e texto do servidor como texto", () => {
    const fechar = vi.fn();
    const n = cartaoAlerta({ nivel: "critico", titulo: "<b>Coletor parado</b>", momento: "2026-10-04T19:42:10" }, fechar);
    expect(n.querySelector(".rotulo")?.textContent).toBe("Crítico · 19:42");
    expect(n.querySelector("b")).toBeNull();
    (n.querySelector("button.fechar") as HTMLElement).click();
    expect(fechar).toHaveBeenCalled();
  });

  it("progresso do status e cargos limitados aos dos dados", () => {
    expect(itensProgresso({ progresso: [{ ABRANGENCIA: "uf", UF: "RJ", ELEICAO: 6257, PCT_SECOES_TOTALIZADAS: 45 },
      { ABRANGENCIA: "br", UF: "BR", ELEICAO: 6259, PCT_SECOES_TOTALIZADAS: 100, TOTALIZACAO_FINAL: true }] }))
      .toEqual(["RJ (eleição 6257): 45,00% das seções", "Brasil (eleição 6259): 100,00% das seções — final"]);
    const sel = document.createElement("select");
    for (const v of ["1", "3", "7"]) sel.append(el("option", { value: v }, v));
    sel.value = "3";
    const mudou = vi.fn(); sel.addEventListener("change", mudou);
    limitarCargos([1], [sel]);
    expect([...sel.options].map((o) => o.disabled)).toEqual([false, true, true]);
    expect(sel.value).toBe("1");
    expect(mudou).toHaveBeenCalled();
  });
});

describe("metadados", () => {
  it("um elemento por item, sem separador; itens vazios saem", () => {
    const n = metadados("Seções 45,00%", false, null, "", "totalização 21:34", 2);
    expect(n.className).toBe("sub metadados");
    expect([...n.children].map((c) => c.textContent)).toEqual(["Seções 45,00%", "totalização 21:34", "2"]);
    expect(n.textContent).not.toContain("·");
  });
  it("cartão: seções, hora, FINAL e vagas como itens", () => {
    const c = { cargo: 7, ds_cargo: "Deputado Estadual", abrangencia: "RJ", proporcional: true, n_candidatos: 0,
      totais: { PCT_SECOES_TOTALIZADAS: 100, SECOES_TOTALIZADAS: 10, SECOES_TOTAL: 10, DT_TOTALIZACAO: null, TOTALIZACAO_FINAL: true, VAGAS: 70 },
      candidatos: [] } as unknown as Cartao;
    const n = cartao(c, { destacar: new Set(), abertos: new Set(), consultarCandidato: vi.fn(), blocoBrasil: () => el("div") });
    expect([...(n.querySelector(".metadados")?.children ?? [])].map((x) => x.textContent))
      .toEqual(["Seções totalizadas 100,00% (10 de 10)", "totalização —", "FINAL", "70 vagas"]);
  });
});
