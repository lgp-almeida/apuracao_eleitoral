# Como recalibrar as margens da projeção e das cadeiras

Quando fazer: depois que `preparar_2026.py` trouxer os microdados de 2026 (votos por seção, `detalhe_votacao_secao_2026` e os munzona com dados).

## Racional

- **As duas constantes são empíricas**, medidas refazendo apurações reais seção a seção, pela hora de totalização de cada uma:
  - `MARGEM_PP` e `MARGEM_PP_2T` (em `apuracao/projecao.py`): o percentil 95 do erro da projeção por faixa de % apurado, **uma tabela por turno** (rodada 44: no 2º turno a projeção erra mais no meio da apuração, e uma margem única cobria só 94,5% dele);
  - `SIGMA` (em `apuracao/projecao_cadeiras.py`): o desvio-padrão do log-erro dos votos projetados, de agremiações e de candidatos.
- **Decisão: juntar os anos (`--anos 2022 2026`), não substituir.** Duas eleições dão mais casos do que uma, e o percentil conjunto cobre o ano mais difícil. Hoje as cadeiras dependem de uma única eleição num único estado.
- **Antes de juntar, o teste que importa é fora da amostra:** validar 2026 com as constantes ATUAIS, calibradas só com 2022. É o que diz se a margem de 2022 valeu em 2026.
- **As tabelas nunca crescem com a apuração:** cada faixa é limitada pela anterior.

## Passo a passo

1. **Rodar os dois scripts**:

   ```bash
   python validar_projecao.py --anos 2022 2026 --saida saidas/backtest_projecao_2022_2026.parquet
   python validar_projecao.py --deputados --anos 2022 2026
   ```

   Cada um imprime as tabelas ATUAL e PROPOSTA já em Python (a margem, uma por turno). Imprime também:
   - para a margem, a cobertura de cada ano e de cada turno, e o p95 por turno e por cargo;
   - Governador e Senador entram nas UFs cujo `votacao_secao_<ano>_<UF>` está no cache (em 06/10/2026: RJ e ES);
   - para as cadeiras, a validação de cada ano com o σ atual e com o proposto.
2. **Critérios de aceite:**
   - **Margem:** a cobertura da proposta fica em cerca de 0,95 em cada ano. Com a margem atual, a cobertura de 2026 abaixo de 0,90 indica que 2022 subestimava o erro, e isso precisa ser registrado.
   - **Cadeiras:**
     - consolidados errados perto de zero (em 2022: 1 em cerca de 680);
     - poucos eleitos fora das duas listas;
     - faixas que não cobrem o oficial perto de zero.
     - Se 2026 com o σ atual tiver vários consolidados errados, reavalie o `LIMIAR` (95%) e o `PCT_MINIMO` (30%), além do σ.
3. **Adotar:** colar as tabelas PROPOSTAS em `apuracao/projecao.py` e `apuracao/projecao_cadeiras.py` e **também** em `test_calibracao.py`, junto com `CALIBRADO_COM`. É o único teste que deve falhar ao recalibrar; os demais leem as constantes do código.
4. **Conferir:** rodar `pytest -q` e `python ensaio_apuracao.py` (o ensaio usa as constantes novas).
5. **Registrar:** criar uma rodada em `docs/` com a cobertura e as validações antes e depois, e as decisões tomadas.

## Cuidados

- **Deputados:** a validação usa os `votacao_*_munzona` do ano, que trazem os eleitos oficiais. Enquanto o TSE não publica o `votacao_partido_munzona_2026`, ela usa o resultado importado (`dados_2026/historico_2026_t1[_UF]`, com a destinação oficial — rodada 40), que dá as mesmas cadeiras da noite.
- **2º turno de 2026:** depois de 25/10 e dos microdados do 2º turno, rodar de novo para juntar 2026 à `MARGEM_PP_2T`.
- **Presidente:** vem do arquivo nacional de votos e do detalhe `_BRASIL`, nas 27 UFs.
- **Reprodutibilidade:** as simulações das cadeiras usam semente fixa e ordem fixa. Com os mesmos dados, o resultado é o mesmo.
