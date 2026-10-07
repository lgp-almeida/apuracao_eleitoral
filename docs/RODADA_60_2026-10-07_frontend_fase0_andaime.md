# Rodada 60 — Front-end, fase 0: andaime Vite + TypeScript (07/10/2026)

Ramo `frontend-refatoracao`. Esta rodada só entra em `main` depois do 2º turno (25/10). Plano completo em
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 0.

## Objetivo

Pôr a página num build Vite + TypeScript sem mudar nada do que ela faz. É a base das fases seguintes, em que o
código sai do arquivo único aos poucos.

## Entregas

- **Fonte em `apuracao/web/frontend/`:**
  - `index.html`, `src/main.ts` (entrada), `src/legado.js` (o antigo `app.js`, movido com `git mv`) e
    `src/estilos/style.css`;
  - `package.json` com versões exatas e mais de duas semanas de publicadas: `leaflet` 1.9.4 (a mesma do vendor),
    `vite` 8.3.0, `typescript` 6.0.3, `@types/leaflet` 1.9.21, `@types/node` 20.19.43; mais o `package-lock.json`;
  - dois tsconfig strict: `tsconfig.json` para a página (DOM) e `tsconfig.node.json` para `vite.config.ts` e
    `construcao.ts` (Node).
- **Build versionado em `apuracao/web/static/`:** `index.html`, `assets/index-<hash>.{js,css}`, `build.json` e
  `licencas/leaflet.txt`. O build é reprodutível: dois builds seguidos dão os mesmos bytes. Usa `base: "./"`, e o
  site de várias UFs foi conferido no ar: `/ac/` carrega `./assets/…` com 200.
- **Leaflet do npm** com `import * as L`. A pasta `static/vendor/` saiu.
- **Cache:** `assets/*` vai com `public, max-age=31536000, immutable`, porque o nome tem o hash do conteúdo. O
  `index.html` continua `no-cache`. Um 404 em `assets/` não recebe `immutable`.
- **`test_frontend_build.py`** (pytest, sem Node): refaz a impressão digital da fonte (SHA-256 de
  `frontend/construcao.ts`, com a lista de arquivos lida do próprio `.ts`) e compara com `static/build.json`.
  Testado: uma linha a mais em `src/main.ts` sem build novo faz o teste falhar. Ele também confere que a página
  só usa caminhos relativos `./assets/…` e que esses arquivos existem.
- **Ponto de acesso dos e2e:** `window.__apuracao = { estado, alertas, tf, tocar, api, desenharPainel,
  atualizarPainel, atualizarAlertas, consultarCandidato, partidosVar }`. Num módulo, os nomes de topo deixam de ser
  globais. Os testes foram trocados mecanicamente (`estado.` → `__apuracao.estado.` etc.) e nenhuma asserção mudou.
  O som dos alertas passa por `window.__apuracao.tocar`, para o teste poder substituí-lo como fazia com
  `window.tocar`.

## Números

| | Antes (gzip) | Depois (gzip) |
|---|---|---|
| JS (app.js + leaflet.js) | 51,3 + 42,3 KB | 80,5 KB |
| CSS (style.css + leaflet.css) | 5,5 + 3,5 KB | 10,6 KB |
| **Total** | **102,6 KB** | **91,1 KB** |

## Decisões e desvios da proposta

- `checkJs` fica desligado no `legado.js`. Ligar `@ts-check` em 3.100 linhas sem tipos derrubaria o
  `typecheck`. Os tipos chegam à medida que o código sai do legado (fase 1 em diante).
- ESLint e Vitest ficaram para a fase 1, junto com o primeiro código puro a testar (`core/`).
- O build não gera sourcemap (seria 1 MB a mais por commit). Para depurar, use `npm run dev`: o proxy manda
  `/api`, `/geo` e `/ufs.json` para o site Python, por padrão em `localhost:8000` (`APURACAO_SITE`).
- Correção da proposta: são **70** testes e2e, não 64.

## Verificação

- `npm run typecheck` e `npm run build` sem erro.
- `pytest -m e2e`: 70 passaram. `pytest -m "not e2e"`: 413 passaram e 1 foi pulado.
- `site_apuracao.py --ambiente oficial --ufs todas`: a página e os assets saem com 200 e com os cabeçalhos de
  cache esperados.

## Pendências

- Fase 1 (núcleo): `core/` (dom, api com tempo-limite, pedidos, agendador, formatos, preferências), `tipos/api.ts`,
  Vitest e ESLint (com a regra que proíbe `innerHTML`).
- Na máquina da noite não é preciso Node. Para quem mexer no front-end:
  `cd apuracao/web/frontend && npm ci && npm run build`.
