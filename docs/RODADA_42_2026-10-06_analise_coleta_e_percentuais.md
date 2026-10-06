# Rodada 42 — Lote 1 do plano de quitação do TODO: análise das parciais (21), denominador do % (23), limpeza

06/10/2026 · pedido do usuário: "avalie o TODO e organize as pendências de forma que podem ser implementadas de
forma agrupada e sequencialmente. Vamos acabar, no que for possível, com este passivo."

**Plano aprovado:** 6 lotes, um por rodada (42–47). Os 3 primeiros vêm antes do 2º turno de 25/10, que terá
Governador do RJ e Presidente; a noite será acompanhada com o RJ e outras UFs. A tabela dos lotes está no topo do
[TODO](TODO.md). Esta rodada é o **lote 1**.

## Achado importante: as parciais da noite de 4/10 do RJ não estão mais nesta máquina

- **Pasta recriada:** `dados_2026/oficial` (com `raw/`) foi recriada em **05/10 às 09:22**. O `raw/` atual tem
  500 versões, todas da recoleta da manhã de 05/10.
- **Sem cópia da noite:** a cópia `copias/oficial` também começou às 09:23 de 05/10, então a noite de 4/10 rodou
  sem cópia de segurança nesta pasta, ou com cópia em outro disco.
- **Sem outra cópia:** procurei em `dados_2026/`, `copias/`, `/prj/prjatrv/lgonzaga` (até 4 níveis) e
  `/mnt/data2` e não achei outra cópia.
- **Consequência:** as **7.210 versões analisadas na rodada 36 se perderam**, e não dá para reproduzir aqueles
  números com a ferramenta nova. Ela foi validada com o ensaio e com testes sintéticos.
- **Para o 2º turno:** rodar com `--copia-dir` em outro disco (o roteiro já pede) e **não apagar
  `dados_2026/oficial_t2` depois da noite**.

## Item 21 — `analisar_coleta.py` (análise das parciais da noite)

**Funcionamento:**
- **Núcleo:** `apuracao/divulgacao/analise.py`, com funções sem I/O sobre duas tabelas que `ler` monta do `raw/`
  e do `raw_brasil/`. A cópia de segurança também serve, porque preserva o `mtime`.
- **As duas tabelas:**
  - **versões:** arquivo, tipo, escopo, UF, município, cargo, **geração** (`dg`/`hg`), **chegada** (`mtime`),
    totalização e % (EA20) e hash;
  - **anúncios:** cada abrangência de cada acompanhamento EA15/EA14, com a hora anunciada.

**Indicadores** (as tabelas vão para a planilha `--saida`):
- **Atraso da coleta:** chegada − geração, por tipo e escopo.
- **Anúncio × publicação:** para cada totalização anunciada × arquivo EA20 da abrangência:
  - se chegou primeiro a versão anterior (`gerado < hora anunciada`, limitada à geração do acompanhamento, como
    `coletor._limitar`);
  - quanto se esperou pela certa;
  - quanto o TSE demorou para gerá-la.
  - A janela vai deste anúncio ao próximo da mesma abrangência; o coletor lê o acompanhamento antes dos EA20 do
    ciclo.
- **Atraso do TSE** por janela de 30 min.
- **Pausas:** do TSE (acompanhamento sem nova geração) e nossas (nada gravado). Uma pausa nossa coberta em ≥ 90%
  por uma do TSE é marcada `TSE_TAMBEM`.
- **Critério do coletor:** versões que a regra chama de anteriores × as que tinham conteúdo diferente da certa;
  totalizações certas de primeira.
- **Peculiaridades:** EA20 com `dt` antes do anúncio, por cargo; acompanhamento com hora no futuro.
- **Fim da noite:** última totalização e % em disco × os anunciados.

**Saídas:** terminal; `--saida` (.xlsx com as tabelas, as totalizações e as versões); `--grafico` (PNG "% apurado:
TSE × aqui"); `--log` (lista as linhas de reinício do log do vigia/site).

**Validação com o ensaio** (`ensaio_apuracao.py`, RJ 2022, 30×, `--atraso-ea20` 3 min; 6.005 versões, 2.434
totalizações anunciadas):
- **Totalizações municipais:** 5.704. Em 640 (11%) chegou primeiro a versão anterior; em 801 a seguinte chegou
  antes da regeração, efeito da aceleração.
- **Atraso do TSE** (geração do EA20 certo − anúncio): mediana de 2,1 a 5,1 min por janela. É o atraso
  simulado de 3 min mais o passo do relógio virtual (um ciclo de 15 s reais = 7,5 min de 2022).
- **Critério do coletor:** das 62 versões que a regra classificou como anteriores, 62 tinham de fato outro
  conteúdo; 4.934 de 4.996 totalizações vieram certas de primeira.
- **Fim da noite:** RJ 100% em disco = 100% anunciado em todos os cargos; Brasil 99,939% × 99,943%.
- **Limite do ensaio:** a geração está no relógio de 2022 e a chegada no relógio real, então "chegada − geração"
  não tem sentido no ensaio. O gráfico detecta isso e usa a hora de geração, avisando no rótulo.
- **Defeito achado pela validação e corrigido:** a primeira versão dava uma folga de 5 min antes do anúncio.
  No ensaio (30×) isso cobre 2h30 de apuração e chegou a contar 31.110 "anteriores" em 6.005 versões.
- **Sobre o `raw/` atual do oficial** (só a manhã de 05/10): uma pausa nossa de 209 min (09:23–12:52, sem coleta)
  coberta por uma do TSE (02:59–12:51, sem nova geração).

## Item 23 — mesmo denominador do "% dos válidos" nas comparações

- **Convenção:** o painel em tempo real **continua com o % do TSE**, que inclui os anulados sub judice no
  denominador e é o que o site do TSE mostra na noite. **Toda comparação entre fontes** recalcula o % como
  `votos ÷ válidos oficiais` nos dois lados (`comparacao.pct_dos_validos`).
- **Onde se aplica:** a métrica "candidato" da Comparação (`_pct_candidato`), a planilha do candidato × eleição
  anterior (`_por_municipio`, `_ficha`) e, por partido, `_pct_partido`, que já era assim.
- **Página:** nota na aba Comparação e no bloco do candidato.
- **Efeito real (Governador RJ 2026):**

  | Candidato | Painel (% do TSE) | Base oficial, a mesma de 2022 |
  |---|---|---|
  | Douglas Ruas | 49,27% | 50,88% |
  | Eduardo Paes | 42,76% | 44,16% |

  A maior diferença num município chega a 10,8 p.p. (Ruas) e 6,3 p.p. (Paes). Há 274 mil votos sub judice.

## Limpeza do TODO

- **Item 3 fechado:** a checagem do oficial foi cumprida na noite de 4/10.
- **Item 19 fechado:** foi entregue na rodada 35.
- **Item 18:** marcado como parcial, com o resto nas rodadas 43 e 44.
- **Plano de lotes:** registrado no topo do TODO.

## Arquivos

- **Novos:** `apuracao/divulgacao/analise.py`, `analisar_coleta.py`, `test_analise_coleta.py`.
- **Alterados:** `apuracao/comparacao.py` (`pct_dos_validos`), `apuracao/web/static/index.html` (notas),
  `test_comparacao.py`.
- **Docs:** TODO, INDEX, CLAUDE.md.

## Verificação

- `pytest -q`: 374 testes passando (+3 da análise, +1 do denominador).
- Ensaio e `raw/` do oficial analisados (números acima). Planilha `saidas/coleta_ensaio_2022.xlsx` e gráfico
  `saidas/coleta_ensaio_2022.png`.

## Próximo

Lote 2 (rodada 43): noite do 2º turno com várias UFs (item 18).
