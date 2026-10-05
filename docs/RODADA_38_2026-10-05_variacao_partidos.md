# Rodada 38 — Variação por partido de 2022 para 2026: gráficos e estatística

05/10/2026 · pedido do usuário:
- "Como representar graficamente a variação dos candidatos a presidente do PT (Lula) e PL (Jair e Flávio
  Bolsonaro), de 2022 para 2026, há alguma ferramenta estatística que dê suporte a este gráfico?"
- Na aprovação: "Coloque no TODO esta sugestão" (a leitura ecológica e a inferência 2022 → 2026, item 22 do
  [TODO](TODO.md)).

## Resposta curta

Como o candidato do PL mudou (Jair → Flávio), a comparação é **por partido** (mesma sigla). A aba
Comparação 2022 × 2026 ganhou o bloco **"Gráfico da variação por partido"**, com até 3 partidos.

O bloco tem três peças:
- **Dispersão 2022 × 2026 por município:**
  - a diagonal y = x marca "sem mudança": acima dela o partido ganhou, abaixo perdeu;
  - cada partido tem a sua reta de tendência;
  - a área do ponto é proporcional aos válidos.
- **Faixa da variação (p.p.):** um ponto por município. Mostra a média, o intervalo de 95% (bootstrap dos
  municípios) e os 5 municípios mais distantes da média, rotulados quando cabem.
- **Fichas:**
  - a variação no estado;
  - a variação média por município (IC 95% e desvio-padrão);
  - a inclinação b com IC e o p do teste "b = 1";
  - o r de Pearson;
  - o **swing de Butler**: ((B₂ − A₂) − (B₁ − A₁)) / 2, no sentido do 1º para o 2º partido escolhido.

Uma tabela por município acompanha os gráficos, para acessibilidade e conferência.

## As ferramentas estatísticas e o que dizem (RJ, presidente, 1º turno, 92 municípios)

| | PT (Lula → Lula) | PL (Jair → Flávio) |
|---|---|---|
| Estado | 40,68% → 39,41% (−1,27 p.p.) | 51,09% → 53,01% (+1,92 p.p.) |
| Variação média por município (sem peso) | −3,25 p.p. (IC 95% −3,63 a −2,86; DP 1,87) | +3,36 p.p. (IC 95% +3,02 a +3,73; DP 1,76) |
| Inclinação b (2026 = a + b·2022) | 0,873 (IC 95% 0,829 a 0,918), p(b = 1) < 0,001 | 0,896 (IC 95% 0,853 a 0,938), p(b = 1) < 0,001 |
| r | 0,971 | 0,974 |
| Ponderado pelos válidos | b = 1,07 (IC 0,75 a 1,40), média −1,18 | b = 1,04 (IC 0,84 a 1,23), média +1,80 |

**Swing de Butler PT → PL:** +1,59 p.p. no estado e +3,30 p.p. na média dos municípios (IC 95% +2,96 a +3,67).

### Leitura
- **Movimento:** o eleitorado andou do PT para o PL em quase todos os municípios. Os pontos do PT ficam abaixo
  da diagonal e os do PL acima.
- **Municípios pequenos:** o movimento foi maior nos pequenos. Por município, a média é cerca de 3,3 p.p.;
  no estado, onde a capital pesa, fica perto de 1,6 p.p.
- **Convergência:** por município, b < 1 nos dois partidos. O partido variou mais a seu favor onde era fraco,
  e o voto ficou mais parecido entre os municípios. Parte disso pode ser **regressão à média**: municípios
  pequenos oscilam mais de uma eleição para outra. A página diz isso na leitura.
- **Ponderado:** a capital domina (n efetivo de Kish ≈ 6,6 de 92). O IC de b inclui 1, e o deslocamento parece
  uniforme. Por isso o padrão é **sem peso**: cada município é uma observação, como no Perfil × voto. Ponderar
  fica como opção, com o aviso "a capital domina".
- **Destaques:** Quissamã (PT −8,9, PL +8,7), Carmo, Trajano de Moraes e São Sebastião do Alto. Rio de Janeiro
  e Niterói ficam no sentido oposto (PT acima da média).

### Ressalvas que aparecem na página
- **População, não amostra:** os municípios são todos os do estado. O IC mede a dispersão entre eles.
- **Leitura ECOLÓGICA:** fala de municípios, não de pessoas. Quem migrou para quem fica para a inferência
  ecológica por seção, quando houver os microdados de 2026 (TODO 22).

## Entregas
- **Domínio:** `comparacao.variacao_partidos(a, b, cargo, partidos, ponderar=False, semente=0)`, sem I/O.
  - Reaproveita `_pct_partido` e `perfil.correlacao`.
  - Novos: `_reta_ponderada` (EP de b com pesos reescalados ao n efetivo, IC e p de b = 1 pela normal),
    `_media_bootstrap` (2.000 reamostragens, semente fixa) e `_leitura`.
  - Limite de 3 partidos (`MAX_PARTIDOS_VARIACAO`, regra da skill dataviz).
- **API:** `GET /api/comparacao/variacao?cargo=&partidos=PT,PL[&ponderar=true]`. Responde 404 sem referência
  e 400 com o motivo (partido inexistente, menos de 3 municípios). Um utilitário `_limpar` aplica `_jsonable`
  em profundidade.
- **Página:**
  - `graficoVariacao` (dispersão) e `graficoSwing` (faixas), com dica, legenda e exportação em SVG/PNG;
  - cores `--serie-1..3` na ordem da escolha, validadas com `validate_palette.js` nos dois temas (aviso de
    contraste do verde no claro, compensado com rótulos diretos e a tabela);
  - endereço `&var=1&var_partidos=PT,PL[&var_ponderar=1]`; no cargo de presidente, PT e PL vêm marcados.
- **Correções de front-end:**
  - **Ordem dos partidos:** é a da escolha, não a da lista. Ela define o sentido do Butler.
  - **Rótulos dos destaques:** ficam acima ou abaixo da faixa, sem sobreposição.
  - **Recarga do mesmo pedido** (o `abrirPorHash` roda duas vezes ao navegar durante a inicialização): o pedido
    não é duplicado e a tela não pisca "Carregando…". Vale também para o bloco da rodada 37, cujo teste e2e
    falhava de forma intermitente por isso.

## Verificação
- **`test_comparacao.py` (+4 testes):**
  - deslocamento uniforme: b = 1, DP 0, IC [2, 2] e Butler;
  - caso proporcional: b ≈ 1,5 com p < 0,001;
  - média ponderada conferida à mão e a mesma semente dando o mesmo IC;
  - os erros e a rota.
- **`test_enderecos.py` (+1 e2e):** a ordem do link, o limite de 3 partidos, a mensagem de erro e o endereço.
- **Suíte completa:** `pytest -q` com 329 passaram e 4 pulados; `test_enderecos.py` 4× seguidas sem falha.
- **Visual:** captura nos temas claro e escuro com os dados reais (instância somente leitura na porta 8001).
