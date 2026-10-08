# Rodada 69 — Front-end, fase 6: limpeza e fechamento (08/10/2026)

Ramo `frontend-refatoracao`, que só entra em `main` depois de 25/10. Segue a
[PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md), §7, fase 6, e fecha a refatoração. A fase
anterior está na [RODADA_68](RODADA_68_2026-10-08_frontend_fase5_design_system.md).

## Objetivo

Tirar o que sobrou: regras CSS e exports sem uso, textos de botão que não dizem a ação, metadados juntos com "·".
Escrever o guia do front-end. Fazer as duas verificações que a proposta pedia e ainda não tinham sido feitas: o ensaio
geral com a página aberta e o site de várias UFs.

## Entregas

- **Sem código morto:**
  - todo seletor dos 18 CSS foi conferido contra o HTML e o TypeScript. A única regra órfã era `.visualmente-oculto`,
    criada na fase 5 e nunca usada, e saiu;
  - `tsc --noUnusedLocals --noUnusedParameters` não acusa nada;
  - o export `CentralAlertas` não tinha uso e saiu.
- **Botões com o nome da ação:**

  | Antes | Agora |
  |---|---|
  | "Limpar" | "Limpar destaque" |
  | "Atualizar" (histórico do candidato) | "Atualizar tabela" |
  | "Desenhar" | "Desenhar gráfico" |
  | "Calcular" | "Calcular transferência" |
  | "Modo TV (…)" | "Abrir modo TV (…)" |
  | "remover" | "Remover" |
- **Metadados como elementos separados:**
  - o componente novo `metadados(...)` (`componentes/metadados.ts`) põe um `<span>` por item, sem "·" entre eles.
    Cada item quebra linha inteiro, e um item longo só quebra por dentro se não couber sozinho;
  - ele é usado no cartão (seções, hora, FINAL, vagas), na projeção e nas cadeiras;
  - a situação do coletor no cabeçalho virou uma lista (`itensProgresso`), um item por eleição.
- **Régua:** em data de outro ano, a hora sai com o ano ("08/09/2023 13:18"). Antes, uma eleição importada mostrava
  "08/09 13:18", que é ambíguo.
- **Guia do front-end:** [`apuracao/web/frontend/README.md`](../apuracao/web/frontend/README.md). Traz os comandos,
  a estrutura de `src/`, as regras (texto do TSE, pedidos, endereço, caminhos relativos), o passo a passo para criar
  uma aba, o design system, os testes e a política de dependências. A proposta passa a apontar para ele e fica
  marcada como executada.

## Defeito achado no ensaio: mapa "Por estado" quebrado

Foi a primeira vez que um navegador acompanhou o ensaio inteiro, alternando abas e registrando erros de JavaScript. O
navegador acusou 6 erros `Invalid LatLng object: (NaN, NaN)` do Leaflet.

- **Causa:** o site é aberto direto em outra aba (ex.: `#mapas`) e o painel carrega com a seção escondida. O mapa
  "Por estado" do cartão Brasil é enquadrado com o contêiner de tamanho 0. Esse mapa não tem ladrilhos e, por isso,
  não tem `maxZoom`. O `fitBounds` então dá zoom **infinito**, e o mapa fica marcado como já enquadrado. Ao abrir o
  Painel, toda conta dá NaN e o mapa fica quebrado até recarregar a página.
- **Desde quando:** o enquadramento direto vem do legado (rodada 35).
- **Correção** (`componentes/mapa/criar.ts`):
  - `enquadrarUmaVez` só enquadra com o contêiner visível. Escondido, o enquadramento fica pendente
    (`_enquadrarPendente`) e o `ResizeObserver` do `criarMapa` o faz quando o mapa aparece;
  - todo mapa ganhou `maxZoom` (`ZOOM_MAXIMO` = 18) como rede de segurança;
  - o bloco Brasil passou a usar `enquadrarUmaVez`. Era o único que chamava `fitBounds` por conta própria.
- **Testes:**
  - novo e2e `test_mapa_por_estado_desenhado_com_o_painel_escondido` (`test_painel_graficos.py`). Ele falhou no build
    antigo, com zoom `inf`, e passa no novo;
  - 2 testes Vitest para o enquadramento pendente.

## Defeito do servidor achado no ensaio (fora do front-end)

"Cópia final com todas as parciais do TSE" falhou nos dois ensaios: 3.680 de 3.682 e 3.686 de 3.688.

- **Causa:** em `apuracao/copia.py`, depois que o instantâneo `final` existe, `verificar()` volta antes do espelho de
  `raw/`. Parcial que chega depois do "final" nunca é copiada; no ensaio, foi o EA20 regerado depois do anúncio.
- **Encaminhamento:** o defeito vale para a noite real e para o 2º turno, que roda pelo `main`. Não foi corrigido
  neste ramo; ficou registrado no [TODO 28](TODO.md).

## Números finais da refatoração

| | Antes (`app.js`) | Agora |
|---|---|---|
| Código da página | 1 arquivo, 3.117 linhas | 70 arquivos `.ts` (fora o catálogo); o maior, `abas/mapas/index.ts`, tem 364 linhas |
| CSS | 1 arquivo, 388 linhas, sem camadas | 18 arquivos em `@layer`, com tokens |
| Testes de JS | nenhum | 134 Vitest + 80 e2e |
| JS + CSS em gzip | 102,6 KB (com o Leaflet) | 96,4 KB (84,7 + 11,7); a fonte vem à parte (26,8 KB, cache `immutable`) |

## Verificação

- `npm run verificar`: tipos, lint, 134 testes do Vitest e build.
- `pytest -q`: 493 passaram (413 sem navegador e 80 e2e) e 3 foram pulados (golden do BU do RJ 2022, que dependem de
  arquivos fora do cache).
- **Ensaio geral** (`ensaio_apuracao.py --velocidade 60`, RJ 2022, cerca de 7 min), feito duas vezes, com um
  navegador alternando Painel, Mapas, Candidato e modo TV a cada 25 s:
  - antes da correção: 6 erros de JavaScript (o mapa "Por estado");
  - depois: **nenhum**. A régua acompanhou a noite de 0,1% a 100%;
  - a conferência com o oficial passou: válidos dos cinco cargos, eleitos, cadeiras 46/46 e 70/70, alertas e
    boletins. Só a cópia de segurança falhou (TODO 28).
- **Site de várias UFs** (`--ufs todas` sobre `historico_2022_t1`): SP, RJ e DF abriram com régua e fonte, a troca
  de UF pelo seletor foi para `/mg/`, sem erro de JavaScript e sem pedido falho. A fonte também usa caminho relativo.

## Pendências

- Entrar em `main` depois do 2º turno (25/10). Antes do merge, rodar de novo `pytest -q` e o ensaio no `main`
  atualizado.
- TODO 28 (cópia de segurança), no `main`, antes do 2º turno.
