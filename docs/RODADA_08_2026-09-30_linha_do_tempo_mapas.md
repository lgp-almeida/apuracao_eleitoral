# Rodada 08 — Linha do tempo por município nos mapas

30/09/2026 · pedido do usuário após a [rodada 07](RODADA_07_2026-09-30_serie_por_municipio.md)

## Objetivo

Levar a série temporal por município para a aba Mapas: ver o mapa como estava em qualquer momento da apuração.

## Como funciona

- **Momento t:** para cada município vale a **última totalização até t**. Município ainda sem totalização aparece como "sem dado".
- **Métricas:** todas as do mapa. % e votos de um candidato; mais votado; abstenção, comparecimento, brancos, nulos e brancos + nulos; seções totalizadas.
- **Fontes:** `historico_totais.parquet` para os totais municipais (o coletor já gravava cada totalização) e `historico_candidatos/` para os candidatos (rodada 07). Candidato ausente numa totalização = 0 voto, graças à linha de referência.
- **Escala de cores fixa** entre os quadros, calculada sobre o momento mais recente da mesma consulta; seções totalizadas usa faixas fixas de 0 a 100%. Sem isso, cores iguais significariam valores diferentes em cada quadro.
- **Cores do mais votado** presas ao candidato: os 3 primeiros **da UF no momento mais recente** (regra "a cor segue a entidade, não a posição").

## O que foi feito

- **`apuracao/divulgacao/serie.py`:**
  - `momentos(hist_totais, cargo)`: horas das totalizações municipais;
  - `totais_ate(...)`: totais municipais no momento;
  - `candidatos_ate(destino, cargo, momento[, número])`: candidatos no momento, lendo só o cargo nos blocos Parquet.
- **API:**
  - `GET /api/mapa` aceita `momento=<ISO>` e devolve `momento` na resposta; momento inválido → 400;
  - nova rota `GET /api/mapa/momentos?cargo`.
- **Aba Mapas:**
  - barra de linha do tempo com botão ▶/⏸ (um quadro a cada 0,9 s), controle deslizante e rótulo "hora · totalização k de N (mais recente)";
  - o título da legenda mostra "— às HH:MM";
  - com menos de 2 totalizações municipais do cargo, uma nota explica que a linha do tempo aparece depois;
  - a atualização automática a cada 60 s só redesenha se o usuário estiver no momento mais recente e não estiver reproduzindo; os momentos novos entram na barra sem mudar a posição de quem está vendo o passado.

## Verificação

- `pytest -q`: **51 testes passando**. O teste novo, `test_mapa_no_momento`, cobre:
  - momentos em ordem;
  - totais "como estavam" com o Rio a 50% às 18h30, os demais municípios com a totalização anterior e nada antes da primeira totalização;
  - candidato com 0 voto às 18h30 e 1.234 às 19h30;
  - mais votado no momento;
  - seções totalizadas;
  - rota com e sem `momento`;
  - momento inválido.
- **Demonstração** (TSE falso, 3 municípios totalizando em horas diferentes, 7 momentos): às 17h15 o Rio tinha 20% das seções e às 18h55, 95%. A barra foi conferida em captura do Chrome.
- **Simulado real:** um único momento (16h37 de 29/09), então a aba mostra a nota em vez da barra.

## Limitações

- Na demonstração, só os 3 municípios do TSE falso têm dados; na noite de 4/10, os 92 municípios entram à medida que totalizam.
- A posição da linha do tempo não vai para o endereço (`#mapas`); não é possível abrir um link direto num momento.
