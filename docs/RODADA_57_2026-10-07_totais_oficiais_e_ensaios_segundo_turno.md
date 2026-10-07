# Rodada 57 — Totais oficiais de 2026 e prontidão do 2º turno (ensaios do ES e do AM)

07/10/2026 · o TSE publicou os microdados que faltavam do 1º turno, e a preparação do 2º turno (25/10) foi fechada:
- prontidão;
- ensaios em duas UFs com 2º turno de Governador;
- roteiro (TODO 26).

Os ensaios acharam três defeitos, corrigidos com teste. Um deles afetaria a noite: um alerta que não sairia.

## Totais oficiais do 1º turno de 2026

- **Publicação no TSE** (horário de Brasília):

  | Arquivo | Publicação |
  |---|---|
  | `votacao_partido_munzona_2026` | 10h10 |
  | `detalhe_votacao_munzona_2026` | 10h21 |
  | `votacao_candidato_munzona_2026` (regerado) | 10h47 |
  | `votacao_partido_munzona_2026` e `consulta_cand_2026` (regerados de novo) | 12h35–12h39 |

- **Importação:** as duas vigias (RJ e lote das 26 UFs, reiniciado com o código da rodada 55) importaram os totais
  **oficiais** e encerraram sozinhas: as 26 UFs às 10h37–10h38 e o RJ às 11h00.
- **Arquivos regerados depois de as vigias encerrarem:**
  - RJ: `python preparar_2026.py`;
  - outras UFs: `preparar_2026.importar(a, "munzona", 1)` por UF. A vigia do lote não reimporta etapa "ok".
- **Conferência noite × oficial, 27 UFs:**
  - **Cadeiras:** iguais em todas.
  - **Votos dos candidatos:** iguais em 26 UFs.
  - **Totais:** a única diferença comum é `SECOES_TOTAL`, porque o oficial conta as seções agregadas.
  - **Presidente no RJ:** os 774 votos que diferiam no provisório (destinação ainda não publicada) agora batem.
- **Pernambuco, a exceção:** deputado federal nº 4033 ("ZOZOI DO IBURA" na noite).
  - Os votos estavam "anulados sub judice" na noite e não constam do candidato_munzona oficial.
  - O `consulta_cand` atual traz outro nome no número ("GERMANA LACERDA").
  - Por isso os **772 votos passaram de sub judice a nulo técnico**: é decisão do TSE depois da eleição, não erro.
  - Cadeiras iguais: 25/25 e 49/49.
- **Provisório (seções) × oficial no RJ** (`saidas/conferencia_secoes_x_munzona_1t.csv`): além de `SECOES_TOTAL`,
  ~3 mil votos de Presidente passaram de válidos a nulos com a destinação oficial.

## Prontidão do 2º turno

`verificar_prontidao.py --turno 2 --ufs todas --testes`: **0 falhas**.

- **2º turno de Governador:** AC, AM, DF, ES, RJ, RN e TO, tirados do resultado do 1º turno.
- **Códigos oficiais já no `ele-c.json`:** Governador 6260, Presidente 6258. O acompanhamento ainda dá 404, o
  normal antes de 25/10.
- **Pastas `oficial_t2_<UF>`:** 25 delas já existem, com só o `status.json` e tabelas vazias de um teste de 06/10.
  O coletor continua delas.
- **Defeito, a checagem do relógio:** lia a hora no **simulado**, que saiu do ar depois do 1º turno (o nome nem
  resolvia). Agora ela lê do oficial e só cai no simulado se ele falhar.

## Ensaio do ES (2º turno de 2022): o TSE simulado carimbava o resultado com a hora errada

- **1ª execução: PROBLEMAS.** 11 abrangências (o estado e 10 municípios) ficaram em 99,99%, sem totalização final.
  Por isso não houve eleito, boletim final nem cópia completa.
- **Causa** (`ensaio.Gerador.resultado`):
  - a fotografia da apuração é do minuto cheio, mas o EA20 levava o carimbo (`dg`/`hg`) da hora exata;
  - **exemplo, município 56162:** a totalização final foi anunciada às 18:02:33 (33/33 seções), mas o EA20 das
    18:02:45 mostrava 18:02:00 (26/33);
  - o coletor seguiu a regra da rodada 36 (EA20 gerado depois do anúncio contém a totalização). Aceitou a versão
    como final e nunca mais a pediu.
  - O TSE real não faz isso, porque gera o EA20 depois do conteúdo. Em 06/10, o mesmo ensaio tinha passado por
    sorte no tempo dos ciclos.
- **Correção:** o carimbo do EA20 passou a ser o minuto da fotografia.
- **2ª execução: OK.**
  - Válidos iguais ao oficial: Presidente 2.208.912 e Governador 2.177.309.
  - 100% e final nos dois cargos.
  - Renato Casagrande eleito.
  - Alerta de "vitória projetada" às 18h.
  - Cópia final com as 1.349 parciais; boletim final gravado.

## Ensaio do AM (2º turno de 2022): o alerta da primeira leitura saía em silêncio

- **Apuração do AM em 2022:** foi das 16h58 às 0h22 (as seções do interior), cerca de 15 minutos reais a 30×.
- **1ª execução:** tudo certo, **menos** o alerta de leitura do Governador. A projeção já dizia "vitória
  projetada" às 17h20, com 8% apurado, e nenhum alerta saiu.
- **Causa** (`alertas.Vigia._leituras`):
  - sem seção apurada, a leitura não era gravada;
  - a primeira leitura gravada já era "vitória projetada", e a regra "a 1ª observação é silenciosa" a calava.
- **Correção:** grava "sem apuração" enquanto nada está apurado, e a primeira leitura real vira notícia
  ("Antes: sem apuração").
  - Um site que sobe no meio da apuração, sem `alertas.json`, continua sem alerta falso.
  - Um reinício também, porque o estado fica salvo no arquivo.
- **2ª execução: OK.**
  - Válidos iguais ao oficial: Presidente 1.966.732 e Governador 1.834.290.
  - 100% e final nos dois cargos.
  - Wilson Lima eleito.
  - Alerta às 17h16.
  - Cópia final com as 1.701 parciais.

## Série do candidato quebrava com hora vazia

- **Sintoma:** no site da noite de 4/10 (porta 8000), `/api/candidato/serie` dava `AttributeError: 'NoneType'
  object has no attribute 'isoformat'` (relatado pelo usuário com captura de tela).
- **Causa:** `historico_candidatos/` tem **790 linhas sem `DT_TOTALIZACAO`** (158 por cargo, municípios). São
  abrangências que o TSE publicou com a data vazia antes de totalizar.
- **Correção:** `serie_candidato` descarta esses pontos, como `para_grafico` já fazia.
- **Com os dados reais:** a série do Presidente sai com 90 pontos no Rio e 116 no estado.
- **Site no ar:** precisa ser reiniciado para ler o código novo. Sob o vigia, basta encerrar o processo do site.

## Roteiro

`docs/ROTEIRO_NOITE_DA_ELEICAO.md` foi reescrito com o 2º turno primeiro:
- UFs e códigos;
- a sequência da noite, com o site de todas as UFs sob o vigia na porta 8001;
- as pastas que não podem ser apagadas;
- a seção "Depois", com as datas reais dos microdados do 1º turno, a CDN com cópia velha e as vigias do 2º turno
  com o Boletim de Urna como total provisório (`--bweb-brasil`).

Com isso, o TODO 26 está feito.

## Arquivos

- `verificar_prontidao.py` (`_relogio`) e `test_prontidao.py`.
- `apuracao/ensaio.py` (`Gerador.resultado`) e `test_ensaio.py` (`test_ea20_carimbado_com_o_minuto_da_fotografia`).
- `apuracao/alertas.py` (`_leituras`) e `test_alertas.py`
  (`test_leitura_definida_logo_no_inicio_da_apuracao_e_noticia`).
- `apuracao/divulgacao/serie.py` (`serie_candidato`) e `test_serie.py`
  (`test_serie_por_municipio_ignora_linha_sem_hora`).
- `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/TODO.md` e `docs/INDEX.md`.
- **Commits:** `7dbafae`, `6fe892e`, `4d1555c` e `1a6c7bd`.

## Verificação

- Cada teste novo falha sem a correção e passa com ela (conferido com `git stash`).
- `pytest -q -m "not e2e"`: 403 passados e 1 pulado.
- Ensaios do 2º turno: ES e AM com "RESULTADO DO ENSAIO: OK".
- Prontidão do 2º turno: 0 falhas, 7 avisos (acompanhamento em 404 nas 7 UFs com Governador).

## Pendências

- **Opcionais antes de 25/10:**
  - ensaio em RN ou TO;
  - conferência do RJ em `saidas/RJ/` (hoje em `saidas/`);
  - ~~download dos microdados que retoma de onde parou~~ (feito na rodada 58).
- **O aviso "o TSE ainda serve resultado anterior … depois de 15 ciclos":** ainda aparece nos ensaios (3 no ES, 7
  no AM), sem afetar o fim. É o limite `TENTATIVAS_ANTIGO` com o atraso do EA20 de 3 min. Vale observar na noite
  real em `arquivos_antigos` do `status.json`.
- **Depois de 25/10:** os microdados do 2º turno e as análises listadas no roteiro.
