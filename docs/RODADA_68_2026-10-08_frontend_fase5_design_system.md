# Rodada 68 — Front-end, fase 5: design system (08/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §5 e §7, fase 5. A fase anterior está na
[RODADA_67](RODADA_67_2026-10-08_frontend_fase4_painel_fim_do_legado.md).

## Objetivo

Dar à página um design system com polimento contido: tokens de tipo, espaço, raio e sombra; CSS em camadas; a fonte
Public Sans servida pelo próprio site, com algarismos tabulares; tema forçável; a régua de apuração sob o cabeçalho; e
um catálogo de componentes. As cores da dataviz e dos mapas (YlOrRd, rodada 31) não mudaram.

## Entregas

- **CSS em camadas.** O `style.css` de 388 linhas virou 18 arquivos em `src/estilos/` (534 linhas):
  - `index.css` declara `@layer vendor, tokens, base, componentes, abas, utilitarios` e importa os demais.
  - O Leaflet entra na camada `vendor`. Fora de camada, ele venceria todas as nossas regras.
  - `tokens.css` reúne cor, tipo, espaço, raio e sombra. `base.css` só tem seletores de elemento.
  - `componentes/` tem 7 arquivos: topo, caixas, formulários, tabelas, gráficos, mapa e alertas.
  - `abas/` tem um arquivo por aba, mais o `tv.css`.
  - `utilitarios.css` guarda o `[hidden]` e o `.visualmente-oculto`.
- **Tokens.** Tipo em 12, 14 (base), 16, 20 e 26 px, só com os pesos 400 e 600. O texto dentro dos gráficos SVG ficou
  fora da escala, como marca de dataviz (`--fs-eixo`, 10 px). Espaço em 4, 8, 12, 16, 24 e 32 px. Raio de 3 px nos
  controles, 6 px em caixas e cartões e 999 px nos selos; as pontas das barras dos gráficos têm token próprio
  (`--raio-marca`). A sombra fica só no que flutua e é mais forte no tema escuro. Sobrou valor solto só na geometria
  das marcas dos gráficos: alturas de barra e o vão de 2 px entre segmentos.
- **Fonte.** `@fontsource-variable/public-sans@5.3.0` (OFL; licença em `static/licencas/public-sans.txt`), servida
  de `assets/` com `immutable`. O arquivo latino tem 26,8 KB. `font-variant-numeric: tabular-nums` vale na página
  inteira.
- **Tema.** Os tokens escuros valem com `prefers-color-scheme` ou com `data-tema="escuro"`; `data-tema="claro"` força
  o claro com o sistema no escuro. Há três formas de escolher:
  - `?tema=claro|escuro` no endereço, antes do `#`: serve a uma TV em quiosque;
  - o seletor "Tema" no cabeçalho, que grava a escolha no navegador;
  - nada, e a página segue o sistema.

  `pagina/tema.ts` é o primeiro import do `main.ts`. Trocar de tema recarrega a página, porque mapas e gráficos leem
  as cores na hora de desenhar e o estado das abas está todo no endereço.
- **Régua de apuração** (`pagina/regua.ts`), a assinatura da página:
  - mostra o % das seções totalizadas na UF em destaque, a hora da última totalização e "✓ final";
  - o trilho corre na borda de baixo do cabeçalho, com uma marca a cada 10%;
  - aparece em todas as abas e no modo TV, em tamanho maior;
  - usa só o `/api/status`, sem rota nova. Das linhas da UF (presidente e cargos estaduais são eleições diferentes),
    usa o menor %, a hora mais recente e "final" só se todas forem finais;
  - tem `role="progressbar"` e `aria-valuetext`.
- **Acessibilidade:**
  - as abas seguem o padrão WAI-ARIA (`pagina/abas.ts`): `aria-controls`/`aria-labelledby`, só a aba aberta no Tab,
    ←/→/Home/End andando entre as visíveis;
  - `:focus-visible` com contorno;
  - `prefers-reduced-motion` desliga animações e transições no CSS e o zoom e o esmaecimento animados do Leaflet.
- **Celular sem rolagem horizontal a 360 px.** Dois defeitos antigos estavam na aba Perfil (496 px):
  - a grade de uma coluna `1fr` (= `minmax(auto, 1fr)`) crescia até a largura da tabela de correlações. As quatro
    grades responsivas passaram a usar `minmax(0, 1fr)`;
  - a tabela da regressão múltipla não tinha rolagem própria e ganhou `.rolagem-x`.

  Também entraram `fieldset { min-width: 0 }` e `select { max-width: 100% }`.
- **Componente `.botao`** (secundário, com contorno): o "Acompanhar nos alertas" tinha a aparência nativa do navegador.
- **Catálogo** (`frontend/catalogo.html` + `src/catalogo/`, só no `npm run dev`, fora do build). Mostra cada
  componente desenhado pelas mesmas funções da página, com dados de exemplo: cores com o valor resolvido, escala de
  tipo, espaço e raio, cabeçalho com régua, controles, superfícies, cartão do painel, tabela, gráficos de linhas e de
  dispersão, legendas e os quatro níveis de alerta. Sem `?tema=`, mostra os dois temas lado a lado, um `iframe` cada,
  porque as cores dos gráficos vêm do `<html>`. O `catalogo.html` entrou na impressão digital da fonte
  (`construcao.ts`).
- **Mensagem de erro do cabeçalho:** agora diz o que fazer: "Servidor indisponível: … A página tenta de novo em 1
  minuto."

## Tamanho

| | Rodada 67 | Agora |
|---|---|---|
| Página em gzip (JS + CSS) | 95,1 KB (84,5 + 10,6) | 96,2 KB (84,5 + 11,7) |
| Fonte | do sistema | +26,8 KB (woff2 latino, uma vez, cache `immutable`) |
| Antes da refatoração (JS + CSS + Leaflet) | 102,6 KB | — |

O critério da proposta (JS + CSS em gzip ≤ o de antes) continua valendo. A fonte não entra nessa conta: é woff2,
já comprimida, e vai para o cache do navegador uma vez. Os arquivos latin-ext e vietnamita também são gerados, mas o
navegador só os baixa se a página tiver um caractere dessas faixas (`unicode-range`).

## Decisões

- **Lista do cartão em 14 px.** Antes era 13 px, fora da escala. As colunas de número foram de 60/64 px para 56/72 px:
  "2.380.229" cabe e a barra encolhe um pouco. Os nomes longos são cortados um pouco antes (com reticências, como antes).
- **As cores escuras aparecem duas vezes em `tokens.css`**: uma para o sistema, outra para o tema forçado. `light-dark()`
  evitaria a cópia, mas `getPropertyValue` devolveria o texto da função em vez da cor. Isso quebraria `cor()`, a
  exportação e os e2e que leem os tokens.
- **A ordem das camadas** vem da 1ª aparição de cada uma no CSS gerado, porque o build descarta a linha `@layer a, b…;`.
  `test_frontend_build.py` confere essa ordem no `static/`.
- **O texto da situação do coletor não mudou.** A proposta pede metadados como elementos separados, e não mais juntos
  com "·". A régua já faz isso; reescrever a linha da situação ficou para a fase 6, junto com a revisão dos textos.

## Verificação

- `npm run verificar`: tipos, lint, 130 testes do Vitest (9 novos em `tests/pagina.test.ts`: tema, régua, abas pelo
  teclado) e build. `npm audit`: 0 vulnerabilidades.
- `pytest -m e2e`: 79 passaram, os 72 de antes sem mudar asserções e os 7 do novo `test_design_e2e.py`:
  - régua em todas as abas e no modo TV;
  - `?tema=` vencendo o sistema nos dois sentidos, com a paleta do mapa igual;
  - seletor de tema que grava a escolha e recarrega no mesmo endereço;
  - Public Sans carregada e números tabulares;
  - abas pelo teclado;
  - 360 px sem rolagem horizontal nas seis abas.
- `pytest -m "not e2e"`: 413 passaram e 3 foram pulados. O teste novo de ordem das camadas está nessa conta. Os
  pulados são os golden do BU do RJ 2022, que dependem de arquivos fora do cache, não do front-end.
- **Capturas Playwright** do site com os dados de `dados_2026/oficial`, antes e depois: seis abas, temas claro e
  escuro, 1400 px e 360 px, mais o modo TV em 1920×1080. Nenhum erro de JavaScript. Antes, a aba Perfil rolava na
  horizontal a 360 px; depois, nenhuma aba rola.
- O catálogo foi conferido no `vite dev`, com os dois temas lado a lado e sem erro de JavaScript.

## Próxima

**Fase 6, limpeza:**
- revisar textos: botão com o nome da ação, linha da situação em elementos separados;
- conferir se sobrou regra CSS sem uso;
- escrever o README do front-end;
- atualizar a proposta e o CLAUDE.md finais;
- rodar o ensaio geral e o `--ufs todas` antes de entrar em `main`.
