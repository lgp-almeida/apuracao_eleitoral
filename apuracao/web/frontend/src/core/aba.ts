/* Contrato de uma aba: o que o roteador e o resto da página precisam dela. Cada aba mora em abas/<aba>/,
 * guarda o próprio estado e só mexe nos elementos da sua seção (#aba-<aba>). */
import type { RotaAba } from "./roteador";
import type { Aba } from "./rotas";

export interface ModuloAba extends RotaAba {
  readonly id: Aba;
  /** Cada vez que a aba aparece (a 1ª vez costuma carregar as listas). */
  aoMostrar?(): void;
}

/** O que a página dá às abas (sem import circular com o resto do legado). */
export interface Contexto {
  /** UF do site (do /api/status). */
  uf(): string;
  /** Mostra uma aba (troca a seção visível e ajusta o endereço). */
  mostrarAba(aba: Aba): void;
  /** Regrava o endereço da aba, se aberta. */
  gravarEndereco(aba: Aba): void;
  /** Endereço atual da aba ("Copiar link"). */
  endereco(aba: Aba): string;
}
