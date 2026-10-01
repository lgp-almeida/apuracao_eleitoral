# Rodada 24 — Vigia e preparo dos microdados de 2026

30/09/2026 · pedido do usuário: "Implemente o item 4" (item 4 de `docs/TODO.md`: preparar os dados de 2026 assim que o TSE publicar)

## Achado que definiu o desenho

Em 30/09/2026, quatro dias antes do pleito, a CDN do TSE **já responde 200** para `detalhe_votacao_munzona_2026`, `votacao_candidato_munzona_2026` e `votacao_partido_munzona_2026`, todos modificados hoje às 11h35. Cada CSV tem **só o cabeçalho** (671 bytes por UF). Os votos por seção (`votacao_secao_2026_RJ`/`_BR`) e o `detalhe_votacao_secao_2026` dão 404.

Consequências:
1. **"Publicado" não é "responde 200":** o vigia só considera que chegou quando o CSV da UF tem pelo menos **uma linha de dados** (`tem_dados`).
2. **O TSE regera os arquivos no mesmo endereço.** O `download` do núcleo nunca baixa de novo o que já está no cache, então um ZIP só com cabeçalho que entrasse hoje ficaria lá para sempre. O vigia compara o **`Last-Modified` da CDN com o registrado no download** (`.proveniencia.json`) e, quando mudou:
   - baixa de novo, trocando o ZIP de forma atômica (diretório temporário e depois `replace`);
   - **apaga os Parquet derivados**, para a conversão ser refeita a partir da versão nova.
   Isso também cobre as retotalizações e correções depois do pleito.

## Entregas

- **`apuracao/microdados.py`:**
  - `ARQUIVOS` lista os 8 arquivos de 2026 e para que serve cada um (votos por seção UF/BR, detalhe por seção, detalhe munzona, candidatos, candidato munzona, partido munzona, perfil);
  - `verificar` faz um HEAD por arquivo e compara com o cache;
  - `preparar` baixa o que é novo ou foi atualizado, detecta "só cabeçalho", apaga os derivados e avisa quem precisa reagir;
  - `converter` gera os Parquet;
  - `limpar_cache_vazio` apaga ZIPs só com cabeçalho;
  - o estado fica em `cache_tse/microdados_2026.json`.
- **`preparar_2026.py`:**
  - sem opções, faz uma verificação (8 HEADs) e prepara o que chegou;
  - `--vigiar` repete a cada hora (no mínimo 10 min entre verificações, para nunca martelar a CDN) e **encerra sozinho** quando os votos por seção da UF, do Brasil e o detalhe por seção chegam;
  - `--limpar-vazios`.
- **O que acontece quando os dados chegam, sem intervenção:**
  1. **Conversão para Parquet:** a partir daí os mapas e a comparação por bairro, o Perfil × voto e as planilhas oferecem 2026 sozinhos (eles descobrem os anos pelo cache).
  2. **Importação do resultado oficial** (`historico.importar`) para `dados_2026/historico_2026_t1` e, se houver, `_t2`. Abre com `python site_apuracao.py --dados dados_2026/historico_2026_t1`, e as cadeiras são conferidas com os eleitos oficiais.
  3. **Primeira análise:** `PerfilVoto.transferencias` calcula a **transferência 2022 → 2026 por bairro** e grava `saidas/transferencia_2022_2026.csv`.
     - Para os 3 primeiros de Presidente, Governador e Senador, cruza com o voto no mesmo partido e cargo em 2022.
     - Dá Pearson, Spearman, inclinação e R², em todos os bairros e na capital.

## Verificação

- **Real, hoje:** 1ª verificação:

  | Arquivo(s) | Situação | Ação |
  |---|---|---|
  | votos por seção, detalhe por seção | "não publicado" | esperar |
  | 3 munzona | "só cabeçalho (sem votos ainda)" | baixados |
  | cadastro de candidatos | "com dados" | baixado |
  | perfil | "com dados, em dia" | nada |

  A 2ª verificação não baixa nada: tudo "em dia".
- **Reação à chegada, com dados reais:** os microdados de 2022 fizeram o papel de 2026, num diretório temporário depois apagado. A reação converteu 4 conjuntos, importou o 1º turno (466 totais, 109.262 linhas de candidatos) e o 2º turno (94 totais) e gerou a transferência "2022 → 2022", com **r = 1,00 nas 18 linhas**, como deve ser com a mesma eleição dos dois lados.
- **`pytest -q`: 183 testes passando** (eram 176).
- **`test_microdados.py`**, 7 testes com uma CDN falsa que conta HEAD e GET:
  - nada publicado, só um HEAD por arquivo;
  - só cabeçalho não conta; a 2ª verificação não baixa nada; um `Last-Modified` novo no mesmo endereço baixa de novo e avisa;
  - a atualização apaga o Parquet derivado;
  - limpeza de ZIP vazio;
  - o CSV da UF certa no ZIP;
  - conversão;
  - o comando `--vigiar` espera 10 min e encerra quando os votos chegam.
  - Passam com a rede bloqueada.
- **Sabotagens** (restauradas byte a byte):
  - sem comparar o `Last-Modified`: 2 falhas;
  - sem apagar os derivados: 1 falha;
  - cabeçalho contando como dados: 3 falhas.

## Arquivos

- **Novos:** `apuracao/microdados.py`, `preparar_2026.py`, `test_microdados.py`.
- **Alterados:**
  - `apuracao/perfil.py` (`transferencias`);
  - `docs/ROTEIRO_NOITE_DA_ELEICAO.md` (seção "Depois");
  - `docs/TODO.md`, `docs/INDEX.md` e `CLAUDE.md`.
- **Cache:** os 3 ZIPs munzona de 2026, só com cabeçalho, e `consulta_cand_2026.zip`, com `microdados_2026.json`.

## Pendências

- **Depois de 4/10:** rodar `python preparar_2026.py --vigiar` e deixá-lo trabalhando.
- **Recalibração com 2026:** com o `detalhe_votacao_secao_2026` em mãos, recalibrar a projeção (`validar_projecao.py --ano 2026`) e as cadeiras (`--deputados`). É um passo manual, porque muda constantes do código.
- **Item 5 do TODO:** perfil por local de votação no estado inteiro.
