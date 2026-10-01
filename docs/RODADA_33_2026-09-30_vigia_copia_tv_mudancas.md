# Rodada 33 — Vigia de processo, cópia de segurança, modo TV e "o que mudou"

30/09/2026 · pedido do usuário: "Registre tudo no TODO. Faremos por agora os itens 1, 2, 3 e 4. Os itens 5, 6 e 7 somente após a apuração. O item 2 garante que depois eu poderei analisar todas as parciais geradas pelo TSE para analisar a evolução da apuração."

As sete sugestões entraram no TODO como itens 11–17. Esta rodada fez os itens 11–14, para a noite de 4/10. Os itens 15–17 ficam para depois da apuração.

## 11. Vigia de processo (`apuracao/vigia_site.py`, `vigiar_site.py`)

- **Uso:** `python vigiar_site.py -- python site_apuracao.py --ambiente oficial --coletar --abrir …`. O vigia sobe o site como processo filho; a saída do site continua no mesmo terminal.
- **Verificação:** `/api/status` a cada 30 s. O vigia reinicia o site se:
  - o **processo terminar** (erro, `kill`), na hora;
  - o site **não responder** em 3 verificações seguidas (travado), depois de encerrá-lo (primeiro com `SIGTERM`; se não sair em 15 s, `SIGKILL`).
- **Proteções:**
  - 90 s de tolerância depois de subir, porque o 1º ciclo do coletor baixa cerca de 470 arquivos;
  - pausa de 60 s depois de 5 reinícios em 10 min (por exemplo, com a porta ocupada), para não entrar em laço;
  - o `--abrir` sai do comando no reinício, para não abrir outra janela do Chrome.
- **Registro:**
  - `dados_2026/vigia/porta_<N>.log`: os eventos;
  - `dados_2026/vigia/porta_<N>.json`: o estado, lido pelo portal;
  - campainha no terminal a cada reinício.
- **Portal:**
  - cada cartão mostra "Vigia: sem reinícios" ou "reiniciado N vez(es); último: …";
  - um site que sumiu fica na lista como **"fora do ar"** (com a hora em que foi visto no ar), em vez de simplesmente desaparecer.
- **Teste real:** site 2022 na porta 8026.
  - `kill -9` no processo: reiniciado em 3 s.
  - `SIGSTOP` (travado): 2 verificações sem resposta, encerramento forçado e reinício, em cerca de 30 s com os intervalos curtos do teste.
  - Ao encerrar o vigia, o site vai junto.

## 12. Cópia de segurança automática (`apuracao/copia.py`, `copiar_dados.py`)

- **O que já existia:** o coletor grava em `raw/` **cada versão distinta** de cada JSON do TSE, comprimida (a evolução da apuração, parcial a parcial). Junto ficam `historico_totais.parquet` (totais de cada versão, por UF e município) e `historico_candidatos/`.
- **A cópia**, para outra pasta (`--copia-dir`; **use outro disco**, por exemplo `/mnt/d/…` no WSL):
  - **espelho incremental de `raw/`** a cada 5 min: os arquivos nunca mudam, então só entram os novos;
  - **instantâneo** do resto (último estado, séries, históricos, boletins, alertas, status) a cada hora cheia, mais um **"final"** quando todos os cargos da UF terminam; ele só aparece completo (troca atômica);
  - guarda os 6 últimos da hora; o final e as cópias manuais nunca são apagados;
  - um registro em `copias.json`.
- **Uso:**
  - o site com `--coletar` faz a cópia sozinho (padrão `copias/<nome dos dados>`, com aviso no log para usar outro disco; `--sem-copia` desliga);
  - `copiar_dados.py --dados … --destino … [--vigiar]` serve para cópia manual ou para o coletor rodando à parte.
- **Guarda:** a cópia recusa um destino dentro da própria pasta de dados. Uma falha (por exemplo, disco da cópia desconectado) vai para o log e o laço segue; nunca derruba o site.
- **Tempo:** a primeira cópia completa da noite de 2022 (5.677 parciais, 107 MB) levou 1,4 s; a seguinte, sem arquivo novo, 0,2 s. Instantâneo de 9,3 MB.
- **Restaurar e analisar:** passo a passo no roteiro ("Se algo der errado" e "Depois"), incluindo `serie.reconstruir`. **Limite:** o coletor pede cada arquivo uma vez por ciclo (60 s); se o TSE publicar duas versões dentro do mesmo minuto, só a última é guardada.

## 13. Modo TV (painel)

- **Como abrir:** botão "Modo TV" no painel, ou o endereço `#painel?tv=1`, para deixar aberto na máquina ligada à TV.
- **Tela:**
  - tela cheia (o navegador só permite depois de um clique);
  - somem as abas e os controles; a faixa de alertas e o "o que mudou" continuam;
  - **um cargo por vez**, trocando a cada 20 s;
  - o cartão é ampliado com `zoom` 1,4, porque os cartões usam tamanhos fixos em px e só o tamanho da fonte não bastava;
  - um rodapé mostra cargo (n de 6), última coleta, último boletim e as teclas.
- **Teclas:** Esc sai (também ao sair da tela cheia), ←/→ navegam, espaço pausa. O redesenho de 60 s mantém o cargo da vez.

## 14. "O que mudou" desde o boletim anterior

- **Fotografia:** cada boletim grava `<nome>.json`, uma fotografia leve com % apurado, líder, leitura da projeção, cadeiras por partido, eleitos e consolidados.
- **Comparação** (`boletim.mudancas`), com a do boletim anterior. Itens:
  - avanço da apuração, numa linha só para os cargos com o mesmo avanço;
  - totalização final;
  - novo líder;
  - leitura da projeção;
  - cadeiras por partido ("PL 16 → 17");
  - quem entrou e quem saiu dos eleitos;
  - novos consolidados e quem deixou de ser.
- **No boletim:** seção "O que mudou desde o boletim das 20h (…)" no HTML e aba "Mudanças" na planilha.
- **No painel:** caixa "O que mudou desde o boletim das …" com o último boletim × **agora**, pela rota `GET /api/mudancas`, com cache pela versão dos dados e do último boletim.
- **Exemplo real do ensaio** (boletim das 21h × 20h de 2022):
  - Dep. Federal: "cadeiras: PT/PC do B/PV 5 → 6; PSD 5 → 4; PP 4 → 3; PTB 0 → 1";
  - quem entrou (Jorge Braz, Laura Carneiro, Bebeto…) e quem saiu dos eleitos;
  - "11 novo(s) consolidado(s)".

## Ensaio geral

O ensaio (`ensaio_apuracao.py`) agora faz a cópia de segurança no relógio de 2022, em `dados_2026/ensaio_2022_copias/`. A conferência ganhou "cópia final com todas as parciais do TSE" e "boletim final diz o que mudou".

**Resultado: OK** em 14,6 min:
- 53 ciclos, 5.943 arquivos, nenhum erro;
- 5.088 consultas, nenhum 5xx; painel com p50/p95 de 145/713 ms;
- 9 boletins;
- 9 cópias (8 da hora e a final), 0,1 a 1,2 s cada;
- **5.695 de 5.695 parciais** na cópia;
- o boletim final diz o que mudou.

## Achados no caminho

- **Poda da cópia apagando o lugar errado:** a primeira versão ordenava todos os instantâneos pelo nome, e as cópias manuais (`manual_…`) ficariam no lugar das da hora. Agora só as da hora (`AAAA-MM-DD_HHhMM`) são podadas. Há teste.
- **Modo TV com letra pequena:** a fonte maior no `body` não chegava aos cartões (tamanhos fixos em px). A correção foi `zoom` no cartão da vez.
- **Teste de rotas restritas lento:** `test_site_na_rede…` passou a levar 120 s porque consultava `/api/perfil/info`, que tenta baixar a malha de bairros do IBGE, com limite de 120 s, quando o cache está vazio. O teste agora usa uma rota restrita que responde sem rede, e voltou a 0,09 s. Na noite, a malha já está no cache.
- **"Apuração 45,87% → 94,65%" repetida em 4 cargos:** passou a sair numa linha só, com os cargos juntos.

## Arquivos

- **Novos:**
  - `apuracao/copia.py`, `copiar_dados.py`;
  - `apuracao/vigia_site.py`, `vigiar_site.py`;
  - `test_copia_vigia.py`: 10 testes;
  - `test_tv_mudancas_e2e.py`: 2 testes no Chrome.
- **Alterados:**
  - `apuracao/boletim.py`: `fotografia`, `mudancas`, `_juntar_apuracao`, `fotografia_anterior`, `mudancas_agora`, seção e aba de mudanças, `<nome>.json`;
  - `apuracao/web/app.py`: `/api/mudancas`, `ultimo_boletim` no status;
  - `apuracao/web/static/*`: caixa "o que mudou", modo TV;
  - `site_apuracao.py`: `--copia-dir`, `--copia-min`, `--sem-copia`;
  - `portal.py`: vigia e "fora do ar";
  - `ensaio_apuracao.py`: cópia e 2 verificações;
  - `test_boletim.py`: 2 testes;
  - `test_site.py`;
  - `docs/TODO.md`: itens 11–17;
  - `docs/ROTEIRO_NOITE_DA_ELEICAO.md`: comando da noite com o vigia e `--copia-dir`, TV, restaurar, analisar as parciais;
  - `CLAUDE.md`, `docs/INDEX.md`.

## Verificação

- **Testes:** `pytest -q` → **293 passando**, duas vezes seguidas, em cerca de 60 s (279 na rodada 32).
- **Ensaio:** OK (acima).
- **Teste real do vigia:** processo morto e processo travado (acima).
- **Visual:**
  - modo TV no Chrome a 1.600 px, tema escuro;
  - portal com o site 8000 sob o vigia.
- **No ar:**
  - 8000 (simulado, **agora sob o vigia**, com cópia numa pasta temporária);
  - 8022 e 8023 (2022);
  - portal na 8100.

## Pendências

- **Na noite:** escolher a pasta da cópia **em outro disco** e usá-la no `--copia-dir` do comando do roteiro.
- **Itens 15–17 do TODO:** depois da apuração.
- **4b:** recalibrar com 2026, quando saírem os microdados.
- **Malha de bairros:** o primeiro download, com o cache vazio, pode levar até 120 s se o IBGE estiver lento (não afeta a noite: já está no cache).
