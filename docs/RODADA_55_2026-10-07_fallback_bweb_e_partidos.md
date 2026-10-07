# Rodada 55 — Boletim de Urna como terceira fonte dos totais e votos por partido reconstruídos

07/10/2026 · pedido em [PROMPT_fallback_bweb_munzona.md](PROMPT_fallback_bweb_munzona.md). O TSE ainda não
publicou o `detalhe_votacao_munzona_2026` nem o `votacao_partido_munzona_2026` (404). Dois fallbacks:
- um terceiro nível de totais, `bweb` (Boletim de Urna);
- a reconstrução do `votacao_partido_munzona`, para as cadeiras.

Os dois têm troca automática pelo oficial quando ele sair.

## Quando o BU ajuda (datas medidas no CKAN)

| Eleição | BU | `votacao_secao` / `detalhe_votacao_secao` | munzona |
|---|---|---|---|
| 2022, 1º turno (02/10) | 05/10 | 06/10 – 07/10 | 07/10 |
| 2022, 2º turno (30/10) | **01/11** | **05/11** (atualização dos arquivos do ano) | 05/11 |
| 2024, 1º turno (06/10) | 09/10 23:28 | 09/10 22:03 | 09/10 22:01 |
| 2026, 1º turno (04/10) | 06/10 18:38 | **06/10 04:57** (antes do BU) | ainda 404 |

- **O ganho está no 2º turno:** 4 dias antes dos microdados em 2022. No 1º turno de 2026, as seções saíram antes.
- **Correções ao documento do pedido:**
  - o `harmonizacao_resultados_tse_multiano.md` não existe no repositório;
  - o dataset `resultados-2026` já existe no CKAN, mas só com PDFs (`Relatorio_Resultado_Totalizacao_*`), que não
    servem de fonte;
  - o cabeçalho do BU não é o da lista do documento (ver a tabela abaixo).

## Regra de decisão (por ano, UF e turno)

```
munzona  detalhe_votacao_munzona com linhas DO TURNO (CSV _BRASIL) + votos + consulta_cand
secoes   votacao_secao (UF ∪ BR) e detalhe_votacao_secao com linhas DO TURNO + consulta_cand + candidato_munzona
bweb     BU do turno no cache com SHA-512 conferido e dados + consulta_cand
None     nada disso
```

- **"Com linhas do turno":** antes, o `votacao_secao` com o 1º turno fazia o 2º parecer disponível.
  `md.turnos(cache, ano, uf, chave)` olha o Parquet convertido.
- **Ordem:** `munzona` > `secoes` > `bweb` > `None` (`md.ORDEM`).
- **`preparar_2026.atualizar`:** importa um turno quando o nível disponível é melhor que o importado, ou quando é o
  mesmo e um insumo dele mudou (o BU novo entra como `md.BWEB`). Nunca rebaixa.
- **`--politica-totais {auto,oficial,secoes,bweb}`:** fora de `auto`, fixa o nível. Se ele não estiver disponível,
  dá `PoliticaIndisponivel` e não importa nada.
- **Ao trocar de nível:** grava `saidas/<UF>/conferencia_<antigo>_x_<novo>_<t>t.csv`. Quando o BU deixa de ser a
  fonte, os Parquet dele saem.
- **Partidos** (`md.fonte_dos_partidos`, `status.json:partidos_de`):
  - o `votacao_partido_munzona` oficial;
  - senão, o candidato_munzona + a legenda das seções (`secoes`) ou do BU (`bweb`);
  - senão `None` (a divulgação).
- **Inalterados:** o `FINAL` (o vigia só encerra com o detalhe e o partido munzona oficiais). No lote, `bweb` fica
  em AGUARDANDO, como `secoes`.
- **Busca do BU** (`preparar_2026.procurar_bu`): só nos turnos sem nada melhor (ou com a política `bweb`). É uma
  consulta ao CKAN por verificação (no lote, uma por execução, `Lote._lista_bu`).
- **`--bweb-brasil`:** baixa os 27 BUs + o exterior (Presidente no Brasil). Sem ele, a abrangência Brasil sai, com
  aviso no `status.json`, porque o BU da UF não dá o total do país.

## Mapeamento BU → `votacao_secao` / `detalhe_votacao_secao` (`apuracao/bweb.py`)

Os cabeçalhos reais de 2022 e 2026 foram conferidos: 45 colunas.

| BU | Destino |
|---|---|
| `CD_CARGO_PERGUNTA` / `DS_CARGO_PERGUNTA` | `CD_CARGO` / `DS_CARGO` (maiúsculas) |
| `DS_TIPO_VOTAVEL` + `NR_VOTAVEL` | Nominal e Legenda ficam com o próprio número; Branco = 95, Nulo = 96 (já vêm assim). Tipo desconhecido → erro |
| `DS_AGREGADAS` (2022) / `DS_SECOES_AGREGADAS` (2026), `"58 / 89 / 91"` | `QT_SECOES_AGREGADAS` |
| `DT_BU_RECEBIDO` (2022 `dd/mm/aaaa hh:mm:ss`; 2026 `aaaa-mm-dd hh:mm:ss`) | `DT_PRIM_TOT_PARCIAL_HOR_TSE` |
| `QT_APTOS` / `QT_COMPARECIMENTO` / `QT_ABSTENCOES` | uma vez por seção × cargo |
| `CD_TIPO_ELEICAO` 0 / `NM_TIPO_ELEICAO` "Eleição Ordinária" | filtro pelo nome |
| `CD_ELEICAO` | reserva do código quando a destinação do turno falta |

- **Aptos repetidos:** no BU eles aparecem em cada votável. Valor que varie dentro de seção × cargo → erro, nunca
  soma.
- **Tipo da eleição ordinária:** no `votacao_secao` o código é `2`. Para o BU não ser filtrado, o
  `zip_to_parquet` do núcleo ganhou `tipo_ordinario=None`; o padrão não mudou.
- **Sentinelas:** `#NULO#` e `-1`.
- **Leitura recusada:** BU com votável repetido na mesma seção × cargo (`bweb.verificar`).
- **Classificação:** nenhuma regra nova. O BU vira os mesmos intermediários da fonte `secoes`, e
  `detalhe_de_secoes`/`destino_legenda` não mudaram, exceto num ponto: `detalhe_de_secoes` soma
  `QT_SECOES_AGREGADAS` quando a coluna existe, e só o BU a traz.

**Contagens do BU:**

| BU | Seções | Tipo de urna | Com agregadas | Duplicadas |
|---|---|---|---|---|
| RJ 2022, 1º turno | 34.068 | todas "APURADA" | 2.264 (2.482 agregadas por cargo) | 0 |
| RJ 2022, 2º turno | 34.068 | todas "APURADA" | 2.264 (2.482 agregadas por cargo) | 0 |
| RJ 2026, 1º turno | 37.675 | todas "Apurada" | 1.007 | 0 |

Tamanho do BU do RJ em 2026: 536 MB, com 3,3 GB descomprimidos.

## `votacao_partido_munzona` reconstruído (`historico.partidos_munzona`)

- **Nominais:** do `votacao_candidato_munzona`, por zona, pela destinação do candidato:
  - "Válido (legenda)" → convertidos;
  - outra "Válido*" → nominais válidos;
  - "Anulado sub judice" → sub judice;
  - outra "Anulado*" → anulados.
- **Legenda:** votável < 100 nos proporcionais, pela agremiação (`destino_legenda`). O nulo técnico não é do
  partido.
- **Atributos** (federação, coligação, nomes): copiados do candidato_munzona, no formato dele.
- **`ST_VOTO_EM_TRANSITO`:** nulo, porque a legenda por seção não se separa por trânsito. No RJ de 2022 só há "N".
- **Gravação:** `ultimo/partidos_munzona.parquet` na pasta importada.
- **Cadeiras:** `cadeiras.entrada_munzona(..., partidos=)` usa o reconstruído no lugar do ZIP oficial, que nem é
  pedido. Na rota (`app.distribuicao`), com `partidos_de` `secoes`/`bweb`, a fonte aparece como "microdados do TSE
  (…; votos por partido reconstruídos …)".

## Resultados

**Golden de 2022 no RJ:**

| Conferência | Resultado |
|---|---|
| Totais BU → `detalhe_de_secoes` × `detalhe_votacao_munzona` oficial, 1º turno | **0 diferenças** nas 915 zonas × cargo, em 13 colunas (aptos, comparecimento, abstenções, **seções totais**, votos, válidos, nominais, legenda, brancos, nulos, nulos técnicos, anulados, sub judice) |
| O mesmo, 2º turno | **0 diferenças** nas 183 zonas × cargo, nas mesmas colunas |
| `partidos_munzona` (fontes `secoes` e `bweb`) × `votacao_partido_munzona` oficial | as **16.836 linhas** (zona × cargo × partido, Presidente incluído), **0 diferenças** nas 8 colunas QT |
| Importação completa pelo BU × pelos totais oficiais | totais, candidatos e situação iguais nos dois turnos (sem a abrangência Brasil) |
| Cadeiras com os partidos reconstruídos | 46/46 e 70/70 iguais ao oficial; 0 divergências com a situação do TSE |

- **Seções totais:** o `SECOES_TOTAL` sai igual ao oficial. A diferença conhecida da rodada 40 desaparece com o BU.

**Diagnóstico de 2026, RJ, 1º turno (`bweb` × `secoes`; não é teste):**
- **Votos:** totais e candidatos com **votos iguais** em tudo, e `partidos_munzona` igual nas 13.908 linhas.
- **Seções:** a única diferença é o `SECOES_TOTAL`, +1.063 por cargo. São as agregadas, que o BU conta e as seções
  não.
- **Cadeiras com os partidos reconstruídos:** 46 e 70 eleitos, iguais aos da noite, e 0 divergências com o
  candidato_munzona.
- **CLI:** `preparar_2026.py --politica-totais bweb` (numa pasta temporária) importou o 1º turno pelo BU. O site
  abriu essa importação, e as cadeiras saíram com o rótulo dos partidos reconstruídos.

## Arquivos

- **Novos:** `apuracao/bweb.py` e `test_bweb.py`.
- **`apuracao/historico.py`:**
  - `load_votos_bweb`, `load_detalhe_bweb`, `load_candidatos_zona`, `legenda_por_zona`, `partidos_munzona`;
  - `importar(..., brasil=)` e `partidos_de`;
  - `detalhe_de_secoes` com as agregadas e o código da eleição do BU.
- **`apuracao/microdados.py`:**
  - `turnos`, `niveis_disponiveis`, `escolher_nivel`, `fonte_dos_partidos`, `ORDEM`/`POLITICAS`/`BWEB`;
  - `baixar(..., sha512=)`.
- **`preparar_2026.py`:** `atualizar` por turno, `importar(a, nivel, turno)`, `procurar_bu`, `--politica-totais`,
  `--bweb-brasil` e o resumo por turno.
- **Lote:** `apuracao/lote_ufs.py` e `baixar_ufs.py`, com as mesmas opções.
- **Cadeiras:** `apuracao/cadeiras.py` (`entrada_munzona(partidos=)`) e `apuracao/web/app.py` (`distribuicao`,
  `SCHEMAS`).
- **Núcleo:** `votos_por_local_votacao.py` (`zip_to_parquet(tipo_ordinario=)`).
- **`pytest.ini`:** a marca `dados`.
- **Testes ajustados:** `test_microdados.py` e `test_lote_ufs.py` (`importar` por turno; `md.turnos` falso nos ZIPs
  sem `NR_TURNO`; o `--so-verificar` agora faz 1 GET ao CKAN).

## Verificação

- `pytest -q -m "not e2e"`: 392 passados e 1 pulado.
- `pytest -q -m e2e`: 70 passados.
- `pytest -q -m dados`: os 3 goldens passam com o cache local.
- `test_bweb.py` (26 testes):
  - contrato dos esquemas;
  - BU sintético nos layouts de 2022 e de 2026;
  - aptos variando, votável repetido e tipo desconhecido → erro;
  - classificação, abrangência Brasil e importação;
  - partidos à mão e cadeiras sem pedir o oficial;
  - tabela da regra de decisão, sem rebaixamento e política fixa;
  - CKAN com carimbos e fora do ar;
  - SHA-512 divergente e troca de versão;
  - BU só com cabeçalho.

## Pendências

- **Vigias:**
  - a do RJ foi reiniciada com o código novo;
  - **a do lote das outras 26 UFs continua com o código antigo em memória.** Com o novo, ela passaria a procurar
    e importar BUs dessas UFs no 2º turno. Isso fica para confirmação do usuário.
- **2º turno de 2026:** o fallback ainda não rodou com dados reais desse turno. O ensaio dele usa o BU do 2º turno
  de 2022 (RJ 3 MB; os 28 somam 69 MB).
