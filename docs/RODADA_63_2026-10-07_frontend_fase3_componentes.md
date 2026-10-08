# Rodada 63 — Front-end, fase 3: componentes (07/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 3. As fases anteriores estão nas rodadas
[60](RODADA_60_2026-10-07_frontend_fase0_andaime.md), [61](RODADA_61_2026-10-07_frontend_fase1_nucleo.md) e
[62](RODADA_62_2026-10-07_frontend_fase2_roteador.md).

## Objetivo

Tirar do `legado.js` os gráficos, os mapas, a tabela, a dica e a exportação, que todas as abas usam e que repetiam
eixos, escalas, legendas e dicas. Eles passam a ser componentes em TypeScript estrito, com testes.

## Entregas (`src/componentes/`, 978 linhas)

- **`escalas.ts`** (puro; a cor é resolvida por um `Resolver`, que nos testes é a identidade):
  - `quebrasQuantis`, `faixa` e `escalaSequencial` (amarelo → vermelho);
  - `classeDivergente`, `limitesPorQuantis`/`limitesPorMaximo` e `escalaDivergente` (subiu/caiu × maior/menor
    que o esperado);
  - `escalaCategorica` (3 cores + "Outros") e `passos`;
  - os tokens `TOKENS_SEQ`/`TOKENS_DIV`/`TOKENS_CAT` num lugar só.
- **`legenda.ts`:** `amostra`, `legendaLinha` e `legendaMapa`. Antes, sete trechos montavam a mesma amostra de cor.
- **`dica.ts`**, as duas dicas do site, uma por situação:
  - `dicaFlutuante`: presa à janela, para o mapa por UF (rodada 35);
  - `comDica`: o ponto mais próximo num gráfico SVG. Agora a dispersão do Perfil × voto também a usa; antes
    reimplementava a mesma busca.
- **`exportar.ts`:** `salvarBlob`, `svgAutonomo`, `baixarGrafico` e `botoesBaixar`. Antes, três gráficos montavam
  à mão os botões "SVG PNG".
- **`tabela.ts`:** `tabelaOrdenavel` tipada, com `ordemInicial` e `ordenar` separadas e testáveis, mais `ficha`.
- **`grafico/`:**
  - `linhas.ts` (evolução na apuração);
  - `dispersao.ts` (Perfil × voto: recebe o formato do indicador e o nome da unidade, em vez de lê-los da aba);
  - `variacao.ts` (dispersão A × B e swing da comparação: recebem o formato da variação).
- **`mapa/`:**
  - `criar.ts`: `criarMapa` com `ResizeObserver`, mais `limparCamadas` e `enquadrarUmaVez`;
  - `camadas.ts`: `criarCamadas({ malhas, fmtDif })` devolve `desenharMapa` (polígonos), `desenharPontos` (locais)
    e `desenharDivergente` (comparação). As malhas vêm do cache da página, injetadas;
  - `tipos.ts`: `MapaApuracao` tipa `_camada`, `_contornos`, `_enquadrado` e `_export`, que os e2e e a exportação
    leem.
- **O legado:** 3.027 → 2.415 linhas (−612). Saíram 27 funções; ficaram só as chamadas, com as dependências
  passadas como argumento.
- **Testes:** 22 testes Vitest novos, 76 no total:
  - escalas: quantis, faixas, divergente nos dois sentidos, categórica, passos;
  - tabela: ordem inicial, pt-BR com acento, clique no cabeçalho, linha clicável;
  - gráficos montados no `happy-dom`: uma marca por ponto e texto dos dados como texto;
  - SVG autônomo e auxiliares puros.

  Os 71 e2e passam sem mudança.

## `ResizeObserver` no lugar de `setTimeout(invalidateSize, 50)`

Um mapa Leaflet criado numa aba escondida nasce com tamanho 0. Antes, quatro `setTimeout(…, 50)` pediam que ele
recalculasse depois de a aba aparecer: em `mostrarAba` (mapas, candidato, comparação) e no bloco Brasil. Era uma
corrida, porque 50 ms podem não bastar num computador carregado na noite da eleição. Agora cada mapa observa o
próprio contêiner e recalcula quando ele muda de tamanho: aba aberta, bloco Brasil movido entre cartões ou janela
redimensionada. O observador é desligado quando o mapa é removido (o mini mapa do candidato é recriado a cada
consulta).

## Pequenas correções junto

- **Gráfico de linhas:** o rótulo na ponta da série mostra o último valor que existe. Antes, um nulo no último
  ponto aparecia como "0,00%".
- **Mapa da comparação por bairro:** ao tirar o mouse, a borda volta a 0,5 px. Antes voltava a 1 px, a dos
  municípios.
- **Enquadramento:** `enquadrarUmaVez` não chama `fitBounds` com limites vazios. Antes isso lançava "Bounds are
  not valid" quando nenhum polígono tinha dado.
- **Dica da dispersão do Perfil × voto:** usa o mesmo posicionamento das outras (deslocada 80 px para cima e 230 px
  à esquerda; antes 70 e 220).

## Desvios da proposta

O mapa por UF do painel (`desenharBrasil`) e a camada de locais sobreposta (`alternarLocais`) continuam no legado,
mas já usam `criarMapa` e `dicaFlutuante`. Os dois são específicos do painel e dos mapas e entram com essas abas na
fase 4.

## Verificação

- `npm run verificar`: tipos, lint, 76 testes do Vitest e build. Em gzip: JS 81,2 KB e CSS 10,6 KB.
- `pytest -m e2e`: 71 passaram, cobrindo cores dos mapas, dicas, exportação e mapa por UF persistente.
  `pytest test_frontend_build.py`: 3 passaram.

## Próxima

Fase 4, as abas, da mais isolada à mais crítica: transferência → perfil → comparação → candidato → mapas → painel
(e alertas e modo TV). Cada uma vai para `abas/<aba>/` com o próprio estado, `refs` no lugar dos `getElementById` e
`Canal` no lugar dos contadores de resposta atrasada.
