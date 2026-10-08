/* Lista de candidatos por cargo (/api/candidatos), com cache da página: busca por nº ou parte do nome e as
 * listas de sugestão (datalist) da aba Candidato e da aba Mapas. Trocar de cargo esvazia o cache (a apuração
 * pode ter mudado a lista). */
import { api } from "../core/api";
import { el } from "../core/dom";

export interface CandidatoLista { NUMERO: number; NOME_URNA: string; PARTIDO: string }

/** Nº digitado, ou o 1º candidato cujo nome de urna contém o texto (sem diferenciar maiúsculas); null se nada. */
export function resolverNaLista(lista: readonly CandidatoLista[], texto: string): number | null {
  const t = texto.trim();
  if (/^\d+$/.test(t)) return Number(t);
  const alvo = t.toUpperCase();
  const achado = lista.find((c) => (c.NOME_URNA || "").toUpperCase().includes(alvo));
  return achado ? achado.NUMERO : null;
}

export function criarCandidatos() {
  let cache: Record<string, Promise<CandidatoLista[]> | undefined> = {};

  const lista = (cargo: string): Promise<CandidatoLista[]> => {
    const p = (cache[cargo] ??= api<CandidatoLista[]>(`api/candidatos?cargo=${cargo}`));
    p.catch(() => { if (cache[cargo] === p) cache[cargo] = undefined; });  // falha não fica no cache
    return p;
  };

  return {
    lista,
    limpar(): void { cache = {}; },
    /** Preenche o datalist com "nº → nome (partido)"; sem dados ainda, fica como está. */
    async preencher(cargo: string, datalist: HTMLElement): Promise<void> {
      try {
        const l = await lista(cargo);
        datalist.replaceChildren(...l.map((c) => el("option", { value: c.NUMERO }, `${c.NOME_URNA} (${c.PARTIDO})`)));
      } catch { /* sem dados ainda */ }
    },
    async resolver(cargo: string, texto: string): Promise<number | null> {
      if (/^\d+$/.test(texto.trim())) return Number(texto.trim());
      return resolverNaLista(await lista(cargo), texto);
    },
  };
}

export type Candidatos = ReturnType<typeof criarCandidatos>;
