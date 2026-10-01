# Rodada 15 — Salvar mapas e gráficos (PNG/SVG/JPEG) e mapa por bairro

30/09/2026 · pedido do usuário: "(1) mostrar os bairros em cada município; (2) salvar o mapa em PNG, JPEG ou SVG", começando pela (2)

## (2) Salvar mapas e gráficos

**Mapas (abas Mapas e Comparação), servidor desenha:**
- **Pedido:** a página envia `POST /api/exportar/mapa` com a **cor de cada polígono e a legenda exatamente como estão na tela**. Assim o arquivo reproduz a tela: mesma classificação, escala fixa da linha do tempo e cores do tema.
- **Desenho:** o servidor usa matplotlib/geopandas e acrescenta título, subtítulo (cargo, UF, ambiente), legenda e rodapé (fonte, **link que reproduz o mapa**, data). O mapa de fundo do OpenStreetMap não é usado.
- **Formatos:**
  - **SVG** com **texto editável** (`svg.fonttype = none`), para Inkscape e Illustrator;
  - **PNG** a 200 dpi;
  - **JPEG** com qualidade 92.
- **Validação** (`apuracao/web/exportar.py`, HTTP 400): formato, cores (só `#hex`/`rgb()`), tamanho dos textos, até 10 mil polígonos e 30 itens de legenda, dpi entre 50 e 600.
- **Na página:** botões "Baixar mapa: PNG · SVG · JPEG" ao lado de "Copiar link".

**Gráficos de série (painel e aba Candidato), navegador exporta:**
- botões "Baixar gráfico: SVG · PNG";
- o SVG sai autônomo, com estilos calculados embutidos, fundo e legenda dentro do arquivo, e sem a camada de interação (linha-guia e área de mouse);
- o PNG é desenhado a partir desse SVG num canvas, com escala 3×.

## (1) Mapa por bairro

- **Malha:** bairros do IBGE, Censo 2022 (`RJ_bairros_CD2022.zip`, 3,2 MB). É baixada uma vez, simplificada (~20 m) e guardada em `cache_tse/malhas/bairros_RJ.geojson` (2,75 MB, 1.509 bairros).
- **Cobertura:** **31 dos 92 municípios** do RJ, os que têm bairros definidos em lei, com **79,3% do eleitorado 2026**. No Rio, 150 dos 162 bairros têm local de votação.
- **Método** (`apuracao/bairros.py`):
  - cada local de votação é posicionado pela coordenada do cadastro de eleitorado do ano (fallback: 2026) e contado no polígono que o contém (point-in-polygon, geopandas);
  - não se usa o bairro-texto do TSE, que no Rio coincide com o do IBGE em só 83% dos locais;
  - os votos de cada local vêm dos microdados por seção.
- **Métricas:** mais votado, % dos válidos e votos de um candidato, brancos + nulos. As demais (abstenção etc.) ficam desativadas nesse modo.
- **Quando existe dado:** só com microdados por seção, ou seja, 2022 e 2024 hoje e 2026 **dias depois** do pleito. O tempo real do TSE vai só até o município.
  - Sem microdados, a API responde 404 com mensagem clara, e a falha é memorizada por 10 min, para não repetir 404 no TSE.
- **API:** `GET /geo/bairros.geojson`, `GET /api/bairros/anos` (anos com microdados no cache, com os cargos de cada um; ZIP ainda não convertido é convertido na hora) e `GET /api/mapa/bairros?ano&cargo&metrica[&numero]&turno`.
- **Aba Mapas:**
  - seletor **Detalhe: Municípios | Bairros (IBGE)** e seletor de ano; os cargos seguem o ano (2024: Prefeito e Vereador);
  - a linha do tempo fica escondida;
  - os contornos dos municípios aparecem por cima, e municípios sem malha mostram só o contorno;
  - nota de cobertura ("919 de 1.509 bairros têm local de votação…");
  - ao voltar para Municípios, o cargo anterior é restaurado;
  - endereço: `#mapas?…&detalhe=bairros&ano_bairros=2022`;
  - a exportação funciona também por bairro (camada `bairros` + contornos dos municípios).
- **Títulos** (bairros e municípios) passam a trazer o candidato, por exemplo "% dos válidos do candidato — nº 22 CLÁUDIO CASTRO". Antes o título dizia só "do candidato".

**2022 real, Governador:** Castro foi o mais votado em 849 dos 919 bairros com dado. Os extremos vão de 91,2% em Provetá (Angra dos Reis) a 24,4% no Humaitá (Rio). O cálculo dos votos por bairro leva cerca de 0,1 s por cargo. Presidente leva cerca de 7 s na primeira vez, porque converte o arquivo nacional para o RJ.

## Verificação

- **`pytest -q`: 92 testes passando**, duas vezes seguidas (cerca de 20 s).
  - **Sem navegador (13, `test_exportar_bairros.py`):**
    - PNG/SVG/JPEG com as assinaturas corretas e SVG com o título acentuado como texto;
    - 5 casos de validação;
    - locais nos bairros certos (Niterói fora);
    - pct, votos, mais votado e brancos + nulos conferidos à mão (ex.: 13/138 e 16/51);
    - anos disponíveis;
    - falha de microdados sem repetir download;
    - rotas de bairros e de exportação (nome do arquivo, 400 e 422).
  - **Navegador (8, `test_exportar_bairros_e2e.py`):**
    - download do mapa nos 3 formatos, da comparação (JPEG) e do gráfico de série (SVG com 3 linhas e sem a camada de interação; PNG);
    - modo bairros: controles, cargos do ano, métricas desativadas, nota de cobertura, contornos, endereço e SVG com o candidato;
    - volta para Municípios com o cargo restaurado;
    - 2026 sem microdados: mensagem e nada para baixar.
- **Sabotagens do JavaScript** (restaurado byte a byte):
  - sem `mapa._export` → 5 testes falham;
  - sem a memória do cargo municipal → falha `test_voltar_para_municipios`. Esse teste encontrou o defeito real de a volta cair em Presidente, já corrigido.
- **Conferência visual:** mapa por bairro de 2022 no site da porta 8022 e o PNG baixado pelo navegador, com título, legenda, contornos e link no rodapé.

## Arquivos

- **Novos:** `apuracao/web/exportar.py`, `apuracao/bairros.py`, `test_exportar_bairros.py`, `test_exportar_bairros_e2e.py`.
- **Alterados:**
  - `apuracao/web/app.py`: rotas de exportação e de bairros, `malha_municipios()` reutilizável, candidato no título;
  - `apuracao/web/static/{index.html,app.js}`;
  - `conftest.py`: `escrever_bairros` com 2 bairros sintéticos, também no site dos testes de navegador;
  - `CLAUDE.md` e `docs/INDEX.md`.
- **Cache:** `cache_tse/malhas/{RJ_bairros_CD2022.zip, bairros_RJ.geojson}`.

## Pendências

- Setores censitários (granularidade ainda menor) e bairros de outras UFs: o código é parametrizado por UF, mas não foi testado fora do RJ.
- Bairros no modo Comparação 2022 × 2026, quando houver microdados de 2026.
