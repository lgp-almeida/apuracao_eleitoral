# Rodada 25 — Procedimento de recalibração das margens (projeção e cadeiras)

30/09/2026 · pedido do usuário: documentar o passo manual de recalibração, com o racional, e registrar os resultados e as decisões depois dos ajustes e ensaios.

## Entregas

- **Guia:** `docs/RECALIBRAR_MARGENS.md`, com o racional, o passo a passo, os critérios de aceite e os cuidados.
- **`validar_projecao.py`:**
  - `--anos 2022 2026` junta as eleições;
  - imprime as tabelas ATUAL e PROPOSTA prontas para colar e diz se são iguais;
  - dá a cobertura por ano, também só no RJ;
  - para as cadeiras, valida cada ano com o σ atual e com o proposto;
  - `--ano` continua aceito.
- **Código:**
  - `margem(pct, tabela)`, `cobertura` e `formatar_tabela` em `projecao.py`;
  - `sigma(pct, tabela)`, `calibrar_tabela_sigma` e `projetar_cadeiras(..., tabela_sigma)` em `projecao_cadeiras.py`.
- **Testes:**
  - `test_calibracao.py` passa a ser o único lugar que fixa os valores calibrados; também cobre o formato das tabelas, a saída pronta para colar e a junção de anos;
  - os demais testes leem as constantes do código.

## Ensaio do procedimento com 2022

| O quê | Resultado |
|---|---|
| Margem da projeção | a proposta é **igual** à `MARGEM_PP` atual; cobertura 0,949 (RJ: 0,989) |
| σ das cadeiras | a proposta é **igual** ao `SIGMA` atual |

A validação das cadeiras deu Estadual 404 consolidados (1 errado) e Federal 276 (0 errados).

## Defeito encontrado e decisão

- **Simulações dependiam da ordem de entrada.** O ruído é sorteado por posição, e `entrada_munzona` agrupa sem manter a ordem, então a mesma semente dava resultados diferentes entre execuções (683 consolidados na rodada 22, 680 aqui).
- **Correção:** `simular` ordena agremiações e candidatos.
- **Teste:** `test_mesma_semente_mesmo_resultado_em_qualquer_ordem`, que falha sem a correção.
- **Linha de base depois da correção:** a validação de 2022 foi refeita e agora é **reproduzível**: duas execuções seguidas deram saída idêntica, com o mesmo hash.

  | Cargo | Consolidados | Errados | Em disputa | Eleitos fora das duas listas | Faixas que não cobrem |
  |---|---|---|---|---|---|
  | Estadual | 401 | 1 | 466 | 1 | 0 |
  | Federal | 280 | 0 | 319 | 4 | 1 |
  | **Total** | **681** | **1** | — | 5 | 1 (de 482) |

  O "683 consolidados" da rodada 22 dependia da ordem de entrada; a linha de base passa a ser 681.
- **Decisão de método:** juntar 2022 e 2026 na recalibração. Antes disso, publicar a validação de 2026 com as constantes atuais, que é o primeiro teste fora da amostra.

## Verificação

- **`pytest -q`: 189 testes passando** (eram 183).
- **Novos testes:**
  - `test_calibracao.py`, com 4 testes: constantes fixadas, formato das tabelas, saída pronta para colar e junção de anos;
  - `test_mesma_semente_mesmo_resultado_em_qualquer_ordem`, que falha sem a correção;
  - `test_tabela_sigma_calibrada_a_partir_dos_erros`, calculado à mão, com faixa vazia e erro para a primeira faixa sem dados;
  - `test_margem_por_faixa`, que usa a tabela do código e uma tabela proposta.
- **Guia:** apontado no roteiro da noite (seção "Depois"), no `CLAUDE.md` e no `docs/TODO.md`.

## Pendências

- Recalibrar de fato quando os microdados de 2026 saírem.
