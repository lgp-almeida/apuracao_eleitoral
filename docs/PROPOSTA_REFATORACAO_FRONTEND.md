# Proposta: refatoração do front-end do site (Vite + TypeScript + design system)

Data: 2026-10-07. Situação: **em execução no ramo `frontend-refatoracao`** — fases 0 a 3 e parte da 4 feitas ([RODADA_60](RODADA_60_2026-10-07_frontend_fase0_andaime.md), [RODADA_61](RODADA_61_2026-10-07_frontend_fase1_nucleo.md), [RODADA_62](RODADA_62_2026-10-07_frontend_fase2_roteador.md), [RODADA_63](RODADA_63_2026-10-07_frontend_fase3_componentes.md), [RODADA_64](RODADA_64_2026-10-07_frontend_fase4_transferencia_perfil.md), [RODADA_65](RODADA_65_2026-10-07_frontend_fase4_comparacao_candidato.md)). Pedido do usuário: planejar, com a skill
`frontend-design`, uma refatoração que deixe o front-end robusto, manutenível e mais limpo. Decisões do usuário:

- **Visual:** reorganizar o código e criar um design system com polimento contido. A paleta dos mapas (YlOrRd,
  rodada 31) e as cores da dataviz não mudam.
- **Ferramental:** build completo com **Vite + TypeScript** (Node 20 já está na máquina, via nvm). Em produção,
  o site continua sem Node.

Acompanhamento: item 27 do [TODO.md](TODO.md).

## 0. Ponto de partida

O front-end do site (`apuracao/web/static/`) cresceu por 59 rodadas sem ser reorganizado:

- `app.js` tem 3.117 linhas (183 KB) num arquivo só e 177 chamadas a `document.getElementById` espalhadas pelo código.
- Um objeto `estado` global guarda uns 40 campos soltos (`compFeito`, `varPedido`, `histEmCurso`…).
- Seis pares `enderecoX`/`aplicarEnderecoX` fazem o mesmo trabalho, cada um de um jeito.
- Quatro contadores de "resposta atrasada" foram escritos à mão (`pedidoMapa`, `histPedido`, `varPedido`, `bancPedido`).
- O Leaflet recalcula o tamanho por `setTimeout(…, 50)`.
- `style.css` tem 388 linhas, sem camadas.

O que está bom e fica:

- nenhum `innerHTML`: todo texto do TSE entra por `textContent`;
- os tokens de cor da dataviz e a paleta YlOrRd dos mapas;
- os endereços `#aba?…` das abas;
- os 64 testes e2e em 11 arquivos, que são a rede de segurança da refatoração.

## 1. Diagnóstico (com números)
- `app.js`: 3.117 linhas, 0 `innerHTML`, 76 `addEventListener`, 177 `getElementById`, 44 `catch`.
- Estado global misturado: abas, caches de malha (`geo`, `geoBairros`, `geoAreas`), mapas Leaflet
  (`mapa`, `mini`, `compMapa`, `brasilMapa`), flags de "já iniciou" e contadores de pedido no mesmo objeto;
  `tf`, `alertas` e `estado.pf` são estados paralelos com outro formato.
- Roteamento: `abrirPorHash` (≈35 linhas de `if`) + 6 pares `endereco*`/`aplicarEndereco*`; a lista de abas
  aparece repetida em 3 lugares.
- Concorrência: proteção contra resposta atrasada só em 4 pontos e cada um à sua maneira; `tick` a cada 60 s
  pode se sobrepor a si mesmo; nenhum `fetch` tem tempo-limite; erro numa aba vira texto num `<p>` diferente
  em cada lugar.
- Gráficos: `graficoLinhas`, `graficoDispersao`, `graficoVariacao`, `graficoSwing` repetem eixos, escalas,
  marcas e dica; há duas dicas (`mostrarDica` fixa e `comDica` em SVG).
- Mapas: `desenharMapa`, `desenharPontos` e `desenharDivergente` repetem legenda, quebras e estilo.
- CSS: um arquivo, tokens só de cor; tamanhos de fonte, espaçamentos e raios soltos em cada regra.
- Testes e2e acessam globais (`estado.mapa` 13×, `estado.compMapa`, `estado.brasilMapa`, `desenharPainel()`).
- Não há teste unitário de JS: formatação, escalas e endereços só são testados pelo navegador.

## 2. Objetivos e critérios de aceite
- Nenhum módulo com mais de ~400 linhas; uma aba = uma pasta.
- `tsc --strict` sem erro; ESLint sem erro; Vitest para todo código puro.
- Os 64 e2e passam **sem mudar asserções** (só o acesso aos globais passa pelo calço da §6).
- Produção continua sem Node: o build é versionado e servido pelo FastAPI como hoje.
- Bundle gzip ≤ o atual (app.js + style.css + Leaflet).
- Comportamento e endereços `#aba?…` idênticos (inclusive o formato antigo `#candidato/<cargo>/<nº>`).

## 3. Ferramental
- Fonte em `apuracao/web/frontend/` (`package.json`, `package-lock.json`, `tsconfig.json` strict,
  `vite.config.ts`, `eslint.config.js`, `src/`, `tests/`).
- `vite build` grava em `apuracao/web/static/` (versionado, como hoje). `base: "./"` — caminhos relativos são
  obrigatórios porque o site de várias UFs monta cada uma em `/<uf>/` (`web/multi.py`).
- Nomes com hash em `static/assets/`; `web/app.py` (linha ~1247) passa a mandar `Cache-Control: immutable`
  para `assets/*` e mantém `no-cache` no `index.html`.
- Dependências fixadas (`npm ci` + lock), poucas: `leaflet@1.9.4` (mesma versão do vendor, que sai),
  `@fontsource/public-sans`; dev: `vite`, `typescript`, `vitest`, `eslint`, `typescript-eslint`, `happy-dom`.
  `npm audit` entra no checklist de revisão, como o `pip-audit`.
- `.gitignore` (lista de permissão): ignorar `node_modules/` e permitir `apuracao/web/frontend/`.
- Teste novo em pytest (`test_frontend_build.py`, sem Node): o `static/build.json` gerado pelo build guarda o
  hash da árvore `frontend/src`; se a fonte mudou e o build não, o teste falha. Assim ninguém sobe fonte sem build.

## 4. Arquitetura proposta (`frontend/src/`)
```
main.ts                  boot: monta abas, roteador, agendador, alertas, seletor de UF
core/
  dom.ts                 el(), svg() (os de hoje, tipados) + refs(raiz, {chave: "#id"}) que falha no boot se faltar id
  api.ts                 api<T>(rota, {sinal, tempoLimite=20s}); ErroApi com status e detail
  pedidos.ts             Canal: cada novo pedido aborta o anterior (AbortController) — substitui os 4 contadores
  agendador.ts           repete tarefas sem sobreposição; pausa o refresh pesado com document.hidden (alertas não)
  rotas.ts               tabela única de abas; cada aba declara ler(URLSearchParams)/escrever(): URLSearchParams
  formatos.ts            int, pct, hora, fmtPP, p1, mil, fmtR, fmtP… (hoje espalhados)
  preferencias.ts        localStorage com try/catch
tipos/api.ts             tipos das respostas das 46 rotas que a página usa (campos consumidos)
componentes/
  tabela.ts              tabelaOrdenavel
  grafico/               base (escalas, eixos, passos, dica) + linhas, dispersao, variacao, swing
  mapa/                  criarMapa (ResizeObserver no lugar de setTimeout), camadas coroplética/pontos/
                         divergente, escalas (quebrasQuantis, escalaDivergente), legenda
  dica.ts                uma dica só (position: fixed, fora do mapa — a decisão da rodada 35)
  exportar.ts            svgAutonomo, baixarGrafico, baixarMapa
  estados.ts             carregando / vazio / erro com "Tentar de novo"
abas/<painel|candidato|mapas|comparacao|perfil|transferencia>/
  index.ts               implementa Aba { iniciar(), ativar(params), desativar(), endereco(), atualizar?() }
  estado.ts              o estado DA aba (sai do objeto global)
  *.ts                   blocos (ex.: painel/cartao.ts, projecao.ts, cadeiras.ts, brasil.ts, tv.ts)
alertas/                 vigia da página (faixa, som, título, acompanhar)
estilos/                 ver §5
```
Regras: domínio (escalas, formatos, rotas, cores por papel) sem DOM e testado no Vitest; texto do TSE só por
`textContent` (regra de lint proibindo `innerHTML`/`insertAdjacentHTML`); nenhum módulo lê id de outra aba.

## 5. Design system (skill frontend-design, com as decisões do usuário)
Assunto: painel de apuração usado por uma equipe na noite da eleição e depois para análise — denso, numérico,
lido de longe na TV. A personalidade vem da tipografia numérica e de um único elemento-assinatura; o resto quieto.
- **Cor:** tokens atuais mantidos (dataviz, `--mapa-1..5`, `--div-*`, status). Única mudança: suporte a
  `data-tema="claro|escuro"` além do `prefers-color-scheme`, para forçar o tema na TV.
- **Tipografia:** uma família, **Public Sans** (origem cívica, variável, servida localmente — o site não depende
  de rede externa); `font-variant-numeric: tabular-nums` em toda tabela, ficha e eixo, para os números não
  "dançarem" a cada atualização. Escala: 12 / 14 (base) / 16 / 20 / 26 px; pesos 400 e 600 só.
- **Espaço e forma:** escala 4 / 8 / 12 / 16 / 24 / 32; raios por hierarquia — 3 px controles, 6 px caixas e
  cartões, 999 px selos; sombra só no que flutua (dica, painel de alertas, aviso).
- **Assinatura (o único gesto ousado):** uma régua fina de apuração sob o cabeçalho — % de seções totalizadas
  da UF e hora da última totalização, com os dados que `/api/status` já traz. Fica visível em todas as abas e
  no modo TV.
- **Texto:** frase com só a 1ª letra maiúscula; botão diz a ação ("Atualizar mapa", "Baixar PNG"); erro diz o
  que houve e o que fazer; metadados que hoje vão juntos com "·" viram elementos separados.
- **Qualidade mínima:** foco visível pelo teclado, `prefers-reduced-motion`, sem rolagem horizontal a 360 px,
  `role="tab"`/`aria-controls` completos nas abas.
- **CSS:** `@layer tokens, base, componentes, abas, utilitarios` (acaba a guerra de especificidade);
  `estilos/tokens.css`, `base.css`, `componentes/*.css`, `abas/*.css`.
- **Catálogo:** `frontend/catalogo.html` (só no `vite dev`, fora do build) mostrando cada componente nos dois
  temas — onde se confere o design system.

## 6. Robustez
- Todo `fetch` com tempo-limite e cancelamento; resposta velha nunca desenha (o `Canal` generaliza o que a
  rodada 50 fez só para o mapa).
- `agendador`: o `tick` de 60 s nunca roda duas vezes ao mesmo tempo; a aba escondida não refaz o painel e
  atualiza ao voltar; os alertas (15 s) continuam com a aba escondida — é quando o som mais importa.
- Indicador de dados velhos: "sem resposta do site desde HH:MM" após 3 falhas seguidas.
- `unhandledrejection` capturado e mostrado na linha de situação, em vez de sumir no console.
- Cada bloco tem estados carregando/vazio/erro do mesmo componente.
- Calço para os e2e: `window.__apuracao = { mapas, estado, desenharPainel }` exposto pelo `main.ts`;
  os testes trocam `estado.mapa` por `__apuracao.mapas.mapa` (troca mecânica, asserções iguais).

## 7. Fases (padrão "estrangulador": cada fase deixa os 64 e2e verdes e pode ir para `main` sozinha)
0. **Andaime:** Vite + TS; `app.js` atual entra como `src/legado.js` (`allowJs`, `// @ts-check`), Leaflet do npm;
   build idêntico em comportamento; `test_frontend_build.py`; cabeçalhos de cache.
1. **Núcleo:** `core/*` + `tipos/api.ts` + Vitest; o legado passa a importar `el`, `api`, formatos.
2. **Roteador:** `rotas.ts` com testes de ida e volta (ler∘escrever = identidade) para os endereços de todas as
   abas, inclusive o formato antigo; some `abrirPorHash` e os 6 pares.
3. **Componentes:** gráfico base, mapa/camadas/legenda, tabela, dica, exportar.
4. **Abas, da mais isolada à mais crítica:** transferência → perfil → comparação → candidato → mapas → painel
   (+ alertas e modo TV por último). Cada uma sai do legado inteira.
5. **Design system:** tokens, camadas CSS, fonte, régua de apuração, catálogo; revisão visual por capturas
   Playwright nos dois temas, celular e TV.
6. **Limpeza:** `legado.js` vazio e removido; atualizar `CLAUDE.md` (comandos `npm ci && npm run build`,
   estrutura) e a rodada em `docs/`.

## 8. Calendário e riscos
- **2º turno em 25/10/2026:** a refatoração fica num ramo (`frontend-refatoracao`) e só entra em `main` depois
  do 2º turno; até lá, correções no front-end vão para o `app.js` atual. Fases 0–2 podem ser preparadas antes.
- Risco: e2e acoplados a globais → calço da §6. Risco: caminho relativo no site de várias UFs → `base: "./"` +
  e2e do `--ufs`. Risco: build desatualizado no repositório → `test_frontend_build.py`. Risco: cadeia de
  suprimentos do npm → poucas dependências, lock, `npm audit`.
- Fora do escopo: mudar cores dos mapas, framework de componentes (React/Vue), mudar a API. Os tipos das
  respostas ficam escritos à mão; gerar do OpenAPI exigiria `response_model` nas 46 rotas — anotado como
  melhoria futura.

## 9. Verificação de cada fase
`npm run build && npm run lint && npm run typecheck && npm test` (Vitest); `pytest -q` (inclui o teste do build) e
`pytest -m e2e`; `python ensaio_apuracao.py` com o site no ar (noite acelerada sem erro de console);
`site_apuracao.py --ufs todas` para os caminhos relativos; capturas antes/depois nos dois temas.

