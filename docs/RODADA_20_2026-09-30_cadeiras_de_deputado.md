# Rodada 20 — Cadeiras de deputado em tempo real, validadas contra 2022

30/09/2026 · pedido do usuário: "Faça a 1, validando contra 2022, mas antes registre estas cinco propostas em um documento, tipo TODO."

## Entregas

- **`docs/TODO.md`:** as 5 propostas aceitas, com prioridade, justificativa e como validar. Registrado no INDEX; o item 1 aponta esta rodada.
- **`apuracao/cadeiras.py`**, domínio puro:
  - `quociente_eleitoral`, com aritmética inteira;
  - `distribuir`, que faz o QP, a exigência de 10% do QE por candidato e as sobras em 2 fases, e registra o passo a passo das sobras;
  - `entrada_divulgacao`, que lê o tempo real (`ultimo/` do coletor);
  - `entrada_munzona`, que lê os microdados oficiais;
  - `comparar_com_oficial`.
- **API:**
  - `GET /api/cadeiras?cargo=6|7|8` traz QE, limites, cadeiras por agremiação (QP + média), eleitos com folga, o passo a passo das sobras, a conferência com o que o TSE já declarou e a salvaguarda de consistência;
  - o cartão de Dep. Federal e Dep. Estadual no `/api/painel` ganha o resumo `cadeiras`;
  - o `/api/candidato` ganha `cadeira`: situação projetada, ordem na lista e margem.
- **Painel:** bloco "Cadeiras projetadas — N vagas" nos cartões de deputado, com:
  - uma barra por agremiação, com as vagas por quociente partidário (QP) e as por sobras, cada uma com sua cor e legenda;
  - a linha "QE · QP + média · projeção com X% das seções" ou "resultado final";
  - "confere com o TSE: N de N eleitos";
  - "Ver os N eleitos projetados", carregado ao abrir.
- **Aba Candidato:** ficha "Projeção de cadeira". Para eleitos: "Eleito por QP · 139.634 votos à frente do 1º suplente de PL". Para suplentes: "Suplente (18º de PL) · faltam 1.112 votos para passar o último eleito da agremiação".
- **Fonte dos dados:**
  - no tempo real, o JSON do TSE; a soma dos partidos é igual aos válidos, conferido no simulado;
  - em eleição passada importada (`status.json` com `ano`), os microdados oficiais, `votacao_partido_munzona` + `votacao_candidato_munzona`, lidos uma vez e guardados em memória;
  - o `ultimo/` histórico não serve para isso: seus votos por partido saem do cadastro de candidatos, que reflete decisões posteriores, e dão 8.532.118 contra 8.395.113 válidos oficiais.

## Regra implementada

Código Eleitoral, arts. 106–109; Res. 23.677/2021, art. 12-A, na redação da Res. 23.748/2026 (ver `Anexo I`, bloco A4).

1. **QE** = válidos ÷ vagas. A fração ≤ 0,5 é desprezada e a > 0,5 arredonda para cima.
2. **QP** = votos da agremiação ÷ QE, sem a fração. Federação conta como um só partido. As vagas do QP vão aos mais votados com ≥ 10% do QE; a vaga do QP sem candidato assim vai para as sobras.
3. **Sobras, fase 1:** maior média entre as agremiações com ≥ 80% do QE que tenham candidato com ≥ 20% do QE.
4. **Sobras, fase 2:** maior média entre **todas** as agremiações, sem votação mínima (regra do STF, positivada para 2026).
5. **Desempates:**
   - média igual: vence a agremiação mais votada;
   - voto igual: vence o mais idoso (art. 110). O JSON não traz a idade, mas traz a ordem do TSE (`seq`), que já embute o desempate.

## Validação

1. **2022, todas as UFs:** 1.572 vagas de deputado federal, estadual e distrital nas 27 UFs, com **0 divergências**, inclusive na classificação QP × média.
   - Microdados usados: regerados pelo TSE em 30/09/2026, já com o recálculo do STF.
   - Tempo: cerca de 1,5 min.
2. **RJ:**

   | Cargo | QE | Por QP | Por média | Divergências |
   |---|---|---|---|---|
   | Dep. Federal | 186.435 | 36 | 10 | 0 |
   | Dep. Estadual | 119.930 | 58 | 12 | 0 |

   - Os QE batem com os oficiais.
   - Fica como teste de regressão com dados reais, que roda quando os ZIPs estão no cache.
3. **Fase 2 exercitada:** no RJ todas as sobras saem na fase 1. Em AP, DF, RO e TO, 9 vagas saem na fase 2, e todas conferem.
   - Restringir a fase 2 às agremiações com 80% do QE (texto original da Lei 14.211) troca 8 eleitos nessas UFs.
   - Os 7 que entram na fase 2 são exatamente os que ganharam o mandato no recálculo do STF de 2025.
4. **Simulado do TSE (dados completos coletados):** 50 + 80 eleitos, com **0 divergências** de eleito × não eleito e as vagas por agremiação iguais às do TSE.
   - No simulado nenhum candidato alcança 10% do QE, e por isso o TSE marca todos "por média"; o cálculo dá o mesmo.
   - Dois empates exatos de votos só bateram depois de usar o `seq` do TSE como desempate.

## Achados e decisões

- **Erro no documento de referência corrigido:** o documento de normas dizia que 7 deputados foram "substituídos por" Goreth, Silvia Waiãpi, Sonize Barbosa, Dr. Pupio, Gilvan Máximo, Lebrão e Lázaro Botelho. É o contrário: esses **perderam** o mandato. Os microdados oficiais marcam todos como SUPLENTE ou NÃO ELEITO. O documento ganhou uma nota [CORRIGIDO] com os 7 que entraram.
- **Variante "80/20" descartada:** foi implementada e depois removida. O resultado original de 2022 não está mais nos microdados (Silvia Waiãpi e Sonize Barbosa hoje têm votos anulados), então não havia como validá-la, e código não validado podia enganar.
- **Salvaguarda de consistência:** a API informa `soma_agremiacoes` e `consistente`, e o painel avisa quando os votos das agremiações não somam os válidos. O recorte do simulado usado nos testes é truncado (4 agremiações), e o aviso aparece ali, como deve.
- **Projeção parcial:** durante a apuração, a distribuição é "a que sairia se a apuração parasse agora". O painel mostra o % de seções e diz "muda até o fim da apuração".
- **Margem do suplente:** é o que falta para passar o último eleito da própria agremiação, **mantido** o número de cadeiras dela. Votos a mais também podem mudar as cadeiras da agremiação, e isso não entra nesse número.

## Verificação

- **`pytest -q`: 141 testes passando** (eram 125).
- **`test_cadeiras.py`**, 14 testes:
  - QE, com os exemplos oficiais e as frações 0,5 e 0,67;
  - um cenário calculado à mão com QP e 10%, empate de médias, empate de votos com desempate, fases 1 e 2, sub judice e margens;
  - vaga sem candidato apto;
  - desempate pelo número;
  - entradas da divulgação (federação, sub judice, `seq`) e dos microdados (zonas somadas, eleição suplementar descartada, anulado);
  - API no tempo real e no histórico;
  - regressão com os dados reais do RJ.
- **`test_cadeiras_e2e.py`**, 2 testes: o bloco no painel, com o aviso de consistência e os eleitos sob demanda, e a ficha na aba Candidato.
- **Sabotagens** no `cadeiras.py` (restaurado byte a byte):
  - sem a fase 2: 2 falhas;
  - sem a exigência de 10%: 1 falha;
  - sem o desempate: 1 falha.
- **Conferência visual (porta 8022, 2022):**
  - o cartão mostra "QE 119.930 · 58 por QP + 12 por média · resultado final · confere com o TSE: 70 de 70 eleitos";
  - na aba Candidato, Douglas Ruas aparece eleito por QP e Renan Jordy como suplente, faltando 1.112 votos;
  - a tabela de eleitos cabe no cartão.
- **Servidores** reiniciados nas portas 8000, 8022 e 8023, com os logs agora em `logs/`.

## Arquivos

- **Novos:** `apuracao/cadeiras.py`, `test_cadeiras.py`, `test_cadeiras_e2e.py`, `docs/TODO.md`.
- **Alterados:**
  - `apuracao/web/app.py` e `apuracao/web/static/{app.js,style.css}`;
  - `docs/Eleicoes_TSE_2022_vs_2026_Normas_Quocientes_Acesso_Programatico_Dados.md` (correção), `CLAUDE.md` e `docs/INDEX.md`.
- **Cache:** `cache_tse/votacao_partido_munzona_2022.zip` (25 MB) e `votacao_candidato_munzona_2022.zip` (578 MB).

## Pendências

- **Validação com dados oficiais de 2026:** vale conferir o `ele-c.json` oficial em 3/10 (item 3 do TODO) e, na noite de 4/10, acompanhar o "confere com o TSE" à medida que o TSE declarar os eleitos.
- **Idade no desempate dos microdados:** não é usada (`entrada_munzona`); em 2022 nenhum empate decidiu vaga. Dá para trazê-la do `consulta_cand` se for preciso.
- **Próximo item do TODO:** (2) projeção do resultado final durante a apuração.
