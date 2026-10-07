# Rodada 56 — Abstenção × mudança de local de votação (2022 → 2026)

07/10/2026 · pedido urgente: uma planilha que compare a abstenção por local de votação em 2022 e 2026, destaque as
seções que mudaram de local e meça se a mudança alterou a abstenção e quem ganhou ou perdeu com isso (Presidente e
Governador). Primeiro o RJ; as outras UFs com `--uf`.

## O que conta como mudança de local

O número do local **não** identifica o prédio. Medido no RJ, com as seções presentes nos dois anos:

| Situação | Seções |
|---|---|
| mesmo nº, mas outro nome **e** outro endereço (ex.: "SOPRECAM" → "COLÉGIO OBJETIVO CAMBOINHAS", D = 0 m) | 2.760 |
| outro nº, mesmo prédio (renumeração) | 370 a menos de 150 m |
| mesmo nº, nome e endereço iguais, coordenada a mais de 5 km (geocodificação) | 50 |

- **Coordenadas:** não servem para identificar o prédio. O TSE repete o ponto em prédios diferentes, e o cadastro
  de 2026 foi regeocodificado (rodada 48).
- **Regra usada:** mesmo lugar = mesmo nome **ou** mesmo endereço (`compact`) **ou**, até 150 m, nomes parecidos.
  Nomes parecidos = sobreposição ≥ 0,5 das palavras que distinguem o prédio, sem "ESCOLA", "MUNICIPAL",
  "COLÉGIO" etc.
- **Classes:**
  - **MUDOU:** outro lugar, com o número igual ou não;
  - **RENUMERADO:** outro número, mesmo prédio; fica fora do efeito;
  - **MANTEVE:** é o grupo de comparação;
  - **FORA:** seção nova, extinta ou agregada, ou sem aptos num dos anos.
- **Distância:** é só a faixa da mudança (até 150 m, 150–500 m, 0,5–2 km, mais de 2 km).

O plano aprovado previa decidir pela distância. Os dados acima mostraram que isso classificaria errado, e a regra
foi trocada (no relato ao usuário).

## Método

- **Abstenção:** abstenções / aptos de Presidente, do detalhe por seção. O Governador entra como coluna à parte.
- **Excesso:** diferença em diferenças **dentro da zona**. É o Δ da seção (2026 − 2022, em p.p.) menos o Δ das
  seções MANTEVE da mesma zona, ponderado pelos aptos de 2026.
- **Eleitores a mais abstendo:** excesso × aptos.
- **Agregação:** somas de numerador e denominador.
- **IC 95%:** bootstrap dos locais de destino (1.000 reamostras, semente fixa, locais ordenados antes de reamostrar).
- **Candidatos (a), votos perdidos estimados:** o excesso de cada seção que mudou, repartido como votou quem
  compareceu nela em 2026. Dá o efeito na margem entre os três mais votados e a perda além da proporcional.
- **Candidatos (b), partidos:** o % do eleitorado de cada partido nos dois anos, com o partido ligado pela
  entidade, e a diferença em diferenças entre MUDOU e MANTEVE na mesma zona.

## Resultado — RJ, 1º turno

**Classes de seção:**

| Classe | Seções | Aptos em 2026 |
|---|---|---|
| MANTEVE | 30.741 | 10.695.708 |
| **MUDOU** | **2.941** | **985.343** (7,7% do eleitorado) |
| RENUMERADO | 206 | 71.881 |
| FORA | 3.967 | 1.104.716 |

**Excesso de abstenção nas seções que mudaram: +1,14 p.p.** (IC 95% +0,89 a +1,40), ou seja **11.253 eleitores a
mais abstendo**.
- **Controle:** a abstenção das seções que ficaram subiu 0,72 p.p. na mesma zona.
- **Sem as seções com eleitorado variando mais de 50%:** +1,23 p.p.

**O efeito cresce com a distância:**

| Faixa | Seções | Excesso |
|---|---|---|
| até 150 m | 1.150 | +0,60 p.p. |
| 150–500 m | 857 | +0,71 p.p. |
| 0,5–2 km | 815 | +1,91 p.p. |
| mais de 2 km | 119 | **+4,11 p.p.** |

**(a) Votos perdidos estimados, 1º turno de 2026:**

| Cargo | Candidato | Votos perdidos | Parte da perda | Parte dos válidos | Leitura |
|---|---|---|---|---|---|
| Presidente | Flávio Bolsonaro (PL) | 5.356 | 50,4% | 53,0% | perdeu menos que a parte |
| Presidente | Lula (PT) | 4.472 | 42,1% | 39,4% | perdeu mais que a parte |
| Governador | Douglas Ruas (PL) | 4.582 | 46,8% | 49,3% | perdeu menos que a parte |
| Governador | Eduardo Paes (PSD) | 4.514 | 46,1% | 42,8% | perdeu mais que a parte |

- **Margem, Presidente:** a abstenção a mais diminuiu a vantagem de Flávio sobre Lula em cerca de 883 votos (a
  margem é de 1.273.823).
- **Margem, Governador:** diminuiu a de Ruas sobre Paes em cerca de 68 votos (a margem é de 564.215).
- **Leitura:** as seções que mudaram eram relativamente mais de Lula e de Paes. Os efeitos são pequenos diante das
  margens.

**(b) Partidos** (% do eleitorado, MUDOU × MANTEVE na mesma zona):

| Cargo | Partido | Diferença em diferenças |
|---|---|---|
| Presidente | PT | −0,70 p.p. |
| Presidente | PL | −0,39 p.p. |
| Governador | PL | −0,40 p.p. |

- **Sem dado em 2022:** Paes (PSD não teve candidato a governador em 2022) e Caiado (PSD sem candidato a
  Presidente).

**Conferência:** a soma das seções reproduz os resultados importados.
- **Aptos e abstenções:** os dois anos iguais aos de `historico_2022_t1` e `historico_2026_t1_RJ`.
- **Votos:** os dos 22 candidatos de Presidente e Governador também iguais.

## Resultado — 27 UFs (`--uf todas`)

- **Saída:** uma planilha por UF em `saidas/<UF>/` e um consolidado em
  `saidas/BR/abstencao_mudanca_local_2022_2026_ufs.xlsx`, com as abas UFs, Presidente no país, Presidente por UF e
  Governador por UF.
- **No país:** 29.989 seções mudaram de prédio, com 9,36 milhões de aptos. Soma de 39.326 eleitores a mais
  abstendo.

**Excesso positivo e significativo (IC 95% sem o zero), 13 UFs:**

| UF | Excesso | | UF | Excesso |
|---|---|---|---|---|
| RJ | +1,14 | | SC | +0,39 |
| SP | +1,14 | | PE | +0,38 |
| AP | +1,09 | | MG | +0,29 |
| RS | +0,69 | | PI | +0,28 |
| PR | +0,62 | | BA | +0,23 |
| SE | +0,46 | | | |

**Significativo no sentido contrário:** só o MS, com −0,57 p.p. Nas outras 13 UFs, o IC inclui o zero.

**Presidente somado nas 27 UFs (votos perdidos estimados):**

| Candidato | Votos perdidos | % dos votos dele |
|---|---|---|
| Flávio Bolsonaro | 18.112 | 0,03% |
| Lula | 16.134 | 0,03% |

O efeito no país é ínfimo diante da votação dos dois.

## Arquivos

- `apuracao/abstencao_locais.py` (leitura, montagem sem I/O e planilha xlsxwriter).
- `abstencao_mudanca_local.py` (CLI: `--uf RJ|todas`, `--ano-base`, `--ano`, `--turno`, `--saida`).
- `test_abstencao_locais.py`: 7 testes, com tudo calculado à mão.
- Saída: `saidas/RJ/abstencao_mudanca_local_2022_2026.xlsx`, com as abas LEIA-ME, Resumo, Seções (MUDOU em
  amarelo; RENUMERADO e FORA em cinza; autofiltro), Locais que mudaram, Zonas, Municípios, Candidatos, Margem e
  Partidos.

## Verificação

- `pytest -q -m "not e2e"`: 399 passados e 1 pulado.
- O CLI no RJ dá o mesmo IC em execuções seguidas.

## Pendências

- Repetir para o 2º turno de 2026 (`--turno 2`) quando saírem os microdados dele.
- O commit e o push da rodada 55 (e desta) ficaram para depois, a pedido do usuário.
