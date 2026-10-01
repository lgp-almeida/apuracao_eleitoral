# Rodada 29 — Alertas durante a noite

30/09/2026 · pedido do usuário: "Siga para o item 8" (item 8 de `docs/TODO.md`)

## Objetivo

Avisar, sem ninguém precisar ficar olhando o painel, quando:
- o coletor para ou dá erro;
- o TSE bloqueia o acesso;
- a apuração empaca;
- a leitura da projeção muda ("indefinido" → "vitória projetada" ou "2º turno");
- um candidato de interesse vira "consolidado" ou sai da disputa.

O aviso aparece no próprio site (som e destaque) e no terminal, sem serviço externo.

## Entregas

### Motor (`apuracao/alertas.py`, classe `Vigia`)

- **Condições.** Valem enquanto durarem: avisam ao começar, atualizam o texto (ex.: "Coleta parada há 16 min") e avisam de novo ao terminar, como "Resolvido: …".

  | Condição | Nível | Regra |
  |---|---|---|
  | coletor encerrado | crítico | a thread do coletor morreu com erro (só com `--coletar`) |
  | coleta parada | crítico | último ciclo há mais de max(10 min, 3 intervalos); num bloqueio, soma a pausa de 11 min; não vale depois da totalização final |
  | bloqueio do TSE (403/429) | crítico | `tipo_erro` = "bloqueio" no `status.json`; o texto manda NÃO reiniciar nem subir outro coletor |
  | divulgação indisponível / erro inesperado | atenção | `tipo_erro` do `status.json` |
  | falha de rede | atenção | só se durar ≥ 150 s: uma falha isolada se resolve no ciclo seguinte |
  | apuração sem avanço | atenção | nenhuma nova totalização do TSE na UF há 20 min, com seções faltando, a coleta funcionando e algum cargo abaixo de 99,5% |

- **Eventos.** Avisam uma vez, no nível "novidade":
  - **leitura da projeção** (Governador, Senador, Presidente no RJ): a categoria é o texto de `projecao.situacao` antes do ":".
    - Passar de "cedo demais" para "indefinido" não é notícia.
    - "Projetada" → "confirmada" é, e aí o texto diz "58,7% dos válidos", não "projeção".
  - **deputados acompanhados:** a situação vem das MESMAS funções da rota de cadeiras.
    - Com a projeção das cadeiras (a partir de 30% apurado): consolidado, em disputa (dentro ou fora das vagas) ou fora da disputa.
    - No fim: eleito ou não eleito.
- **Silêncio na 1ª observação.** A primeira leitura e a primeira situação de cada candidato são gravadas sem alerta: só MUDANÇA vira alerta.
- **Persistência:** `<dados>/alertas.json` guarda o histórico (300), as condições ativas, as leituras e as situações. Reiniciar o site não repete nem perde alertas; um arquivo ilegível começa do zero, sem derrubar o site.
- **Terminal:** uma linha `ALERTA [nível] título — detalhe` no log. Crítico e atenção tocam a campainha (`\a`) quando o terminal é interativo.
- **Laço:** `executar` roda a cada 15 s numa thread do site. Um erro vai para o log e a volta seguinte roda normalmente.

### Coletor

- O `status.json` passa a ter `tipo_erro` (bloqueio, indisponivel, rede, inesperado) e `pausa_s`.
- `tipo_do_erro(exc)` classifica a exceção, e `coletar_resultados.py --uma-vez` usa a mesma classificação.

### API (`apuracao/web/app.py`)

- `GET /api/alertas?desde=<id>`: alertas novos, condições ativas e deputados acompanhados com a situação atual.
- `POST /api/alertas/interesse` `{cargo, numero, acompanhar}`: só deputado (6, 7, 8), no máximo 50.
- **Site na rede (`--host 0.0.0.0`):** a leitura dos alertas é livre, mas mudar os acompanhados é só da própria máquina. A lista nova `ROTAS_SO_LOCAL` junta as rotas pesadas e as que alteram estado.

### Página

- **Faixa no topo:** as condições ativas, com ícone, rótulo ("Crítico", "Atenção") e borda na cor de status da paleta de referência (vermelho #d03b3b, âmbar #fab219). A cor nunca carrega o sentido sozinha. O crítico pulsa 3 vezes (desligado com `prefers-reduced-motion`).
- **Avisos no canto:**
  - alertas novos desde que a página abriu;
  - crítico e atenção ficam até serem dispensados; novidade e "resolvido" saem em 30 s;
  - no máximo 5; abrir o painel dispensa todos (estão no histórico e, no celular, cobririam o painel).
- **Som:** bipes de WebAudio, sem arquivo:
  - 4 no crítico, 2 na atenção, 1 na novidade;
  - a caixa "som" fica guardada no navegador;
  - o navegador só libera o áudio depois de um clique na página.
- **Título da aba:** "⚠" enquanto há condição crítica ou de atenção, e "(n)" alertas não vistos. Serve com a aba em segundo plano.
- **Botão "Alertas":**
  - contador e painel lateral com o histórico e os deputados acompanhados (com a situação atual e "remover");
  - fecha com Esc.
- **Aba Candidato:** botão "Acompanhar nos alertas" / "Deixar de acompanhar" para deputado, só na apuração em andamento (2026).
- **Texto do TSE:** entra sempre por `textContent`.
- **Linha de comando:**
  - `site_apuracao.py --interesse 7:13713 6:1234` acompanha deputados desde a subida;
  - `--sem-alertas` desliga os alertas.

### Ensaio geral

`ensaio_apuracao.py` verifica os alertas a cada ciclo, no relógio de 2022, acompanhando por padrão o deputado estadual 13713 (`--interesse`). A conferência ganhou duas verificações:
- nenhum alerta crítico com a coleta normal;
- o alerta de leitura do Governador chegou a "vitória no 1º turno".

## Decisões

- **Mesmos números do site.** O vigia usa `app.state.consultas`, e `create_app` cria o vigia com elas. A leitura e a situação dos candidatos nunca divergem do que a página mostra.
- **Dois relógios.** "Coleta parada" compara o relógio REAL com `ultimo_ciclo_fim`, gravado pelo coletor em UTC. "Sem avanço" compara a hora de Brasília com `DT_TOTALIZACAO`, a hora do TSE. No ensaio, o segundo é o relógio de 2022.
- **A causa esconde a consequência.** Com a coleta parada, bloqueada ou encerrada, "sem avanço" não é avisado: a causa já está na tela.
- **Deputados, não todos.** Com mais de mil candidatos, avisar toda mudança seria ruído. A equipe escolhe quem acompanhar, pelo botão ou por `--interesse`. Os majoritários têm o alerta de leitura, que vale para todos.
- **Sem serviço externo** (e-mail, Telegram): nada de credenciais na máquina da noite. O boletim da rodada 28 cobre quem está longe.

## Achados (corrigidos)

1. **Ensaio: "Apuração sem avanço há 24 min" às 23h58, com 99,99% das seções.**
   - Em 2022, o RJ ficou em 99,99% das 23h33 às 00h07; é a cauda normal da apuração, não um travamento.
   - **Correção:** sem aviso quando todo cargo em andamento está acima de `CAUDA_PCT` = 99,5%.
   - **Teste:** `test_cauda_da_apuracao_nao_e_travamento`.
2. **Ensaio: "projeção de 58,7% (de 58,7% a 58,7%)" no resultado final.**
   - **Correção:** com a margem zerada, o texto diz "com 58,7% dos válidos".
   - **Teste:** `test_resultado_final_nao_e_chamado_de_projecao`.
3. **O cabeçalho mais cheio espremia o texto de situação**, que quebrava em 7 linhas. Quando o status chegava, a página descia cerca de 100 px, e o teste de dica do Perfil × voto passou a falhar de forma intermitente (3 em 4 rodadas), porque o mouse ia para onde o ponto estava antes.
   - **Correção:** `.situacao` com base de 420 px; sem espaço, as abas descem de linha.
   - **Verificação:** 4 de 4 rodadas dos e2e e 4 de 4 da suíte completa.
4. **Corrida no botão "Acompanhar".** O `abrirPorHash` inicial roda depois do 1º `tick` e redesenhava o candidato enquanto o pedido estava em curso; o botão novo mostrava o rótulo antigo.
   - **Correção:** o rótulo vem sempre do estado dos alertas (`rotularAcompanhar`, chamado a cada desenho).
5. **Símbolos que não existem em toda fonte** (🔔, ⛔) apareciam como "▯" no Chrome do WSL. Ficaram só símbolos básicos: ✖, ⚠, ℹ, ✓.

## Arquivos

- **Novos:**
  - `apuracao/alertas.py`;
  - `test_alertas.py`: 19 testes;
  - `test_alertas_e2e.py`: 2 testes no Chrome.
- **Alterados:**
  - `apuracao/divulgacao/coletor.py`: `tipo_erro`, `pausa_s` e `tipo_do_erro`;
  - `coletar_resultados.py`;
  - `apuracao/web/app.py`: vigia, rotas e `ROTAS_SO_LOCAL`;
  - `apuracao/web/static/{index.html,app.js,style.css}`;
  - `site_apuracao.py`: thread, `--interesse` e `--sem-alertas`;
  - `ensaio_apuracao.py`: alertas no relatório e 2 verificações;
  - `apuracao/boletim.py`: `agora_brasilia` vem de `alertas`;
  - `conftest.py`: a fixture `site` expõe o `app`;
  - `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/TODO.md`, `docs/INDEX.md`, `CLAUDE.md`.

## Verificação

- **Testes:** `pytest -q` → **246 passando**, contra 225 na rodada 28.
  - A suíte completa rodou 4 vezes seguidas sem falha, depois das correções 3 e 4.
  - Os testes dos alertas cobrem:
    - coleta parada: avisa uma vez, o texto acompanha a duração e depois resolve;
    - bloqueio, com a pausa sem virar "parada";
    - falha de rede isolada × persistente;
    - divulgação indisponível;
    - sem avanço, a cauda e a causa escondendo a consequência;
    - nada antes da apuração;
    - leituras;
    - deputado acompanhado: consolidado, fora da disputa e eleito;
    - persistência ao reiniciar;
    - arquivo corrompido e eleição passada;
    - erro no laço;
    - a API e o 403 na rede;
    - no Chrome: faixa, aviso, som, título, contador, painel, Esc, resolvido e o botão "Acompanhar".
- **Ensaio geral** (`python ensaio_apuracao.py`, com os ajustes): **RESULTADO OK** em 14,2 min reais.
  - **Coleta:** 52 ciclos, 5.861 arquivos pedidos (5.522 novos, 339 com 304), nenhum 404 e nenhum erro.
  - **Site:** 4.979 consultas, nenhum erro 5xx; `/api/painel` com p50/p95 de 135/1.152 ms.
  - **Conferência com o oficial:**
    - válidos iguais nos majoritários;
    - cadeiras 46/46 e 70/70;
    - Castro eleito;
    - 9 boletins, com o final.
  - **Alertas da noite de 2022 refeita**, todos de novidade e nenhum crítico:

    | Hora (2022) | Alerta |
    |---|---|
    | 19h15 | Governador: vitória no 1º turno projetada — Castro 55,8% (51,3% a 60,3%), com 10,4% do eleitorado apurado |
    | 19h36 | Presidente: mais votado no estado definido — Bolsonaro 49,7% (45,9% a 53,5%), com 22,0% apurado |
    | 20h10 | Senador: eleito (projeção) — Romário 35,5% (32,8% a 38,2%), com 47,2% apurado |
    | 00h20 | Governador: vitória confirmada (58,7%); Senador: eleito (36,2%); Presidente: mais votado confirmado (51,1%) |
    | 00h20 | 13713 Marina do MST: eleita (antes: consolidado) — por QP, 46.422 votos |

  - No 1º ensaio, antes da correção 1, houve também "Apuração sem avanço há 24 min" às 23h58, resolvido às 00h07.
- **Visual:** conferido no Chrome, claro a 1.400 px e escuro a 390 px (faixa, avisos e painel).
- **Sites de teste:** reiniciados com o código novo (8000 simulado com `--coletar`, 8022 e 8023 históricos); `/api/alertas` responde nos três.

## Pendências

- **Som na noite:** clicar uma vez na página ao abrir; o navegador bloqueia áudio sem interação.
- **Processo inteiro caído:** se o processo do site cair, não há quem avise. O terminal mostra o erro, e o roteiro já manda subir de novo.
- **Próximo item do TODO:** 9, a transferência do 1º para o 2º turno por local, para 25/10.
