import { afterEach, describe, expect, it, vi } from "vitest";
import { el } from "../src/core/dom";
import { indiceDaTecla, ligarAbas, marcarAba } from "../src/pagina/abas";
import { dadosRegua, desenharRegua, horaCurta } from "../src/pagina/regua";
import type { Status } from "../src/pagina/situacao";
import { aplicarTema, CHAVE_TEMA, escolherTema, ligarSeletorTema } from "../src/pagina/tema";

afterEach(() => { delete document.documentElement.dataset.tema; localStorage.clear(); document.body.replaceChildren(); });

describe("tema", () => {
  it("o endereço vence a escolha gravada; valor desconhecido segue o sistema", () => {
    expect(escolherTema("escuro", "claro")).toBe("escuro");
    expect(escolherTema(null, "claro")).toBe("claro");
    expect(escolherTema(null, null)).toBeNull();
    expect(escolherTema("sistema", "escuro")).toBeNull();  // ?tema= explícito, mas inválido: o sistema
    expect(escolherTema(null, "roxo")).toBeNull();
  });
  it("data-tema no <html> só quando forçado", () => {
    aplicarTema("escuro");
    expect(document.documentElement.dataset.tema).toBe("escuro");
    aplicarTema(null);
    expect(document.documentElement.dataset.tema).toBeUndefined();
  });
  it("o seletor grava a escolha, aplica e recarrega", () => {
    const sel = el("select", {}, el("option", { value: "" }, "do sistema"), el("option", { value: "escuro" }, "escuro")) as HTMLSelectElement;
    const recarregar = vi.fn();
    ligarSeletorTema(sel, recarregar);
    expect(sel.value).toBe("");
    sel.value = "escuro";
    sel.dispatchEvent(new Event("change"));
    expect(localStorage.getItem(CHAVE_TEMA)).toBe("escuro");
    expect(document.documentElement.dataset.tema).toBe("escuro");
    expect(recarregar).toHaveBeenCalledOnce();
  });
});

describe("régua de apuração", () => {
  type Linha = Status["progresso"][number];
  const linha = (o: Partial<Linha>): Linha =>
    ({ ABRANGENCIA: "uf", UF: "RJ", ELEICAO: 1, PCT_SECOES_TOTALIZADAS: 50, DT_TOTALIZACAO: null, TOTALIZACAO_FINAL: false, ...o });

  it("menor % e hora mais recente das linhas da UF; o Brasil fica de fora", () => {
    const d = dadosRegua({ uf: "RJ", progresso: [
      linha({ ABRANGENCIA: "br", UF: "BR", PCT_SECOES_TOTALIZADAS: 10, DT_TOTALIZACAO: "2026-10-04T23:00:00" }),
      linha({ ELEICAO: 1, PCT_SECOES_TOTALIZADAS: 61.2, DT_TOTALIZACAO: "2026-10-04T20:10:00" }),
      linha({ ELEICAO: 2, PCT_SECOES_TOTALIZADAS: 60.4, DT_TOTALIZACAO: "2026-10-04T20:12:00" }),
    ] });
    expect(d).toEqual({ uf: "RJ", pct: 60.4, hora: "2026-10-04T20:12:00", final: false });
  });
  it("final só com todas as linhas finais; sem linha da UF não há régua", () => {
    expect(dadosRegua({ uf: "RJ", progresso: [linha({ TOTALIZACAO_FINAL: true }), linha({ TOTALIZACAO_FINAL: true })] })?.final).toBe(true);
    expect(dadosRegua({ uf: "RJ", progresso: [linha({ TOTALIZACAO_FINAL: true }), linha({})] })?.final).toBe(false);
    expect(dadosRegua({ uf: "RJ", progresso: [linha({ ABRANGENCIA: "br" })] })).toBeNull();
    expect(dadosRegua({ uf: "RJ", progresso: [linha({ PCT_SECOES_TOTALIZADAS: null })] })).toBeNull();
  });
  it("hora curta: só a hora no mesmo dia, com a data em outro", () => {
    expect(horaCurta("2026-10-04T22:22:21", new Date(2026, 9, 4, 23))).toBe("22:22");
    expect(horaCurta("2026-10-04T22:22:21", new Date(2026, 9, 5, 9))).toBe("04/10 22:22");
    expect(horaCurta("2023-09-08T13:18:00", new Date(2026, 9, 5, 9))).toBe("08/09/2023 13:18");
    expect(horaCurta("lixo")).toBe("lixo");
  });
  it("desenha o %, o trilho e o texto acessível; sem dados esconde os dois", () => {
    const raiz = el("div", { hidden: true });
    const trilho = el("div", { hidden: true }, el("div"));
    desenharRegua(raiz, trilho, { uf: "RJ", pct: 45.27, hora: null, final: false });
    expect(raiz.hidden || trilho.hidden).toBe(false);
    expect(raiz.querySelector(".regua-pct")?.textContent).toBe("45,3%");
    expect(raiz.querySelector(".regua-hora")).toBeNull();
    expect(raiz.getAttribute("aria-valuetext")).toBe("45,3% das seções totalizadas em RJ");
    expect((trilho.firstElementChild as HTMLElement).style.width).toBe("45.27%");
    desenharRegua(raiz, trilho, null);
    expect(raiz.hidden && trilho.hidden).toBe(true);
  });
});

describe("abas pelo teclado", () => {
  it("setas giram, Home/End vão às pontas, outra tecla não faz nada", () => {
    expect(indiceDaTecla("ArrowRight", 4, 5)).toBe(0);
    expect(indiceDaTecla("ArrowLeft", 0, 5)).toBe(4);
    expect(indiceDaTecla("Home", 3, 5)).toBe(0);
    expect(indiceDaTecla("End", 0, 5)).toBe(4);
    expect(indiceDaTecla("Enter", 0, 5)).toBeNull();
    expect(indiceDaTecla("ArrowRight", 0, 0)).toBeNull();
  });
  it("só a aba aberta entra no Tab; a seta pula a aba escondida e abre a seguinte", () => {
    const nav = el("nav", {},
      el("button", { role: "tab", "data-aba": "painel" }, "Painel"),
      el("button", { role: "tab", "data-aba": "comparacao", hidden: true }, "Comparação"),
      el("button", { role: "tab", "data-aba": "perfil" }, "Perfil"));
    document.body.append(nav);
    const abrir = vi.fn((aba) => marcarAba(nav, aba));
    ligarAbas(nav, abrir);
    marcarAba(nav, "painel");
    const [painel, , perfil] = [...nav.querySelectorAll("button")];
    expect([painel?.tabIndex, perfil?.tabIndex]).toEqual([0, -1]);
    painel?.focus();
    nav.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(abrir).toHaveBeenLastCalledWith("perfil");
    expect(document.activeElement).toBe(perfil);
    expect(perfil?.getAttribute("aria-selected")).toBe("true");
    painel?.click();
    expect(abrir).toHaveBeenLastCalledWith("painel");
  });
});
