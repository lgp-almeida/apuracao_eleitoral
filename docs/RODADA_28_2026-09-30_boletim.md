# Rodada 28 — Boletim automático para a equipe

30/09/2026 · pedido do usuário: "Siga para o item 7" (item 7 de `docs/TODO.md`)

## Objetivo

Quem não está no computador do site não vê nada, e abrir o site na rede sem senha não é recomendável (rodada 27). O objetivo é gerar, a cada hora e na totalização final, um resumo pronto para enviar à equipe:
- painel;
- projeção com margem;
- cadeiras, com consolidados e em disputa;
- destaques por município.

Formato: HTML autônomo (um arquivo) e planilha.

## Entregas

### Conteúdo (`apuracao/boletim.py`)

- **Cargos majoritários** (Presidente BR e RJ, Governador, Senador):
  - % das seções, comparecimento, abstenção, brancos e nulos, hora da totalização;
  - os 8 primeiros no HTML (todos os do painel na planilha), com votos, % válidos e barra;
  - com a apuração em andamento: projeção e faixa por candidato, a leitura ("indefinido", "vitória projetada"…) e "onde falta mais voto".
- **Deputados:**
  - vagas, válidos, quociente eleitoral e a fonte;
  - cadeiras por partido ou federação "se a apuração acabasse agora", com a projeção e a faixa p5–p95 a partir de 30% apurado;
  - os eleitos, com "por QP" / "por média" e o status na projeção (consolidado / em disputa);
  - os que estão fora na projeção mas ainda em disputa, com a % de simulações em que se elegem;
  - no fim, a conferência com os eleitos declarados pelo TSE.
- **Por município** (Governador; se não houver, Presidente ou Senador):
  - totalizados, com apuração e em quantos o líder do estado não lidera;
  - os 12 maiores eleitorados com líder, 2º e vantagem em p.p.;
  - onde o líder do estado não lidera.
- **Avisos no topo:** ambiente de teste (simulado, ensaio), arquivo histórico e último erro do coletor.

### Formatos

- **HTML de um arquivo:**
  - CSS embutido, sem script, sem nada externo: abre sem internet, no celular e no e-mail;
  - tema claro e escuro (`prefers-color-scheme`);
  - na impressão, as seções recolhidas (`<details>`) saem abertas;
  - largura de celular sem rolagem da página (as tabelas rolam dentro do cartão; conferido a 390 px);
  - todo texto do TSE passa por `html.escape` (o simulado tem nomes com aspas e símbolos).
- **Planilha** (`xlsxwriter`), com filtro e cabeçalho fixo em todas as abas:
  - Resumo e Cargos;
  - uma aba por cargo majoritário, com a projeção;
  - para cada cargo de deputado, as abas "cadeiras", "eleitos" e "projeção";
  - municípios com todas as linhas.

### Quando gerar (`Boletineiro`)

- **Boletim da hora:** um por intervalo de relógio (18h00, 19h00…), enquanto a apuração anda. Arquivo `boletim_<AAAA-MM-DD>_<HHhMM>.html`/`.xlsx`.
- **Boletim final:** `boletim_final.*`, uma vez, quando todos os cargos **na UF** têm totalização final. Depois dele não há boletim de hora.
- **Último boletim:** `boletim_ultimo.*` é a cópia do mais recente, para mandar sem procurar.
- **Memória:** são os próprios arquivos. Reiniciar o processo não repete nem pula boletim.
- **Gravação atômica:** temporário e troca. A planilha é gravada antes do HTML, que é o que marca o boletim como feito.
- **Erros:** um erro num boletim vai para o log, e o laço tenta de novo em 30 s. O boletim nunca derruba o site nem o coletor.

### Onde roda

- **`site_apuracao.py --coletar`:** grava sozinho, numa thread, em `<dados>/boletins/`.
  - `--boletim-min 30` muda o intervalo;
  - `--sem-boletim` desliga.
- **`gerar_boletim.py`:**
  - sem opções: um boletim agora, fora de hora;
  - `--vigiar`: a cada hora e no fim, para quando coleta e site rodam em processos separados.
- **`ensaio_apuracao.py`:** gera os boletins no relógio de 2022 e confere que o final foi gravado ("boletim final gravado" na conferência).

## Decisões

- **Mesmos números do site, por construção.** O boletim não recalcula nada: `create_app` expõe `app.state.consultas` (`Consultas` em `web/app.py`), com as MESMAS funções das rotas `/api/painel`, `/api/projecao` e `/api/cadeiras` e os mesmos caches por versão (rodada 27). Um teste confere votos, projeção e cadeiras da planilha contra a API.
- **Arquivo, não serviço.** Nada é enviado para fora: a equipe recebe o arquivo pelo canal que já usa. Isso evita credenciais na máquina da noite e a exposição do site.
- **O final não espera o Presidente no Brasil.** O Brasil aparece no boletim final com o % que tiver, e `gerar_boletim.py` faz outro quando ele terminar. O motivo está no achado do ensaio, abaixo.
- **Hora cheia de Brasília** (`agora_brasilia`, sem fuso, a mesma convenção da hora de totalização do TSE). O relógio é injetável: o ensaio usa o de 2022, e os testes, um fixo.

## Achados do ensaio (corrigidos)

1. **O boletim final não saía.** A regra exigia totalização final em todas as linhas BR e UF.
   - **O que aconteceu no ensaio:** o RJ terminou às 00h19 de 2022, mas o Presidente no Brasil ficou em 99,94% (o exterior termina horas depois).
   - **Correção:** o final considera só os cargos na UF.
   - **Teste:** `test_final_nao_espera_o_presidente_no_brasil`, que falha na regra antiga.
2. **Municípios sem nome no ensaio.** A `SessaoEnsaio` servia a lista de municípios do recorte de teste, que tem 3. Os outros 89 do RJ ficavam sem nome no site e no boletim do ensaio ("Onde falta mais voto" com linhas em branco).
   - **Alcance:** no simulado e no oficial a lista vem completa do TSE (92 municípios).
   - **Correção:** o ensaio passa a servir a lista do 2022 importado.
   - **Teste:** `test_sessao_serve_a_lista_de_municipios_dada`.
3. **Textos:**
   - "Fora hoje, mas ainda em disputa" virou "Fora na projeção, mas ainda em disputa": o "fora" é na distribuição projetada, e o candidato pode estar entre os eleitos da apuração parcial;
   - "(maiores 1)" virou a contagem.

## Arquivos

- **Novos:**
  - `apuracao/boletim.py`: conteúdo, HTML, planilha e `Boletineiro`;
  - `gerar_boletim.py`: linha de comando;
  - `test_boletim.py`: 11 testes.
- **Alterados:**
  - `apuracao/web/app.py`: `Consultas` e `app.state.consultas`;
  - `site_apuracao.py`: thread do boletim, `--sem-boletim` e `--boletim-min`;
  - `ensaio_apuracao.py`: boletins no relógio de 2022, conferência do final e `--boletim-min`;
  - `apuracao/ensaio.py`: `SessaoEnsaio(…, municipios)`;
  - `test_ensaio.py`: 1 teste;
  - `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/TODO.md`, `docs/INDEX.md`, `CLAUDE.md`.

## Verificação

- **Testes:** `pytest -q` → **225 passando**, contra 213 na rodada 27; os e2e incluídos.
  - Os testes do boletim cobrem:
    - um boletim por hora cheia, sem repetir ao reiniciar;
    - intervalos de 15, 30, 60 e 120 min;
    - o final uma vez só, sem boletim de hora depois dele;
    - nada gerado sem votos;
    - nome com HTML escapado e página sem script nem recurso externo;
    - os mesmos números da API na planilha;
    - erro no boletim sem derrubar o laço;
    - a linha de comando;
    - o final sem o Presidente no Brasil.
- **Ensaio geral** (`python ensaio_apuracao.py`, com as correções): **RESULTADO OK** em 14,5 min reais (17h21 → 00h20 de 2022).
  - **Boletins:** 8 de hora (17h a 00h) e o final, todos sem erro, cada um em 0,1–1,6 s.
  - **Coleta:** 53 ciclos, 5.978 arquivos pedidos (5.610 novos, 368 com 304), nenhum 404 e nenhum erro.
  - **Site:** 5.053 consultas de 4 usuários simultâneos, nenhum erro 5xx. `/api/painel` com p50/p95 de 141/1.081 ms.
  - **Conferência com o oficial:**
    - válidos iguais nos majoritários, com diferença de 0,005% e 0,006% nos deputados;
    - cadeiras 46/46 e 70/70;
    - Castro eleito;
    - boletim final gravado.
  - **Boletim das 21h:**
    - Dep. Federal: 40 consolidados e 11 em disputa por 6 vagas;
    - Dep. Estadual: 65 consolidados e 11 em disputa por 5 vagas;
    - 46 de 92 municípios totalizados; Castro só não lidera em Niterói.
  - **Visual:** conferido no Chrome, claro a 1.100 px e escuro a 390 px.
- **Sites de teste:** reiniciados com o código novo (8000 simulado com `--coletar`, 8022 e 8023 históricos).
  - O de 8000 gravou `dados_2026/simulado/boletins/boletim_final.*` logo ao subir, porque o simulado está totalizado.
- **Linha de comando:** `gerar_boletim.py` sobre os dados do ensaio leva 1,3 s.

## Pendências

- **Presidente no Brasil depois do final:** se ele terminar horas depois, rodar `python gerar_boletim.py --ambiente oficial` para um boletim com o Brasil a 100%.
- **2º turno:** o mesmo mecanismo, com `--turno 2`. Não houve ensaio de 2º turno com boletim; o conteúdo se adapta aos cartões que o painel tiver.
- **Próximo item do TODO:** 8, alertas durante a noite. Um alerta poderia apontar para o boletim da hora.
