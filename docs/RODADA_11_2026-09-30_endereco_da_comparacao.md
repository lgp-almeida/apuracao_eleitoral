# Rodada 11 — Endereço completo na aba Comparação

30/09/2026 · pedido do usuário após a [rodada 10](RODADA_10_2026-09-30_endereco_do_candidato.md)

## Objetivo

Completar os endereços do site: abrir, favoritar e compartilhar uma comparação 2022 × 2026 exatamente como está na tela. Mapas (rodada 09) e Candidato (rodada 10) já faziam isso.

## Formato

```
#comparacao?cargo=7&metrica=partido&partido=PL&ordem=DIF-desc
#comparacao?cargo=3&metrica=candidato&numero_a=22&numero_b=66
```

| Parâmetro | Significado | Se ausente |
|---|---|---|
| `cargo` | 1, 3, 5, 6, 7 | Governador |
| `metrica` | `abstencao`, `comparecimento`, `brancos_nulos`, `brancos`, `nulos`, `eleitorado`, `partido`, `candidato` | `abstencao` |
| `partido` | sigla, com `metrica=partido` | o primeiro da lista |
| `numero_a`, `numero_b` | número do candidato no ano de referência e no atual, com `metrica=candidato` | — |
| `ordem` | ordem da tabela: `<COLUNA>-desc`/`-asc` (`NM_MUNICIPIO`, `VALOR_A`, `VALOR_B`, `DIF`) | `VALOR_A-desc` |

`#comparacao` sem parâmetros continua abrindo a aba com a consulta padrão.

## O que foi feito (só front-end)

- **`enderecoComp()` / `gravarEnderecoComp()`:** regravam o endereço com `history.replaceState` ao desenhar a comparação e ao reordenar a tabela.
- **`aplicarEnderecoComp()`:**
  - aplica cargo e métrica;
  - **espera a lista de partidos do cargo carregar** antes de escolher o partido;
  - preenche os números e a ordem;
  - consulta uma vez, sem disparar também a consulta padrão da aba.
- **Valores desconhecidos no endereço** (cargo, métrica ou partido inexistente) são ignorados, e o controle fica com o valor que já tinha.
- **Botão "Copiar link desta comparação"** (mesma `copiarLink` das outras abas).
- **Troca de aba:** ao sair da aba, o endereço volta a `#<aba>` (a regra agora vale para Mapas, Candidato e Comparação).
- **Sem referência:** se o site não tem eleição de referência (`--comparar-com`), os parâmetros são ignorados.

## Verificação

- **DOM e captura** do Chrome em modo headless, no site do simulado (referência 2022 real):
  - `#comparacao?cargo=7&metrica=partido&partido=PL&ordem=NM_MUNICIPIO-asc` abriu com Dep. Estadual, métrica de partido, "PL (só 2022)" selecionado e a tabela em ordem alfabética (Angra dos Reis, Aperibé, Araruama). Fichas: PL 21,86% em 2022 × 0,00% no simulado = −21,86 p.p.;
  - `#comparacao?cargo=3&metrica=candidato&numero_a=22&numero_b=66` abriu com os campos de número visíveis. Fichas: nº 22 em 2022 (58,69%) × nº 66 no simulado (9,21%).
- `pytest -q`: 51 testes passando. A mudança é só de front-end e **não tem teste automatizado**.

## Situação dos endereços

| Aba | Endereço completo |
|---|---|
| Painel | `#painel` (sem estado a guardar) |
| Candidato | `#candidato?cargo=&numero=&municipio=&ordem=` |
| Mapas | `#mapas?cargo=&metrica=&numero=&momento=&locais=1` |
| Comparação | `#comparacao?cargo=&metrica=&partido=\|numero_a=&numero_b=&ordem=` |

Ainda não vai para o endereço: o formulário da planilha histórica, na aba Candidato.
