/* Notas sob o mapa (cobertura e como ler cada camada), sem DOM. */
import { decimal, int } from "../../core/formatos";
import type { Camada } from "./regras";
import type { EstatisticaCamada, MapaAreas, MapaBairros, MapaLocais } from "./tipos";

/** Reta do resíduo: r, R², quantas unidades e o sentido das cores. */
function reta(est: EstatisticaCamada | null | undefined, minValidos: number | undefined, unidades: string): string {
  return est && est.pearson !== null ? ` Reta voto × indicador: r = ${decimal(est.pearson, 2)}, ` +
    `R² = ${decimal(est.r2, 2)}, ${int(est.n)} ${unidades} com ≥ ${int(minValidos)} votos válidos. ` +
    "Azul: o voto foi MAIOR que o esperado pelo indicador; vermelho: menor. Correlação ecológica." : "";
}

const TRANSFERENCIA = "Inferência ecológica (padrão médio, não o voto de pessoas)";

export function notaBairros(d: MapaBairros): string {
  const c = d.cobertura;
  return `Bairros do IBGE (Censo 2022): ${int(c.bairros_com_dado)} de ${int(c.bairros)} bairros têm local ` +
    `de votação (${int(c.locais_em_bairro)} locais). Municípios sem malha de bairros aparecem só com o contorno. ` +
    "Cada local é contado no bairro que contém sua coordenada.";
}

export function notaLocais(d: MapaLocais, camada: Camada): string {
  const c = d.cobertura;
  return `${int(c.com_valor)} de ${int(c.locais)} locais com valor (coordenada do cadastro de eleitorado ` +
    `de ${d.ano}); a área do ponto é proporcional ao eleitorado do local.` +
    reta(d.estatistica, d.min_validos, "locais") +
    (camada === "variacao" ? ` Só os locais presentes em ${d.ano_ref} e ${d.ano} (mesmo município, zona e nº do local); ` +
      "partido pela entidade (fusões e trocas de nº). Azul: subiu; vermelho: caiu." : "") +
    (camada === "transferencia" ? ` ${TRANSFERENCIA}: o destino dos ` +
      "eliminados é estimado por município (todos os locais do município têm o mesmo valor); eliminados, abstenção " +
      "extra e o resíduo são de cada local." : "") +
    (!d.itens.length && camada === "residuo" ? ` Nenhum local com ${int(d.min_validos)} votos válidos ou mais ` +
      "para o resíduo (ele só usa locais com votos suficientes)." : "");
}

export function notaAreas(d: MapaAreas, camada: Camada): string {
  const c = d.cobertura;
  const amostra = (d.fonte_indicador || "").includes("amostra");
  const corpo = camada === "perfil"
    ? `Fonte: ${d.fonte_indicador}.` + (amostra ? " Estimativa da amostra do Censo: tem erro amostral" +
      (c.areas_cv_fragil != null ? ` — ${int(c.areas_cv_fragil)} áreas pouco confiáveis (CV > 30%) e ` +
        `${int(c.areas_cv_cautela)} para usar com cautela (CV de 15% a 30%), pelos coeficientes do IBGE.` : ".") : "")
    : "O voto da área é a soma dos locais de votação dentro dela (o local fica na área do setor que contém a sua " +
      "coordenada)." + (camada === "variacao" ? ` A área é a mesma nos dois anos (${d.ano_ref} e ${d.ano}).` : "") +
      (camada === "transferencia" ? ` ${TRANSFERENCIA}, feita por local e ` +
        "somada na área: o destino dos eliminados é estimado por município (todas as áreas do município têm o mesmo " +
        "valor); eliminados, abstenção extra e o resíduo são de cada área." : "");
  return `Áreas de ponderação do Censo 2022 (IBGE): ${int(c.areas_com_dado)} de ${int(c.areas)} áreas ` +
    "com local de votação têm valor; uma cidade pequena é uma área só. " + corpo +
    reta(d.estatistica, d.min_validos, "áreas") +
    (d.camada === "variacao" ? " Partido pela entidade (fusões e trocas de nº). Azul: subiu; vermelho: caiu." : "") +
    (!Object.keys(d.itens).length && d.camada === "residuo" ? ` Nenhuma área com ${int(d.min_validos)} votos válidos ` +
      "ou mais para o resíduo (ele só usa áreas com votos suficientes)." : "");
}

/** Nota da linha do tempo quando ainda não há 2 totalizações. */
export const notaLinhaDoTempo = (n: number): string => `Linha do tempo: aparece a partir da 2ª totalização municipal ` +
  `(${n} registrada${n === 1 ? "" : "s"} para este cargo).`;
