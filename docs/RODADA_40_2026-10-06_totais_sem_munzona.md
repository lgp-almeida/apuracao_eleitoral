# Rodada 40 — Resultado de 2026 sem esperar o detalhe por município-zona; gatilho de importação corrigido

06/10/2026 · pedidos do usuário:
- "Como verificar se os microdados de 2026 já estão liberados?" e "Não é melhor usar o baixar_ufs.py e depois o
  preparar_2026.py".
- "Vamos especular. Qual o conteúdo de 'Detalhe por município-zona'. Não são informações calculadas a partir de
  dados contidos em 'Votos por seção – RJ'…".
- "/plan … verificar se existem incompatibilidades entre elas e, principalmente, rever o TODO e o INDEX…
  Seja criterioso e aprofundado." Decisões na aprovação: execução real **só RJ**; destinação/situação dos
  candidatos vindas do `votacao_candidato_munzona` **em todo histórico**.

## Contexto

Em 06/10 a CDN do TSE já tinha quase tudo de 2026:

| Arquivo | Situação |
|---|---|
| votos por seção RJ | 290 MB |
| votos por seção BR | 51 MB |
| detalhe por seção | 171 MB |
| candidatos | 3 MB |
| `votacao_candidato_munzona` | 316 MB |
| perfil | 212 MB |
| `detalhe_votacao_munzona` | 404 |
| `votacao_partido_munzona` | 404 |

Sem o detalhe munzona, o importador não tinha os totais oficiais. Além disso, havia o defeito (A).

## (A) O gatilho de importação nunca importava 2026 sozinho

**Defeito:**
- **Memória vazia:** o "já tem dados" começava vazio a cada execução: `anteriores = set()` em
  `preparar_2026.main` e `ao_chegar(args, set())` em `Lote.microdados`.
- **Vigia parava cedo:** o `--vigiar` encerrava com votos UF/BR e detalhe por seção.
- **Etapa marcada OK cedo:** a etapa do lote virava OK nesse momento e passava a ser pulada.

Quando o detalhe munzona saísse numa execução posterior, `PARA_IMPORTAR ⊆ tem` dava falso: **2026 nunca seria
importado sem intervenção**.

**Correção:**
- **Estado pelo disco:** o "já chegou" vem do disco (`microdados.no_cache`).
- **Totais disponíveis:** `fonte_dos_totais(com_dados)` decide entre "munzona" (oficiais), "secoes"
  (reconstruídos, provisórios) e None.
- **Reimportação:** qualquer mudança em um arquivo de `PARA_IMPORTAR` reimporta.
- **`--vigiar`:** só encerra com `FINAL`, que inclui o detalhe e o partido munzona.
- **Lote:** só fica OK com os totais **oficiais** importados; o provisório fica `AGUARDANDO`, e por isso o
  `--vigiar` do lote e as novas execuções voltam a ele.

Mais duas falhas do mesmo tipo, achadas na execução real:
- **`garantir_importacao`:** arquivos no cache sem importação (baixados por uma execução antiga ou que caiu)
  agora são importados, comparando o `status.json` do destino com o melhor total disponível.
- **Falha de rede num arquivo** (06/10, "Connection reset by peer" no meio do lote): antes, abortava tudo e os
  arquivos que já tinham chegado não eram convertidos nem analisados, e na execução seguinte apareciam "em dia".
  Agora cada arquivo tem seu próprio tratamento: o que falhou fica "tentar de novo" (`com_erro`), a reação roda
  com o que chegou e o lote marca ERRO com o nome do arquivo.

  Os 3 arquivos da execução que caiu, anterior à correção, tiveram a conversão, o IBGE e a transferência feitos
  à mão uma vez.

## (B) Totais reconstruídos das seções

O detalhe munzona tem 47 colunas. As **contagens** saem da soma das seções; a **classificação** do voto
(válido/anulado/nulo técnico) depende da situação jurídica de cada candidato na totalização.

Regra (`historico.detalhe_de_secoes`):

| Voto | Vira |
|---|---|
| votável 95 | branco |
| votável 96 | nulo |
| votável 97 | anulado em apuração separada |
| proporcional < 100 de partido COM candidato no cargo | legenda válida |
| proporcional < 100 de partido SEM candidato | nulo técnico |
| nominal com destinação "Válido*" | válido |
| nominal com destinação "Anulado sub judice" | sub judice |
| nominal com outra destinação | anulado |
| número fora do candidato_munzona (negado antes da eleição) | nulo técnico |
| cargo SEM nenhuma linha de destinação publicada | válido, com aviso no status |

**Fontes:**
- aptos, comparecimento e abstenção: `detalhe_votacao_secao`;
- destinação e situação: `votacao_candidato_munzona` (`historico.destinacao_oficial`), **só do cache**, sem
  rede.

**Validação, RJ 2022, 1º e 2º turno, 5 cargos, mun/uf/br:**
- **Votos por categoria:** 732 combinações zona × cargo (cargos estaduais) com **diferença 0** em válidos,
  nominais, legenda, brancos, nulos, nulos técnicos (1.608.536), anulados (286.752) e sub judice (38.713).
- **Importação completa** (466 + 94 linhas de totais, 109.262 + 188 de candidatos, 5.755 de partidos):
  candidatos e partidos **idênticos**. Nos totais, só duas colunas diferem, ambas explicadas:
  - **`SECOES_TOTAL`:** o detalhe por seção lista só as principais (34.068). O oficial soma as agregadas
    (+2.482 = 36.550). Só entra no "% de seções totalizadas", que é 100% no histórico.
  - **`DT_TOTALIZACAO`:** o oficial do 1º turno traz **01/12/2022**, uma retotalização dois meses depois. O
    reconstruído traz a última seção da noite (`DT_PRIM_TOT_PARCIAL_HOR_TSE`, convertida para data antes do
    máximo, para acertar na virada de mês).
- **Desempenho:** a reconstrução leva cerca de 74 s no RJ (Presidente com o Brasil inteiro). `importar(...,
  detalhe=)` reaproveita para os dois turnos.

**API:** `historico.importar(..., totais_de="munzona"|"secoes", detalhe=None)`. O nome não é `totais`, para não
esconder a função `totais()`. CLI: `importar_resultado_historico.py --totais secoes`. O `status.json` ganha
`totais`, `totais_de` e `avisos`, e o `ambiente` recebe o sufixo "· totais provisórios". Ao trocar o provisório
pelo oficial, `preparar_2026` grava `saidas/<UF>/conferencia_totais_<ano>_t<turno>.csv`
(`historico.conferir_totais`).

## Destinação e situação do candidato_munzona em todo histórico (decisão do usuário)

O candidato_munzona regerado em 01/10/2026 ainda traz Castro 2022 como `INAPTO`, mas com destinação **Válido** e
situação **ELEITO**: o resultado da totalização se preserva ali, ao contrário do `consulta_cand`.
`candidatos_e_partidos(..., destinacao=)` passa a usar esse resultado.

**Reimportação do RJ (2014, 2018, 2022, dois turnos) e das 27 UFs de 2022:**
- totais, votos e eleitos idênticos;
- DESTINACAO mudou em 138 candidatos de 2022 (80 "Nulo técnico", 53 "Anulado", 3 "Anulado sub judice", e Castro
  "Válido") e em 188 de 2018 (nulos técnicos);
- 2014 não teve mudança.

**Defeitos antigos encontrados ao reimportar:**
- **Agremiação por cargo:** a agremiação do partido era escolhida só pelo `NR_PARTIDO`, sem o cargo, e dependia
  da ordem das linhas. PSB e MDB de deputado herdavam a coligação de Governador ("A VIDA VAI MELHORAR",
  "Coligação Brasil para Todos"); foram 372 linhas em 2022. Agora a escolha é por (cargo, partido) e
  determinística.
- **Votos de partido:** só os nominais **válidos** contam para o partido, quando há a destinação oficial. Esta
  tabela alimenta as cadeiras do histórico quando o `votacao_partido_munzona` falta. Em 2026, os 338 mil votos
  sub judice de Dep. Estadual mudavam **3 eleitos**; com a correção, 70/70.

## 2026 real (RJ)

- **Comando:** `python baixar_ufs.py --etapas microdados --ufs RJ`.
  - A 1ª execução caiu por rede, o que levou à correção acima. A 2ª baixou o resto, converteu e importou
    `dados_2026/historico_2026_t1_RJ` com **totais provisórios**.
  - Situação da etapa: `aguardando` ("falta no TSE: detalhe_munzona, partido_munzona").
  - Transferência 2022 → 2026 gravada em `saidas/RJ/transferencia_2022_2026.csv` (18 linhas).
- **Conferência com a noite** (`dados_2026/oficial`, totalização final do TSE), 465 linhas de totais (estado e
  92 municípios × 5 cargos):
  - **idênticos:** eleitorado, comparecimento, abstenção, votos, brancos, legenda, anulados, sub judice e seções
    (37.675);
  - **válidos/nulos idênticos** em Governador, Senador, Dep. Federal e Dep. Estadual;
  - **Presidente: +387 válidos no estado (0,004%)**. O TSE ainda não publicou a destinação do Presidente: o
    membro `_BR.csv` do candidato_munzona tem só o cabeçalho e o `_BRASIL.csv` não tem o cargo 1. O
    `consulta_cand` também vem sem situação para os 14 candidatos. Os nominais contam como válidos, mas o nº 28
    (387 votos) não aparece na divulgação, ou seja, é nulo técnico. O aviso está no `status.json`.
- **Candidatos** (cargos 3, 5, 6 e 7, 82.185 pares candidato × abrangência): votos, situação e destinação com
  **0 diferenças**. Há 332 candidatos só no reconstruído, todos nulos técnicos (Dep. Federal 133 / 48.446 votos;
  Dep. Estadual 199 / 4.180), que a divulgação não lista.
- **Cadeiras** (recuo para o `ultimo/`, porque o partido munzona ainda dá 404, com a falha memorizada por 10 min
  em vez de um 404 a cada pedido): Dep. Federal **46/46** e Dep. Estadual **70/70**, com votos e vagas por
  agremiação iguais aos da noite e 0 divergências com a situação oficial.
- **Achado:** a divulgação em tempo real calcula o "% dos válidos" do candidato sobre **válidos + anulados sub
  judice** (diferença < 10⁻⁹ em todos os cargos). O histórico usa os válidos oficiais. Não mexi; ficou no TODO 23.

## Arquivos

- **`apuracao/microdados.py`:** `fonte_dos_totais`, `FINAL`, `no_cache`, `com_erro`, erro por arquivo, pasta do
  cache criada.
- **`preparar_2026.py`:** `ao_chegar(a)`, `importar`, `garantir_importacao`, conferência e parada por `FINAL`.
- **`apuracao/lote_ufs.py`:** OK só com os totais oficiais.
- **`apuracao/historico.py`:** `destinacao_oficial`, `detalhe_de_secoes`, `load_detalhe_secoes`,
  `cargos_com/sem_destinacao`, `conferir_totais`, `importar(totais_de, detalhe)`, destinação e situação do
  munzona, agremiação por cargo, partido com só os nominais válidos.
- **`apuracao/web/app.py`:** memória de falha do `entrada_munzona`.
- **`importar_resultado_historico.py`:** opção `--totais`.
- **Testes:**
  - `test_microdados.py` (+5): vigia provisório → oficial, execução nova, cache sem importação, falha de rede
    num arquivo, `fonte_dos_totais`;
  - `test_historico.py` (+8): regras de reconstrução, importação provisória, conferência, só do cache, cargo sem
    destinação, cadeiras sem repetir o 404, Castro "Válido/Eleito", partido só com os válidos;
  - `test_lote_ufs.py` (+1).
- **Docs:** esta rodada, INDEX, TODO, ROTEIRO e CLAUDE.md.

## Decisões e desvios do plano

- **Nome do parâmetro:** `totais_de` em vez de `totais`, para não esconder a função `totais()`.
- **Ensaio não refatorado:** o `ensaio.carregar_2022` lê do mesmo arquivo nome de urna, federação e `SQ`, que a
  tabela de destinação não carrega. Trocar o leitor mexeria num caminho validado sem ganho.
- **Fora do plano, mas necessários pela execução real:** cargo sem destinação publicada, erro por arquivo,
  `garantir_importacao`, agremiação por cargo e partido só com os válidos.

## Verificação

- `pytest -q`: 361 testes passando (360 antes do último teste desta rodada).
- Comparações reais acima: 2022 reconstruído × oficial; 2014–2022 antes × depois da reimportação; 2026
  reconstruído × noite; cadeiras 2026 × noite.

## Complemento: `preparar_2026.py --so-verificar`

Pedido do usuário: "Como monitorar o TSE de forma rápida? Só para saber se os dados estão disponíveis?".

- **O que faz:** só os 8 HEADs (`md.verificar`), sem baixar, importar nem gravar estado.
- **Tabela:** status na CDN, data e tamanho no TSE, situação e ação.
- **Resumo:**
  - o que ainda dá 404;
  - o que já saiu e não foi baixado (ou foi atualizado pelo TSE);
  - se o resultado está importado com totais provisórios ou oficiais;
  - o que falta para os totais oficiais.
- **Exclusiva com `--vigiar`.** Teste: `test_so_verificar_nao_baixa_nem_importa`.

## Pendências

- **Quando o TSE publicar o `detalhe_votacao_munzona_2026` e o `votacao_partido_munzona_2026`:** rodar
  `python baixar_ufs.py --etapas microdados --ufs RJ`, ou deixar `--vigiar`. Ele reimporta com os totais oficiais
  e grava `saidas/RJ/conferencia_totais_2026_t1.csv`.
- **Destinação do Presidente** (membro `_BR` do candidato_munzona): quando sair, a mudança no ZIP dispara a
  reimportação e os 387 votos do nº 28 viram nulo técnico.
- **Outras UFs:** só o RJ foi baixado (decisão do usuário). O mesmo comando com `--ufs` cobre as demais; os
  arquivos nacionais já estão no cache.
- **TODO:** 23 (denominador do "% dos válidos") e 4b (recalibração com 2026, dados disponíveis).
