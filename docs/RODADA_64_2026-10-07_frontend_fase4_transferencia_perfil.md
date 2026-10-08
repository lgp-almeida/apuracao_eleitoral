# Rodada 64 — Front-end, fase 4 (parte 1): abas Transferência e Perfil × voto (07/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 4. As fases anteriores estão nas rodadas
[60](RODADA_60_2026-10-07_frontend_fase0_andaime.md) a [63](RODADA_63_2026-10-07_frontend_fase3_componentes.md).

## Objetivo

A fase 4 tira cada aba do `legado.js`, da mais isolada para a mais crítica: transferência → perfil → comparação →
candidato → mapas → painel (com alertas e modo TV). Esta rodada faz as duas primeiras e define o padrão que as
outras seguem.

## O padrão de uma aba (`src/abas/<aba>/`)

- **`index.ts`:** `criarAba<Nome>(ctx)` devolve um `ModuloAba` (`core/aba.ts`), registrado direto no roteador
  (`ModuloAba` estende `RotaAba`). Ele tem:
  - `id`;
  - `escrever()`: estado → parâmetros;
  - `aplicar(params)`: parâmetros → estado, e mostra a aba;
  - `aoMostrar()`: a 1ª vez carrega as listas;
  - `estado`: só o da aba, exposto aos testes.
- **Contexto (`Contexto`):** é tudo o que a aba recebe da página: `uf()`, `mostrarAba`, `gravarEndereco` e
  `endereco`. Ela não importa nada do legado, então não há dependência circular.
- **Elementos:** buscados na montagem por `refs`/`ref`, que falham logo listando os ids ausentes. Acabam os
  `getElementById` espalhados.
- **Pedidos:** `api` com `Canal`, em que o pedido novo cancela o anterior e o cancelamento é ignorado com
  `cancelado(e)`. Saem os contadores `tf.ultimo` e `estado.pf.pedido`.
- **`tipos.ts`:** as respostas da API que a aba usa. É o `tipos/api.ts` da proposta, dividido por aba.
- **`desenhar.ts`:** o resultado em DOM, a partir dos dados e sem estado, testado no `happy-dom`.
- **`formatos.ts`**, quando a aba tem vocabulário próprio (o Perfil × voto tem unidades, indicadores e a força da
  correlação).
- **Na página:** `legado.js` cria o módulo com `criarAba…(contexto)` e o registra uma vez na tabela
  (`registrarModulo`). `mostrarAba` chama o `aoMostrar` do módulo; não há mais `if (aba === "…")` para essas
  abas.

Compartilhados novos: `core/aba.ts` (contrato), `core/cargos.ts` (`NOMES_CARGO`/`nomeCargo`, antes uma constante
no meio da comparação) e `componentes/link.ts` (`copiarLink`).

## Entregas

- **`abas/transferencia/`** (251 linhas): `tipos`, `desenhar` (`desenharTransferencia`, `formatarCelula`,
  `leituraFragil`) e `index`.
- **`abas/perfil/`** (447 linhas):
  - `tipos`;
  - `formatos`: `fmtX`, `forca`, `unidadeDoX`, `UNIDADES`, `REG_PADRAO`;
  - `desenhar`: fichas, correlações, resíduos e regressão;
  - `index`: listas por unidade, candidatos e partidos dos dois lados, endereço e análise.

  Os 37 campos `pf-…` são conferidos na montagem.
- **No legado:** 2.415 → 1.985 linhas (−430). `__apuracao.tf` saiu (nenhum teste o usava).
- **Testes:** 11 Vitest novos, 87 no total:
  - formato das células e leitura frágil;
  - barras: segmento desprezível omitido e nome do TSE com HTML como texto;
  - formatos do perfil, fichas, correlações com clique, resíduos e regressão com VIF alto.

## Decisões

- **O Perfil × voto faz três pedidos por análise** (dispersão, correlações e regressão), todos com o mesmo sinal do
  `Canal`. O erro da regressão continua virando a mensagem "Regressão indisponível", mas o cancelamento é
  relançado, para não aparecer como erro.
- **O cálculo da transferência cancela o anterior.** Antes, o anterior continuava a calcular no servidor e a
  resposta só era descartada. O servidor não interrompe a conta, mas a página deixa de esperar por ela.

## Verificação

- `npm run verificar`: tipos, lint, 87 testes do Vitest e build.
- `pytest -m e2e`: 71 passaram, incluindo `test_perfil_e2e.py` (8) e `test_transferencia_e2e.py` (2) sem mudança.
  `pytest test_frontend_build.py`: 3 passaram.

## Próxima

Fase 4, parte 2: a aba Comparação, com o mapa por bairro, as bancadas e a variação por partido. É a mais longa das
que faltam: 370 linhas no legado e três controles de resposta atrasada (`bancPedido`, `varPedido`, `compDetalhe`).
