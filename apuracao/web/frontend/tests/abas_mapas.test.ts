import { afterEach, describe, expect, it, vi } from "vitest";
import { indiceAte, LinhaDoTempo, rotuloMomento } from "../src/abas/mapas/linha-tempo";
import { notaAreas, notaBairros, notaLinhaDoTempo, notaLocais } from "../src/abas/mapas/notas";
import { consultaCamada, controles, metricaPadrao, metricasPermitidas, METRICAS_BAIRRO, METRICAS_VARIACAO } from "../src/abas/mapas/regras";
import type { MapaAreas, MapaLocais } from "../src/abas/mapas/tipos";
import { corpoExportacao } from "../src/componentes/mapa/exportar";
import { enquadrarUmaVez } from "../src/componentes/mapa/criar";
import type { MapaApuracao } from "../src/componentes/mapa/tipos";
import { criarMalhas } from "../src/dados/malhas";
import * as L from "leaflet";

afterEach(() => vi.unstubAllGlobals());

describe("regras dos controles", () => {
  it("métricas por detalhe e camada", () => {
    expect(metricasPermitidas("municipios", "voto")).toBeNull();
    expect(metricasPermitidas("bairros", "voto")).toBe(METRICAS_BAIRRO);
    expect(metricasPermitidas("locais", "variacao")).toBe(METRICAS_VARIACAO);
    expect(metricaPadrao("variacao")).toBe("pct_candidato");
    expect(metricaPadrao("perfil")).toBe("vencedor");
  });

  it("campos visíveis e o nº do candidato", () => {
    const mun = controles("municipios", "voto", "pct_candidato");
    expect([mun.camada, mun.metrica, mun.numero, mun.placeholder]).toEqual([false, true, true, "número"]);
    expect(controles("municipios", "voto", "vencedor").numero).toBe(false);
    const perfil = controles("locais", "perfil", "vencedor");
    expect([perfil.indicador, perfil.metrica, perfil.numero, perfil.transf]).toEqual([true, false, false, false]);
    const res = controles("areas", "residuo", "vencedor");
    expect([res.indicador, res.numero, res.placeholder]).toEqual([true, true, "número (2 dígitos = partido)"]);
    const tr = controles("locais", "transferencia", "vencedor");
    expect([tr.transf, tr.indicador, tr.metrica]).toEqual([true, false, false]);
    expect(controles("locais", "variacao", "pct_candidato").placeholder).toBe("número (vale o partido)");
  });

  it("consulta da camada ou o que falta", () => {
    const base = { ano: "2022", cargo: "3", turno: 1, metrica: "pct_candidato", numero: "", indicador: "renda_media",
      transf: "elim_para_a", municipio: "" };
    expect(consultaCamada({ ...base, camada: "voto" })).toEqual({ falta: "Informe o número de um candidato." });
    expect(consultaCamada({ ...base, camada: "variacao" })).toEqual({ falta: "Informe o número de um candidato ou partido (vale o partido)." });
    expect(String(consultaCamada({ ...base, camada: "voto", numero: " 22 " })))
      .toBe("ano=2022&camada=voto&cargo=3&turno=1&metrica=pct_candidato&numero=22");
    expect(String(consultaCamada({ ...base, camada: "transferencia", municipio: "3304557" })))
      .toBe("ano=2022&camada=transferencia&cargo=3&turno=2&metrica=elim_para_a&municipio=3304557");
    expect(String(consultaCamada({ ...base, camada: "perfil" }))).toBe("ano=2022&camada=perfil&cargo=3&turno=1&indicador=renda_media");
    expect(consultaCamada({ ...base, camada: "residuo" })).toHaveProperty("falta");
  });
});

describe("linha do tempo", () => {
  const ms = ["2026-10-04T17:00:00", "2026-10-04T17:10:00", "2026-10-04T17:30:00"];

  it("índice do último momento até a hora pedida", () => {
    expect(indiceAte(ms, "2026-10-04T17:20:00")).toBe(1);
    expect(indiceAte(ms, "2026-10-04T16:00:00")).toBe(0);
    expect(indiceAte(ms, "2026-10-05T00:00:00")).toBe(2);
  });

  it("acompanha o fim; o pedido do endereço vira índice uma vez", () => {
    const lt = new LinhaDoTempo();
    lt.irParaOFim();
    lt.receber(ms.slice(0, 2));
    expect(lt.idx).toBe(1);
    lt.receber(ms);  // chegou totalização nova: quem estava no fim continua no fim
    expect([lt.idx, lt.noFim, lt.noPassado]).toEqual([2, true, false]);
    lt.idx = 0;
    lt.receber(ms);  // vendo o passado: não é atropelado
    expect([lt.idx, lt.noPassado, lt.atual]).toEqual([0, true, ms[0]]);
    lt.pedido = "2026-10-04T17:15:00";
    lt.receber(ms);
    expect([lt.idx, lt.pedido]).toEqual([1, null]);
  });

  it("rótulo e nota", () => {
    expect(rotuloMomento(ms, 2)).toMatch(/\(mais recente\) · totalização 3 de 3$/);
    expect(rotuloMomento(ms, 0)).toMatch(/[^)] · totalização 1 de 3$/);
    expect(notaLinhaDoTempo(1)).toContain("(1 registrada para este cargo)");
    expect(notaLinhaDoTempo(0)).toContain("(0 registradas");
  });
});

describe("notas sob o mapa", () => {
  it("bairros, locais (com reta e variação) e áreas (amostra com CV)", () => {
    expect(notaBairros({ rotulo: "", itens: {}, cobertura: { bairros: 160, bairros_com_dado: 150, locais_em_bairro: 1200 } }))
      .toMatch(/^Bairros do IBGE \(Censo 2022\): 150 de 160 bairros têm local de votação \(1\.200 locais\)/);
    const loc: MapaLocais = { rotulo: "", itens: [], ano: 2022, ano_ref: 2018, min_validos: 100,
      cobertura: { locais: 10, com_valor: 9 }, estatistica: { pearson: 0.5, r2: 0.25, n: 8 } };
    const t = notaLocais(loc, "residuo");
    expect(t).toContain("r = 0,50, R² = 0,25, 8 locais com ≥ 100 votos válidos");
    expect(t).toContain("Nenhum local com 100 votos válidos");
    expect(notaLocais({ ...loc, estatistica: null }, "variacao")).toContain("Só os locais presentes em 2018 e 2022");
    const ar: MapaAreas = { rotulo: "", itens: {}, camada: "perfil", fonte_indicador: "IBGE amostra",
      cobertura: { areas: 50, areas_com_dado: 48, areas_cv_fragil: 3, areas_cv_cautela: 7 } };
    expect(notaAreas(ar, "perfil")).toContain("3 áreas pouco confiáveis (CV > 30%) e 7 para usar com cautela");
  });
});

describe("dados e exportação", () => {
  it("malhas: uma vez cada; falha não fica no cache", async () => {
    const f = vi.fn(async () => new Response('{"type":"FeatureCollection","features":[]}'));
    vi.stubGlobal("fetch", f);
    const m = criarMalhas();
    await Promise.all([m.municipios(), m.municipios(), m.bairros()]);
    expect(f.mock.calls.map((c) => (c as unknown as [string])[0])).toEqual(["geo/municipios.geojson", "geo/bairros.geojson"]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })));
    await expect(m.areas()).rejects.toThrow();
    vi.stubGlobal("fetch", f);
    await m.areas();
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("corpo da exportação: subtítulo por camada e o link no rodapé", () => {
    const cores = { fundo: "#fff", texto: "#000", sem_dado: "#eee", contorno: "#fff" };
    const c = { aba: "mapas", uf: "RJ", cargo: "Governador", ambiente: "Simulado", link: "http://x/#mapas" };
    const e = { camada: "municipios", cores: {}, legenda: [], titulo: "Mais votado" };
    expect(corpoExportacao(e, "png", c, cores)).toMatchObject({ subtitulo: "Governador — RJ · Simulado",
      nome: "mapa mapas Mais votado", extras: ["Link: http://x/#mapas"], fundo: "#fff", ano: null });
    expect(corpoExportacao({ ...e, camada: "locais", ano: 2022 }, "svg", c, cores).subtitulo)
      .toBe("RJ · locais de votação (cadastro de 2022); área do ponto ∝ eleitorado");
    expect(corpoExportacao({ ...e, subtitulo: "Abstenção" }, "svg", c, cores).subtitulo).toBe("Abstenção — RJ · bairros do IBGE");
  });
});

describe("enquadramento", () => {
  const mapaFalso = (conteiner: HTMLElement) =>
    ({ getContainer: () => conteiner, fitBounds: vi.fn() }) as unknown as MapaApuracao & { fitBounds: ReturnType<typeof vi.fn> };
  const limites = L.latLngBounds([[-33, -74], [5, -34]]);

  it("mapa escondido (tamanho 0): não enquadra agora, guarda para quando aparecer", () => {
    const m = mapaFalso(document.createElement("div"));  // fora do documento: tamanho 0
    enquadrarUmaVez(m, limites, [4, 4]);
    expect(m.fitBounds).not.toHaveBeenCalled();
    expect(m._enquadrarPendente).toEqual({ limites, padding: [4, 4] });
    expect(m._enquadrado).toBe(true);  // a atualização automática não refaz
  });
  it("mapa visível: enquadra uma vez só", () => {
    const div = document.createElement("div");
    document.body.append(div);
    Object.defineProperties(div, { clientWidth: { value: 400 }, clientHeight: { value: 300 } });
    const m = mapaFalso(div);
    enquadrarUmaVez(m, limites);
    enquadrarUmaVez(m, limites);
    expect(m.fitBounds).toHaveBeenCalledOnce();
    expect(m._enquadrarPendente).toBeUndefined();
    div.remove();
  });
});
