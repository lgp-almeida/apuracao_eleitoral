# Rodada 36 — Noite de 4/10: descompassos da coleta e as correções

04/10/2026 · pedidos do usuário:
- "Estou com problema, veja: … nenhuma eleição do 1º turno no ele-c.json — nova tentativa em 300s … Outros sites que acessam o TSE já estão disponibilizando dados."
- "Avalie a evolução dos downloads, pois ocorreram alguns descompassos na apuração. Preciso saber se foi problema no TSE ou erros ocorridos aqui."
- "Sim, faça a correção e registre a rodada 34. Já subi o site novamente."

O pedido falava em "rodada 34", mas as rodadas 34 (IBGE) e 35 (Presidente por UF) já existiam. Por isso este registro é a **rodada 36**.

## Resposta curta

Houve problemas **dos dois lados**, mas o descompasso que se viu no site foi **principalmente nosso**:
- o TSE anuncia a totalização de um município no acompanhamento (EA15) **antes** de regerar o resultado (EA20);
- o coletor aceitava o EA20 que viesse, mesmo na versão anterior, e não pedia de novo;
- só os reinícios manuais traziam as versões novas.

## O que aconteceu (análise de `dados_2026/oficial/raw/`)

### Visão geral

- **7.210 versões** baixadas, das 17h28 às 22h03.
- O acompanhamento chegou com 1–2 min de atraso em relação à geração no TSE.

### Defeito nosso: confirmação sem conferir a versão

- **2.820 de 7.423 totalizações municipais (38%)** receberam primeiro a **versão anterior** do EA20.
- Tempo até termos a versão certa:
  - quando o EA20 já veio certo: mediana de **1,2 min**;
  - quando veio a versão anterior: mediana de **4,7 min**, p95 de **25 min** e máximo de **83 min**.
- As levas atrasadas só se corrigiram nos **reinícios manuais**:

| Reinício | Versões novas recuperadas |
|---|---|
| 18h55 | 62 |
| 19h20 | 65 |
| 19h55 | 203 |
| 21h50 | 117 |

### Defeito nosso: ciclo errado no `ele-c.json`

- O `ele-c.json` oficial tem **54 pleitos**: o primeiro é `ele2024`, e os de `ele2026` vêm por último:
  - 6257 (federal) e 6259 (estadual);
  - 6258 e 6260 no 2º turno;
  - 6261 (municipal).
- O `parse_config` usava `pl[0]`, então o coletor não achava a eleição do 1º turno.
- **Tempo perdido:** cerca de 6 min. O TSE gerou os primeiros arquivos às 17h21; a coleta começou às 17h28, depois da correção.
- A simulação usada no ensaio só tinha um pleito, e a prontidão de 3/10 só verificava se o arquivo respondia. Por isso o erro não apareceu antes.

### Interrupções do nosso lado

- **Parada das 17h53 às 18h05:** o terminal foi fechado. O log do vigia não registra o encerramento.
- **Reinícios manuais:** 17h28, 18h56, 19h22, 19h54, 20h25, 21h52 e 22h04.

### Lado do TSE

- **Pausa das 19h32 às 20h05:** o acompanhamento ficou sem nova geração por 13 e 20 min. O alerta "Apuração sem avanço" disparou às 19h52.
- **EA20 depois do anúncio:**
  - mediana de 0,2–0,9 min e p95 de 5–10 min;
  - na janela das 19h30, até **41 min**.
- **Peculiaridades dos arquivos:**
  - nos EA20 de deputados, o `dt`/`ht` fica **1–2 min antes** da hora anunciada (12 casos). Por isso a conferência usa a **geração** do arquivo (`dg`/`hg`), não o `dt`/`ht`;
  - o EA14 nacional traz uma hora de totalização **no futuro** (05/10 09h19 na noite; 30/09 07h10 no simulado).

### Estado em disco às 22h05

| Fonte | Apurado | Hora |
|---|---|---|
| Nossos dados | 99,99% | 21h48 |
| TSE, eleição 6257 | 100% | 22h04 |
| TSE, eleição 6259 | 100% | 22h19 |

O site foi reiniciado pelo usuário depois, sob o vigia.

## Correções

### 1. Ciclo mais recente do `ele-c.json` (`modelo.parse_config`)

- Usa o ciclo de **maior ano** em `c` (por exemplo, `ele2026`).
- Junta as eleições de **todos os pleitos** desse ciclo, porque o 2º turno pode vir num pleito próprio.
- Teste com o arquivo oficial real: `tests/fixtures/divulgacao/ele-c-oficial-2026-10-02.json`.

### 2. Só aceitar o EA20 gerado depois do anúncio (`coletor.py`)

- **Regra:** a totalização anunciada no EA15/EA14 só é dada por vista se o EA20 tiver sido **gerado** (`dg`/`hg`) **depois** da hora anunciada.
- **Versão anterior** (`_versao_anterior`):
  - o arquivo é pedido de novo no ciclo seguinte. Em geral o TSE responde 304, um pedido barato;
  - o limite é de `TENTATIVAS_ANTIGO = 15` ciclos. Depois disso, aceita com aviso no log, para que um quirk do TSE não deixe o arquivo travado.
- **Hora no futuro** (`_limitar`): a hora anunciada é limitada à geração do próprio acompanhamento. Sem isso, o Presidente-BR ficaria "antigo" para sempre.
- **Status e log:**
  - `ResumoCiclo.arquivos_antigos`;
  - `arquivos_antigos` no `status.json`;
  - "N ainda na versão anterior" no log do ciclo.
- **Validação com os dados da noite:**
  - o critério reconhece **1.634 de 1.667** versões anteriores;
  - aceita de primeira **85.077 de 86.011** versões corretas.
  - As 934 restantes seriam pedidas de novo, a custo de um 304 cada, e aceitas no ciclo seguinte.

### 3. Ensaio com o atraso do TSE (`ensaio.Gerador`, `ensaio_apuracao.py --atraso-ea20`)

- O gerador do ensaio pode servir o EA20 com geração `atraso` minutos antes do relógio virtual. O padrão é **3 min**.
- Assim, o ensaio reproduz o "anuncia antes de publicar" da noite.
- A tabela de ciclos ganhou a coluna "antigos".

### 4. Prontidão (`verificar_prontidao._ambiente`)

- Passa a verificar as **eleições que o coletor usaria** (Governador e Presidente no ciclo escolhido).
- Se faltar alguma no ciclo 2026, o resultado é FALHA; antes de 2026 ser publicado, é AVISO.

## Arquivos

- **Alterados:**
  - `apuracao/divulgacao/modelo.py`: `parse_config`, `_ano_do_ciclo`;
  - `apuracao/divulgacao/coletor.py`: `TENTATIVAS_ANTIGO`, `_versao_anterior`, `_limitar`, `_ab_gerado`, `arquivos_antigos`;
  - `apuracao/ensaio.py`, `ensaio_apuracao.py`: atraso do EA20;
  - `verificar_prontidao.py`;
  - `conftest.py`: `FakeTSE.totalizar(..., publicar=)` e `FakeTSE.publicar`, para que o falso regere o EA20 como o TSE;
  - testes: `test_divulgacao.py` (+4), `test_ensaio.py` (+1) e `test_prontidao.py` (+1);
  - `test_portal.py`: o teste lia o estado do vigia **real** (`dados_2026/vigia`) e falhava com o site oficial no ar. Agora usa uma pasta temporária;
  - `CLAUDE.md`, `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/INDEX.md`.
- **Novo:** `tests/fixtures/divulgacao/ele-c-oficial-2026-10-02.json`.

## Verificação

- **Sem a correção, os testes novos falham:** com o código antigo, os dois testes principais do coletor falham.
- **Suíte:**
  - `pytest -q -m "not e2e"`: 264 passando;
  - `pytest -q -m e2e`: 57 passando.
- **Ciclo real no oficial** (depois da correção do `parse_config`): 493 arquivos, sem erro.
- **Ensaio geral** (`python ensaio_apuracao.py`, com `--atraso-ea20 3`): **OK** em 14,4 min.
  - 52 ciclos, 7.097 pedidos, 5.666 arquivos novos, nenhum erro;
  - **2.035 respostas na versão anterior**, todas pedidas de novo;
  - 5.117 consultas ao site, nenhum 5xx; painel com p50/p95 de 148/815 ms;
  - conferência com o oficial: válidos de Presidente, Governador e Senador **exatos**; deputados a 0,005–0,006%; tudo 100% e final; cadeiras **46/46 e 70/70** sem divergência; Castro eleito no 1º turno; cópia final com 5.822 de 5.822 parciais; boletim final com "o que mudou".

## Achados no ensaio

- **O primeiro ensaio terminou em PROBLEMAS** (99,997% apurado, sem boletim e sem cópia final). O relógio do ensaio parava no fim de 2022 (00h20), e o EA20 simulado é gerado 3 min antes do relógio. Assim, a última totalização anunciada nunca era publicada, e o coletor a tratava corretamente como versão anterior.
- **Correção:** o relógio do ensaio vai até o fim mais o atraso (00h23), como no TSE real, que regera o EA20 depois do último anúncio. O teste do ensaio já fazia isso (`fim + 5 min` com o relógio fixado).
- **Avisos de "depois de 15 ciclos" no log** (7 no ensaio): aparecem em abrangências que seguem totalizando a cada ciclo, como a UF, a capital e o Brasil. Com ~7 min virtuais por ciclo e o EA20 sempre 3 min atrás, quase sempre há uma seção anunciada ainda não publicada.
  - É só ruído: o que chega é **sempre gravado**, e a abrangência continua sendo pedida a cada nova totalização.
  - O total final confere com o oficial.

## Pendências

- **2º turno (25/10):**
  - rodar o ensaio e a prontidão na véspera;
  - conferir no `ele-c.json` que os pleitos 6258 e 6260 aparecem no ciclo `ele2026`.
- **Fechar o terminal derruba o vigia junto com o site.** No 2º turno, rodar o vigia em `tmux`/`screen` ou com `nohup`.
- **Análise das parciais (TODO 15–17):** a análise desta rodada usou `raw/`. Os scripts ficaram no diretório temporário da sessão; vale transformá-los numa ferramenta (`analisar_coleta.py`).
