# Rodada 30 — Transferência de votos do 1º para o 2º turno (e abstenção extra)

30/09/2026 · pedido do usuário: "Siga para o item 9" (item 9 de `docs/TODO.md`)

## Objetivo

Se houver 2º turno para Governador em 25/10, estimar, por local de votação, para onde foram os votos dos eliminados e medir a abstenção extra. O método é inferência ecológica, com as ressalvas dela. Antes, validar com Presidente 2022 (1º e 2º turno).

## Método (`apuracao/transferencia.py`)

- **Categorias:**
  - 1º turno: os dois finalistas, cada eliminado com ≥ 1% dos válidos na área (até 5), "Outros", branco/nulo e abstenção;
  - 2º turno: finalista A, finalista B, branco/nulo e abstenção.
  - Em cada unidade e turno, as categorias somam o eleitorado apto; a abstenção fecha a conta.
- **Modelo:** y_i ≈ x_i · B, em que x e y são a composição de cada unidade nos dois turnos (frações do eleitorado) e B é a matriz de transferência (linhas somam 1, B ≥ 0). B é estimada por mínimos quadrados ponderados pelo eleitorado, com as restrições.
- **Solução numérica** (só numpy; não há scipy):
  - FISTA com projeção no simplex e reinício adaptativo;
  - a matriz do problema é mal condicionada (10⁴ nas seções e 10⁶ nos municípios do RJ); sem o reinício, 5.000 iterações ainda erravam 0,1 p.p., e com ele o erro fica abaixo de 10⁻⁵;
  - o algoritmo é vetorizado para resolver todos os estratos de uma vez, iterando só os que ainda não convergiram.
- **Estratos:** uma matriz por zona eleitoral (unidade = seção) ou por município (unidade = local), combinadas pelo eleitorado de cada categoria.
  - Estratos com menos de 30 unidades vão juntos para "restante".
  - Cada local recebe o padrão da sua região: a tabela "votos dos eliminados, por região".
  - O motivo foi a validação: a estratificação reduziu o erro fora da amostra (tabela abaixo).
- **Municípios como unidade:** os eliminados viram um grupo só ("Eliminados").
  - Com 92 unidades e os eliminados separados, 15 das 28 células ficavam no limite; por exemplo, "Ciro → 100% Lula".
  - Agrupados, 7 de 20 ficam no limite.
- **Intervalo de 95%:** bootstrap por bloco (local de votação; as seções do mesmo local não são independentes), com 200 replicações. Cada replicação parte da estimativa e para em 1.500 iterações, o que muda o intervalo em menos de 0,7 p.p. nos locais e 0,001 p.p. nas seções.
  - É o intervalo percentil, estendido até a estimativa quando as restrições deixam o bootstrap todo de um lado dela.
  - Mede só a variação amostral, não o viés de agregação.
- **Validação cruzada:** 5 dobras por bloco. O modelo, treinado em 4/5 dos locais, prevê a composição do 2º turno do 1/5 restante (p.p. do eleitorado, ponderado), e o erro é comparado com o de:
  - uma matriz única, sem estratos;
  - o **swing uniforme**: cada finalista, branco/nulo e abstenção mudam na unidade o mesmo que mudaram na área.
- **Abstenção extra:**
  - 1º → 2º turno na área, e por unidade (as maiores);
  - "quem votou no 1º e se absteve no 2º", pela coluna abstenção da matriz.
- **Resíduos:** onde o finalista A foi melhor ou pior do que a matriz prevê, por unidade.

## Validação com 2022 (Presidente, RJ) e 2024 (prefeito)

### Erro fora da amostra (p.p. do eleitorado, média das 4 categorias do 2º turno)

| Área e unidade | Unidades | Estratos | Modelo | Matriz única | Swing uniforme |
|---|---|---|---|---|---|
| Presidente 2022, RJ, seção | 34.068 | 175 zonas | **1,54** | 1,64 | 1,86 |
| Presidente 2022, RJ, local | 4.813 | 38 municípios | **0,86** | 0,98 | 1,19 |
| Presidente 2022, RJ, município | 92 | — | **0,58** | 0,58 | 0,74 |
| Prefeito 2024, Niterói, seção | 1.305 | 4 zonas | 1,86 | 1,84 | 2,94 |
| Prefeito 2024, Petrópolis, seção | 801 | — | 2,01 | 2,02 | 2,83 |

O modelo sempre erra menos que o swing uniforme, com ganho de 17% a 37%. A estratificação ajuda no estado inteiro e é neutra dentro de um município. Os erros de níveis diferentes não se comparam entre si: unidades maiores são mais lisas.

### Matriz de Presidente 2022 no RJ (para onde foi cada grupo; IC 95%)

| 1º turno (% do eleitorado) | Bolsonaro | Lula | Branco/nulo | Abstenção |
|---|---|---|---|---|
| **Por seção** | | | | |
| Bolsonaro (37,7%) | 98,7 | 0,4 | 0,3 | 0,6 |
| Lula (30,0%) | 2,5 | 92,3 | 1,3 | 3,9 |
| Tebet (2,9%) | 35,3 (33,7–36,8) | 45,6 (43,1–46,0) | 15,1 | 4,0 |
| Ciro (2,4%) | 34,8 (33,2–36,7) | 36,8 (34,9–38,2) | 18,1 | 10,3 |
| Branco/nulo (3,5%) | 25,8 | 16,3 | 45,9 | 11,9 |
| Abstenção (22,7%) | 4,7 | 7,1 | 0,4 | 87,7 |
| **Por local** | | | | |
| Tebet | 27,5 (24,7–30,3) | 48,5 (44,4–51,1) | 16,8 | 7,2 |
| Ciro | 29,1 (24,3–32,8) | 39,0 (34,7–42,4) | 23,9 | 8,0 |

- **Abstenção:** 22,74% → 22,24% (−0,50 p.p.) no estado. Pela matriz das seções, cerca de 152 mil eleitores de Lula no 1º turno se abstiveram no 2º, e cerca de 207 mil abstencionistas do 1º votaram em Lula no 2º.
- **Viés de agregação** (`--comparar-niveis`, a mesma matriz com seções, locais e municípios): a maior diferença para as seções é de 18,6 p.p. nos locais e 63,2 p.p. nos municípios, sempre nos grupos pequenos. Por município, o destino dos eliminados (juntos) foi 20,5% Bolsonaro e 61,2% Lula; por seção, 36,4% e 39,2%. **Conclusão: por município a leitura é frágil, e a página avisa.**
- **Caminho da noite (tempo real):** com os dados que o coletor gravou nos dois turnos (`historico_2022_t1` e `_t2`), as contagens por município são **idênticas** às dos microdados agregados, e a matriz também (diferença 0,0). Há um teste para isso.

### Prefeito 2024 (os dois 2º turnos do RJ)

- **Niterói** (seção): +4,40 p.p. de abstenção. Talíria Petrone → Rodrigo Neves 89% (84–92%). Cerca de 17,8 mil eleitores de Neves no 1º turno se abstiveram no 2º, que ele venceu.
  - Por local (134 unidades), 10 células ficam no limite; **em município pequeno, use a seção**.
- **Petrópolis** (seção): +6,70 p.p. de abstenção. Bomtempo → Hingo 65%, e Eduardo → Hingo 68%.

### Dados sintéticos com a matriz conhecida (testes)

Os eleitores de cada seção passam do 1º para o 2º turno por sorteio multinomial com a matriz da zona (duas zonas diferentes).

- **Precisão:** a análise recupera a matriz com erro ≤ 5 p.p. nos grupos com ≥ 2% do eleitorado (≤ 10 p.p. no grupo de 0,4%).
- **Intervalo:** cobre a verdade em 89% das células.
- **Por zona:** cada zona recebe o seu padrão.
- **Validação:** modelo < matriz única < swing uniforme.

## Entregas

- **`apuracao/transferencia.py`:** `carregar_microdados` (votacao_secao + detalhe, os dois turnos; presidente no arquivo nacional), `montar_unidades` (seção, local ou município), `unidades_divulgacao` (tempo real, do coletor), `analisar`, `validacao_cruzada`, `comparar_niveis`, `resumo` e `para_planilha`.
  - `calcular` guarda os microdados carregados em memória.
  - Prefeito exige município: o número e o nome do candidato só valem dentro dele.
- **`transferencia_turnos.py`** (linha de comando): microdados (`--ano --cargo --nivel --municipio`), tempo real (`--dados-1t --dados-2t`), `--comparar-niveis` e `--saida` .xlsx (aba Matriz com IC e validação; aba "Por unidade" com observado × previsto, abstenção extra e destino dos eliminados no estrato).
- **API:**
  - `GET /api/transferencia/info`: anos no cache e se há tempo real, no site do 2º turno, cujo 1º turno é `<ambiente>` ou `<nome>_t1`;
  - `GET /api/transferencia/municipios`: em prefeito, só os municípios com 2º turno;
  - `GET /api/transferencia`: resultado guardado em cache (a versão dos dados entra na chave, no tempo real), com um cálculo por vez;
  - todas em `ROTAS_PESADAS`: com o site na rede, só a própria máquina.
- **Aba "1º → 2º turno" no site:**
  - fonte (microdados ou tempo real; o tempo real já vem escolhido quando existe), ano, cargo, unidade e área;
  - fichas: unidades, regiões com matriz própria, abstenção 1º → 2º, erro fora da amostra × swing e células no limite;
  - uma barra empilhada por grupo do 1º turno, em cores fixas: finalista A em azul, B em laranja, branco/nulo em cinza claro e abstenção em cinza escuro, com legenda e rótulo ≥ 7%; ao passar o mouse, o intervalo e os eleitores;
  - matriz completa com IC, destino dos eliminados por região, maior abstenção extra e onde o finalista A foi melhor ou pior que o previsto;
  - aviso de **leitura frágil** no nível município ou com ≥ 6 células no limite;
  - endereço `#transferencia?fonte=&ano=&cargo=&nivel=&municipio=` e "Copiar link".

## Correções no caminho

1. **Nomes de prefeito trocados:** em Niterói 2024 apareciam Ramagem e Tarcísio Motta, candidatos do Rio de Janeiro. O número do candidato se repete entre municípios, e o nome vinha do estado inteiro.
   - **Correção:** `carregar_microdados` filtra o município antes.
   - **Teste:** prefeito sem município é recusado.
2. **NaN em Petrópolis 2024:** sem nenhum voto em "Outros", a linha dava NaN e a API caía.
   - **Correção:** grupos vazios saem da matriz, e o bootstrap usa `nanpercentile`.
   - **Teste:** `test_grupo_sem_eleitores_sai_da_matriz`.
3. **Celular:**
   - as 6 abas não quebravam linha;
   - a grade do painel (cartões com mínimo de 420 px) fazia a página rolar na horizontal a 390 px, **defeito anterior a esta rodada**, na tela principal da noite;
   - agora o painel e a aba nova cabem em 390 px (`min(420px, 100%)` e `min-width: 0`).
4. **`el({style: {"--cor": …}})`** não aplicava propriedades CSS personalizadas (`Object.assign` as ignora); passou a usar `setProperty`.
5. **Desempenho:** a primeira versão levava mais de 10 min por seção (FISTA estrato a estrato em Python e `np.add.at` a cada replicação). Agora:
   - os produtos por unidade são calculados uma vez e somados com `reduceat`;
   - o FISTA roda em lote, só nos estratos ativos;
   - o bootstrap parte da estimativa;
   - resultado: seção em ~20 s, local em ~12 s e município em ~6 s, na primeira vez; depois vem do cache.

## Arquivos

- **Novos:**
  - `apuracao/transferencia.py`;
  - `transferencia_turnos.py`;
  - `test_transferencia.py`: 15 testes, 2 deles com 2022 real se estiver no cache;
  - `test_transferencia_e2e.py`: 2 testes no Chrome.
- **Alterados:**
  - `apuracao/web/app.py`: rotas e `ROTAS_PESADAS`;
  - `apuracao/web/static/{index.html,app.js,style.css}`: aba, `el` com variáveis CSS, abas e painel no celular;
  - `docs/TODO.md`, `docs/INDEX.md`, `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `CLAUDE.md`.

## Verificação

- **Testes:** `pytest -q` → **262 passando** (duas vezes seguidas), contra 246 na rodada 29.
- **Números:** os da validação acima, obtidos com os comandos do roteiro sobre o cache de 2022 e 2024.
- **Visual:** conferido no Chrome, claro a 1.400 px, escuro a 1.400 px (tempo real) e celular a 390 px sem rolagem horizontal.

## Pendências

- **2026:** na noite de 25/10, a aba mostra o tempo real (municípios, leitura frágil). A estimativa boa vem com os microdados do 2º turno: `preparar_2026.py --vigiar` baixa os do 1º turno. Depois de 25/10, é preciso estender o vigia para os microdados do 2º turno. Enquanto isso, basta o ZIP no cache e esta aba.
- **Nomes de urna de prefeito:** saem pelo cadastro de candidatos do ano; o de 2024 não está no cache, e aparece o nome completo.
- **Validação externa:** com pesquisas de intenção de voto por voto no 1º turno, não foi feita; não há verdade individual publicada.
- **Tabela da aba Perfil × voto:** ainda passa da largura do celular (defeito anterior, fora do escopo).
- **Próximo item do TODO:** 10, o mapa por local de votação. Os resíduos e o destino dos eliminados por local desta rodada são candidatos naturais a camadas dele.
