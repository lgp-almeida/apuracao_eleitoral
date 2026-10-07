# Rodada 51 — Escala divergente no mapa por área: resíduo e variação

06/10/2026 · pendência 1 da [RODADA_50](RODADA_50_2026-10-06_mapa_areas_ponderacao.md). O mapa por área de ponderação
só tinha voto e perfil, porque o `desenharMapa` (polígonos) só pintava escalas sequenciais e categóricas.

## Entregas

### Backend — `areas_ponderacao.mapa`

- **Camada "residuo":** o resíduo do Perfil × voto por área (`PerfilVotoArea.dispersao`).
  - **Número:** de 2 dígitos em cargo proporcional, conta como o partido (`mapa_locais.alvo`).
  - **Na resposta:** vem a estatística da reta, e cada área traz `voto` e `indicador` para a dica.
- **Camada "variacao":** a métrica no `ano` menos a de `ano_ref` (padrão ano − 4), em p.p.
  - **Regra:** a mesma do mapa por local (`mapa_locais.variacao`: partido pela entidade; partido novo é recusado).
  - **Diferença:** a área não muda entre eleições, porque é a do Censo 2022. Os locais de cada ano entram na
    área do setor que os contém, então não é preciso casar locais entre anos, como no mapa por local.
- **Participação:** `PerfilVotoArea.participacao` soma abstenções, comparecimento e aptos dos locais da área.
  - **Uso:** a camada "voto" e a "variacao".
  - **Desvio:** `mapa_locais.participacao` pergunta à unidade antes de usar `_participacao` (por local).
- **API:** `GET /api/mapa/areas` aceita `min_validos` e `ano_ref`.

### Página

- **`escalaDivergente(vals, sentido)`:** saiu do `desenharPontos` e passou a ser comum aos pontos (locais) e aos
  polígonos (áreas).
  - **Faixas:** pelos quantis de |valor|, sete cores `--div-*`: azul acima de zero, vermelho abaixo.
  - **Legenda:** "subiu/caiu" na variação; "maior/menor que o esperado" no resíduo.
- **`desenharMapa`:** ganhou o ramo divergente.
  - **Formato:** os valores em p.p. com sinal (`fmtPP`).
  - **Dica:** traz os dois lados da conta, "2022: x% → 2026: y%" na variação e "voto · indicador" no resíduo.
- **Consulta comum:** `consultaCamada` monta os parâmetros da camada (métrica, número, indicador, município) para
  os dois detalhes. Antes, o mapa por local tinha a sua cópia.
- **Por área:** só a transferência continua desabilitada.
- **Nota:** `notaDivergenteArea` traz a reta (r, R², áreas com o mínimo de votos) e o aviso de que a área é a
  mesma nos dois anos.

## Números reais (RJ)

| Camada | Áreas | Tempo | Mínimo | Mediana | Máximo |
|---|---|---|---|---|---|
| Resíduo: Bolsonaro 2022 × % de evangélicos (≥ 200 válidos) | 754 | 1,4 s | −18,9 | +0,4 | +20,2 p.p. (r = 0,62) |
| Variação do % do PL, Presidente 2022 → 2026 | 746 | 1,0 s | −6,1 | +1,9 | +12,1 p.p. |
| Variação da abstenção, Presidente 2022 → 2026 | 746 | 3,0 s | −13,3 | +0,7 | +8,7 p.p. |

## Arquivos

- **Pacote:** `apuracao/areas_ponderacao.py` (camadas, `PerfilVotoArea.participacao`), `apuracao/mapa_locais.py`
  (`participacao`).
- **Site:** `apuracao/web/app.py` (parâmetros da rota), `apuracao/web/static/app.js`.
- **Testes:** `test_areas_ponderacao.py` e `test_mapa_locais_e2e.py`.
- **Documentação:** `CLAUDE.md`.

## Verificação

- **Resíduo:** sem reta com 3 áreas sintéticas (o mínimo é 5), e o mapa sai vazio com a estatística. Com uma
  dispersão simulada, sai o resíduo e a dica traz o voto e o indicador.
- **Variação:** 2024 − 2020 por área, com participação simulada. A área sem 2020 sai, e `ano_ref` ≥ `ano` é
  recusado.
- **e2e:** polígonos nas cores `--div-*`, legenda subiu/caiu/estável, nota e endereço, com a resposta da API
  pronta (o sintético só tem 2024). Só a transferência fica desabilitada por área. O teste passou 3 vezes
  seguidas.
- **Suíte completa:** **428 ok**, 1 pulado.

## Pendências

1. **Destino dos eliminados por área:** feito na [RODADA_52](RODADA_52_2026-10-06_area_transferencia.md) (inferência
   por local somada na área).
2. **Erro amostral:** marcar no mapa as áreas com coeficiente de variação alto nos indicadores da amostra.
