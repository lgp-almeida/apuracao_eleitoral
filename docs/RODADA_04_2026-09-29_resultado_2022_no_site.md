# Rodada 04 — Resultados de 2022 (1º e 2º turno) no site de apuração

29/09/2026 · pedido do usuário após a [rodada 03](RODADA_03_2026-09-29_coleta_e_site.md)

## Objetivo

Abrir no site de apuração (painel, candidato, mapas) os resultados de 2022 do RJ e do Presidente, nos dois turnos.

## Por que não pela divulgação em tempo real

A divulgação em JSON de 2022 saiu do ar: todos os endereços `resultados.tse.jus.br/oficial/ele2022/...` respondem 404. A solução foi montar **as mesmas tabelas do coletor** (`ultimo/{totais,candidatos,partidos,municipios}.parquet` + `status.json`) a partir dos microdados da CDN. Assim, o site não precisou de mudanças estruturais.

## O que foi feito

- **`apuracao/historico.py` + CLI `importar_resultado_historico.py --ano 2022 --uf RJ --turno 1 2`.** Grava `dados_2026/historico_2022_t1/` e `…_t2/` em cerca de 3 s, com os arquivos já no cache. Fontes:

| Tabela | Fonte |
|---|---|
| totais (aptos, comparecimento, abstenção, seções, válidos, nominais, legenda, brancos, nulos, anulados, sub judice) | `detalhe_votacao_munzona_2022` (4,4 MB), somado por município, UF e Brasil (exterior incluído) |
| votos por candidato | `votacao_secao_2022_RJ` (estaduais) e `votacao_secao_2022_BR` (Presidente, todas as UFs; 271 MB, 5,4 milhões de linhas) |
| nome de urna, partido, federação/coligação, situação por turno | `consulta_cand_2022` (4,4 MB) |
| código IBGE dos municípios | EA12 da divulgação 2026 do TSE, em cache em `cache_tse/municipios_tse_ibge.parquet` |

- **`votos_por_local_votacao.py`:** constante `NATIONAL = "BR"`. Com esse `uf_filter`, `zip_to_parquet` mantém todas as UFs, o que é necessário para o total do Presidente no Brasil.
- **Site:**
  - título, selo e camada de locais de votação passam a seguir o ano dos dados (`status.json` → `ano`);
  - os seletores de cargo mostram só os cargos presentes nos dados (no 2º turno de 2022 do RJ, só Presidente);
  - para dados históricos, o cabeçalho diz "Importado em" em vez de "Última coleta";
  - `/api/status` devolve `cargos`.
- **Testes:** `test_historico.py`, com 4 testes sobre dados sintéticos. Cobrem totais por abrangência (Brasil com outras UFs e exterior), situação, duplicados e candidato inapto eleito, partidos, vagas, 2º turno e a importação aberta no site.

## Conferência com o resultado oficial de 2022

| | Obtido | Oficial |
|---|---|---|
| Presidente, 1º turno, Brasil | Lula 57.259.504 (48,43%) · Bolsonaro 51.072.345 (43,20%) | idem |
| Presidente, 2º turno, Brasil | Lula 60.345.999 (50,90%, eleito) · Bolsonaro 58.206.354 (49,10%) | idem |
| Presidente, 2º turno, RJ | Bolsonaro 56,53% · Lula 43,47% | idem |
| Aptos Brasil / válidos 1º turno | 156.454.011 / 118.229.719 | idem |
| Governador RJ | Cláudio Castro 58,69%, eleito no 1º turno | eleito no 1º turno |
| Senador RJ | Romário 36,16%, eleito | idem |
| Vagas RJ | 46 Dep. Federal, 70 Dep. Estadual | idem |

## Achados

1. **O cadastro de candidatos reflete decisões posteriores ao pleito.** O `consulta_cand_2022` foi regerado em 29/09/2026. Cláudio Castro aparece **INAPTO**, mas foi eleito em 2022 com votos válidos (Witzel e Luiz Eugênio também constam INAPTO). O importador **não** trata esses votos como anulados: mostra na destinação "candidatura INAPTO no cadastro de 29/09/2026". Nos cargos de Governador e Dep. Estadual, a soma dos votos de candidaturas hoje "aptas" diverge dos nominais válidos da totalização, por isso a destinação não pode ser deduzida do cadastro atual.
2. **Retotalizações.** O `detalhe_votacao_munzona` traz a data da última totalização: 05/09/2026 para Dep. Federal e Estadual, o que é coerente com o recálculo das sobras citado no Anexo I; 01/12/2022 para Governador e Senador. O site mostra essa data como "totalização".
3. **Números de candidato repetidos:** 10 casos, por substituição de candidatura. Fica a candidatura APTA com situação preenchida.
4. **Tempo real × histórico:** a divulgação em tempo real não separava os votos de candidaturas sub judice por candidato da mesma forma que os microdados; os totais de sub judice vêm do `detalhe` (0 para Presidente em 2022; 38.713 para Dep. Estadual no RJ).

## Verificação

- `pytest -q`: **43 testes passando**.
- Sites no ar e conferidos por captura de tela:
  - 1º turno em `http://localhost:8022`: painel com os 6 cargos;
  - 2º turno em `http://localhost:8023`: mapa de mais votado por município, Presidente.

## Como usar

```
python importar_resultado_historico.py --ano 2022 --uf RJ --turno 1 2
python site_apuracao.py --dados dados_2026/historico_2022_t1 --porta 8022
python site_apuracao.py --dados dados_2026/historico_2022_t2 --porta 8023
```

## Pendências

- O mesmo importador serve para 2026 depois que o TSE publicar os microdados, e é a base da comparação 2022 × 2026 (ainda por fazer).
- Outras UFs e 2018 não foram testados. O código é parametrizado, mas o layout dos arquivos antigos pode variar.
