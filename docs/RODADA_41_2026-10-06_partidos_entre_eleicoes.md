# Rodada 41 — O mesmo partido em eleições diferentes: número × sigla × entidade

06/10/2026 · pedido do usuário: "Faça uma avaliação completa de como a mudança da relação nome do partido ×
número do partido. Exemplo: em 2022 o número 14 correspondia ao partido PTB, em 2026 corresponde ao partido
Missão. O objetivo é encontrar bugs no tratamento do nome e do número nos scripts."

Decisão do usuário (no plano): comparar pela **entidade**:
- **renomeação:** o mesmo partido;
- **fusão/incorporação:** soma os antecessores no ano antigo;
- **número reaproveitado por partido novo:** sem antecessor.

## O que muda entre os anos (cadastros de candidatos do TSE, 2014–2026)

| Nº | 2014 | 2018 | 2022 | 2026 | O que é |
|---|---|---|---|---|---|
| 14 | PTB | PTB | PTB | **MISSÃO** | número reaproveitado; o PTB fundiu-se no PRD (2023) |
| 25 | DEM | DEM | — | **PRD** | PRD = PTB + PATRIOTA; o DEM foi para o UNIÃO (44) |
| 20 | PSC | PSC | PSC | **PODE** | o Podemos incorporou o PSC e trocou o 19 pelo 20 |
| 19 | PTN | PODE | PODE | — | Podemos até 2022 |
| 65 | PC do B | PC do B | PC do B | **PCDOB** | mesmo partido; a **sigla** mudou no cadastro |
| 33 | PMN | PMN | PMN | MOBILIZA | renomeação |
| 35 | — | PMB | PMB | DEMOCRATA | renomeação |
| 44 | PRP | PRP | UNIÃO | UNIÃO | número reaproveitado (UNIÃO = DEM + PSL) |
| 51 / 90 | PATRIOTA / PROS | | | — | fundidos no PRD / incorporado ao SOLIDARIEDADE |

**Federação:** o texto muda de formato conforme a fonte.

| Fonte | Texto |
|---|---|
| 2022 e tempo real 2026 | "PT/PC do B/PV" |
| cadastro de 2026 | "13-PT/65-PC do B/43-PV" |

## Defeitos encontrados (reproduzidos com os dados reais do RJ)

| # | Onde | Defeito | Efeito real |
|---|---|---|---|
| D1 | comparação por **bairro** (`bairros.ComparacaoBairros`) | partido ligado pelo **número** | 14 PTB × MISSÃO, 20 PSC × PODE, 33 e 35 apareciam "nos dois anos" e eram comparados; o Podemos de 2022 (19) ficava sem par |
| D2 | transferência 2022 → 2026 (`perfil.transferencias`, `saidas/<UF>/transferencia_2022_2026.csv`) | `int(str(n)[:2])` no mesmo nº de 2022 | latente: candidato do MISSÃO seria correlacionado com o PTB; do PODE, com o PSC (nos 3 primeiros de 2026 no RJ não ocorreu) |
| D3 | Perfil × voto, partido do eixo X/Y ao trocar o ano (`preencherAlvo`) | a página mantinha o **mesmo nº** | 14 MISSÃO virava 14 PTB sem aviso |
| D4 | comparação por **município** (`comparacao.comparar`, `partidos_disponiveis`) | partido ligado pela **sigla exata** | PCdoB virava dois partidos ("PC do B" só 2022, "PCDOB" só 2026); PRD e PODE + PSC sem comparação; partido ausente aparecia com 0% |
| D5 | gráfico de variação (`comparacao.variacao_partidos`, rodada 38) | `.upper()` na sigla | "PC do B" virava "PC DO B", inexistente: o gráfico falhava para siglas com minúscula |
| D6 | histórico importado (`historico.cadastro`) | `AGREMIACAO` = "FEDERAÇÃO" (texto genérico do `NM_COLIGACAO`) | as 5 federações de 2026 com o mesmo nome; o destaque de federação casava todas. As cadeiras não sofriam: usam `FEDERACAO` |
| D7 | histórico de 2026 | `FEDERACAO` = "13-PT/65-PC do B/43-PV" | o mesmo partido com rótulos diferentes conforme a fonte |

Sem defeito: os usos de `numero_partido` **dentro do mesmo ano** (projeção de cadeiras, ensaio, mapa por local,
siglas do ano em `bairros.siglas`).

## Correções

- **`apuracao/partidos.py` (novo, sem I/O):**
  - **`EVENTOS`:** 18 eventos com a primeira eleição geral em que valem e a fonte (renomeações, fusões,
    incorporações).
  - **`NOVOS`:** NOVO, PMB, UP, MISSÃO.
  - **Funções:** `chave` (sigla por `compact`, então "PC do B" = "PCDOB"), `descendente`, `correspondencia`
    (nº novo → nºs antigos), `sem_sucessor`, `rotulo`, `normalizar_federacao`.
  - **`conferir`:** acusa toda troca de nº ou sigla que a tabela não explica.
    **Conferido contra os cadastros reais de 2014, 2018, 2022 e 2026: nenhum aviso.**
- **D1:**
  - `ComparacaoBairros.partidos` lista por entidade: PARTIDO = nº no ano mais recente, `SIGLA_A` = "PTB +
    PATRIOTA";
  - `numeros_do_partido` dá os nºs de cada lado;
  - `comparar` soma os antecessores;
  - sem correspondente, o valor fica **sem dado** em vez de 0%.
- **D2:** `transferencias` usa os antecessores (`Alvo.partido` aceita tupla de nºs; coluna nova `PARTIDO_ANTES`);
  sem antecessor, a linha sai com aviso no log.
- **D3:** a escolha de partido só é mantida ao trocar o ano se o nº **e** a sigla forem os mesmos.
- **D4:**
  - `comparacao.siglas_do_partido` resolve a entidade pela sigla de qualquer dos dois anos;
  - `partidos_disponiveis` passa a ter `SIGLAS_A`/`SIGLAS_B`;
  - `_pct_partido` soma a lista de siglas, e lista vazia dá "sem dado";
  - o rótulo da API diz a composição ("PRD (2026) × PTB + PATRIOTA (2022)").
- **D5:** sem `.upper()`. A sigla é normalizada contra os dados (`_canonica`: "pt" → "PT", "pc do b" →
  "PC do B"); partido sem correspondente dá erro explicando o motivo.
- **D6/D7:** `historico.cadastro` normaliza a federação e usa a própria federação como agremiação quando ela
  concorre sozinha. Histórico reimportado: RJ 2014, 2018, 2022 e 2026 (provisório) e as 27 UFs de 2022.
- **Página:**
  - `rotuloEntidade` mostra "PRD (PTB + PATRIOTA em 2022)" e "PCDOB (PC do B em 2022)" na Comparação e no
    gráfico de variação;
  - na Comparação por bairro: "25 PRD (PTB + PATRIOTA em 2022)".

## Números (RJ, Dep. Federal, 2022 × 2026)

**Por município:**

| Partido | 2022 | 2026 |
|---|---|---|
| PCDOB | PC do B: 125.298 | 195.821 |
| PRD | PTB + PATRIOTA: 268.657 | 66.502 |
| PODE | PODE + PSC: 305.881 | 111.166 |
| SOLIDARIEDADE | SOLIDARIEDADE + PROS: 458.330 | 226.778 |
| MOBILIZA | PMN: 95.910 | 14.561 |
| DEMOCRATA | PMB: 21.964 | 13.657 |
| MISSÃO | sem antecessor | 75.096 |

Variação no estado (% dos válidos): PC do B → PCDOB, de 1,46% para 2,24%; PTB + PATRIOTA → PRD, de 3,13% para
0,76%.

**Por bairro:** PRD: 216.905 → 43.763 votos nos bairros (3,15% → 0,63% dos válidos). O 14 não é mais comparado.

**Outras conferências:**
- cadeiras 2026 (histórico provisório) continuam iguais à noite: 46/46 e 70/70;
- as 5 federações aparecem com nomes distintos ("PT/PC do B/PV", "UNIÃO/PP", "PSDB/CIDADANIA", "PSOL/REDE",
  "PRD/SOLIDARIEDADE");
- transferência 2022 → 2026 refeita: os 3 primeiros de cada cargo no RJ não são de partido afetado, e o
  resultado não mudou.

## Arquivos

- **Novos:** `apuracao/partidos.py`, `test_partidos.py`.
- **Alterados:** `apuracao/bairros.py`, `apuracao/perfil.py`, `apuracao/comparacao.py`, `apuracao/historico.py`,
  `apuracao/web/app.py`, `apuracao/web/static/app.js`.
- **Testes:** `test_comparacao.py`, `test_exportar_bairros.py`, `test_historico.py`, `test_enderecos.py`.
- **Docs:** esta rodada, INDEX, CLAUDE.md, TODO.

## Decisões

- **Datas dos eventos:** são as das eleições gerais (o primeiro ano em que a sigla nova aparece no cadastro).
  Isso basta para comparar eleições gerais. Para comparar com eleições municipais (2020, 2024), a data exata
  importaria em PMN → MOBILIZA, PMB → DEMOCRATA e PC do B → PCDOB, que não confirmei além dos cadastros.
- **Testes antigos:**
  - partido sem correspondente passa de 0% a "sem dado" (`test_comparar_partido_e_candidato`);
  - `SIGLA_B` só existe quando houve voto em B (`test_comparar_partido_e_brancos`);
  - mensagem da variação mais precisa ("sem correspondente").

## Verificação

- `pytest -q`: 370 testes passando, incluindo os 61 de navegador.
- `test_tabela_explica_os_cadastros_reais` roda contra os 4 cadastros do cache.

## Pendências

- Quando surgir partido novo, fusão ou renomeação, `test_tabela_explica_os_cadastros_reais` falha. Registre o
  evento em `apuracao/partidos.py` (TODO 24).
- Comparações com eleições municipais (2020/2024) usam a mesma tabela; confira as datas dos eventos se a
  comparação cruzar uma mudança.
