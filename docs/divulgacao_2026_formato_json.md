# Divulgação de resultados 2026 — formato dos JSON e regras de coleta

29/09/2026. Tudo o que está aqui foi observado no ambiente de simulado do TSE (`https://resultados-sim.tse.jus.br/simulado/simulado2026`). Os códigos de eleição e o esquema do ambiente oficial estão no [Anexo I](<Anexo I — Atualizações ao Comparativo TSE 2022 × 2026.md>), bloco A6. Código: `apuracao/divulgacao/`.

## Ambientes

| Ambiente | Base | Nome | Situação em 29/09/2026 |
|---|---|---|---|
| Simulado | `https://resultados-sim.tse.jus.br/simulado` | `simulado2026` | no ar, com todas as seções totalizadas (pleito 17801) |
| Oficial | `https://resultados.tse.jus.br` | `oficial` | `ele-c.json` responde **404 com página HTML**. O TSE carrega os parâmetros oficiais em 3/10 |

O cliente trata 404 e páginas HTML como "divulgação ainda não disponível" e tenta de novo a cada 5 minutos, sem repetir em laço.

## Arquivos usados

| Arquivo | Caminho (relativo a `<base>/<ambiente>/`) | Conteúdo |
|---|---|---|
| EA11 | `comum/config/ele-c.json` | ciclo (`ele2026`), pleito, eleições (`cd`, 2º turno `cdt2`), cargos por eleição (`cp`: código, nome, `tp` 1 = majoritário, 2 = proporcional) e **modelos de diretório** (`arq[].dir`, ex.: `<base>/<ambiente>/<ciclo>/<cd_eleicao>/dados/<uf>`) |
| EA12 | `<ciclo>/<e>/config/mun-e<e:06>-cm.json` | por UF, municípios com código TSE (`cd`), **código IBGE (`cdi`)**, nome, capital (`c`) e zonas (`z`) |
| EA14 | `<ciclo>/<e>/dados/br/br-e<e:06>-ab.json` | acompanhamento por UF, mais a linha `br` |
| EA15 | `<ciclo>/<e>/dados/<uf>/<uf>-e<e:06>-ab.json` | acompanhamento por município, mais a linha da UF |
| EA20 | `<ciclo>/<e>/dados/<uf>/<uf>[<mun:05>]-c<cargo:04>-e<e:06>-u.json` | resultado unificado de um cargo na UF, no Brasil (`br`) ou num município |

- **Códigos no simulado:**
  - eleições: 21270 Federal (2º turno 21271), 21272 Estadual (2º turno 21273), 21274 Conselheiro Distrital;
  - cargos: 1 Presidente, 3 Governador, 5 Senador, 6 Dep. Federal, 7 Dep. Estadual, 8 Distrital, 25 Conselheiro.
- **No oficial:** as eleições são 6257, 6259 e 6261 (Anexo I). O coletor **lê os códigos do `ele-c.json`**, nunca os fixa no código.
- **EA10 (eleitos)** responde 404 até a totalização final; não é usado.

## Campos do EA20 (e do acompanhamento)

- **Números:** tudo vem como texto com vírgula decimal (`"9,04"`). Os campos com sufixo `n` (`pvapn`, `pan`…) têm mais casas; o parser os prefere.
- **`s` (seções):** `ts` total, `st` totalizadas, `pst` %.
- **`e` (eleitorado):** `te` eleitorado, `c` comparecimento, `pc` %, `a` abstenção, `pa` %.
- **`v` (votos):**
  - `tv` total;
  - `vv` válidos, `pvv` % sobre `tv`;
  - `vnom` nominais, `vl` legenda (só proporcionais);
  - `vb` brancos, `tvn` nulos;
  - `van` anulados, `vansj` **anulados sub judice**;
  - `vvc` = válidos + anulados sub judice.
- **Cabeçalho:**
  - `dt`/`ht`: hora da última totalização daquela abrangência;
  - `tf = s`: totalização final;
  - `esae`: matematicamente definida;
  - `idg`: identificador do arquivo gerado. **Não é versão.**
- **`carg[]`:** `cd`, `nmn` nome, `nv` vagas (Senador = 2), `qe` quociente eleitoral (proporcionais), `fed[]` (federações e seus partidos `npar`).
- **`carg[].agr[]` (agremiações):** `vag` vagas obtidas.
- **`agr[].par[]` (partidos):** `tvtn` nominais, `tvtl` legenda.
- **`cand[]`:** `n` número, `nmu` nome de urna, `vap` votos, `pvap` %, `seq` posição, `st` situação, `e = s` eleito **ou vai ao 2º turno**, `dvt` destinação, `vs[]` vice/suplentes.

**Armadilha — votos sub judice:** os votos de candidatura *sub judice* entram em `vap` do candidato, mas **não** em `vv`. No simulado, a soma dos votos dos candidatos a Governador do RJ = `vv` + `vansj` (7.824.970 + 1.761.169). O `pvap` desses candidatos é calculado sobre `vvc`, e um deles aparece como "2º turno". O site mostra a destinação ("Anulado sub judice") ao lado da situação.

**Nível mais fino em tempo real: o município.** Resultado por local ou seção só chega pelos microdados da CDN, dias depois (`votacao_secao_2026_<UF>.zip`), que `planilha_candidato.py --ano 2026` já lê. Os boletins de urna por seção (`arquivo-urna`) existem, mas não são coletados.

## Regras de coleta implementadas

- **Taxa:** no máximo 20 req/s. O limite do TSE é 100/s, e estourar bloqueia por 10 min, com o bloqueio reiniciando a cada tentativa. Em 403/429, o coletor pausa por 11 min.
- **`If-None-Match`/ETag em todo pedido:** o TSE responde 304 (que também conta no limite).
- **404:** memorizado no ciclo, para não repetir; vários 404 podem bloquear o IP. No 2º turno, só Governador e Presidente são pedidos.
- **Incremental:** a cada ciclo, EA15 da UF e EA14 (br) só da eleição federal. O EA20 só é baixado para as abrangências cujo `dt/ht` mudou.
  - **Presidente por UF** (rodada 35): o EA14 traz uma linha por UF (27 + `zz`, exterior). Quando o `dt/ht` de outra UF muda, o coletor pede o EA20 do presidente dela (`<uf>-c0001-e<fed>-u.json`, ~10 kB) e o grava em `raw_brasil/` e `ultimo/brasil_*.parquet`, separado dos dados da UF. No 1º ciclo do simulado: 493 arquivos (466 + 27).
  - Medido no simulado: 1º ciclo com 466 arquivos em 35–39 s (8 downloads simultâneos); ciclo sem mudança com 3 requisições (304) em 0,2 s.
- **Histórico:** o TSE sobrescreve os parciais, então cada versão distinta de cada arquivo é guardada em `raw/…/<AAAAMMDD_HHMMSS>_<idg>_<sha1[:10]>.json.gz` (o hash do conteúdo garante que nenhuma versão se perca; ver rodada 06). Os totais vão para `historico_totais.parquet`, e o % dos válidos por candidato/partido na UF e no Brasil vai para `historico_serie.parquet` (série do painel). A série por candidato em cada município, UF e Brasil vai para `historico_candidatos/`, um bloco Parquet por ciclo (rodada 07).
- **Tamanho:** o 1º ciclo completo (RJ + Presidente) ocupa cerca de 12 MB comprimidos.
