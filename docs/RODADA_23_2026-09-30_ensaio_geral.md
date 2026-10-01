# Rodada 23 — Ensaio geral e roteiro da noite da eleição

30/09/2026 · pedido do usuário: "Implemente o item 3, o ensaio geral." (item 3 de `docs/TODO.md`)

## Entregas

- **`apuracao/ensaio.py`:** a apuração real de 2022 (RJ) reconstituída e servida **no formato do TSE**:
  - `carregar_2022` junta:
    - detalhe por seção, com a hora da 1ª totalização;
    - votos por seção de Presidente (todas as UFs), Governador, Senador, Dep. Federal e Estadual;
    - candidatos e destinação oficial (`votacao_candidato_munzona`), com a situação final;
  - `Relogio` percorre a noite de 2022, acelerada;
  - `Gerador` monta, para a hora virtual, os EA14/EA15 (acompanhamento, com a hora da última totalização de cada município) e os EA20 (UF, 92 municípios e Brasil);
  - `SessaoEnsaio` responde como o servidor do TSE: EA11/EA12 dos recortes do simulado, o resto gerado na hora, ETag/304 e 404.
- **`ensaio_apuracao.py`:** num só processo, sobe:
  - o "TSE" do ensaio;
  - o **coletor de verdade**, com o mesmo limite de 20 req/s da noite;
  - o **site de verdade** (http://localhost:8040);
  - **usuários simultâneos** consultando 12 rotas (painel, projeção, cadeiras, candidato, série, mapas, status).
  - No fim, **confere com o resultado oficial** (válidos de cada cargo, 100% e final, eleito no 1º turno, cadeiras 46/46 e 70/70) e grava `dados_2026/ensaio_2022/relatorio_ensaio.json` com ciclos, a projeção do Governador ao longo da noite, a latência por rota e a conferência.
  - Opções: `--velocidade`, `--inicio HH:MM`, `--carga N`, `--max-rps`, `--manter`.
- **`verificar_prontidao.py`:** checa, com OK/AVISO/FALHA e código de saída:
  - dependências, disco e cache (malhas, 2022 importado, microdados);
  - a hora do computador contra a do TSE (cabeçalho `Date`);
  - os ambientes simulado e **oficial** (configuração, códigos esperados 6257/6259, acompanhamento do RJ);
  - a porta 8000 e o diretório `dados_2026/oficial`, que não pode ter dados de outro ambiente;
  - opcionalmente, com `--testes`, a suíte de testes.
- **`docs/ROTEIRO_NOITE_DA_ELEICAO.md`:** o que fazer e em que ordem de 2/10 à madrugada de 5/10 (e no 2º turno), o comando único da noite, como ler o painel, a tabela de incidentes e a cópia de segurança.

## O ensaio realista (velocidade 30, limite de 20 req/s, 6 usuários)

- **Duração:** a noite de 2022 do RJ (17h21 → 0h20) em **14,3 min**.
- **Coleta:** **52 ciclos** do coletor, **sem nenhum erro**, com 6.009 pedidos ao TSE do ensaio.
  - O 1º ciclo baixou 466 arquivos em 29,8 s.
  - No pico (19h–20h30) foram 300 a 380 arquivos novos por ciclo, em 21–28 s.
  - Depois de 23h, 1 a 16 por ciclo; os 304 funcionaram.
- **Site:** **7.577 consultas, 0 erros 5xx**.
  - Mediana abaixo de 40 ms em quase todas as rotas.
  - Painel: mediana 146 ms, p95 1,1 s, máximo 2,3 s.
  - Cadeiras e candidato: p95 0,3–0,5 s, máximo ~1,5 s nos momentos de recálculo com 300 simulações.
- **Conferência final:** **OK em tudo.**
  - Válidos de Presidente, Governador e Senador **idênticos** ao oficial; deputados a 0,005–0,006%, pela legenda de partido com votos anulados.
  - 100% e final nos 5 cargos.
  - Castro eleito no 1º turno.
  - Cadeiras **46/46 e 70/70**.
- **Projeção do Governador durante o ensaio:**
  - "cedo demais" até 2% apurado;
  - "indefinido" de 2% a 6,5%;
  - "vitória no 1º turno projetada" desde 10% apurado (19h05), com projeção de 55,8% contra 58,69% final, dentro da margem de ±4,51;
  - a projeção entrou na margem final (±0,43) às 20h27, com 83%.

## Defeitos que o ensaio encontrou (e que apareceriam na noite de 4/10)

1. **Erro 500 no início da apuração.**
   - **Problema:** sem nenhum voto válido, o quociente eleitoral é 0 e `_eleger` dividia por zero. `/api/cadeiras` e `/api/candidato` de deputado respondiam 500 (39 erros no ensaio relâmpago).
   - **Correção:** `distribuir` e `projetar_cadeiras` passam a gerar `TseDataError`, que vira 404 na API; a ficha do candidato simplesmente não mostra a cadeira.
   - **Teste:** `test_sem_votos_validos_nao_divide_por_zero`.
2. **Leitura precipitada da projeção.**
   - **Problema:** com 0,04% apurado o painel dizia "vitória no 1º turno projetada" (Castro com 83,6%). A margem só foi calibrada a partir de 2% apurado.
   - **Correção:** abaixo de 2% (`PCT_MINIMO_LEITURA`) a leitura é "cedo demais: X% do eleitorado apurado".
   - **Teste:** `test_cedo_demais_para_ler_a_projecao`.
3. **O 2º turno gravaria por cima do 1º.**
   - **Problema:** `destino_padrao` não considerava o turno. Em 25/10 os dados iriam para `dados_2026/oficial`, trocando o último estado e misturando as séries.
   - **Correção:** o 2º turno usa `dados_2026/oficial_t2` (`destino_padrao(..., turno)`), em `coletar_resultados.py` e `site_apuracao.py`.
   - **Teste:** `test_segundo_turno_nao_grava_por_cima_do_primeiro`.
4. **No próprio script do ensaio:**
   - a projeção nula antes do 1º voto derrubava o laço;
   - a leitura da hora do TSE usava HEAD, que vem sem `Date`, e passou a usar GET;
   - o selo do site dizia "simulado" e agora diz "ensaio 2022".

## Verificação

- **`pytest -q`: 176 testes passando** (eram 167).
- **`test_ensaio.py`**, 6 testes, com uma reconstituição sintética de 2 municípios e 4 seções:
  - relógio;
  - JSON no formato do TSE na metade da apuração (seções, eleitorado, válidos, brancos, legenda, federação, QE, hora da última totalização);
  - fim, com a situação oficial e os anulados fora dos válidos e dos votos do partido;
  - o **coletor real** contra o ensaio: 6 arquivos, depois 0 pedidos sem mudança, depois só UF + Niterói, e o fim;
  - ETag/304/404;
  - resumo da carga.
- **Sabotagens** (restauradas byte a byte):
  - sem 304: 1 falha;
  - "anulado conta como válido": não foi pega de início. Ganhou a verificação dos votos do partido e agora falha 1 teste.
- **Oficial hoje:** `coletar_resultados.py --ambiente oficial --uma-vez` responde "divulgação ainda não disponível … 404", o esperado até 3/10.
- **`verificar_prontidao.py`:** "PRONTO: 0 falha(s), 3 aviso(s)", com os avisos esperados: oficial 404, porta 8000 com o simulado no ar e, na 1ª versão, a hora do TSE, já corrigida.
- **Servidores** reiniciados nas portas 8000, 8022 e 8023.

## Arquivos

- **Novos:** `apuracao/ensaio.py`, `ensaio_apuracao.py`, `verificar_prontidao.py`, `test_ensaio.py`, `docs/ROTEIRO_NOITE_DA_ELEICAO.md`.
- **Alterados:**
  - `apuracao/cadeiras.py` (sem voto válido), `apuracao/projecao_cadeiras.py` e `apuracao/projecao.py` (cedo demais);
  - `apuracao/divulgacao/coletor.py` (`destino_padrao` com turno), `coletar_resultados.py` e `site_apuracao.py`;
  - `test_cadeiras.py`, `test_projecao.py` e `test_divulgacao.py`;
  - `docs/TODO.md`, `docs/INDEX.md` e `CLAUDE.md`.
- **Dados:** `dados_2026/ensaio_2022/` (último ensaio, com o relatório) e `logs/ensaio_realista.log`.

## Pendências

- **3/10:** rodar `verificar_prontidao.py` e um ciclo no oficial assim que o `ele-c.json` sair (roteiro).
- **Carga maior:** o ensaio usou 6 usuários. Com muito mais gente, o roteiro indica separar coleta e site em dois processos.
- **Item 4 do TODO:** preparar os dados de 2026 assim que o TSE publicar os microdados.
