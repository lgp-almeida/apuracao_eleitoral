/* Aba "Painel": um cartão por cargo (totalização, candidatos, série, projeção, cadeiras, presidente por UF),
 * destaque de partidos, "o que mudou" e modo TV. Atualiza a cada 60 s com a aba aberta.
 * Endereço: #painel[?destacar=PT,PL][&tv=1] */
import { copiarLink } from "../../componentes/link";
import type { MapaApuracao } from "../../componentes/mapa/tipos";
import type { Contexto, ModuloAba } from "../../core/aba";
import { api } from "../../core/api";
import { refs } from "../../core/dom";
import { criarBrasil, type EstadoBrasil } from "./brasil";
import { cartao } from "./cartao";
import { criarDestaque } from "./destaque";
import { criarMudancas } from "./mudancas";
import type { Painel } from "./tipos";
import { criarModoTv, type ContextoTv, type EstadoTv } from "./tv";

export interface EstadoPainel {
  painel: Painel | null;
  destacar: Set<string>;
  destacarDefinido: boolean;
  /** Cargos com a lista de eleitos aberta (reabre no redesenho de 60 s). */
  cadAbertos: Set<number>;
  brasil: EstadoBrasil;
  tv: EstadoTv;
}

export interface DependenciasPainel {
  consultarCandidato(cargo: number, numero: number): void;
  situacao: ContextoTv["situacao"];
}

export function criarAbaPainel(ctx: Contexto, deps: DependenciasPainel) {
  const r = refs({ cartoes: "#cartoes", limpar: "#destaque-limpar", link: "#destaque-link", linkMsg: "#destaque-link-msg" });
  const gravar = () => ctx.gravarEndereco("painel");
  const brasil = criarBrasil((m: MapaApuracao) => ctx.registrarMapa("brasilMapa", m));
  const tv = criarModoTv({
    tituloCartao: (i) => { const c = estado.painel?.cartoes[i]; return c ? `${c.ds_cargo} — ${c.abrangencia}` : null; },
    situacao: deps.situacao, mostrarPainel: () => ctx.mostrarAba("painel"), gravarEndereco: gravar,
  });
  const estado: EstadoPainel = { painel: null, destacar: new Set(), destacarDefinido: false, cadAbertos: new Set(),
    brasil: brasil.estado, tv: tv.estado };
  const destaque = criarDestaque(estado, gravar, desenhar);
  const atualizarMudancas = criarMudancas();

  function desenhar(): void {
    if (!estado.painel) return;
    const ctxCartao = { destacar: estado.destacar, abertos: estado.cadAbertos,
      consultarCandidato: deps.consultarCandidato, blocoBrasil: brasil.bloco };
    r.cartoes.replaceChildren(...estado.painel.cartoes.map((c) => cartao(c, ctxCartao)));
    destaque.opcoes(estado.painel.cartoes);
    tv.aplicar();
  }

  async function atualizarPainel(): Promise<void> {
    try { estado.painel = await api<Painel>("api/painel"); } catch { return; }
    desenhar();
    void brasil.atualizar();
  }

  function escrever(): URLSearchParams {
    const q = new URLSearchParams();
    if (estado.destacar.size) q.set("destacar", [...estado.destacar].join(","));
    if (estado.tv.ativo) q.set("tv", "1");
    return q;
  }

  function aplicar(q: URLSearchParams): void {
    const d = q.get("destacar");
    if (d !== null) destaque.definir(d.split(","), true);
    ctx.mostrarAba("painel");
    if (q.get("tv") === "1") tv.ligar(true);
  }

  r.limpar.addEventListener("click", () => destaque.definir([]));
  r.link.addEventListener("click", () => void copiarLink(ctx.endereco("painel"), r.linkMsg));

  const modulo: ModuloAba = {
    id: "painel",
    escrever,
    aplicar,
    enderecoAoMostrar: true,
    async atualizar() { await atualizarPainel(); void atualizarMudancas(); },
  };
  return Object.assign(modulo, { estado, desenhar, atualizarPainel, destaqueInicial: destaque.inicial });
}
