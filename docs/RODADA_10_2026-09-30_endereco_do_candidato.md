# Rodada 10 — Endereço completo na aba Candidato

30/09/2026 · pedido do usuário após a [rodada 09](RODADA_09_2026-09-30_endereco_do_mapa.md)

## Objetivo

Levar para o endereço tudo o que define a consulta na aba Candidato, como já foi feito no mapa: abrir, favoritar e compartilhar a consulta exatamente como está na tela.

## Formato

```
#candidato?cargo=7&numero=13713&municipio=60011&ordem=VOTOS-desc
```

| Parâmetro | Significado | Se ausente |
|---|---|---|
| `cargo`, `numero` | candidato consultado (obrigatórios) | — |
| `municipio` | código TSE do município da caixa "Evolução na apuração" | o município com mais votos do candidato |
| `ordem` | ordem da tabela por município: `<COLUNA>-desc` ou `-asc` (`NM_MUNICIPIO`, `VOTOS`, `PCT_VALIDOS`, `POSICAO_MUN`, `PCT_SECOES_TOTALIZADAS`) | `VOTOS-desc` |

O formato antigo `#candidato/<cargo>/<número>[/<município>]` continua aceito.

## O que foi feito (só front-end: `apuracao/web/static/app.js`)

- **`estado.cand`** guarda cargo, número, município e ordem. `enderecoCandidato()` e `gravarEnderecoCandidato()` regravam o endereço com `history.replaceState` (sem poluir o histórico) quando:
  - a consulta abre;
  - o município da evolução muda (seletor ou clique na tabela);
  - a tabela é reordenada.
- **`tabelaOrdenavel`** aceita `opcoes.ordem` (ordem inicial) e `opcoes.aoOrdenar` (aviso a cada troca). A aba Comparação, que usa a mesma função, não mudou.
- **`abrirPorHash`** entende `#candidato?…`. Ao trocar de aba, o endereço volta a ser `#<aba>`, tanto para Mapas quanto para Candidato.
- **Botão "Copiar link desta consulta"** na caixa de evolução. A função `copiarLink` passou a ser compartilhada com o mapa.

## Verificação

- **Visual e DOM** (Chrome em modo headless, demonstração do TSE falso com 3 municípios):
  - `#candidato?cargo=3&numero=68&municipio=60011&ordem=NM_MUNICIPIO-asc` abriu com o Rio no seletor, a evolução do Rio × RJ desenhada e a tabela em ordem alfabética (Niterói, Quissamã, Rio);
  - o formato antigo `#candidato/3/68/58653` abriu com Niterói selecionado.
- `pytest -q`: 51 testes passando. A mudança é só de front-end e **não tem teste automatizado**.

## Limitações

- O formulário da planilha histórica (ano, cargo, município, comparar com) não vai para o endereço.
- A aba Comparação ainda não guarda os controles no endereço (`#comparacao` só abre a aba).
