# Rodada 12 — Planilha histórica no endereço da aba Candidato

30/09/2026 · pedido do usuário após a [rodada 11](RODADA_11_2026-09-30_endereco_da_comparacao.md)

## Objetivo

Completar o endereço da aba Candidato (rodada 10) com o formulário da planilha histórica, a última parte do site que ainda não ia para o endereço.

## Formato

```
#candidato?cargo=7&numero=66010&pl=1&pl_ano=2022&pl_cargo=deputado+estadual&pl_numero=13713&pl_municipio=Niterói&pl_comparar=2024
```

| Parâmetro | Campo | Observação |
|---|---|---|
| `pl=1` | bloco "Planilha histórica" aberto | sem ele, nenhum campo `pl_*` é gravado nem aplicado |
| `pl_ano` | Ano | 2022, 2024, 2026 |
| `pl_cargo` | Cargo | presidente, governador, senador, deputado federal, deputado estadual, prefeito, vereador |
| `pl_numero` | Número | prevalece sobre o número do candidato consultado |
| `pl_municipio` | Município | texto livre |
| `pl_comparar` | Comparar locais com | ano |

- Os parâmetros da consulta (`cargo`, `numero`, `municipio`, `ordem`) são opcionais. `#candidato?pl=1&…` abre só a planilha preenchida.
- **Não há download automático:** abrir o link só preenche o formulário, e o `.xlsx` é gerado pelo botão. Um arquivo gerado sozinho ao abrir um link seria surpreendente e pesado, porque o 1º uso de um ano baixa microdados.

## O que foi feito (só front-end)

- **`CAMPOS_PLANILHA`:** mapeia parâmetro → campo.
- **`enderecoCandidato()`:** grava `pl=1` e os campos preenchidos quando o bloco está aberto. Passou a funcionar também sem candidato consultado.
- **`aplicarPlanilha()`:** abre o bloco e preenche os campos; valor desconhecido num seletor é ignorado.
- **Quando o endereço é atualizado:** ao abrir ou fechar o bloco (evento `toggle`) e a cada alteração de campo (`change`).
- **Ordem ao abrir um link:** primeiro a consulta do candidato (que preenche o nº da planilha com o do candidato), depois os campos do endereço, que prevalecem.

## Verificação

- **Captura** do Chrome em modo headless, site do simulado: o link acima abriu a consulta do 66010 e o bloco da planilha aberto com 2022, deputado estadual, **13713** (e não 66010), Niterói e 2024.
- **DOM:** `#candidato?pl=1&pl_ano=2024&pl_cargo=vereador` abriu a aba Candidato com o bloco aberto e sem consulta.
- `pytest -q`: 51 testes passando. A mudança é só de front-end e **não tem teste automatizado**.

## Estado final dos endereços

Tudo o que aparece nas quatro abas agora pode ser reproduzido pelo endereço: Painel (`#painel`), Candidato (consulta, município da evolução, ordem da tabela e planilha histórica), Mapas (cargo, métrica, candidato, momento da linha do tempo e camada de locais) e Comparação (cargo, métrica, partido ou par de números e ordem).
