# Roteiro da noite da eleição — 1º turno, 4/10/2026 (e 2º turno, 25/10)

Comandos na raiz do projeto, com `source venv/bin/activate`. O horário é o de Brasília. A divulgação começa às 17h.

## Resumo em uma tela

| Quando | O quê | Comando |
|---|---|---|
| até 2/10 | ensaio geral com a apuração de 2022 | `python ensaio_apuracao.py` (cerca de 15 min; deve terminar em "RESULTADO DO ENSAIO: OK") |
| até 3/10 | malhas e Censo 2022 do IBGE no cache (rodada 34; baixa algumas centenas de MB uma vez) | `python preparar_ibge.py` |
| 3/10, fim do dia | prontidão, e o oficial publica a configuração | `python verificar_prontidao.py` |
| 3/10, depois que o oficial publicar | um ciclo de teste no oficial, num diretório descartável | `python coletar_resultados.py --ambiente oficial --uma-vez --destino dados_2026/oficial_teste` e depois `rm -r dados_2026/oficial_teste` |
| 4/10, 16h | prontidão completa, com os testes | `python verificar_prontidao.py --testes` |
| 4/10, 16h30 | encerrar os sites de teste (portas 8000, 8022, 8023, 8040) | Ctrl+C nos terminais, ou `kill` nos PIDs de `ps -eo pid,args \| grep site_apuracao` |
| 4/10, 16h45 | **subir coleta e site, sob o vigia** (rodada 33) | `python vigiar_site.py -- python site_apuracao.py --ambiente oficial --coletar --abrir --copia-dir <pasta em OUTRO disco>/oficial` (ex.: `/mnt/d/apuracao_copias/oficial`) |
| 4/10, 17h em diante | acompanhar no navegador | http://localhost:8000 |
| 4/10, junto com o site | portal com os links de todos os sites no ar (opcional; mostra também quedas e reinícios do vigia) | `python portal.py` → http://localhost:8100 |
| 4/10, na TV da sala | painel em tela cheia, um cargo por vez | http://localhost:8000/#painel?tv=1 (ou botão "Modo TV" no painel; clique uma vez na página para a tela cheia) |
| 4/10, a cada hora cheia e no fim | mandar o boletim para a equipe | `dados_2026/oficial/boletins/boletim_ultimo.html` e `.xlsx` (gravados sozinhos) |
| ao fim | conferir a cópia final automática e fazer o `tar` de sempre | `ls <copia-dir>/instantaneos/final` e `tar czf oficial_4out.tgz dados_2026/oficial` |

- **2º turno:** o mesmo roteiro com `--turno 2`. Os dados vão para `dados_2026/oficial_t2` e não se misturam com os do 1º turno. A comparação usa `dados_2026/historico_2022_t2`.
  - **Transferência de votos 1º → 2º turno** (rodada 30): no site do 2º turno, a aba "1º → 2º turno" já abre no **tempo real** (municípios, com os dados do 1º turno em `dados_2026/oficial`). É leitura **frágil** (92 unidades; em 2022 o destino dos eliminados por município diferiu até 22 p.p. do estimado por seção) e a página avisa. A estimativa boa (seção ou local) vem com os microdados do 2º turno: com o ZIP no cache, `python transferencia_turnos.py --ano 2026 --cargo governador --nivel secao --saida saidas/transferencia_2026.xlsx` ou a mesma aba com fonte "Microdados".

## Antes da noite

1. **Ensaio geral** (`ensaio_apuracao.py`). Toca a apuração real de 2022 do RJ, seção a seção pela hora em que cada uma entrou, acelerada 30 vezes.
   - **O que roda:** o coletor de verdade (com o limite de 20 req/s), o site de verdade e 6 usuários consultando ao mesmo tempo.
   - **O que confere no fim:**
     - os válidos de cada cargo contra o oficial;
     - 100% apurado;
     - Castro eleito;
     - as cadeiras (46/46 e 70/70).
   - **Onde fica o relatório:** `dados_2026/ensaio_2022/relatorio_ensaio.json`.
   - **Opções:** `--velocidade 120` para um ensaio curto; `--inicio 19:30` para começar no meio da noite; `--manter` para deixar o site no ar ao fim.
2. **Prontidão** (`verificar_prontidao.py`). Checa dependências, disco, cache (malhas, Censo 2022, última verificação do IBGE, 2022 importado), a hora do computador contra a do TSE, os ambientes simulado e oficial, a porta 8000 e o diretório `dados_2026/oficial`. Deve terminar em "PRONTO".
   - **Oficial com 404 na configuração:** antes de 3/10 é o esperado e sai como AVISO.
   - **Dados de outro ambiente em `dados_2026/oficial`:** é FALHA. Apague o diretório.
3. **Códigos das eleições:** o coletor lê do `ele-c.json`, nunca do código. Se o oficial vier com códigos diferentes de 6257/6259 (Anexo I), nada precisa mudar; a prontidão só avisa.

## Na noite

- **Subir tudo:** um único comando sobe coleta e site: `python site_apuracao.py --ambiente oficial --coletar --abrir`.
  - O coletor faz um ciclo a cada 60 s (`--intervalo`). No 1º ciclo baixa cerca de 470 arquivos, em uns 25 s com o limite de 20 req/s; depois baixa só o que mudou.
  - O topo do site mostra a hora da última coleta e qualquer erro do coletor.
  - Um arquivo que falhar (rede, erro 5xx, página HTML no lugar do JSON) é pedido de novo no ciclo seguinte; o `status.json` conta esses casos em `arquivos_com_falha`. Um erro inesperado não para mais a coleta: vai para o log e o ciclo seguinte roda normalmente.
- **Alertas** (rodada 29): o site verifica a cada 15 s e avisa na própria página (faixa no topo, aviso no canto, som e "⚠" no título da aba) e no terminal (linha `ALERTA [...]` e campainha).
  - **Crítico** (faixa vermelha, 4 bipes):
    - coleta parada há mais de 10 min (3 intervalos, se o intervalo for maior);
    - TSE bloqueou o acesso (403/429): **não reinicie nem rode outro coletor**, a pausa de 11 min é automática;
    - coletor encerrado por erro: reinicie o site.
  - **Atenção** (faixa amarela, 2 bipes):
    - divulgação do TSE indisponível;
    - falha de rede que dura mais de 2,5 min;
    - erro inesperado no coletor;
    - apuração sem nova totalização do TSE no RJ há 20 min, com seções faltando: confira no site do TSE se a divulgação parou para todos.
  - **Novidade** (1 bipe):
    - a leitura da projeção mudou (Governador, Senador, Presidente no RJ; ex.: "indefinido" → "vitória no 1º turno projetada");
    - um deputado acompanhado mudou de situação (em disputa → consolidado, saiu da disputa, eleito/não eleito no fim).
  - **Deputados acompanhados:** botão "Acompanhar nos alertas" na aba Candidato, ou `--interesse 7:13713 6:1234` ao subir o site. A situação só existe a partir de 30% apurado (projeção das cadeiras).
  - **Som:** o navegador só toca depois de um clique na página; clique uma vez ao abrir. A caixa "som" no topo liga/desliga.
  - **Histórico:** botão "Alertas" no topo. Fica em `dados_2026/oficial/alertas.json` (reiniciar não repete nem perde alertas).
  - **Coleta e site em processos separados:** os alertas rodam no processo do site, que lê o `status.json` do coletor; "coletor encerrado" só existe com `--coletar`.
  - `--sem-alertas` desliga.
- **Destacar partidos/federações** (rodada 31): no painel, caixa "Destacar partidos/federações" acima dos cartões; os deputados desses partidos saem com ★ e fundo nas listas de eleitos projetados, no boletim e na planilha. Para já subir com o destaque (e o boletim sair com ele): `--destacar PL "PT/PC do B/PV"` no `site_apuracao.py`. Cada lista tem o botão "Salvar lista (.xlsx)".
- **Boletim para a equipe** (rodada 28): com `--coletar`, o site grava sozinho em `dados_2026/oficial/boletins/`:
  - `boletim_2026-10-04_19h00.html` e `.xlsx` a cada hora cheia, enquanto a apuração anda, e `boletim_final.*` quando todos os cargos têm totalização final;
  - `boletim_ultimo.html`/`.xlsx`: cópia do mais recente, para mandar sem procurar;
  - o HTML é um arquivo só, abre em qualquer navegador e celular sem internet; a planilha tem uma aba por cargo, as cadeiras, os eleitos e os municípios;
  - os números são os mesmos do site na hora da geração (as mesmas funções das rotas);
  - **boletim fora de hora:** `python gerar_boletim.py --ambiente oficial` (grava `boletim_<data>_<hora>` na mesma pasta);
  - **coleta e site em processos separados:** sem `--coletar` o site não grava boletins; rode `python gerar_boletim.py --ambiente oficial --vigiar` num terceiro terminal;
  - outro intervalo: `--boletim-min 30` no site; desligar: `--sem-boletim`.
- **Se o site ficar lento com muita gente consultando:** rode coleta e site em processos separados, cada um num terminal:

  ```bash
  python coletar_resultados.py --ambiente oficial          # terminal 1: só a coleta
  python site_apuracao.py --ambiente oficial               # terminal 2: só o site (lê os mesmos dados)
  ```

- **O que o painel mostra e como ler:**
  - **Projeção do resultado final** (Presidente no RJ, Governador, Senador): mostra o parcial e a projeção, com margem.
    - Abaixo de 2% apurado a leitura diz "cedo demais".
    - No RJ, até ~50% apurado, o parcial foi tão bom quanto a projeção, ou melhor (rodada 21).
  - **Cadeiras de deputado:**
    - antes de 30% apurado: distribuição sobre os votos parciais;
    - a partir de 30%: cadeiras projetadas, com faixa por partido, e eleitos consolidados × em disputa (rodada 22);
    - no fim: "confere com o TSE: N de N eleitos".

- **Ver o site de outro computador:** não é recomendado. O site não tem senha nem HTTPS.
  - Com `--host 0.0.0.0`, qualquer máquina que alcance esta vê painel, mapas e candidatos (dados públicos do TSE).
  - Planilha, mapa e comparação por bairro, Perfil × voto e exportação de mapa respondem 403 para quem não está neste computador. Essas rotas baixam centenas de MB e disputariam a máquina com o coletor.
  - No WSL2, `0.0.0.0` nem chega à rede local sem configuração extra do Windows (redirecionamento de porta).
  - Para a equipe, mande o boletim (`boletins/boletim_ultimo.html`), que não exige abrir o site na rede.

## Se algo der errado

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "divulgação ainda não disponível" (404 ou página HTML do TSE) | o TSE ainda não abriu os arquivos | nada: o coletor tenta de novo a cada ciclo |
| erro "HTTP 403/429 … limite de acesso do TSE" | bloqueio por excesso de acessos do IP (10 min) | o coletor **pausa sozinho 11 min**. Não reinicie em laço: cada tentativa reinicia o bloqueio. Confira se outra máquina da mesma rede está consultando o TSE |
| o processo caiu ou foi fechado | erro, queda de energia, Ctrl+C | com o **vigia** (`vigiar_site.py`), ele sobe de novo sozinho em até ~1,5 min (veja `dados_2026/vigia/porta_8000.log` e o portal). Sem o vigia: rode **o mesmo comando** de novo. Os dados em `dados_2026/oficial` continuam, e o coletor refaz o 1º ciclo e segue. **Não apague o diretório** |
| o site não responde (página não carrega), mas o processo está lá | travamento | o vigia reinicia depois de 3 verificações sem resposta (~1,5 min). Sem o vigia: Ctrl+C e o mesmo comando |
| disco cheio ou `dados_2026/oficial` danificado | disco, arquivo corrompido | pare o site; restaure a última cópia: `cp -r <copia-dir>/instantaneos/<hora mais recente>/. dados_2026/oficial/` e `cp -rn <copia-dir>/raw/. dados_2026/oficial/raw/`; suba de novo (o coletor completa o que faltar) |
| a série do painel ou a linha do tempo sumiram | arquivo de série corrompido | com o site parado, apague `dados_2026/oficial/historico_serie.parquet` (ou `historico_candidatos/`) e suba de novo: o coletor reconstrói a partir dos JSON brutos em `raw/` |
| sem internet | rede | o coletor anota o erro e tenta de novo no ciclo seguinte; os dados voltam a fluir sozinhos |
| números diferentes do app Resultados do TSE | coleta atrasada (o painel mostra a hora da totalização) | espere o próximo ciclo. Se continuar, compare a hora da totalização no topo do cartão |
| a porta 8000 está ocupada | outro site esquecido no ar | encerre-o (`verificar_prontidao.py` mostra qual), ou use `--porta 8001` |
| aviso "os votos das agremiações não somam os válidos" | JSON incompleto do TSE (raro) | a projeção de cadeiras pode estar incompleta; espere o próximo ciclo |

## Depois

- **Analisar a evolução da apuração (todas as parciais do TSE):**
  - `dados_2026/oficial/raw/<eleição>/<arquivo>/*.json.gz`: cada versão distinta de cada JSON que o TSE publicou e o coletor baixou (o nome traz a hora de geração do TSE). A cópia fica também em `<copia-dir>/raw/`.
  - `historico_totais.parquet`: os totais (seções, comparecimento, válidos…) de cada versão, por UF e município.
  - `historico_candidatos/`: os votos de cada candidato em cada versão.
  - Se preciso, `apuracao.divulgacao.serie.reconstruir(pasta)` e `reconstruir_candidatos(pasta)` refazem as séries a partir de `raw/`.
  - Limite: o coletor pede cada arquivo uma vez por ciclo (60 s); se o TSE publicar duas versões dentro do mesmo minuto, só a última é guardada.

- **Cópia de segurança:** `tar czf oficial_4out.tgz dados_2026/oficial`. Os JSON brutos em `raw/` são o histórico da apuração, que o TSE sobrescreve.
- **Microdados de 2026:** saem dias depois. Deixe rodando `python preparar_2026.py --vigiar`, que verifica a cada hora com um HEAD por arquivo.
  - Quando os votos por seção chegam, ele converte e importa o resultado oficial para `dados_2026/historico_2026_t1`.
  - Também grava `saidas/transferencia_2022_2026.csv`.
  - Mapas por bairro e por local de votação, comparação e Perfil × voto passam a oferecer 2026 sozinhos.
  - Se o TSE atualizar um arquivo, ele baixa de novo. Nesse caso reinicie o site para ele reler os dados.
- **Dados do IBGE** (rodada 34): `python preparar_ibge.py --so-verificar` mostra se o IBGE publicou uma versão nova das malhas ou dos agregados do Censo 2022 (ele põe a data no nome do arquivo). `python preparar_ibge.py` baixa, refaz os derivados e, se a versão nova não converter, volta à anterior. Depois, reinicie o site. `preparar_2026.py` já garante o IBGE no cache quando os votos por seção chegam.
- **Recalibrar as margens** da projeção e das cadeiras com 2026, seguindo `docs/RECALIBRAR_MARGENS.md`. Primeiro valide 2026 com as margens de 2022 (o teste fora da amostra) e depois junte os dois anos.
