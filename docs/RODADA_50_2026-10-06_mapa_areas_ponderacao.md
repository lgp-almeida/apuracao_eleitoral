# Rodada 50 — Mapa por área de ponderação (TODO 25)

06/10/2026 · item 25 do [TODO](TODO.md), proposto na [RODADA_49](RODADA_49_2026-10-06_censo_amostra_e_universo.md).
Lá, a área de ponderação do Censo 2022 virou unidade do Perfil × voto; aqui ela ganha mapa.

## Entregas

### Malha das áreas — `areas_ponderacao.malha(uf, cache)`

- **Como é feita:** é a fusão (`dissolve`) dos setores da malha do IBGE, ligados a cada área pela composição
  oficial (`ap_composicao.parquet`).
  - **Simplificação:** `SIMPLIFICAR_GRAUS` = 0,0006° (~60 m), com coordenadas a 5 casas (~1 m).
  - **Propriedades:** `CD_AP`, `NM_AP`, `NM_MUN`, `CD_MUN`.
  - **Área sem moradores:** não tem tabela no IBGE e fica como "Área NNN".
- **Tamanho e tempo:**

  | | Áreas | Gerada em | Sem simplificar | Simplificada |
  |---|---|---|---|---|
  | RJ | 826 (771 com moradores) | 6 s | 4,2 MB | **1,5 MB** |
  | SP | 2.535 | 17 s | 16,7 MB | **5,9 MB** |

  Para comparar, a malha de bairros do RJ tem 2,7 MB, e o site não comprime as respostas.
- **Cache:** `cache_tse/malhas/areas_ponderacao_<UF>.geojson`, derivado no `ibge.py` da malha de setores, da
  composição e das tabelas (de onde vêm os nomes). O `ibge.atualizar` refaz a malha quando qualquer um deles muda.

### Valores — `areas_ponderacao.mapa(pva, ano, camada, …)`

- **Formato:** o do mapa por bairro (`itens` pelo código da área, `tipo`, `rotulo`, `unidade`, `cobertura`,
  `categorias` no "mais votado"). Assim a página reaproveita o `desenharMapa`.
- **Camada "voto":** as métricas do mapa por bairro sobre `PerfilVotoArea._vb`, os votos dos locais da área.
  - **Abstenção e comparecimento:** somam abstenções e aptos dos locais (Σ ÷ Σ), nunca a média dos percentuais.
  - **Rótulo:** "Mais votado na área".
- **Camada "perfil":** qualquer indicador da unidade área: o eleitorado do TSE, o universo do Censo e a amostra
  (religião, instrução, renda per capita…). A fonte vai em `fonte_indicador`.
- **Áreas mostradas:** só as que têm local de votação. O filtro por município usa os 7 primeiros dígitos do código.
- **Fora do mapa por área:** resíduo, variação e transferência. O `desenharMapa` só pinta escalas sequenciais e
  categóricas, e o TODO pedia voto e perfil.

### API

- **Rotas novas:** `GET /geo/areas.geojson` e `GET /api/mapa/areas` (cache das últimas 24 consultas). As duas
  estão em `ROTAS_PESADAS`, como as de bairros.
- **Exportação:** `POST /api/exportar/mapa` aceita `camada: "areas"`, com o contorno dos municípios.

### Página (aba Mapas)

- **Detalhe novo:** "Áreas de ponderação (IBGE)".
  - **Camadas:** só voto e perfil; as outras ficam desabilitadas.
  - **Indicadores:** os da unidade área. `prepararLocais(unidade)` passou a guardar as informações por unidade.
  - **Município:** enquadra as áreas do município escolhido.
  - **Nota:** `#areas-nota` cita a cobertura, a regra do local → área e o erro amostral nos indicadores da amostra.
- **`desenharMapa`:** a camada `"areas"` tem borda fina e o contorno dos municípios por cima, como os bairros.
- **Endereço:** `#mapas?…&detalhe=areas&ano_bairros=&camada=voto|perfil&indicador=&municipio=`.
- **Exportação:** o subtítulo é "áreas de ponderação do Censo 2022 (IBGE)".

### Defeito encontrado e corrigido: resposta atrasada

- **O problema:** trocar a camada e logo o indicador dispara dois pedidos. Se o primeiro respondia por último, o
  mapa ficava com o indicador errado.
- **Como apareceu:** o e2e novo falhava de vez em quando.
- **Correção:** `atualizarMapaAreas` e `atualizarMapaLocais` (mapa por local, rodada 32, que tinha a mesma corrida)
  numeram os pedidos com um contador **único** (`estado.pedidoMapa`, `novoPedidoMapa`) e descartam a resposta
  superada. Um contador só para os dois detalhes também cobre a troca rápida local ↔ área.
- **Teste determinístico:** `test_troca_rapida_vale_o_ultimo_pedido` segura a resposta do 1º pedido
  (`page.route`) até o 2º desenhar e só depois a libera.
  - **Sem a correção:** falha ("% com superior completo" por cima de "Renda média").
  - **Com ela:** passa 5 vezes seguidas.

## Números reais (RJ, Presidente 2022, 1º turno)

| Camada | Áreas com valor | Tempo | Faixa |
|---|---|---|---|
| % de Bolsonaro | 754 / 754 | 1,3 s (1ª vez: votos) | 27,1% – 74,2% |
| Mais votado | 754 / 754 | < 0,1 s | — |
| Abstenção | 754 / 754 | < 0,1 s | 13,9% – 33,2% |
| % de evangélicos (amostra) | 754 / 754 | 0,1 s | 4,3% – 56,1% |
| Renda per capita mediana (amostra) | 754 / 754 | < 0,1 s | R$ 500 – R$ 8.000 |

## Arquivos

- **Pacote:** `apuracao/areas_ponderacao.py` (`malha`, `mapa`, `CAMADAS_MAPA`), `apuracao/ibge.py` (derivado
  `malhas/areas_ponderacao_{uf}.geojson` + gerador).
- **Site:** `apuracao/web/app.py` (rotas, exportação), `apuracao/web/static/{index.html,app.js}`.
- **Testes:** `test_areas_ponderacao.py` (+4) e `test_mapa_locais_e2e.py` (+2: áreas e troca rápida).
- **Documentação:** `docs/TODO.md` (item 25 feito), `CLAUDE.md` (módulo e endereço).

## Verificação

- **Testes novos:**
  - **Malha:** 5 setores sintéticos → 3 áreas, e cache na 2ª chamada.
  - **Valores:** voto igual ao do Perfil × voto por área, perfil, filtro por município e camada inválida.
  - **Abstenção:** Σ abstenções ÷ Σ aptos.
  - **API:** malha, voto, perfil, indicador inválido (400) e exportação SVG.
  - **e2e:** rampa de cores, camadas desabilitadas, religião no perfil, endereço de ida e volta com município.
    Passou 5 vezes seguidas depois da correção da corrida.
- **Suíte completa:** **424 ok**, 1 pulado.

## Pendências

1. **Escala divergente:** feita na [RODADA_51](RODADA_51_2026-10-06_area_escala_divergente.md) (resíduo e variação por área).
2. **Erro amostral:** marcar no mapa as áreas com coeficiente de variação alto nos indicadores da amostra.
