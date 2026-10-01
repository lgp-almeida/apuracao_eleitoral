# Rodada 19 — Perfil do eleitorado × voto por bairro, Censo 2022 do IBGE e transferência entre eleições

30/09/2026 · pedido do usuário: "faça o perfil do eleitorado × voto por bairro, incluindo todos os cargos: presidente, governador, senador, deputados federal e estadual. Se possível calcular a correlação (estatística) entre o perfil do voto por bairro e o voto do candidato. Verifique os dados do IBGE por setor censitário e a transferência entre eleições"

## Entregas

- **Nova aba "Perfil × voto"** (`#perfil`), com um ponto por bairro do IBGE:
  - **eixo Y:** % dos válidos de um **candidato** ou de um **partido**. Vale para qualquer ano com microdados e **todos os cargos**: Presidente (1º e 2º turno), Governador, Senador, Dep. Federal, Dep. Estadual e também Prefeito e Vereador;
  - **eixo X:** um indicador de perfil (TSE ou Censo) **ou o voto em outra eleição** (transferência);
  - **filtros:** município, mínimo de votos válidos no bairro (padrão 200) e ponderação pelos votos válidos.
- **Resultados na tela:**
  - fichas com n de bairros, **Pearson r** e sua força, **IC 95%**, **Spearman ρ**, **p-valor**, **R²** e **inclinação** (efeito de +1 unidade de X, em p.p.);
  - gráfico de dispersão com reta de tendência, cor pelo sinal do resíduo, dica ao passar o mouse e download em SVG/PNG;
  - **tabela de correlação com todos os 10 indicadores**, da mais forte para a mais fraca; clicar numa linha leva o indicador ao eixo X;
  - os 10 bairros mais **acima** e os 10 mais **abaixo** da tendência.
- **Endereço completo:** `#perfil?ano=&turno=&cargo=&numero=|partido=&x=<indicador>|voto[&x_ano=&x_turno=&x_cargo=&x_numero=|x_partido=][&municipio=<IBGE>]&min_validos=[&ponderar=true]`, com "Copiar link".
- **API:** `/api/perfil/info`, `/api/perfil/candidatos`, `/api/perfil/partidos`, `/api/perfil/correlacoes` e `/api/perfil/dispersao`. O erro 400 vale para parâmetro inválido; o 404, para ano sem microdados, como 2026 até a publicação.

## Fontes de perfil (verificadas)

### TSE — `perfil_eleitor_secao_<ano>_<UF>.zip` (eleitores inscritos por seção)

| Ano | Tamanho (RJ) | Observação |
|---|---|---|
| 2022 | 64 MB | 12.827.296 eleitores; contagem em `QT_ELEITORES_PERFIL` |
| 2024 | 198 MB | mesmo layout |
| 2026 | 212 MB | **já publicado** (antes da eleição); a contagem passa a se chamar `QT_ELEITORES`; raça/cor passa a vir preenchida |

- **Indicadores usados:**
  - % com superior completo;
  - % sem fundamental completo (analfabeto, lê e escreve, fundamental incompleto);
  - % de 16 a 24 anos;
  - % com 60 anos ou mais;
  - % de mulheres.
- **Como são somados:** pelos locais de votação que caem em cada bairro, usando a **mesma ponte local → bairro** dos votos. Assim o perfil descreve exatamente quem vota naquele bairro.
- **Raça/cor do TSE: não usada.** Vem vazia (`#NE`/não informado) em 2022 e 2024. Em 2026, **82,9%** dos eleitores estão como "não informado"; é uma autodeclaração recente e parcial, portanto uma amostra enviesada. Cor/raça vem do Censo.

### IBGE — agregados do Censo 2022

O pedido era verificar os dados **por setor censitário**. O IBGE publica os agregados por setor **e também já agregados por bairro**, com o **mesmo `CD_BAIRRO` da nossa malha**. Para o recorte de bairro, portanto, não é preciso somar setores.

| Pasta no FTP do IBGE | O que há | Uso |
|---|---|---|
| `Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/` | básico (pessoas, domicílios, área, moradores/domicílio), cor ou raça, alfabetização, demografia, características do domicílio 1–3, parentesco, óbitos, indígenas/quilombolas | **básico** e **cor ou raça** |
| `…Rendimento_do_Responsavel/` (versão 08/05/2026) | renda média e mediana do responsável, por setor, bairro, distrito, subdistrito e município | **renda por bairro** |
| `…/Agregados_por_Setor_csv/`, `malha_com_atributos/` | as mesmas tabelas por **setor censitário** | não usado (ver pendências) |
| Favelas e comunidades urbanas, entorno dos domicílios, religiões etc. | outras publicações | não usado |

- **Indicadores usados:**
  - renda média do responsável (`V06004`) e renda mediana (`V06006`);
  - % de pretos e pardos (`V01318` + `V01320` sobre o total de `V01317`–`V01321`);
  - densidade (`V0001` / `AREA_KM2`);
  - moradores por domicílio (`V0005`).
- **Cobertura no RJ:** os três arquivos cobrem os **1.509 bairros** da malha. A renda existe em 1.489 bairros. Cor ou raça está sob **sigilo ("X")** em 9 bairros, que viram nulo e ficam fora da análise, nunca entram como zero.
- **Download:** cerca de 3,5 MB, uma única vez, para `cache_tse/ibge_censo2022/`. O resultado fica em `censo_bairros_RJ.parquet`.
- **Atenção:** o IBGE põe a data da versão no nome do arquivo. Se republicar, basta atualizar `CENSO_ARQUIVOS` em `apuracao/perfil.py`.

## Estatística

- **Implementação:** numpy, sem scipy, que não está no venv. Os testes conferem com `np.corrcoef`, `np.polyfit` e o posto do pandas.
- **Pearson:** opcionalmente ponderado pelos votos válidos do bairro. Com peso, entra o **n efetivo de Kish**, (Σw)²/Σw², que alarga o IC quando poucos bairros grandes dominam.
- **Spearman:** Pearson dos postos médios; robusto a extremos e invariante a transformação monotônica, como a renda.
- **IC 95% e p-valor:** pela transformação **z de Fisher** (aproximação normal). Para Spearman, usa-se o erro-padrão de Fieller, √(1,06/(n−3)). Com n de 150 a 900 bairros, a aproximação é boa.
- **Reta e resíduo:** reta de mínimos quadrados; resíduo = voto observado − voto previsto pela reta.
- **Correlação ecológica:** compara **bairros, não pessoas**. Associação não é causa e não diz como cada eleitor votou; a página avisa isso.

## Resultados reais (RJ, bairros com ≥ 200 votos válidos)

As duas correlações mais fortes de cada um dos três mais votados:

| Eleição | Candidato | Mais forte | Segunda | n |
|---|---|---|---|---|
| Presidente 2022, 1º turno | 22 Bolsonaro | densidade r = −0,25 | moradores/domicílio r = +0,25 | 910 |
| | 13 Lula | densidade r = +0,22 | moradores/domicílio r = −0,19 | 910 |
| | 15 Simone Tebet | % pretos e pardos r = −0,63 | renda mediana r = +0,62 | 909 |
| Governador 2022 | 22 Cláudio Castro | % sem fundamental r = **+0,58** | % superior r = −0,52 | 905 |
| | 40 Marcelo Freixo | % sem fundamental r = −0,52 | renda mediana r = +0,49 | 905 |
| Senador 2022 | 222 Romário | % sem fundamental r = +0,46 | densidade r = −0,41 | 904 |
| | 400 Alessandro Molon | % sem fundamental r = **−0,75** | % superior r = +0,75 | 904 |
| | 142 Daniel Silveira | % sem fundamental r = −0,50 | % pretos e pardos r = −0,49 | 904 |
| Dep. Federal 2022 | 5077 Talíria Petrone | % superior r = +0,74 | % sem fundamental r = −0,66 | 907 |
| | 2212 Eduardo Pazuello | % superior r = **+0,75** | renda média r = +0,73 | 907 |
| Dep. Estadual 2022 | 50007 Renata Souza | renda mediana r = +0,60 | renda média r = +0,59 | 908 |
| | 22022 Douglas Ruas | moradores/domicílio r = −0,19 (ρ = −0,35) | — | 909 |
| Prefeito 2024, Rio | 55 Eduardo Paes | % sem fundamental r = +0,54 | % superior r = −0,29 | 152 |

- **Presidente:** no RJ, a divisão Lula × Bolsonaro por bairro se associa pouco ao perfil (|r| ≤ 0,25).
- **Governador, Senado e deputados:** a escolaridade separa fortemente.
- **Deputados:** nos votados na capital, Pearson e Spearman às vezes divergem (ex.: Douglas Ruas). Isso sinaliza relação não linear ou puxada por poucos bairros; vale olhar o gráfico.

## Transferência entre eleições (X = voto em outra eleição)

| Transferência | Área | n | r | ρ | Inclinação | R² |
|---|---|---|---|---|---|---|
| Bolsonaro (Presidente 2022) → PL (Prefeito 2024, Ramagem) | Rio | 151 | **+0,86** | +0,83 | 0,58 | 74% |
| o mesmo | todos os municípios com bairros | 575 | +0,30 | +0,30 | 0,83 | 9% |
| Lula (Presidente 2022) → Paes (Prefeito 2024) | Rio | 151 | +0,64 | +0,60 | 0,42 | 41% |
| Freixo (Governador 2022) → Paes (Prefeito 2024) | Rio | 151 | +0,36 | +0,34 | 0,20 | 13% |
| PSOL (Dep. Estadual 2022) → PSOL (Vereador 2024) | Rio | 151 | **+0,95** | +0,93 | 0,92 | 91% |
| Bolsonaro (Presidente) → Castro (Governador), 2022 | todos | 905 | +0,72 | +0,72 | 1,03 | 52% |

- **Como ler:** no Rio, cada 1 p.p. de Bolsonaro em 2022 corresponde a 0,58 p.p. de Ramagem em 2024.
- **Bairros:** abaixo da tendência ficaram Sepetiba, Santa Cruz e Paciência (−8 a −10 p.p.); acima, Campo dos Afonsos, Acari e Barra da Tijuca.
- **Todos os municípios juntos:** a mesma transferência cai para r = 0,30, porque cada município tem candidatos e contextos próprios. **Transferência municipal se analisa por município**, e a página tem o filtro para isso.

## Defeitos encontrados e decisões

1. **Ausência de candidatura não é 0%.**
   - **Problema:** em 2024 o PL não teve candidato a prefeito em vários municípios. Os bairros deles entravam com 0%, formavam uma "parede" no eixo e derrubavam a correlação (r = 0,12, com os piores resíduos todos em municípios sem candidato).
   - **Correção:** em Prefeito e Vereador, os bairros de municípios onde o alvo não teve **nenhum** voto ficam de fora. Em cargos estaduais e federais, 0% é dado real e fica.
2. **Número municipal é uma pessoa diferente em cada município.**
   - **Problema:** o "22" de prefeito em 2024 reúne 19 candidatos, mas a lista e o título mostravam só o primeiro nome.
   - **Correção:** agora aparecem "19 candidatos diferentes (um por município)". Com o filtro de município, aparece o nome certo (22 = Alexandre Ramagem no Rio), e a lista de candidatos respeita o município escolhido.
3. **Erro 500 no primeiro uso** (encontrado pelo teste de navegador).
   - **Problema:** a página pede dispersão e correlações ao mesmo tempo. Com o cache frio, as duas requisições convertiam o mesmo ZIP do perfil em paralelo e colidiam nos arquivos temporários.
   - **Correção:** `Bairros.trava` (`threading.RLock`) serializa todo carregamento e conversão (votos, participação, local → bairro, anos, perfil e Censo). Os caches de bairros das rodadas 15 a 18 tinham o mesmo risco latente.
   - **Teste:** `test_pedidos_paralelos_nao_colidem_na_conversao` falha sem a trava.
4. **Análises sobrepostas:** cliques rápidos podiam deixar uma resposta antiga desenhar por cima da nova. Agora só a análise mais recente desenha (`estado.pf.pedido`).
5. **Classe CSS:** os blocos da aba usavam `.cartao`, e 4 testes do painel, que contam os `.cartao`, passaram a falhar. A aba ganhou a classe `.bloco`.

## Verificação

- **`pytest -q`: 125 testes passando** (eram 105). Com a rede bloqueada por proxy inválido, os 125 também passam.
- **`test_perfil.py`**, 14 testes:
  - estatística: reta perfeita, conferência com numpy e pandas, p-valor de Fisher contra o valor calculado à mão (r = 0,5 e n = 28 dão p = 0,006), ponderação e n efetivo, dados insuficientes;
  - Censo: só a UF, sigilo vira nulo, densidade;
  - perfil por bairro: 180 e 110 eleitores, com os % conferidos à mão; em 2026, a coluna renomeada;
  - ausência de candidatura e número municipal ambíguo;
  - dispersão, transferência e filtro por município;
  - lista dos 10 indicadores;
  - concorrência;
  - API: 200, 400 e 404.
- **`test_perfil_e2e.py`**, 6 testes:
  - o endereço abre a análise, com fichas, 10 linhas de correlação e o indicador selecionado;
  - dica ao passar o mouse e clique na tabela;
  - transferência com os campos de X e o endereço;
  - 2026 sem dados;
  - análise padrão em página limpa;
  - download do SVG.
- **Sabotagens** (restauradas byte a byte):
  - sem a trava, o teste de concorrência falha;
  - sem a rota `#perfil?…` no JS, 5 testes de navegador falham.
- **Conferência visual:** Castro × % superior (905 bairros) e Bolsonaro 2022 → PL 2024 no Rio, sem erro de JavaScript.
- **Servidores** reiniciados nas portas 8000, 8022 e 8023.

## Arquivos

- **Novos:** `apuracao/perfil.py`, `test_perfil.py`, `test_perfil_e2e.py`.
- **Alterados:**
  - `votos_por_local_votacao.py`, com os códigos e contagens do perfil em `INT_COLUMNS`;
  - `apuracao/bairros.py`, com a trava;
  - `apuracao/web/app.py`, com as rotas `/api/perfil/*` e NaN virando `null`;
  - `apuracao/web/static/{index.html,app.js,style.css}`;
  - `conftest.py`, com o perfil de 2024/2026 e o Censo sintéticos;
  - `requirements.txt` (numpy), `CLAUDE.md` e `docs/INDEX.md`.
- **Cache:**
  - `cache_tse/perfil_eleitor_secao_{2022,2024,2026}_RJ.zip` e os Parquet;
  - `cache_tse/ibge_censo2022/` (3 ZIPs do IBGE + `censo_bairros_RJ.parquet`).

## Pendências

- **Setor censitário para os 61 municípios sem malha de bairros** (cerca de 21% do eleitorado).
  - **Dados:** os setores cobrem o estado inteiro e trazem renda e cor/raça.
  - **Como:** ligar cada local de votação ao setor que o contém, ou a um raio em volta dele, e somar os setores por local.
  - **Resultado:** "perfil por local de votação" no estado todo.
- **Mapas de perfil por bairro** na aba Mapas, por exemplo renda e % superior como camadas de contexto.
- **2026:** o perfil do TSE de 2026 já está no cache. Assim que o TSE publicar os votos por seção de 2026, a aba funciona sem mudança de código, inclusive a transferência 2022 → 2026.
- **Regressão múltipla:** vários indicadores ao mesmo tempo, por exemplo escolaridade controlada por renda. Hoje cada correlação é bivariada.
