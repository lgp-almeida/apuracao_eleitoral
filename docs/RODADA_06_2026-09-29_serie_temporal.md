# Rodada 06 — Série temporal da apuração no painel

29/09/2026 · pedido do usuário após a [rodada 05](RODADA_05_2026-09-29_comparacao_2022_2026.md)

## Objetivo

Mostrar, em cada cartão do painel, como os mais votados evoluem ao longo da apuração.

## O que foi feito

- **`apuracao/divulgacao/serie.py`:**
  - `linhas()`: a cada totalização nova de uma abrangência **UF ou Brasil**, uma linha por **candidato** (cargos majoritários) ou por **partido** (proporcionais, porque são milhares de candidatos), com a hora da totalização, o % de seções totalizadas, os votos e o % dos válidos;
  - `acrescentar()`: grava `historico_serie.parquet` sem duplicar pontos;
  - `reconstruir()`: refaz a série a partir de todas as versões dos EA20 de UF/BR guardadas em `raw/`. O coletor chama essa função sozinho quando a série ainda não existe, então o que foi coletado antes desta rodada não se perde;
  - `para_grafico()`: pontos e as 3 séries com mais votos na última totalização.
- **Coletor:** acrescenta a série junto com `historico_totais` sempre que há arquivos novos.
- **API:** cada cartão de `/api/painel` traz `serie` (pontos e séries).
- **Painel:** gráfico SVG próprio, sem biblioteca.
  - **Eixos:** x = % de seções totalizadas (0–100%), y = % dos válidos.
  - **Marcas** (regras da skill dataviz): linhas de 2 px nas 3 primeiras cores categóricas, ponto final de 8 px, rótulo direto do valor na ponta com afastamento anticolisão, legenda com número, nome e partido, grade recessiva.
  - **Passagem do mouse:** linha-guia vertical e dica com hora, % de seções e o valor de cada série.
  - **Menos de 2 totalizações:** o cartão diz "A série aparece a partir da 2ª totalização".

## Achado e correção no coletor

Os JSON brutos eram gravados com nome `<geração dg/hg>_<idg>`. Se uma versão nova de um arquivo chegasse com o mesmo carimbo, ela **não era gravada**, porque o arquivo já existia, e o histórico bruto perdia versões. O teste de reconstrução revelou o problema. Agora o nome inclui um hash do conteúdo, `<AAAAMMDD_HHMMSS>_<idg>_<sha1[:10]>.json.gz`, e toda versão distinta é guardada. As coletas já existentes continuam legíveis, porque a reconstrução só olha o diretório de cada arquivo.

## Verificação

- `pytest -q`: **49 testes passando** (3 novos em `test_serie.py`). O `FakeTSE.avancar_uf` simula novas totalizações da UF (hora, % de seções, votos). Os testes cobrem:
  - 3 pontos gravados;
  - partidos nos cargos proporcionais;
  - nada municipal na série;
  - ordem por hora;
  - reconstrução idêntica à série gravada;
  - série no `/api/painel`.
- **Visual:** apuração de demonstração com 6 totalizações (TSE falso), conferida em captura do Chrome.
- **Dados reais:** a série do simulado foi reconstruída a partir dos brutos, mas tem **1 ponto por cargo**. O simulado terminou às 16h de 29/09, com 100% das seções, e o painel mostra o aviso. Os dados de 2022 (microdados) também têm um único ponto, o final.

## Pendências

- Na noite de 4/10, a série se forma a cada totalização coletada (intervalo de 60 s).
- Não há série no nível de município. A série é gravada só para UF/BR; o JSON bruto municipal fica guardado e permitiria reconstruí-la se for necessário.
