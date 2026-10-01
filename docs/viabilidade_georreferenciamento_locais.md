# Viabilidade do georreferenciamento dos locais de votação (RJ)

29/09/2026 · medido com `python ingerir_eleitorado.py --ano <ano> --uf RJ --relatorio-geo` e com
a comparação 2024 × 2026 de `apuracao/locais.py`.

## Conclusão

**É viável mapear por ponto (local de votação) já.** Os cadastros de eleitorado do TSE trazem
latitude/longitude para praticamente todos os locais do RJ, com precisão de 6–7 casas decimais
(~10 cm a 1 m). Os mapas por **município** e por **setor censitário** também são viáveis,
porque os pontos permitem cruzamento espacial (*spatial join*) com as malhas do IBGE. Por
**bairro**, o campo `NM_BAIRRO` do TSE é texto livre e não é malha oficial. Serve para
agrupar em tabelas, mas não para desenhar polígonos.

## Medições

| Cadastro | Locais | Com coordenada | Fora do retângulo do RJ | Pontos com endereços distintos (locais) |
|---|---|---|---|---|
| 2022 | 4.820 | 100% | 0 | 4 (8) |
| 2024 | 4.971 | 100% | 0 | 3 (6) |
| 2026 | 5.062 | 99,88% (6 sem) | 0 | 15 (30) |

- **Precisão (2026, por seção):** 7 casas decimais em 34.698 seções, 6 em 3.596, 5 em 373 e 4 em 62.
- **Estabilidade entre anos:** 4.868 locais existem em 2024 e em 2026 com a mesma chave (município + zona + nº).
  - Mediana e percentil 90 do deslocamento: **0 m**; 4.673 locais têm exatamente o mesmo ponto.
  - 156 locais se deslocaram mais de 150 m e 47 mais de 1 km.
  - 14 locais "saltaram" mais de 5 km, e a planilha os aponta como `COORDENADA_SALTO_5KM`. Com a mesma chave, isso sugere erro de geocodificação em um dos anos, não mudança de endereço.
- **Formato:** em 2024 o separador decimal é `.`; em 2026 é `,`. Nos dois, `-1` significa ausente, e a conversão para Parquet já trata tudo isso.
- **Bairros:** o Rio tem 1.450 locais distribuídos em 161 bairros (texto normalizado). No estado são 1.656 grafias distintas. 95 locais mudaram de bairro entre 2024 e 2026 sem mudar de chave (`BAIRRO_DIVERGENTE`).

## Caminho para os mapas (frente (e))

1. **Pontos:** a aba "Por local" da planilha (`NR_LATITUDE`, `NR_LONGITUDE`, votos, %) já é uma camada de pontos, EPSG:4326. Dá para desenhar direto em Folium, Plotly ou Kepler.gl, com círculos proporcionais aos votos ou cor pela % sobre os válidos.
2. **Município:** agregar por `CD_MUNICIPIO`, converter o código TSE para IBGE (tabela de-para em `docs/geoprocessamento_eleitoral_tse_ibge.md`) e unir com a malha do `geobr.read_municipality`.
3. **Setor censitário ou zona desenhada:** `geopandas.sjoin(pontos, geobr.read_census_tract(...), predicate="within")`. Isso dispensa o casamento por CEP e endereço do CNEFE descrito no documento de geoprocessamento, porque o TSE já fornece o ponto.
4. **Mapas de calor e de diferença:** comparar candidatos ou anos no mesmo local, pela chave de local ou pelo ponto. Locais com `DESLOCADO`/`COORDENADA_SALTO_5KM` devem ser revisados antes de se comparar anos pelo ponto.

## Pendências

- `geobr` não está instalado no `venv` (necessário para os passos 2 e 3). A malha do IBGE também pode ser baixada direto do site.
- Os 6 locais sem coordenada em 2026 e os 14 saltos de mais de 5 km precisam de correção manual ou de geocodificação (Nominatim/CNEFE) se forem relevantes para o mapa.
- Revisar os locais que compartilham o mesmo ponto com endereços diferentes (30 em 2026). Pode ser geocodificação pelo centro da rua ou do bairro.
