# Rodada 27 — Revisão de código e de segurança do caminho da noite, e versões fixadas

30/09/2026 · pedido do usuário: "Registre no TODO e comece pela 1" (item 6 de `docs/TODO.md`)

## Objetivo

Revisar o que roda na noite de 4/10, com as skills `code-reviewer` e `security-auditor`. As rodadas 20–26 mexeram muito em cadeiras, projeção, API e coletor.

- **Escopo:**
  - `apuracao/divulgacao/{cliente,modelo,coletor,serie}.py`;
  - as rotas do painel, candidato, mapa, projeção e cadeiras em `apuracao/web/app.py`;
  - `apuracao/{projecao,cadeiras,projecao_cadeiras}.py`;
  - `site_apuracao.py`.
- **Também:**
  - fixar as versões;
  - avaliar o que `--host 0.0.0.0` expõe;
  - rodar o ensaio geral no fim.

Toda correção veio com um teste que falhava antes dela.

## Achados e correções

### 🛑 Bloqueadores (3, corrigidos)

1. **O coletor dava a totalização por vista ANTES de baixar os arquivos** (`coletor.py`, `_abrangencias_alteradas`).
   - **Defeito:** a hora nova do EA15 era gravada em `_ultima_totalizacao` logo na leitura do acompanhamento. Se o EA20 daquele município falhasse no mesmo ciclo (timeout, 5xx, página HTML, 404 momentâneo), o ciclo seguinte já não o pedia.
   - **Consequência na noite:** a **totalização final** de um município acontece uma vez só. Com uma falha de rede naquele minuto, o município ficaria parado no parcial até o fim da noite, e o estado também, porque o painel soma as abrangências que o TSE mandou.
   - **Correção:** `_abrangencias_alteradas` só lista o que mudou, e `_confirmar` dá a totalização por vista depois do download.
     - **Falha** (rede, 5xx, HTML, JSON com estrutura inesperada): a abrangência é pedida de novo no ciclo seguinte. Os arquivos dela que não mudaram voltam como 304 e custam pouco.
     - **404:** no máximo `TENTATIVAS_404` = 3 ciclos. Vários 404 podem bloquear o IP.
   - **Testes:** `test_arquivo_que_falhou_e_pedido_de_novo_no_ciclo_seguinte` (4 casos: rede, 500, 404 e HTML) e `test_404_persistente_desiste_depois_de_algumas_tentativas`.

2. **Uma falha num único arquivo derrubava o ciclo inteiro**, e alguns casos pausavam a coleta.
   - **Defeito:** a exceção de um download no `ThreadPoolExecutor` subia para o ciclo e descartava as respostas dos outros arquivos.
   - **Pior caso:** um único EA20 com HTML no lugar do JSON virava `DivulgacaoIndisponivel`, que **pausa a coleta por 5 minutos** e recarrega a configuração.
   - **Correção:** `_baixar` devolve a falha como valor, e o ciclo segue com os outros arquivos. Só o bloqueio (403/429) continua interrompendo o ciclo, porque insistir reinicia o bloqueio. A divulgação fora do ar continua detectada no acompanhamento, que é lido antes.
   - **Caso de canto:** o ciclo interrompido por bloqueio já tinha guardado as ETags no cliente. No ciclo seguinte esses arquivos voltavam como 304 e eram **ignorados**, embora o coletor não os tivesse. Agora um 304 de arquivo que o coletor não guardou usa o conteúdo do cache.
   - **Teste:** `test_bloqueio_no_meio_do_ciclo_nao_perde_o_que_ja_veio`.

3. **O cache de cadeiras e da projeção de cadeiras usava `id()` dos DataFrames como chave** (`app.py`).
   - **Defeito:** o CPython reaproveita o endereço de um objeto liberado. Com as tabelas recarregadas a cada coleta, o endereço alterna entre dois valores (medido: 8 gerações, 3 ids distintos, alternando).
   - **Consequência:** a chave de duas coletas atrás voltava a valer, e o painel mostraria **cadeiras e eleitos de dois ciclos antes**. No fim da apuração, quando os arquivos param de mudar, esse resultado velho poderia ficar para sempre.
   - **Correção:** `Dados.com_versao` devolve a tabela com a versão dela (o `mtime_ns` do Parquet lido junto), e a chave passa a ser a versão das três tabelas (`tabelas_do_resultado`). Não restou nenhum `id()` como chave no projeto.
   - **Teste:** `test_cadeiras_acompanham_cada_nova_coleta`. Ele força o pior caso: `id()` constante no módulo e seis coletas seguidas.

### ⚠️ Importantes (4, corrigidos)

4. **Um erro inesperado matava a coleta pelo resto da noite.** `executar` só tratava indisponibilidade, bloqueio e rede. Um `KeyError` num JSON diferente do esperado, ou um disco cheio, encerrava a thread do coletor, e o site passava a mostrar dados parados.
   - **Correção:** o erro vai para o log com o traceback, entra no `status.json` e o ciclo seguinte roda normalmente.
   - **Teste:** `test_erro_inesperado_nao_mata_o_laco`.
5. **`/api/mapa?momento=` com fuso** (ex.: `…T21:30:00+00:00`) dava **erro 500**: o Polars não compara hora com fuso com a coluna sem fuso. Agora converte para a hora de Brasília, a do TSE. Teste em `test_serie.py`.
6. **`/api/planilha` deixava um diretório no `/tmp` a cada planilha pedida**, inclusive quando dava erro. Agora apaga depois do envio (`BackgroundTask`) ou no erro. Teste em `test_site.py`.
7. **O `ele-c.json` do ensaio anunciava cargos que o ensaio não gera.** Com a correção 1, isso daria 404 repetido. Ele passa a anunciar só os cargos reconstituídos, como o TSE, que só anuncia o que publica (`apuracao/ensaio.py`).

### Segurança (skill `security-auditor`)

- **Front-end:** nenhum `innerHTML`, `insertAdjacentHTML`, `eval` ou `new Function` em `app.js`.
  - Os tooltips e popups do Leaflet, que interpretariam uma string como HTML, recebem nós DOM feitos por `el()`, que insere o texto com `createTextNode`.
  - Os nomes do TSE (o simulado tem aspas e símbolos) não viram HTML.
- **Entradas da API:**
  - parâmetros tipados pelo FastAPI;
  - exportação com cor, tamanho e `dpi` (50–600) validados em `exportar.py`;
  - o nome do arquivo da planilha só usa inteiros e a UF;
  - `StaticFiles` bloqueia `../`.
  - Não há SQL nem `subprocess` com entrada do usuário. O `subprocess` que existe só abre o Chrome com a URL local.
- **Segredos e dados pessoais:**
  - nenhum segredo no código;
  - os dados são públicos do TSE e do IBGE, e todo perfil é agregado (seção, local, bairro);
  - os logs não trazem dados pessoais.
- **Dependências:** eram só mínimos (`>=`). Agora estão fixadas (abaixo).
  - O `pip-audit` achou 3 CVEs no `urllib3` 2.7.0: atualizado para 2.8.0 (ver Verificação).

### `--host 0.0.0.0`: o que expõe

- **O que fica visível:** sem senha e sem HTTPS, qualquer máquina que alcance a porta vê tudo o que o site mostra. São dados públicos do TSE, então não há vazamento.
- **Risco real: disponibilidade.** Várias rotas baixam microdados e malhas (centenas de MB) e convertem ou cruzam dados com muita CPU e memória. Com `--coletar`, isso acontece **no mesmo processo do coletor**. Alguém na rede consultando o Perfil × voto na hora da apuração atrasaria a coleta.
  - As rotas: planilha, mapa e comparação por bairro, Perfil × voto, exportação, locais.
- **Correção:**
  - `create_app(..., pesadas_so_local=True)` — o `site_apuracao.py` liga isso sozinho quando `--host` não é loopback;
  - as rotas de `ROTAS_PESADAS` respondem **403** para quem não está na própria máquina;
  - painel, mapas por município, candidato, projeção e cadeiras continuam abertos;
  - ao subir exposto, o site avisa no log.
  - **Teste:** `test_site_na_rede_so_atende_consultas_pesadas_da_propria_maquina`.
- **No WSL2:** `0.0.0.0` nem chega à rede local sem redirecionamento de porta no Windows.
- **Recomendação** (no roteiro): na noite, `127.0.0.1`; para a equipe, capturas ou o boletim (item 7).

### 💡 Sugestões (não feitas)

- **Leitura de tabelas no meio de uma gravação:** `Dados` lê `totais`, `candidatos` e `partidos` separadamente. Durante a gravação do coletor, que leva milissegundos, uma resposta pode misturar tabelas de duas coletas.
  - A salvaguarda "os votos das agremiações não somam os válidos" (rodada 20) aponta o caso, e a resposta seguinte já sai certa.
  - Resolver de vez pede gravar as tabelas num diretório por versão, com troca atômica do ponteiro.
- **Custo do painel:** o painel recalcula a projeção dos majoritários a cada pedido, sem cache. É barato (92 municípios), mas cabe o mesmo cache por versão das cadeiras se o site ficar lento com muitos usuários.

### ✅ O que está bem feito

- O `LimitadorTaxa` é global e seguro entre threads; o 404 é memorizado por ciclo.
- A pausa de 11 min no bloqueio não reinicia o bloqueio.
- A gravação é atômica em todo lugar (tmp + `replace`). O JSON bruto guarda cada versão com hash, e a série se reconstrói de `raw/`.
- O domínio (cadeiras, projeção, projeção de cadeiras) não faz I/O e foi validado com a apuração real de 2022.

## Versões fixadas

- **`requirements.txt`:** `==` nas dependências diretas, iguais às do venv que passou nos testes e no ensaio. Por exemplo: polars 1.44.2, fastapi 0.142.1, uvicorn 0.54.0, numpy 2.5.1, geopandas 1.1.4.
- **`requirements-lock.txt` (novo):** `pip freeze` completo, com as dependências indiretas, para reinstalar idêntico.
- **`verificar_prontidao.py`:** passa a comparar as versões instaladas com as fixadas (`versoes_fixadas`) e dá AVISO quando diferem. Teste em `test_prontidao.py`.
- **`CLAUDE.md`:** dizia que `geobr` não estava instalado. Está (2.1.1), e o texto foi corrigido.

## Arquivos

- **Alterados:**
  - `apuracao/divulgacao/coletor.py`: `_baixar`, `_confirmar`, `TENTATIVAS_404`, `arquivos_com_falha` no resumo e no `status.json`, e laço protegido;
  - `apuracao/web/app.py`: `Dados.com_versao`, `tabelas_do_resultado`, `ROTAS_PESADAS`, `eh_loopback`, `pesadas_so_local`, momento com fuso e limpeza da planilha;
  - `apuracao/ensaio.py`: o `ele-c.json` anuncia só os cargos gerados;
  - `site_apuracao.py`: aviso e restrição quando o site fica exposto;
  - `verificar_prontidao.py`: `versoes_fixadas`;
  - `requirements.txt`;
  - `conftest.py`: `FakeTSE.falhas`, com falhas de um tiro só (rede ou código HTTP).
- **Novos:** `requirements-lock.txt`, `test_prontidao.py`.
- **Testes alterados:** `test_divulgacao.py` (+5 testes, um deles com 4 casos), `test_cadeiras.py` (+1), `test_site.py` (+1, e a planilha confere o `/tmp`), `test_serie.py` (fuso).
- **Documentação:** `docs/ROTEIRO_NOITE_DA_ELEICAO.md` (arquivos com falha e o site na rede), `docs/TODO.md`, `docs/INDEX.md`, `CLAUDE.md`.

## Verificação

- **Testes:** `pytest -q` passa com **213 testes**, os de navegador incluídos; eram 203. Os testes novos falhavam antes das correções.
- **Ensaio geral:** `python ensaio_apuracao.py`, com a apuração de 2022 do RJ a 30×, o coletor real, o site real e usuários simultâneos (4 neste ensaio). O resultado fica abaixo.

Ensaio: **RESULTADO DO ENSAIO: OK**, com o código desta rodada. Os números estão em `dados_2026/ensaio_2022/relatorio_ensaio.json`.

- **Duração:** noite de 2022 das 17:21 às 00:20, em 14,4 min reais.
- **Coleta:** 53 ciclos, 6.034 arquivos pedidos (5.702 novos, 332 com 304), **0 com 404**, 0 ciclos com erro.
  - O ensaio anterior (rodada 23) teve 7.577 pedidos. A diferença vem do ritmo dos ciclos na hora virtual, não de arquivos a menos: a conferência bate igual.
  - O 1º ciclo baixou 466 arquivos em 29,7 s.
- **Site:** 5.020 consultas de 4 usuários simultâneos, com **0 erros 5xx ou de rede**.
  - Tempos p50/p95: painel 140/971 ms; cadeiras 15–16/136–379 ms.
  - Houve um 404 em `cadeiras?cargo=6` antes de haver dados.
- **Conferência com o oficial:** válidos de Presidente, Governador e Senador iguais. Deputados com diferença de 0,005% e 0,006%, a mesma da rodada 23 (anulados sub judice). 100% e totalização final em todos os cargos. Cadeiras 46/46 e 70/70 sem divergência. Castro eleito no 1º turno.

**Depois do ensaio:**
- `urllib3` passou de 2.7.0 para 2.8.0, por causa do `pip-audit` abaixo.
- Nova rodada completa: `pytest -q` com 213 testes, `pip check` sem conflito e `verificar_prontidao.py` em **PRONTO** (0 falhas, 2 avisos esperados: a porta 8000 com o site de teste e os códigos do oficial).
  - O `urllib3` é usado só pelo `requests`. O ensaio não passa por ele: a sessão do TSE é falsa.
  - A prontidão faz os acessos reais ao TSE e passou com a versão nova.

**`pip-audit`** (num venv descartável, sobre `requirements-lock.txt`):
- `urllib3` 2.7.0 tinha **3 vulnerabilidades** (CVE-2026-97687, -97688 e -97689), corrigidas na 2.8.0.
- Foi atualizado e fixado em `requirements.txt`. Nova auditoria: **nenhuma vulnerabilidade conhecida**.

**Observação da prontidão:** o oficial hoje ainda serve a configuração de **2024** (`ciclo ele2024`, eleições 619 e 633–637). É seguro: sem Governador no arquivo, o coletor responde "nenhuma eleição do 1º turno" e tenta de novo a cada 5 min. Em 3/10, conferir que o ciclo virou `ele2026`.

## Pendências

- As sugestões 💡 acima.
- 3/10: `verificar_prontidao.py` e um ciclo no oficial, como está no roteiro. Conferir que o oficial passou de `ele2024` para `ele2026`.
- Repetir o `pip-audit` se alguma versão mudar antes de 4/10.
