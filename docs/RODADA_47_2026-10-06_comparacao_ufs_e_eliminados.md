# Rodada 47 — Lote 6: comparação entre UFs (TODO 20) e destino dos eliminados por local (TODO 17b)

06/10/2026 · último lote do plano de quitação do TODO ([RODADA_42](RODADA_42_2026-10-06_analise_coleta_e_percentuais.md)).

**O plano previa este lote para depois do 2º turno. Ficou pronto antes, sem esperar os dados:**
- **Item 20:** já há as 27 pastas da noite de 4/10 (`oficial_<UF>`) e os históricos de 2022 das 27 UFs;
- **Item 17b:** funciona com os microdados de 2022;
- **2026:** os dois passam a valer sozinhos quando existirem as pastas `oficial_t2_<UF>` (noite de 25/10) e os
  microdados do 2º turno de 2026.

## Item 20 — `comparar_ufs.py`: abstenção, brancos/nulos e transferência lado a lado

- **Núcleo:** `apuracao/entre_ufs.py`, sobre as pastas no formato do coletor (`ufs.dir_uf`; no RJ, a pasta
  antiga). Pasta que falta não é erro: a UF fica sem a linha.
- **Participação:** abstenção (% do eleitorado) e brancos + nulos (% do total de votos, o denominador do mapa),
  por UF × cargo × eleição × turno, com o % apurado (a noite em andamento aparece como parcial).
- **Variação:** 2026 − 2022, em p.p.
- **Transferência 1º → 2º turno por UF:** `transferencia.unidades_divulgacao`, com municípios como unidades.
  - **O que mostra:** para onde foram os eliminados, quanto cada finalista manteve, a abstenção extra e as
    células no limite (0% ou 100%).
  - **Onde não dá:** com poucos municípios (o DF tem 1), a linha traz a nota em vez de números.
  - **Leitura frágil:** inferência ecológica com municípios como unidades; ver a rodada 30.
- **Saídas:** terminal, `.xlsx` (leia, participacao, variacao, transferencia) e PNG da abstenção por UF.
- **Desempenho:** 27 UFs, Presidente + Governador, com a transferência de 2022, em 5 s.

### Números reais: Presidente, 1º turno, 2026 × 2022

- **Abstenção:** subiu em 14 das 27 UFs. Mediana +0,02 p.p.
  - **O Sul, o Sudeste e o Centro-Oeste subiram:** MS +1,78, RS +1,57, DF +1,36, PR +1,10, SP +0,93, RJ +0,57.
  - **O Norte e o Nordeste caíram:** RO −2,94, MA −2,47, PA −2,12, AP −2,10, AC −2,00, CE −1,93, AL −1,75.
- **Brancos + nulos:** subiram em 23 das 27 UFs. Mediana +0,25 p.p.
  - **Maiores altas:** PA +1,73, AL +1,64, CE +1,41, PB +1,03.
- **Governador, 1º turno:** SE tinha 44,4% de brancos + nulos em 2022. São os votos anulados de uma candidatura
  indeferida; a variação de SE (−29,8 p.p.) reflete isso, não uma mudança de comportamento.
- **Transferência em 2022, Presidente:** os eliminados foram mais para Lula no RJ (61%) e em SP (45% × 32%), e
  mais para Bolsonaro em MG (71%) e no RS (47% × 31%).
  - **RR (15 municípios):** a matriz bateu no limite (100% para Bolsonaro). A coluna `CELULAS_NO_LIMITE`
    sinaliza essas leituras.

## Item 17b — camada "Destino dos eliminados (1º → 2º turno)" no mapa por local

- **Núcleo:** `mapa_locais.transferencia` + camada `"transferencia"` em `mapa_locais.pontos`, sobre
  `transferencia.calcular(nível local, estrato município, sem bootstrap)`.
- **Métricas:**

  | Métrica | O que é |
  |---|---|
  | `elim_para_a` | Destino dos eliminados: % para o 1º finalista. **Estimado por município**: todos os locais do município têm o mesmo valor |
  | `eliminados_1t` | % do eleitorado do local que votou nos eliminados no 1º turno (observado) |
  | `abst_extra` | Abstenção do 2º turno − do 1º, em p.p. (observado, divergente) |
  | `residuo_a` | 1º finalista: observado − previsto pela matriz, em p.p. (divergente; "onde o finalista foi melhor do que a matriz prevê") |

- **Página:**
  - aba Mapas → Detalhe "Locais de votação" → Camada "Destino dos eliminados", com o seletor "Mostrar";
  - a dica mostra "1º turno: x% → 2º turno: y%" ou "previsto → observado";
  - endereço `&camada=transferencia&transf=abst_extra`.
- **Novos campos na resposta da API:** `lados` (rótulos do antes/depois na dica) e `sentido` ("variacao" →
  legenda subiu/caiu; "residuo" → maior/menor que o esperado). Também valem para a camada de variação da
  rodada 46.
- **RJ, Presidente 2022 (4.813 locais, cerca de 2 s):**

  | Métrica | Mediana | Mín. | Máx. |
  |---|---|---|---|
  | Eliminados no 1º turno | 5,66% | 0 | 17,5 |
  | Destino dos eliminados para Bolsonaro (38 valores, um por estrato) | 34,9% | 8,4 | 75,1 |
  | Abstenção extra | −0,24 p.p. | −11,5 | +10,5 |
  | Resíduo de Bolsonaro | −0,08 p.p. | −6,2 | +5,8 |

- **Quando não há dados:** Governador RJ 2022 (sem 2º turno) e 2026 antes dos microdados do 2º turno respondem
  "sem 2º turno de … em …" (404 na API).

## Defeito corrigido na página

Com o Detalhe "Locais de votação", `atualizarMapa` exigia o nº de candidato da métrica ESCONDIDA ("% de um
candidato") antes de chegar à camada. A camada de perfil, aberta sem número, ficava em "Informe o número de um
candidato". Agora cada camada valida o que precisa.

## Arquivos

- **Novos:** `apuracao/entre_ufs.py`, `comparar_ufs.py`, `test_entre_ufs.py`.
- **Alterados:**
  - `apuracao/mapa_locais.py` (camada `transferencia`, `lados`/`sentido`);
  - `apuracao/web/static/{index.html,app.js}`;
  - `test_migracao.py` (+1);
  - `test_mapa_locais_e2e.py` (+1 e2e).

## Verificação

- `pytest -q`: **400 testes passando**, 64 e2e incluídos.
- **Testes sintéticos novos:**
  - pastas de 3 UFs: UF sem pasta, sem referência e sem 2º turno;
  - DF com 1 município: sai com a nota;
  - matriz verdadeira recuperada em SP (±4 p.p.);
  - CLI com planilha e gráfico;
  - camada de transferência com `calcular` simulado.
- **Números reais:** acima.

## Pendências (fim do plano)

- **Depois de 25/10:** rodar `comparar_ufs.py` com o 2º turno de 2026 (as pastas `oficial_t2_<UF>` entram
  sozinhas). Na mesma ocasião:
  - `validar_projecao.py` com o 2º turno, para juntar 2026 à `MARGEM_PP_2T` (rodada 44);
  - a conferência do 2º turno (`conferir_resultado.py`; o `preparar_2026` faz sozinho).
- **Quando os microdados do 2º turno de 2026 saírem:** a camada "Destino dos eliminados" com `ano_bairros=2026`
  e `transferencia_turnos.py --ano 2026`.
- **Fora dos lotes:**
  - **item 4:** importação final de 2026, que depende do TSE publicar o detalhe e o partido munzona;
  - **item 24:** tabela de partidos, contínuo.
