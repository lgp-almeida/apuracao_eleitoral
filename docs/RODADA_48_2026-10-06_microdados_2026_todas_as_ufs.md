# Rodada 48 — Microdados de 2026 nas 27 UFs, correções no IBGE e a legenda de federação nos totais provisórios

06/10/2026 · depois do fim do plano de quitação do TODO ([RODADA_47](RODADA_47_2026-10-06_comparacao_ufs_e_eliminados.md)).

**Contexto:** a importação do RJ da [RODADA_40](RODADA_40_2026-10-06_totais_sem_munzona.md) foi feita em outro
computador. Nesta máquina, o cache tinha só os ZIPs de 2026 de 30/09 (quase todos só com cabeçalho) e nenhum
`historico_2026_*`.

## O que o TSE publicou (verificado às 19h30 de 06/10)

Feito com `preparar_2026.py --so-verificar`, mais um HEAD por arquivo de UF nas 27 UFs.

| Arquivo | Situação no TSE |
|---|---|
| `votacao_secao_2026_<UF>.zip` | **publicado nas 27 UFs** (06/10 ~04:57 GMT; AL regerado às 19:22 GMT). SP 788 MB, MG 256 MB, RJ 290 MB; 2,6 GB no total |
| `votacao_secao_2026_BR.zip` (Presidente) | publicado, 143 MB |
| `votacao_secao_2026_ZZ.zip` (exterior) | publicado, 0,18 MB |
| `detalhe_votacao_secao_2026.zip` | publicado em 05/10, 171 MB |
| `votacao_candidato_munzona_2026.zip` | publicado em 05/10, 316 MB (sem a destinação de Presidente) |
| `consulta_cand_2026.zip` | regerado em 05/10 |
| `perfil_eleitor_secao_2026_<UF>.zip` | 27 UFs, de 17/07, sem mudança |
| `detalhe_votacao_munzona_2026.zip` | **404, ainda não publicado** |
| `votacao_partido_munzona_2026.zip` | **404, ainda não publicado** |
| `eleitorado_local_votacao_2026.zip` | **regerado em 06/10 às 09:34 GMT**: de 88 MB (29/09, o do cache) para 176 MB (ver abaixo) |

## Lote das 27 UFs

- **Comando:** `baixar_ufs.py --etapas microdados --ufs todas --vigiar`, iniciado às 19:39 e com log em
  `logs/microdados_2026_vigiar.log`.
- **1ª passada:** de 19:39 a 20:23. As 27 UFs foram importadas em `dados_2026/historico_2026_t1_<UF>` com
  **totais provisórios**, reconstruídos das seções. Todas ficaram `aguardando` ("falta no TSE: detalhe_munzona,
  partido_munzona").
  - **Tempo por UF:** de 19 s (DF, AP) a 153 s (MG). **SP levou 1.013 s.**
  - **2º turno:** nada, porque o 2º turno é em 25/10.
- **Depois da passada:** o vigia volta ao TSE a cada **60 min**. Quando os dois arquivos munzona saírem, ele
  reimporta com os totais oficiais e grava `saidas/<UF>/conferencia_totais_2026_t1.csv`.
- **Conferência com a noite:** `saidas/<UF>/conferencia_2026_t1.xlsx`, em **25 UFs**. SP e TO ficaram sem ela,
  porque nesta máquina falta a coleta da noite: não há `dados_2026/oficial_TO`, e `oficial_SP` só tem `raw/`
  (120 KB, sem `status.json`). A conferência é pulada sem aviso nesse caso.
- **Transferência 2022 → 2026 por bairro:** `saidas/<UF>/transferencia_2022_2026.csv`, com 18 linhas por UF.
  Não sai no DF nem no TO, porque o IBGE não publica malha de bairros dessas UFs.

## Correções

### 404 do IBGE atribuído ao TSE (`fae57c0`)

- **Problema:** `download()` (`votos_por_local_votacao.py`) acrescentava a todo 404 a dica "os microdados podem
  ainda não ter sido publicados (o TSE publica alguns dias após o pleito)". Isso valia até para a malha de
  bairros do DF e do TO no geoftp do IBGE.
- **Correção:** a dica agora só vale para URLs do CDN do TSE (`CDN_BASE`).
- **Teste:** `test_download_404_so_atribui_ao_tse_o_que_e_do_tse`.
- **Atenção:** o lote em andamento carregou o código antigo, então o log ainda mostra a frase velha no DF e no TO.

### Setores do Censo sem município, RS (`2213a1e`)

- **Problema:** `perfil_local.setores` quebrava no RS com "cannot convert float NaN to integer". A malha de
  setores tem dois setores sem `CD_MUN` (43000010… com 2.884 km² e 43000020… com 10.202 km²). Pelas áreas, são
  a Lagoa Mirim e a Lagoa dos Patos, sem população.
- **Correção:** a leitura da malha foi para `_pontos`, que descarta setor sem município.
- **Resultado:** RS gerado à mão em seguida, com 25.567 setores, **497 municípios** e **10.882.965
  habitantes**, os números do Censo 2022.
- **Teste:** `test_setor_sem_municipio_sai_da_malha`.

## Eleitorado de 2026 regerado pelo TSE

O `download` nunca baixa de novo um arquivo que já existe, por isso a troca foi feita à mão.

- **Backup:** o ZIP de 29/09, a proveniência e os 27 Parquet foram para
  `cache_tse/anterior/eleitorado_2026_de_2026-09-29/`.
- **Arquivo novo:** gerado pelo TSE em 06/10 às 06:29 e baixado por
  `baixar_ufs.py --etapas eleitorado --anos-eleitorado 2026 --ufs todas --refazer`. As 27 UFs ficaram ok.
- **Por que dobrou de tamanho:** passa a trazer o cadastro dos **dois turnos** (`NR_TURNO` 1 e 2, as mesmas
  seções), como o de 2022 já trazia. `eleitorado.load_sections` filtra `turno` (padrão 1), então nada sai em
  dobro.
- **1º turno, novo × antigo, 27 UFs:** as **mesmas seções e o mesmo eleitorado** (RJ: 38.738 seções e
  12.857.000 eleitores).
  - **Mudanças:** 8.332 seções com coordenada diferente, 827 com nome do local diferente, 464 que trocaram de
    local (nº do local) e 267 com bairro-texto diferente.
  - **Onde mais mudou:** BA (2.293 coordenadas), SP (1.029), RN (880) e MG (820). No PA, 200 seções trocaram de
    local; em SE, 73. AC, AM e MT não mudaram nada.
- **Transferência 2022 → 2026 por bairro:** refeita nas 25 UFs com malha, sobre as coordenadas novas. O log
  está em `logs/transferencia_eleitorado_novo.log`.

## Dados de 2022 das 27 UFs nesta máquina

- **Antes:** só o RJ tinha o resultado de 2022 importado. Faltavam os votos por seção do DF e do TO, e o perfil
  do eleitor de todas as UFs, menos o RJ.
- **Comando:** `baixar_ufs.py --etapas historico eleitorado --anos 2022 --turnos 1 2 --anos-eleitorado 2022 --ufs
  todas`, mais os votos por seção de 2022 do DF e do TO. As 108 tarefas ficaram **ok**.
- **Resultado (`historico_2022_t{1,2}_<UF>`):**
  - o histórico dos dois turnos nas 27 UFs. No RJ continua a pasta antiga, sem sufixo.
  - o cadastro de eleitorado e o perfil do eleitor de 2022 das 27 UFs. Só o perfil de SP tem 16,5 milhões de
    linhas.
- **Fonte dos votos:** DF e TO foram importados pela fonte "munzona", porque os votos por seção deles chegaram
  depois; as demais UFs, pela "secao". As duas fontes dão os mesmos votos e eleitos (rodada 39). A diferença é
  que a "munzona" não lista candidato inapto.
- **Pendências do lote:** as 25 que aparecem são a divulgação do 2º turno de 2026, que só existe em 25/10.

## Achado e correção: a legenda nos totais provisórios

A conferência tempo real × importado (`conferir_resultado`, rodada 45) bate **as cadeiras de deputado nas 27
UFs**. Nos votos, porém, há diferenças.

### Presidente (todas as UFs): esperado

- **Candidato 28:** aparece só no importado, e seus votos contam como válidos. A noite os deu como nulos.
- **Situação:** 12 candidatos com SITUACAO "Não informado" no importado.
- **Causa:** o TSE ainda não publicou a destinação de Presidente no `votacao_candidato_munzona`. É o aviso que o
  `status.json` já traz, e some com o munzona.

### Deputados (22 das 25 UFs conferidas): defeito da regra da legenda (antes da correção)

Para cargo proporcional, `historico.detalhe_de_secoes` (regra da rodada 40) dizia:
"legenda válida se o **partido** tem candidato no cargo, senão nulo técnico". O RJ 2022, onde a regra foi
validada, não tinha o caso que a quebra. A diferença de LEGENDA no total de cada UF é **exatamente** a legenda
dos partidos sem voto nominal.

**1. Partido federado sem candidato próprio: o importado chama de nulo, a noite dá como legenda válida da
federação.**

| UF | Cargo | Partido | Votos de legenda |
|---|---|---|---|
| AC | Dep. Federal / Dep. Estadual | REDE | −71 / −62 |
| SC | Dep. Federal | PSDB | −2.138 |
| CE | Dep. Estadual | CIDADANIA | −2.287 |
| PB | Dep. Federal | PV | −1.744 |
| RR | Dep. Federal | PP | −660 |

Outros partidos no mesmo caso: PCdoB e PRD. É o caso mais comum.

**2. Partido com candidatos, todos sem voto válido (sub judice): o importado contava a legenda como válida, a
noite como anulada sub judice.**

| UF | Partido | Votos de legenda (Federal / Estadual) |
|---|---|---|
| MG | PCO | +457 / +437 |
| PR | PCO | +310 / +381 |
| PA | MOBILIZA | +491 / +491 |
| SE | PSOL | +1.222 / +1.282 |

- **Sem diferença:** BA, GO e RJ.
- **Efeito:** o erro passa para VALIDOS e daí para o quociente eleitoral. Nesta eleição, não mudou nenhum eleito.
- **Alcance:** os totais oficiais (`detalhe_votacao_munzona`) substituem os provisórios assim que saírem.

### Gabarito de 2022: o defeito era mais largo

- **Método:** a reconstrução de 2022 (`load_detalhe_secoes`) comparada com o detalhe munzona OFICIAL de 2022,
  nas 25 UFs com votos por seção no cache, em Dep. Federal, Estadual e Distrital, por (turno, cargo).
- **Ferramenta:** um validador de sessão, que não fica no repositório.
- **Resultado com a regra antiga:** **só RJ e PA batiam**. O oficial separa a legenda em válida, anulada sub
  judice e anulada, e isso mostrou quatro trocas:
  1. sócio de federação sem candidato próprio: legenda **válida** (nós: nulo técnico);
  2. agremiação só com candidatos sub judice: legenda **sub judice** (nós: válida);
  3. agremiação com todos os candidatos anulados: legenda **anulada**, ex.: SP 40.027 votos (nós: válida);
  4. voto nominal em candidato com destino **"Válido (legenda)"**: conta como **legenda**, não nominal
     (`QT_VOTOS_NOM_CONVR_LEG_VALIDOS`), ex.: RS 85.911 e RN 88.265 (nós: nominal).

### A regra nova (`historico.destino_legenda`)

- **Agremiação:** a legenda é da agremiação. Federação conta como um partido, inclusive o sócio sem candidato
  próprio. Como a composição da federação vem só por SIGLA ("PCDOB / PT / PV"), o número de cada sócio sai da
  sigla dos candidatos de qualquer UF, comparada por `partidos.chave`.
- **Destino da legenda, por (turno, UF, cargo):**

  | Candidatos da agremiação | Legenda vai para |
  |---|---|
  | algum com "Válido*" | válida |
  | nenhum válido, algum "Anulado sub judice" | sub judice |
  | todos anulados | anulada |
  | nenhum candidato | nulo técnico |

- **Voto nominal:** "Válido (legenda)" passa a contar como legenda.
- **Tabela de partidos:** a legenda do partido também passa a contar só quando é válida. Na noite, o PCO do PR
  tinha 0.
- **Colunas novas:** `destinacao_oficial` ganha SG_PARTIDO, NR_FEDERACAO e COMPOSICAO_FEDERACAO.
  - São opcionais: anos sem federação ficam sem elas.
  - `_parquet_com_colunas(..., opcionais)` só refaz o Parquet se o CSV tiver a coluna que falta.

### Resultado

| Gabarito | Regra antiga | Regra nova |
|---|---|---|
| 2022 × oficial | 2/25 UFs iguais | **16/25** |
| 2026 × noite | 3/25 UFs iguais | **24/25** |

- **Conferência de 2026 depois da reimportação:** **nenhuma diferença de deputado fora de RO**, e cadeiras
  iguais nas 25 UFs. O Presidente segue diferente, à espera da destinação do TSE.
- **O que sobra depende do DRAP do partido, que não está em nenhum arquivo público:**
  - **2022, 11 partidos em 9 UFs.** O oficial dá legenda **válida** a partido sem nenhum candidato votável
    (PRTB em AL, PCO na BA, PP no MT, PCB em GO e no MA…). Dá também a partido com todos os candidatos
    anulados (PCO na PB e no PR), enquanto o mesmo PCO, também todo anulado, tem legenda **anulada** em GO e em
    SC. Os dados de candidato são iguais e o resultado é oposto.
  - **2026, RO:** o MOBILIZA (Dep. Federal, 565 votos) não tem candidato no arquivo, e a noite pôs a legenda em
    sub judice.
- **Testes:**
  - `test_destino_da_legenda_pela_agremiacao`: cobre as quatro regras, a sigla vinda de outra UF e o ano sem
    federação.
  - `test_partido_soma_so_nominais_validos`: ganhou o caso da legenda sub judice.
  - Suíte: 339 testes ok, 1 pulado (sem os e2e).
- **Reimportação:** as 27 UFs de 2026 foram reimportadas com a regra nova (1–7 s por UF) e as conferências
  refeitas. O vigia foi parado, porque carregava o código antigo, e religado (PID 29719).

## Arquivos

- `votos_por_local_votacao.py`, `test_votos_por_local_votacao.py`: dica do 404 só para o TSE.
- `apuracao/perfil_local.py`, `test_perfil_local.py`: `_pontos`, setor sem município.
- `apuracao/historico.py`, `test_historico.py`: `destino_legenda`, `_agremiacoes`, colunas de federação na
  destinação, "Válido (legenda)", legenda válida na tabela de partidos.
- Dados (fora do git): `cache_tse/` (+ 11,7 GB: ZIPs e Parquet de 2026, malhas e Censo das UFs), `dados_2026/historico_2026_t1_<UF>`
  (27), `saidas/<UF>/`.

## Verificação

- `pytest -q test_votos_por_local_votacao.py test_ibge.py test_microdados.py test_perfil_local.py`: tudo passa.
- Os 27 resultados `microdados_2026 aguardando` e as conferências por UF estão no log, resumidas acima.

## Pendências

1. **Legenda que depende do DRAP:** os casos restantes acima ficam até os totais oficiais. A tabela de partidos
   do histórico de anos com `votacao_partido_munzona` poderia ler a legenda de lá, em vez da regra.
2. **Totais oficiais:** com `detalhe_votacao_munzona` e `votacao_partido_munzona`, a importação definitiva sai
   sozinha pelo vigia em execução. Depois, conferir `conferencia_totais_2026_t1.csv`.
3. **Coleta da noite de SP e TO nesta máquina:** rodar `baixar_ufs.py --etapas divulgacao --ufs SP TO` (se o
   TSE ainda servir os JSON da noite) e depois `conferir_resultado.py` nas duas. Avisar quando a conferência é
   pulada por falta da pasta da noite.
4. **Destinação de Presidente** no `votacao_candidato_munzona`: depende do TSE.
