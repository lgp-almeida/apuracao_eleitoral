# Rodada 07 — Série temporal por município na aba Candidato

30/09/2026 · pedido do usuário após a [rodada 06](RODADA_06_2026-09-29_serie_temporal.md)

## Objetivo

Na aba Candidato, mostrar como o % dos válidos do candidato evolui ao longo da apuração em cada município, comparado com o estado.

## Volume e desenho

Cada arquivo municipal do TSE traz **todos** os candidatos do cargo; Dep. Estadual no Rio tem cerca de 2 mil. A série do painel (`historico_serie.parquet`, rodada 06) é reescrita a cada ciclo e só cobre UF/BR. Fazer o mesmo por município daria dezenas de milhões de linhas por noite. Solução:

- **`historico_candidatos/`**: um bloco Parquet **por ciclo**, só com os arquivos que mudaram, sem reescrever os blocos anteriores. Cada bloco tem:
  - uma linha por candidato **com voto** (> 0) na abrangência (município, UF ou BR), com hora da totalização, % de seções, votos e % dos válidos;
  - uma linha de referência `NUMERO = 0` por totalização. Candidato ausente num momento em que houve totalização = 0 voto ali.
- **Consulta** (`serie.serie_candidato`): `scan_parquet` com filtro de cargo + número empurrado para o Parquet. Nos dados do simulado: 1,2 milhão de linhas, 1,5 MB, **15 ms** por consulta.
- **`reconstruir_candidatos`**: refaz os blocos a partir de todas as versões guardadas em `raw/`, em lotes de 200 arquivos. O coletor chama essa função sozinho quando o diretório ainda não existe; no simulado, reconstruiu a partir de 932 brutos em cerca de 3 s.

## O que foi feito

- **`apuracao/divulgacao/serie.py`:** `linhas_candidatos`, `gravar_bloco`, `reconstruir_candidatos` e `serie_candidato`.
- **Coletor:** ao fim de cada ciclo, grava o bloco dos EA20 novos (`<AAAAMMDDTHHMMSSffffff>.parquet`).
- **API:** `GET /api/candidato/serie?cargo&numero[&municipio]` devolve o município (se pedido), a UF e, para Presidente, o Brasil.
- **Aba Candidato:**
  - caixa "Evolução na apuração" com seletor de município; por padrão, o município onde o candidato tem mais votos;
  - **clique numa linha da tabela** troca o município;
  - gráfico com a linha do município e a do estado (e do Brasil, para Presidente). O **eixo x é a hora**, porque município e estado avançam em ritmos diferentes;
  - a dica mostra, para cada linha, o %, os votos, o % de seções e a hora da totalização;
  - endereço direto: `#candidato/<cargo>/<número>/<município TSE>`.
- **Gráfico:** a função do painel foi generalizada (`graficoLinhas`, eixo x numérico qualquer, x por série). O painel continua com x = % de seções.

## Achado

Na primeira versão, `linhas_candidatos` juntava candidatos e totais de um lote só pela abrangência. Na **reconstrução**, um lote pode ter várias versões do mesmo arquivo, e os votos de uma versão se misturavam com os totais de outra: o Rio às 18h aparecia com os votos das 16h. O teste de reconstrução revelou o problema; agora as linhas são montadas por arquivo, cada uma com os próprios totais. No coletor ao vivo isso não ocorria, porque cada ciclo tem uma versão por arquivo.

## Verificação

- `pytest -q`: **50 testes passando**. O teste novo, `test_serie_por_municipio`, usa `FakeTSE.avancar_municipio` e cobre:
  - um bloco por ciclo;
  - pontos 100% → 50% → 90%;
  - 0 voto preenchido pela linha de referência;
  - candidato inexistente;
  - reconstrução igual à série ao vivo;
  - a rota com município, UF e Brasil.
- **Visual:** demonstração com 6 totalizações do Rio e do estado (TSE falso), conferida em captura do Chrome.
- **Simulado real:** a série foi reconstruída e a rota responde, com 1 ponto por abrangência (simulado encerrado); a caixa mostra "A evolução aparece a partir da 2ª totalização".

## Pendências

- Na noite de 4/10, os blocos se acumulam a cada ciclo. Se passarem de algumas centenas de arquivos, compactá-los num só (não implementado; a consulta continua rápida com muitos arquivos pequenos).
