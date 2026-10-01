# Rodada 35 — Presidente por UF no cartão Brasil

01/10/2026 · pedido do usuário: acompanhar no domingo também a eleição presidencial com abrangência nacional. Antes de planejar, foi esclarecido que o cartão "Presidente — BRASIL" **não tem projeção**: ele mostra só o parcial oficial do TSE. A projeção (`projecao.py`) trabalha por município e só existe para a UF configurada. O usuário escolheu o **detalhe por UF, sem projeção nacional**.

## Objetivo

Até aqui, o coletor baixava o EA14 nacional (`br-e<fed>-ab.json`), mas descartava as linhas das UFs e guardava só a linha `br`. Ele também baixava o EA20 nacional do presidente. Para o Brasil, o site mostrava o total, a série e os candidatos, mas não dizia quais estados já tinham apurado, nem quem liderava em cada um.

## Entregas

- **Coletor** (`apuracao/divulgacao/coletor.py`):
  - as linhas das OUTRAS UFs do EA14 (26 + `zz`, o exterior) passam a ser abrangências da eleição federal. O EA20 do presidente na UF (`<uf>-c0001-e<fed>-u.json`, cerca de 10 kB) só é pedido quando o `dt/ht` daquela UF muda. Valem as mesmas regras de `_confirmar` e `TENTATIVAS_404` de antes;
  - os brutos vão para `raw_brasil/`. As tabelas vão para `ultimo/brasil_totais.parquet` e `ultimo/brasil_candidatos.parquet`, que trazem também o RJ, já coletado pelo caminho de antes e sem pedido extra;
  - nada disso entra em `raw/`, `ultimo/totais`, na série ou no histórico.
  - Opção `--sem-presidente-ufs` em `coletar_resultados.py` e `site_apuracao.py`.
- **Cópia de segurança** (`copia.py`): o espelho incremental cobre `raw/` e `raw_brasil/` (`RAIZES_BRUTAS`). O instantâneo da hora deixa as duas pastas de fora.
- **IBGE** (`ibge.py`): nova fonte `malha_ufs`, a malha do Brasil por UF da API `servicodados`, com qualidade mínima (98 kB, 27 feições, `codarea` = código IBGE da UF). Ela é baixada por `preparar_ibge.py` como as demais.
- **API** (`web/app.py`):
  - `presidente_por_uf(tot, cand)`, função pura. Para cada UF dá:
    - o % apurado, a hora e se a totalização é final;
    - o 1º e o 2º colocados, com a diferença em p.p.;
    - o % dos 3 mais votados no conjunto das UFs.
  - Ordem: UFs em ordem alfabética e o exterior ("Exterior") por último.
  - Rotas novas: `GET /api/presidente/ufs` (cache pela versão das duas tabelas) e `GET /geo/ufs.geojson` (503 se a malha faltar e o IBGE não responder).
- **Página** (`app.js` e `style.css`): bloco "Por estado" no fim do cartão "Presidente — BRASIL".
  - Mapa "Quem lidera": 3 cores e "Outros". O seletor "% de <candidato>" usa a escala `--mapa-1..5`. UF sem apuração fica cinza.
  - Tabela ordenável: UF (✓ = final), apurado, 1º e %, 2º e %, diferença.
  - O bloco é um nó persistente, devolvido ao cartão a cada redesenho do painel, para o mapa do Leaflet não ser recriado a cada minuto. Ele se atualiza junto com o painel.

## Decisões

- **Dados das outras UFs separados.** Vários consumidores filtram `ABRANGENCIA == "uf"` sem filtrar a UF: `serie.reconstruir*` lê todo o `raw/`, e há também `boletim.py`, `comparacao.py`, `ensaio.py` e `historico_totais`. Misturar SP ou MG nessas tabelas contaminaria séries, boletim e reconstruções.
- **Sem projeção nacional.** Foi a escolha do usuário. A margem calibrada em 2022 vale por UF, não para o total do Brasil.
- **Custo para o TSE.** Na 1ª coleta, 27 arquivos a mais. Depois, só a UF cuja totalização mudou. O EA14 já era pedido a cada ciclo.

## Verificação

- `pytest -q -m "not e2e"`: 252 passaram, 6 pulados (309 no total).
- `pytest -q -m e2e`: 57 passaram.
- Os testes novos:
  - `test_divulgacao.py`:
    - SP é pedido uma vez e de novo só quando muda o dt/ht dele;
    - SP vai para `raw_brasil/` e `brasil_*`, nunca para `raw/`, `totais`, `historico_totais` ou a série;
    - `presidente_ufs=False` não pede nada.
  - `test_site.py`: a rota e a função pura (exterior por último, UF sem apuração sem líder, os 3 mais votados no conjunto).
  - `test_copia_vigia.py`: espelho de `raw_brasil/`.
  - `test_painel_graficos.py` (e2e): tabela, cores dos dois mapas e o bloco que sobrevive ao redesenho.
  - A fixture do simulado ganhou `sp-c0001-e021270-u.json`.
- Simulado real (`coletar_resultados.py --ambiente simulado --uma-vez`): 493 arquivos (466 + 27). `brasil_totais` tem 28 linhas (27 UFs e o exterior). `ultimo/totais` ficou só com o RJ e a série só com BR e RJ. O site mostrou o mapa e a tabela com a malha real do IBGE.
- O ensaio geral não foi rodado nesta rodada: o `detalhe_votacao_secao_2022.zip` está incompleto no cache. O EA14 do ensaio só tem RJ e BR, então o comportamento dele não muda.

## Complemento: tabela no hint de cada UF

Pedido do usuário: no hint de cada estado do mapa, uma tabela com o % apurado, o % de cada candidato, brancos, nulos e abstenção. O custo é baixo: os dados já estavam em `brasil_*`, então não há pedido novo ao TSE.

- **`presidente_por_uf`**: cada UF ganha:
  - `candidatos`, com todos os candidatos em ordem de votos (número, nome, partido, votos e % dos válidos);
  - `brancos`/`pct_brancos`, `nulos`/`pct_nulos`, `abstencao`/`pct_abstencao` e `comparecimento`.
  - Os percentuais vêm prontos do TSE: brancos e nulos sobre o total de votos, abstenção sobre o eleitorado.
- **Página**: `dicaUf` monta a tabela (`.tabela-dica`):
  - cabeçalho com a UF, o % apurado, a hora e "FINAL";
  - o valor da métrica escolhida;
  - os candidatos, com o líder em negrito;
  - brancos, nulos e abstenção.
- **Bug encontrado na conferência visual:** com 12 candidatos, a tabela é mais alta que o mapa (360 px), e o tooltip do Leaflet, desenhado dentro do mapa, saía cortado. A dica passou a ser um elemento `position: fixed` no `body` (`mostrarDica`/`posicionarDica`/`esconderDica`), que acompanha o mouse e fica presa à janela.
- **Verificação:**
  - `pytest -q`: 309 passaram, 6 pulados;
  - `test_site.py` confere os campos novos com o `brasil_totais.parquet`;
  - o e2e passa o mouse de verdade sobre SP e confere a tabela inteira dentro da janela e a dica escondida ao sair;
  - no simulado real, o hint de SP mostrou 13 candidatos, brancos 6,64% (2.020.082), nulos 6,68% (2.032.809) e abstenção 14,86% (5.312.531), iguais aos do Parquet.

## Pendências

- Na máquina da noite, rodar `python preparar_ibge.py` para baixar `malhas/ufs_BR.geojson`. Sem a malha, o site tenta baixá-la na primeira vez; se não conseguir, mostra só a tabela.
- Reiniciar o site que estiver no ar para carregar o coletor novo.
