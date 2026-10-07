# Rodada 49 — Religião por área de ponderação e novas variáveis do Censo 2022 no Perfil × voto

06/10/2026 · pedido do usuário: incluir a religião e analisar as outras variáveis do Censo 2022 úteis para o
perfil socioeconômico e demográfico do voto. Plano aprovado em
`~/.claude/plans/prancy-giggling-robin.md`.

**Escolhas do usuário:**
- todas as famílias de variáveis do universo propostas (escolaridade e moradia, saneamento, entorno
  urbanístico, indígenas e quilombolas);
- a área de ponderação só como unidade do Perfil × voto. O mapa por área virou o item 25 do
  [TODO](TODO.md).

## O que o IBGE publica (levantado nesta rodada)

**Universo (todos os domicílios): por setor, e portanto por bairro, local e área.**

| Tema | Arquivo | Variáveis usadas |
|---|---|---|
| Alfabetização | `Agregados_por_setores_alfabetizacao_BR.zip` (142 MB; 735 MB descomprimido) | V00900/V00901: sabe/não sabe ler, 15+ |
| Domicílio 1 | `…caracteristicas_domicilio1_BR.zip` | V00001 (DPPO), V00017 (um morador), V00049 (apartamento) |
| Domicílio 2 | `…caracteristicas_domicilio2_BR_20250417.zip` (784 MB descomprimido; chave **"setor"**) | V00111 (água da rede), V00238 (sem banheiro), V00309/V00310 (esgoto na rede), V00397/V00398 (lixo coletado) |
| Parentesco | `…parentesco_BR.zip` | V01042/V01063 (responsável / responsável mulher) |
| Povos | `…pessoas_indigenas_BR.zip`, `…pessoas_quilombolas_BR.zip` | V01690, V03196 (÷ V0001 do básico) |
| Entorno | `Agregados_por_Setores_Censitarios_Caracteristicas_urbanisticas_do_entorno_dos_domicilios/…/…entorno_moradores_BR.zip` | V05206/07 pavimentação, V05212/13 iluminação, V05215/16 ponto de ônibus, V05221/22 calçada, V05230–33 árvores ("sim" ÷ ("sim" + "não")) |

- **Entorno:** o de 2022 não tem "esgoto a céu aberto" nem "lixo acumulado". Entraram calçada e ponto de ônibus.
- **Óbitos:** existe por setor, mas ficou de fora: é pouco ligado ao voto e cheio de sigilo.

**Amostra (questionário ampliado): só por área de ponderação (AP).**
- **Tabelas:** `Microdados_e_Areas_de_Ponderacao/Areas_de_Ponderacao/tabelas_xlsx.zip` (40 MB, 24/08/2026), 31
  tabelas `TabN_M.xlsx`.
  - **Nomes:** as tabelas 7.2 a 7.4 da lista em PDF **não vêm** no ZIP. Há uma 11.1 (estado conjugal) e uma 12.1
    (tipo de família).
  - **Cobertura:** 14.270 APs em todos os 5.570 municípios (Rio 209, SP 332, RJ 771); mediana de cerca de 10.800
    pessoas de 10+.
- **Setor → AP:** `Documentacao/Áreas de ponderação/Composição das Áreas de Ponderação.xlsx` cobre os **468.097
  setores**, e a ligação é exata.
  - **14.406 códigos:** 136 a mais que as tabelas. São áreas **sem moradores** (252 setores com população zero),
    para as quais o IBGE não publica tabela.

## Entregas

### `apuracao/censo.py` (novo): catálogo de contagens por setor

- **Catálogo:** `INDICADORES` é declarativo. Cada indicador traz o rótulo, o numerador e o denominador como
  (fonte, coluna) e a unidade, "moradores" ou "domicílios", que vira a fonte mostrada na tela. São 15 indicadores.
- **Gravação:** o setor guarda **N_<chave> e D_<chave>**, não o percentual. Assim a soma por bairro, local ou
  área é Σ N ÷ Σ D, nunca uma média de percentuais.
- **Sigilo ("X") por indicador:** o setor sai só daquele indicador; nunca vale zero. A coluna inteira ausente,
  como o entorno fora da pesquisa, também fica sem dado.
- **Funções:** `contagens`, `taxa` e `taxas`, todas sem I/O.
- **Na tela:** a lista de indicadores da página agrupa por fonte: "IBGE — Censo 2022 (domicílios)", "(moradores)",
  "(amostra, área de ponderação)".

### `apuracao/areas_ponderacao.py` (novo): a área de ponderação

- **Leitura:**
  - `ler_tabela`: confere o cabeçalho de cada coluna usada e dá erro claro se o IBGE mudar a tabela. "-" vira
    zero e "X" vira sem dado.
  - `ler_composicao` e `indicadores_amostra`, mais `conferir_brasil`, que compara a soma das APs com a linha
    "Brasil".
- **Derivados** (`ibge._geradores`), nacionais:
  - `ap_composicao.parquet` (setor → AP);
  - `ap_amostra.parquet`, com 14 indicadores:
    - **religião (10+):** católicos, evangélicos, sem religião, espíritas, umbanda e candomblé;
    - **instrução (25+):** superior completo, sem instrução ou fundamental incompleto;
    - **renda domiciliar per capita:** média e mediana;
    - **trabalho:** % de ocupados (14+) e taxa de desocupação;
    - **outros:** % de moradores com internet, % que já morou em outro município (÷ população residente, Tab3_7),
      % dos ocupados a mais de 1 h do trabalho.
- **`PerfilVotoArea(PerfilVotoLocal)`, com `UNIDADE = "area"`:**
  - **Votos:** os locais de votação somados pela AP do setor que **contém** o local.
  - **Perfil do TSE:** média dos locais ponderada pelos eleitores.
  - **Universo:** `perfil_local.agregar` com a composição como ligação, exata. Renda, cor, densidade, favela,
    sexo e idade e o catálogo saem por área.
  - **Amostra:** direto da tabela.
  - **Código da AP:** os 7 primeiros dígitos são o município, então o filtro por município e a regra de ausência
    de candidatura municipal valem sem mudança.

### As três unidades usam o mesmo catálogo

- **Bairro:** `PerfilVoto.censo` junta aos agregados por bairro do IBGE o catálogo somado pelos setores de cada
  bairro. O `CD_BAIRRO` agora vem da malha de setores, lido em `_pontos`. Sem setores (sem rede), o catálogo fica
  sem dado e o resto segue.
- **Local:** `agregar` inclui o catálogo.
- **Área:** como acima.

### Leitura e fontes

- **`_ler_setores_csv` em streaming:** o CSV nacional é lido linha a linha pelo prefixo da UF. Antes, ele ia
  inteiro para a memória, e a alfabetização sozinha passa de 700 MB descomprimida.
- **Ajustes na leitura:** aceita a chave "setor" (domicílio 2); a coluna ausente fica de fora com aviso; não
  repete coluna pedida duas vezes.
- **`ibge.FONTES`:** 9 fontes novas.
  - **Dos setores:** 7 (alfabetização, domicílio 1 e 2, parentesco, indígenas, quilombolas, entorno), com o
    derivado `censo_setores_<UF>`.
  - **Da área de ponderação:** 2 ("fixo"), a composição e as tabelas.
- **`censo_setores_<UF>.parquet`:** é refeito sozinho quando falta coluna, como na rodada 48.

### API e página

- **API:** `perfis["area"]` em `web/app.py`, com `?unidade=area` em todas as rotas `/api/perfil/*`.
- **Opção nova:** "Áreas de ponderação do IBGE (estado inteiro; religião e amostra do Censo)".
- **Unidade:** `unidadePf`/`NomeUnidade` deixam os rótulos "Áreas na análise" e "Área acima da tendência".
- **Endereço:** `#perfil?…&unidade=area`.
- **Nota:** `#pf-nota-area` sobre o erro amostral aparece só nessa unidade.

## Números reais

### Amostra: soma das APs × linha "Brasil"

As 22 colunas de contagem batem: a maior diferença é de **0,02%** ("mais de 240 minutos", Tab10_2); as demais
ficam abaixo de 0,002%.

Brasil, pela Tab4_1: católicos 56,7%, evangélicos 26,9%, sem religião 9,3%.

### Universo: Brasil, soma dos setores (sem sigilo)

468.097 setores, de 11 a 19 s por UF.

| Indicador | Brasil (setores sem sigilo) | Setores sem dado | Referência do IBGE |
|---|---|---|---|
| alfabetizados (15+) | 92,53% | 62.120 | 93,0% |
| apartamentos | 16,32% | 54.864 | — |
| um só morador | 18,97% | 32.022 | — |
| chefiados por mulher | 49,20% | 25.002 | — |
| água da rede | 85,40% | 33.433 | 82,9% (moradores) |
| esgoto na rede | **68,61%** | **111.618** | 62,5% |
| lixo coletado | 92,56% | 101.246 | 90,9% |
| sem banheiro | 0,48% | 47.946 | — |
| rua pavimentada / iluminação / calçada / ponto de ônibus / árvores | 88,8% / 97,7% / 84,3% / 8,8% / 66,2% | 128.550 (fora da pesquisa do entorno) | — |
| indígenas | **0,96%** | 89.694 | 0,83% |
| quilombolas | 0,66% | 23.587 | 0,65% |

**O sigilo enviesa a soma nacional.** O IBGE põe "X" nas contagens pequenas, típicas de setor rural ou pequeno,
e esses setores saem da conta do indicador.
- **Esgoto e lixo:** 24% e 22% dos setores ficam sem dado, justamente os com menos rede. O Brasil sai acima do
  publicado (68,6% × 62,5%).
- **Indígenas:** sai acima também, porque o denominador dos setores com dado é menor.
- **Onde o efeito é pequeno:** na comparação entre unidades urbanas (bairro, local e área na cidade).
- **Onde pesa:** no município pequeno e na área rural, em que sobram poucos setores.

### Sanidade no RJ: Presidente 2022, 1º turno (Pearson, unidades com ≥ 200 válidos)

| Unidade | n | Candidato | evangélicos | católicos | superior (amostra) | renda pc mediana | +1 h até o trabalho | apartamentos | chefiado por mulher |
|---|---|---|---|---|---|---|---|---|---|
| Área, estado | 754 | Bolsonaro | **+0,62** | −0,48 | −0,40 | −0,38 | +0,02 | −0,49 | −0,39 |
| Área, estado | 754 | Lula | −0,49 | +0,40 | +0,22 | +0,21 | 0,00 | +0,32 | +0,36 |
| Área, capital | 199 | Bolsonaro | **+0,69** | −0,57 | −0,41 | −0,38 | **+0,71** | −0,54 | −0,38 |
| Área, capital | 199 | Lula | −0,53 | +0,42 | +0,19 | +0,16 | −0,58 | +0,36 | +0,46 |
| Local, capital | 1.399 | Bolsonaro | — | — | — | — | — | −0,58 | −0,37 |

**O que a tabela mostra:**
- **Religião:** é o indicador mais forte do voto em Bolsonaro no RJ, nas duas escalas.
- **Distância do trabalho:** na capital, mais de 1 h até o trabalho é ainda mais forte (+0,71). Mede a periferia
  distante: Zona Oeste e subúrbios.
- **Erro no plano:** eu esperava "superior × Lula negativo na capital". No RJ, o superior vai **contra Bolsonaro**
  (−0,41), e o de Lula é fraco e positivo. Parte do voto de renda alta foi para outros candidatos no 1º turno.
- **Coerência entre unidades:** os indicadores do universo (apartamentos, responsável mulher) dão correlações
  próximas por área e por local.

**Inferência ECOLÓGICA:** são áreas, não pessoas.

## Arquivos

- **Novos:** `apuracao/censo.py`, `apuracao/areas_ponderacao.py`, `test_censo.py`, `test_areas_ponderacao.py`.
- **Alterados:**
  - **Pacote:** `apuracao/ibge.py` (9 fontes, 2 geradores), `apuracao/perfil.py` (catálogo por bairro, fonte por
    indicador), `apuracao/perfil_local.py` (streaming, `CD_BAIRRO`, catálogo nos setores e no `agregar`).
  - **Site:** `apuracao/web/app.py`, `apuracao/web/static/{index.html,app.js}`.
  - **Testes:** `conftest.py` (catálogo e `CD_BAIRRO` nos setores sintéticos, `escrever_areas`, áreas na fixture
    `site`), `test_perfil_e2e.py` (unidade área).
  - **Documentação:** `docs/TODO.md` (item 25), `CLAUDE.md`.

## Verificação

- **Testes novos:**
  - **Catálogo:** sigilo por indicador, zero × sem dado, soma N/D, fonte ausente, catálogo por local e por bairro,
    e o bairro sem setores.
  - **Leitura:** em streaming (UF, "setor", coluna ausente e repetida).
  - **Tabelas da amostra:** "-"/"X", cabeçalho mudado vira erro, linha Brasil, indicadores e composição.
  - **Unidade área:** votos e perfil do TSE por área, Censo por área, dispersão e municípios.
  - **API e e2e:** a API com `unidade=area` e o e2e da unidade (3 áreas, nota, endereço, troca para local).
- **Suíte completa** (com os e2e): **419 ok**, 1 pulado.
- **Dados reais:** setores das 27 UFs regerados com o catálogo, de 11 a 18 s por UF depois do primeiro download
  das fontes nacionais.

## Decisões e cuidados

- **Amostra só por área:** os indicadores da amostra existem só na unidade área (a lista da API muda com a
  unidade). Neles, sobra o erro amostral, publicado pelo IBGE nos coeficientes de variação e não usado aqui.
- **Local → área:** é pelo setor que **contém** o local, não pelo raio de 800 m da unidade local. A área é
  grande, e o setor que contém decide sem ambiguidade.
- **Duas medidas de instrução:** os rótulos da amostra de instrução trazem "Censo" para não confundir com o
  `pct_superior` do TSE, que mede os eleitores.

## Pendências

1. **Mapa por área de ponderação:** item 25 do TODO.
2. **Sigilo nos indicadores de saneamento:** medir quanto o resultado por local ou área rural muda ao tratar o
   "X" como desconhecido pequeno (ex.: 1 ou 2), em vez de tirar o setor; ou mostrar, por unidade, a fração da
   população coberta pelo indicador.
3. **Coeficientes de variação:** os do IBGE por área poderiam marcar as estimativas frágeis na dispersão.
