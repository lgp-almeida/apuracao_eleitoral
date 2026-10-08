/* Destaque de partidos/federações (rodada 31): um candidato é destacado se o PARTIDO ou a AGREMIACAO (federação =
 * todos os seus partidos) foi escolhido. Vale nas listas de eleitos, fica no navegador e no endereço #painel?destacar=.
 * Prioridade: endereço > navegador > --destacar do site. */
import { el, refs } from "../../core/dom";
import { gravarJson, lerJson } from "../../core/preferencias";
import { lerEndereco } from "../../core/rotas";
import type { Cadeiras, Cartao } from "./tipos";

export interface EstadoDestaque {
  destacar: Set<string>;
  /** Já veio do endereço, do navegador ou do usuário: o padrão do site não vale mais. */
  destacarDefinido: boolean;
}

export const destacado = (destacar: ReadonlySet<string>, x: { PARTIDO?: string; AGREMIACAO?: string }): boolean =>
  (x.PARTIDO !== undefined && destacar.has(x.PARTIDO)) || (x.AGREMIACAO !== undefined && destacar.has(x.AGREMIACAO));

/** Agremiações com algum escolhido: a própria (partido ou federação) ou um partido da federação. */
export function agremiacoesDestacadas(destacar: ReadonlySet<string>, k: Pick<Cadeiras, "composicao">): Set<string> {
  return new Set((k.composicao || []).filter((a) => destacar.has(a.AGREMIACAO) || a.PARTIDOS.some((p) => destacar.has(p)))
    .map((a) => a.AGREMIACAO));
}

/** Agremiações dos cartões com cadeiras (uma vez cada, na ordem em que aparecem). */
export function composicoes(cartoes: readonly Cartao[]): Map<string, string[]> {
  const comp = new Map<string, string[]>();
  for (const c of cartoes) for (const a of c.cadeiras?.composicao || []) if (!comp.has(a.AGREMIACAO)) comp.set(a.AGREMIACAO, a.PARTIDOS);
  return comp;
}

/**
 * @param estado onde fica a escolha (o do painel)
 * @param gravarEndereco regrava #painel?destacar=
 * @param redesenhar redesenha os cartões com a escolha nova
 */
export function criarDestaque(estado: EstadoDestaque, gravarEndereco: () => void, redesenhar: () => void) {
  const r = refs({ caixa: "#destaque", resumo: "#destaque-resumo", opcoes: "#destaque-opcoes" });

  function definir(lista: readonly string[], gravar = true): void {
    estado.destacar = new Set(lista.filter(Boolean));
    estado.destacarDefinido = true;
    if (gravar) {  // escolha do usuário: fica no navegador e no endereço
      gravarJson("destacar", [...estado.destacar]);
      gravarEndereco();
    }
    redesenhar();
  }

  return {
    definir,
    /** Endereço > navegador > padrão do site, sem reescrever o endereço. Só na 1ª vez. */
    inicial(padrao: readonly string[] | null | undefined): void {
      if (estado.destacarDefinido) return;
      const { aba, params } = lerEndereco(location.hash);
      const doEndereco = aba === "painel" ? params.get("destacar") : null;
      if (doEndereco !== null) { definir(doEndereco.split(","), false); return; }
      const salvo = lerJson<unknown>("destacar");
      definir(Array.isArray(salvo) ? salvo.map(String) : [...(padrao || [])], false);
    },
    /** Caixas de escolha a partir das agremiações dos cartões (redesenho a cada 60 s mantém o foco do teclado). */
    opcoes(cartoes: readonly Cartao[]): void {
      const comp = composicoes(cartoes);
      r.caixa.hidden = !comp.size;
      r.resumo.textContent = estado.destacar.size ? `(${[...estado.destacar].join(", ")})` : "(nenhum)";
      const marca = (valor: string, rotulo: string) => el("label", {}, el("input", { type: "checkbox", value: valor,
        checked: estado.destacar.has(valor), onchange: (e: Event) => {
          const novo = new Set(estado.destacar);
          if ((e.target as HTMLInputElement).checked) novo.add(valor); else novo.delete(valor);
          definir([...novo]);
        } }), rotulo);
      const itens = [...comp].map(([ag, partidos]) => (partidos.length > 1 || partidos[0] !== ag
        ? el("fieldset", {}, el("legend", {}, "Federação"), marca(ag, ag), ...partidos.map((p) => marca(p, p)))
        : marca(ag, ag)));
      const foco = (document.activeElement as HTMLInputElement | null)?.value;
      r.opcoes.replaceChildren(...itens);
      if (foco) r.opcoes.querySelector<HTMLElement>(`input[value="${CSS.escape(foco)}"]`)?.focus();
    },
  };
}

export type Destaque = ReturnType<typeof criarDestaque>;
