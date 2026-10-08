# Front-end do site de apuração

Fonte da página do site (`site_apuracao.py`). É escrita em TypeScript estrito e compilada com o Vite. O build vai
para `../static/` **e entra no repositório**: em produção o FastAPI serve esses arquivos e a máquina da noite da
eleição não precisa de Node.

A história da refatoração que deu esta forma ao código está na
[proposta](../../../docs/PROPOSTA_REFATORACAO_FRONTEND.md) e nas rodadas 60 a 69 de `docs/`.

## Comandos

Node ≥ 20.19 (há um no nvm da máquina: `source ~/.nvm/nvm.sh`).

```bash
npm ci                 # dependências exatas do package-lock.json
npm run verificar      # tipos (tsc --strict), ESLint, Vitest e build — rode antes de todo commit
npm run dev            # página em http://localhost:5173 com recarga automática; os dados vêm do site
                       # Python já no ar (APURACAO_SITE, padrão http://localhost:8000)
npm test               # só o Vitest
npm audit              # confira a cada mudança de dependência (como o pip-audit no Python)
```

Também há o catálogo de componentes: com o `npm run dev` no ar, abra `/catalogo.html`. Ele mostra cada componente
nos dois temas, lado a lado, desenhado pelas mesmas funções da página. `?tema=claro` ou `?tema=escuro` mostra um
tema só. O catálogo fica fora do build.

**Mudou algo aqui? Rode `npm run verificar` e inclua `../static/` no commit.** O `test_frontend_build.py` (pytest,
sem Node) refaz a impressão digital da fonte (`construcao.ts`) e falha se a fonte mudou sem build novo. O mesmo
teste confere outras três coisas:
- a página usa só caminhos relativos;
- `ROTAS_PESADAS` de `src/core/api.ts` é igual à de `app.py`;
- as camadas do CSS gerado estão na ordem declarada.

## Estrutura de `src/`

| Pasta | O que tem |
|---|---|
| `main.ts` | Entrada: tema, fonte, estilos e o arranque, nesta ordem. |
| `core/` | Peças sem tela, todas testadas no Vitest. `api` (tempo-limite, cancelamento, `ErroApi`); `pedidos` (`Canal`: um pedido novo cancela o anterior); `agendador` (`repetir` sem sobreposição); `rotas` e `roteador` (tabela única dos endereços `#aba?…`); `dom` (`el`, `svg`, `ref`, `refs`, `cor`); `formatos`; `preferencias` (localStorage protegido); `aba` (o contrato `ModuloAba`/`Contexto`). |
| `componentes/` | Peças de tela reutilizáveis: escalas de cor, legenda, dica, tabela ordenável, metadados, gráficos (`grafico/`), mapas Leaflet (`mapa/`) e exportação. |
| `dados/` | Listas carregadas uma vez e compartilhadas entre abas (candidatos, malhas). |
| `abas/<aba>/` | Uma pasta por aba. `index.ts` cria o `ModuloAba`; `tipos.ts` tem as respostas da API usadas; `desenhar.ts` monta o DOM sem estado; os blocos com endereço próprio têm arquivo próprio. |
| `alertas/` | Alertas da noite: faixa, avisos, som, título da aba e "Acompanhar". |
| `pagina/` | O que liga tudo: `inicio.ts` (estado comum, roteador, ciclo de 60 s, `window.__apuracao` dos e2e), cabeçalho e situação, régua de apuração, abas acessíveis, tema e seletor de UF. |
| `estilos/` | O design system, descrito abaixo. |
| `catalogo/` | Catálogo de componentes (só no dev). |

## Regras

- **Texto vindo dos dados só por `textContent` ou `el()`/`svg()`.** O ESLint proíbe `innerHTML`, `outerHTML`,
  `insertAdjacentHTML` e `document.write`. O TSE testa o simulado com nomes cheios de aspas e símbolos.
- **Nunca use `fetch`, `localStorage` ou `setInterval` direto.** Use `api`/`enviar`/`baixar`, `preferencias` e
  `repetir`. Num pedido que pode ficar velho, use um `Canal` e ignore o erro quando `cancelado(e)` for verdadeiro.
- **O endereço guarda todo o estado visível.** Cada aba dá `escrever()` (estado → parâmetros) e `aplicar()`
  (parâmetros → estado). Grave com `ctx.gravarEndereco(aba)`, nunca com `history.replaceState`.
- **Uma aba só mexe na própria seção** (`#aba-<aba>`) e não importa outra aba: o que ela precisa de fora chega pelo
  `Contexto` ou como dependência injetada pelo `inicio.ts`.
- **Caminhos relativos sempre.** O site de várias UFs monta cada uma em `/<uf>/`: escreva `api/x`, nunca `/api/x`.
- **Cores dos gráficos e mapas pelos tokens** (`cor("--serie-1")`, `TOKENS_SEQ`…). A paleta YlOrRd dos mapas é a
  mesma nos dois temas, por pedido do usuário (rodada 31).

### Como criar uma aba

1. Inclua o nome em `ABAS`, em `core/rotas.ts`.
2. Crie em `index.html` o botão (`role="tab"`, `id="botao-<aba>"`, `aria-controls="aba-<aba>"`) e a seção
   (`id="aba-<aba>"`, `role="tabpanel"`, `aria-labelledby`, `hidden`).
3. Crie `abas/<aba>/index.ts` com `criarAba<Nome>(ctx): ModuloAba`. Pegue os elementos com `refs()`, que falha no
   arranque se faltar um id.
4. Registre a aba em `pagina/inicio.ts` (`registrar(...)`).
5. Ponha os estilos em `estilos/abas/<aba>.css` e importe o arquivo em `estilos/index.css`, na camada `abas`.
6. Escreva testes Vitest para o que é puro e um teste e2e (pytest + Playwright) para o caminho na página.

## Design system (`estilos/`)

- **Camadas:** `@layer vendor, tokens, base, componentes, abas, utilitarios`. A camada posterior vence, qualquer
  que seja a especificidade. O Leaflet fica na `vendor`, porque fora de camada ele venceria todas. O build descarta
  a linha de ordem e vale a ordem em que cada camada aparece: mantenha os `@import` de `index.css` na mesma ordem.
- **Tokens (`tokens.css`):**
  - tipo: `--fs-1..5` = 12/14/16/20/26 px; o texto dentro dos SVG usa `--fs-eixo`;
  - pesos: 400 e 600;
  - espaço: `--esp-1..6` = 4/8/12/16/24/32 px;
  - raio: `--raio-controle`, `--raio-caixa`, `--raio-selo` e `--raio-marca` (pontas das barras);
  - sombra: `--sombra-dica` e `--sombra-aviso`, só no que flutua.

  Valor solto só na geometria das marcas de gráfico.
- **Tema:** segue o sistema ou é forçado por `data-tema="claro|escuro"` no `<html>`. O atributo vem de `?tema=` no
  endereço ou do seletor do cabeçalho (`pagina/tema.ts`). As cores escuras aparecem duas vezes em `tokens.css`, uma
  para o sistema e outra para o tema forçado: mantenha as duas iguais.
- **Fonte:** Public Sans variável, servida pelo próprio site (`@fontsource-variable`), com `tabular-nums` na página
  inteira.
- **Celular:** nenhuma aba pode rolar na horizontal a 360 px. Grade de uma coluna é `minmax(0, 1fr)`, nunca `1fr`.
  Tabela larga fica dentro de `.tabela-rolagem` ou `.rolagem-x`.
- **Componentes de texto:** `.nota` e `.sub` (apoio), `metadados()` (um item por elemento, sem "·"), `.botao`
  (secundário) e `button.link`.

## Testes

- **Vitest** (`tests/*.test.ts`, happy-dom): o código puro e a montagem do DOM de cada aba.
- **e2e** (pytest + Playwright no Chrome, `pytest -m e2e` na raiz do repositório): o site de verdade, com um TSE
  falso (`conftest.py`). Chegam à página por `window.__apuracao`. O `test_console_e2e.py` falha com qualquer erro de
  JavaScript nas seis abas; o `test_design_e2e.py` cobre régua, tema, fonte, teclado e celular.

## Dependências

Versões exatas no `package.json`, sem `^`, e lock completo. Use poucas: em execução só o `leaflet` e a fonte. Ao
atualizar, rode `npm audit`, `npm run verificar` e os e2e, e anote na rodada. Licenças de terceiros servidas com a
página: `public/licencas/`.
