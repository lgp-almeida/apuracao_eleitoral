import { describe, expect, it, vi } from "vitest";
import { Roteador, type Ambiente } from "../src/core/roteador";
import type { Aba } from "../src/core/rotas";

function montar(hashInicial = "", abaInicial: Aba = "painel") {
  let hash = hashInicial;
  let aba: string = abaInicial;
  const substituicoes: string[] = [];
  const ambiente: Ambiente = { local: () => hash, substituir: (h) => { hash = h; substituicoes.push(h); } };
  const mostrar = vi.fn((a: Aba) => { aba = a; });
  const r = new Roteador(mostrar, () => aba, ambiente);
  return { r, mostrar, substituicoes, hash: () => hash, irPara: (a: Aba) => { aba = a; } };
}

describe("Roteador.abrir", () => {
  it("com parâmetros, aplica; sem parâmetros (ou sem aplicar), só mostra", () => {
    const { r, mostrar } = montar();
    const aplicar = vi.fn();
    r.registrar("mapas", { aplicar });
    r.abrir("#mapas?cargo=3");
    expect(aplicar).toHaveBeenCalledOnce();
    expect(aplicar.mock.calls[0][0].get("cargo")).toBe("3");
    expect(mostrar).not.toHaveBeenCalled();
    r.abrir("#mapas");
    r.abrir("#perfil?ano=2022");  // perfil sem aplicar registrado
    expect(mostrar.mock.calls.map((c) => c[0])).toEqual(["mapas", "perfil"]);
  });

  it("formato antigo do candidato chega como parâmetros", () => {
    const { r } = montar();
    const aplicar = vi.fn();
    r.registrar("candidato", { aplicar });
    r.abrir("#candidato/7/13713");
    expect(Object.fromEntries(aplicar.mock.calls[0][0])).toEqual({ cargo: "7", numero: "13713" });
  });

  it("endereço sem aba conhecida não faz nada", () => {
    const { r, mostrar } = montar();
    r.abrir("#nada?x=1"); r.abrir("");
    expect(mostrar).not.toHaveBeenCalled();
  });
});

describe("Roteador.gravar / endereco", () => {
  it("regrava só a aba aberta, só quando muda, com o estado da aba", () => {
    const { r, substituicoes, irPara } = montar("#mapas", "mapas");
    let cargo = "3";
    r.registrar("mapas", { escrever: () => new URLSearchParams({ cargo }) });
    r.gravar("mapas");
    r.gravar("mapas");  // igual: não regrava
    cargo = "7"; irPara("painel");
    r.gravar("mapas");  // aba fechada: não regrava
    expect(substituicoes).toEqual(["#mapas?cargo=3"]);
    expect(r.endereco("mapas")).toBe("#mapas?cargo=7");
    expect(r.endereco("perfil")).toBe("#perfil");
  });

  it("registrar duas vezes a mesma aba é erro", () => {
    const { r } = montar();
    r.registrar("painel", {});
    expect(() => r.registrar("painel", {})).toThrow("painel");
  });
});

describe("Roteador.aoMostrar", () => {
  it("outra aba no endereço vira '#aba' (ou o endereço completo, se a aba pedir)", () => {
    const { r, substituicoes } = montar("#mapas?cargo=3");
    r.registrar("painel", { escrever: () => new URLSearchParams({ destacar: "PT" }), enderecoAoMostrar: true });
    r.aoMostrar("perfil");
    expect(substituicoes).toEqual(["#perfil"]);
    r.aoMostrar("painel");
    expect(substituicoes).toEqual(["#perfil", "#painel?destacar=PT"]);
  });

  it("mesma aba ou endereço vazio: só o painel com estado regrava", () => {
    const { r, substituicoes } = montar("");
    let destacar = "";
    r.registrar("painel", { escrever: () => new URLSearchParams(destacar ? { destacar } : {}), enderecoAoMostrar: true });
    r.aoMostrar("mapas");
    r.aoMostrar("painel");
    expect(substituicoes).toEqual([]);
    destacar = "PL";
    r.aoMostrar("painel");
    expect(substituicoes).toEqual(["#painel?destacar=PL"]);
  });
});
