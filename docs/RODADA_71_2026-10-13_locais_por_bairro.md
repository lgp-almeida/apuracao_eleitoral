# Rodada 71 — Locais de votação e seções de um bairro (13/10/2026)

Script de linha de comando novo, no ramo `frontend-refatoracao` (commit `113ee42`) e no `main` por `cherry-pick`
(commit `e683a1c`). Não mexe no site, no coletor nem no front-end.

## Objetivo

Dado o nome de um bairro, listar os locais de votação dele e as seções eleitorais de cada local.

## Entregas

- **`locais_por_bairro.py`** (CLI). O bairro é o único argumento obrigatório:

  ```bash
  python locais_por_bairro.py Tijuca --municipio "Rio de Janeiro"
  python locais_por_bairro.py tijuca --contem
  python locais_por_bairro.py Icaraí --municipio Niterói --fonte ibge --saida saidas/icarai.xlsx
  ```

  - Para cada local mostra zona, número, nome, endereço, bairro, nº de seções, eleitores e a lista de seções. As
    agregadas aparecem como `375 (agregada à 109)`. No fim, o total.
  - `--saida`: CSV (`;`) com uma linha por seção, com `TIPO_SECAO` (PRINCIPAL/AGREGADA), `NR_SECAO_PRINCIPAL` e
    `QT_ELEITOR_SECAO`.
  - Sem resultado, sugere nomes parecidos e devolve 1 (ex.: `barra` no Rio → `BARRA DA TIJUCA`, `barra olímpica`,
    `BARRA DE GUARATIBA`).
  - Opções: `--uf` (padrão RJ), `--ano` (padrão 2026), `--turno`, `--municipio`, `--contem`, `--fonte`,
    `--cache-dir`, `--sha512`, `-v`.
- **`apuracao/locais_bairro.py`** (sem I/O): `locais_do_bairro`, `secoes_dos_locais` e `sugestoes`. Recebem as seções
  de `eleitorado.load_sections` e reaproveitam `eleitorado.places` (resumo por local) e `bairros.locais_em_bairros`
  (ponto no polígono).

## Duas fontes de bairro

| Fonte | Critério | Quando usar |
|---|---|---|
| `cadastro` (padrão) | `NM_BAIRRO` do cadastro do TSE, comparado por `compact` (sem acento, caixa ou pontuação); exato, ou "contém" com `--contem` | o bairro como o TSE escreve |
| `ibge` | o bairro da malha do IBGE/Censo 2022 que contém a coordenada do local | o bairro oficial, o mesmo do mapa por bairro do site |

Números reais do cadastro de 2026 (RJ, 5.062 locais, 1.656 nomes de bairro distintos após `compact`):

| Consulta | Locais | Seções | Eleitores |
|---|---:|---:|---:|
| Tijuca, Rio de Janeiro, cadastro | 54 | 410 | 150.904 |
| Tijuca, Rio de Janeiro, ibge | 50 | 387 | 146.745 |
| Tijuca, estado inteiro, cadastro | 56 | 425 | 155.677 |
| `tijuca --contem`, estado inteiro (inclui Barra da Tijuca) | 84 | 690 | 269.242 |
| Icaraí, Niterói, cadastro | 18 | 180 | 57.636 |
| Icaraí, Niterói, ibge | 21 | 207 | 67.313 |

As duas fontes não coincidem, porque o texto do TSE é livre (CLAUDE.md: ~83% de coincidência no Rio). Como o
mesmo nome existe em vários municípios (há uma "Tijuca" em Teresópolis), vale passar `--municipio`.

## Adendo: planilha .xlsx (13/10/2026)

O CSV de `--saida` virou planilha `.xlsx`, gravada SEMPRE (padrão `saidas/<UF>/locais_bairro_<bairro>_<ano>.xlsx`,
bairro por `compact`; `--saida` muda o caminho). Sem resultado, nada é gravado.

- **Locais:** um por linha, com coordenadas, nº de seções, eleitores e a lista `SECOES` já rotulada
  (`375 (agregada à 109)`), a mesma que o terminal mostra (`tabela_locais`).
- **Seções:** uma por linha (`TIPO_SECAO`, `NR_SECAO_PRINCIPAL`, `QT_ELEITOR_SECAO`), o conteúdo do antigo CSV.
- **Consulta:** parâmetros (bairro, fonte, exato/contém, UF, município, ano, turno) e totais.

Gravada num `.tmp` e trocada no fim (`para_planilha`), como as outras saídas. Tijuca (Rio): 54 locais e 410 seções,
os mesmos números do terminal. 8 testes (2 novos: a tabela de locais e o destino padrão; o do CLI lê as três abas).

## Arquivos

- `locais_por_bairro.py` e `apuracao/locais_bairro.py` (novos).
- `test_locais_por_bairro.py`: 6 testes no cadastro sintético do `conftest.py`.
  - acento e caixa ignorados, agregada com a principal, mesmo bairro em dois municípios;
  - exato por padrão e `--contem` sob pedido;
  - a fonte `ibge` usa a coordenada: a Escola X diz "CENTRO" no cadastro mas cai na "Lapa Sintética";
  - local sem coordenada fica de fora;
  - erro sem malha;
  - CLI: impressão, CSV e sugestão com código 1.
- `CLAUDE.md`: módulo e comando registrados.

## Decisões

- **Exato por padrão:** com "contém", `Tijuca` traria a Barra da Tijuca (28 locais a mais no estado).
- **Sem município, o estado inteiro:** o nome digitado pode existir em mais de um município. A saída agrupa por
  município para deixar isso visível, em vez de recusar a consulta.
- **Ponte local → seção pelo cadastro de eleitorado** (não pela votação): lista também as seções agregadas e serve
  para 2026 antes dos microdados de votação.

## Verificação

- `pytest -q -m "not e2e"`: no ramo, 423 passaram e 1 foi pulado (sem os 80 e2e); no `main`, depois do
  `cherry-pick`, 419 passaram e 1 foi pulado (sem os 70 e2e). O script não toca no front-end.
- `ruff check` sem apontamentos nos três arquivos novos.
- Consultas reais acima, no cache de 2026.

## Pendências

- Nenhuma: o script está no `main` e no ramo `frontend-refatoracao`.
