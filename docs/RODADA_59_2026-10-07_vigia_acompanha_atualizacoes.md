# Rodada 59 — Vigia que continua acompanhando o TSE depois dos totais oficiais

07/10/2026 · depois dos totais oficiais do 1º turno, o TSE regerou arquivos várias vezes no mesmo dia:
- `votacao_partido_munzona_2026` às 10h10, 12h39 e 16h39;
- `consulta_cand_2026` e `votacao_candidato_munzona_2026` à tarde.

Duas falhas obrigaram a reimportar à mão duas vezes.

## As duas falhas

1. **As vigias paravam nos oficiais.** `preparar_2026 --vigiar` encerra no `FINAL`; `baixar_ufs --vigiar`
   encerra quando nada está "aguardando".
2. **"Mudou" era da memória do download, não da importação.** Os munzona são **nacionais**, um ZIP para as 27
   UFs:
   - a 1ª UF a baixar a versão nova recebia `mudaram`;
   - as outras viam o arquivo "em dia" e não reimportavam;
   - o lote ainda pulava a etapa `microdados_2026` "ok".

## Como ficou

- **Insumos da importação** (`historico.importar`): o `status.json` ganha `insumos`, nome do ZIP → versão de cada
  arquivo do cache que a importação usa (`md.insumos_atuais`).
  - **Para os microdados:** o `Last-Modified` da proveniência, dos arquivos em `md.INSUMOS` = `PARA_IMPORTAR` +
    `partido_munzona`.
  - **Para o Boletim de Urna do turno:** o SHA-512.
- **Reimportar por insumo** (`preparar_2026.atualizar`): no mesmo nível, o turno é reimportado quando os
  `insumos` gravados diferem dos atuais. A comparação é feita pelo **disco**, então vale para o arquivo baixado por
  outra UF ou por outro processo.
  - **Importação antiga, sem o registro:** é refeita uma vez.
  - **Na reimportação do mesmo nível:** `conferir_totais(antes, depois)` vai para
    `saidas/<UF>/conferencia_atualizacao_<data>_<t>t.csv`, e o log diz "nenhum total mudou" ou quantas linhas
    mudaram.
- **`--acompanhar`** (`preparar_2026.py` e `baixar_ufs.py`): como `--vigiar`, mas não para nos oficiais.
  - Depois dos oficiais, verifica a cada `--intervalo-final` (padrão 3 h, mínimo 1 h).
  - Para com Ctrl+C ou `--ate AAAA-MM-DD`.
  - No lote, `Config.acompanhar` faz a etapa `microdados` rodar mesmo "ok". O detalhe passa a ser "reimportado: o
    TSE atualizou <arquivos> (<turno>)", e a situação continua "ok".
- **`--so-verificar`:** diz, por turno, se os arquivos da importação estão "em dia", "mudaram" (e quais) ou "sem
  registro".

## Verificação

- **Testes novos:**
  - `insumos_atuais` lido das proveniências (o perfil não entra);
  - reimporta quando um arquivo nacional muda sem `mudaram`; não reimporta sem mudança; refaz a importação sem
    registro;
  - `--acompanhar` não para no `FINAL`, usa o intervalo final de no mínimo 1 h, para em `--ate` e exclui
    `--vigiar`;
  - no lote, a UF "ok" é reimportada só quando o TSE regera, com o detalhe "reimportado";
  - o BU entra nos insumos da importação pelo BU.
- **Sem a implementação**, os 4 testes de `test_microdados.py`/`test_lote_ufs.py` falham.
- **Importações falsas dos testes** (`cli_falso`, lote e `test_bweb`): passaram a gravar `insumos`, como a
  importação real.
- `pytest -q -m "not e2e"`: 410 passados e 1 pulado.
- **Real:**
  - `--so-verificar` mostrou "sem registro (reimporta na próxima execução)";
  - as duas vigias foram ligadas com `--acompanhar` e refizeram a importação uma vez (RJ e 26 UFs), cada uma com
    "nenhum total mudou";
  - em seguida, "arquivos da importação: em dia" e próxima verificação em 180 min.

## Em execução

- `preparar_2026.py --acompanhar` (RJ): PID em `logs/acompanhar_RJ.pid`, log em `logs/acompanhar_RJ.log`.
- `baixar_ufs.py --etapas microdados --ufs <26 UFs> --acompanhar`: `logs/acompanhar_ufs.pid` e
  `logs/acompanhar_ufs.log`.
- Os dois processos subiram antes do ajuste do texto do log, que na 1ª reimportação ainda dizia "porque o TSE
  atualizou um arquivo". Ao reiniciá-los, a mensagem nova vale.

## Arquivos

- `apuracao/microdados.py` (`INSUMOS`, `insumos_atuais`) e `apuracao/historico.py` (`importar`: `insumos`).
- `preparar_2026.py` (`atualizar`, `importar`, `insumos_importados`, `--acompanhar`, `--intervalo-final`, `--ate`
  e o resumo).
- `apuracao/lote_ufs.py` (`Config.acompanhar`, `ja_feita` e o detalhe "reimportado") e `baixar_ufs.py`.
- Testes: `test_microdados.py`, `test_lote_ufs.py` e `test_bweb.py`.
- Docs: `docs/ROTEIRO_NOITE_DA_ELEICAO.md` ("Depois"), `CLAUDE.md` e `docs/INDEX.md`.
