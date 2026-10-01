# Rodada 32 — Mapa por local de votação

30/09/2026 · pedido do usuário: "Siga para o item 10" (item 10 de `docs/TODO.md`, pendência da rodada 26)

## Objetivo

Pontos coloridos na aba Mapas, um por local de votação do estado, com três leituras:
- o voto;
- os indicadores de perfil do eleitorado;
- o resíduo do Perfil × voto: onde o voto foge do que o perfil do local prevê.

## Entregas

### `apuracao/mapa_locais.py` (novo) — `pontos(plocal, ano, camada, …)`

Tudo sai dos caches de `PerfilVotoLocal` (rodada 26); nada é recalculado à parte.

| Camada | Fonte | Escala |
|---|---|---|
| **voto** | as métricas do mapa por bairro (mais votado, % e votos de um candidato, brancos/nulos, abstenção/comparecimento): `bairros.metrica` sobre os votos por local (`PerfilVotoLocal._vb`); a participação vem de `participacao_por_bairro` com a UNIDADE do local | amarelo → vermelho (`--mapa-*`); mais votado: 3 cores + "Outros" |
| **perfil** | um indicador por local: TSE do ano (escolaridade, idade, sexo…) ou Censo 2022 por setor (raio de 800 m; renda, cor, densidade, favela…) | amarelo → vermelho |
| **resíduo** | o RESÍDUO da `dispersao` do Perfil × voto (p.p.): voto observado menos a reta voto × indicador; só locais com ≥ 50 votos válidos | divergente: azul = voto maior que o esperado, vermelho = menor, cinza = como esperado |

- **Partido:** no resíduo, um número de 2 dígitos em cargo proporcional é o **partido** (nominais + legenda), como no Perfil × voto.
- **Município:** o filtro (código IBGE) vale para todas as camadas; no resíduo, a reta é recalculada só com os locais do município.
- **Dados de cada ponto:** unidade, coordenada (cadastro de eleitorado do ano), nome, município, zona, local, eleitorado e valor; no resíduo, também o voto e o indicador.

### API

- **`GET /api/mapa/locais?ano=&camada=voto|perfil|residuo&cargo=&turno=&metrica=&numero=&indicador=&municipio=&min_validos=`**
  - guarda o resultado em cache;
  - está em `ROTAS_PESADAS`, então com o site na rede só atende a própria máquina;
  - pedido inválido responde 400; sem microdados, 404.
- **Exportação** (`POST /api/exportar/mapa`) com `camada: "locais"` e `ano`: os municípios em cinza por baixo e só os pontos que a página pintou, com área proporcional ao eleitorado, nas cores da tela (PNG, SVG ou JPEG).

### Página (aba Mapas)

- **Detalhe** tem a opção nova "Locais de votação (pontos)". Os anos e cargos vêm dos microdados no cache, como no modo por bairro, e não há linha do tempo (resultado final).
- **Controles:**
  - Camada: Voto, Perfil do eleitorado ou Resíduo;
  - Indicador, agrupado por fonte (TSE ou IBGE);
  - Área (estado ou um município);
  - o número (candidato, ou 2 dígitos para o partido) só se habilita quando a camada usa;
  - a caixa "Locais de votação" (pontos sem cor) some nesse modo, porque os pontos já são os locais.
- **Pontos:**
  - `circleMarker` em canvas, com raio proporcional à raiz do eleitorado (2,5 a 12 px) e anel na cor da superfície;
  - os maiores são desenhados primeiro, para os pequenos ficarem por cima e continuarem clicáveis;
  - ao passar o mouse: nome, município, zona/local, valor e eleitorado (no resíduo, também voto e indicador);
  - a legenda tem amostras redondas e a nota "Área do ponto ∝ eleitorado".
- **Faixas do resíduo:** quantis de |resíduo| (33%, 66% e 90%), não o máximo, porque com 5 mil pontos um local extremo achataria o resto.
- **Nota abaixo do mapa:** a cobertura e, no resíduo, a reta (r, R², n) e a explicação das cores. Se nenhum local tiver votos suficientes para o resíduo, a nota diz isso.
- **Endereço:** `#mapas?…&detalhe=locais&ano_bairros=2022&camada=residuo&indicador=pct_superior&numero=13713&municipio=3304557`, com "Copiar link".

## Números com os microdados de 2022 (RJ)

- **Cobertura:** 4.820 locais com coordenada; 4.813 com voto de Dep. Estadual e 4.811 com renda do Censo.
- **Tempo de resposta:** 0,1 a 2,2 s na primeira vez (a renda por setor é a mais lenta) e imediato depois.
- **Deputada 13713 (Dep. Estadual):**
  - de 0,0% a 14,0% dos válidos por local;
  - resíduo × "% com superior completo": r = 0,57 no estado e **0,72 na capital** (R² 0,52, 1.400 locais);
  - no mapa da capital, os pontos azuis (acima do esperado) se concentram no litoral da Zona Sul, e os vermelho-claros (abaixo) no litoral da Barra da Tijuca e do Recreio; leitura visual, sem teste estatístico por região.
- **PL (22, Dep. Federal) × renda média na capital:** r = 0,09. A renda quase não explica o voto no partido; o mapa de resíduos mostra onde ele foge disso.

## Correção no caminho

- **Exportação com a malha vazia:** se a malha de municípios estivesse vazia (por exemplo, IBGE fora do ar na primeira vez), a exportação quebrava. Agora desenha sem contorno. Achado no teste da API.

## Arquivos

- **Novos:**
  - `apuracao/mapa_locais.py`;
  - `test_mapa_locais_e2e.py`: 3 testes no Chrome.
- **Alterados:**
  - `apuracao/perfil_local.py`: `locais()` traz `QT_ELEITORES`;
  - `apuracao/web/app.py`: rota, cache, `ROTAS_PESADAS`, exportação de pontos;
  - `apuracao/web/exportar.py`: pontos e malha vazia;
  - `apuracao/web/static/{index.html,app.js,style.css}`;
  - `test_perfil_local.py`: 3 testes, com as três camadas no sintético (o resíduo confere `voto − (a + b·indicador)` e soma zero), a regra do partido, a API e a exportação SVG;
  - `CLAUDE.md`, `docs/TODO.md`, `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/INDEX.md`.

## Verificação

- **Testes:** `pytest -q` → **279 passando**, duas vezes seguidas (273 na rodada 31).
- **Ensaio geral:** **RESULTADO OK** em 14,2 min.
  - 52 ciclos, 5.901 arquivos, nenhum 404 e nenhum erro.
  - 5.015 consultas, nenhum 5xx; painel com p50/p95 de 145/1.009 ms.
  - 9 boletins; 7 alertas, nenhum crítico.
- **Visual no Chrome:**
  - voto da 13713 no estado, em tema claro;
  - resíduo na capital, em tema escuro;
  - renda do Censo e mais votado para governador;
  - celular a 390 px sem rolagem horizontal;
  - exportação PNG com 3 mil pontos.
- **No ar:** sites de teste 8000, 8022 e 8023 reiniciados com o código novo, e o portal na 8100. O mapa por local fica em http://localhost:8022, aba Mapas → Detalhe "Locais de votação (pontos)".

## Pendências

- **2026:** o mapa por local depende dos microdados, que saem dias depois do pleito (`preparar_2026.py --vigiar`). Com eles no cache, o ano 2026 aparece sozinho.
- **Camadas da rodada 30** (destino dos eliminados por local, resíduo do 2º turno): ficam como ideia para depois do 2º turno.
- **TODO:** todas as propostas do TODO estão feitas, exceto a 4b (recalibrar com 2026), que depende dos microdados.
