# Rodada 67 — Front-end, fase 4 (parte 4): Painel, alertas e o fim do `legado.js` (08/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 4. As partes anteriores estão nas
rodadas [64](RODADA_64_2026-10-07_frontend_fase4_transferencia_perfil.md),
[65](RODADA_65_2026-10-07_frontend_fase4_comparacao_candidato.md) e [66](RODADA_66_2026-10-07_frontend_fase4_mapas.md).

## Objetivo

Migrar o Painel (a aba da noite), os alertas, o modo TV, a situação do coletor e o seletor de UF. Com isso não
sobra nada no `legado.js`: ele foi apagado e o arranque passou para TypeScript. A fase 6 da proposta previa remover
o legado; a remoção foi feita aqui, porque o que sobrava era só o arranque.

## Entregas

- **`abas/painel/`** (800 linhas):
  - `cartao.ts`: cartão por cargo, composições, série e lista de candidatos;
  - `projecao.ts`: projeção dos majoritários, com o trilho e "onde faltam votos";
  - `cadeiras.ts`: barra por agremiação, cadeiras projetadas e listas de eleitos sob demanda;
  - `destaque.ts`: partidos destacados, com prioridade endereço > navegador > padrão do site;
  - `brasil.ts`: presidente por UF, com bloco persistente, mapa, tabela e dica fora do mapa;
  - `tv.ts`: modo TV;
  - `mudancas.ts`: "o que mudou";
  - `tipos.ts` e `index.ts`.
- **`alertas/`:** `apresentacao.ts` (puro: níveis, som, título da aba e cartão) e `index.ts` (pedidos, faixa,
  avisos, histórico, "Acompanhar" e o som WebAudio).
- **`pagina/`:**
  - `inicio.ts`: o arranque. Liga o estado comum (UF, ano, turno, mapas por nome), registra as seis abas no
    roteador, cuida do ciclo de 60 s, dos alertas de 15 s, dos botões de exportar mapa e do `window.__apuracao`;
  - `situacao.ts`: cabeçalho e status do coletor, mais `limitarCargos`;
  - `seletor-uf.ts`.
- **`legado.js` apagado.** O `tsconfig` perdeu `allowJs`/`checkJs` e o ESLint perdeu o bloco do legado: todo o código
  da página passa por `tsc --strict` e pelas regras estritas do `typescript-eslint`. São 66 arquivos, e o maior
  (`abas/mapas/index.ts`) tem 364 linhas, dentro do teto de cerca de 400 da proposta.
- **Testes e2e:**
  - os testes que liam o painel pelo estado global passam a ler `__apuracao.abas.painel.estado`: `brasil.dados` e
    `destacar`, este também escrito por um teste. As asserções são as mesmas. `__apuracao.estado.<mapa>`,
    `alertas`, `tocar` (substituível), `api`, `desenharPainel`, `atualizarPainel` e `consultarCandidato`
    continuam;
  - **novo `test_console_e2e.py`:** percorre as seis abas, pelo endereço e pelos botões, abre os blocos sob demanda
    e falha com qualquer erro de JavaScript (`pageerror` ou `console.error`, exceto recurso não carregado).
    Conferido: um erro injetado faz o teste falhar. 72 e2e no total.
- **Vitest:** 12 testes novos, 121 no total:
  - destaque (partido, federação, composições);
  - cartão: composições, texto do TSE como texto, duplo clique abre o candidato, bloco Brasil só no Presidente —
    BRASIL;
  - cadeiras: destaque, aviso de inconsistência, link da planilha, lista que reabre;
  - trilho da projeção, dica por UF, cartão da vez no modo TV, título das mudanças;
  - alertas: nível mais grave, título da aba, cartão;
  - cabeçalho: progresso e `limitarCargos`.

## Tamanho

| | Antes da refatoração | Agora |
|---|---|---|
| Código da página | `app.js`, 3.117 linhas, 1 arquivo | 66 arquivos `.ts` (5.130 linhas, com tipos e comentários) |
| Testes de JS | nenhum | 121 Vitest + 72 e2e |
| Página em gzip (JS + CSS + Leaflet) | 102,6 KB | 95,1 KB (JS 84,5 + CSS 10,6) |

## Decisões

- **"Acompanhar nos alertas"** é criado pela central de alertas e chega à aba Candidato como dependência
  (`botaoAcompanhar`). A aba não conhece os alertas.
- **O painel não importa a aba Candidato.** O duplo clique num candidato chega por `consultarCandidato`, injetado
  pelo arranque.
- **O som substituível dos testes** (`window.__apuracao.tocar = …`) é um acessor sobre `alertas.tocar`. A central
  sempre chama `central.tocar`, então trocar o som no teste vale para os alertas novos.

## Verificação

- `npm run verificar`: tipos, lint, 121 testes do Vitest e build.
- `pytest -m e2e`: 72 passaram (os 71 de antes, sem mudar asserções, e o de console).
  `pytest -m "not e2e"`: 414 passaram e 1 foi pulado.
- Não rodei o ensaio geral (`ensaio_apuracao.py`), porque ele exercita servidor e coletor, que não mudaram, e não
  executa o JavaScript da página. O teste de console cobre o risco novo.

## Próximas

- **Fase 5, design system:** tokens de tipo, espaço e raio; `@layer`; Public Sans local com números tabulares; a régua
  de apuração sob o cabeçalho; catálogo de componentes.
- **Fase 6, limpeza:** o que sobrou, já que o legado saiu nesta rodada. Revisar o `style.css` por regras órfãs e
  fechar a documentação com um README do front-end.
