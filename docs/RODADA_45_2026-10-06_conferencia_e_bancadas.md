# Rodada 45 — Lote 4: conferência tempo real × microdados (TODO 16) e bancadas 2026 × 2022 (TODO 15)

06/10/2026 · lote 4 do plano de quitação do TODO ([RODADA_42](RODADA_42_2026-10-06_analise_coleta_e_percentuais.md)),
o primeiro depois dos lotes do 2º turno.

## Item 16 — `conferir_resultado.py` (tempo real × importado)

- **Núcleo:** `apuracao/conferencia.py` compara uma pasta da noite (`dados_2026/oficial[_t2][_UF]`) com a importada
  dos microdados (`historico_<ano>_t<turno>[_UF]`). Compara:
  - **totais:** eleitorado, comparecimento, abstenção, votos, válidos, nominais, legenda, brancos, nulos, anulados,
    sub judice e seções, por cargo × abrangência;
  - **candidatos:** votos, situação (no estado) e destinação de cada um; os que têm voto **só num lado** (nulos
    técnicos, que a divulgação não lista);
  - **cadeiras:** os eleitos de deputado pela distribuição de cada fonte;
  - **avisos** do importado: totais provisórios, destinação ainda não publicada.
- **Saída:** planilha `saidas/<UF>/conferencia_<ano>_t<turno>.xlsx`. Código 0 se tudo bate, 1 se há diferença.
- **Roda sozinho** no `preparar_2026` (e no lote) depois de cada importação, quando existe a pasta da noite.
- **RJ, 1º turno de 2026** (provisório): **reproduz exatamente a conferência manual da rodada 40.**

  | Item | Resultado |
  |---|---|
  | totais | diferentes só no Presidente: válidos/nominais/nulos, 387 votos no estado (774 somando estado e municípios) |
  | candidatos | 12 diferenças, todas do Presidente ("Não informado") |
  | voto só no importado | os nulos técnicos (Presidente 60 linhas; Dep. Federal 133; Dep. Estadual 199) |
  | cadeiras | 46/46 e 70/70 iguais |

## Item 15 — bancadas 2026 × 2022

- **Núcleo:** `apuracao/bancadas.py`, sem I/O, sobre duas `Fonte`.
  - **partidos pela ENTIDADE** (rodada 41): o PRD soma os eleitos de PTB + PATRIOTA; o MISSÃO, no nº 14
    reaproveitado, não herda os do PTB.
  - **trajetória de cada eleito:** reeleito, eleito antes para outro cargo, já tinha concorrido sem se eleger, ou
    novato. A pessoa é identificada pelo nome civil completo, como na rodada 37.
  - **quem saiu:** cada eleito da referência que não voltou ao cargo, e o que fez agora (não concorreu; concorreu
    e não se elegeu; concorreu a outro cargo).
- **Rotas:** `GET /api/bancadas?cargo=` e `/api/bancadas/planilha` (.xlsx: Resumo, Partidos, Eleitos, Saíram).
- **Página:** bloco "Bancadas de deputado × eleição anterior" na aba Comparação, com resumo, três tabelas
  ordenáveis e o botão de salvar. Endereço: `&banc=1&banc_cargo=7`.
- **RJ, 2026 (noite) × 2022:**

  | Cargo | Reeleitos | Eleitos antes para outro cargo | Já tinham concorrido | Novatos | Saíram |
  |---|---|---|---|---|---|
  | Dep. Federal (46) | 21 | 2 | 4 | 19 | 25 |
  | Dep. Estadual (70) | 40 | 0 | 9 | 21 | 30 |

  - **Dep. Federal, por partido:** PL 11 → 15; PSDB 0 → 4; UNIÃO 6 → 1; PCDOB (PC do B em 2022) 1 → 2;
    SOLIDARIEDADE (+ PROS em 2022) 2 → 1.
  - **Dep. Estadual, por partido:** PL 17 → 21; PSD 6 → 9; UNIÃO 8 → 4; PRD (PTB + PATRIOTA) 2 → 1.

## Arquivos

- **Novos:** `apuracao/conferencia.py`, `conferir_resultado.py`, `apuracao/bancadas.py`, `test_conferencia.py`,
  `test_bancadas.py`.
- **Alterados:** `preparar_2026.py` (conferência após importar), `apuracao/web/app.py` (rotas),
  `apuracao/web/static/{index.html,app.js}` (bloco), `test_enderecos.py` (+1 e2e).

## Verificação

- `pytest -q`: 386 testes passando.
- Números reais acima.

## Pendências

- **Conferência oficial:** repetir quando o TSE publicar o detalhe munzona (totais oficiais) e depois do 2º turno.
  O `preparar_2026` faz sozinho.
- **Variação de voto de cada partido no mapa por local:** a segunda metade do item 15 vai para o lote 5 (17a).
