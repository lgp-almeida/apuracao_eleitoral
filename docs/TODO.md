# TODO — propostas pendentes

Lista viva das propostas aceitas e ainda não feitas. Quando uma proposta for feita, marque-a como feita e aponte a rodada que a entregou (`docs/RODADA_NN_…`). Não apague a linha.

Registrado em 30/09/2026, a 4 dias do 1º turno (4/10/2026). A ordem segue a prioridade: primeiro o que serve na noite da apuração, depois o que depende dos microdados de 2026, publicados dias após o pleito.

**Plano de quitação (06/10/2026, aprovado pelo usuário):** um lote por rodada, nesta ordem.

| Lote | Rodada | Itens | Quando |
|---|---|---|---|
| 1 | 42 | 21 (análise das parciais), 23 (denominador do %), limpeza (3 e 19 fechados) | antes do 2º turno |
| 2 | 43 | 18: boletim/cópia/alertas no site de várias UFs, UF nova sem reiniciar, prontidão e ensaio do 2º turno por UF | antes do 2º turno |
| 3 | 44 | 18 (margem do 2º turno por UF) + 4b (recalibração com 2026) | antes do 2º turno |
| 4 | 45 | 16 (ferramenta de conferência) + 15 (bancadas 2026 × 2022) | depois |
| 5 | 46 | 22 (migração 2022 → 2026 por seção) + 17a (variação no mapa por local) | depois |
| 6 | 47 | 20 (comparação entre UFs) + 17b (destino dos eliminados) | depois dos microdados do 2º turno |

Fora dos lotes: 4 (importação final de 2026: depende do TSE; automática com `--vigiar`) e 24 (contínuo).

**Plano concluído em 06/10/2026 (rodadas 42–47).** Os lotes 5 e 6 ficaram prontos antes do 2º turno: o que depende
dele entra sozinho quando os dados existirem (ver as pendências da [RODADA_47](RODADA_47_2026-10-06_comparacao_ufs_e_eliminados.md)).

| # | Proposta | Quando serve | Situação |
|---|---|---|---|
| 1 | Distribuição de cadeiras de deputado em tempo real | noite de 4/10 | **feito**: [RODADA_20](RODADA_20_2026-09-30_cadeiras_de_deputado.md) |
| 2 | Projeção do resultado final durante a apuração | noite de 4/10 | **feito**: [RODADA_21](RODADA_21_2026-09-30_projecao_do_resultado.md) |
| 2b | Projeção das cadeiras de deputado (consolidados × em disputa) | noite de 4/10 | **feito**: [RODADA_22](RODADA_22_2026-09-30_projecao_de_cadeiras.md) (pedido do usuário em 30/09) |
| 3 | Ensaio geral e roteiro de prontidão | 3/10 e 4/10 | **feito**: [RODADA_23](RODADA_23_2026-09-30_ensaio_geral.md) e [roteiro](ROTEIRO_NOITE_DA_ELEICAO.md); a checagem do oficial foi cumprida na noite de 4/10, que rodou no oficial (fechado na rodada 42) |
| 4 | Preparar os dados de 2026 assim que o TSE publicar | dias após o pleito | **feito**: [RODADA_24](RODADA_24_2026-09-30_microdados_2026.md); gatilho de importação corrigido e totais provisórios das seções na [RODADA_40](RODADA_40_2026-10-06_totais_sem_munzona.md). RJ importado em 06/10 (provisório); falta o detalhe munzona do TSE |
| 4b | Recalibrar margem da projeção e σ das cadeiras com 2026 | quando saírem os microdados de 2026 | **feito**: [RODADA_44](RODADA_44_2026-10-06_margens_por_turno.md) (margem do 1º turno com 2022 + 2026, margem própria do 2º turno; σ validado em 2026 e mantido). Refazer com o 2º turno de 2026 depois de 25/10 |
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
| 15 | Bancadas 2026 × 2022 (eleitos por partido/federação, reeleitos, novatos; variação por local) | após a apuração | **feito**: [RODADA_45](RODADA_45_2026-10-06_conferencia_e_bancadas.md) (bancadas, reeleitos, novatos) e [RODADA_46](RODADA_46_2026-10-06_migracao_2022_2026.md) (variação por local) |
| 16 | Conferência automática do tempo real com os microdados de 2026 | após a apuração | **feito**: [RODADA_45](RODADA_45_2026-10-06_conferencia_e_bancadas.md) (`conferir_resultado.py`; roda sozinho após cada importação) |
| 17 | Novas camadas no mapa por local (destino dos eliminados no 2º turno; variação 2022 → 2026) | após a apuração | **feito**: 17a na [RODADA_46](RODADA_46_2026-10-06_migracao_2022_2026.md) (camada "Variação desde a eleição anterior"); 17b na [RODADA_47](RODADA_47_2026-10-06_comparacao_ufs_e_eliminados.md) (camada "Destino dos eliminados"; com 2022 agora, 2026 quando saírem os microdados do 2º turno) |
| 18 | Várias UFs: pasta de dados por UF, limite de acessos ao TSE dividido entre UFs, ensaio/prontidão/calibração por UF, portal por UF | 2º turno, 25/10 | **feito**: [RODADA_39](RODADA_39_2026-10-05_todas_as_ufs.md), [RODADA_43](RODADA_43_2026-10-06_segundo_turno_varias_ufs.md) e [RODADA_44](RODADA_44_2026-10-06_margens_por_turno.md) (margem por turno; Governador/Senador medidos nas UFs com votos por seção no cache — RJ e ES) |
| 19 | Painel nacional do Presidente (mapa do Brasil por UF, % apurado e vencedor em cada estado) | a definir | **feito**: [RODADA_35](RODADA_35_2026-10-01_presidente_por_uf.md) (bloco "Por estado" do cartão Brasil: mapa, quem lidera, % apurado e hint com todos os candidatos; fechado na rodada 42) |
| 20 | Comparação entre UFs (abstenção, brancos/nulos, transferência 1º → 2º turno) | após a apuração | **feito**: [RODADA_47](RODADA_47_2026-10-06_comparacao_ufs_e_eliminados.md) (`comparar_ufs.py`; o 2º turno de 2026 entra sozinho com as pastas `oficial_t2_<UF>`) |
| 21 | Análise das parciais da noite (`analisar_coleta.py`): TSE × coletor, atrasos, versões anteriores, pausas | antes do 2º turno, 25/10 | **feito**: [RODADA_42](RODADA_42_2026-10-06_analise_coleta_e_percentuais.md) |
| 22 | Quem migrou para quem de 2022 para 2026 (inferência ecológica por seção) | após os microdados de 2026 | **feito**: [RODADA_46](RODADA_46_2026-10-06_migracao_2022_2026.md) (`migracao_votos.py`, por local; fora da amostra 0,83 p.p. × swing 1,14 no Presidente RJ) |
| 23 | Mesmo denominador do "% dos válidos" no tempo real e no histórico (o TSE divulga sobre válidos + sub judice) | antes de comparar 2026 × 2022 com sub judice | **feito**: [RODADA_42](RODADA_42_2026-10-06_analise_coleta_e_percentuais.md) (comparações sobre os válidos oficiais; o painel mantém o % do TSE) |
| 24 | Manter `apuracao/partidos.py` (`EVENTOS`/`NOVOS`) a cada partido novo, fusão ou renomeação; conferir as datas para comparar com eleições municipais | a cada cadastro novo do TSE | contínuo — o teste com os cadastros reais acusa |
| 25 | Mapa por área de ponderação (aba Mapas): malha das áreas pela fusão dos setores, camadas de voto e de perfil (religião e amostra do Censo) | a definir | **feito**: [RODADA_50](RODADA_50_2026-10-06_mapa_areas_ponderacao.md) (Detalhe "Áreas de ponderação", camadas voto e perfil) |
| 26 | Prontidão do 2º turno: `verificar_prontidao.py --turno 2 --ufs todas --testes`, ensaio do 2º turno numa UF com 2º turno, códigos oficiais do `ele-c.json` e revisão do roteiro para várias UFs | antes de 25/10 (prontidão até ~20/10; códigos quando o TSE publicar) | **prontidão feita em 07/10**: 0 falhas; 2º turno de Governador em AC, AM, DF, ES, RJ, RN e TO; códigos oficiais 6260 (Gov.) e 6258 (Pres.) já no `ele-c.json`; acompanhamento ainda 404 (normal antes de 25/10). Checagem do relógio passou a usar o oficial (o simulado saiu do ar). Ensaio do 2º turno (ES) OK em 07/10, depois de corrigir o TSE simulado do ensaio (o EA20 era carimbado com a hora exata e mostrava o minuto cheio: o coletor aceitava a versão anterior como final e 11 abrangências ficavam em 99,99%). Roteiro do 2º turno atualizado em 07/10 (`docs/ROTEIRO_NOITE_DA_ELEICAO.md`). **Feito** |
| 27 | Fallback dos totais pelo Boletim de Urna (3º nível, por turno) e votacao_partido_munzona reconstruído para as cadeiras | 2º turno (BU sai dias antes dos microdados) | **feito**: [RODADA_55](RODADA_55_2026-10-07_fallback_bweb_e_partidos.md) (golden RJ 2022 com 0 diferença; pedido em [PROMPT_fallback_bweb_munzona.md](PROMPT_fallback_bweb_munzona.md)) |
| 28 | Abstenção × mudança de local de votação 2022 → 2026 (planilha; impacto em Presidente e Governador) | urgente (07/10) | **feito** (27 UFs + consolidado): [RODADA_56](RODADA_56_2026-10-07_abstencao_mudanca_local.md); falta o 2º turno |
| 28b | Cópia de segurança para de espelhar `raw/` depois do instantâneo "final" (seção 28 abaixo) | antes do 2º turno, 25/10 | **feito**: [RODADA_70](RODADA_70_2026-10-08_copia_depois_do_final.md) |

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

## 15. Bancadas 2026 × 2022 (após a apuração) — FEITO (rodada 45)

- **O quê:**
  - eleitos por partido e federação comparados com 2022: ganhos, perdas, reeleitos e novatos;
  - no mapa por local, a variação de voto de cada partido.

## 16. Conferência do tempo real com os microdados (após a apuração) — FEITO (rodada 45)

- **O quê:** quando os microdados de 2026 saírem, conferir se os totais gravados pelo coletor na noite batem com os oficiais, por município e cargo, e registrar as diferenças.
- **Feito à mão na [RODADA_40](RODADA_40_2026-10-06_totais_sem_munzona.md), RJ, com os totais reconstruídos das seções:**
  - Governador, Senador e Deputados idênticos em totais, votos, situação e destinação;
  - cadeiras 46/46 e 70/70;
  - Presidente +387 válidos (destinação ainda não publicada).
- **Falta:**
  - a ferramenta (relatório por UF/cargo/município em `saidas/`);
  - repetir com os totais oficiais quando o detalhe munzona sair (`preparar_2026` já grava a conferência
    reconstruído × oficial).

## 17. Novas camadas no mapa por local (após a apuração) — FEITO (rodadas 46 e 47)

- **O quê:**
  - **17b, feito ([RODADA_47](RODADA_47_2026-10-06_comparacao_ufs_e_eliminados.md)):** o destino dos eliminados no
    2º turno, por local (sobre a rodada 30). Funciona com 2022; com 2026 quando os microdados do 2º turno saírem;
  - **17a, feito ([RODADA_46](RODADA_46_2026-10-06_migracao_2022_2026.md)):** a variação 2022 → 2026 por local
    (partido pela entidade, abstenção, comparecimento, brancos/nulos).

---

Registrado em 30/09/2026 (pedido do usuário: "Registre no TODO, o item 18 para o 2º turno"). Na noite de 4/10, só o RJ, que está ensaiado.

## 18. Várias UFs (para o 2º turno) — FEITO (rodadas 39, 43 e 44)

- **Feito na [RODADA_39](RODADA_39_2026-10-05_todas_as_ufs.md):**
  - pasta de dados com a UF (`ufs.dir_uf`; as pastas antigas, sem sufixo, continuam valendo para o RJ);
  - limite de acessos ao TSE dividido entre as UFs: `baixar_ufs.py` e `site_apuracao.py --ufs --coletar`
    usam UM limitador para todas;
  - um site com seletor de UF (`site_apuracao.py --ufs`), em vez do portal agrupado;
  - histórico de qualquer UF pela fonte munzona, sem baixar o votacao_secao de cada uma.
- **Feito na [RODADA_43](RODADA_43_2026-10-06_segundo_turno_varias_ufs.md):**
  - boletim, cópia de segurança e alertas de cada UF no site de várias UFs;
  - o site sobe sem nenhuma UF com dados e monta a que ganhar dados, sem reiniciar;
  - prontidão do 2º turno por UF (`verificar_prontidao.py --turno 2 --ufs todas`);
  - ensaio de qualquer UF e do 2º turno (`ensaio_apuracao.py --uf ES --turno 2`: OK).
- **Feito na [RODADA_44](RODADA_44_2026-10-06_margens_por_turno.md):**
  - `validar_projecao.py` por turno e por cargo;
  - Governador e Senador em toda UF com `votacao_secao` no cache;
  - margem própria do 2º turno.
- **Não feito, de propósito:** baixar o `votacao_secao_2022` das 27 UFs só para calibrar Governador por UF (vários GB). O Presidente nas 27 UFs e o Governador em RJ e ES já dão a margem; uma UF pode ser incluída a qualquer momento, baixando o arquivo dela.

## 19. Painel nacional do Presidente — FEITO (rodada 35)

- **O quê:** mapa do Brasil por UF na noite, com % apurado e vencedor em cada estado.
- **Custo de coleta:** 27 arquivos por ciclo (o resultado de cada UF), não os de todos os municípios do país.

## 20. Comparação entre UFs (após a apuração) — FEITO (rodada 47)

- **Feito na [RODADA_47](RODADA_47_2026-10-06_comparacao_ufs_e_eliminados.md):** `comparar_ufs.py` (núcleo
  `apuracao/entre_ufs.py`). Depois de 25/10, rodar de novo: o 2º turno de 2026 entra sozinho.

- **O quê:** abstenção, brancos/nulos e transferência de votos do 1º para o 2º turno lado a lado, entre UFs, sobre as análises que já existem (rodadas 19, 26 e 30).

---

Registrado em 04/10/2026 (pedido do usuário: "Registre no TODO a análise das parciais (analisar_coleta.py)").

## 21. Análise das parciais da noite (`analisar_coleta.py`) — FEITO (rodada 42)

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

## 22. Quem migrou para quem de 2022 para 2026 (inferência ecológica por seção, após os microdados de 2026) — FEITO (rodada 46)

- **Feito na [RODADA_46](RODADA_46_2026-10-06_migracao_2022_2026.md):** `migracao_votos.py` (núcleo `apuracao/migracao.py`),
  unidade = local presente nos dois anos (a seção é renumerada entre anos), Presidente e Governador. Senador fica de
  fora (1 vaga em 2022, 2 em 2026).

- **Por quê:** o gráfico de variação por partido da aba Comparação ([RODADA_38](RODADA_38_2026-10-05_variacao_partidos.md)) é uma leitura ecológica. Ele fala de municípios, não de pessoas, e não diz que "eleitores de Lula votaram em Flávio".
- **Ferramenta:** para estimar quem migrou para quem, o caminho certo é a inferência ecológica de `transferencia.py`, que hoje faz 1º → 2º turno.
- **Extensão:** levar o cálculo para 2022 → 2026 por seção quando os microdados de 2026 saírem.
- **Atenção ao casar as seções:** casar 2022 × 2026 pela seção (ou pelo local) com `locais.py`, por causa das seções remanejadas e dos locais novos e desativados.
- **Leitura:** com unidade município, a leitura é FRÁGIL (viés de agregação medido em 2022). Validar fora da amostra como na rodada 30.

---

Registrado em 06/10/2026 (rodada 40).

## 23. Mesmo denominador do "% dos válidos" no tempo real e no histórico — FEITO (rodada 42)

- **Achado:** a divulgação em tempo real (JSON do TSE, gravado pelo coletor) dá o percentual do candidato sobre
  **válidos + anulados sub judice**. A conferência da [RODADA_40](RODADA_40_2026-10-06_totais_sem_munzona.md) deu
  diferença < 10⁻⁹ em todos os cargos. O histórico importado dos microdados usa os **válidos oficiais**.
- **Efeito:**
  - o mesmo candidato tem % diferente conforme a fonte quando há candidatura sub judice no cargo: até 10,8 p.p. num
    município, para Governador RJ 2026, com 274 mil votos sub judice;
  - a Comparação 2022 × 2026, as variações (rodadas 37 e 38) e a planilha do candidato misturam as duas
    convenções.
- **O quê:**
  - escolher uma convenção para o site (sugestão: a oficial, válidos) e aplicar às duas fontes;
  - ou mostrar as duas, com o rótulo de qual é qual.

## 24. Manter a tabela de partidos entre eleições

- **Contexto:** [RODADA_41](RODADA_41_2026-10-06_partidos_entre_eleicoes.md).
- **Quando:** `test_partidos.py::test_tabela_explica_os_cadastros_reais` falha ao chegar um cadastro novo (partido
  novo, fusão, incorporação ou renomeação). Registre o evento em `EVENTOS` (ou em `NOVOS`) com a fonte.
- **Eleições municipais:** a tabela usa a 1ª eleição GERAL em que cada mudança vale. Para comparar com 2020/2024,
  confirmar as datas de PMN → MOBILIZA, PMB → DEMOCRATA e PC do B → PCDOB.

## 25. Mapa por área de ponderação — FEITO (rodada 50)

- **Contexto:** [RODADA_49](RODADA_49_2026-10-06_censo_amostra_e_universo.md). A área de ponderação já é unidade do
  Perfil × voto, a única com religião e os demais resultados da amostra do Censo 2022. O usuário pediu o mapa para
  depois.
- **O quê:**
  - **Malha:** a fusão (`dissolve`) dos setores da malha do IBGE pela composição (`ap_composicao.parquet`), com cache
    `cache_tse/malhas/areas_ponderacao_<UF>.geojson` gerado pelo `ibge.py` (um derivado a mais da malha de
    setores).
  - **Na aba Mapas:** um Detalhe "Áreas de ponderação", com camadas de voto (as métricas do mapa por bairro sobre
    `PerfilVotoArea._vb`) e de perfil (os indicadores da área, inclusive a religião).
  - **Exportação** PNG/SVG e os testes e2e (cores, dica, endereço `detalhe=areas`).
- **Cuidado:** são poucas áreas por município pequeno (uma área = a cidade inteira). Avisar na legenda que os
  valores da amostra têm erro amostral (o IBGE publica os coeficientes de variação por área).

---

Registrado em 07/10/2026 (pedido do usuário: "Coloque no TODO a prontidão do 2º turno").

## 26. Prontidão do 2º turno (25/10/2026)

- **Contexto:** as ferramentas para o 2º turno em várias UFs estão prontas desde a
  [RODADA_43](RODADA_43_2026-10-06_segundo_turno_varias_ufs.md) (pastas `<ambiente>_t2_<UF>`, prontidão e ensaio
  por UF) e a [RODADA_44](RODADA_44_2026-10-06_margens_por_turno.md) (margem própria do 2º turno), mas ainda não
  foram rodadas contra o resultado real do 1º turno de 2026.
- **O quê:**
  - **Prontidão:** `python verificar_prontidao.py --turno 2 --ufs todas --testes`. As UFs com 2º turno de
    Governador vêm do resultado do 1º turno, e o acompanhamento é só delas. Corrigir o que faltar: cache, pastas,
    porta, dependências.
  - **Ensaio:** `python ensaio_apuracao.py --uf <UF> --turno 2` numa ou duas UFs que terão 2º turno (o RJ, se
    tiver), com o site aberto e consultas simultâneas. Conferir o fim com o oficial.
  - **Códigos oficiais:** quando o TSE publicar o `ele-c.json` do 2º turno, rodar
    `coletar_resultados.py --ambiente oficial --uma-vez`, com `--uf` nas UFs com 2º turno, e confirmar que o
    coletor acha Governador e Presidente no ciclo certo.
  - **Roteiro:** atualizar o [ROTEIRO_NOITE_DA_ELEICAO.md](ROTEIRO_NOITE_DA_ELEICAO.md) para o 2º turno em várias
    UFs: `site_apuracao.py --ufs ... --coletar` sob o `vigiar_site.py`, cópia em outro disco e boletim e alertas
    por UF.
- **Junto, opcional:** retomar o download dos microdados de onde parou (pendência da
  [RODADA_54](RODADA_54_2026-10-07_cdn_versao_antiga.md)). A CDN fecha conexões no meio de arquivos de ~290 MB.
- **Depois de 25/10 (já previsto em outros itens):** item 4b (refazer a margem do 2º turno com 2026) e o 2º turno
  de 2026 nos itens 17b e 20, quando saírem os microdados.

---

Registrado em 07/10/2026 (pedido do usuário: planejar a refatoração do front-end, só a proposta).

## 27. Refatoração do front-end (Vite + TypeScript + design system)

- **Proposta completa:** [PROPOSTA_REFATORACAO_FRONTEND.md](PROPOSTA_REFATORACAO_FRONTEND.md). Traz o diagnóstico com
  números, a arquitetura por módulos, o design system, a robustez, as fases e os riscos.
- **O quê:** tirar o `app.js` de 3.117 linhas do arquivo único. O código vai para `apuracao/web/frontend/src/` (TypeScript
  strict, Vite) e o build é versionado em `apuracao/web/static/`. Uma aba = uma pasta; o roteador fica numa tabela única;
  todo pedido tem cancelamento e tempo-limite. O design system traz tokens, `@layer`, Public Sans e a régua de apuração,
  sem mudar as cores da dataviz nem as dos mapas.
- **Como:** 7 fases no padrão estrangulador: andaime → núcleo → roteador → componentes → abas (transferência →
  perfil → comparação → candidato → mapas → painel) → design system → limpeza. Cada fase passa nos 64 e2e sem
  mudar asserções, no Vitest, no `tsc --strict` e no ensaio geral.
- **Quando:** num ramo (`frontend-refatoracao`), que só entra em `main` **depois do 2º turno (25/10/2026)**. Até lá,
  as correções do front-end vão para o `app.js` atual.

## 28. Cópia de segurança para de espelhar `raw/` depois do instantâneo "final" — FEITO (rodada 70)

Registrado em 08/10/2026, achado no ensaio da rodada 69 (ramo `frontend-refatoracao`). **Feito na
[RODADA_70](RODADA_70_2026-10-08_copia_depois_do_final.md)**, no `main` e no ramo.

- **O defeito:** em `apuracao/copia.py`, `Copiador.verificar()` devolvia `None` quando o instantâneo `final` já
  existia, antes do espelho de `raw/` a cada `espelho_min`. Toda parcial que chegasse depois do "final" nunca era
  copiada. Exemplos: o EA20 regerado depois do anúncio no EA15 (rodada 36) e uma retotalização.
- **Como apareceu:** o ensaio a 60× falhou em "cópia final com todas as parciais do TSE" com 3.680 de 3.682. As duas
  que faltaram eram os `rj-e0212{70,72}-ab` gerados às 00:23, que chegaram 13 s depois do instantâneo `final`.
- **Correção:** com o `final` feito, o espelho de `raw/` continua no intervalo de sempre, e o `final` é refeito
  quando chega parcial nova. `encerrar()` faz a verificação sem esperar o intervalo; o ensaio a usa no fim.
