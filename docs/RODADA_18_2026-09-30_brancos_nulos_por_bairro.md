# Rodada 18 — Brancos e nulos separados por bairro

30/09/2026 · pedido do usuário: "Adicione brancos e nulos separados por bairro"

## Objetivo

Até aqui, por bairro, só existia "Brancos + nulos (%)". Passam a existir também **Brancos (%)** e **Nulos (%)**:
- no mapa por bairro (aba Mapas);
- na comparação por bairro (aba Comparação), em p.p.

## Decisão: fonte e denominador

- **Fonte:** os votos por seção que o mapa por bairro já usa (`votacao_secao`), com o votável 95 para branco e o 96 para nulo. Não foi preciso usar o `detalhe_votacao_secao` da rodada 17: são os mesmos votos, e reaproveitar o que já está em memória evita outro arquivo.
- **Denominador:** o total de votos do cargo no bairro, com válidos, brancos, nulos e anulados em separado (97). É o mesmo do mapa por município (`PCT_BRANCOS`/`PCT_NULOS` = votos / `VOTOS_TOTAL`) e do "Brancos + nulos (%)" por bairro. Por isso **as partes somam o todo**, o que um teste verifica.
- **Implementação:** um só dicionário, `NAO_VALIDOS` em `apuracao/bairros.py`, liga cada métrica aos seus votáveis: `brancos_nulos` → 95 e 96, `brancos` → 95, `nulos` → 96, nas versões `_pct` do mapa e nas da comparação. `metrica` e `valor_por_bairro` usam esse dicionário em vez do `[95, 96]` fixo.
- **Bairro sem voto branco:** mostra 0%, não "sem dado".

## Entregas

- `apuracao/bairros.py`:
  - `METRICAS` ganhou `brancos_pct` e `nulos_pct`;
  - `METRICAS_COMPARACAO` ganhou `brancos` e `nulos`;
  - `NAO_VALIDOS`.
- `apuracao/web/static/app.js`: as opções Brancos e Nulos ficam ativas nos dois modos Bairros. Na comparação por bairro **todas** as métricas passam a estar disponíveis. No mapa por bairro, só "Seções totalizadas (%)" continua desativada, porque é dado do tempo real.
- **API:** sem rota nova. `/api/mapa/bairros` e `/api/comparacao/bairros` aceitam as métricas novas, e `/api/bairros/anos` passa a listá-las.

## Números reais (RJ, área dos bairros)

**Governador 2022, extremos:**

| Métrica | Mínimo | Máximo |
|---|---|---|
| Brancos | 1,3% (Provetá, Angra dos Reis) | 17,0% (Paraíso, Valença) |
| Nulos | 2,0% (Provetá) | 18,6% (Passagem, Valença) |
| Brancos + nulos | 3,3% (Provetá) | 34,6% (Varginha, Valença) |

Os extremos ficam em bairros pequenos, com poucos locais de votação.

**Dep. Estadual 2022 × Vereador 2024:**

| Métrica | 2022 | 2024 | Diferença |
|---|---|---|---|
| Brancos | 6,74% | 4,65% | −2,09 p.p. |
| Nulos | 6,51% | 5,29% | −1,22 p.p. |
| Brancos + nulos | 13,26% | 9,94% | −3,32 p.p. |

Conferência: 6,74 + 6,51 = 13,25, a menos do arredondamento.

## Verificação

- **`pytest -q`: 105 testes passando** (eram 104).
- **Sem navegador:**
  - bairro A com 7 brancos e 13 nulos em 158 votos; bairro B com 0% (e não nulo);
  - rota com "Nulos (%) — 2024"; "Seções totalizadas" responde 400;
  - na comparação, brancos 7/209 e nulos 13/209, somando o todo.
- **Navegador:**
  - teste novo `test_brancos_e_nulos_por_bairro`: nulos no mapa, com legenda e endereço, e brancos na comparação, com 3,35% na ficha;
  - as asserções que usavam Brancos como exemplo de métrica desativada foram trocadas: no mapa, "Seções totalizadas"; na comparação, nenhuma opção desativada.
- **Sabotagem:** sem `nulos_pct` e `brancos`/`nulos` nas listas do JS, 3 testes de navegador falham. O `app.js` foi restaurado byte a byte.
- **Servidores** reiniciados nas portas 8000, 8022 e 8023; as rotas foram conferidas com os números acima.

## Arquivos

- **Alterados:** `apuracao/bairros.py`, `apuracao/web/static/app.js`, `test_exportar_bairros.py`, `test_exportar_bairros_e2e.py`, `CLAUDE.md` e `docs/INDEX.md`.

## Pendências

- Hora da apuração por bairro: **descartada pelo usuário** (informação irrelevante); não propor de novo.
- 2026 por bairro depende da publicação dos microdados pelo TSE.
