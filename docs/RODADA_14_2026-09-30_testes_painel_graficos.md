# Rodada 14 — Testes de navegador para o painel, os gráficos e os mapas

30/09/2026 · pedido do usuário após a [rodada 13](RODADA_13_2026-09-30_testes_dos_enderecos.md)

## Objetivo

Estender os testes de navegador (Chrome via Playwright, marca `e2e`) dos endereços para o conteúdo visual: cartões do painel, gráficos de série, mapas e tema.

## Infraestrutura (refatoração)

- **Fixtures no `conftest.py`:** `site` (**uma instância por sessão** de testes), `navegador`, `pagina`, `nova_pagina` (fábrica com opções de contexto, ex.: `color_scheme="dark"`) e os utilitários `abrir`, `endereco` e `esperar_endereco` saíram de `test_enderecos.py`.
- **Dados mais ricos:** além dos municípios, o **estado** avança a cada totalização (`avancar_uf`), para a série do painel ter 4 pontos. Um candidato a governador recebe o nome `<b id="injetado">CANDIDATO HTML</b>`.
- **Correção no `FakeTSE`:** documentos gerados a partir de outro cargo (Dep. Federal a partir de Dep. Estadual) agora recebem o nome do cargo certo. Antes, os dados de teste mostravam "Deputado Estadual" em dois cartões.

## Testes novos (`test_painel_graficos.py`, 10)

| Teste | O que prova |
|---|---|
| `test_painel_cartoes` | 6 cartões na ordem certa; eleitorado 13.319.487; comparecimento, abstenção, válidos, brancos, nulos e sub judice; barra de progresso; 11 candidatos a governador; "2 vagas" no Senador; bloco de partidos em Dep. Estadual; destinação "Anulado sub judice" visível |
| `test_painel_mostra_html_como_texto` | o nome em HTML aparece como texto e **não** cria elemento na página (`#injetado` não existe) |
| `test_painel_serie_temporal` | gráfico do governador com 3 linhas, 3 rótulos "…%" na ponta e legenda de 3; Presidente (1 ponto) mostra o aviso; dica aparece ao passar o mouse com "das seções" e 3 valores, e some ao sair |
| `test_evolucao_do_candidato` | aba Candidato: 2 linhas (Rio e RJ), legenda com os dois, dica com votos e % de seções |
| `test_mapa_mais_votado_cores_categoricas` | só cores `--serie-1..3`, "Outros" ou "sem dado"; legenda com 3 candidatos + Outros + sem dado |
| `test_mapa_sequencial_e_dica` | cores só da rampa `--seq-1..5`; passar o mouse num município abre a dica com o valor |
| `test_linha_do_tempo_reproduz_ate_o_fim` | ▶ vira ⏸, reproduz até "totalização 4 de 4 (mais recente)", volta a ▶ e tira `momento` do endereço |
| `test_comparacao_mapa_divergente` | cores só da paleta divergente `--div-*`; legenda com aumento, variação menor que ± e redução; 3 fichas |
| `test_modo_claro_e_escuro` ×2 | fundo #f9f9f7 × #0d0d0d e barra de progresso com o passo do tema (#2a78d6 × #3987e5) |

## Achado

A dica do mapa "não abria" no primeiro teste. A investigação mostrou que o site está correto: logo após carregar, o mapa ainda anima o zoom do enquadramento inicial, e o renderizador em canvas do Leaflet ignora o mouse durante a animação. O teste agora espera `!estado.mapa._animatingZoom` e repete o movimento até a dica aparecer.

## Verificação

- `pytest -q`: **71 testes passando** em cerca de 15 s (51 sem navegador + 20 de navegador). Os testes de navegador rodaram 3 vezes seguidas sem instabilidade (20/20 em cerca de 10,5 s cada).
- **Sabotagem do JavaScript** (restaurado byte a byte depois):
  - série sem linhas → falham `test_painel_serie_temporal` e `test_evolucao_do_candidato`;
  - nome do candidato inserido com `innerHTML` → falha `test_painel_mostra_html_como_texto`.

## Arquivos

- **Novo:** `test_painel_graficos.py`.
- **Alterados:** `conftest.py` (fixtures de navegador compartilhadas, `avancar_uf` no cenário e nome do cargo nos documentos gerados), `test_enderecos.py` (usa as fixtures compartilhadas), `CLAUDE.md` e `docs/INDEX.md`.
