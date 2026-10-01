# Rodada 22 — Projeção das cadeiras de deputado: consolidados × em disputa

30/09/2026 · pedido do usuário: "Reconheço que projetar deputado federal e estadual é mais difícil, pois a margem de erro é muito grande. Mesmo assim, é possível?" e, depois do experimento, "Sim, implemente assim antes do item 3".

## A pergunta: dá para projetar deputado?

**Experimento:** a apuração real de 2022 no RJ foi refeita seção a seção (Dep. Federal, 46 vagas; Dep. Estadual, 70). Em cada momento, as cadeiras foram distribuídas sobre os votos parciais e sobre os votos projetados, e o resultado foi comparado com o oficial.

| % apurado | Estadual: cadeiras no partido errado, parcial → projeção | Estadual: eleitos errados | Federal: cadeiras erradas | Federal: eleitos errados |
|---|---|---|---|---|
| 10% | 4 → 5 | 16 → 12 | 2 → 2 | 8 → 6 |
| 50% | 3 → 2 | 9 → 6 | 2 → 0 | 6 → 3 |
| 90% | 0 → 0 | 1 → 0 | 0 → 0 | 2 → 2 |

**Resposta:**
- **cadeiras por partido:** sim, mesmo cedo;
- **nome a nome:** só com a incerteza explícita. A disputa dentro de cada partido se decide por poucos milhares de votos, muitas vezes concentrados em lugares que ainda não apuraram.

Daí o desenho: faixa de cadeiras por agremiação e eleitos "consolidados" × "em disputa".

## Entregas

- **`apuracao/cadeiras.py`:** o núcleo da distribuição virou `_eleger` (Python puro, rápido); `distribuir` usa esse núcleo. Nenhum resultado mudou: os testes, incluindo as 116 vagas reais do RJ, continuam passando.
- **`apuracao/projecao_cadeiras.py`:**
  1. projeta, por município, os votos de cada agremiação e de cada candidato (método de `apuracao/projecao.py`);
  2. distribui as cadeiras sobre essa projeção;
  3. faz **300 simulações** com ruído log-normal no tamanho do erro medido em 2022 (`SIGMA` por faixa de % apurado; agremiações e candidatos em separado), refazendo a distribuição inteira em cada uma. A semente é fixa, então o painel não "pisca" sem dado novo;
  4. classifica cada candidato:
     - **consolidado**: eleito em ≥ 95% das simulações (`LIMIAR`);
     - **em disputa, dentro** ou **em disputa, fora**: eleito em parte delas;
     - **fora**: eleito em menos de 5% delas.
  5. dá a faixa de cadeiras de cada agremiação (percentis 5–95 das simulações).
  - Também traz as funções da apuração reconstituída: `votos_secao_deputado` (legenda vai para a agremiação do partido; candidatos anulados ficam fora), `estado_em`, `momentos` e `calibrar_sigma`.
- **`validar_projecao.py --deputados`:** recalcula o σ e a validação (cerca de 15 s).
- **API:**
  - `/api/cadeiras` ganha `projecao` enquanto a apuração está em andamento (UF entre 0 e 100% e não final; nunca em eleição passada importada), com `ativa` a partir de **30% apurado** (`PCT_MINIMO`), número de consolidados e em disputa, faixas por agremiação e a lista de candidatos com frequência e situação;
  - `/api/candidato` ganha `cadeira.projecao` (situação, frequência, votos projetados);
  - resultado guardado em memória até as tabelas mudarem (cerca de 0,6 s por cálculo).
- **Painel:** com a projeção ativa, o cartão de deputado mostra:
  - "Cadeiras projetadas — N vagas", com o eleitorado apurado e o QE projetado;
  - em destaque, "47 eleitos consolidados · 23 vagas em disputa entre 48 candidatos";
  - por agremiação, uma barra com as cadeiras firmes (o mínimo) e as que podem vir (até o máximo), e o texto "17 (15–18)";
  - "Ver consolidados e a disputa": tabela com candidato e agremiação, votos projetados, situação e "Sim." (% das simulações);
  - nota do método, com os números de 2022 e a ressalva de amostra.
  Abaixo de 30%, continua a distribuição sobre os votos parciais, com a nota "a projeção de cadeiras começa com 30%".
- **Aba Candidato:** por exemplo, "Em disputa — hoje dentro · eleito em 57% das simulações · 40.328 votos projetados (50,12% apurado)".

## Calibração: σ do log-erro dos votos projetados (RJ 2022, Federal + Estadual)

| % apurado | 0–10 | 10–20 | 20–30 | 30–40 | 40–50 | 50–60 | 60–70 | 70–80 | 80–90 | 90–100 |
|---|---|---|---|---|---|---|---|---|---|---|
| Agremiações | 0,142 | 0,130 | 0,126 | 0,109 | 0,086 | 0,072 | 0,059 | 0,038 | 0,022 | 0,012 |
| Candidatos com ≥ 10% do QE | 0,425 | 0,338 | 0,289 | 0,239 | 0,194 | 0,145 | 0,131 | 0,093 | 0,052 | 0,025 |

O viés é praticamente nulo (média do log-erro entre −0,01 e +0,06).

## Validação (RJ 2022, 9 momentos × 2 cargos)

| Cargo | % apurado | Consolidados (errados) | Em disputa | Eleitos fora das duas listas | Faixas que cobrem o oficial |
|---|---|---|---|---|---|
| Estadual | 10 | 25 (0) | 91 | 1 | 27/27 |
| Estadual | 30 | 35 (**1**) | 69 | 0 | 27/27 |
| Estadual | 50 | 46 (0) | 50 | 0 | 27/27 |
| Estadual | 70 | 52 (0) | 36 | 0 | 27/27 |
| Estadual | 90 | 65 (0) | 11 | 0 | 27/27 |
| Federal | 10 | 20 (0) | 66 | 1 | 26/26 |
| Federal | 40 | 30 (0) | 37 | 1 | 25/26 |
| Federal | 50 | 31 (0) | 37 | 0 | 26/26 |
| Federal | 90 | 40 (0) | 11 | 0 | 26/26 |

- **No total:** dos **683 consolidados, 1 não se elegeu** (99,85%), e as faixas de cadeiras cobriram **481 de 482** casos.
- **Ressalva:** o σ foi medido e testado na **mesma** eleição (só o RJ 2022 tem votos por seção no cache), então é um resultado "dentro da amostra". O corte de 30% para ativar a projeção é conservador: mesmo com 10% não houve consolidado errado.

## Defeitos e decisões

- **TSE falso dos testes:** o recorte do simulado vem com `tf='s'` (totalização final), e `avancar_uf`/`avancar_municipio` mantinham a marca mesmo baixando as seções para 40%. Com isso a API tratava a apuração como final e não projetava. Agora `tf` segue o percentual.
- **Válidos da reconstituição:** os válidos por município precisam incluir a **legenda**, e por isso vêm das agremiações, não só dos nominais (`estado_em`).
- **Tabela no cartão:** transbordava. A agremiação foi para baixo do nome e os rótulos foram encurtados ("disputa, dentro"; "Sim.").
- **Aviso de consistência:** o bloco projetado também avisa quando os votos das agremiações não somam os válidos.

## Verificação

- **`pytest -q`: 167 testes passando** (eram 156).
- **`test_projecao_cadeiras.py`**, 11 testes:
  - σ decrescente, e o de candidato maior que o de agremiação;
  - as quatro situações;
  - apuração completa: tudo consolidado e faixas sem largura;
  - apuração parcial: os candidatos com folga ficam consolidados, o empate 15 × 15 fica em disputa, o sub judice fica fora, e a mesma semente dá o mesmo resultado;
  - votos por seção (legenda, anulado, brancos);
  - API;
  - regressão com dados reais: Estadual a 50%, com ≥ 40 consolidados, todos eleitos, e as faixas cobrindo todas as agremiações.
- **`test_cadeiras_e2e.py`**, reescrito para o bloco projetado (apuração a 80% no site de testes): título, "eleitos consolidados", faixas, aviso, tabela e ficha na aba Candidato.
- **Sabotagens** (restauradas byte a byte): sem ruído, 2 falhas; limiar de 50%, 4 falhas.
- **Conferência visual:** retrato temporário da apuração real de 2022 às 20h03 (50%), com PL 17 (15–18), PT/PC do B/PV 8 (7–9) e "47 consolidados · 23 vagas em disputa entre 48". Depois foi removido.
- **Servidores** reiniciados nas portas 8000, 8022 e 8023; ambos os conjuntos de dados estão em 100%, e por isso sem projeção.

## Arquivos

- **Novos:** `apuracao/projecao_cadeiras.py`, `test_projecao_cadeiras.py`, `saidas/sigma_deputados.parquet`.
- **Alterados:**
  - `apuracao/cadeiras.py` (`_eleger`) e `apuracao/web/app.py`;
  - `apuracao/web/static/{app.js,style.css}`;
  - `validar_projecao.py` (`--deputados`), `conftest.py` (`tf` no TSE falso) e `test_cadeiras_e2e.py`;
  - `docs/TODO.md`, `docs/INDEX.md` e `CLAUDE.md`.

## Pendências

- **Validar fora da amostra:** deputados de outras UFs de 2022 (um `votacao_secao_2022_<UF>.zip` de centenas de MB para cada) ou os dados de 2026 depois da eleição.
- **Correlação entre candidatos:** o ruído é independente entre candidatos, mas candidatos do mesmo reduto erram juntos. Por enquanto a validação não mostrou problema.
- **Próximo item do TODO:** o 3, ensaio geral. O retrato montado aqui duas vezes vira o "tocador" da apuração de 2022.
