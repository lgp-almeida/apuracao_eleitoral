# Rodada 65 — Front-end, fase 4 (parte 2): abas Comparação e Candidato (07/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 4, no padrão de aba da
[RODADA_64](RODADA_64_2026-10-07_frontend_fase4_transferencia_perfil.md).

## Objetivo

Migrar as duas abas seguintes, ambas com blocos que abrem e fecham e têm endereço próprio, e que juntas tinham
quatro controles de resposta atrasada escritos à mão: `bancPedido`, `varPedido`/`varEmCurso`/`varMostrado` e
`histPedido`/`histEmCurso`/`histMostrado`.

## Entregas

- **`abas/comparacao/`** (583 linhas):
  - `index.ts`: info da referência, campos por métrica, municípios × bairros, mapa divergente, tabela e endereço;
  - `bancadas.ts` e `variacao.ts`: um bloco cada, com `escrever`/`aplicar` próprios que o `index` compõe no
    endereço;
  - `formatos.ts`: `rotuloEntidade`, `rotuloPartidoBairros`, `anosBairros`, `escolhaInicial`, `MAX_VAR`;
  - `tipos.ts`.
- **`abas/candidato/`** (461 linhas):
  - `index.ts`: consulta, tabela por município, evolução e mini mapa;
  - `historico.ts` (resultado × eleição anterior) e `planilha.ts`: um bloco cada;
  - `desenhar.ts`: `textoCadeira`, fichas, `celulaHistorico`;
  - `tipos.ts`.
- **Compartilhados novos:**
  - `dados/candidatos.ts`: a lista de candidatos por cargo com cache, usada pelas abas Candidato e Mapas. Antes era
    `estado.candidatosCache` mais três funções soltas. Agora guarda a promessa, então dois pedidos simultâneos viram
    um só, e uma falha não fica no cache;
  - `core/cadeiras.ts` (`STATUS_CAD`);
  - `core/formatos.ts` ganhou `fmtVariacao`, o antigo `fmtComp`, que três abas usam.
- **Contexto das abas** (`core/aba.ts`) ganhou `turno()`, `malhas` e `registrarMapa(nome, mapa)`. Cada aba cria as
  camadas de mapa com as malhas que a página fornece, e registra o mapa pelo nome que a exportação
  (`data-mapa="compMapa"`) e os e2e (`__apuracao.estado.compMapa`) usam.
- **`ModuloAba.preparar()`:** carga na abertura da página. A comparação descobre se há eleição de referência e o
  candidato preenche a lista do cargo.
- **No legado:** 1.985 → 1.310 linhas (−675). `consultarCandidato`, `preencherLista` e `resolverNumero` viraram
  linhas de uma só, porque o painel e a aba Mapas ainda os chamam.
- **Testes:** 13 Vitest novos, 100 no total:
  - comparação: `fmtVariacao`, partidos pela entidade (renomeado, só num ano), escolha inicial da variação,
    bancadas, tabela da variação com Butler;
  - candidato: busca por nº ou nome, cache que agrupa pedidos e esquece falhas, `datalist`, texto da cadeira nos
    quatro casos e células do histórico.

## Comportamento

- **Pedidos que agora cancelam o anterior:** a consulta do candidato e a série de evolução. Antes, cliques rápidos
  em municípios ou candidatos deixavam a resposta mais lenta desenhar por cima da mais nova. Também cancelam o
  anterior a comparação (mapa e tabela), as bancadas, a variação e o histórico.
- **Blocos de cálculo pesado** (variação e histórico): continuam sem repetir um pedido idêntico já a caminho, e
  sem piscar "Calculando…" quando o resultado na tela já é o pedido.
- **Erro na comparação:** o mapa da comparação limpa camada, contornos e `_export` (= `null`), como antes. O teste
  `test_exportar_bairros_e2e` confere isso.

## Verificação

- `npm run verificar`: tipos, lint, 100 testes do Vitest e build.
- `pytest -m e2e`: 71 passaram, incluindo endereços, exportação por bairro, variação, bancadas, histórico e alertas
  do candidato. `pytest test_frontend_build.py`: 3 passaram.

## Próxima

Fase 4, parte 3: as abas Mapas e Painel, com alertas e modo TV. O legado fica com 1.310 linhas, quase todas
dessas duas abas.
