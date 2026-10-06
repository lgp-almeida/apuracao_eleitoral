# Rodada 43 — Lote 2: a noite do 2º turno com várias UFs (TODO 18)

06/10/2026 · lote 2 do plano de quitação do TODO ([RODADA_42](RODADA_42_2026-10-06_analise_coleta_e_percentuais.md)).
Decisão do usuário: o 2º turno (25/10) será acompanhado com o RJ e outras UFs, no site de várias UFs.

**Contexto:** em 25/10 haverá 2º turno para Governador em **AC, AM, DF, ES, RJ, RN e TO**, segundo o resultado do
1º turno coletado, e para Presidente (Flávio Bolsonaro × Lula). No `ele-c.json` oficial, as eleições do 2º turno
são **6260** (estadual) e **6258** (federal).

## Entregas

### Site de várias UFs pronto para a noite
- **Boletim, cópia e alertas de cada UF** (`apuracao/web/servicos.py`, `ServicosUFs`):
  - antes, com `--ufs` o site só avisava que eles "valem só no site de uma UF";
  - agora UMA thread percorre as UFs montadas, com os alertas a cada 15 s, o boletim a cada 30 s e a cópia a cada
    60 s; os próprios objetos decidem se há algo a fazer;
  - um erro numa UF vai para o log e não para as outras;
  - a cópia de cada UF fica em `<copia-dir>/<pasta da UF>`; uma cópia dentro da pasta de dados é recusada sem
    derrubar nada.
- **Defeito que impediria a noite:**
  - **antes:** `create_multi_app` dava erro se nenhuma UF tivesse dados. No 2º turno as pastas
    `oficial_t2_<UF>` começam vazias, então o site não subia antes do 1º ciclo do coletor;
  - **agora:** com `--coletar` o site sobe mesmo vazio (página "Aguardando", que recarrega sozinha) e **monta
    cada UF quando ela ganha dados, sem reiniciar** (em `/ufs.json`, `/`, `/<uf>` e pela thread de serviços);
  - os serviços da UF começam no momento em que ela é montada (`ao_montar`).
- **Defeito na aba "1º → 2º turno":**
  - **antes:** `dir_1t` só achava o 1º turno se a pasta terminasse em `_t2`; com a UF no nome
    (`oficial_t2_RJ`, inclusive no site de uma UF) a transferência em tempo real ficava indisponível;
  - **agora:** acha `oficial_<UF>` e, no RJ, a pasta antiga `oficial`; nunca usa o 1º turno de outra UF.

### Prontidão do 2º turno por UF
- **Comando:** `python verificar_prontidao.py --turno 2 --ufs todas`.
- **O que confere:**
  - as eleições do 2º turno no `ele-c.json` (FALHA se faltarem);
  - as UFs com 2º turno para Governador, tiradas do resultado do 1º turno, sem rede;
  - por UF: a pasta do 2º turno (vazia, do oficial, ou FALHA se for de outro ambiente), a referência de 2022 do
    2º turno e a pasta do 1º turno;
  - o acompanhamento só das 7 UFs com 2º turno (404 repetido bloqueia o IP);
  - as portas 8000 e 8001.
- **Resultado em 06/10:** **PRONTO, 0 falhas**. 10 avisos esperados:
  - acompanhamento ainda 404 nas 7 UFs;
  - portas 8000 e 8001 com os sites no ar;
  - relógio do simulado do TSE inacessível.

### Referência de 2022 do 2º turno das 27 UFs
`python baixar_ufs.py --etapas historico --turnos 2`: 27 UFs em cerca de 0,5 s cada (fonte munzona; ES pela fonte
"secao"). Antes só o RJ tinha; sem isso, a aba Comparação do 2º turno ficaria vazia nas outras UFs.

### Ensaio de qualquer UF e do 2º turno
- **Comando:** `ensaio_apuracao.py --uf <UF> --turno 2`.
- **Reconstituição** (`ensaio.carregar_2022(..., uf, turno=2)`):
  - o 2º turno de 2022, com Governador se a UF teve e Presidente;
  - no 2º turno, o mais votado no Brasil é o eleito;
  - cargo sem esse turno na UF sai (o RJ não teve 2º turno para Governador em 2022).
- **Servidor falso:** serve os códigos `cdt2` do recorte (21271/21273), então o coletor percorre o **caminho de 2º
  turno** (só Governador e Presidente), que nunca tinha sido ensaiado.
- **Conferências:** deixaram de ser fixas no RJ ("Castro eleito", 46/70 cadeiras). Agora vêm do histórico da UF
  e do turno: válidos, apuração final, cadeiras (só no 1º turno) e eleitos dos majoritários.
- **Resultado com o ES** (Governador + Presidente, 2º turno de 2022, velocidade 60; `votacao_secao_2022_ES`, 50 MB,
  baixado):

  | Conferência | Resultado |
  |---|---|
  | válidos de Presidente | 2.208.912 = oficial |
  | válidos de Governador | 2.177.309 = oficial |
  | eleito | Renato Casagrande, como em 2022 |
  | alertas | nenhum crítico; leitura "vitória" às 17h58 |
  | cópia | com as 898 parciais |
  | boletim | final gravado |

  **"RESULTADO DO ENSAIO: OK".**
- **`analisar_coleta.py` sobre esse ensaio:** 846 totalizações municipais. As 7 versões que a regra chamou de
  anteriores tinham de fato outro conteúdo, e 714 de 721 totalizações vieram certas de primeira.
- **O ensaio do RJ (1º turno)** continua igual; foi rodado de novo no lote 1, com resultado OK.

### Roteiro
`docs/ROTEIRO_NOITE_DA_ELEICAO.md` ganhou a tabela da noite do 2º turno com várias UFs:
- comando do site sob o vigia (`--turno 2 --ufs todas --coletar --porta 8001 --copia-dir …`);
- prontidão e ensaio;
- o aviso de **não apagar `dados_2026/oficial_t2_*`** depois da noite;
- a análise das parciais ao fim.

## Arquivos

- **Novos:** `apuracao/web/servicos.py`.
- **Alterados:**
  - `apuracao/web/multi.py` (montagem sob demanda, `permitir_vazio`, `ao_montar`);
  - `site_apuracao.py` (serviços por UF);
  - `apuracao/web/app.py` (`dir_1t`);
  - `verificar_prontidao.py` (`--turno 2 --ufs`);
  - `apuracao/ensaio.py` e `ensaio_apuracao.py` (`--uf`, `--turno`).
- **Testes:** `test_site.py` (+2), `test_prontidao.py` (+1), `test_transferencia.py` (+1).
- **Docs:** roteiro, TODO, INDEX, CLAUDE.md.

## Verificação

- `pytest -q`: 378 testes passando.
- Ensaio do ES no 2º turno: OK. Prontidão do 2º turno: 0 falhas.

## Pendências

- **Rodada 44 (lote 3):** margem do 2º turno e por UF (`validar_projecao.py --turno 2 --ufs`) e recalibração com
  2026 (TODO 4b).
- **Usuários simulados do ensaio:** no 2º turno eles ainda consultam rotas de cargos que não existem (deputados,
  Senador) e recebem 404. Não é erro, mas poderiam usar só os cargos da reconstituição.
