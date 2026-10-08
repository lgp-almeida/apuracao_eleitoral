# Rodada 66 — Front-end, fase 4 (parte 3): aba Mapas (07/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 4, no padrão de aba das rodadas
[64](RODADA_64_2026-10-07_frontend_fase4_transferencia_perfil.md) e [65](RODADA_65_2026-10-07_frontend_fase4_comparacao_candidato.md).

## Objetivo

Migrar a aba Mapas, a de maior regra de controles. Ela tem quatro detalhes (município, bairro, local e área de
ponderação), cinco camadas, a linha do tempo da noite e a camada de locais sobreposta. O Painel, com alertas e modo
TV, fica para uma rodada própria: é o último e o mais crítico na noite da eleição.

## Entregas

- **`abas/mapas/`** (680 linhas, contando as peças compartilhadas abaixo):
  - `regras.ts` (puro): `metricasPermitidas`, `metricaPadrao` e `controles(detalhe, camada, metrica)`, que dizem que
    campos aparecem e se o nº vale; `consultaCamada` monta os parâmetros por local ou área, ou diz o que falta.
    Antes, essa lógica estava espalhada em `prepararDetalhe` e `ajustarControlesLocais` e misturada com o DOM;
  - `linha-tempo.ts`: a classe `LinhaDoTempo` (`receber`, `noFim`, `noPassado`, `irParaOFim`, `parar`),
    `indiceAte` (o momento pedido pelo endereço) e `rotuloMomento`;
  - `notas.ts` (puro): o texto de cobertura e de leitura de cada detalhe e camada;
  - `locais-sobrepostos.ts`: os pontos de todos os locais, com popup;
  - `tipos.ts` e `index.ts`.
- **Compartilhados novos:**
  - `dados/malhas.ts`, com as malhas de municípios, bairros e áreas uma vez por página. A falha não fica no cache.
    Substitui `estado.geo`, `geoBairros` e `geoAreas` e as funções `malha*`;
  - `componentes/mapa/exportar.ts`: `corpoExportacao` (puro) e `exportarMapa`. O botão "Baixar mapa" das abas Mapas
    e Comparação passa por ele.
- **Contrato da aba:**
  - `ModuloAba.atualizar()`: o ciclo de 60 s chama o da aba aberta. O `tick` não tem mais `if` para os mapas;
  - o contexto ganhou `ano()`.
- **Testes e2e:** `window.__apuracao.abas` dá o módulo de cada aba migrada, por exemplo
  `__apuracao.abas.mapas.estado.detalhe`. Uma linha de `test_mapa_locais_e2e.py` foi trocada para usá-lo; as
  asserções são as mesmas.
- **No legado:** 1.310 → 833 linhas (−477). Sobram o Painel, os alertas, o modo TV, o seletor de UF e o arranque da
  página.
- **Testes:** 9 Vitest novos, 109 no total:
  - regras dos controles em cada detalhe e camada, e a consulta da camada ou o que falta;
  - linha do tempo: acompanhar o fim, não atropelar quem vê o passado, momento pedido pelo endereço;
  - notas de bairros, locais e áreas (reta, variação, CV da amostra);
  - malhas (um pedido; a falha não fica) e o corpo da exportação por camada.

## Comportamento

- **Um pedido novo de mapa cancela o anterior**, qualquer que seja o detalhe. Antes, só os mapas por local e por
  área tinham isso, com o contador `pedidoMapa`. Uma troca rápida de detalhe ou de cargo no mapa por município ou
  por bairro podia deixar a resposta atrasada desenhar por cima.
- **Mapa por bairro com métrica de candidato** sem nº digitado avisa "Informe o número de um candidato.", como
  antes. A busca pelo nome continua só no mapa por município.

## Verificação

- `npm run verificar`: tipos, lint, 109 testes do Vitest e build.
- `pytest -m e2e`: 71 passaram, incluindo endereço e linha do tempo, os quatro detalhes, as cinco camadas, as cores
  e a exportação. `pytest test_frontend_build.py`: 3 passaram.

## Próxima

Fase 4, parte 4: o Painel (cartões, projeção, cadeiras, destaque, presidente por UF, série), os alertas, o modo
TV, o "o que mudou", a situação do coletor e o seletor de UF. Depois disso o `legado.js` fica só com o arranque e
some na fase 6.
