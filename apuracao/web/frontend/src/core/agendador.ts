/* Tarefas repetidas: uma execução nunca começa antes de a anterior terminar e, se pedido,
 * a tarefa não roda com a aba escondida — roda uma vez ao voltar se perdeu alguma vez. */

export interface OpcoesRepeticao {
  /** Não roda com document.hidden (o refresh pesado); alertas devem continuar (false). */
  pausarOculto?: boolean;
  /** Erro da tarefa (a repetição continua). Padrão: console.error. */
  aoErrar?: (e: unknown) => void;
}

export interface Repeticao {
  /** Roda agora (se não estiver rodando); a promessa termina com a execução. */
  agora(): Promise<void>;
  parar(): void;
}

export function repetir(tarefa: () => unknown, intervaloMs: number, opcoes: OpcoesRepeticao = {}): Repeticao {
  const { pausarOculto = false, aoErrar = (e: unknown) => console.error(e) } = opcoes;
  let rodando: Promise<void> | null = null;
  let perdeu = false;

  const agora = (): Promise<void> => {
    if (rodando) return rodando;  // sem sobreposição: quem chama espera a execução em curso
    const execucao = (async () => {
      try { await tarefa(); } catch (e) { aoErrar(e); }
    })();
    rodando = execucao;
    // liberar DEPOIS de atribuir: uma tarefa que falha sem chegar a um await termina antes da atribuição
    void execucao.then(() => { if (rodando === execucao) rodando = null; });
    return execucao;
  };
  const passo = (): void => {
    if (pausarOculto && document.hidden) { perdeu = true; return; }
    if (!rodando) void agora();
  };
  const aoMudarVisibilidade = (): void => {
    if (!document.hidden && perdeu) { perdeu = false; void agora(); }
  };

  const id = setInterval(passo, intervaloMs);
  if (pausarOculto) document.addEventListener("visibilitychange", aoMudarVisibilidade);
  return {
    agora,
    parar() {
      clearInterval(id);
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    },
  };
}
