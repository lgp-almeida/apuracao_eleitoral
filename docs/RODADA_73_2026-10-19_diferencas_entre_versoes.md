# Rodada 73 — Diferenças entre versões do cadastro de eleitorado (19/10/2026)

Rodada no ramo `frontend-refatoracao`, sem commit (aguarda o usuário). Não mexe no site, no coletor nem no front-end.

## Objetivo

Criar o comando `ingerir_eleitorado.py --diferencas`: dizer o que mudou entre duas versões guardadas do cadastro de
eleitorado (TODO 30, item "Diferença entre duas versões do cadastro como comando").

## Por que

- **O TSE regera o cadastro de 2026 todo dia desde 15/10.** As versões guardadas no acervo da rodada 72 são 29/09,
  06/10, 15/10, 16/10 e 17/10.
- **A comparação de 17/10 foi feita à mão.** O adendo de 17/10 da rodada 72 comparou as versões linha a linha com um
  script fora do repositório, e cada versão nova pediria refazê-lo.
- **A pergunta volta todo dia até o 2º turno:** "mudou alguma coisa nos locais e na distribuição das seções?".

## Entregas

### 1. `apuracao/diferencas_cadastro.py`

Duas leituras, sem I/O exceto `ler_csv` e `para_planilha`:

- **Linha a linha, no CSV do TSE:**
  - `ler_csv` lê todas as colunas como texto, com a chave como inteiro, e deixa de fora `DT_GERACAO`/`HH_GERACAO`,
    que mudam a cada geração.
  - `comparar_linhas` compara pela chave turno + UF + município + zona + seção. Dá as células alteradas (coluna,
    antes, depois, com o município e o nº do local da versão nova), as linhas criadas e extintas e as colunas que
    entraram ou saíram do layout.
  - Chave repetida ou ausente é erro.
- **UF por UF:** `comparar_zips` compara UF por UF quando os dois ZIPs têm um CSV por UF.
  - Nas 27 UFs: 7 s e 1,7 GB de memória, contra 14 s e 4,1 GB comparando tudo de uma vez.
  - Com um CSV nacional (como o de 2024), lê o CSV uma vez e filtra as UFs.
- **Resumos:**
  - `resumo_colunas`: linhas alteradas por coluna e turno.
  - `alteracoes`: as células agrupadas por local, com a lista de seções.
  - `resumo_ufs`: por UF, linhas alteradas, criadas, extintas e seções em local temporário nas duas versões.
- **Situação entre os turnos em cada versão (`locais_turnos`):**
  - `situacoes`: as oito situações nas duas versões, lado a lado.
  - `mudancas_de_situacao`: as seções presentes no 2º turno das duas versões que mudaram de situação ou de local no
    2º turno. "—" quer dizer sem situação, ou seja, o mesmo local nos dois turnos.
  - `quadro_de_situacoes`: o cruzamento antes × depois.
  - Versão sem linhas do 2º turno (a de 29/09) não tem situação, e o comando avisa.
- **Seções em local temporário:** `temporarios` conta, por turno, as seções que votam fora do local cadastrado. É a
  contagem por trás dos "4.352 seções" divulgados em 16/10 (rodada 72).

### 2. `ingerir_eleitorado.py --diferencas [ANTES [DEPOIS]]`

- **Quais versões:**
  - com duas versões (carimbo ou começo dele), compara uma com a outra;
  - com uma, compara com a versão do cache, que é guardada no acervo antes;
  - sem nenhuma, compara as duas mais recentes guardadas.
- **Com `--atualizar --diferencas`**, baixa a versão nova, se houver, e já mostra o que mudou.
- **UFs:** `--uf` (padrão: todas).
- **`--limite`:** quantas alterações por local imprimir (padrão 30).
- **`--saida`:** caminho da planilha. O padrão é `saidas/<UF>/diferencas_cadastro_<ano>_<antes>_<depois>.xlsx`, ou
  `saidas/BR/` com as 27 UFs.
- **A planilha tem oito abas:** Resumo (por coluna), UFs, Alterações (por local), Células, Criadas e extintas,
  Situações, Mudou de situação e Consulta. A Consulta traz as duas versões (carimbo, geração, Last-Modified, SHA-512,
  URL, acervo) e as contagens. Aba maior que o limite do Excel sai cortada, com aviso na Consulta.
- **Erros:** versão não guardada, menos de duas versões guardadas, as duas versões iguais e mais de duas versões
  pedidas.

### 3. `apuracao/ufs.rotulo`

O nome curto de um conjunto de UFs para a pasta de saída ("BR" para as 27; "RJ_SP"). Antes ficava duplicado no
`locais_entre_turnos.py`, que passou a usá-lo.

## Números reais

| Comparação | Linhas | Criadas / extintas | Células (linhas) | Temporárias no 2º turno | Mudaram de situação |
|---|---|---|---|---|---|
| 16/10 → 17/10, 27 UFs | 1.028.928 → 1.028.928 | 0 / 0 | 5.702 (1.175) | 4.352 → 4.864 | 539 seções (163.450 eleitores) |
| 16/10 → 17/10, RJ | 77.476 → 77.476 | 0 / 0 | 10 (5) | 47 → 47 | 0 |
| 29/09 → 06/10, RJ | 38.738 → 77.476 | 38.738 / 0 | 987 (424) | 0 → 0 | sem 2º turno em 29/09 |

- **16/10 → 17/10 confere com o adendo de 17/10 da rodada 72:**
  - as 5.702 células e as 1.367 alterações por local;
  - 488 seções que deixam de voltar ao local cadastrado no 2º turno (`VOLTA_AO_ORIGINAL → —`, 148.619 eleitores);
  - 29 que passam a ir a um local temporário só no 2º turno;
  - 15 `NOME_OU_ENDERECO` em GO, 5 `VOLTA_AO_ORIGINAL` no RS e 2 `OUTRO_PREDIO` na BA.
- **RJ de 16/10 para 17/10:** só o endereço do local 1198 da zona 157 de Nova Iguaçu, no 2º turno, nas seções 113 a
  117. O endereço do local e o endereço original passaram a ser "Rua do Imperador, 08 (acesso pela Rua Itabuna, 220)".
- **RJ de 29/09 para 06/10:**
  - As 38.738 linhas criadas são o 2º turno, que entrou no arquivo depois do 1º.
  - No 1º turno, três seções de Nova Friburgo trocaram de local: zona 26, seções 12, 13 e 14, da Faculdade de Nova
    Friburgo (local 1457) para o Colégio Resolve (antigo Pensi, local 1147).
  - As seções em local temporário no 1º turno passaram de 44 para 47.
  - As outras 984 células são coordenada, endereço, nome, bairro, CEP, telefone e acessibilidade dos locais.
- **A versão de 06/10 dá 0 seções em local temporário no 2º turno** porque repetia no 2º turno o local cadastrado
  (rodada 72).

## Decisões

- **Comparação no texto do CSV, não nos Parquet.** O Parquet guarda só as colunas usadas (`ELECTORATE_WANTED`), sem
  telefone, CEP, tipo do local ou acessibilidade. O CSV mostra tudo o que o TSE mudou, sem conversão.
- **A situação entre os turnos usa os Parquet** (`el.load_sections` na pasta da versão, onde os Parquet ficam). É a
  mesma regra de prédio do `locais_entre_turnos.py`.
- **Criadas e extintas ficam fora de `mudancas_de_situacao`.** Elas já aparecem nas diferenças do CSV, e a mudança de
  situação só faz sentido para a seção que existe nas duas versões.
- **Sem versões, valem as duas mais recentes pelo carimbo, que é a ordem de geração do TSE.** A do cache é guardada
  antes, para entrar na conta.

## Arquivos

- **Novos:** `apuracao/diferencas_cadastro.py`, `test_diferencas_cadastro.py` (10 testes, um deles golden) e este
  documento.
- **Alterados:**
  - `ingerir_eleitorado.py`: `--diferencas`, `--limite` e `--saida`.
  - `apuracao/ufs.py`: `rotulo`.
  - `locais_entre_turnos.py`: usa `ufs.rotulo`.
- **Documentação:** `CLAUDE.md`, `docs/INDEX.md`, `docs/TODO.md` (item 30) e `docs/ROTEIRO_NOITE_DA_ELEICAO.md`
  (24/10).

## Verificação

- **`pytest -q test_diferencas_cadastro.py -m "dados or not dados"`:** 10 passaram. São eles:
  - células, criadas e extintas;
  - resumo por coluna e alterações por local;
  - situações e mudanças entre as versões;
  - versão sem 2º turno;
  - CSV nacional filtrado pela UF;
  - chave repetida ou ausente;
  - CLI com a versão do cache e com as duas mais recentes;
  - destino padrão;
  - erros de versão;
  - golden do RJ de 15/10 a 17/10.
- **Testes relacionados:** `test_versoes.py`, `test_locais_entre_turnos.py` e `test_locais_por_bairro.py` (golden
  incluso) passaram.
- **Suíte sem os testes de navegador:** `pytest -q -m "not e2e"` deu 464 passados e 1 pulado (o de antes), com 80
  e2e de fora.
- **ruff:** `ruff check --line-length 120` sem apontamentos.
- **mypy:** sem erros nos arquivos tocados, exceto dois já conhecidos: o `import xlsxwriter` sem stubs (o mesmo de
  `locais_turnos.py`) e o erro antigo de `ingerir_eleitorado.py`, citado na rodada 72.

## Pendências

- **Rodar em 24/10:** `python ingerir_eleitorado.py --ano 2026 --atualizar --uf todas --diferencas` (no roteiro).
- **O resto do TODO 30 continua:** cadastro × onde a seção votou, depois dos microdados do 2º turno, e o acervo no
  vigia dos microdados.
