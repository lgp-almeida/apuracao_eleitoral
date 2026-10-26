# Rodada 74 — Noite do 2º turno: cinco correções na coleta de todas as UFs (25/10/2026)

Rodada no ramo `frontend-refatoracao`, feita com o site no ar durante a apuração. Não mexe no front-end.

## Objetivo

Colocar no ar o acompanhamento do 2º turno nas 27 UFs, com o comando do roteiro:

```
vigiar_site.py --porta 8001 -- site_apuracao.py --ambiente oficial --turno 2 --ufs todas --coletar ...
```

E corrigir o que impedisse a coleta durante a noite.

## Contexto

- **Subida às 19h07,** duas horas depois do início da divulgação.
- **Prontidão rápida** (`verificar_prontidao.py --turno 2 --ufs todas`): 0 falhas, 1 aviso.
- **O aviso: o RJ dava 404 no acompanhamento de Governador.**
  - O acompanhamento nacional do próprio TSE (`br-e006260-ab.json`) lista só AC, AM, DF, ES, RN e TO.
  - O RJ teve 2º turno estadual (Douglas Ruas × Eduardo Paes no 1º turno), mas não está na divulgação da eleição
    6260. O problema não é do coletor.
- **Cópia de segurança** em `/mnt/c/apuracao_copias/t2`.
  - No WSL, `/mnt/d`, `/mnt/e`, `/mnt/g` e `/mnt/z` não estão montados: são pastas do mesmo disco dos dados. Só o
    `C:` é outro disco (30 GB livres).
  - A cópia do 1º turno, só RJ, ocupou 255 MB.

## Entregas

### 1. Vigia: sonda do site de várias UFs (`apuracao/vigia_site.py`)

- **Bug.** `sondar_http` pedia `/api/status`. No site de várias UFs (`--ufs`), a raiz não tem essa rota: ela fica em
  `/<uf>/api/status` e a raiz responde 404. O vigia entendia isso como "sem resposta".
  - Às 19:10:17 aconteceu o reinício nº 1, depois de 90 s de tolerância e 3 sondas.
  - Sem a correção, o site e o coletor seriam reiniciados a cada ~2,5 min a noite toda.
- **Correção.** Se `/api/status` dá 404, a sonda vale por `/ufs.json`, rota que só o site de várias UFs tem.
  - Um 500 no site de uma UF continua contando como falha: o `/ufs.json` só é pedido depois de um 404.

### 2. Cliente: conexões fechadas a cada ciclo (`apuracao/divulgacao/cliente.py`)

- **Bug.**
  - Das 19:18 às 19:22 nenhum ciclo terminou: 7 "Read timed out" (30 s) seguidos, nenhuma UF atualizada.
  - Ao mesmo tempo, pedidos novos ao TSE (curl e `requests`, com e sem o User-Agent do coletor) respondiam em
    0,2 s.
  - O processo tinha 90 conexões TCP "estabelecidas" com os servidores do TSE (Akamai), todas com as filas vazias.
- **Causa.**
  - Cada UF tem um `ClienteDivulgacao` com a própria `requests.Session`, e com 27 UFs a mesma sessão fica ~7 min
    parada entre um uso e outro.
  - A NAT do WSL2 derruba conexão ociosa sem avisar: o pedido seguinte vai por uma conexão morta e só cai no
    tempo-limite.
  - Como `executar(max_ciclos=1)` encerra o ciclo da UF no 1º erro, cada UF perdia 30 s e não coletava nada.
  - No 1º turno (só RJ, ciclo de 60 s) a conexão nunca ficava ociosa tanto tempo.
- **Correção.**
  - `novo_ciclo()` agora chama `sessao.close()`, ao custo de um handshake TLS por UF a cada ciclo.
  - Depois do `close()` a `requests.Session` continua usável: os pools são recriados sob demanda (conferido contra o
    TSE).
  - `close()` só é chamado quando existe: `FakeTSE` e `SessaoEnsaio` não o têm.

### 3. `--so-presidente` (`coletor.py`, `site_apuracao.py`, `coletar_resultados.py`)

- **Problema.**
  - No 2º turno, o coletor de cada UF pedia a eleição estadual sempre que ela existia no `ele-c.json`.
  - A eleição 6260 é uma só para o país, então as 20 UFs sem 2º turno estadual, mais o RJ, recebiam 404 no
    acompanhamento a cada volta: 287 404 até 20h05.
  - A rodada 43 registra que 404 repetido pode bloquear o IP. Não houve bloqueio.
- **Escolha do usuário.** Das duas opções propostas (só Presidente, ou Governador só nas UFs que o TSE divulga), o
  usuário ficou com a primeira.
- **Entrega.**
  - Opção `so_presidente` no `Coletor`: `preparar` não registra a eleição estadual.
  - A lista de municípios (EA12) passa a vir da eleição federal. Antes, nas UFs sem 2º turno estadual, ela ficava
    vazia (AL: 0 → 102; SP: 0 → 645).
  - Flag `--so-presidente` no `site_apuracao.py` (uma UF e várias) e no `coletar_resultados.py`.
- **Efeito no site.**
  - O `ultimo/` é regravado da memória do processo a cada ciclo, então depois do reinício o Governador sai do site
    nas 6 UFs que o tinham. Não fica número congelado.
  - O que já tinha sido coletado do Governador fica em `raw/`, nas séries e no `historico_totais.parquet`.

### 4. Brasil parado em 30%: a marca da totalização inclui as seções (`coletor.py`)

- **Bug.**
  - Às 21h o painel do Brasil seguia em 30,2% de seções, enquanto o TSE já passava de 99%.
  - O EA14 nacional traz para o Brasil a MESMA hora de totalização a noite toda, e no futuro ("26/10/2026 09:05:23").
  - O coletor só pedia o EA20 de uma abrangência quando o `DT_TOTALIZACAO` mudava; no Brasil, ele nunca mudou.
- **Correção.** A marca da última totalização confirmada (`_ultima_totalizacao`) passou a ser a tupla (dt/ht,
  seções totalizadas, andamento). Seções novas com a mesma hora = totalização nova.
  - A marca só é gravada em `_confirmar`, depois que os arquivos chegam (`_marca_vista` guarda a do EA15/EA14 até lá).
- **No ar** às 21:22 (site reiniciado pelo vigia); o Brasil voltou a avançar no ciclo seguinte.

### 5. Versão final do Brasil não percebida: andamento e geração do EA14 (`coletor.py`)

- **Bug.** Com 100% das seções, a hora fixa e o mesmo nº de seções, a versão final (`and="f"`, situação "Eleito")
  não mudava a marca: o Brasil ficou na última parcial.
- **Correção.**
  - O `ANDAMENTO` já entra na marca (entrega 4).
  - No Brasil entra também a geração do EA14 (`_ab_gerado`): o arquivo regerado com qualquer mudança faz o EA20
    nacional ser pedido de novo. O EA20 continua sujeito à regra de `dg`/`hg` ≥ hora anunciada (`_limitar`).
  - Nas UFs e municípios a geração do acompanhamento NÃO entra: mudaria a cada ciclo e pediria todos os EA20.
- **No ar** às 23:32; o Brasil final apareceu com Lula eleito.

## Números reais

- **Linha do tempo (horário de Brasília):**

  | Hora | Fato |
  |---|---|
  | 19:07 | 1ª subida |
  | 19:10 | reinício falso do vigia (correção 1) |
  | 19:11 | vigia corrigido no ar |
  | 19:18 → 19:22 | sem coleta (correção 2) |
  | 19:22 | site reiniciado com o cliente corrigido |
  | 20:05 | subida com `--so-presidente` (correção 3) |
  | 21:22 | marca com as seções (correção 4) |
  | 23:26 | TSE anuncia RR final no EA15 (o EA20 de RR nunca foi regerado na noite) |
  | 23:32 | marca com andamento e geração do EA14 no Brasil (correção 5) |

- **De 20:05 até 21:05:** 0 timeouts, 0 404, 0 bloqueios, 0 reinícios.
- **Uma volta pelas 27 UFs** leva ~4¾ min: um ciclo por UF, 2 a 11 s cada, mais o intervalo de 60 s.
- **Uma única falha de rede depois da correção 2,** às 19:52 (`TLSV1_ALERT_INTERNAL_ERROR` num arquivo de AL): erro
  do lado do TSE, e o ciclo seguinte terminou normalmente.
- **Parcial às 20h53:**

  | Abrangência | Seções apuradas | Flávio Bolsonaro | Lula |
  |---|---|---|---|
  | Brasil | 30,2% | 50,47% (18.823.884) | 49,53% (18.476.333) |
  | RJ | 31,9% | 53,2% | 46,8% |

- **Resultado final no Brasil:** Lula 64.256.232 votos (51,79%), eleito; Flávio Bolsonaro 59.826.041 (48,21%).
  Eleitorado 158.745.502, comparecimento 128.236.074, abstenção 19,22%, brancos 1,12%, nulos 2,12%. Lula venceu em
  11 UFs e Flávio em 14 (até o fim da noite).
- **Fim da noite:** Brasil e 26 UFs com totalização final, boletim final e instantâneo "final" da cópia.
  - **RR:** o EA15 anuncia a UF final às 23:26:38, mas o TSE continuou servindo o EA20 gerado às 22:45:56 com
    `tf=n` (conferido até ~00:09). O coletor desistiu às 23:54, depois de `TENTATIVAS_ANTIGO` (15) ciclos. Os votos
    estão completos (100% das seções); falta só a marca de final, e com ela o boletim e a cópia final de RR.

## Arquivos

| Arquivo | Mudança |
|---|---|
| `apuracao/vigia_site.py` | `sondar_http` com `/ufs.json` quando `/api/status` dá 404 |
| `apuracao/divulgacao/cliente.py` | `novo_ciclo()` fecha as conexões da sessão |
| `apuracao/divulgacao/coletor.py` | `Coletor(..., so_presidente=False)`; marca da totalização = (dt/ht, seções, andamento[, geração do EA14 no Brasil]) |
| `site_apuracao.py`, `coletar_resultados.py` | `--so-presidente` |
| `test_copia_vigia.py` | `test_sonda_aceita_o_site_de_varias_ufs` |
| `test_divulgacao.py` | `test_novo_ciclo_fecha_as_conexoes_guardadas`, `test_so_presidente_nao_pede_a_eleicao_estadual`, `test_brasil_com_a_mesma_hora_no_futuro_e_pedido_quando_as_secoes_avancam` |
| `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `CLAUDE.md`, `docs/INDEX.md` | registro |

## Verificação

- **Testes:** `pytest -q test_divulgacao.py test_copia_vigia.py test_alertas.py test_lote_ufs.py test_enderecos.py -m
  "not e2e"` → 69 passaram.
- **No ar, com o site oficial:**
  - **Correção 1:** vigia "no ar", sem nenhuma sonda falha desde 19:11.
  - **Correção 2:** duas voltas completas depois da ociosidade, sem timeout.
  - **Correção 3:** a primeira volta com `--so-presidente` mostra `eleições {6258: (1,)}` nas 27 UFs, com 0 404 e só
    o cargo 1 no `ultimo/totais.parquet`.
  - **Correções 4 e 5:** o Brasil passou de 30,2% para 100% e chegou à versão final.
- **Correções 4 e 5 (testes):** `pytest -q test_divulgacao.py test_copia_vigia.py test_alertas.py test_lote_ufs.py
  test_boletim.py test_comparacao.py` → 97 passaram. O teste novo falha sem a correção: muda as seções e o andamento
  da linha br do EA14 com a mesma hora (1 pedido a mais cada) e depois só a geração (mais 1).

## Decisões

- **Fechar a sessão no início do ciclo,** em vez de tentar de novo depois do timeout. Uma retentativa ainda perderia
  30 s por UF. TCP keepalive dependeria do kernel e da NAT.
- **Sem `--so-presidente` não muda nada:** o padrão continua coletando o Governador.

## Pendências

- **Governador só nas UFs que o TSE divulga** (a opção 2, não escolhida): ler a lista de UFs do acompanhamento
  nacional da eleição estadual (EA14) e pedir o Governador só nelas, de novo a cada N ciclos para pegar UF que entre
  depois. Evitaria os 404 sem perder o Governador.
- **`verificar_prontidao.py` não testa o vigia contra o site de várias UFs,** e o ensaio roda com uma UF. Um ensaio
  com `--ufs` e sessões ociosas teria pegado as correções 1 e 2 antes da noite.
- **Saber por que o RJ ficou fora da divulgação do Governador** no TSE.
- **RR sem a versão final:** o coletor só volta a pedir quando a marca de RR mudar no EA15. Se o TSE regerar só o
  EA20, é preciso reiniciar o site (a memória das tentativas é do processo).
- **O ensaio não simula a hora fixa no futuro do EA14 nacional** (correções 4 e 5).
