# Rodada 62 — Front-end, fase 2: roteador (07/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 2. As fases anteriores estão na
[RODADA_60](RODADA_60_2026-10-07_frontend_fase0_andaime.md) e na [RODADA_61](RODADA_61_2026-10-07_frontend_fase1_nucleo.md).

## Objetivo

Antes, os endereços `#<aba>?…` eram tratados em quatro lugares, cada um de um jeito:

- `abrirPorHash`, uma cadeia de `if` por aba;
- seis funções `endereco*`, umas devolvendo o hash, outras só a consulta;
- três funções `gravarEndereco*`;
- nove `history.replaceState` soltos.

A lista das abas aparecia repetida. Agora há uma tabela só.

## Entregas

- **`src/core/rotas.ts`** (puro, sem DOM):
  - `ABAS`, o tipo `Aba` e `ehAba`;
  - `lerEndereco(hash)` → `{ aba, params }`. Converte o formato antigo `#candidato/<cargo>/<nº>[/<município>]` em
    parâmetros. Só o 1º `?` separa, então um `?` dentro do valor continua no valor;
  - `escreverEndereco(aba, params)`, que não deixa `?` sobrando;
  - `abaDoEndereco(hash)`.
- **`src/core/roteador.ts`**, a classe `Roteador`. Cada aba registra uma `RotaAba` com três campos opcionais:
  - `escrever`: estado da aba → parâmetros;
  - `aplicar`: parâmetros → estado (e abre a aba);
  - `enderecoAoMostrar`: o painel grava o endereço completo ao aparecer, porque destaque e modo TV são estado.

  O roteador tem quatro operações:
  - `abrir(hash)`: aplica os parâmetros, ou só mostra a aba; endereço desconhecido não faz nada;
  - `gravar(aba)`: regrava só a aba aberta e só se o endereço mudou;
  - `endereco(aba)`: o link de "Copiar link";
  - `aoMostrar(aba)`: o ajuste do endereço ao trocar de aba.

  O acesso a `location`/`history` vem injetado (`Ambiente`), e é isso que permite testar o roteador no Vitest.
- **No legado:**
  - as seis funções `endereco*` viraram `parametros*`, que devolvem `URLSearchParams`;
  - a aplicação do painel e a do candidato, antes dentro de `abrirPorHash`, viraram `aplicarEnderecoPainel` e
    `aplicarEnderecoCandidato`;
  - a tabela é registrada uma vez, no fim do arquivo (`roteador.registrar(...)`);
  - saíram `abrirPorHash`, `gravarEnderecoCandidato`/`Mapa`/`Comp`, `enderecoTf` e os 9 `history.replaceState`
    (sobra 0);
  - o `legado.js` caiu de 3.051 para 3.027 linhas.
- **Testes:**
  - Vitest, 21 testes novos (54 no total): ida e volta sem perda para endereços reais de todas as abas, formato
    antigo, endereço vazio ou desconhecido, `?` no valor, e `abrir`/`gravar`/`endereco`/`aoMostrar` do roteador;
  - e2e novo, `test_troca_de_aba_e_link_colado_com_a_pagina_aberta` (71 no total). O botão da aba reescreve o
    endereço e o painel leva o destaque. Com a página aberta, um link colado abre a aba pedida, inclusive no formato
    antigo, e uma aba desconhecida não muda nada.

## Mudanças de comportamento (pequenas)

- O formato antigo `#candidato/<cargo>/<nº>` passa pelo mesmo caminho do novo. Depois da consulta, a planilha e o
  resultado × eleição anterior são aplicados (fechados, já que o endereço não os pede) e o endereço é regravado no
  formato novo, como o e2e já esperava.
- `#painel?destacar=` é decodificado uma vez só, por `URLSearchParams`. Antes passava também por
  `decodeURIComponent`. Os destaques com espaço e vírgula (ex.: "PC do B") continuam iguais.
- A análise do Perfil × voto e o cálculo da transferência só regravam o endereço com a aba deles aberta, como
  as demais abas. Na prática eles só rodam com a aba aberta.

## Desvios da proposta

A proposta previa sumir com os seis pares `endereco*`/`aplicarEndereco*`. O despacho, a forma do endereço, a
gravação e o link já saíram deles e estão na tabela única. O que sobra em cada `parametros*`/`aplicarEndereco*` é
leitura e escrita dos controles da própria aba (DOM), que vai para `abas/<aba>/` na fase 4, junto com o resto da aba.

## Verificação

- `npm run verificar`: tipos, lint, 54 testes do Vitest e build.
- `pytest -m e2e`: 71 passaram. `pytest test_frontend_build.py test_site.py`: 18 passaram. O Python não mudou.

## Próxima

Fase 3, componentes: base de gráfico (escalas, eixos, passos, dica) para linhas, dispersão, variação e swing;
mapa (criação com `ResizeObserver` no lugar de `setTimeout(…, 50)`, camadas coroplética/pontos/divergente,
escalas e legenda); tabela ordenável; uma dica só; exportação.
