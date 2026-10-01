# Rodada 02 — Ano-base da comparação de locais (`--comparar-com`)

29/09/2026 · ajuste de `planilha_candidato.py` pedido pelo usuário após a [rodada 01](RODADA_01_2026-09-29_eleitorado_planilha_candidato.md)

## Problema

Com `--ano 2022`, o Resumo mostrava "Locais do resultado com mudança 2024→2026". O rótulo estava fiel ao código, que sempre comparava o cadastro de 2024 com o de 2026. O problema era que, para um resultado de 2022, essa comparação é a errada. Na planilha do candidato 13713 (Dep. Estadual, RJ), 97 dos 4.813 locais usados em 2022 não existem no cadastro de 2024:

- 91 apareciam como `SEM_CADASTRO_2024_E_2026`;
- 6 apareciam como `NOVO_EM_2026`, o que é errado do ponto de vista de 2022: existiam em 2022, sumiram em 2024 e voltaram em 2026.

## O que mudou

- **Nova opção `--comparar-com ANO`.** As mudanças de local são medidas entre o cadastro de eleitorado do **ano-base** e o de 2026.
  - O padrão é o ano do resultado (`--ano`).
  - Para resultados de 2026, o padrão é 2024.
  - `--comparar-com 2024` reproduz o comportamento da rodada 01.
  - Um ano-base a partir de 2026 é recusado, com código de saída 1.
- **Nomes derivados dos anos comparados:**
  - `MUDANCA_<base>_2026`, `LOCAL_<base>`/`LOCAL_2026` (aba Por seção), `VALOR_<base>`/`VALOR_2026` (Inconsistências) e `SEM_CADASTRO_<base>_E_2026`;
  - `DESATIVADO_EM_2026`, `NOVO_EM_2026` e `SECAO_EXTINTA_EM_2026` continuam com o ano novo.
- **Eleitorado:** sempre `ELEITORADO_2024` e `ELEITORADO_2026`, como na especificação original, mais `ELEITORADO_<base>` quando o ano-base é outro. `VAR_ELEITORADO`/`VAR_ELEITORADO_PCT` agora medem a variação **do ano-base para 2026**.
- **Resumo:**
  - nova linha "Comparação de locais: cadastro <base> × cadastro 2026";
  - os rótulos agora trazem os dois anos, por exemplo "Locais do resultado (2022) com mudança 2022→2026";
  - a legenda também é gerada com os anos da comparação.
- **Bairro e coordenadas:** vêm do cadastro do ano do resultado; se o local não estiver nele, de 2026, do ano-base e, por fim, de 2024.
- **Cadastro obrigatório:** o do ano-base passa a ser obrigatório e é baixado da CDN se faltar. O do ano do resultado continua opcional quando não é o ano-base.

## Arquivos

- `apuracao/locais.py`: todas as funções recebem `old` (ano-base) e `new` (padrão 2026). As constantes `DESATIVADO`/`NOVO`/`INCONSISTENCY_COLUMNS` foram substituídas por `desativado()`, `novo()`, `change_col()` e `inconsistency_columns()`.
- `apuracao/planilha.py`: `Registers` passa a guardar os cadastros por ano (`sections: dict[int, DataFrame]`, `base_year`, `result_year`) e calcula os locais de cada um. `legend()` e `no_register()` são geradas pelos anos. O escritor de xlsx reconhece colunas por prefixo, e não por ano fixo.
- `planilha_candidato.py`: opção `--comparar-com`, `PlanilhaConfig.base_year` e carga dos cadastros `{base, 2024, 2026}` mais o do ano do resultado. A proveniência registra `base_year`.
- Testes: `test_eleitorado_locais.py` usa a nova assinatura. `test_planilha_candidato.py` ganhou a fixture `cache_2022` (sem rede) e três testes:
  - ano-base padrão = ano do resultado, com colunas e rótulos de 2022;
  - cadastro do ano-base obrigatório e `--comparar-com 2026` recusado;
  - `--comparar-com 2024` num resultado de 2022.

## Verificação

- `pytest -q`: **21 testes passando**.
- Execução real, com o comando do usuário: `python3 planilha_candidato.py --ano 2022 --uf RJ --cargo "deputado estadual" --candidato 13713 --turno 1 --saida saidas/planilha_13713_RJ_2022_t1a.xlsx`

| | Rodada 01 (2024→2026) | Agora (2022→2026) |
|---|---|---|
| Locais do resultado com mudança | 1.184 | 1.687 |
| Seções do resultado que mudaram de local | 651 | 1.414 |
| `SEM_CADASTRO_*` | 91 | 0 |
| `NOVO_EM_2026` (incorreto para 2022) | 6 | 0 |
| `DESATIVADO_EM_2026` | 91 | 182 |
| Inconsistências | 350 | 451 |

Os totais de votos não mudaram: 46.422 votos em 4.813 locais. Todos os locais do resultado têm eleitorado de 2022; 97 não têm o de 2024, e 182 não existem em 2026.
