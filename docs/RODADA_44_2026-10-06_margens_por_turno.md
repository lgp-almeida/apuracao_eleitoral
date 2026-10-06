# Rodada 44 — Lote 3: margem da projeção por turno, recalibração com 2026 (TODO 4b e 18)

06/10/2026 · lote 3 do plano de quitação do TODO ([RODADA_42](RODADA_42_2026-10-06_analise_coleta_e_percentuais.md)),
o último antes do 2º turno de 25/10.

## Defeito encontrado no ensaio do 2º turno: a leitura dizia "vitória no 1º turno"

- **O defeito:** no ensaio do ES (rodada 43), o alerta e o painel disseram "Governador: vitória **no 1º turno**
  projetada" e depois "confirmada", durante o 2º turno. `projecao.situacao` não conhecia o turno; no 2º turno ela
  também poderia dizer "2º turno projetado".
- **Correção:** `situacao(..., turno)`. No 2º turno a leitura é "vitória projetada/confirmada" ou "indefinido: o
  líder está a menos de uma margem dos 50%". A API tira o turno da coluna `TURNO` dos totais.

## Margem: uma tabela por turno

**Dados:** `validar_projecao.py --anos 2022 2026`, com a apuração refeita seção a seção pela hora de totalização:
- Presidente nas 27 UFs (2022: 1º e 2º turno; 2026: 1º);
- **Governador e Senador em toda UF com `votacao_secao` no cache**: RJ e ES em 2022, RJ em 2026. Antes, só o RJ;
- o turno sem seções é pulado (2026 ainda não teve 2º turno; o RJ não teve 2º turno para Governador em 2022).

**p95 do erro da projeção (p.p.), por faixa de % apurado:**

| Faixa | 1º turno | 2º turno |
|---|---|---|
| até 10% | 7,02 | 8,82 |
| 20% | 3,51 | 3,76 |
| 30% | 2,76 | 3,33 |
| **40%** | **2,11** | **2,98** |
| 50% | 1,78 | 2,07 |
| 70% | 1,08 | 1,17 |
| 90% | 0,42 | 0,35 |

**Decisão:**
- **Uma margem por turno.** No 2º turno, com 2 candidatos, a projeção erra mais no meio da apuração. A margem
  única (2022) cobria só **94,5%** do 2º turno.
- **Por que não uma tabela conjunta:** recalibrar uma única tabela com 2022 + 2026 pioraria o 2º turno (92,7%),
  porque 2026 só tem 1º turno e é mais previsível.

**As tabelas adotadas:**
- **`MARGEM_PP` (1º turno), 2022 + 2026:** `[(10, 7.02), (20, 4.72), (30, 3.51), (40, 2.76), (50, 2.11),
  (60, 1.78), (70, 1.4), (80, 1.08), (90, 0.78), (100, 0.42)]`.
- **`MARGEM_PP_2T` (2º turno), 2022:** `[(10, 8.82), (20, 4.24), (30, 3.76), (40, 3.33), (50, 2.98), (60, 2.07),
  (70, 1.55), (80, 1.17), (90, 0.7), (100, 0.35)]`.

**Teste fora da amostra (critério do guia):** a margem antiga, só de 2022, cobriu **97,2%** das projeções de 2026
(RJ: 100%). A margem de 2022 valeu em 2026, então juntar os anos é seguro.

**p95 por cargo com 30% ou mais apurado (p.p.):**

| Ano | Cargo | Turno | Projeção | Parcial |
|---|---|---|---|---|
| 2022 | Governador | 1º | 1,59 | 1,32 |
| 2022 | Governador | 2º | 1,15 | 0,22 |
| 2022 | Presidente | 1º | 1,85 | 2,98 |
| 2022 | Presidente | 2º | 2,20 | 3,86 |
| 2022 | Senador | 1º | 1,67 | 1,67 |
| 2026 | Governador | 1º | 0,82 | 1,74 |
| 2026 | Presidente | 1º | 1,46 | 2,34 |
| 2026 | Senador | 1º | 0,48 | 0,65 |

## σ das cadeiras: validado com 2026 e mantido

- **Fonte de 2026:** `validar_projecao.py --deputados --anos 2022 2026`. Enquanto o `votacao_partido_munzona_2026`
  dá 404, os votos e eleitos de 2026 vêm do resultado importado com a destinação oficial
  (`historico_2026_t1_RJ`, rodada 40), que reproduz as cadeiras da noite (46/46 e 70/70) — `entrada_oficial`.
- **Fora da amostra (σ de 2022 aplicado a 2026):**

  | Cargo | Consolidados errados | Eleitos fora das duas listas | Faixas que não cobrem |
  |---|---|---|---|
  | Dep. Estadual | **0** | 5 | 1 |
  | Dep. Federal | **0** | 1 | 0 |

- **σ proposto (2022 + 2026):** não melhora. Continua com 0 errados, mas tem mais eleitos fora (federal 2 × 1) e
  mais faixas que não cobrem (estadual 2 × 1).
- **Decisão: manter o `SIGMA`**, registrado em `test_calibracao.py` com `CALIBRADO_COM`.

## Arquivos

- **Alterados:**
  - `apuracao/projecao.py` (`MARGEM_PP` nova, `MARGEM_PP_2T`, `margem(..., turno)`, `projetar(..., turno)`,
    `situacao(..., turno)`);
  - `apuracao/web/app.py` (turno, texto do método);
  - `validar_projecao.py` (Governador/Senador por UF, por turno e cargo, propostas por turno, `entrada_oficial`).
- **Testes:** `test_calibracao.py` (constantes e `test_margem_por_turno`), `test_projecao.py` (leitura do 2º turno).
- **Docs:** `RECALIBRAR_MARGENS.md`, TODO, INDEX, CLAUDE.md.

## Verificação

`pytest -q`: 379 testes passando. Os números acima vêm dos logs de `validar_projecao.py`
(`saidas/erros_projecao_2022_2026.parquet`).

## Pendências

- **Depois de 25/10 e dos microdados do 2º turno:** rodar de novo para juntar 2026 à `MARGEM_PP_2T`.
- **Calibrar Governador em mais UFs:** basta ter o `votacao_secao_2022_<UF>` no cache. Não baixei os das 27 UFs
  (vários GB).
- **Quando o `votacao_partido_munzona_2026` sair:** repetir `--deputados` com os microdados oficiais.
