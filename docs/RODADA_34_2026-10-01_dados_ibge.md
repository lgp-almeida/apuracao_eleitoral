# Rodada 34 — Dados do IBGE: download antecipado e atualização

01/10/2026 · pedido do usuário: "Avalie como implementar o download e update de dados do IBGE necessários ao funcionamento pós eleição".

## Objetivo

Depois da eleição entram em uso o mapa e a comparação por bairro de 2026, o Perfil × voto (por bairro e por local), o mapa por local e a transferência 2022 → 2026. Todos dependem de dados do IBGE. Até aqui, esses dados eram baixados sob demanda, de quatro jeitos diferentes, e nunca eram atualizados:

| Dado | Antes | Problema |
|---|---|---|
| Malha municipal (API `servicodados` v3) | `requests.get` cru dentro do `app.py` | sem proveniência; escrita não atômica |
| Malha de bairros (geoftp) | `requests.get` cru em `bairros.malha` | idem; o GeoJSON derivado nunca era refeito |
| Censo 2022 por bairro (renda, básico, cor) | `v.download` com URL fixa | **nome com data fixa** (`_20260508`, `_20260520`) |
| Malha de setores + Censo por setor | `v.download` com URL fixa | idem; o Parquet derivado nunca era refeito |

O que foi verificado no IBGE real em 01/10/2026:

- o FTP lista os diretórios por HTTPS;
- quando o IBGE republica um arquivo, a data entra no nome (`…basico_BR_20260520.zip`, `…domicilio2_BR_20250417.zip`). Com URL fixa, a versão antiga sai do ar e uma instalação nova quebra; numa instalação antiga, o cache fica velho para sempre;
- o geoftp responde a HEAD com `Last-Modified`/`ETag`;
- a API `servicodados` não aceita HEAD (responde 405).

## Entregas

- **`apuracao/ibge.py`**: catálogo `FONTES` com 9 fontes. Cada `Fonte` guarda:
  - o **modelo** do nome (`{versao}` = "" ou `_AAAAMMDD`; `{uf}`);
  - a versão conhecida;
  - a pasta no cache;
  - os derivados.
- **`caminho(chave, cache, uf)`**: é o que os módulos de domínio chamam.
  - Se o arquivo está no cache, devolve a versão mais nova que houver lá, sem ir à rede.
  - Se falta, descobre a versão no índice do FTP e baixa uma vez pelo `v.download`. Se o índice não responder, tenta a versão conhecida.
- **`verificar`**: índices + um HEAD por arquivo, sem baixar nada. Ações possíveis:
  - "baixar": a fonte não está no cache;
  - "baixar versão nova": há data mais nova no nome;
  - "baixar de novo": o `Last-Modified` é mais novo que o do cache, ou, sem data local, o tamanho difere;
  - "conferir": malha da API, só com `--forcar-api` ou depois de 30 dias;
  - "tentar de novo": o IBGE está fora do ar ou respondeu com erro HTTP.
- **`atualizar`**:
  - baixa com `microdados.baixar` (temporário + troca atômica + proveniência com SHA-512);
  - guarda a versão anterior (`.anterior`, se o nome é o mesmo) e o derivado antigo;
  - refaz o derivado com as funções que já existiam (`bairros.malha`, `perfil.censo_por_bairro`, `perfil_local.setores`);
  - se o derivado der certo, apaga a versão anterior; se falhar, **volta à anterior** (arquivo, proveniência e derivado). Assim, nunca fica sem dado;
  - malha da API: GET + SHA-512, e só troca o arquivo se o conteúdo mudou; uma página de erro (não JSON) não entra no cache.
- **`preparar`**: garante todas as fontes e todos os derivados (baixa só o que falta).
- **Estado** da última verificação: `<cache>/ibge_estado.json`.
- **CLI `preparar_ibge.py`**: `--so-verificar`, `--forcar-api`, `--vigiar` (24 h; mínimo 1 h), `--uf` e `--cache-dir`. Ao trocar algum arquivo, avisa para reiniciar os sites no ar.
- **Módulos de domínio**:
  - `bairros.malha`, `perfil.censo_por_bairro`, `perfil_local.setores`/`ligar` e `app.py` (malha municipal) agora usam `ibge.caminho`;
  - saíram as URLs fixas (`MALHA_URL` ×2, `CENSO_BASE`, `CENSO_ARQUIVOS`, `MALHA_SETORES`, `IBGE_UF`);
  - `perfil.UF_IBGE` passa a ser `ibge.UF_IBGE`.
- **Prontidão**: confere os Parquet do Censo (por bairro e por setor) e mostra a linha "IBGE atualizado", lida de `ibge_estado.json`, sem rede. Dá AVISO se a verificação nunca foi feita, se há ação pendente ou se faz mais de 30 dias.
- **`preparar_2026.py`**: quando chegam votos por seção ou o perfil, chama `ibge.preparar` antes da transferência.

## Decisões

- **Sem recarga a quente**: os caches em memória (`Bairros._geo`, `PerfilVoto._censo`, `PerfilVotoLocal._censo_ano`, a malha municipal no `app.py`) continuam como estavam. O IBGE muda em meses, e a CLI avisa quando é preciso reiniciar o site.
- **Versão por data no nome, não por `Last-Modified`**: é assim que o IBGE publica as versões. O HEAD cobre o caso raro de um arquivo republicado com o mesmo nome.
- **Sem data local e com o mesmo tamanho**: o arquivo é considerado em dia (ZIP posto à mão). Isso evita rebaixar centenas de MB à toa.
- **Testes**: `download_sem_rede` também bloqueia o índice do IBGE, mas só quando a sessão é o `requests` real. A fixture de sessão `site` (e2e) mantém o patch durante toda a sessão de testes, e os testes de `test_ibge.py` usam sessões falsas.

## Verificação

- `pytest -q`: **303 passaram**, 6 pulados (os mesmos de antes). Os 16 novos em `test_ibge.py` cobrem:
  - modelo e versão do nome;
  - escolha da versão datada mais nova (ignorando xlsx e outro nível);
  - cache sem rede;
  - download pelo índice;
  - volta à versão conhecida quando não há índice;
  - 404 da malha de bairros com a mensagem de antes;
  - API: proveniência e recusa de página de erro;
  - matriz do `verificar`;
  - IBGE fora do ar;
  - atualização com versão nova (derivado refeito, antiga apagada; a 2ª rodada não baixa nada);
  - volta atrás quando a versão nova não converte, com nome novo e com o mesmo nome;
  - falha no download;
  - API conferida só quando pedida;
  - CLI e prontidão.
- IBGE real (`python preparar_ibge.py --so-verificar` com cache vazio): as 9 fontes foram resolvidas, todas com HTTP 200:
  - renda: `20260508`;
  - básico: `20260520`;
  - cor: sem data;
  - malhas: de 12/11/2024.
- Download real das duas malhas pequenas: malha municipal (153 kB) e malha de bairros, com 1.509 bairros no GeoJSON. Na verificação seguinte, ambas aparecem "em dia".

## Pendências

- Rodar `python preparar_ibge.py` na máquina da noite **antes de 3/10**, para baixar os agregados nacionais (algumas centenas de MB) e gerar os Parquet. O roteiro já tem esse passo.
- Se o IBGE publicar novos temas úteis (alfabetização já existe por bairro e por setor), basta acrescentar uma `Fonte` e o indicador correspondente.
