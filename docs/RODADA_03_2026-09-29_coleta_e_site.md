# Rodada 03 — Coleta dos resultados de 2026 (d) e site local de apuração (e)

29/09/2026 · plano aprovado: `~/.claude/plans/crispy-dazzling-hoare.md` (versão da rodada 03)

## Objetivo

Deixar pronto, para a noite do 1º turno (4/10/2026):
- **(d)** a importação dos resultados em tempo real do TSE;
- **(e)** um site local, no Chrome, com painel geral, consulta por número de candidato e mapas.

**Decisões do usuário:** backend Python (FastAPI) com página HTML/JS; coleta de todos os cargos do RJ mais Presidente (Brasil, RJ e municípios); cruzamentos que dependem de microdados ficam para depois da eleição.

## O que foi entregue

### (d) Coleta — `coletar_resultados.py` + `apuracao/divulgacao/`

- **`cliente.py`:**
  - limite de 20 req/s compartilhado entre threads;
  - ETag/304;
  - 404 memorizado por ciclo;
  - página HTML ou 404 no lugar de JSON gera `DivulgacaoIndisponivel` (mensagem clara, nova tentativa em 5 min);
  - 403/429 geram `BloqueioTSE` (pausa de 11 min);
  - caminhos montados a partir dos modelos de diretório do próprio `ele-c.json`.
- **`modelo.py`:** parse puro de EA11, EA12, EA14/15 e EA20 para tabelas Polars (`totais`, `candidatos`, `partidos`, `municipios`, `acompanhamento`).
- **`coletor.py`:**
  - ciclo incremental: compara o `dt/ht` de cada abrangência (EA14/15) e baixa o EA20 só do que mudou;
  - 8 downloads simultâneos;
  - grava o JSON bruto de cada mudança (`raw/`), o último estado (`ultimo/*.parquet`), `historico_totais.parquet` e `status.json`.
- **Execução:** `python coletar_resultados.py --ambiente simulado|oficial [--uma-vez] [--turno 2] [--intervalo 60]`, com dados em `dados_2026/<ambiente>/`.

**Medições no simulado real:**
- 1º ciclo: 187 abrangências e 466 arquivos em 35–39 s. Todas as 469 requisições com 200, nenhum 404, cerca de 12 MB.
- Ciclo sem mudança: 3 requisições (304) em 0,2 s.
- Totais conferidos com o JSON: Governador RJ com 38.926 seções, eleitorado de 13.319.487 e 7.824.970 válidos.
- A versão sequencial levava 245 s; a paralelização reduziu para 35 s.

### (e) Site — `site_apuracao.py` + `apuracao/web/`

- **Um comando só na noite da eleição:** `python site_apuracao.py --ambiente oficial --coletar --abrir`. Sobe o site em `http://localhost:8000` e o coletor numa thread.
- **Abas:**
  - **Painel:** cartões de Presidente (Brasil e RJ), Governador, Senador (2 vagas), Dep. Federal e Dep. Estadual. Cada cartão mostra seções totalizadas; eleitorado com comparecimento e abstenção; votos válidos, brancos, nulos e anulados sub judice; candidatos com % e situação; e, nos cargos proporcionais, os partidos. Atualiza a cada 60 s.
  - **Candidato:** busca por número ou nome; fichas (votos, %, posição, situação, destinação, vice); tabela ordenável por município, com a posição do candidato em cada um; minimapa. Tem também o formulário da **planilha histórica**, que gera o `.xlsx` da rodada 01/02 pelo navegador (13713/2022 em 6 s).
  - **Mapas:** coroplético por município.
    - Métricas: mais votado; % ou votos de um candidato; abstenção; comparecimento; brancos, nulos ou os dois somados; seções totalizadas.
    - Camada opcional com os 5.056 locais de votação de 2026, dimensionados pelo eleitorado.
- **Links diretos:** `#mapas` e `#candidato/<cargo>/<número>`.
- **Dependências locais:**
  - Leaflet 1.9.4 está dentro do projeto (`static/vendor/`), sem depender de CDN;
  - a malha municipal vem da API do IBGE, baixada uma vez para `cache_tse/malhas/`;
  - o fundo do mapa usa o OpenStreetMap e precisa de internet, mas o mapa funciona sem ele.
- **Cores** (skill dataviz):
  - rampa azul sequencial em 5 quantis, com mais casas decimais quando os percentuais são pequenos;
  - no mapa de mais votado, só 3 cores categóricas mais "Outros", porque num mapa todos os pares de cor se tocam;
  - modo escuro com tons próprios;
  - textos nunca na cor da série.
- **Segurança:** todo texto vindo do TSE entra por `textContent`, porque o simulado usa nomes como `Candidato string 1234!@#$"TSE"`.

## Arquivos

- **Novos:**
  - `apuracao/divulgacao/{__init__,cliente,modelo,coletor}.py`;
  - `apuracao/web/{__init__,app}.py`, `apuracao/web/static/{index.html,app.js,style.css}`, `apuracao/web/static/vendor/leaflet/`;
  - `coletar_resultados.py`, `site_apuracao.py`;
  - `tests/fixtures/divulgacao/*.json`: 13 recortes reais do simulado, 156 KB;
  - `test_divulgacao.py`, `test_site.py`;
  - `docs/divulgacao_2026_formato_json.md` e este documento.
- **Alterados:**
  - `conftest.py`: `FakeTSE`, que serve as fixtures com ETag/304/404/HTML, gera arquivos que faltam e simula uma nova totalização;
  - `requirements.txt`: fastapi, uvicorn, httpx;
  - `CLAUDE.md` e `docs/INDEX.md`.
- **Dependências instaladas no venv:** fastapi 0.142.1, uvicorn 0.54.0, httpx 0.28.1.

## Decisões e achados

1. **O ambiente oficial ainda não está no ar.** Em 29/09, `ele-c.json` do oficial responde 404 com página HTML; a mensagem do coletor diz isso explicitamente. **Pendência:** repetir `--ambiente oficial --uma-vez` a partir de 3/10.
2. **O EA12 traz o código IBGE (`cdi`).** A tabela externa de correspondência TSE↔IBGE deixou de ser necessária para os mapas.
3. **Votos sub judice.** Os votos de candidatura sub judice somam no candidato, mas não nos válidos. No simulado, dois candidatos a Governador estão nessa situação, e um aparece como "2º turno". O painel e a página do candidato mostram a destinação.
4. **`e = s` não significa só "eleito".** Também marca quem vai ao 2º turno, por isso o site exibe a situação (`st`).
5. **Ordem de grandeza por ciclo.** Dep. Estadual no município do Rio tem 479 KB e 1.950 candidatos; o estado inteiro tem cerca de 307 mil linhas de candidato-abrangência.
6. **2º turno.** Só Governador e Presidente são pedidos. Pedir os demais cargos daria 404 a cada ciclo, o que arrisca o bloqueio do IP.
7. **Granularidade do tempo real.** O mínimo é o município; mapas por local de votação com votos de 2026 dependem dos microdados publicados dias depois.

## Verificação

- `pytest -q`: **39 testes passando** (21 anteriores e 18 novos), offline.
  - Parse das fixtures reais e caminhos derivados do `ele-c.json`.
  - Cliente: ETag/304, 404 memorizado, HTML → indisponível, limitador.
  - Coletor: 1º ciclo com 21 arquivos, ciclo sem mudança só com 304, nova totalização rebaixando apenas os 4 cargos do Rio, 2º turno e ambiente indisponível.
  - Rotas do site: painel, candidato, mapas, camadas geográficas e planilha, com número ambíguo → 400.
- **Simulado real:** ciclos medidos acima; `site_apuracao.py --coletar` subiu o site com o coletor na thread (466 arquivos em 39 s). As três abas foram conferidas em capturas do Chrome em modo headless, e a planilha 13713/2022 foi baixada pelo site.
- **Oficial:** `coletar_resultados.py --ambiente oficial --uma-vez` termina com código 1 e a mensagem "divulgação ainda não disponível… respondeu 404".

## Pendências

- **3/10:** testar no ambiente oficial quando os parâmetros entrarem no ar e conferir os códigos 6257/6259.
- **4/10 à noite:** rodar `python site_apuracao.py --ambiente oficial --coletar --abrir` e acompanhar `status.json` e o cabeçalho do site.
- **Pós-eleição:**
  - mapas por local de votação com os microdados `votacao_secao_2026_RJ`;
  - comparação 2022 × 2026 por município ou local;
  - boletins de urna por seção;
  - outras UFs (o código já é parametrizado por `--uf`);
  - série temporal da apuração no site (o `historico_totais.parquet` já é gravado).
- **Não verificado:** a alternância da camada de locais e o modo escuro só foram testados via API e CSS; não houve captura de tela desses dois.
- **Aviso nos testes:** o `TestClient` emite um aviso de depreciação (starlette recomenda `httpx2`). É inofensivo.
