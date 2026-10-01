# Rodada 21 — Projeção do resultado final durante a apuração

30/09/2026 · pedido do usuário: "Faça a 2, a projeção do resultado final" (item 2 de `docs/TODO.md`)

## Entregas

- **`apuracao/projecao.py`**, domínio puro:
  - `projetar(mun, votos)`: projeção por município;
  - `margem(pct)`: margem calibrada;
  - `situacao(p, vagas, objetivo)`: leitura "definido × indefinido";
  - `entrada_divulgacao`: lê o `ultimo/` do coletor;
  - reconstituição da apuração de 2022 (`secoes_com_hora`, `votos_por_secao`, `estado_em`, `backtest`, `calibrar`, `detalhe_nacional`).
- **`validar_projecao.py`:** refaz a apuração de 2022 seção a seção, mede o erro do parcial e da projeção e gera a calibração da margem. Uso: `python validar_projecao.py [--saida saidas/backtest_projecao.parquet]`, cerca de 50 s.
- **API:**
  - `GET /api/projecao?cargo=1|3|5` traz % do eleitorado apurado, margem, leitura, candidatos (parcial, projeção, mínimo e máximo), os 15 municípios onde faltam mais votos e o método;
  - o cartão majoritário da UF no `/api/painel` ganha o resumo `projecao`, só enquanto a apuração está entre 0 e 100%.
- **Painel:** bloco "Projeção do resultado final" nos cartões de Presidente (RJ), Governador e Senador, com:
  - a leitura em destaque ("vitória no 1º turno projetada", "indefinido…", "2º turno projetado");
  - um gráfico de ponto com faixa: faixa da margem, ponto na projeção e traço no parcial;
  - a linha dos 50% no Governador;
  - "Onde faltam votos", com o eleitorado apurado e os válidos estimados que faltam por município.
- **Núcleo:** o detalhe por seção passou a guardar `DT_PRIM_TOT_PARCIAL_HOR_TSE`, a hora em que cada seção entrou na totalização. Os Parquet do detalhe foram reconvertidos.

## Método

Por município, só com o que o TSE publica em tempo real:

1. **Fração apurada** = eleitorado das seções totalizadas ÷ eleitorado do município (`est`/`te` do JSON, igual a comparecimento + abstenção).
2. **Válidos finais** = válidos atuais ÷ fração apurada. Em município ainda sem apuração: eleitorado × válidos por eleitor já apurado no estado.
3. **O que falta** em cada município segue a participação do candidato já apurada ali; em município sem apuração, a participação no estado.
4. **Projeção** = votos atuais + restantes, somados no estado.

**Leitura** (`situacao`), feita com a margem e sem probabilidades inventadas:

| Cargo | Objetivo | Critério |
|---|---|---|
| Governador | "maioria" | o líder acima de 50% mesmo na margem, ou todos abaixo |
| Senador | "vagas" | os N primeiros fora do alcance do (N+1)º |
| Presidente na UF | "liderança" | só quem vence no estado; o turno é decidido no país |

## Validação e calibração com a apuração real de 2022

Todas as seções do TSE trazem a hora da 1ª totalização. Em 2022 no RJ, as 34.068 seções entraram entre 17h26 e 0h19. Com isso a apuração foi refeita como o tempo real a teria mostrado: 20 momentos (2%, 5%, 10% … 95% do eleitorado) em **58 apurações** (Presidente nas 27 UFs, 1º e 2º turno, e Governador e Senador no RJ), com os 4 primeiros de cada.

Erro absoluto frente ao resultado final, em p.p. (340 medições por faixa):

| % do eleitorado apurado | Parcial, erro médio | Projeção, erro médio | Parcial, p95 | Projeção, p95 |
|---|---|---|---|---|
| 0–10 | 2,49 | 2,39 | 8,16 | 8,07 |
| 10–20 | 1,86 | **1,51** | 6,03 | **4,51** |
| 20–30 | 1,62 | **1,26** | 5,44 | **3,78** |
| 30–40 | 1,45 | **1,02** | 4,75 | **3,10** |
| 40–50 | 1,28 | **0,86** | 3,98 | **2,67** |
| 50–60 | 1,08 | **0,67** | 3,43 | **2,07** |
| 60–70 | 0,89 | **0,55** | 2,72 | **1,55** |
| 70–80 | 0,67 | **0,39** | 2,12 | **1,17** |
| 80–90 | 0,47 | **0,27** | 1,44 | **0,82** |
| 90–100 | 0,24 | **0,13** | 0,87 | **0,43** |

- **Ganho:** a projeção erra de 20% a 50% menos que o parcial a partir de 10% apurado.
- **Margem (`MARGEM_PP`):** é o percentil 95 do erro da projeção em cada faixa: 8,07 · 4,51 · 3,78 · 3,10 · 2,67 · 2,07 · 1,55 · 1,17 · 0,82 · 0,43 p.p. É empírica ("em 2022, 95% das projeções nesta fase erraram menos que isto"), e não um intervalo de confiança.

**RJ à parte** (Presidente nos dois turnos, Governador e Senador; 28 medições por faixa):

| % apurado | Parcial, erro médio | Projeção, erro médio | Projeção, máximo |
|---|---|---|---|
| 0–10 | 0,91 | 1,79 | 6,39 |
| 10–20 | 0,53 | 1,17 | 3,78 |
| 20–30 | 0,63 | 1,22 | 3,78 |
| 30–40 | 0,74 | 0,91 | 3,04 |
| 40–50 | 0,71 | 0,73 | 2,53 |
| 50–60 | 0,67 | **0,59** | 1,95 |
| 70–80 | 0,39 | **0,32** | 1,19 |
| 90–100 | 0,16 | **0,08** | 0,27 |

- **No RJ a projeção só supera o parcial da metade da apuração em diante.** Antes disso ela erra mais: a capital (38% do eleitorado) apura por zonas, e as primeiras seções do Rio não representam a cidade. O tempo real só vai até o município, então não dá para corrigir isso por zona.
- **Decisão:** mostrar **parcial e projeção lado a lado**, com a margem nacional. Ela cobre o RJ em quase todos os casos (o máximo do RJ passa da margem só nas faixas 60–70 e 70–80, por 0,05 e 0,02 p.p.). A nota do painel diz isso.
- **Variantes testadas e descartadas:** misturar a participação do município com a do estado, pesando pela fração apurada ("encolhida", linear ou raiz). Erraram mais que a projeção por município em todas as faixas; a linear quase não melhora o parcial (1,86 → 1,86 em 10–20%).

**Conferência visual:** um retrato da apuração real de 2022 às 19h59 (46% apurado) num servidor temporário, depois removido.

| Candidato | Parcial | Projeção | Final | Leitura |
|---|---|---|---|---|
| Castro (Governador) | 57,15% | 57,05% | 58,69% | "vitória no 1º turno projetada" |
| Romário (Senador) | — | — | — | "eleito (projeção)" |
| Bolsonaro (Presidente, RJ) | — | — | — | "mais votado no estado definido" |

A projeção de Castro ficou dentro da margem de ±2,67.

## Defeitos e cuidados

- **Presidente na UF:** a primeira versão dizia "vitória no 1º turno confirmada" para Bolsonaro no RJ em 2022 (51,1%). O turno é decidido no país, então a leitura para Presidente passou a ser só quem lidera no estado.
- **Votos anulados depois:** no backtest, os votos por seção contam como válidos candidatos anulados depois (Daniel Silveira, Senado 2022), e o "final" é calculado da mesma forma, então a calibração não é afetada. No tempo real, o JSON já separa os anulados sub judice dos válidos.
- **Contraste:** a faixa da margem sumia sobre o trilho. Passou a ser `--seq-2` sobre `--sem-dado`, com o ponto em `--seq-5`.
- **Presidente no Brasil:** fica sem projeção. O coletor só traz os municípios do RJ, e a projeção nacional exigiria as 27 UFs.

## Verificação

- **`pytest -q`: 156 testes passando** (eram 141).
- **`test_projecao.py`**, 14 testes:
  - projeção calculada à mão, com 3 municípios, um sem apuração: o parcial dá 56,25% para A e a projeção dá 41,25%;
  - apuração completa projeta o próprio resultado;
  - margem por faixa;
  - leituras dos três objetivos;
  - reconstituição pela hora das seções;
  - calibração que não cresce com a apuração;
  - API;
  - regressão com dados reais: Governador RJ 2022 com ≥ 95% dos pontos dentro da margem e, da metade em diante, erro menor que o parcial.
- **`test_projecao_e2e.py`:** o bloco no cartão do Governador (margem, leitura, pontos, linha dos 50%, lista intacta, "Onde faltam votos").
- **Sabotagens** (restauradas byte a byte): projeção sem a participação por município, 2 falhas; margem fixa, 4 falhas.
- **Servidores** reiniciados nas portas 8000, 8022 e 8023.

## Arquivos

- **Novos:** `apuracao/projecao.py`, `validar_projecao.py`, `test_projecao.py`, `test_projecao_e2e.py`, `saidas/backtest_projecao.parquet`.
- **Alterados:**
  - `votos_por_local_votacao.py` (`SECTION_DETAILS_OPTIONAL`);
  - `apuracao/web/app.py` e `apuracao/web/static/{app.js,style.css}`;
  - `docs/TODO.md`, `docs/INDEX.md` e `CLAUDE.md`.
- **Cache:** `detalhe_votacao_secao_2022__BR.parquet` (3,08 milhões de linhas, todas as UFs) e os Parquet do RJ reconvertidos.

## Pendências

- **Item 3 do TODO (ensaio geral):** o retrato montado aqui já prova a ideia. Dá para "tocar" a apuração de 2022 hora a hora num diretório de ensaio e deixar o site rodar como na noite da eleição.
- **Cadeiras com projeção:** hoje a distribuição de cadeiras usa os votos parciais. Dá para distribuir sobre os votos projetados dos partidos, mas isso ainda não foi validado.
- **Margem por UF:** a margem é nacional. Com a apuração de 2026 gravada, dá para recalibrar para o RJ.
