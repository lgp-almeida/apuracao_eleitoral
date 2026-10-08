# Rodada 70 — Cópia de segurança continua depois do "final" (08/10/2026)

Correção no `main`, para o 2º turno (25/10). Fecha o [TODO 28](TODO.md). O defeito foi achado no ensaio da
rodada 69, feito no ramo `frontend-refatoracao`; a correção vai também para esse ramo (`cherry-pick`), porque o
`apuracao/copia.py` é igual nos dois.

## Objetivo

Toda parcial que o TSE publica tem de entrar na cópia de segurança, inclusive as que chegam depois de todos os
cargos da UF terem totalização final.

## O defeito

- Em `apuracao/copia.py`, `Copiador.verificar()` devolvia `None` assim que o instantâneo `final` existia, ANTES do
  espelho de `raw/`. Daí em diante nada mais era copiado.
- O TSE publica depois do final: o EA20 regerado depois do anúncio no EA15 (rodada 36) e as retotalizações.
- No ensaio da rodada 69 (60×), a conferência "cópia final com todas as parciais do TSE" falhou duas vezes: 3.680 de
  3.682 e 3.686 de 3.688. As que faltaram eram os `rj-e0212{70,72}-ab` gerados às 00:23 de 2022, que chegaram 13 s
  depois do instantâneo `final`.

## Entregas

- **`Copiador.verificar()`** tem um só caminho para a hora e para o final:
  1. o instantâneo da vez (da hora ou `final`) ainda não existe → `copiar` (espelho + instantâneo), como antes;
  2. senão, a cada `espelho_min` (5 min), espelha `raw/` e `raw_brasil/`, **também depois do final**;
  3. se o espelho trouxe parcial nova e a situação é final, o instantâneo `final` é **refeito** (troca atômica, como
     sempre), com o `ultimo/` e as séries que chegaram junto. O `copias.json` registra cada refação.
- **`Copiador.encerrar()`:** a mesma verificação sem esperar os 5 min. O ensaio a chama no fim, em vez de
  `verificar()`: a 60×, os 5 min reais do espelho são a noite inteira, e a parcial tardia nunca seria espelhada a
  tempo da conferência.
- **Roteiro da noite:** no 2º turno, antes de desligar o site, esperar uns 10 min depois do final, ou fazer uma
  cópia à mão com `copiar_dados.py`. O laço do site roda numa thread daemon, que não faz uma última cópia ao sair.

## Arquivos

- `apuracao/copia.py`: `verificar` e `encerrar`.
- `ensaio_apuracao.py`: a última cópia do ensaio usa `encerrar()`.
- `test_copia_vigia.py`: 2 testes novos.
  - `test_parcial_depois_do_final_e_espelhada_e_refaz_o_final` falha no código antigo (`verificar()` devolvia
    `None`).
  - `test_espelho_respeita_o_intervalo_e_encerrar_nao_espera`.
- `docs/ROTEIRO_NOITE_DA_ELEICAO.md`, `docs/TODO.md`, `docs/INDEX.md`.

## Decisões

- **Refazer o final, sem criar um "final_2":** o final é o que se restaura. Quem restaura quer o estado mais novo,
  e o `raw/` guarda a história inteira.
- **Sem cópia ao sair:** uma thread daemon pode morrer antes de terminar uma cópia, e uma cópia pela metade seria
  pior que nenhuma (o instantâneo é atômico, mas o espelho não espera). O roteiro manda esperar ou copiar à mão.

## Verificação

- `pytest -q` no `main`: 481 passaram, os 2 novos incluídos, e 3 foram pulados (os golden do BU, que dependem
  de arquivos fora do cache).
- Ensaio geral `ensaio_apuracao.py --velocidade 60` no `main`: **OK** nas 19 conferências.
  - válidos dos cinco cargos, Castro e Romário eleitos, cadeiras 46/46 e 70/70;
  - alertas e boletim final;
  - **cópia final com todas as parciais do TSE: 3.681 de 3.681**, em 9 cópias (8 da hora e o final).
- **O limite desta verificação:** desta vez o instantâneo final saiu às 00:23 de 2022, quando as parciais tardias
  já tinham chegado. Nenhuma chegou depois dele, então o ensaio não passou pelo caminho novo, que depende de qual
  ciclo vê o "final" primeiro. Esse caminho fica provado pelo teste
  `test_parcial_depois_do_final_e_espelhada_e_refaz_o_final`, que falha no código antigo. O `encerrar()` no fim do
  ensaio garante a conferência quando a corrida acontecer.

## Pendências

- Merge do ramo `frontend-refatoracao` em `main` depois de 25/10 (TODO 27); o ramo recebe esta correção por
  `cherry-pick`.
