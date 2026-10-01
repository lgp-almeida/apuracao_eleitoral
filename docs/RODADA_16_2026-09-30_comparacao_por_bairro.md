# Rodada 16 — Bairros na aba Comparação

30/09/2026 · pedido do usuário: "Adicione os bairros na aba Comparação"

## Objetivo

Comparar duas eleições **bairro a bairro**: qualquer ano e cargo de um lado contra qualquer ano e cargo do outro. Isso inclui cargos diferentes, como Deputado Estadual 2022 × Vereador 2024. Para o eleitorado, comparar dois cadastros.

## Entregas

- **Backend** (`apuracao/bairros.py`):
  - `numero_partido`: a partir do número do votável, 2 dígitos para candidato; legenda (< 100) é o próprio número; 95/96/97 não contam.
  - `valor_por_bairro`: devolve numerador, denominador e valor por bairro.
  - `ComparacaoBairros`: `comparar` gera a tabela por bairro e o resumo da área dos bairros; `partidos` lista os partidos dos dois lados, com a sigla de cada ano e o aviso quando a sigla mudou.
- **Métricas** (`METRICAS_COMPARACAO`):
  - brancos + nulos (p.p.);
  - eleitorado, em variação % entre dois cadastros, sem precisar de microdados de votos;
  - % dos válidos do partido (p.p.);
  - % dos válidos de um candidato de cada lado (p.p.).
- **Partido pelo número**, não pela sigla: 22 é PL em 2022 e 2024, e 13 era PR em 2024 e é PL em 2026. A lista mostra "sigla A → sigla B" quando a sigla muda.
- **Resumo da área:** soma numeradores e denominadores de todos os bairros com dado. Não é média de percentuais.
- **API:**
  - `GET /api/comparacao/bairros/info`: anos com votos, anos com cadastro, cargos por ano e métricas;
  - `GET /api/comparacao/bairros/partidos`;
  - `GET /api/comparacao/bairros?ano_a&cargo_a&ano_b&cargo_b&metrica[&partido|&numero_a&numero_b]&turno`;
  - erros: 400 para parâmetro inválido, 404 para ano sem microdados.
- **Página (aba Comparação):**
  - seletor **Detalhe: Municípios | Bairros (IBGE)**, com Ano A/Cargo A e Ano B/Cargo B; o cargo único fica escondido;
  - métricas sem dado por bairro ficam desativadas, e o 2026 de votos fica indisponível até sair o microdado;
  - mapa divergente com a camada de bairros e os contornos dos municípios por cima;
  - tabela "Por bairro", com linhas "Bairro — Município";
  - fichas com os valores da área dos bairros e nota com o subtítulo;
  - ao voltar para Municípios, tudo é restaurado;
  - quando não há microdados, uma mensagem clara aparece, o mapa é limpo e não há nada para baixar;
  - endereço: `#comparacao?cargo=&metrica=[&partido=|&numero_a=&numero_b=]&detalhe=bairros&ano_a=&cargo_a=&ano_b=&cargo_b=`;
  - a exportação PNG/SVG/JPEG usa a camada de bairros. O subtítulo é "Cargo ano × Cargo ano" ou "Cadastro de eleitorado A × B".

## Números reais (RJ)

- **PL (22):** 20,90% dos válidos para Deputado Estadual 2022 × 13,04% para Vereador 2024 na área dos bairros, **−7,86 p.p.** (939 bairros com dado). Leia http://127.0.0.1:8000/#comparacao?detalhe=bairros&ano_a=2022&cargo_a=7&ano_b=2024&cargo_b=13&metrica=partido&partido=22
- **Eleitorado da área dos bairros:** 10.341.145 em 2024 × 10.182.216 em 2026, **−1,54%** (955 bairros). Entre 2022 e 2026, −0,76%.

## Decisões e defeitos encontrados

- **Subtítulo:** o subtítulo vazio no eleitorado deixava o arquivo exportado sem dizer quais cadastros foram comparados. Agora traz "Cadastro de eleitorado 2024 × 2026", o que o teste de navegador verifica.
- **Siglas sem rede:** as siglas vêm do cadastro de candidatos do TSE (`historico.load_candidatos`). Nos testes de navegador, `ComparacaoBairros.siglas` é substituída no `conftest.py` (55 PSD, 22 PL), para nada ser baixado.
- **Teste de sigla:** um teste esperava "PR" comparando 2024 × 2024. Passou a usar 2024 × 2026 (13: PR → PL, com aviso de mudança).

## Verificação

- **`pytest -q`: 99 testes passando** (eram 92).
- **`test_exportar_bairros.py`**, 17 testes, dos quais 4 novos:
  - número do partido;
  - eleitorado entre cadastros;
  - partido e brancos + nulos conferidos à mão;
  - rota da API, com 400 e 404.
- **`test_exportar_bairros_e2e.py`**, 11 testes, dos quais 3 novos:
  - eleitorado 2024 × 2026: controles, métrica desativada, 2 bairros "— Rio de Janeiro", título "Por bairro", contornos, endereço e SVG com o subtítulo;
  - partido 55 (PSD) 2024 × 2024: sigla na lista e diferença de 0,00 p.p.;
  - 2026 sem microdados: mensagem, sem fichas, `_export` nulo, e a volta para Municípios restaura cargo e métricas e tira `detalhe` do endereço.
- **Sabotagem:** sem `detalhe=bairros` no endereço, `test_comparacao_por_bairro_eleitorado` falha. O `app.js` foi restaurado byte a byte (`cmp`).
- **Servidores reiniciados**, nas portas 8000 (simulado, com `--coletar`), 8022 e 8023 (2022, 1º e 2º turno). A API foi conferida com os números acima.

## Arquivos

- **Alterados:**
  - `apuracao/bairros.py` e `apuracao/web/app.py`, com as 3 rotas;
  - `apuracao/web/static/{index.html,app.js,style.css}`;
  - `conftest.py`, com as siglas sem rede;
  - `test_exportar_bairros.py` e `test_exportar_bairros_e2e.py`;
  - `CLAUDE.md` e `docs/INDEX.md`.

## Pendências

- Os votos de 2026 por bairro dependem dos microdados `votacao_secao_2026_RJ`, que o TSE publica dias depois do pleito. Quando saírem, o modo passa a aceitar 2026 sem mudança de código, porque `anos_disponiveis` converte o ZIP.
- Abstenção e comparecimento por bairro: o microdado por seção tem esses campos, mas a métrica ainda não foi exposta.
