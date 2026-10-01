# Rodada 13 — Testes automatizados dos endereços das abas

30/09/2026 · pedido do usuário após a [rodada 12](RODADA_12_2026-09-30_planilha_no_endereco.md)

## Objetivo

As rodadas 09–12 levaram o estado das abas Mapas, Candidato e Comparação para o endereço, com verificação só visual. Esta rodada cria testes automatizados. O código é JavaScript da página, então os testes rodam **num navegador de verdade**.

## Como

- **Playwright** (biblioteca Python, 1.63) com o **Chrome já instalado** (`channel="chrome"`): nenhum navegador é baixado. Sem Chrome, os testes são **pulados**, não quebram a suíte.
- **Servidor:** um por módulo de teste, numa porta livre (uvicorn numa thread).
- **Dados:**
  - 2026: TSE falso com 4 totalizações do cargo de Governador (Rio 20% às 17h10, Niterói 40% às 17h30, Rio 80% às 18h), para a linha do tempo existir;
  - referência 2022: o importador histórico sobre os microdados sintéticos de `test_historico.py`;
  - malha municipal e cadastro de eleitorado sintéticos.
- **Sem internet:** os ladrilhos do OpenStreetMap são bloqueados (`page.route`).
- **Marca `e2e`** (em `pytest.ini`, criado nesta rodada, que também silencia o aviso de depreciação do `TestClient`).
  - `pytest -q -m e2e`: só estes;
  - `pytest -q -m "not e2e"`: pula estes.

## Testes (`test_enderecos.py`, 10)

| Teste | O que prova |
|---|---|
| `test_mapa_link_abre_momento_e_regrava` | link com `momento=17:20` abre na "totalização 2 de 4" (a de 17h10), legenda "às…", endereço regravado com a hora exata; controle deslizante no fim remove `momento`; camada de locais → `locais=1`; ir ao Painel → `#painel` |
| `test_mapa_candidato_no_endereco` | métrica e número do link aplicados; trocar pelo formulário regrava o endereço |
| `test_candidato_link_completo` | município e ordem do link aplicados (tabela alfabética); ordenar por Votos e trocar município regravam `ordem` e `municipio` |
| `test_candidato_formato_antigo` | `#candidato/3/<n>/<mun>` abre o município e é convertido para o formato novo |
| `test_planilha_no_endereco` | bloco aberto com os campos do link (o nº da planilha prevalece sobre o do candidato); mudar o ano regrava; fechar o bloco remove `pl`/`pl_*` |
| `test_planilha_sem_consulta` | `#candidato?pl=1&…` abre só a planilha |
| `test_comparacao_partido` | cargo, métrica e partido aplicados (o partido depois de a lista carregar), tabela alfabética; ordenar por Diferença regrava `ordem` |
| `test_comparacao_candidatos_e_valores_invalidos` | par de números aplicado; cargo/métrica desconhecidos são ignorados (padrões mantidos) |
| `test_copiar_link` ×2 | "Copiar link" do mapa e da comparação põe na área de transferência exatamente a URL da tela |

## Verificação

- `pytest -q`: **61 testes passando** em cerca de 10 s (51 anteriores + 10 de navegador); `-m "not e2e"`: 51 em cerca de 5 s.
- **Os testes foram sabotados de propósito** para provar que detectam falhas. O `app.js` foi restaurado byte a byte depois:
  - `gravarEnderecoMapa` sem efeito → 2 testes de mapa falham. Na primeira versão, só 1 falhava; o teste de candidato no mapa foi reforçado para conferir a regravação, e não só a abertura do link;
  - `aplicarPlanilha` ignorando os campos → os 2 testes de planilha falham.

## Arquivos

- **Novos:** `test_enderecos.py`, `pytest.ini`.
- **Alterados:** `requirements.txt` (playwright), `CLAUDE.md` e `docs/INDEX.md`.
- **Instalado no venv:** playwright 1.63.0.
