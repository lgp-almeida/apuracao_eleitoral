# Roteiro da noite da eleição — 2º turno, 25/10/2026 (e o 1º turno, 4/10)

Comandos na raiz do projeto, com `source venv/bin/activate`. O horário é o de Brasília. A divulgação começa às 17h.

## 2º turno — 25/10/2026

**O que haverá:** Presidente em todas as UFs e Governador em **AC, AM, DF, ES, RJ, RN e TO** (lido do resultado
oficial do 1º turno pela prontidão).

**Já verificado em 07/10:**
- **Prontidão** (`verificar_prontidao.py --turno 2 --ufs todas --testes`): 0 falhas.
  - Códigos do 2º turno já no `ele-c.json` oficial: Governador 6260, Presidente 6258.
  - Acompanhamento ainda em 404, o normal antes da tarde de 25/10.
  - Referência de 2022 e 1º turno de 2026 presentes em todas as UFs.
- **Ensaio** (`ensaio_apuracao.py --uf ES --turno 2`): OK. Votos válidos iguais ao oficial, 100% e final,
  Casagrande eleito, cópia e boletim finais.
  - O ensaio só passou depois de corrigir o TSE simulado dele (o EA20 era carimbado com a hora exata).
- **Simulado do TSE:** saiu do ar depois do 1º turno. A prontidão lê a hora do oficial.

| Quando | O quê | Comando |
|---|---|---|
| até 23/10 (opcional) | ensaio em outra UF que teve 2º turno de Governador em 2022 (AC, AM, RN ou TO) | `python ensaio_apuracao.py --uf AM --turno 2` (deve terminar em "RESULTADO DO ENSAIO: OK") |
| 24/10 | prontidão completa | `python verificar_prontidao.py --turno 2 --ufs todas --testes` |
| 25/10, 16h | prontidão de novo (sem os testes, é rápida) | `python verificar_prontidao.py --turno 2 --ufs todas` |
| 25/10, 16h30 | encerrar sites de teste e vigias de microdados que estejam no ar | Ctrl+C, ou `kill` nos PIDs de `ps -eo pid,args \| grep -E "site_apuracao\|preparar_2026\|baixar_ufs"` |
| 25/10, 16h45 | **subir o site de todas as UFs com coleta, sob o vigia** | `python vigiar_site.py --porta 8001 -- python site_apuracao.py --ambiente oficial --turno 2 --ufs todas --coletar --porta 8001 --copia-dir <pasta em OUTRO disco>/t2` |
| 25/10, 17h em diante | acompanhar (seletor de UF no cabeçalho) | http://localhost:8001 |
| 25/10, na TV | painel em tela cheia de uma UF | http://localhost:8001/rj/#painel?tv=1 |
| a cada hora cheia e no fim | boletim de cada UF para a equipe | `dados_2026/oficial_t2_<UF>/boletins/boletim_ultimo.html` e `.xlsx` |
| ao fim | conferir a cópia final e guardar tudo; **não apagar** `dados_2026/oficial_t2_*`. Não desligue o site logo depois do final: o TSE ainda publica (EA20 regerado, retotalização) e a cópia segue espelhando a cada 5 min e refaz o `final` (rodada 70). Espere uns 10 min ou faça uma cópia à mão: `python copiar_dados.py --dados dados_2026/oficial_t2_<UF> --destino <copia-dir>/t2/oficial_t2_<UF> --uf <UF>` | `ls <copia-dir>/t2/oficial_t2_RJ/instantaneos/final` e `tar czf oficial_t2_25out.tgz dados_2026/oficial_t2_*` |
| ao fim | análise das parciais da noite | `python analisar_coleta.py --dados dados_2026/oficial_t2_RJ --saida saidas/coleta_t2_RJ.xlsx --grafico saidas/coleta_t2_RJ.png` |
| logo depois | **ligar as vigias dos microdados** (ver "Depois → Microdados do 2º turno") | `python preparar_2026.py --vigiar` e `python baixar_ufs.py --etapas microdados --ufs todas --vigiar` |

- **Pastas:**
  - os dados de cada UF vão para `dados_2026/oficial_t2_<UF>`, inclusive o RJ;
  - a comparação usa `dados_2026/historico_2022_t2[_<UF>]`;
  - a cópia de cada UF fica em `<copia-dir>/oficial_t2_<UF>`.
- **Pastas que já existem:** 25 UFs já têm `oficial_t2_<UF>` com só o `status.json` e tabelas vazias, de um teste de
  06/10. Não atrapalham: o coletor continua delas. Não apague: são as pastas da noite.
- **Site antes da divulgação:** ele sobe mesmo sem nenhuma UF com dados (página "Aguardando"). Cada UF entra no
  seletor quando ganha dados, sem reiniciar. Boletim, cópia e alertas são de **cada** UF.
- **Só o RJ, num site de uma UF:** `python site_apuracao.py --ambiente oficial --turno 2 --coletar` (porta 8000).
  Não rode os dois ao mesmo tempo para a mesma UF: são dois coletores no mesmo TSE.
- **Projeção no 2º turno:** a leitura é "vitória projetada", nunca "no 1º turno"/"2º turno projetado". A margem é a
  do 2º turno (`MARGEM_PP_2T`), que erra mais no meio da apuração.
- **Transferência de votos 1º → 2º turno** (rodada 30): no site do 2º turno, a aba "1º → 2º turno" já abre no
  **tempo real**, por município, com o 1º turno de `dados_2026/oficial_<UF>`.
  - É leitura **frágil**, e a página avisa: em 2022 o destino dos eliminados por município diferiu até 22 p.p. do
    estimado por seção.
  - A estimativa boa (por seção ou local) vem com os microdados do 2º turno.

## 1º turno — 4/10/2026 (feito; como referência)

| Quando | O quê | Comando |
|---|---|---|
| até 2/10 | ensaio geral com a apuração de 2022 | `python ensaio_apuracao.py` (cerca de 15 min; deve terminar em "RESULTADO DO ENSAIO: OK") |
| até 3/10 | malhas e Censo 2022 do IBGE no cache | `python preparar_ibge.py` |
| 3/10 | prontidão e um ciclo de teste no oficial, num diretório descartável | `python verificar_prontidao.py`; `python coletar_resultados.py --ambiente oficial --uma-vez --destino dados_2026/oficial_teste` |
| 4/10, 16h | prontidão completa | `python verificar_prontidao.py --testes` |
| 4/10, 16h45 | coleta e site sob o vigia | `python vigiar_site.py -- python site_apuracao.py --ambiente oficial --coletar --abrir --copia-dir <outro disco>/oficial` |
| 4/10 | acompanhar, portal e TV | http://localhost:8000 · `python portal.py` (http://localhost:8100) · `#painel?tv=1` |
| ao fim | cópia e `tar` | `tar czf oficial_4out.tgz dados_2026/oficial` |

O que aprendemos com o 1º turno:
- as parciais da noite do RJ se perderam por terem sido apagadas (rodada 42);
- o TSE anunciava a totalização antes de regerar o resultado (rodada 36);
- os microdados saíram 2 a 3 dias depois (veja "Depois").

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
  - **O TSE anuncia antes de publicar** (rodada 36): o acompanhamento (EA15) diz que um município foi totalizado minutos antes de o resultado (EA20) ser regerado. O coletor só aceita o EA20 gerado depois da hora anunciada; se vier a versão anterior, pede de novo a cada ciclo (até 15), e o `status.json` conta em `arquivos_antigos`. **Não é preciso reiniciar o site para "destravar" a apuração** (em 4/10, os reinícios manuais faziam esse papel).
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
  - **Presidente por estado** (cartão "Presidente — BRASIL", rodada 35): mapa de quem lidera em cada UF (ou o % de um candidato) e tabela com % apurado, 1º, 2º e diferença. É o parcial oficial de cada UF: **não há projeção nacional**.
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
- **Microdados de 2026 — o que aconteceu no 1º turno:**
  - **Datas:**
    - votos por seção em 06/10, à 01h57 (a UF) e 16h22 (o `_BR`, regerado depois);
    - detalhe por seção em 06/10;
    - Boletim de Urna em 06/10, às 15h38;
    - **`votacao_partido_munzona` e `detalhe_votacao_munzona` só em 07/10, às 10h10 e 10h21**, regerados ainda às
      12h39.
  - **Totais:** o RJ e as outras UFs foram importados com os totais **provisórios** (das seções) em 06/10 e
    trocados pelos **oficiais** em 07/10, sozinhos. Conferência: votos iguais aos da noite e cadeiras iguais nas 27
    UFs.
  - **A CDN do TSE às vezes entrega a cópia velha** de um arquivo que o HEAD já anuncia como novo. O download
    compara as datas e pede de novo (rodada 54). Se aparecer "a CDN ainda entrega a versão de …", espere a próxima
    verificação.
  - **O TSE regera arquivos depois dos totais oficiais** (o partido munzona saiu às 10h10 e foi regerado às 12h39
    e às 16h39). Por isso as vigias passaram a ter o modo `--acompanhar` (rodada 59), que não para nos oficiais.
    - Cada importação guarda a versão de cada arquivo que usou (`insumos` no `status.json`). Se uma versão muda,
      ela é refeita, mesmo que o download tenha vindo de outra UF.
    - O log mostra o que mudou nos totais, e a conferência vai para
      `saidas/<UF>/conferencia_atualizacao_<data>_<t>t.csv`.

    ```bash
    python preparar_2026.py --acompanhar                                         # RJ
    python baixar_ufs.py --etapas microdados --ufs todas --acompanhar            # as outras UFs
    ```

    - Depois dos totais oficiais, verificam a cada 3 h (`--intervalo-final`). Param com Ctrl+C ou com
      `--ate AAAA-MM-DD`.
    - `python preparar_2026.py --so-verificar` diz, por turno, se os arquivos da importação estão em dia.
- **Microdados do 2º turno — depois de 25/10:**
  - **Ligar as duas vigias logo depois da noite** (se as do 1º turno com `--acompanhar` já estiverem no ar,
    elas cuidam do 2º turno também):

    ```bash
    python preparar_2026.py --acompanhar                                  # RJ
    python baixar_ufs.py --etapas microdados --ufs todas --acompanhar     # as outras UFs
    ```

  - **Nível dos totais, POR TURNO** (rodada 55): oficial (`detalhe_votacao_munzona`) > seções (`votacao_secao` +
    `detalhe_votacao_secao`) > **Boletim de Urna** > nada. Um nível melhor substitui o pior, nunca o contrário. A
    troca grava `saidas/<UF>/conferencia_<antigo>_x_<novo>_2t.csv`.
  - **O Boletim de Urna costuma sair antes:** em 2022, o BU do 2º turno saiu em 01/11, e os microdados e o munzona
    só em 05/11. As vigias procuram o BU no portal de dados do TSE (CKAN) quando o turno ainda não tem nada melhor,
    conferem o SHA-512 e importam com os totais **provisórios (BU)**.
  - **Presidente no Brasil pelo BU:** sem `--bweb-brasil`, a abrangência Brasil sai (com aviso no `status.json`),
    porque o BU da UF não dá o total do país. Com ela, as vigias baixam os 28 BUs do turno (69 MB no 2º turno de
    2022):

    ```bash
    python preparar_2026.py --vigiar --bweb-brasil
    ```

  - **Para só olhar:** `python preparar_2026.py --so-verificar`, que mostra, por turno, o que foi importado, o que
    o cache permite e o BU listado no CKAN.
  - **Para forçar um nível:** `--politica-totais bweb|secoes|oficial`. Ele falha se o nível estiver indisponível;
    nunca cai para outro.
  - **Com `--vigiar`**, as vigias encerram com o detalhe e o partido munzona oficiais; **com `--acompanhar`**, seguem verificando.
- **Com os microdados do 2º turno no cache:**
  - transferência 1º → 2º turno por seção (`transferencia_turnos.py --ano 2026 --cargo governador --nivel secao`)
    e a camada "Destino dos eliminados" no mapa;
  - `python comparar_ufs.py` (o 2º turno entra sozinho);
  - abstenção × mudança de local do 2º turno: `python abstencao_mudanca_local.py --uf todas --turno 2`;
  - recalibrar a margem do 2º turno com 2026 (`docs/RECALIBRAR_MARGENS.md`).
- **Dados do IBGE** (rodada 34): `python preparar_ibge.py --so-verificar` mostra se o IBGE publicou uma versão nova das malhas ou dos agregados do Censo 2022 (ele põe a data no nome do arquivo). `python preparar_ibge.py` baixa, refaz os derivados e, se a versão nova não converter, volta à anterior. Depois, reinicie o site. `preparar_2026.py` já garante o IBGE no cache quando os votos por seção chegam.
- **Recalibrar as margens** da projeção e das cadeiras com 2026, seguindo `docs/RECALIBRAR_MARGENS.md`. Primeiro valide 2026 com as margens de 2022 (o teste fora da amostra) e depois junte os dois anos.
