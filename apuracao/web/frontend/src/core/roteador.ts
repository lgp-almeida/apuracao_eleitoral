/* A tabela única das abas: cada aba registra como escreve o seu endereço (estado → parâmetros) e como o
 * aplica (parâmetros → estado). O roteador abre o endereço (carga e hashchange), regrava-o sem encher o
 * histórico (replaceState não dispara hashchange) e dá o link para copiar. */
import { abaDoEndereco, type Aba, type Endereco, escreverEndereco, lerEndereco } from "./rotas";

export interface RotaAba {
  /** Estado visível da aba → parâmetros do endereço. Sem isto, o endereço da aba é só "#aba". */
  escrever?(): URLSearchParams;
  /** Parâmetros do endereço → estado da aba. Chamado só quando o endereço traz parâmetros; quem aplica
   * também mostra a aba. Sem isto (ou sem parâmetros), o roteador só mostra a aba. */
  aplicar?(params: URLSearchParams, endereco: Endereco): unknown;
  /** Ao mostrar a aba, grava o endereço completo, não só "#aba" (o painel: destaque e modo TV são estado). */
  enderecoAoMostrar?: boolean;
}

export interface Ambiente {
  local(): string;
  substituir(hash: string): void;
}

const ambienteDoNavegador: Ambiente = {
  local: () => location.hash,
  substituir: (hash) => history.replaceState(null, "", hash),
};

export class Roteador {
  private readonly rotas = new Map<Aba, RotaAba>();

  /**
   * @param mostrar mostra a aba (troca o painel visível e carrega o que ela precisa)
   * @param abaAtual a aba visível agora
   */
  constructor(
    private readonly mostrar: (aba: Aba) => void,
    private readonly abaAtual: () => string,
    private readonly ambiente: Ambiente = ambienteDoNavegador,
  ) {}

  registrar(aba: Aba, rota: RotaAba): this {
    if (this.rotas.has(aba)) throw new Error(`aba já registrada: ${aba}`);
    this.rotas.set(aba, rota);
    return this;
  }

  /** Endereço atual da aba, a partir do estado dela (o que "Copiar link" copia). */
  endereco(aba: Aba): string {
    return escreverEndereco(aba, this.rotas.get(aba)?.escrever?.());
  }

  /** Regrava o endereço da aba, se ela estiver aberta e o endereço tiver mudado. */
  gravar(aba: Aba): void {
    if (this.abaAtual() !== aba) return;
    const alvo = this.endereco(aba);
    if (this.ambiente.local() !== alvo) this.ambiente.substituir(alvo);
  }

  /** Ajuste do endereço ao mostrar uma aba (botão da aba ou código): outra aba no endereço vira esta. */
  aoMostrar(aba: Aba): void {
    const atual = abaDoEndereco(this.ambiente.local());
    const rota = this.rotas.get(aba);
    if (atual !== null && atual !== aba) {
      this.ambiente.substituir(rota?.enderecoAoMostrar ? this.endereco(aba) : escreverEndereco(aba));
    } else if (rota?.enderecoAoMostrar && rota.escrever?.().toString()) {
      this.ambiente.substituir(this.endereco(aba));
    }
  }

  /** Abre o endereço: aplica os parâmetros na aba, ou só a mostra. Endereço sem aba conhecida: nada. */
  abrir(hash: string = this.ambiente.local()): void {
    const endereco = lerEndereco(hash);
    if (endereco.aba === null) return;
    const rota = this.rotas.get(endereco.aba);
    if (rota?.aplicar && endereco.params.toString()) rota.aplicar(endereco.params, endereco);
    else this.mostrar(endereco.aba);
  }
}
