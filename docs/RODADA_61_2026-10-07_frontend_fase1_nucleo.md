# Rodada 61 — Front-end, fase 1: núcleo (07/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 1. A fase anterior está na
[RODADA_60](RODADA_60_2026-10-07_frontend_fase0_andaime.md).

## Objetivo

Tirar do `legado.js` as peças que todo o resto usa e colocá-las em TypeScript estrito, com testes unitários. Junto
entram o lint e as duas primeiras melhorias de robustez da §6: pedido com tempo-limite e repetição sem sobreposição.

## Entregas

- **`src/core/`** (TypeScript strict):
  - `dom.ts`: `el`, `svg` e `cor` tipados. Inclui `ref`/`refs`, buscas obrigatórias que listam todos os ids ausentes
    (ainda sem uso: entram quando cada aba migrar).
  - `api.ts`: `api`, `enviar` (POST JSON) e `baixar` (arquivo + nome do `Content-Disposition`). Todos passam por
    `pedir`, que dá o tempo-limite (60 s, ou 10 min nas rotas pesadas), aceita cancelamento e lança `ErroApi` com o
    `detail` do FastAPI e o status. `ROTAS_PESADAS` é um espelho da lista do `web/app.py`, e
    `test_frontend_build.py::test_rotas_pesadas_iguais_as_do_site` falha se as duas divergirem.
  - `pedidos.ts`: `Canal` (cada pedido novo cancela o anterior) e `cancelado(e)`.
  - `agendador.ts`: `repetir(tarefa, ms, { pausarOculto })`. Uma execução nunca começa antes de a anterior
    terminar, e um erro não interrompe a repetição. Com a aba escondida a tarefa espera e roda uma vez ao voltar.
  - `formatos.ts`: `int`, `pct`, `p1`, `fmtNum`, `hora`, `fmtPP`, `fmtFreq`, `fmtR`, `fmtP`, `mil` e `decimal`,
    antes espalhados por cinco trechos do arquivo.
  - `preferencias.ts`: `lerPreferencia`/`gravarPreferencia` e `lerJson`/`gravarJson`, que toleram armazenamento
    bloqueado.
- **O legado passa a importar o núcleo.** Saíram dele as definições acima e os cinco `fetch` diretos (exportar mapa,
  planilha, acompanhar deputado, `ufs.json` e o próprio `api`). O ciclo de 60 s e os alertas de 15 s rodam por
  `repetir`. O ciclo pausa com a aba escondida; os alertas não, porque é aí que o som importa. O `legado.js` caiu
  de 3.117 para 3.051 linhas.
- **Vitest** (`happy-dom`): 33 testes em `tests/`. Cobrem formatos pt-BR, escape de texto, `ref`/`refs`, tempo-limite
  por rota, `detail`/status, cancelamento, POST/arquivo, `Canal`, agendador com relógio falso e armazenamento
  bloqueado.
- **ESLint 10** (`eslint.config.js`):
  - código novo: `typescript-eslint` estrito;
  - legado: `no-undef`, que pega qualquer nome removido sem `import`, e mais duas regras de erro óbvio;
  - todo o código: proíbe `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write` e `eval`. Conferido: um
    `innerHTML` no legado faz o lint falhar.
- **Scripts:** `npm run lint`, `npm test` e `npm run verificar` (tipos + lint + testes + build).

## Bug encontrado pelos testes

`repetir` não liberava a trava "rodando" quando a tarefa lançava erro antes do primeiro `await`. O `finally` rodava
antes de a promessa ser atribuída, então a repetição parava para sempre. Nenhum código migrado tinha esse caso, mas
seria o tipo de falha silenciosa que para o painel no meio da noite. Agora a trava é liberada depois da atribuição,
e o teste "erro na tarefa não para a repetição" cobre o caso.

## Mudanças de comportamento (pequenas e intencionais)

- Pedido sem resposta em 60 s vira o erro "o site não respondeu em 60 s". Nas rotas pesadas o limite é 10 min.
  Antes, a página esperava para sempre.
- O `tick` de 60 s não se sobrepõe a si mesmo e não roda com a aba escondida. Ao voltar, roda uma vez.
- `svg()` ignora filhos `null`/`false`, como `el()`. Antes eles viravam o texto "null".

## Desvios da proposta

- `tipos/api.ts` fica para a migração de cada aba (fase 4). Tipar agora as 46 rotas daria tipos sem nenhum
  consumidor TypeScript para conferi-los.
- Os quatro contadores de resposta atrasada (`pedidoMapa`, `histPedido`, `varPedido`, `bancPedido`) continuam no
  legado. O `Canal` os substitui na fase 3/4, quando cada chamador passar a tratar `cancelado(e)`. Trocar só o
  mecanismo agora faria o cancelamento aparecer como mensagem de erro.
- `ref`/`refs` existem, mas os 177 `getElementById` só somem quando cada aba migrar.
- Versões: `eslint` 10.11.0, `@eslint/js` 10.0.1, `typescript-eslint` 8.70.0, `globals` 17.12.0, `vitest` 4.1.11
  (o 5 pede `@types/node` ≥ 22, e o projeto está no 20) e `happy-dom` 20.14.5. Todas exatas e com mais de duas
  semanas de publicadas. A ESLint 9 foi descartada por já estar sem suporte.

## Verificação

- `npm run verificar`: tipos sem erro, lint sem erro, 33 testes do Vitest e build. Em gzip: JS 81,1 KB e CSS 10,6 KB.
- `pytest -m e2e`: 70 passaram. `pytest -m "not e2e"`: 414 passaram e 1 foi pulado (inclui o teste novo das rotas
  pesadas).

## Próxima

Fase 2, roteador: `core/rotas.ts` com uma tabela única de abas, cada uma com `ler`/`escrever` dos parâmetros, e
testes de ida e volta para todos os endereços, inclusive `#candidato/<cargo>/<nº>`. Saem `abrirPorHash` e os 6 pares
`endereco*`/`aplicarEndereco*`.
