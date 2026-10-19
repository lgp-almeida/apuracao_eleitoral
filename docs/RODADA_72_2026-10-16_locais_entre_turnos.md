# Rodada 72 — Acervo de versões do cache e locais de votação entre o 1º e o 2º turno (16/10/2026)

Rodada no ramo `frontend-refatoracao`, sem commit (aguarda o usuário). Não mexe no site, no coletor nem no front-end.

## Objetivo

1. **Atualizar o cadastro de eleitorado de 2026 no cache** sem perder as versões anteriores, para garantir a
   proveniência e poder refazer uma análise com os dados que ela usou.
2. **Criar um comando** que diga, seção por seção, se o local de votação muda entre o 1º e o 2º turno.

## Por que

- **O cadastro de 2026 muda sem aviso.** O TSE o regerou no mesmo endereço em 29/09, 06/10, 15/10 e 16/10. A versão
  de 06/10, a que estava no cache, repetia no 2º turno o local cadastrado. Só a de 15/10 em diante traz os locais
  temporários do 2º turno.
- **O cache não se atualizava sozinho.** O `download` do núcleo nunca baixa de novo o que já existe. Na rodada 48, a
  troca foi feita à mão, com uma cópia em `cache_tse/anterior/`.
- **Sem histórico, a análise não se refaz.** Trocar o ZIP apagava a versão anterior, e uma planilha não dizia de que
  versão vinha.

## Entregas

### 1. Acervo de versões (`apuracao/versoes.py`)

Cada versão de um arquivo do TSE fica em `cache_tse/versoes/<nome do ZIP>/<carimbo>/`:

| Arquivo | O que é |
|---|---|
| `<ZIP>` | Link físico do ZIP do cache, ou cópia se estiver em outro sistema de arquivos. Fica **só leitura**. |
| `<nome>.proveniencia.json` | Cópia exata da proveniência gravada no download. |
| `versao.json` | Carimbo, geração do TSE, SHA-512 conferido, URL, quando foi baixada e guardada, e de onde veio. |

- **Carimbo:** é a geração que o TSE grava no CSV (`DT_GERACAO` + `HH_GERACAO`, horário de Brasília), por exemplo
  `2026-10-16T062901`. Sem ela, vale o Last-Modified da CDN em UTC (`…Z`).
- **`guardar`:**
  - é idempotente: o mesmo SHA-512 devolve a mesma versão;
  - **recusa** ZIP que não confere com a própria proveniência (`VersaoDivergente`), sem guardar nem trocar nada;
  - quando a mesma geração tem outro conteúdo, a versão nova fica ao lado, com `_<8 dígitos do SHA>` no carimbo.
- **`atualizar`:** guarda a versão do cache, faz um HEAD e, se o Last-Modified for mais novo (ou com `forcar`), baixa
  a nova por `microdados.baixar`. Esse download tem troca atômica, continua de onde parou e recusa cópia velha da CDN.
  Depois guarda a nova e apaga os Parquet derivados, mas **só se o conteúdo mudou**. Situações possíveis: "baixado",
  "atualizado", "em dia" e "republicado sem mudança".
- **`escolher`:** acha a versão pelo carimbo inteiro ou por um começo que só uma tenha (`2026-10-06`).
- **`em_uso`:** é a versão do cache, guardada no acervo se ainda não estiver. Toda comparação a chama.
- **A pasta de uma versão tem o layout do cache:** serve de `--cache-dir`, e o Parquet derivado é gravado nela.

### 2. `ingerir_eleitorado.py`: `--atualizar`, `--forcar` e `--versoes`

```bash
python ingerir_eleitorado.py --ano 2026 --atualizar --uf todas   # baixa a versão nova, guarda a anterior, refaz as 27 UFs
python ingerir_eleitorado.py --ano 2026 --versoes                # lista o acervo; "← no cache" marca a versão em uso
```

`--uf` passou a aceitar `todas`. Ele continua obrigatório, exceto com `--atualizar` ou `--versoes`.

### 3. Locais entre turnos (`apuracao/locais_turnos.py` + `locais_entre_turnos.py`)

O cadastro traz cada seção uma vez por turno, com o local onde ela vota e o local cadastrado (`*_ORIGINAL`). As duas
linhas são casadas por UF + município + zona + seção, e cada seção com diferença recebe uma situação:

| Situação | Quando |
|---|---|
| `VOLTA_AO_ORIGINAL` | local temporário no 1º turno; no 2º, de volta ao local cadastrado |
| `TEMPORARIO_NO_2T` | local cadastrado no 1º turno; local temporário no 2º |
| `OUTRO_TEMPORARIO` | local temporário nos dois turnos, em lugares diferentes |
| `OUTRO_LOCAL` | nº de local diferente sem ser pelo local temporário (o cadastro mudou, ou o ano não traz o original) |
| `OUTRO_PREDIO` | **mesmo nº de local, mas outro nome E outro endereço:** provavelmente outro prédio (confira) |
| `NOME_OU_ENDERECO` | mesmo nº, só o nome ou só o endereço diferente: o mesmo prédio, texto corrigido |
| `AGREGACAO` | mesmo local; a seção passou a ser agregada a outra, ou deixou de ser |
| `SO_NO_2T` | seção que só existe no 2º turno |

As cinco primeiras (`MUDA_DE_LOCAL`) são as que mandam o eleitor a outro prédio. Uma seção que só existe no 1º turno
não conta como mudança, porque o município pode não ter 2º turno. Ela entra só na contagem.

```bash
python locais_entre_turnos.py                          # RJ, versão do cache
python locais_entre_turnos.py --ufs todas --limite 100
python locais_entre_turnos.py --municipio "Rio de Janeiro"
python locais_entre_turnos.py --versao 2026-10-06      # refaz com uma versão guardada
```

O comando imprime o resumo por situação e os pares de locais. Para endereço diferente, mostra os dois. Grava também a
planilha `saidas/<UF>/locais_entre_turnos_<ano>_<carimbo>.xlsx` (`saidas/BR/` com `--ufs todas`), com quatro abas:

- **Resumo:** as oito situações, com zero onde não houve.
- **Locais:** um par (local do 1º → do 2º) por linha, com as seções, os eleitores e a distância.
- **Seções:** uma seção por linha, com os locais dos dois turnos, o local original e a distância.
- **Consulta:** parâmetros, a versão do cadastro (carimbo, geração do TSE, Last-Modified, SHA-512, URL, pasta do
  acervo) e as contagens.

## Números reais

### Acervo do cadastro de 2026, depois desta rodada

| Carimbo | Geração do TSE | Last-Modified da CDN | Tamanho | SHA-512 | De onde veio |
|---|---|---|---:|---|---|
| `2026-09-29T062809` | 29/09 06:28:09 | — | 88,1 MB | `c1e770e0…` | cópia à mão da rodada 48 (`cache_tse/anterior/`), por link |
| `2026-10-06T062912` | 06/10 06:29:12 | 06/10 09:34:36 GMT | 175,8 MB | `b89b399d…` | o cache até hoje |
| `2026-10-15T143326` | 15/10 14:33:26 | 15/10 17:37:58 GMT | 176,0 MB | `3142b0b6…` | baixada de manhã com `curl` para a análise |
| `2026-10-16T062901` | 16/10 06:29:01 | 16/10 09:33:54 GMT | 176,3 MB | `cda47a0b…` | `--atualizar` em 16/10 |
| `2026-10-17T062828` | 17/10 06:28:28 | 17/10 09:33:49 GMT | 176,6 MB | `627b66da…` | **no cache**, por `--atualizar` em 17/10 (adendo) |

- **A CDN entregou cópia velha.** Às 15:41 GMT de 16/10, o HEAD e o GET ainda davam a versão de 15/10. Às 18:29 GMT,
  `--atualizar` recebeu a de 16/10, com Last-Modified 09:33 GMT. É o mesmo comportamento de nó desatualizado da
  rodada 54. A versão de 15/10 só existia na pasta temporária da sessão. Foi guardada no acervo com uma proveniência
  montada dos cabeçalhos do `curl` (Date, ETag, Last-Modified).
- **O cache foi atualizado em 21 s** (download e conversão das 27 UFs). Os 27 Parquet antigos saíram e foram refeitos.
  No 1º turno, o RJ continua com 38.738 seções, 12.857.000 eleitores e 47 seções remanejadas.

### Seções que mudam de local entre os turnos, por versão

As colunas trazem seções / eleitores / locais no 2º turno. "—" quer dizer nenhuma.

| Versão | Recorte | `VOLTA_AO_ORIGINAL` | `TEMPORARIO_NO_2T` | `OUTRO_TEMPORARIO` | `OUTRO_PREDIO` | `NOME_OU_ENDERECO` |
|---|---|---|---|---|---|---|
| 06/10 | RJ | 47 / 13.744 / 14 | — | — | 14 / 4.923 / 1 | 5 / 1.311 / 1 |
| 15/10 | RJ | — | — | — | 19 / 6.803 / 2 | 10 / 2.416 / 3 |
| 16/10 | RJ | — | — | — | 19 / 6.803 / 2 | 10 / 2.416 / 3 |
| 17/10 | RJ | — | — | — | 19 / 6.803 / 2 | 10 / 2.416 / 3 |
| 06/10 | 27 UFs | 6.589 / 1.930.532 / 1.737 | — | — | 19 / 6.314 / 2 | 94 / 30.869 / 12 |
| 15/10 | 27 UFs | 2.420 / 709.226 / 663 | 119 / 36.843 / 34 | 11 / 3.836 / 4 | 43 / 13.844 / 7 | 247 / 69.031 / 43 |
| 16/10 | 27 UFs | 2.364 / 690.359 / 647 | 127 / 38.701 / 39 | 16 / 5.552 / 5 | 44 / 13.991 / 8 | 326 / 94.376 / 54 |
| 17/10 | 27 UFs | 1.881 / 543.110 / 515 | 156 / 46.761 / 46 | 16 / 5.552 / 5 | 46 / 14.503 / 9 | 341 / 99.265 / 56 |

`OUTRO_LOCAL`, `AGREGACAO` e `SO_NO_2T` deram zero em todas. São 514.464 seções nos dois turnos nas 27 UFs; o
exterior (ZZ) fica de fora de `--ufs todas`.

- **Na versão de 16/10, 2.551 seções (748.603 eleitores) votam em outro prédio no 2º turno.** A maioria volta ao
  local cadastrado. As UFs com mais casos são PE (324), SP (309), PR (308), PI (227) e MG (205).
- **A versão de 15/10 confere com a análise feita à mão de manhã:** 2.420, 119 e 11 seções, com os mesmos eleitores e
  locais.
- **RJ, o achado da rodada:** pelo nº do local, nenhuma seção muda entre os turnos. **Pela regra de prédio, 19 seções
  (6.803 eleitores) mudam:**
  - zona 156 de Nova Iguaçu, local 1279: 14 seções do CIEP 351 (Estrada Santa Bárbara, s/n) vão para o Colégio
    Estadual Barão de Tinguá (Rua Gisela, 157);
  - zona 188 do Rio, local 1295: 5 seções da EEEPV da Rua Muaná, 105 (Brás de Pina) vão para a da Rua Irapuá, 243
    (Penha Circular).

  Nos dois casos, a linha do 2º turno também dá o prédio novo como local original: o TSE redefiniu o local, e não
  mandou a seção para um local temporário. A coordenada ficou a mesma.
- **Outros prédios com o mesmo nº, fora do RJ:** Ibitirama/ES (7 seções), Candeias/BA, Santa Isabel/GO e Tutóia/MA
  (5 cada), Morros/MA (2) e São Tiago/MG (1).

### Adendo de 17/10: o que mudou nas versões depois de 15/10

O TSE regerou o cadastro de novo em 17/10, às 06:28. `--atualizar` guardou a de 16/10 e baixou a nova. As versões
foram comparadas linha a linha, em todas as colunas do CSV de cada UF (chave turno + UF + município + zona + seção;
o script ficou fora do repositório).

- **Nenhuma seção foi criada nem extinta entre as versões.** A agregação (`NR_SECAO_PRINCIPAL`) e o eleitorado por
  seção também não mudaram. As mudanças estão em locais (nº, nome, endereço, coordenada, tipo, situação, telefone):
  - de 15/10 para 16/10: 1.057 células;
  - de 16/10 para 17/10: 5.702 células.
- **O nº do local só mudou em linhas do 2º turno:** 74 seções de 15/10 para 16/10 e 522 de 16/10 para 17/10.
- **RJ:**
  - De 15/10 para 16/10, nada mudou.
  - De 16/10 para 17/10, só o endereço do local 1198 da zona 157 de Nova Iguaçu (Igreja Evangélica Assembleia de Deus
    Ministério Viga), nas 5 seções 113 a 117 (1.311 eleitores) e só no 2º turno. O endereço passou de "Rua Itabuna,
    220" para "Rua do Imperador, 08 (acesso pela Rua Itabuna, 220)", e o `DS_ENDERECO_LOCVT_ORIGINAL` mudou igual. No 1º
    turno o endereço é "Rua do Imperador, 8": é o mesmo prédio, com a entrada pela Rua Itabuna no 2º turno.
  - Os números entre turnos do RJ são os mesmos de 16/10.
- **Brasil, de 16/10 para 17/10:**
  - 488 seções (148.619 eleitores) deixaram de voltar ao local cadastrado no 2º turno. Em 16/10, a linha do 2º turno
    dava o local original. Em 17/10, ela dá o mesmo local temporário do 1º turno, com o original inalterado.
    - PE 120, SP 102, PI 89, PR 50, PB 28, AP 25, BA 23, MG 20, AL 16, SE 13 e RS 2.
  - Novos casos:
    - 29 `TEMPORARIO_NO_2T` (MA, PI, PR e RS);
    - 15 `NOME_OU_ENDERECO` (GO);
    - 5 `VOLTA_AO_ORIGINAL` (RS);
    - 2 `OUTRO_PREDIO` (BA).
  - Saldo: 2.099 seções (609.926 eleitores) mudam de prédio entre os turnos, contra 2.551 em 16/10.
- **Os "4.352 seções com local alterado para o 2º turno" divulgados em 16/10 saem deste arquivo.** Na versão de 16/10,
  exatamente 4.352 linhas do 2º turno têm `NR_LOCAL_VOTACAO_ORIGINAL` ≠ `NR_LOCAL_VOTACAO`, isto é, seção em local
  temporário. As 499.248 "seções do país" da mesma notícia são as 497.897 principais das 27 UFs mais as 1.351 do
  exterior.
  - Não é a mudança entre os turnos: 4.209 dessas seções já estavam no mesmo local temporário no 1º turno.
  - Só 143 vão para um local temporário no 2º turno (`TEMPORARIO_NO_2T` e `OUTRO_TEMPORARIO`).
  - Os números por UF da imprensa (SP 982, MG 514, RJ 431, BA 312) não batem com nenhuma contagem do cadastro. No
    RJ são 47 seções em local temporário nos dois turnos, sempre o mesmo local.
  - A nota do TSE não foi lida: `www.tse.jus.br` e `www.tre-rj.jus.br` devolvem 403 (Akamai) a acesso automatizado.
  - Em 17/10, a mesma contagem dá 4.864.

### Adendo de 17/10: `locais_por_bairro.py` com turno e versão

A lista de um bairro (rodada 71) gravava `saidas/<UF>/locais_bairro_<bairro>_<ano>.xlsx`. Esse nome não tinha turno,
fonte nem versão do cadastro: `--turno 2` gravava por cima da lista do 1º turno, e a planilha não dizia de que versão
viera.

- **Nome do arquivo:** `locais_bairro_<bairro>_<ano>_t<turno>[_ibge]_<carimbo>.xlsx`.
- **Aba Consulta:** além do turno, os campos de `Versao.para_consulta()` (carimbo, geração do TSE, Last-Modified,
  baixado em, SHA-512, URL, acervo).
- **Saída na tela:** uma linha com a versão antes da lista.
- **Acervo:** a versão usada é guardada por `vs.em_uso`, como no `locais_entre_turnos.py`.
- **`--versao`:** refaz a lista com uma versão guardada (a pasta da versão serve de cache).
- **Turno sem linhas no cadastro:** passou a ser erro ("não tem linhas do 2º turno"). Antes, saía como "nenhum local
  no bairro".
- **Testes:** `test_locais_por_bairro.py` tem 12, 5 deles novos ou ampliados:
  - versão na Consulta e no acervo;
  - destino padrão com turno, fonte e carimbo;
  - gravação no destino padrão;
  - `--versao` refaz igual sem o ZIP no cache, e uma versão inexistente lista as guardadas;
  - turno sem linhas.
- **Rocinha, Gávea e São Conrado (pela malha do IBGE, 2º turno, versão de 17/10):**

  | Bairro | Locais | Seções | Eleitores |
  |---|---:|---:|---:|
  | Rocinha | 6 | 54 | 22.404 |
  | São Conrado | 5 | 50 | 19.592 |
  | Gávea | 11 | 71 | 26.444 |

  - Nada mudou nesses bairros nas versões de 06/10, 15/10, 16/10 e 17/10, nem entre os turnos.
  - Entre 29/09 e 06/10, só a coordenada de dois locais foi corrigida, com o mesmo nome e endereço: o Complexo
    Esportivo da Rocinha (cerca de 130 m) e a Escola Parque da Gávea (cerca de 330 m).
  - Pelo texto do TSE, a Rocinha tem 1 local e 5 seções: 5 dos 6 locais dela estão como "São Conrado".

## Decisões

- **Link físico só leitura, e não cópia:** não ocupa espaço enquanto o cache tem o mesmo arquivo. A troca do cache é
  sempre por `replace`, então não afeta o link. Só leitura porque link e cache são o mesmo arquivo: um `cp` por cima
  do ZIP do cache estragaria as duas cópias. O próprio teste do CLI esbarrou nisso ao reescrever o ZIP no lugar, e
  passou a gravar ao lado e trocar.
- **Carimbo pela geração do TSE, e não pelo Last-Modified:** a geração está no conteúdo e é a data que o TSE mostra.
  O Last-Modified é metadado da CDN e muda de nó para nó. As duas datas ficam na ficha.
- **O acervo inclui a versão em uso:** é ela que uma análise cita, e assim a lista de versões é completa. A cópia de
  `cache_tse/anterior/` ficou onde estava. Só ganhou um link no acervo, e o arquivo agora é só leitura.
- **"Mesmo prédio" sem o critério da distância:** a regra de `abstencao_locais` (rodada 56) diz que é o mesmo prédio
  quando o nome é igual OU o endereço é igual OU, até 150 m, os nomes são parecidos. Entre turnos, o TSE repete a
  coordenada no prédio novo, então a distância é sempre 0. Com o 3º critério, a EEEPV da Rua Muaná e a da Rua Irapuá
  (nomes 75% parecidos, mesmo ponto) seriam o mesmo prédio. Fica valendo só nome igual OU endereço igual
  (`compact`). Na dúvida, o caso vai para `OUTRO_PREDIO`, que pede conferência, em vez de sumir.
- **O acervo não foi ligado ao vigia dos microdados (`microdados.preparar`)**, que também troca ZIPs. Lá os arquivos
  são grandes (SP: 767 MB por versão) e as retotalizações são frequentes. Ficou como pendência.

## Arquivos

- **Novos:** `apuracao/versoes.py`, `apuracao/locais_turnos.py`, `locais_entre_turnos.py`.
- **Alterado:** `ingerir_eleitorado.py` (`--atualizar`, `--forcar`, `--versoes`, `--uf todas`).
- **Testes:**
  - `test_versoes.py` (13): carimbo; guardar idempotente e só leitura; a versão sobrevive à troca do cache; ZIP
    divergente recusado; mesma geração com outro conteúdo; escolher por prefixo; atualizar guarda, baixa e apaga os
    derivados; republicado sem mudança; `forcar`; cache vazio; HEAD com erro; CLI `--atualizar`/`--versoes`.
  - `test_locais_entre_turnos.py` (12, um deles golden): as oito situações num cadastro sintético de dois turnos;
    pontuação não conta; a chave inclui o município; contagens; resumo com zeros; pares de locais; layout sem as
    colunas `*_ORIGINAL`; CLI com planilha e versão; `--versao` refaz igual depois de o cache mudar; erros de uso.
  - **Golden** `test_golden_rj_2026_versoes_do_cadastro` (marca `dados`; pulado sem o acervo): as três versões do RJ
    e os dois prédios.
- **Dados:** `cache_tse/eleitorado_local_votacao_2026.zip` na versão de 16/10, os 27 Parquet refeitos e
  `cache_tse/versoes/eleitorado_local_votacao_2026/` com as 4 versões. Planilhas em
  `saidas/RJ/locais_entre_turnos_2026_2026-10-16T062901.xlsx` e
  `saidas/BR/locais_entre_turnos_2026_2026-10-1{5T143326,6T062901}.xlsx`.
- **Documentação:** `CLAUDE.md`, `docs/INDEX.md`, `docs/TODO.md` (item 30) e `docs/ROTEIRO_NOITE_DA_ELEICAO.md`
  (atualizar o cadastro e comparar os locais em 24/10).

## Verificação

- `pytest -q test_versoes.py test_locais_entre_turnos.py`: 25 passaram, golden incluso.
- `pytest -q -m "not e2e"`: 450 passaram e 1 foi pulado (o de antes), sem os 80 e2e. A mudança não toca no front-end.
- `ruff check --line-length 120` sem apontamentos nos seis arquivos. `mypy` sem erros nos três módulos novos; resta
  um erro antigo em `ingerir_eleitorado.py` (tipo de `val` entre os dois laços de impressão).
- O SHA-512 da versão de 15/10 guardada é o do arquivo baixado de manhã. A de 16/10 confere com a proveniência
  gravada pelo download.

## Pendências

- **Rodar de novo antes do 2º turno:** o TSE pode regerar o cadastro outra vez antes de 25/10.
  `python ingerir_eleitorado.py --ano 2026 --atualizar --uf todas` e `python locais_entre_turnos.py --ufs todas`
  (no roteiro, em 24/10).
- **Depois de 25/10, conferir com onde a seção votou:** o `votacao_secao_2026` do 2º turno traz o local de cada seção.
  Uma comparação cadastro × votação mostraria a interdição de última hora (TODO 30).
- **Ligar o acervo ao vigia dos microdados** (TODO 30): falta decidir quantas versões guardar, por causa do espaço.
