# Rodada 37 — Resultado do candidato por município × eleição anterior

05/10/2026 · pedido do usuário:
- "No menu/aba 'Candidato', crie mais uma planilha de histórico de resultados. A atual depende da publicação de
  microdados da eleição de 2026. Eu quero que a nova planilha mostre os resultados de 2026 e, se existirem, os
  resultados de 2022, quando o candidato for o mesmo, no nível de município. Mostre também a % de variação de
  um ano para o outro, permita o download."

## Objetivo

Ter, já durante e logo depois da apuração, o resultado do candidato por município ao lado do resultado de 2022.
A planilha de microdados (por local, zona, bairro e seção) só funciona para 2026 depois que o TSE publica os
microdados, dias após o pleito. A nova planilha usa os dados do coletor (`ultimo/`) e a referência que o site já
carrega (`--comparar-com`, padrão `dados_2026/historico_2022_t<turno>`).

## Como se identifica "o mesmo candidato"

Decisão do usuário: pelo **mesmo nome civil completo** (`NOME`, comparado com `eleitorado.compact`), em
**qualquer cargo**. O número e o cargo mudam muito de uma eleição para outra, e o CPF não vem na divulgação.

Medição nos dados de 4/10 (RJ, nível UF, todos os cargos):

| Situação | Candidatos |
|---|---|
| Nomes civis iguais em 2022 e 2026 | 463 |
| … com outro número | 339 |
| … com outro cargo | 127 |
| Nomes repetidos dentro do mesmo ano | 0 |

Regras de identificação:
- **Homônimos:** se houver vários em 2022, o do mesmo cargo desempata. Persistindo o empate, o critério é
  "ambíguo" e a página lista as opções ("usar este").
- **Indicação à mão:** `cargo_ref`/`numero_ref` (campos "Cargo/Número na eleição anterior") indicam o
  candidato de 2022. O cargo padrão é o mesmo.
- **Notas automáticas:** a página avisa quando o cargo mudou (ex.: Douglas Ruas, deputado estadual 22022 em
  2022 → governador 22 em 2026) e quando o cargo é senador (o nº de vagas muda).

## Entregas

- `comparacao.historico_candidato(atual, ref, uf, cargo, numero, cargo_ref, numero_ref)` (sem I/O) devolve
  `HistoricoCandidato`. A tabela tem a linha do estado e uma por município, com estas colunas:
  - `VOTOS_<ano>`, `PCT_VALIDOS_<ano>` e `POSICAO_<ano>` dos dois anos;
  - `PCT_SECOES_TOTALIZADAS`;
  - `VAR_VOTOS_PCT`: variação dos votos em %, nula se não houve voto no ano de referência;
  - `VAR_PCT_VALIDOS_PP`: variação do % dos válidos em p.p.

  Os nomes das colunas vêm dos anos das fontes (`sufixos`), nada fica fixo em 2022/2026. O arquivo do TSE é
  esparso: um município sem linha do candidato conta como 0 voto e 0%, sem posição.
- `comparacao.planilha_historico` gera o .xlsx em memória com as abas "Sobre" e "Por município". Usa
  `boletim._aba`, que ganhou os formatos `var` (+0,0%) e `pp` (+0,00 p.p.).
- Rotas novas, leves (fora de `ROTAS_PESADAS`):
  - `GET /api/candidato/historico`;
  - `GET /api/candidato/historico/planilha`, que salva como `historico_<nº>_<UF>_<ano>x<ref>.xlsx`.
- Aba Candidato: bloco "Resultado por município × eleição anterior". Mostra fichas, notas, uma tabela ordenável e
  o botão "Salvar planilha (.xlsx)". O bloco carrega ao abrir e a cada consulta. Ao trocar de candidato, a
  indicação manual é limpa. O endereço guarda `hist=1&hist_cargo=&hist_numero=`.

## Verificação

- Testes:
  - `test_comparacao.py`: +4 testes (casamento em outro cargo, município ausente = 0, variações, sem par,
    homônimos/ambíguo/indicado, planilha aberta com openpyxl e rotas);
  - `test_enderecos.py`: +2 e2e (endereço `hist=1`, link e download; nome com HTML como texto).
- `pytest -q`: 323 passaram, 4 pulados.
- Dados reais (`dados_2026/oficial` × `historico_2022_t1`), 92 municípios + UF:
  - Dr. Luizinho (dep. federal 1177): 213.904 votos contra 190.071 em 2022, +12,5%;
  - Douglas Ruas (governador 22) casou com o deputado estadual 22022 de 2022, com a nota de troca de cargo.

## Pendências

- Homônimos de pessoas diferentes com o mesmo nome civil completo não são detectados quando há um só em 2022.
  A ficha mostra cargo, número e partido de 2022 para conferência.
- Só há referência quando o site tem `--comparar-com` (ou o diretório padrão do 2022 importado).
