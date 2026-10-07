# Rodada 52 — Destino dos eliminados (1º → 2º turno) por área de ponderação

06/10/2026 · pendência 1 da [RODADA_51](RODADA_51_2026-10-06_area_escala_divergente.md). Com esta camada, o mapa por
área de ponderação tem as cinco camadas do mapa por local: voto, perfil, resíduo, variação e transferência.

## Decisão: somar a inferência por local, não refazê-la com a área como unidade

A transferência por local (rodada 47) roda `transferencia.calcular` com o **local** como unidade e o **município**
como estrato. Para a área, a inferência não é refeita: os resultados de cada local são somados na área.

- **Grandezas observadas:** eliminados no 1º turno, abstenção nos dois turnos e voto do 1º finalista no 2º.
  - **Como entram:** médias dos locais ponderadas pelos aptos do turno de cada uma, ou seja, Σ contagens ÷ Σ aptos.
  - **Abstenção extra:** sai das somas.
- **Voto previsto do 1º finalista:** é linear nos percentuais do 1º turno (matriz do município × composição do
  local). Somado assim, dá a previsão da área quando os aptos do local são os mesmos nos dois turnos, o que acontece
  quase sempre: o cadastro é o mesmo, e mudam só seções agregadas ou não instaladas. O resíduo (observado − previsto)
  também sai das somas.
- **Destino dos eliminados:** é estimado por **município**, e toda área fica dentro de um só município (o código da
  área começa pelo dele). A área recebe o valor do seu município, o mesmo em todos os locais dela.
- **Por que não a área como unidade:** a área teria menos unidades por estrato (o Rio tem 209 áreas e milhares de
  locais), e a inferência ficaria mais frágil sem ganho.

## Entregas

- **`mapa_locais.transferencia_por_local`:** a inferência por local, com a UNIDADE do local.
- **`mapa_locais.camada_transferencia`:** monta a camada (métrica, rótulo, tipo, lados) a partir de linhas de local
  **ou** de área. `mapa_locais.transferencia` passou a usar as duas, sem mudar o comportamento.
- **`areas_ponderacao.transferencia_por_area`:** a soma descrita acima.
- **Camada nova em `areas_ponderacao.mapa`:** "transferencia", com as quatro métricas do mapa por local
  (`METRICAS_TRANSFERENCIA`).
  - **Sequenciais (%):** eliminados no 1º turno e destino dos eliminados.
  - **Divergentes (p.p.):** abstenção extra e resíduo do 1º finalista.
- **Página:**
  - **Camadas:** `CAMADAS_AREA` tem as cinco.
  - **Nota:** a nota da área explica a inferência ecológica e o destino por município.
  - **Consulta:** sai de `consultaCamada`, que já mandava `transf` e `turno=2`.

## Números reais (RJ, Presidente 2022, 1º → 2º turno)

| Métrica | Áreas | Tempo | Mínimo | Mediana | Máximo |
|---|---|---|---|---|---|
| Eliminados no 1º turno (% do eleitorado) | 754 | 4,0 s | 2,6 | 5,5 | 13,5 |
| Destino dos eliminados: % para Bolsonaro (por município) | 754 | 2,6 s | 8,4 | 34,9 | 75,1 |
| Abstenção extra no 2º turno (p.p.) | 754 | 2,6 s | −5,7 | −0,3 | +3,6 |
| Bolsonaro: observado − previsto (p.p.) | 754 | 2,5 s | −1,5 | 0,0 | +2,7 |

No Rio, as 209 áreas têm o mesmo destino dos eliminados (34,9%), como esperado da estimativa por município.

## Verificação

- **`test_destino_dos_eliminados_por_area`**, com a inferência por local simulada (o sintético não tem 2º turno):
  - **Médias:** abstenção do 1º turno, abstenção extra e resíduo da área Escola X + CIEP, ponderados por 300 e 100
    aptos.
  - **Destino:** o do município.
  - **Camadas:** sequencial e divergente, e o filtro por município.
- **e2e:** `test_area_destino_dos_eliminados` confere o controle de métrica, a nota de inferência ecológica e o
  endereço. As cinco camadas ficam habilitadas por área. O teste passou 3 vezes seguidas.
- **Suíte completa:** **430 ok**, 1 pulado.

## Arquivos

- **Pacote:** `apuracao/mapa_locais.py`, `apuracao/areas_ponderacao.py`.
- **Site:** `apuracao/web/static/app.js`.
- **Testes:** `test_areas_ponderacao.py`, `test_mapa_locais_e2e.py`.
- **Documentação:** `CLAUDE.md`, `docs/RODADA_51_…` (pendência apontada para cá).

## Pendências

1. **Erro amostral:** feito na [RODADA_53](RODADA_53_2026-10-06_erro_amostral_areas.md).
