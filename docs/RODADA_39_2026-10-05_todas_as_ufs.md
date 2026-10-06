# Rodada 39 — Todas as UFs: download automatizado e site com seletor de UF

05/10/2026 · pedido do usuário: "Quero baixar os dados de todos os estados, não somente do RJ. Como
automatizar? Através de um script bash?"

Escolhas do usuário:
- **Dados:** os quatro conjuntos (resultado 2026 da divulgação, histórico, eleitorado e IBGE, microdados de
  2026 quando saírem).
- **Site:** **um site com seletor de UF**.

## Resposta curta: por que Python e não bash

Um laço bash com `--uf` funcionaria para os passos simples, mas não resolve três pontos:
- **Limite do TSE:** processos paralelos somariam 20 acessos/s cada no mesmo IP, e o TSE bloqueia.
- **Retomada:** é preciso saber, depois de uma queda, quais UFs e etapas já terminaram.
- **Pastas:** cada UF precisa da sua, sem misturar com as do RJ.

O orquestrador `baixar_ufs.py` resolve os três. O bash fica para rodá-lo em segundo plano:

    nohup python baixar_ufs.py --etapas divulgacao historico > lote_ufs.log 2>&1 &

## Entregas

### Pastas por UF (`apuracao/ufs.py`)
- **Convenção:** `dados_2026/<base>_<UF>` (`oficial_SP`, `historico_2022_t1_SP`…).
- **`dir_uf(base, uf)`:** para o RJ, aceita a pasta antiga sem sufixo se o `status.json` dela disser RJ (nada
  foi movido). Para as outras UFs, nunca devolve a pasta do RJ.
- **Usado no destino padrão** de `coletar_resultados.py`, `site_apuracao.py`, `gerar_boletim.py`,
  `importar_resultado_historico.py` e `preparar_2026.py`.
- **Defeito latente corrigido:** o `preparar_2026.py --uf SP` gravaria o histórico de 2026 de SP por cima do
  do RJ.

### Orquestrador (`apuracao/lote_ufs.py` + `baixar_ufs.py`)
- **Etapas:**
  - `divulgacao`: o mesmo `Coletor` da noite, até 3 ciclos por UF até a totalização final;
  - `historico`;
  - `eleitorado` (cadastro e perfil);
  - `ibge` (`ibge.preparar`);
  - `microdados` (`microdados.preparar`): "aguardando" até o TSE publicar; `--vigiar` repete a cada hora.
- **Estado** em `dados_2026/lote_ufs.json`, por UF × etapa: ok, erro, aguardando, incompleto, não se aplica ou
  pendente, com detalhe e duração. Rodar de novo retoma; `--refazer` refaz tudo.
- **Uma UF com erro não para as outras.**
- **Limite do TSE:** UM `LimitadorTaxa` para todas as UFs (`--max-rps`, padrão 10/s). Um bloqueio do TSE
  suspende só a divulgação; as outras etapas usam a CDN.
- **`--so-plano`:** mostra o que falta, sem acessar nada.

### Histórico de qualquer UF pela fonte munzona (`apuracao/historico.py`)
- **Sem fonte munzona**, importar o histórico das 27 UFs exigiria o `votacao_secao_<ano>_<UF>` de cada uma
  (vários GB por ano).
- **Com a fonte munzona**, os arquivos nacionais `votacao_{candidato,partido}_munzona_<ano>`, já no cache,
  servem a todas as UFs.
  - O CSV `_BRASIL` de cada ano é convertido UMA vez para Parquet: 10 s em 2022, 140 s em 2018, 32 s em
    2014.
  - Cada UF só filtra o Parquet: AC e RR levaram 0,2–0,3 s.
- **Padrão:** a fonte é "secao" se o ZIP da UF já estiver no cache (o RJ continua igual); senão, "munzona".
  A pasta grava qual fonte foi usada (`status.json["fontes"]`).
- **Equivalência conferida no RJ real**, fonte "secao" × "munzona":

| Ano | Candidatos nas duas fontes | Votos diferentes | Eleitos iguais | Só na fonte "secao" |
|---|---|---|---|---|
| 2022 (1º turno) | 107.225 | 0 | sim | 2.037 linhas: candidatos INAPTOS (votos anulados), ex.: Daniel Silveira, senador, 1,57 milhão |
| 2022 (2º turno) | 188 | 0 | sim | — |
| 2018 | 120.977 | 0 | sim | 186 inaptos + 2 "Válido" na UF (465 mil votos, quase todos anulados) |
| 2014 | 85.782 | 0 | sim | 216 inaptos + 4 "Válido" na UF (310 mil votos) |

  Totais, válidos e percentuais são idênticos, porque os votos anulados não entram nos válidos. O arquivo
  por município não lista candidato com candidatura inapta, e às vezes nem o partido dele. Tentei atribuir
  os nominais anulados do arquivo de partidos ao candidato majoritário, mas o PTB do Daniel Silveira nem
  aparece no arquivo de senador, então desisti da recuperação.
- **DF:** `CARGOS_UF` ganhou o 8 (deputado distrital), que faltava no histórico.

### Site com seletor de UF (`apuracao/web/multi.py` + `site_apuracao.py --ufs`)
- **Montagem:** o `create_app` de cada UF em `/<uf>/`. A página já usava só caminhos relativos (`api/…`,
  `geo/…`), então funciona montada sem nenhuma mudança.
- **Rotas da raiz:** `/` vai para a UF padrão; `/ufs.json` lista as UFs (nome, % das seções, disponível ou
  não).
- **Seletor no cabeçalho** (`iniciarSeletorUf`): escondido no site de uma UF, onde `/ufs.json` não existe.
  Trocar de UF mantém a aba e o endereço (`#…`). UF sem dados aparece desabilitada.
- **Defeito de segurança evitado:** as regras por rota (`ROTAS_SO_LOCAL`, cabeçalho sem cache) comparavam
  `request.url.path`. Montado em `/rj`, o caminho vira `/rj/api/planilha`, e a rota pesada ficaria liberada
  para a rede. Agora se usa `caminho_no_app(request)`, sem o prefixo da montagem, e um teste cobre isso.
- **`--ufs --coletar`:** um coletor percorre as UFs com um limitador só. Boletim, cópia e alertas continuam
  só no site de uma UF.

## Primeira execução real (27 UFs, divulgação 2026 + histórico 2022)

`python baixar_ufs.py --etapas divulgacao historico`, com `--max-rps 10`:
- **Resultado:** **54 tarefas, 54 "ok"** (27 UFs × divulgação e histórico).
- **Divulgação:** **27.551 arquivos** do TSE (oficial) em **48 min 49 s** de relógio. Ficou em ~9,4 acessos/s,
  dentro do limite único, e cada UF fechou em 1 ciclo.
- **Exemplos de duração:**
  - MG: 4.271 arquivos, 7,7 min;
  - SP: 3.231 arquivos, 6 min;
  - RS: 2.491 arquivos, 4,4 min;
  - DF: 11 arquivos, 2 s (com o cargo 8, distrital).
- **Histórico 2022 pela fonte munzona:** 0,2–0,5 s por UF, porque os Parquet nacionais já estavam convertidos.
  MG tem 853 municípios e 381.609 linhas de candidatos.
- **Recursos:** pico de memória de 3,1 GB; `dados_2026/` ficou com 531 MB.
- **Conferência com resultados conhecidos de 2022:** SP (Tarcísio 42,32% × Haddad 35,70%, 2º turno), MG (Zema
  eleito no 1º turno), RS (Onyx × Leite, 2º turno) e BA (Jerônimo × ACM Neto, 2º turno).
- **Defeito encontrado e corrigido:** o histórico do DF veio com 0 municípios.
  - **Causa:** o cache `municipios_tse_ibge.parquet` (5.569 municípios, 26 UFs) tinha sido gerado do EA12 de
    uma eleição municipal, que não inclui o DF. Isso foi antes da correção da rodada 36, que passou a usar o
    ciclo mais recente do `ele-c.json`.
  - **Correção:** `municipios_tse_ibge` refaz o cache uma vez quando a UF pedida não está nele. O cache passou
    a ter 27 UFs, e o DF, Brasília (IBGE 5300108).

## Verificação
- **Testes:** `pytest -q` com 345 passaram e 4 pulados.
  - `test_ufs.py`: `dir_uf`, pasta antiga e lista;
  - `test_lote_ufs.py`: retomada sem acessos, falha numa UF, limitador único, bloqueio e `--so-plano`;
  - `test_historico.py`: munzona = seção sobre ZIPs sintéticos, nos 2 turnos, com a suplementar ignorada; cache
    de municípios sem a UF é refeito;
  - `test_site.py`: rotas multi-UF, regra pesada sob o prefixo e no-cache;
  - `test_enderecos.py`: e2e do seletor.
- **Navegador:** RJ → AC pelo seletor, mantendo `#mapas?cargo=3&metrica=vencedor`; o mapa do AC desenhado
  certo.

## Pendências
- **Etapas pesadas:** eleitorado, IBGE e microdados para as 27 UFs não rodaram nesta rodada.
  - O perfil do eleitorado é ~1 GB nas 27 UFs.
  - Os microdados de 2026 aguardam o TSE.
- **TODO 18 (atualizado):** ensaio, prontidão e calibração por UF; boletim e alertas no site de várias UFs;
  montar uma UF nova sem reiniciar.
