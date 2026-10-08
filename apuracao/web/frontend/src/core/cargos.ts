/* Nomes dos cargos pelo código do TSE (o mesmo em todas as eleições gerais e municipais). */
export const NOMES_CARGO: Readonly<Record<number, string>> = {
  1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual", 11: "Prefeito",
};

/** Nome do cargo, ou o próprio código se desconhecido. */
export const nomeCargo = (c: number | string): string => NOMES_CARGO[Number(c)] ?? String(c);
