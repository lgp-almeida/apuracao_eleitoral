# Rodada 54 — CDN do TSE entregando a versão antiga; IBGE de DF e TO no lote

07/10/2026 · retomada dos microdados de 2026. O TSE regerou os votos por seção na tarde de 06/10. Esta rodada
baixa as versões novas e liga a vigia, que espera o detalhe e o partido munzona, e roda o lote das 27 UFs.

## O que o TSE tem publicado (07/10, 01h)

| Arquivo | Situação |
|---|---|
| `votacao_secao_2026_BR.zip` | regerado em 06/10 19:22 GMT (161,6 MB; antes 143,4 MB) |
| `votacao_secao_2026_RJ.zip` | regerado em 06/10 19:32 GMT (288,3 MB; antes 289,8 MB) |
| `votacao_secao_2026_AM.zip` | regerado (baixado pelo lote) |
| `detalhe_votacao_munzona_2026.zip`, `votacao_partido_munzona_2026.zip` | **404**: ainda não publicados |

Os totais de 2026 continuam **provisórios**, reconstruídos das seções (rodada 40), nas 27 UFs.

## Bug: a CDN entrega a versão antiga no GET

- **Sintoma:** a 1ª verificação da vigia, 40 s depois de um download, baixou o `_BR` de novo e tentou o `_RJ`, que
  estava "em dia".
- **Causa:** os nós da CDN têm cópias diferentes. O HEAD anunciava `Last-Modified` 06/10 19:22, e o GET devolvia o
  arquivo de 04:58 (`content-range: …/143403125`). Isso foi medido com `curl -r 0-0` na mesma URL, várias vezes.
  - **Efeito:** a proveniência gravava a data velha, e a vigia baixaria 160–290 MB **a cada hora**, para sempre,
    trocando o cache pela versão velha como se fosse nova.
  - **Com um parâmetro na URL** (`?v=<n>`), o GET vem sempre da versão nova.
- **Correção (`microdados.baixar`):**
  - recebe `esperado`, o `Last-Modified` do HEAD;
  - GET mais velho que o HEAD é repetido **uma vez** com `?v=<timestamp>`;
  - se ainda vier velho, o GET é recusado com `TseDataError`. O ZIP, a proveniência e os derivados ficam como
    estavam, e o arquivo fica "tentar de novo" para a próxima verificação;
  - a proveniência guarda a URL sem o parâmetro.
- **Verificado:** a vigia religada registrou `a CDN entregou a versão de … 04:58:20 GMT, o HEAD anuncia … 19:22:49
  GMT` e baixou a de 19:22.

## IBGE de DF e TO deixa de ser "erro" no lote

O IBGE não publica malha de bairros do DF e do TO (404, rodada 48), e o `ibge.preparar` contava isso como falha,
então a etapa `ibge` do lote ficava sempre em "erro". Agora o 404 da `malha_bairros` só gera um aviso no log, e o
derivado `malhas/bairros_<UF>.geojson` não é tentado. Outra falha da malha, como a de rede, continua sendo falha.

## Execução

- **`preparar_2026.py`:** importou o RJ (466 totais, 83.330 linhas de candidatos, 92 municípios).
- **Lote (`baixar_ufs.py`):** 101 → 27 tarefas pendentes. As 27 que restam são `microdados_2026`, "aguardando" os
  munzona. O `divulgacao_t2` "incompleto" é o 2º turno, que só existe em 25/10.
  - **Etapas que faltavam:** eleitorado e perfil de 2022 (22–23 UFs) e `ibge` (27 UFs; DF e TO, depois do
    conserto).
  - **Microdados:** `_RJ` e `_AM` nas versões novas, reimportados.
- **Conferência tempo real × importado, depois da reimportação:**

  | UF | Diferenças | Cadeiras |
  |---|---|---|
  | RJ | só o Presidente: válidos, nominais e nulos, 774 votos em 60 linhas; 12 candidatos | 46/46 e 70/70 |
  | AM | só o Presidente: 164 votos em 16 linhas | 8/8 e 24/24 |

  As diferenças do Presidente esperam a destinação oficial do TSE (rodada 45).
- **Vigia no ar:** `preparar_2026.py --vigiar`, com log em `logs/preparar_2026_vigia.log` e PID em
  `logs/preparar_2026_vigia.pid`. Ela verifica a cada 60 min e só para com os totais oficiais (`FINAL`).

## Arquivos

- `apuracao/microdados.py`: `_get` e `baixar(..., esperado=)`; `preparar` passa o `Last-Modified` do HEAD.
- `apuracao/ibge.py`: `preparar` não conta o 404 da malha de bairros como falha.
- `test_microdados.py`: `test_cdn_com_copia_velha_no_get`.
- `test_ibge.py`: `test_preparar_uf_sem_malha_de_bairros_nao_e_falha`.

## Verificação

- `pytest -q -m "not e2e"`: 365 passados e 1 pulado, antes da correção do IBGE. Depois dela, `test_ibge.py`,
  `test_lote_ufs.py` e `test_microdados.py`: 36 passados.
- Os dois testes novos falham sem a correção (conferido com `git stash`).
- **Defeito no próprio teste novo:** a 1ª versão de `test_preparar_uf_sem_malha_de_bairros_nao_e_falha` foi à rede
  de verdade, porque `ibge.caminho` baixa por `v.download`, e não pela sessão injetada. Agora ela usa
  `download_sem_rede`.

## Pendências

- **Munzona:** quando o TSE publicar o `detalhe_votacao_munzona_2026` e o `votacao_partido_munzona_2026`, a vigia
  importa o RJ com os totais oficiais. Para as outras 26 UFs, rode `baixar_ufs.py --etapas microdados`, ou deixe
  `--vigiar`.
- **`_RJ`:** o download pela vigia caiu duas vezes com a conexão fechada pela CDN, e o lote baixou depois.
  `microdados.baixar` não retoma downloads, e um arquivo de 290 MB que cai é pedido inteiro de novo na verificação
  seguinte.
