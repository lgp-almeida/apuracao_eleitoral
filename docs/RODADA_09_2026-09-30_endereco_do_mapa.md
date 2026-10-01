# Rodada 09 — Linha do tempo (e demais controles) no endereço do mapa

30/09/2026 · pedido do usuário após a [rodada 08](RODADA_08_2026-09-30_linha_do_tempo_mapas.md)

## Objetivo

Poder abrir, favoritar e compartilhar um mapa exatamente como está na tela, inclusive num momento passado da apuração.

## Formato

```
#mapas?cargo=3&metrica=pct_candidato&numero=68&momento=2026-09-29T18:30:00&locais=1
```

| Parâmetro | Significado | Se ausente |
|---|---|---|
| `cargo` | 1, 3, 5, 6, 7 | o cargo selecionado (Governador) |
| `metrica` | valor do seletor "Mostrar" (`vencedor`, `pct_candidato`, `votos_candidato`, `abstencao_pct`, …) | `vencedor` |
| `numero` | candidato, nas métricas de candidato | — |
| `momento` | hora ISO; o mapa abre na **última totalização até essa hora** | acompanha o mais recente |
| `locais` | `1` liga a camada de locais de votação | desligada |

- `#mapas` sem parâmetros continua funcionando, e os demais endereços (`#candidato/…`, `#comparacao`) não mudaram.

## O que foi feito (só front-end: `apuracao/web/static/`)

- **`enderecoMapa()` / `gravarEnderecoMapa()`:** o endereço é regravado a cada desenho do mapa (controles, controle deslizante, ▶) e ao ligar ou desligar a camada de locais. Usa `history.replaceState`, então não enche o histórico do navegador nem dispara `hashchange`.
- **`momento`:** só é gravado quando a linha do tempo não está no mais recente. Um link sem `momento` continua acompanhando a apuração.
- **`aplicarEnderecoMapa()`:** aplica os parâmetros. O momento é guardado como "pedido" e convertido em posição da linha do tempo quando os momentos do cargo chegam (`carregarMomentos`: a comparação de texto ISO dá a última totalização ≤ hora pedida).
- **Troca de aba:** ao sair da aba Mapas, o endereço vira `#<aba>`.
- **Botão "Copiar link deste mapa"** (área de transferência); sem permissão, o link aparece na tela.

## Verificação

- **Visual** (demonstração do TSE falso com 7 momentos): o link `#mapas?cargo=3&metrica=secoes_totalizadas_pct&momento=2026-09-29T17:15:00` abriu com o seletor em "Seções totalizadas", a barra em "17:10 · totalização 2 de 7" (última até 17h15), o Rio com 20% e a legenda "— às 29/09/2026, 17:10:00". Conferido em captura e no DOM do Chrome em modo headless.
- `pytest -q`: 51 testes passando. A mudança é só de front-end e **não tem teste automatizado**; a verificação foi visual.

## Limitações

- O endereço da aba Candidato continua no formato de caminho (`#candidato/<cargo>/<número>/<município>`), sem os demais controles.
- Não foi testado se o endereço acompanha o botão ▶ quadro a quadro. Pelo código, ele é regravado a cada quadro.
