# Rodada 17 — Abstenção e comparecimento por bairro

30/09/2026 · pedido do usuário: "Adicione abstenção e comparecimento por bairro"

## Objetivo

Mostrar abstenção e comparecimento por bairro do IBGE:
- na aba **Mapas**, modo Bairros;
- na aba **Comparação**, modo Bairros, entre quaisquer dois anos e cargos.

## Fonte dos dados

O `votacao_secao`, usado até aqui, **não tem** aptos nem comparecimento: só os votos de cada votável. Os dois vêm de outro arquivo do TSE, o **`detalhe_votacao_secao_<ano>.zip`** (CDN, pasta `detalhe_votacao_secao`), com uma linha por seção e cargo: `QT_APTOS`, `QT_COMPARECIMENTO` e `QT_ABSTENCOES`.

| Ano | ZIP | CSVs | Observação |
|---|---|---|---|
| 2022 | 244 MB | um por UF + `_BRASIL` | o `_RJ` **não tem Presidente** (nem o 2º turno dele); o `_BRASIL` tem todos os cargos e turnos |
| 2024 | 87 MB | um por UF + `_BRASIL` | traz também a suplementar de Três Rios (ver abaixo) |
| 2026 | 404 hoje | — | publicado junto com os votos, dias depois do pleito |

Por isso o `section_details_spec` lê o CSV **`_BRASIL`**, filtrado pela UF. Isso usa o novo campo `DatasetSpec.member`, o sufixo preferido pelo `pick_csv_member`.

**Conferência:** a soma por município de aptos e abstenções do detalhe por seção (Governador 2022, 1º turno) **bate exatamente** com o `detalhe_votacao_munzona` oficial nos **92 municípios**: 12.809.126 aptos e 2.915.468 abstenções.

## Defeito encontrado: eleição suplementar no mesmo arquivo

- **Problema:** `votacao_secao_2024_RJ` e `detalhe_votacao_secao_2024` trazem, além das eleições municipais de 2024, a **eleição suplementar de Três Rios de 05/10/2025** (`CD_TIPO_ELEICAO` = 1). Ela vem como "turno 1", nas mesmas seções.
- **Efeito:** tudo que lia 2024 somava as duas eleições. Os votos para prefeito de Três Rios no 1º turno davam **93.001** em vez de **49.623**, o que afetava a planilha, o `por-local` e os bairros.
- **Correção** (`zip_to_parquet`): quando o CSV tem `CD_TIPO_ELEICAO`, só a eleição **ordinária** (`2`) é mantida. A constante é `ORDINARY_ELECTION`.
- **Cache:** o Parquet antigo `cache_tse/votacao_secao_2024_RJ__RJ.parquet` foi apagado e reconvertido. Os de 2022 só têm a eleição ordinária e não mudam.
- **Cadastros de eleitorado:** não têm a coluna e não mudam.

## Entregas

- **Núcleo** (`votos_por_local_votacao.py`):
  - `SECTION_DETAILS_REQUIRED`/`OPTIONAL`, `section_details_spec` e `load_section_details`;
  - `DatasetSpec.member`, `pick_csv_member(..., preferred)` e o filtro da eleição ordinária.
- **Domínio** (`apuracao/bairros.py`):
  - `participacao_por_bairro`, que filtra turno e **código do cargo** e soma por local e depois por bairro;
  - `metrica_participacao`, com VALOR = % dos aptos e NUM/DEN para o total da área;
  - `Bairros.participacao`, com cache em memória e a mesma memória de falha de 10 min dos votos, agora em `_carregar`. Um cargo sem linhas naquele ano ou turno gera `TseDataError` (HTTP 404).
  - **Métricas novas:** `abstencao_pct` e `comparecimento_pct` no mapa; `abstencao` e `comparecimento`, em p.p., na comparação.
- **API:** `/api/mapa/bairros` e `/api/comparacao/bairros` aceitam as métricas novas, e o `/api/bairros/anos` passa a listá-las.
- **Página:** as opções Abstenção e Comparecimento ficam ativas nos dois modos Bairros. Brancos (%), Nulos (%) e Seções totalizadas continuam desativadas.

## Números reais (RJ, área dos bairros)

- **Abstenção, Governador 2022 (1º turno):** 22,92% (919 bairros), de 7,4% a 36,7%.
- **Presidente 2022:** 22,90% no 1º turno e 22,28% no 2º turno, que só existe no CSV `_BRASIL`. Os extremos do 2º turno vão de 7,9% em São Vicente (Barra Mansa) a 34,2% em São Bernardo (Belford Roxo).
- **Prefeito/Vereador 2024:** 27,41% (936 bairros). No 2º turno de prefeito, 29,32% (40 bairros).
- **Comparação Governador 2022 × Prefeito 2024:** **+4,49 p.p.** Maior aumento na capital e na Baixada, conferido na tela.
  http://127.0.0.1:8000/#comparacao?detalhe=bairros&ano_a=2022&cargo_a=3&ano_b=2024&cargo_b=11&metrica=abstencao

## Testes

**`pytest -q`: 104 testes passando** (eram 99).

**Cenário sintético** (`conftest.py`):
- `detalhe_votacao_secao_2024.zip` com `_RJ` incompleto de propósito e `_BRASIL` completo, contendo uma linha de suplementar, uma de 2º turno de prefeito e uma de SP;
- uma linha de suplementar de 1.000 votos também no `votacao_secao_2024_RJ` (`VS_HEADER` ganhou `CD_TIPO_ELEICAO`).

**Testes novos ou alterados:**
- **`test_suplementar_no_mesmo_arquivo_e_descartada`:** o candidato tem 29 votos no Rio, não 1.029.
- **`test_abstencao_e_comparecimento_por_bairro`:** bairro A com 920 aptos e 750 comparecimentos; bairro B com 450 aptos e 140 abstenções; o 2º turno vem do `_BRASIL`; cargo inexistente dá erro.
- **`test_comparar_abstencao_e_comparecimento`:** área de 310/1.370 e 1.060/1.370; 2026 sem detalhe dá erro.
- **API:** abstenção por bairro, comparecimento, brancos (400) e cargo sem dado (404).
- **Navegador:** abstenção no mapa por bairro e comparecimento na comparação (77,37%, 0,00 p.p.). Os testes que usavam "abstenção desativada" como exemplo passaram a usar Brancos.

**Testes sem rede:** `download_sem_rede` (`conftest.py`) só serve o que está no cache e responde 404 ao resto. Aplicado aos testes de bairros e ao site dos testes de navegador. Antes, os pedidos de 2026 iam de fato ao TSE e passavam só porque a falha de conexão também vira 404. Com a rede bloqueada por proxy inválido, os 71 testes sem navegador passam.

**Sabotagens** (arquivos restaurados byte a byte):
- sem o filtro de suplementar: 8 testes falham, inclusive 2 da planilha, que também somavam a suplementar;
- sem as métricas no JS: falham os testes de navegador correspondentes (abstenção no mapa; comparecimento na comparação).

**Servidores** reiniciados nas portas 8000, 8022 e 8023; as rotas foram conferidas com os dados reais.

## Arquivos

- **Alterados:**
  - `votos_por_local_votacao.py`, `apuracao/bairros.py`, `apuracao/web/app.py` e `apuracao/web/static/app.js`;
  - `conftest.py`, `test_exportar_bairros.py` e `test_exportar_bairros_e2e.py`;
  - `CLAUDE.md` e `docs/INDEX.md`.
- **Cache novo:**
  - `cache_tse/detalhe_votacao_secao_{2022,2024}.zip`, com `.proveniencia.json`;
  - `cache_tse/detalhe_votacao_secao_{2022,2024}__RJ.parquet`.

## Pendências

- 2026 por bairro, com votos e participação, depende da publicação do `votacao_secao_2026_RJ` e do `detalhe_votacao_secao_2026`.
- Brancos e nulos separados por bairro: feito na rodada 18. A hora da apuração por bairro foi descartada pelo usuário.
- Outros arquivos do TSE podem ter a mesma mistura de eleição suplementar. O filtro vale para qualquer CSV com `CD_TIPO_ELEICAO`, mas os Parquet convertidos antes desta rodada só se corrigem se forem apagados. Hoje só o de votação de 2024 do RJ estava afetado.
