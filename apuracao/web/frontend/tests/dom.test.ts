import { describe, expect, it, vi } from "vitest";
import { el, ref, refs, svg, SVG } from "../src/core/dom";

describe("el", () => {
  it("texto entra como texto, nunca como HTML", () => {
    const nome = '<img src=x onerror="alert(1)"> "Zé" & cia';
    const n = el("td", {}, nome);
    expect(n.textContent).toBe(nome);
    expect(n.querySelector("img")).toBeNull();
  });

  it("atributos: omite null/undefined/false, true vira vazio, class e números", () => {
    const n = el("input", { class: "a b", disabled: true, hidden: false, title: null, "data-x": 3 });
    expect(n.className).toBe("a b");
    expect(n.getAttribute("disabled")).toBe("");
    expect(n.hasAttribute("hidden")).toBe(false);
    expect(n.hasAttribute("title")).toBe(false);
    expect(n.getAttribute("data-x")).toBe("3");
  });

  it("estilo aceita propriedade personalizada", () => {
    const n = el("div", { style: { "--cor": "red", width: "10px" } });
    expect(n.style.getPropertyValue("--cor")).toBe("red");
    expect(n.style.width).toBe("10px");
  });

  it("on… vira ouvinte", () => {
    const f = vi.fn();
    el("button", { onclick: f }).click();
    expect(f).toHaveBeenCalledOnce();
  });

  it("filhos: listas achatadas, nulos ignorados, 0 mantido", () => {
    const n = el("p", {}, ["a", null, ["b", false, 0]], undefined, el("b", {}, "c"));
    expect(n.textContent).toBe("ab0c");
  });
});

describe("svg", () => {
  it("cria no espaço de nomes do SVG e ignora filhos nulos", () => {
    const n = svg("g", { "stroke-width": 2 }, svg("text", {}, "x"), null);
    expect(n.namespaceURI).toBe(SVG);
    expect(n.getAttribute("stroke-width")).toBe("2");
    expect(n.textContent).toBe("x");
  });
});

describe("ref/refs", () => {
  it("devolvem os elementos e listam todos os ausentes", () => {
    document.body.replaceChildren(el("div", { id: "a" }), el("span", { id: "b" }));
    expect(ref("#a").id).toBe("a");
    const r = refs({ a: "#a", b: "#b" });
    expect(r.b.tagName).toBe("SPAN");
    expect(() => refs({ a: "#a", x: "#x", y: "#y" })).toThrow("#x, #y");
    expect(() => ref("#z")).toThrow("#z");
  });
});
