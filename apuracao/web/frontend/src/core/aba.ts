/* Contrato de uma aba: o que o roteador e o resto da página precisam dela. Cada aba mora em abas/<aba>/,
 * guarda o próprio estado e só mexe nos elementos da sua seção (#aba-<aba>). */
import type { MapaApuracao, Malhas } from "../componentes/mapa/tipos";
import type { RotaAba } from "./roteador";
import type { Aba } from "./rotas";

export interface ModuloAba extends RotaAba {
  readonly id: Aba;
  /** Cada vez que a aba aparece (a 1ª vez costuma carregar as listas). */
  aoMostrar?(): void;
  /** Carga na abertura da página, antes de abrir o endereço (ex.: a comparação descobre se existe). */
  preparar?(): Promise<void>;
  /** Ciclo de atualização (60 s), só com a aba aberta. */
  atualizar?(): Promise<void>;
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
  /** Turno da eleição no site (do /api/status). */
  turno(): number;
  /** Ano da eleição do site (2026 no tempo real; o da importação num histórico). */
  ano(): number;
  /** Malhas do site, com cache da página. */
  malhas: Malhas;
  /** Torna um mapa conhecido da página pelo nome (exportação: data-mapa="<nome>"; testes e2e). */
  registrarMapa(nome: string, mapa: MapaApuracao): void;
}
