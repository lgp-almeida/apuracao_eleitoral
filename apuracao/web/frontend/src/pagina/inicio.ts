/* Arranque da página: o estado comum (UF, ano, turno, mapas por nome), as abas, o roteador, o ciclo de 60 s,
 * os alertas e o ponto de acesso dos testes e2e. Cada aba mora em abas/<aba>/; aqui só se ligam as peças. */
import { criarAbaCandidato } from "../abas/candidato/index";
import { criarAbaComparacao } from "../abas/comparacao/index";
import { criarAbaMapas } from "../abas/mapas/index";
import { criarAbaPainel } from "../abas/painel/index";
import { criarAbaPerfil } from "../abas/perfil/index";
import { criarAbaTransferencia } from "../abas/transferencia/index";
import { criarAlertas, ALERTAS_MS } from "../alertas/index";
import { exportarMapa } from "../componentes/mapa/exportar";
import type { MapaApuracao } from "../componentes/mapa/tipos";
import type { Contexto, ModuloAba } from "../core/aba";
import { repetir } from "../core/agendador";
import { api } from "../core/api";
import { ref } from "../core/dom";
import { Roteador } from "../core/roteador";
import { type Aba, ehAba } from "../core/rotas";
import { criarCandidatos } from "../dados/candidatos";
import { criarMalhas } from "../dados/malhas";
import { iniciarSeletorUf } from "./seletor-uf";
import { criarSituacao, limitarCargos } from "./situacao";

const REFRESH_MS = 60_000;

/** Estado comum às abas (o de cada aba fica no módulo dela). Os mapas ficam aqui pelo nome: a exportação
 * (data-mapa="<nome>") e os testes e2e (__apuracao.estado.<nome>) os acham assim. */
const estado: { aba: Aba; uf: string; ano: number; turno: number; ultimaColeta: string | null;
  ultimoBoletim: { titulo: string; gerado_em: string } | null; [mapa: string]: unknown } = {
  aba: "painel", uf: "", ano: 2026, turno: 1, ultimaColeta: null, ultimoBoletim: null,
};

const modulos = new Map<Aba, ModuloAba>();
const roteador = new Roteador(mostrarAba, () => estado.aba);

function mostrarAba(aba: Aba): void {
  estado.aba = aba;
  roteador.aoMostrar(aba);
  document.querySelectorAll<HTMLElement>(".abas button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === aba)));
  document.querySelectorAll<HTMLElement>(".aba").forEach((s) => { s.hidden = s.id !== `aba-${aba}`; });
  modulos.get(aba)?.aoMostrar?.();
}

const contexto: Contexto = {
  uf: () => estado.uf, turno: () => estado.turno, ano: () => estado.ano, mostrarAba,
  gravarEndereco: (a) => roteador.gravar(a), endereco: (a) => roteador.endereco(a),
  malhas: criarMalhas(),  // municípios, bairros e áreas de ponderação, uma vez por página
  registrarMapa: (nome, mapa) => { estado[nome] = mapa; },
};

function registrar<M extends ModuloAba>(m: M): M {
  modulos.set(m.id, m);
  roteador.registrar(m.id, m);
  return m;
}

const candidatos = criarCandidatos();  // listas de candidatos por cargo: abas Candidato e Mapas
const alertas = criarAlertas(() => estado.ano);
const abaCandidato = registrar(criarAbaCandidato(contexto, { candidatos, botaoAcompanhar: alertas.botaoAcompanhar }));
const abaPainel = registrar(criarAbaPainel(contexto, {
  consultarCandidato: (cargo, numero) => void abaCandidato.consultar(cargo, numero),
  situacao: () => ({ ultimaColeta: estado.ultimaColeta, ultimoBoletim: estado.ultimoBoletim }),
}));
registrar(criarAbaMapas(contexto, { candidatos }));
const abaComparacao = registrar(criarAbaComparacao(contexto));
registrar(criarAbaPerfil(contexto));
registrar(criarAbaTransferencia(contexto));

const atualizarSituacao = criarSituacao((s) => {
  estado.uf = s.uf;
  estado.turno = s.coletor.turno || 1;
  estado.ano = s.coletor.ano || 2026;  // resultados históricos (importar_resultado_historico.py) trazem o ano
  estado.ultimoBoletim = s.ultimo_boletim ?? null;
  estado.ultimaColeta = s.coletor.ultimo_ciclo_fim || s.coletor.ultimo_ciclo_inicio || null;
  abaPainel.destaqueInicial(s.destacar_padrao);
  alertas.atualizarTitulo();
  limitarCargos(s.cargos || [], [ref<HTMLSelectElement>("#cand-cargo"), ref<HTMLSelectElement>("#mapa-cargo")]);
});

/** Ciclo de 60 s: situação do coletor e a aba aberta. */
async function tick(): Promise<void> {
  await atualizarSituacao();
  await modulos.get(estado.aba)?.atualizar?.();
}

// botões das abas e "Baixar mapa" (Mapas e Comparação)
document.querySelectorAll<HTMLElement>(".abas button").forEach((b) => b.addEventListener("click", () => {
  if (ehAba(b.dataset.aba)) mostrarAba(b.dataset.aba);
}));
document.querySelectorAll<HTMLElement>(".baixar-mapa").forEach((b) => b.addEventListener("click", () => {
  const qual = b.dataset.mapa ?? "mapa";
  const cargo = ref<HTMLSelectElement>(qual === "mapa" ? "#mapa-cargo" : "#comp-cargo");
  void exportarMapa(estado[qual] as MapaApuracao | undefined, b.dataset.formato ?? "png",
    b.parentElement?.querySelector<HTMLElement>(".baixar-msg") ?? b, {
      aba: qual === "mapa" ? "mapas" : "comparacao", uf: estado.uf, cargo: cargo.selectedOptions[0]?.textContent || "",
      ambiente: ref("#ambiente").textContent ?? "", link: `${location.origin}${location.pathname}${location.hash}`,
    });
}));

// Ponto de acesso dos testes e2e (no script clássico estes nomes eram globais; nos módulos, não).
window.__apuracao = {
  estado, api,
  abas: Object.fromEntries(modulos),
  alertas: alertas.estado,
  get tocar() { return alertas.tocar; },
  set tocar(f) { alertas.tocar = f; },
  atualizarAlertas: () => alertas.atualizar(),
  desenharPainel: () => abaPainel.desenhar(),
  atualizarPainel: () => abaPainel.atualizarPainel(),
  consultarCandidato: (cargo: number, numero: number) => abaCandidato.consultar(cargo, numero),
  partidosVar: () => abaComparacao.partidosVar(),
};

// arranque
repetir(() => alertas.atualizar(), ALERTAS_MS).agora();  // continua com a aba escondida: é quando o som importa
window.addEventListener("hashchange", () => roteador.abrir());
void iniciarSeletorUf();
// o ciclo de 60 s nunca roda duas vezes ao mesmo tempo; com a aba escondida espera a volta
const ciclo = repetir(tick, REFRESH_MS, { pausarOculto: true });
const preparar = (m: ModuloAba) => m.preparar?.() ?? Promise.resolve();
void preparar(abaComparacao).then(() => ciclo.agora()).then(() => roteador.abrir());
void preparar(abaCandidato);
