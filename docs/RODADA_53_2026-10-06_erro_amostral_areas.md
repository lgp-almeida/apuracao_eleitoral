# Rodada 53 — Erro amostral dos indicadores da amostra por área de ponderação

06/10/2026 · última pendência da série das áreas de ponderação (rodadas 49–52). Religião, instrução, trabalho,
internet, migração e deslocamento vêm da **amostra** do Censo 2022. Numa área pequena, ou para uma característica
rara, a estimativa pode ser pouco confiável, e o mapa não mostrava isso.

## Fonte: os coeficientes de variação do IBGE

- **Arquivo:** `Microdados_e_Areas_de_Ponderacao/Documentacao/Áreas de ponderação/Coeficientes de variação e de
  regressão.xlsx` (214 KB).
  - **Abas:** uma por UF, região e Brasil.
  - **Conteúdo:** os coeficientes da regressão do CV contra o tamanho da estimativa, e a tabela de **CV (%) por
    tamanho da estimativa** (de 100 a 200 milhões), para pessoas e para domicílios. O −1 marca tamanho que não
    existe na UF.
- **Relação:** ln CV é linear em ln tamanho, com inclinação ≈ −0,5. A interceptação publicada não reproduz a tabela
  diretamente (há um fator constante ≈ 7), então uso a **tabela**, interpolada em log-log. Ela reproduz exatamente
  os valores publicados nos pontos dela.
- **Faixas do IBGE:**

  | CV | Leitura |
  |---|---|
  | até 15% | boa precisão |
  | de 15% a 30% | use com cautela |
  | acima de 30% | pouco confiável |

## Entregas (`apuracao/areas_ponderacao.py`)

- **Fonte nova** no `ibge.py`: `ap_cv` ("fixo"), com o derivado `ibge_censo2022/ap_cv.parquet` (UF, TAMANHO, CV, só
  das 27 UFs). É gerado por `ler_cv`/`tabela_cv`, que dá erro se faltar a tabela de uma UF.
- **`coeficiente_variacao(contagens, tabela_uf)`:** interpolação log-log; fora da tabela, a reta das pontas;
  contagem ≤ 0 ou nula dá CV nulo. `faixa_cv` devolve a faixa.
- **Contagens na amostra:** `ap_amostra.parquet` passa a guardar o **numerador** estimado de cada indicador em
  percentual (`N_<chave>`). O arquivo antigo é refeito sozinho.
- **Que CV:** o do indicador é o do numerador, as pessoas com a característica na área. É a prática do IBGE para
  proporções.
- **Sem CV:**
  - a renda média e a mediana, porque o arquivo não dá CV para média de valores;
  - os indicadores do universo e do TSE, que não têm erro amostral.
- **`PerfilVotoArea.cv(indicador)`:** CV por área, com a tabela da UF.
- **`mapa(…, "perfil")`:** num indicador da amostra, cada área traz `cv`. A resposta inclui `cv_limites` = [15, 30]
  e conta as áreas `areas_cv_fragil` e `areas_cv_cautela` na `cobertura`.

## Página

- **Área frágil (CV > 30%):** cor mais clara (opacidade 0,35) e **borda tracejada**. O estilo volta certo depois
  do mouse.
- **Dica:** "CV x% — boa precisão / use com cautela / pouco confiável".
- **Legenda:** aviso com o número de áreas frágeis, que vai também para a **exportação** (`_export.extras`, escrito
  no PNG/SVG).
- **Nota da área:** conta as áreas frágeis e as de cautela.

## Números reais (RJ, 771 áreas)

| Indicador | CV mediano | CV máximo | Cautela (15–30%) | Pouco confiável (> 30%) |
|---|---|---|---|---|
| católicos | 5,7% | 17,7% | 1 | 0 |
| evangélicos | 6,2% | 23,2% | 5 | 0 |
| sem religião | 8,5% | 58,3% | 78 | 5 |
| superior completo (amostra) | 11,5% | 49,5% | 212 | 6 |
| taxa de desocupação | 17,8% | 130,0% | 439 | 79 |
| espíritas | 21,6% | 423,9% | 348 | **225** |
| umbanda e candomblé | 24,4% | 423,9% | 359 | **270** |

As religiões frequentes são confiáveis em quase todas as áreas. Espíritas e umbanda/candomblé, raros, são pouco
confiáveis em cerca de um terço das áreas do RJ, e a desocupação pede cautela na maioria. Antes, esses valores
apareciam no mapa como se fossem tão firmes quanto os outros.

## Verificação

- **Testes unitários:**
  - **`ler_cv`:** com planilha sintética no formato do IBGE (Brasil e regiões fora; −1 ignorado; aba de UF
    faltando dá erro).
  - **Interpolação:** dentro e fora da tabela, contagem zero ou nula, e as faixas.
  - **`PerfilVotoArea.cv`:** 50 × 4.000 evangélicos estimados viram CV frágil × bom; sem CV para renda nem para o
    universo.
  - **Mapa:** `cv` e as contagens na `cobertura`, e nada disso em indicador do TSE.
- **e2e:** só a área com 50 evangélicos fica tracejada; o aviso aparece na legenda, na nota e na exportação; com um
  indicador do TSE, nenhuma marcação. O teste passou 3 vezes seguidas.
- **Suíte completa:** **434 ok**, 1 pulado.

## Arquivos

- **Pacote:** `apuracao/areas_ponderacao.py`, `apuracao/ibge.py`.
- **Site:** `apuracao/web/static/app.js`.
- **Testes:** `conftest.py` (contagens e tabela de CV sintéticas), `test_areas_ponderacao.py`,
  `test_mapa_locais_e2e.py`.
- **Documentação:** `CLAUDE.md`, `docs/RODADA_52_…` (pendência apontada para cá).

## Pendências

1. **Perfil × voto por área:** a dispersão ainda não marca os pontos frágeis. Poderia dar opção de excluir áreas
   com CV > 30% da correlação.
