# Rodada 26 — Perfil × voto por local de votação no estado inteiro, e regressão com vários indicadores

30/09/2026 · pedido do usuário: "Implemente o item 5" (`docs/TODO.md`)

## Objetivo

O Perfil × voto (rodada 19) usava bairros do IBGE, que cobrem só 31 dos 92 municípios (79% do eleitorado). Esta rodada acrescenta:
- os **setores censitários** do Censo 2022, que cobrem o estado todo, ligados a cada **local de votação**;
- a análise com **vários indicadores ao mesmo tempo** (por exemplo, escolaridade controlada por renda).

## Dados (IBGE, Censo 2022)

- **Malha:** `RJ_setores_CD2022.zip` (geoftp, 32 MB), com 41.700 setores.
- **Agregados por setor**, arquivos nacionais filtrados pelo RJ ao ler:
  - básico: pessoas, área, moradores por domicílio e **tipo do setor**, com 1 = favela ou comunidade urbana;
  - renda do responsável;
  - cor ou raça.
- **Formato:** o CSV de renda por setor usa **ponto decimal**; o de bairro, vírgula. O leitor aceita os dois.
- **Sigilo ("X"):** um setor com qualquer cor em sigilo sai **inteiro** da conta de cor. Tirar só a coluna com X distorceria o percentual.
- **Cache:** `cache_tse/ibge_censo2022/censo_setores_RJ.parquet`.

## Como ligar setores a locais: três métodos testados, um escolhido por dados

**Critério.** O perfil de quem **vota** no local (TSE: % com superior completo) deve concordar com o perfil de quem **mora** no entorno (IBGE: renda, cor). Uma ligação geográfica melhor dá correspondência mais forte.

**Cadastro de 2024** (4.870 locais com ≥ 200 eleitores); o de 2022 deu o mesmo ordenamento:

| Método | Locais cobertos | superior × renda mediana (log) | superior × % pretos e pardos |
|---|---|---|---|
| setor que **contém** o local | 4.870 | 0,804 | −0,616 |
| **área de influência** (setor → local mais próximo do mesmo município) | 4.720 | 0,859 | −0,694 |
| **raio 800 m** | 4.754 | **0,879** | **−0,740** |
| **raio 800 m + contém** (sem setor no raio, o que contém) | **4.870 (100%)** | **0,879** | −0,726 |

**Raios testados:** 300 m (0,857), 500 m (0,873), **800 m (0,879)**, 1.200 m (0,877) e 2.000 m (0,851).

**Decisão:** `raio+contem` com 800 m (`METODO_PADRAO`). Tem a correspondência mais forte e cobre 100% dos locais. A área de influência cobre o estado inteiro, mas mistura setores distantes em área rural e deixa sem setor os locais "vizinhos" de outro mais próximo.

**Para repetir a medição:**

```bash
python -c "from pathlib import Path; from apuracao import perfil_local as p; print(p.validar_metodos(2024, 'RJ', Path('cache_tse')))"
```

## Entregas

- **`apuracao/perfil_local.py`:**
  - `setores`, `locais` (chave UNIDADE = IBGE do município + zona + local, para os filtros por município valerem igual), `ligar` (4 métodos), `agregar`, `perfil_tse_por_local` e `validar_metodos`;
  - `PerfilVotoLocal`, subclasse de `PerfilVoto` com o local como unidade e o indicador novo **% de moradores em favela ou comunidade urbana**.
- **`apuracao/perfil.py`:**
  - ganchos `_vb`, `_nomes`, `CENSO` e `UNIDADE` para trocar a unidade sem duplicar a análise;
  - **`regressao_multipla`**: mínimos quadrados, ponderável, com indicadores padronizados. Traz o efeito em p.p. por +1 desvio-padrão, EP, IC 95%, p, VIF, R² e R² ajustado, e o r simples ao lado;
  - `PerfilVoto.regressao`.
- **API:**
  - `unidade=bairro|local` em `/api/perfil/info`, `candidatos`, `correlacoes` e `dispersao`;
  - rota nova `GET /api/perfil/regressao?...&indicadores=a,b,c`;
  - erro 400 para unidade desconhecida ou poucas unidades para o número de indicadores.
- **Página (aba Perfil × voto):**
  - campo **Unidade** ("Bairros do IBGE (31 municípios)" ou "Locais de votação (estado inteiro)");
  - municípios, indicadores, rótulos ("Locais na análise", "Local acima da tendência") e tabelas acompanham a unidade;
  - bloco **"Vários indicadores ao mesmo tempo"**, com caixas de marcar (padrão: superior, renda média, pretos e pardos, 60+) e a tabela de efeitos. Linhas com VIF > 5 ficam esmaecidas, com explicação;
  - endereço com `unidade=local` e `reg=a,b,c` (este só quando diferente do padrão).

## Resultados reais (RJ 2022, ≥ 200 votos válidos)

| Candidato | Por bairro (rodada 19) | Por local (esta rodada) |
|---|---|---|
| Bolsonaro, Presidente | densidade r = −0,25 (910) | densidade **r = −0,42** (4.704) |
| Lula, Presidente | densidade r = +0,22 | densidade **r = +0,33** |
| Castro, Governador | % sem fundamental r = +0,58 (905) | **r = +0,72** (4.668) |
| Molon, Senado | % sem fundamental r = −0,75 | % superior **r = +0,78** |
| Pazuello, Dep. Federal | % superior r = +0,75 | r = +0,77 |
| Renata Souza, Dep. Estadual | renda mediana r = +0,60 | r = +0,69 |

**Com vários indicadores ao mesmo tempo** (por local):
- **Castro:** R² = 0,44.
  - Renda média: −6,8 p.p. por desvio-padrão.
  - Superior: −4,7.
  - **% pretos e pardos: −3,8, apesar do r simples +0,38.** Controladas renda e escolaridade, o sinal se inverte. É o exemplo de por que a análise conjunta importa, e de por que ela precisa de leitura cuidadosa.
  - VIF de renda e superior entre 4,5 e 4,9: andam juntos, mas abaixo de 5.
- **Bolsonaro:** R² = 0,18. O efeito mais forte é o da renda (−3,5 p.p. por desvio-padrão); pretos e pardos também invertem o sinal (r simples +0,19; efeito −1,9).

## Ressalvas (também na página)

- **Correlação ecológica:** compara locais, não pessoas; associação não é causa.
- **Duas populações diferentes:** o Censo mede quem MORA a até 800 m do local; o TSE mede quem VOTA ali, e o eleitor nem sempre mora perto.
- **Inferência na regressão:** o IC e o p usam o EP clássico (sem correção para heterocedasticidade nem para correlação espacial entre locais vizinhos). Com cerca de 4.700 locais tudo sai "significativo"; o que informa é o tamanho do efeito e a comparação com o r simples.

## Verificação

- **`pytest -q`: 203 testes passando** (eram 189).
- **`test_perfil_local.py`**, 13 testes, com setores sintéticos no `conftest.py` (malha em shapefile, agregados e mapa TSE → IBGE):
  - regressão: recupera os efeitos exatos, VIF alto com colinearidade, erros com poucos dados e sem variação;
  - locais e chave;
  - os 4 métodos de ligação;
  - o "contém" cobrindo quem não tem setor no raio;
  - agregação: renda ponderada, densidade, favela, sigilo total e **parcial**;
  - perfil do TSE por local;
  - dispersão e regressão por local;
  - API.
- **Teste de navegador** `test_unidade_local_de_votacao`: unidade no seletor e no endereço, 4 pontos, "Estado inteiro", legenda "Local", regressão que explica quando não há locais suficientes, `reg=` no endereço e a volta para bairros.
- **Sabotagens** (restauradas byte a byte):
  - JS sem a unidade no endereço: 1 falha.
  - Sem o "contém" e com o sigilo parcial entrando na conta: de início **passaram despercebidas**, porque os centros dos setores sintéticos coincidiam com os locais e o sigilo era só total. O cenário ganhou um setor com o centro a cerca de 100 m do local e um setor rural com sigilo parcial; agora cada sabotagem derruba 1 teste.
- **Conferência visual (porta 8000):** Castro × % sem fundamental por local, com 4.668 pontos, correlação e regressão, sem erro de JavaScript.

## Arquivos

- **Novos:** `apuracao/perfil_local.py`, `test_perfil_local.py`.
- **Alterados:**
  - `apuracao/perfil.py`, `apuracao/web/app.py` e `apuracao/web/static/{index.html,app.js,style.css}`;
  - `conftest.py` (`escrever_setores`, também no site dos testes de navegador) e `test_perfil_e2e.py`;
  - `docs/TODO.md`, `docs/INDEX.md` e `CLAUDE.md`.
- **Cache:** `cache_tse/ibge_censo2022/`, com a malha de setores, os 3 agregados por setor e `censo_setores_RJ.parquet`.

## Pendências

- **2026:** com os microdados de 2026, a unidade "local" funciona igual (o cadastro de 2026 já está no cache).
- **Erros-padrão robustos:** EP robusto (heterocedasticidade e agrupamento por município) daria IC mais honestos.
- **Mapa:** um mapa por local (pontos coloridos) na aba Mapas complementaria a dispersão.
