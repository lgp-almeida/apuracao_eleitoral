import { describe, expect, it } from "vitest";
import { abaDoEndereco, ABAS, escreverEndereco, lerEndereco } from "../src/core/rotas";

const obj = (q: URLSearchParams) => Object.fromEntries(q);

// endereços reais de cada aba (CLAUDE.md, "Endereços do site", e test_enderecos.py)
const EXEMPLOS = [
  "#painel",
  "#painel?destacar=PT%2CPC+do+B&tv=1",
  "#candidato?cargo=7&numero=13713&municipio=60011&ordem=VOTOS-desc&hist=1&hist_cargo=6&pl=1&pl_ano=2022",
  "#mapas?cargo=3&metrica=pct_candidato&numero=68&momento=2026-09-29T18%3A30%3A00&locais=1",
  "#mapas?cargo=3&metrica=vencedor&detalhe=locais&ano_bairros=2022&camada=variacao&municipio=3304557",
  "#comparacao?cargo=7&metrica=partido&partido=PL&ordem=DIF-desc&var=1&var_partidos=PT%2CPL&var_ponderar=1",
  "#comparacao?cargo=3&metrica=abstencao&detalhe=bairros&ano_a=2022&cargo_a=3&ano_b=2024&cargo_b=11&banc=1&banc_cargo=7",
  "#perfil?ano=2022&turno=1&cargo=3&numero=22&x=voto&x_ano=2018&x_turno=1&x_cargo=3&x_partido=PT&unidade=area&min_validos=0",
  "#transferencia?fonte=microdados&cargo=1&ano=2022&nivel=local&municipio=58190",
];

describe("lerEndereco / escreverEndereco", () => {
  it.each(EXEMPLOS)("ida e volta sem perda: %s", (hash) => {
    const { aba, params } = lerEndereco(hash);
    if (aba === null) throw new Error(`sem aba: ${hash}`);
    expect(escreverEndereco(aba, params)).toBe(hash);
  });

  it("cada aba tem pelo menos um exemplo", () => {
    expect(new Set(EXEMPLOS.map(abaDoEndereco))).toEqual(new Set(ABAS));
  });

  it("formato antigo do candidato vira parâmetros", () => {
    expect(obj(lerEndereco("#candidato/7/13713/60011").params)).toEqual({ cargo: "7", numero: "13713", municipio: "60011" });
    expect(obj(lerEndereco("#candidato/3/22").params)).toEqual({ cargo: "3", numero: "22" });
    expect(lerEndereco("#candidato/3").params.toString()).toBe("");  // incompleto: só a aba
    expect(lerEndereco("#candidato/3/22").aba).toBe("candidato");
  });

  it("vazio ou desconhecido não tem aba", () => {
    expect(lerEndereco("").aba).toBeNull();
    expect(lerEndereco("#").aba).toBeNull();
    expect(lerEndereco("#xyz?a=1").aba).toBeNull();
    expect(abaDoEndereco("#mapass")).toBeNull();
  });

  it("sem parâmetros não deixa '?' sobrando; '?' no valor fica no valor", () => {
    expect(escreverEndereco("mapas", new URLSearchParams())).toBe("#mapas");
    expect(escreverEndereco("perfil")).toBe("#perfil");
    expect(lerEndereco("#painel?").params.toString()).toBe("");
    expect(lerEndereco("#painel?destacar=a?b").params.get("destacar")).toBe("a?b");
  });

  it("aba do endereço ignora parâmetros e o formato antigo", () => {
    expect(abaDoEndereco("#candidato/7/1")).toBe("candidato");
    expect(abaDoEndereco("perfil?ano=2022")).toBe("perfil");
  });
});
