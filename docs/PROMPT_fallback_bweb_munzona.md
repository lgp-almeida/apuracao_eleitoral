# Prompt para o Claude Code — Fallback BU (bweb) → munzona

> Comece em **modo plano** (`/plan`). Não escreva código antes de eu aprovar o plano.
> Leia antes: `CLAUDE.md`, `docs/RODADA_40_2026-10-06_totais_sem_munzona.md`, `apuracao/microdados.py`,
> `apuracao/historico.py` (`detalhe_de_secoes`, `destinacao_oficial`, `destino_legenda`, `importar`,
> `conferir_totais`, `load_votos_munzona`), `apuracao/cadeiras.py` (`entrada_munzona`),
> `apuracao/web/app.py` (`falhas_munzona`), `preparar_2026.py`, `apuracao/lote_ufs.py` e
> `harmonizacao_resultados_tse_multiano.md`.

---

## 1. Contexto

Em 07/10/2026, três dias após o 1º turno de 04/10, o TSE ainda não publicou:

- `detalhe_votacao_munzona_2026.zip` → 404
- `votacao_partido_munzona_2026.zip` → 404
- o dataset `resultados-2026` → não existe no CKAN

Os dois arquivos existem em todos os ciclos, sempre com a mesma URL na CDN. Os prazos de publicação foram:

| Ano | Eleição | Criação do dataset `resultados-<ano>` | Atraso |
|---|---|---|---|
| 2022 | 02/10 | 06/10 (recurso `detalhe_munzona` em 07/10) | 4 a 5 dias |
| 2024 | 06/10 | 09/10 | 3 dias |

Não há prazo normativo para esses arquivos. A publicação é uma convenção do portal.

Já publicados para 2026:

- `votacao_secao` (UF e BR)
- `detalhe_votacao_secao`
- `consulta_cand`
- `votacao_candidato_munzona`
- `perfil_eleitor_secao`
- datasets `resultados-2026-boletim-de-urna`, `resultados-2026-correspondencias-esperadas-e-efetivadas-1-turno` e logs Gedai

O BU tem nome com timestamp, por exemplo
`cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_1t_RJ_051020261403.zip`, mais o `.sha512`.

**Situação no código:**

- **Totais:** `fonte_dos_totais` já escolhe entre `"munzona"` (oficial) e `"secoes"` (reconstruído, provisório).
- **Votos por partido** (`partido_munzona`): **não há fallback**. `cadeiras.py` cai na divulgação JSON, e `app.py` guarda as falhas em `falhas_munzona`.

## 2. Objetivo

1. **Terceiro nível para os totais.** Acrescentar o nível `"bweb"` para quando nem o oficial nem `"secoes"` estiverem disponíveis. Isso cobre:
   - o 2º turno de 25/10;
   - UFs cujo `votacao_secao` não foi baixado;
   - qualquer janela em que o BU sai antes dos microdados por seção.
2. **Fallback do `votacao_partido_munzona`.** Montar uma reconstrução por município × zona × partido, com a mesma hierarquia de fontes.
3. **Regra única de decisão** (seção 4), com proveniência explícita e troca automática pelo oficial quando ele sair.

## 3. Princípios (não negociáveis)

- **Não reimplementar a classificação dos votos.** O adaptador bweb só **traduz o BU para os mesmos dados intermediários** que a fonte `"secoes"` já consome:
  - votos por seção no esquema do `votacao_secao`;
  - detalhe por seção no esquema do `detalhe_votacao_secao`.

  A partir daí `detalhe_de_secoes`, `destinacao_oficial` e `destino_legenda` rodam sem alteração. Assim a regra da rodada 40 (95/96/97, legenda com e sem candidato, sub judice, nulo técnico) fica em um único lugar.
- **Hierarquia estrita e sem rebaixamento.** A ordem é `munzona` > `secoes` > `bweb` > `None`. Um nível superior já importado nunca é trocado por um inferior.
- **Publicado = CSV com pelo menos uma linha de dados.** Responder 200 não basta: a CDN já serviu ZIPs só com cabeçalho, de 671 bytes. Um 404 e um arquivo só com cabeçalho contam igualmente como "não publicado".
- **Estado vem do disco** (`microdados.no_cache`), nunca da memória do processo, como na rodada 40.
- **Nenhum nome de BU fixado no código.** Descoberta via CKAN:
  - `package_show?id=resultados-<ano>-boletim-de-urna`;
  - filtrar `resources[].url` por `bweb_<turno>t_<UF>_*.zip`;
  - em caso de mais de um, escolher o de maior timestamp.

  Validar o SHA-512 contra o `.sha512` antes de usar.
- **Testes sem rede**, com dados sintéticos primeiro e o golden de 2022 depois.
- **Seguir as convenções do repositório:**
  - nomes em português;
  - Polars;
  - troca atômica de arquivos;
  - `*.proveniencia.json`;
  - documento `docs/RODADA_<n>_...md`;
  - atualizar `CLAUDE.md` e `TODO.md`.

## 4. Regra de decisão do fallback

Avaliar por **(ano, UF, turno)** e por **artefato**, separadamente para `totais` e `partido`.

```
publicado(x) := x no cache E CSV da UF com ≥ 1 linha de dados (SHA-512 conferido no caso do BU)

fonte_dos_totais(ano, uf, turno):
    se publicado(detalhe_munzona) e BASE_IMPORTAR ⊆ cache                          → "munzona"
    senão se BASE_IMPORTAR ∪ {detalhe_secao, candidato_munzona} ⊆ cache             → "secoes"
    senão se publicado(bweb_<turno>t_<UF>) e {candidatos} ⊆ cache                   → "bweb"
    senão                                                                           → None

fonte_dos_partidos(ano, uf, turno):
    se publicado(partido_munzona)                                                   → "munzona"
    senão se publicado(candidato_munzona) e votos_por_secao(uf) disponíveis         → "secoes"
    senão se publicado(candidato_munzona) e publicado(bweb UF)                      → "bweb"
    senão                                                                           → None  (cadeiras continuam na divulgação JSON)
```

Regras complementares:

- **Destinação ausente no nível `"bweb"`.** Se `candidato_munzona` não estiver no cache, a destinação vem do `consulta_cand`, como já faz `_destinacao_ou_nada`. Registrar aviso no `status.json`. Nesse caso os partidos ficam `None`.
- **Presidente, abrangência BR, no nível `"bweb"`.** Exige os 27 BUs de UF mais o `ZZ`. Se faltar algum:
  - gerar só as abrangências UF e município;
  - registrar aviso;
  - não baixar o Brasil inteiro sem a flag explícita `--bweb-brasil`.
- **Quando reimportar:** sempre que o nível subir, ou o `Last-Modified` / SHA de qualquer insumo do nível atual mudar.
- **Ao subir de nível:** rodar `conferir_totais(antes, depois)` e gravar o relatório em `saidas/<UF>/conferencia_<nivel_antigo>_x_<nivel_novo>_<turno>t.csv`.
- **Na transição para `"munzona"`**, apagar os Parquet derivados do nível anterior.
- **Configuração** (CLI do `preparar_2026.py` e do lote):
  - `--politica-totais {auto,oficial,secoes,bweb}`, padrão `auto`;
  - fora de `auto`, a política fixa o nível e falha se ele não estiver disponível; nunca cai silenciosamente para outro.

**Efeito em `FINAL` e no lote:**

- `FINAL` não muda: o vigia só encerra com `detalhe_munzona` e `partido_munzona` oficiais.
- `"bweb"` e `"secoes"` → `AGUARDANDO`.
- `status.json`:
  - `totais_de` passa a aceitar `"bweb"`;
  - incluir `partidos_de` com o mesmo domínio;
  - `ambiente` com o sufixo `· totais provisórios (BU)`;
  - `DESCRICAO_TOTAIS["bweb"]` = `"reconstruídos do Boletim de Urna (provisório, até o TSE publicar os microdados)"`.

## 5. Especificação do adaptador `bweb`

Criar o módulo `apuracao/bweb.py`, sem I/O de rede nas funções de transformação.

```python
def descobrir(ano: int, turno: int, uf: str, sessao) -> RecursoBU | None   # CKAN + escolha do timestamp
def baixar(recurso: RecursoBU, cache: Path, sessao) -> Path                  # troca atômica + SHA-512 + proveniência
def ler(zp: Path, uf: str) -> pl.LazyFrame                                   # CSV bruto, latin-1, ';', sentinelas → null
def votos_por_secao(bu: pl.LazyFrame) -> pl.LazyFrame        # MESMO esquema que load_votos devolve hoje
def detalhe_por_secao(bu: pl.LazyFrame) -> pl.LazyFrame      # MESMO esquema que load_detalhe_secoes consome
def partidos_munzona(votos_secao: pl.LazyFrame, cand_munzona: pl.LazyFrame,
                     candidatos: pl.LazyFrame, uf: str, turno: int) -> pl.DataFrame
```

`partidos_munzona` serve às duas fontes, `"secoes"` e `"bweb"`. Por isso o melhor lugar para ela é `historico.py`, e não `bweb.py`. Decidir no plano.

### 5.1 Leitura do BU

- **Cabeçalho:** conferir as colunas contra o **cabeçalho real** do arquivo de 2026 já no cache, e o de 2022 para o golden. **Não confiar em listas de memória.** As colunas esperadas, a confirmar:
  `ANO_ELEICAO, NR_TURNO, CD_ELEICAO, SG_UF, CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, NR_SECAO, NR_LOCAL_VOTACAO, CD_CARGO_PERGUNTA, DS_CARGO_PERGUNTA, NR_PARTIDO, SG_PARTIDO, QT_APTOS, QT_COMPARECIMENTO, QT_ABSTENCOES, CD_TIPO_URNA, DS_TIPO_URNA, CD_TIPO_VOTAVEL, DS_TIPO_VOTAVEL, NR_VOTAVEL, NM_VOTAVEL, QT_VOTOS, DS_AGREGADAS, DT_BU_RECEBIDO, DT_EMISSAO_BU, NR_JUNTA_APURADORA, NR_TURMA_APURADORA`.
- **Formato:** `latin-1`, separador `;`, aspas.
- **Sentinelas → null:** `#NULO#`, `#NE#`, `-1`, `-3`. Confirmar quais aparecem de fato.
- **Renomeações:** `CD_CARGO_PERGUNTA` → `CD_CARGO`, e as demais necessárias para casar com o esquema de `votacao_secao`. Documentar o mapeamento em uma tabela no módulo.
- **Códigos de `CD_TIPO_VOTAVEL`:** derivar da tabela distinta `CD_TIPO_VOTAVEL × DS_TIPO_VOTAVEL` do próprio arquivo, sem fixar valores. Normalizar para a convenção de `NR_VOTAVEL` do `votacao_secao` (95 branco, 96 nulo, 97 anulado em apuração separada, < 100 legenda). Se o BU representar brancos e nulos de outro jeito, converter aqui.

### 5.2 Armadilhas obrigatórias

1. **`QT_APTOS`, `QT_COMPARECIMENTO` e `QT_ABSTENCOES` se repetem em cada linha** de votável da mesma seção × cargo.
   - Deduplicar por `(SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO, CD_CARGO)` antes de somar.
   - Afirmar que o valor é constante dentro do grupo; se não for, lançar erro e não somar.
2. **Seções agregadas (`DS_AGREGADAS`):** os aptos das agregadas já estão no BU da principal.
   - Não somar duas vezes.
   - Derivar `QT_SECOES_AGREGADAS` contando os itens de `DS_AGREGADAS`.
   - Isso pode corrigir a diferença conhecida de `SECOES_TOTAL` da rodada 40, que vem de o detalhe por seção listar só as principais. Medir.
3. **Unicidade:** a chave `(SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO, CD_CARGO, NR_VOTAVEL)` deve ser única. Se houver BU duplicado, por exemplo de urna substituída, manter um só pelo critério que o golden de 2022 indicar e registrar a contagem.
4. **`CD_TIPO_URNA`:** urna normal, contingência e apuração/SA entram todas. Reportar a contagem por tipo no relatório da rodada.
5. **Presidente:**
   - o BU de cada UF traz Presidente da UF;
   - o `ZZ` traz o exterior;
   - replicar exatamente o que a fonte `"secoes"` faz hoje com `votacao_secao_<ano>_BR`.
6. **Seções sem BU** (não instaladas) não aparecem no BU.
   - Opcional: usar o dataset `correspondencias-esperadas-e-efetivadas` para preencher `QT_SECOES_NAO_INSTALADAS` e um indicador de completude.
   - Sem ele, deixar a coluna nula e registrar aviso.
7. **Data de totalização:** o análogo é `max(DT_BU_RECEBIDO)`, convertido para data antes do máximo, pelo mesmo motivo da rodada 40.

### 5.3 Reconstrução do `votacao_partido_munzona`

Esquema de saída igual ao **cabeçalho real** de `cache_tse/votacao_partido_munzona_2022.zip`.

- **Colunas mínimas obrigatórias** são as que os consumidores leem:
  - `cadeiras.entrada_munzona`: `CD_TIPO_ELEICAO, NR_TURNO, CD_CARGO, SG_PARTIDO, NR_FEDERACAO, SG_FEDERACAO, QT_TOTAL_VOTOS_LEG_VALIDOS, QT_VOTOS_NOMINAIS_VALIDOS`;
  - `historico.load_votos_munzona`: as colunas `_LEGENDA`.
- **Colunas não deriváveis** ficam nulas, nunca com 0.

Regras:

- **Nominais:** agregar o `votacao_candidato_munzona` por município × zona × cargo × partido. Não usar seções.
  - Fontes: `QT_VOTOS_NOMINAIS_VALIDOS` e as colunas de anulados e sub judice correspondentes.
  - Convertidos em legenda: `QT_VOTOS_NOM_CONVR_LEG_VALIDOS`, pela destinação.
  - Confirmar no golden de 2022 que essa agregação reproduz exatamente as colunas nominais do arquivo oficial.
- **Legenda:**
  - Fonte: votos com `NR_VOTAVEL` < 100 em cargos proporcionais, vindos dos votos por seção (fonte `"secoes"` ou `"bweb"`) somados por zona.
  - Classificação: `destino_legenda` da rodada 48 (válida, anulada, sub judice ou nulo técnico).
  - `QT_TOTAL_VOTOS_LEG_VALIDOS` = legenda válida + nominais convertidos em legenda.
- **Federação/coligação:** do `candidato_munzona`, com o `consulta_cand` como reserva; usar `normalizar_federacao`.
- **Cargos majoritários:** sem votos de legenda. Conferir no 2022 se o oficial traz linhas para eles e reproduzir o mesmo comportamento.

**Integração:**

- `cadeiras.py` passa a usar `fonte_dos_partidos`:
  - com `"munzona"`, `"secoes"` ou `"bweb"` → microdados, marcando o rótulo como provisório nos dois últimos;
  - com `None` → divulgação JSON, como hoje.
- `falhas_munzona` em `app.py` deixa de ser o único caminho.

## 6. Validação e testes

1. **Sintéticos** (`tests/test_bweb.py`, pytest, sem rede). Um BU mínimo com:
   - duas zonas, seção agregada e aptos repetidos;
   - votáveis 95/96/97;
   - legenda de partido com e sem candidato;
   - candidato sub judice e candidato fora do `candidato_munzona`;
   - urna de contingência, BU duplicado e linha do `ZZ`.

   O que verificar:
   - `votos_por_secao` e `detalhe_por_secao` com esquema e dtypes **idênticos** aos das loaders atuais (teste de contrato);
   - totais e partidos esperados calculados à mão.
2. **Regra de decisão:** tabela de casos para `fonte_dos_totais` e `fonte_dos_partidos`, cobrindo:
   - 404;
   - só cabeçalho;
   - SHA divergente;
   - presença de cada combinação de insumos;
   - não rebaixar;
   - política fixa indisponível → erro.
3. **Golden 2022, RJ, 1º e 2º turnos** (marcado `@pytest.mark.dados`, roda só com cache local):
   - **Totais:** `bweb → detalhe_de_secoes` × `detalhe_votacao_munzona_2022` oficial, nas mesmas categorias da rodada 40. Meta: **diferença 0** por zona × cargo.
   - **Partidos:** `partidos_munzona` (fontes `"secoes"` e `"bweb"`) × `votacao_partido_munzona_2022` oficial. Meta: diferença 0 nas colunas consumidas.
   - **Outras diferenças:** qualquer diferença fora de `SECOES_TOTAL` e `DT_TOTALIZACAO` tem de ser explicada no documento da rodada, ou é defeito.
4. **Conferência real 2026:** com os dois disponíveis no cache, rodar `bweb` × `secoes` para o RJ no 1º turno e relatar as diferenças. É diagnóstico, não teste bloqueante.
5. **Nenhuma regressão** nos testes existentes.

## 7. Fora do escopo

- O coletor em tempo real e a divulgação JSON.
- Alterar as regras de classificação de `detalhe_de_secoes` e `destino_legenda`.
- Usar o BU quando `"secoes"` estiver disponível. Ele só vale como diagnóstico, item 6.4.
- Baixar os BUs de todas as UFs por padrão.

## 8. Entregáveis

- `apuracao/bweb.py`, `partidos_munzona`, mudanças em `microdados.py`, `historico.py`, `cadeiras.py`, `preparar_2026.py` e `lote_ufs.py`.
- Testes do item 6.
- `docs/RODADA_<n>_<data>_fallback_bweb_e_partidos.md` com:
  - a regra de decisão;
  - o mapeamento de colunas bweb → `votacao_secao` / `detalhe_votacao_secao`;
  - os resultados do golden 2022 e da conferência 2026.
- `CLAUDE.md` e `TODO.md` atualizados.
- Execução real **só no RJ**. Confirmar comigo antes de rodar outras UFs.
