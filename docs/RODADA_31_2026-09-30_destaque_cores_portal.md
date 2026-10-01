# Rodada 31 — Destaque de partidos, listas salvas, cores dos mapas e portal

30/09/2026 · pedido do usuário, antes do item 10: (1) escolher partidos e federações cujos deputados são destacados nas listas de "eleitos projetados"; (2) salvar essas listas em arquivo; (3) trocar as cores dos mapas: "no mapa de um deputado, as cores vão de azul escuro (menos votos) para azul claro (mais votos), não é intuitivo", com a proposta amarelo = menos e vermelho = mais; (4) uma página "portal" com links para os sites no ar.

## Decisões do usuário

Tomadas pelo plano aprovado (`/plan`), com perguntas respondidas:
- **Destaque:** vale no site, no arquivo salvo e no boletim.
- **Arquivo:** .xlsx.
- **Cores:** todos os mapas de intensidade.
- **Portal:** detecta os sites sozinho.

## Entregas

### 1. Destaque de partidos e federações

- **No painel:** uma caixa "Destacar partidos/federações nas listas de eleitos", acima dos cartões, com uma opção para cada agremiação.
  - Federação aparece como grupo, com a própria federação e os partidos dela.
  - As opções vêm de `composicao`, novo campo de `/api/cadeiras`: os partidos de cada agremiação, da mais votada à menos.
- **Regra** (`destacado()`, igual no Python e no JS): destaca o candidato cujo PARTIDO **ou** AGREMIAÇÃO foi escolhido. Marcar a federação destaca todos os partidos dela; marcar um partido da federação destaca só esse partido.
- **Visual:**
  - linhas com ★, negrito, fundo azul-claro e borda à esquerda (o destaque não depende só da cor);
  - agremiação com ★ na barra de cadeiras;
  - no resumo da lista, "— K destacado(s)";
  - vale para as duas listas: eleitos da apuração atual e consolidados/disputa da projeção;
  - a tabela de eleitos ganhou a coluna Partido, com a federação em letra pequena embaixo.
- **Estado da escolha:**
  - fica no endereço (`#painel?destacar=PL,PT/PC do B/PV`, com "Copiar link") e no navegador (`localStorage`);
  - a ordem de prioridade é endereço, depois navegador, depois `--destacar` do site (via `/api/status`);
  - o redesenho de 60 s mantém o destaque e **reabre as listas que estavam abertas** (`estado.cadAbertos`).
- **Boletim:**
  - ★ e fundo nas listas de eleitos e de "fora na projeção", que abrem sozinhas quando há destacados;
  - uma linha "★ Destaque nas listas de eleitos: …" no topo;
  - coluna "Destacado" na planilha;
  - opção `--destacar` em `site_apuracao.py` e em `gerar_boletim.py`.

### 2. Listas salvas em .xlsx

- **`GET /api/cadeiras/planilha?cargo=6|7&destacar=…`:** as mesmas listas de `/api/cadeiras`, geradas em memória.
  - Abas:
    - "Sobre": cargo, vagas, % de seções, hora da totalização, situação, fonte, gerado em, destaque;
    - cadeiras por agremiação;
    - eleitos, com "Destacado";
    - projeção, quando ativa.
  - Reaproveita o gerador de abas do boletim (`_abas_proporcional`, e agora `formatos_planilha` e `planilha_eleitos` em `boletim.py`).
  - Nome do arquivo: `eleitos_projetados_deputado_estadual_RJ_<AAAA-MM-DD_HHhMM>.xlsx`, com a hora da totalização.
- **Botão "Salvar lista (.xlsx)"** em cada bloco de cadeiras; o link leva o destaque atual.

### 3. Cores dos mapas: amarelo (menos) → vermelho (mais)

- **Tokens:** `--mapa-1..5` = `#fed976 #feb24c #fd8d3c #f03b20 #bd0026` (ColorBrewer YlOrRd sem o passo mais claro, que se confundia com o cinza "sem dado").
  - Usados em `desenharMapa`: mapa por município, por bairro, mini-mapa do candidato, linha do tempo, legenda e exportação PNG/SVG/JPEG (que recebe as cores da página).
  - A ordem é a **mesma no tema escuro**, por pedido do usuário: essa é uma exceção à regra da skill dataviz de inverter a rampa no escuro, e está registrada no CSS e no `CLAUDE.md`.
- **Medições** (a validação categórica da skill não se aplica a rampa sequencial, e ela mesma avisa):
  - luminosidade OKLab monotônica, 0,90 → 0,82 → 0,75 → 0,63 → 0,50;
  - menor passo entre vizinhos ΔE 8,4, acima da meta de 8;
  - o 1º passo fica a ΔE 13 do "sem dado";
  - contraste do vermelho mais escuro com a superfície escura: 2,65.
  - Das candidatas testadas, a que terminava em `#800026` tinha passos mais regulares, mas sumia no fundo escuro (1,61).
- **Sem mudança:**
  - mapa categórico (líder) e mapas de comparação (azul × vermelho, ganho × perda);
  - `--seq-*` (azul), que continua só nas barras de projeção e cadeiras.

### 4. Portal (`portal.py`)

- **Endereço:** `python portal.py` → http://localhost:8100. A 8080, pensada no plano, já estava ocupada nesta máquina; o padrão 8100 fica fora da faixa procurada.
- **Detecção:** a cada acesso, pergunta `/api/status` às portas 8000–8099 desta máquina (em paralelo, 0,5 s de limite; 0,15 s no total com 4 sites no ar). Só lista o que responde como site da apuração: JSON com `coletor` e `progresso`.
- **Cartão por site:**
  - título, selo (OFICIAL, teste, histórico, ensaio), turno e porta;
  - situação (coletando, erro, resultado importado, só leitura);
  - % apurado por abrangência (as duas eleições da UF juntas, com o menor %);
  - última coleta, diretório de dados (`/api/status` agora traz `dados`) e erro do coletor.
- **Página:** HTML autônomo (CSS embutido, texto por `textContent`), claro e escuro, cabe no celular e se atualiza a cada 30 s. Os links usam o endereço pelo qual o portal foi aberto.
- **Segurança:** o portal só consulta a própria máquina, em portas fixas; nada vem do usuário.

## Achados no caminho (corrigidos)

1. **O destaque vindo do endereço se perdia na carga.** O primeiro `atualizarStatus` gravava `#painel` antes de `abrirPorHash` ler `?destacar=`. Agora a escolha inicial lê o endereço e não o reescreve.
2. **Tabela de eleitos larga demais** com as colunas Partido e Agremiação: a coluna "Via" ficava cortada no cartão. A agremiação passou para uma linha pequena sob o partido, só quando difere dele (federação).
3. **Siglas com espaço no simulado** ("P 9974") viram "+" no endereço. O teste passou a ler com `URLSearchParams`; o código já estava certo.

## Arquivos

- **Novos:**
  - `portal.py`;
  - `test_portal.py`: 4 testes;
  - `test_destaque_e2e.py`: 2 testes no Chrome.
- **Alterados:**
  - `apuracao/web/app.py`: `/api/cadeiras/planilha`, `composicao`, `dados` e `destacar_padrao` no status, `create_app(destacar=)`;
  - `apuracao/web/static/{app.js,index.html,style.css}`: destaque, salvar, `--mapa-*`, `el` já aceitava variáveis CSS (rodada 30);
  - `apuracao/boletim.py`: `destacado`, `formatos_planilha`, `planilha_eleitos`, `montar/Boletineiro(destacar=)`, coluna Destacado, CSS `tr.destaque`;
  - `site_apuracao.py` e `gerar_boletim.py`: `--destacar`;
  - `test_cadeiras.py`: planilha e federação;
  - `test_boletim.py`: destaque;
  - `test_painel_graficos.py`: cores `--mapa-*`, a 1ª faixa amarela e o tema escuro sem inversão;
  - `CLAUDE.md`, `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/INDEX.md`.

## Verificação

- **Testes:** `pytest -q` → **273 passando**, duas vezes seguidas (262 na rodada 30).
- **Ensaio geral** (`python ensaio_apuracao.py`): **RESULTADO OK** em 14,1 min.
  - 52 ciclos, 5.937 arquivos, nenhum 404 e nenhum erro.
  - 5.000 consultas ao site, nenhum 5xx; `/api/painel` com p50/p95 de 144/971 ms.
  - 9 boletins, 7 alertas (nenhum crítico).
  - Conferência com o oficial toda OK.
- **Visual:**
  - painel com destaque (PL e PT/PC do B/PV em 2022: 17 dos 46 eleitos federais);
  - mapa da deputada 13713 em claro e escuro, amarelo → vermelho;
  - portal a 1.100 e 390 px, sem rolagem horizontal.
- **No ar:** sites de teste 8000 (simulado `--coletar`), 8022 e 8023 (2022; a 8023 com `--turno 2`), e o portal em http://localhost:8100.

## Pendências

- **Destaque dos majoritários:** não foi pedido, e as listas de governador e senador são curtas.
- **Próximo item do TODO:** 10, o mapa por local de votação, que deve usar a mesma rampa `--mapa-*`.
