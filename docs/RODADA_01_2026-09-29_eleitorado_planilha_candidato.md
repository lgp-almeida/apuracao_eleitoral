# Rodada 01 — Ingestão do eleitorado e planilha por candidato

29/09/2026 · plano aprovado: `~/.claude/plans/crispy-dazzling-hoare.md` (resumido aqui)

## Objetivo

Primeira rodada da suíte de apuração das eleições de 2026. O pedido tinha cinco frentes:

- (a) ingerir no cache o eleitorado de 2026;
- (b) **prioridade absoluta:** dado ano + número do candidato, gerar um `.xlsx` com votos somados por local de votação, zona e bairro. A planilha traz o eleitorado de 2024 e de 2026, destaca os locais que mudaram entre os dois anos e lista as inconsistências de cadastro;
- (c) avaliar se as coordenadas permitem fazer mapas;
- (d) cliente online dos resultados de 2026 no TSE;
- (e) site local com dashboard, consulta por candidato e mapas.

Nesta rodada foram entregues **(a), (b) e (c)**. **(d) e (e)** ficaram para a próxima.

## O que foi feito

### (a) Ingestão do eleitorado — `ingerir_eleitorado.py`

- Converte o ZIP do cache em Parquet por UF (`cache_tse/eleitorado_local_votacao_<ano>__<UF>.parquet`) e imprime um resumo.
- `--relatorio-geo` acrescenta ao resumo a qualidade das coordenadas.
- Quando o ZIP foi colocado no cache à mão, que é o caso de 2026, grava `eleitorado_local_votacao_2026.proveniencia.json` com SHA-512, tamanho, data do arquivo e data/hora de geração do TSE lidas do próprio CSV (29/09/2026 06:28:09).
- O eleitorado de 2024, que faltava, foi baixado da CDN (45 MB). O de 2022 foi baixado sob demanda (24 MB) quando a planilha de 2022 foi gerada.

Números do RJ (1º turno):

| | 2024 | 2026 |
|---|---|---|
| Seções | 37.706 | 38.738 |
| Seções agregadas | 1.498 | 1.063 |
| Seções remanejadas (`_ORIGINAL`) | 97 | 44 |
| Seções em local BLOQUEADO | 3.758 | 2.198 |
| Eleitores | 13.033.929 | 12.857.000 |
| Municípios / zonas | 92 / 183 | 92 / 183 |
| Locais | 4.971 | 5.062 |
| Locais sem coordenada | 0 | 6 |

### (b) Planilha por candidato — `planilha_candidato.py`

```
python planilha_candidato.py --ano 2024 --uf RJ --cargo vereador --candidato 22222 --municipio "Rio de Janeiro"
```

| Aba | Conteúdo |
|---|---|
| Resumo | candidato, cargo, área, totais, eleitorado 2024/2026, contagens de mudanças e de inconsistências por tipo, legenda |
| Por local | votos (candidato, nominais, legenda, brancos, nulos, válidos, % sobre válidos), bairro, coordenadas, `FONTE_CADASTRO`, `ELEITORADO_2024/2026`, variação, `MUDANCA_2024_2026`, `LOCAL_2026`, `SITUACAO_LOCAL_2026`, `DISTANCIA_M`, seções que saíram/entraram |
| Por zona | votos + eleitorado da zona inteira em cada ano + nº de locais com mudança |
| Por bairro | idem, com bairro normalizado dentro do município |
| Por secao | votos por seção + local em 2024/2026 + `STATUS_SECAO` |
| Mudancas locais / Mudancas secoes | todas as mudanças 2024→2026 na área, inclusive de locais sem votos no ano do resultado |
| Inconsistencias | `TIPO / CHAVE / VALOR_2024 / VALOR_2026 / DETALHE` |
| Proveniencia | configuração da execução + `.proveniencia.json` de cada arquivo usado |

**Destaque:** formatação condicional na linha inteira. Amarelo quando há mudança; vermelho quando o local foi `DESATIVADO_EM_2026`, a seção é `SECAO_EXTINTA_EM_2026` ou o local está `SEM_CADASTRO_2024_E_2026`. Todas as abas têm cabeçalho congelado e tabela do Excel com filtro.

**Status de mudança de local:**
- `MANTIDO`;
- `RENOMEADO` e `ENDERECO_ALTERADO`;
- `DESLOCADO` (mais de 150 m);
- `DESATIVADO_EM_2026` e `NOVO_EM_2026`;
- `SECOES_SAIRAM` e `SECOES_ENTRARAM`;
- `REMANEJAMENTO_2026`;
- `TEMPORARIO_2026`.

**Tipos de inconsistência:**
- `COORDENADA_AUSENTE`, `COORDENADA_FORA_DA_UF` e `COORDENADA_COMPARTILHADA`;
- `COORDENADA_SALTO_5KM`;
- `BAIRRO_DIVERGENTE`;
- `VARIACAO_ELEITORADO` (mais de ±50%);
- `RENUMERACAO_PROVAVEL`;
- `ZONA_EM_UM_SO_ANO`;
- `LOCAL_SEM_CADASTRO`;
- `LOCAL_2026_AUSENTE_NA_LISTA_TRE`, `LOCAL_TRE_AUSENTE_NO_CADASTRO_2026` e `SECOES_DIVERGEM_DA_LISTA_TRE`.

A conferência com a lista do TRE usa `cache_tse/consulta_de_locais_de_votacao_2026-09-29.json` e é feita só para o RJ.

**Comparação 2024 × 2026 no RJ inteiro:**
- 793 seções mudaram de local, 45 deixaram de existir e 1.077 são novas.
- Das mudanças por local:
  - endereço alterado: 655;
  - renomeado: 532;
  - novo: 194;
  - deslocado: 156;
  - desativado: 103.

**Execuções reais** (arquivos em `saidas/`):

| Planilha | Votos | Locais | Locais com mudança | Inconsistências |
|---|---|---|---|---|
| `planilha_13713_RJ_2022_t1.xlsx` — Dep. Estadual, RJ | 46.422 (0,537% dos válidos) | 4.813 | 1.184 | 350 |
| `planilha_22222_RJ_2024_t1_rio_de_janeiro.xlsx` — Vereador, Rio | 130.480 (4,298%) | 1.438 | 250 | 75 |

### (c) Viabilidade dos mapas

A resposta é sim; o detalhamento está em [viabilidade_georreferenciamento_locais.md](viabilidade_georreferenciamento_locais.md). Entre 99,9% e 100% dos locais do RJ têm coordenada nos cadastros de 2022, 2024 e 2026. Nenhuma cai fora do estado, a precisão é de 6–7 casas decimais, e 96% dos locais estão no mesmo ponto em 2024 e 2026.

## Arquivos

- **Novos:**
  - `apuracao/__init__.py`;
  - `apuracao/eleitorado.py`: cadastro por seção e por local, proveniência de ZIP local, `compact()`, haversine, relatório de coordenadas;
  - `apuracao/locais.py`: comparação por seção e por local, inconsistências, conferência TRE;
  - `apuracao/planilha.py`: `build_report` (sem I/O) e `write_workbook`;
  - `ingerir_eleitorado.py`, `planilha_candidato.py`;
  - `conftest.py`, `test_eleitorado_locais.py`, `test_planilha_candidato.py`;
  - `requirements.txt`;
  - `docs/viabilidade_georreferenciamento_locais.md` e este documento.
- **Alterados:**
  - `votos_por_local_votacao.py`: colunas do layout de 2026 em `ELECTORATE_WANTED`/`INT_COLUMNS`; `candidate_name` recebe o município (bug abaixo);
  - `CLAUDE.md`;
  - `docs/INDEX.md`.
- **Dependências instaladas no venv:** `xlsxwriter` 3.2.9 e `openpyxl` 3.1.5.

## Decisões e achados

1. **Reaproveitar sem mover.** O pacote `apuracao/` importa as funções de `votos_por_local_votacao.py` em vez de movê-las. Isso evitou uma refatoração que atrasaria (b). A migração fica para quando (d)/(e) exigirem.
2. **Bug corrigido: nome errado de candidato em eleição municipal.** O número de vereador/prefeito só é único dentro do município, e `candidate_name` pegava o primeiro nome da UF. O 22222 do Rio saía como "SHEILA DE CARVALHO SABENÇA", ou outro nome dependendo da execução, em vez de CARLOS NANTES BOLSONARO. Os votos estavam certos, porque o filtro por município já era aplicado. Agora o nome é buscado no município e, sem `--municipio`, o número ambíguo gera erro claro. A correção vale também para os subcomandos antigos.
3. **Comparação de textos só por letras e dígitos (`compact`).** Sem isso, "AV. X, 80" e "AV X 80" contavam como mudança. A correção eliminou cerca de 200 falsos `ENDERECO_ALTERADO`.
4. **Formato da lista do TRE.** A lista não tem o nº do local e junta num único item os locais de mesmo nome na mesma zona (mesmo prédio, números diferentes), além de repetir itens. Ela também inclui as seções agregadas. Agrupando os dois lados por (município, zona, nome) e comparando todas as seções, as divergências caíram de 611 para 21 reais.
5. **Contagem de locais:** a contagem certa é por município+zona+nº. O número inicial do plano (4.974) não incluía o município na chave; o correto são 5.062 em 2026.
6. **Local BLOQUEADO não é mudança.** É situação cadastral (2.198 seções em 2026) e aparece em `SITUACAO_LOCAL_2026`, sem destaque. Isso desvia do plano, que previa marcá-lo.
7. **Formato dos cadastros por ano.** 2024 vem em CSV nacional com ponto decimal; 2026, em CSV por UF com vírgula decimal. A conversão existente trata os dois; o turno 2 é ignorado no cadastro.
8. **Bug do Polars 1.44.** `pl.format` sobre o resultado de um full join não consolidado dispara panic. Os joins `how="full"` passaram a terminar em `.rechunk()`.

## Verificação

- `pytest -q`: **19 testes passando** (7 antigos e 12 novos), offline, com ZIPs sintéticos no layout real, cabeçalho de 2026 copiado do arquivo do TSE. O cenário está descrito no topo de `conftest.py`. Os testes cobrem:
  - local mantido, renomeado/deslocado, desativado e novo;
  - seção que troca de local e seção remanejada;
  - seção agregada contando no eleitorado;
  - bairro com grafias diferentes;
  - coordenada -1;
  - linha de 2º turno ignorada;
  - número de candidato ambíguo entre municípios;
  - resultado de ano sem cadastro próprio;
  - totais iguais nas quatro abas;
  - regras de destaque.
- **Dados reais:** a planilha de 2022 bate com o `por-local` do script antigo (46.422 votos, 4.813 locais) e os totais das quatro abas coincidem.

## Pendências

- **(d)** cliente de `resultados.tse.jus.br` 2026 com snapshots (Anexo I, bloco A6). Os códigos de cargo além de 0001/0003/0005 ainda precisam ser confirmados. Convém testar no simulado antes do 1º turno (4/10).
- **(e)** site local com dashboard, consulta por candidato e mapas.
- Instalar `geobr` para mapas por município e por setor censitário.
- Revisar manualmente os 14 saltos de coordenada acima de 5 km e os 6 locais sem coordenada em 2026.
- `LOCAL_2026_AUSENTE_NA_LISTA_TRE` pode ser só diferença de grafia; ainda não há casamento aproximado de nomes.
