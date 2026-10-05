# TODO — propostas pendentes

Lista viva das propostas aceitas e ainda não feitas. Quando uma proposta for feita, marque-a como feita e aponte a rodada que a entregou (`docs/RODADA_NN_…`). Não apague a linha.

Registrado em 30/09/2026, a 4 dias do 1º turno (4/10/2026). A ordem segue a prioridade: primeiro o que serve na noite da apuração, depois o que depende dos microdados de 2026, publicados dias após o pleito.

| # | Proposta | Quando serve | Situação |
|---|---|---|---|
| 1 | Distribuição de cadeiras de deputado em tempo real | noite de 4/10 | **feito**: [RODADA_20](RODADA_20_2026-09-30_cadeiras_de_deputado.md) |
| 2 | Projeção do resultado final durante a apuração | noite de 4/10 | **feito**: [RODADA_21](RODADA_21_2026-09-30_projecao_do_resultado.md) |
| 2b | Projeção das cadeiras de deputado (consolidados × em disputa) | noite de 4/10 | **feito**: [RODADA_22](RODADA_22_2026-09-30_projecao_de_cadeiras.md) (pedido do usuário em 30/09) |
| 3 | Ensaio geral e roteiro de prontidão | 3/10 e 4/10 | **feito**: [RODADA_23](RODADA_23_2026-09-30_ensaio_geral.md) e [roteiro](ROTEIRO_NOITE_DA_ELEICAO.md); falta só a checagem do oficial em 3/10 |
| 4 | Preparar os dados de 2026 assim que o TSE publicar | dias após o pleito | **feito**: [RODADA_24](RODADA_24_2026-09-30_microdados_2026.md); depois de 4/10, rodar `preparar_2026.py --vigiar` |
| 4b | Recalibrar margem da projeção e σ das cadeiras com 2026 | quando saírem os microdados de 2026 | pendente — procedimento pronto e ensaiado: [RECALIBRAR_MARGENS](RECALIBRAR_MARGENS.md), [RODADA_25](RODADA_25_2026-09-30_recalibracao.md) |
| 5 | Perfil por local de votação no estado inteiro | pós-eleição | **feito**: [RODADA_26](RODADA_26_2026-09-30_perfil_por_local.md) (setores + regressão com vários indicadores) |
| 6 | Revisão de código e de segurança do caminho da noite + versões fixadas | antes de 4/10 | **feito**: [RODADA_27](RODADA_27_2026-09-30_revisao_noite.md) (3 bloqueadores e 4 importantes corrigidos) |
| 7 | Boletim automático para a equipe (HTML de um arquivo + planilha, a cada hora e no fim) | noite de 4/10 | **feito**: [RODADA_28](RODADA_28_2026-09-30_boletim.md) (gravado pelo site com `--coletar`; `gerar_boletim.py`) |
| 8 | Alertas durante a noite (coletor parado, bloqueio, apuração estagnada, mudança de leitura) | noite de 4/10 | **feito**: [RODADA_29](RODADA_29_2026-09-30_alertas.md) (site com som e destaque + terminal; deputados acompanhados) |
| 9 | Transferência do 1º para o 2º turno por local (e abstenção extra) | 2º turno, 25/10 | **feito**: [RODADA_30](RODADA_30_2026-09-30_transferencia_turnos.md) (aba "1º → 2º turno"; validado com Presidente 2022 e prefeito 2024) |
| 10 | Mapa por local de votação (voto, perfil, resíduo do Perfil × voto) | pós-eleição | **feito**: [RODADA_32](RODADA_32_2026-09-30_mapa_por_local.md) (aba Mapas → Detalhe "Locais de votação") |
| 11 | Vigia de processo: reinicia o site se parar de responder, com log e aviso no portal | noite de 4/10 | **feito**: [RODADA_33](RODADA_33_2026-09-30_vigia_copia_tv_mudancas.md) (vigiar_site.py) |
| 12 | Cópia de segurança automática a cada hora (dados, séries e JSON brutos de todas as parciais) | noite de 4/10 | **feito**: [RODADA_33](RODADA_33_2026-09-30_vigia_copia_tv_mudancas.md) (copia.py / --copia-dir) |
| 13 | Modo TV no painel (tela cheia, fonte grande, rotação automática dos cargos) | noite de 4/10 | **feito**: [RODADA_33](RODADA_33_2026-09-30_vigia_copia_tv_mudancas.md) (#painel?tv=1) |
| 14 | "O que mudou" desde o boletim anterior, no boletim e no painel | noite de 4/10 | **feito**: [RODADA_33](RODADA_33_2026-09-30_vigia_copia_tv_mudancas.md) (boletim e painel) |
| 15 | Bancadas 2026 × 2022 (eleitos por partido/federação, reeleitos, novatos; variação por local) | após a apuração | pendente |
| 16 | Conferência automática do tempo real com os microdados de 2026 | após a apuração | pendente |
| 17 | Novas camadas no mapa por local (destino dos eliminados no 2º turno; variação 2022 → 2026) | após a apuração | pendente |
| 18 | Várias UFs: pasta de dados por UF, limite de acessos ao TSE dividido entre UFs, ensaio/prontidão/calibração por UF, portal por UF | 2º turno, 25/10 | pendente |
| 19 | Painel nacional do Presidente (mapa do Brasil por UF, % apurado e vencedor em cada estado) | a definir | pendente |
| 20 | Comparação entre UFs (abstenção, brancos/nulos, transferência 1º → 2º turno) | após a apuração | pendente |
| 21 | Análise das parciais da noite (`analisar_coleta.py`): TSE × coletor, atrasos, versões anteriores, pausas | antes do 2º turno, 25/10 | pendente (feita à mão na [RODADA_36](RODADA_36_2026-10-04_coleta_versao_anterior.md)) |

---

## 1. Distribuição de cadeiras de deputado em tempo real — FEITO (rodada 20)

- **Por quê:** "quem entra" é a pergunta mais feita na noite da eleição. Hoje o site só lê o quociente eleitoral que vem no JSON do TSE (`carg[].qe`) e não calcula a distribuição das vagas.
- **O quê:**
  - calcular, a cada coleta, para Dep. Federal e Dep. Estadual: quociente eleitoral, quociente partidário, cláusula de 10% e sobras em duas fases, pela regra de 2026 (art. 12-A; ver `Anexo I`, bloco A4);
  - com isso, obter as **cadeiras por partido ou federação** e a **lista de eleitos projetada**, com os suplentes.
- **Na tela:**
  - cartão no painel com as cadeiras por partido;
  - na aba Candidato, a situação do candidato: "entra", "suplente" ou "precisa de mais X votos".
- **Validação:** reproduzir as vagas reais de 2022 com os dados já importados (`dados_2026/historico_2022_t1`). Atenção: o STF derrubou a regra 80/20 (ADIs 7228/7263/7325) e 2022 foi recalculado em 2025; confira qual versão os microdados trazem.

## 2. Projeção do resultado final durante a apuração — FEITO (rodada 21)

- **Por quê:** os municípios apuram em ritmos diferentes, e o percentual parcial do estado fica enviesado pelos que apuram primeiro.
- **O quê:**
  - completar cada município com o seu percentual atual;
  - pesar cada um pelo eleitorado e pela abstenção que ele teve em 2022;
  - daí, projetar o total do estado para Governador, Senador e Presidente (RJ).
- **Na tela:**
  - "projeção: X% (intervalo)";
  - votos que ainda faltam por município;
  - a chance de haver 2º turno para Governador.
- **Dados:** só o que o coletor já grava (série por município). Validar com a série da apuração de 2022.

## 3. Ensaio geral e roteiro de prontidão — FEITO (rodada 23)

- **3/10:** quando o TSE publicar os códigos oficiais, rodar `coletar_resultados.py --ambiente oficial --uma-vez`.
- **Ensaio:** reproduzir uma apuração inteira (do simulado ou a de 2022, reconstituída pela hora de cada seção — ver rodada 21) em velocidade acelerada, com o site aberto e consultas simultâneas. Pedidos em paralelo já revelaram um defeito na rodada 19.
- **Roteiro de operação** (`docs/`):
  - o que fazer se o TSE bloquear o acesso ou sair do ar;
  - como reiniciar sem perder o histórico;
  - quais comandos rodar e em que ordem.

## 4. Preparar os dados de 2026 assim que o TSE publicar — FEITO (rodada 24)

- **Verificação:** a cada hora, um único acesso leve (HEAD) aos ZIPs de 2026: `votacao_secao_2026_RJ`, `_BR`, `detalhe_votacao_secao_2026`.
- **Conversão:** ao aparecerem, baixar e converter automaticamente. Assim ficam prontos sem intervenção os mapas por bairro, a comparação por bairro e o Perfil × voto de 2026.
- **Primeira análise:** a transferência 2022 → 2026.

## 5. Perfil por local de votação no estado inteiro — FEITO (rodada 26)

- **Por quê:** o Perfil × voto (rodada 19) cobre só os 31 municípios com malha de bairros. Faltam 61 municípios, cerca de 21% do eleitorado.
- **Como:** os agregados do Censo 2022 por **setor censitário** cobrem o estado todo. Ligar cada local de votação ao setor que o contém, ou a um raio em volta dele, e somar os setores por local.
- **Junto:** uma análise com vários indicadores ao mesmo tempo (por exemplo, escolaridade controlada por renda), que hoje é feita um indicador por vez.

## 6. Revisão de código e de segurança do caminho da noite — FEITO (rodada 27)

- **Por quê:** as rodadas 20–26 mexeram muito em cadeiras, projeção, API e coletor. O ensaio geral achou 3 defeitos que só apareceriam na noite; pode haver outros.
- **Escopo:** só o que roda em 4/10:
  - `apuracao/divulgacao/{cliente,modelo,coletor,serie}.py`;
  - as rotas do painel, candidato, projeção e cadeiras em `apuracao/web/app.py`;
  - `apuracao/{projecao,cadeiras,projecao_cadeiras}.py`;
  - `site_apuracao.py`.
  Com as skills `code-reviewer` e `security-auditor`, e as correções vêm com teste.
- **Também:**
  - fixar as versões em `requirements.txt` (hoje só há mínimos, `>=`);
  - avaliar o que `--host 0.0.0.0` expõe, já que não há senha;
  - rodar o ensaio geral no fim.

## 7. Boletim automático para a equipe — FEITO (rodada 28)

- **O quê:** a cada hora e na totalização final, um resumo pronto para enviar: painel, projeção com margem, cadeiras (consolidados e em disputa), destaques por município.
- **Formato:** HTML autônomo (um arquivo) e planilha.
- **Por quê:** quem não está no computador do site não vê nada, e expor o site na rede sem senha não é recomendável.

## 8. Alertas durante a noite — FEITO (rodada 29)

- **Quando avisar:**
  - coletor parado ou com erro;
  - bloqueio do TSE;
  - apuração estagnada;
  - leitura da projeção mudando ("indefinido" → "vitória projetada" ou "2º turno");
  - candidato de interesse virando "consolidado" ou saindo da disputa.
- **Como:** aviso no próprio site (som e destaque) e no terminal, sem serviço externo.

## 9. Transferência do 1º para o 2º turno por local — FEITO (rodada 30)

- **Quando:** se houver 2º turno para Governador em 25/10.
- **O quê:** estimar, por local de votação, para onde foram os votos dos eliminados, e medir a abstenção extra (inferência ecológica, com as ressalvas).
- **Validação:** testar antes com Presidente 2022 (1º e 2º turno).

## 10. Mapa por local de votação — FEITO (rodada 32)

- **O quê:** pontos coloridos na aba Mapas (voto, indicadores de perfil, resíduo do Perfil × voto). É a pendência da rodada 26.

---

Registrado em 30/09/2026 (pedido do usuário: "Registre tudo no TODO. Faremos por agora os itens 1, 2, 3 e 4. Os itens 5, 6 e 7 somente após a apuração"). Os itens 11–14 são para a noite de 4/10; os 15–17, depois da apuração.

## 11. Vigia de processo — FEITO (rodada 33)

- **Por quê:** se o processo do site cair, hoje ninguém é avisado (pendência da rodada 29).
- **O quê:** um script à parte que consulta `/api/status` a cada 30 s. Se o site não responder por algumas vezes seguidas, ele sobe o site de novo com os mesmos argumentos e grava o evento num log.
- **No portal:** o site parado aparece como "fora do ar".

## 12. Cópia de segurança automática — FEITO (rodada 33)

- **Por quê:** proteger os dados contra disco cheio ou arquivo corrompido no meio da apuração e **guardar todas as parciais do TSE** para analisar depois a evolução da apuração (pedido do usuário).
- **O que já existe:** o coletor guarda em `raw/` cada versão distinta de cada JSON baixado, comprimida (no ensaio de 2022, 5.677 versões em 107 MB).
- **O quê:** copiar `dados_2026/<ambiente>` (último estado, séries, `raw/`, boletins, alertas) a cada hora para outra pasta, de forma incremental: os arquivos de `raw/` nunca mudam, então só entram os novos.
- **Guarda:** as últimas cópias horárias, mais uma final.
- **Leitura depois:** documentar como ler a evolução a partir de `raw/`.

## 13. Modo TV no painel — FEITO (rodada 33)

- **O quê:** tela cheia, fonte grande, sem os controles; passa sozinho pelos cargos a cada 20 s.
- **Visível sempre:** os alertas e a hora do último boletim.
- **Para quem:** quem acompanha numa TV da sala.

## 14. "O que mudou" desde o boletim anterior — FEITO (rodada 33)

- **O quê:** diferença entre o boletim atual e o anterior:
  - quanto a apuração andou;
  - mudança de líder ou de leitura da projeção;
  - quem ganhou ou perdeu cadeira projetada;
  - quem entrou ou saiu da disputa.
- **Onde:** no boletim e no painel.

## 15. Bancadas 2026 × 2022 (após a apuração)

- **O quê:**
  - eleitos por partido e federação comparados com 2022: ganhos, perdas, reeleitos e novatos;
  - no mapa por local, a variação de voto de cada partido.

## 16. Conferência do tempo real com os microdados (após a apuração)

- **O quê:** quando os microdados de 2026 saírem, conferir se os totais gravados pelo coletor na noite batem com os oficiais, por município e cargo, e registrar as diferenças.

## 17. Novas camadas no mapa por local (após a apuração)

- **O quê:**
  - o destino dos eliminados no 2º turno, por local (sobre a rodada 30);
  - a variação 2022 → 2026 por local.

---

Registrado em 30/09/2026 (pedido do usuário: "Registre no TODO, o item 18 para o 2º turno"). Na noite de 4/10, só o RJ, que está ensaiado.

## 18. Várias UFs (para o 2º turno)

- **Já funciona trocando `--uf`:** coletor, site, boletim, alertas, cópia, vigia, cadeiras (validadas nas 27 UFs em 2022), mapas e Perfil × voto. Teste em 30/09: um ciclo do simulado do **Acre** baixou 116 arquivos em 11,5 s, com os 22 municípios.
- **Falta:**
  - pasta de dados com a UF por padrão (hoje `dados_2026/oficial` serve a uma UF só: duas se misturam);
  - **limite de acessos ao TSE dividido entre as UFs** (cada processo usa 20 req/s, e eles somam no mesmo IP): `--max-rps` no site ou um coletor para várias UFs com um limite só;
  - ensaio, prontidão e `validar_projecao.py` aceitando qualquer UF (hoje conferem só o RJ: Castro eleito, 46/70 cadeiras, arquivos `_RJ`);
  - calibração da margem de Governador/Senador e do erro das cadeiras por UF, com os microdados de 2022 dela (a margem do Presidente já foi medida nas 27 UFs);
  - portal agrupado por UF.
- **Hoje, para uma UF a mais:** `--dados dados_2026/oficial_<UF> --porta <outra>` e o limite de acessos dividido à mão.

## 19. Painel nacional do Presidente

- **O quê:** mapa do Brasil por UF na noite, com % apurado e vencedor em cada estado.
- **Custo de coleta:** 27 arquivos por ciclo (o resultado de cada UF), não os de todos os municípios do país.

## 20. Comparação entre UFs (após a apuração)

- **O quê:** abstenção, brancos/nulos e transferência de votos do 1º para o 2º turno lado a lado, entre UFs, sobre as análises que já existem (rodadas 19, 26 e 30).

---

Registrado em 04/10/2026 (pedido do usuário: "Registre no TODO a análise das parciais (analisar_coleta.py)").

## 21. Análise das parciais da noite (`analisar_coleta.py`)

- **Por quê:** a análise da noite de 4/10 ([RODADA_36](RODADA_36_2026-10-04_coleta_versao_anterior.md)) foi feita com scripts avulsos, num diretório temporário da sessão. Transformar em ferramenta permite refazê-la no 2º turno e comparar as noites.
- **Entrada:** `<dados>/raw/` e `raw_brasil/`, com todas as versões gravadas pelo coletor (ou o espelho da cópia de segurança). Sem rede.
- **Dados de cada versão:**
  - geração no TSE (`dg`/`hg`);
  - totalização anunciada (`dt`/`ht`) e % apurado;
  - chegada aqui (data de gravação do arquivo).
- **O que mede:**
  - **atraso da coleta:** chegada × geração, por tipo de arquivo (acompanhamento EA14/EA15, resultado EA20 da UF e dos municípios);
  - **anúncio × publicação:** para cada totalização municipal anunciada no EA15, quando chegou o EA20 gerado depois dela; quantas receberam primeiro a versão anterior; mediana, p95 e máximo. Em 4/10 foram 2.820 de 7.423 (38%);
  - **atraso do próprio TSE:** EA20 gerado depois do anúncio (mediana e p95), por janela de 30 min;
  - **pausas:**
    - do TSE: acompanhamento sem nova geração por mais de N min;
    - nossas: nenhuma versão gravada por mais de N min. Separar das do TSE e cruzar com o log do vigia e do site (reinícios, terminal fechado);
  - **validação do critério do coletor:** quantas versões anteriores ele reconhece e quantas corretas aceita de primeira (em 4/10, 1.634 de 1.667 e 85.077 de 86.011);
  - **peculiaridades:** `dt` do EA20 antes da hora anunciada (deputados) e hora no futuro no EA14 nacional;
  - **fim da noite:** % e hora da última totalização em disco × no TSE.
- **Saída:**
  - resumo no terminal;
  - planilha (`--saida x.xlsx`) com as versões, as totalizações e os indicadores;
  - linha do tempo opcional em PNG: % apurado no TSE × aqui.
- **Uso:** `python analisar_coleta.py --dados dados_2026/oficial [--log <log do vigia>] [--saida saidas/coleta_4_10.xlsx]`. Funções sem I/O em `apuracao/divulgacao/analise.py`, com testes sobre um `raw/` sintético.
- **Também no ensaio:** rodar sobre `dados_2026/ensaio_2022` e conferir que não há pausa nossa e que nenhuma versão anterior fica sem ser pedida de novo.

## 22. Quem migrou para quem de 2022 para 2026 (inferência ecológica por seção, após os microdados de 2026)

- **Por quê:** o gráfico de variação por partido da aba Comparação ([RODADA_38](RODADA_38_2026-10-05_variacao_partidos.md)) é uma leitura ecológica. Ele fala de municípios, não de pessoas, e não diz que "eleitores de Lula votaram em Flávio".
- **Ferramenta:** para estimar quem migrou para quem, o caminho certo é a inferência ecológica de `transferencia.py`, que hoje faz 1º → 2º turno.
- **Extensão:** levar o cálculo para 2022 → 2026 por seção quando os microdados de 2026 saírem.
- **Atenção ao casar as seções:** casar 2022 × 2026 pela seção (ou pelo local) com `locais.py`, por causa das seções remanejadas e dos locais novos e desativados.
- **Leitura:** com unidade município, a leitura é FRÁGIL (viés de agregação medido em 2022). Validar fora da amostra como na rodada 30.
