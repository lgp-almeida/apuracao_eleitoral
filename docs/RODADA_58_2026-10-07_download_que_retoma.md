# Rodada 58 — Download dos microdados que continua de onde parou

07/10/2026 · pendência das rodadas 54 e 57. Em 06/10, o `votacao_secao_2026_RJ` (290 MB) caiu duas vezes no meio
(`IncompleteRead`, `RemoteDisconnected`). A cada queda, o arquivo inteiro era pedido de novo na verificação
seguinte, uma hora depois. No 2º turno, essa hora conta.

## Como ficou (`apuracao/microdados.py`)

- **Arquivo parcial:** o download vai para `<zip>.parcial`, no cache, ao lado de `<zip>.parcial.json`, que guarda
  a versão (o `Last-Modified`) a que o parcial pertence. Antes ia para uma pasta temporária, apagada em qualquer
  falha.
- **Continuar:** havendo parcial, o GET pede só o que falta (`Range: bytes=N-`) com `If-Range: <versão>`.
  - Se o arquivo no TSE ainda é aquela versão, vem 206 e os bytes são acrescentados.
  - Se o TSE trocou o arquivo, vem 200 com o arquivo inteiro, e o parcial recomeça do zero, sem misturar versões.
  - Comportamento conferido na CDN real: `If-Range` certo dá 206 só com o pedaço; data errada dá 200 com tudo.
- **Quedas** (`ConnectionError`, `Timeout`, `ChunkedEncodingError`): o download continua até `RETOMADAS` = 5
  vezes na mesma verificação, com `PAUSA_RETOMADA_S` = 5 s entre elas.
  - Se ainda falhar, o parcial **fica** no cache, e a próxima verificação (outra execução, outro processo)
    continua dele.
- **Versão:** um parcial de versão diferente da anunciada pelo HEAD é descartado antes de começar. Cópia velha da
  CDN (rodada 54) também descarta o parcial antes do pedido com `?v=`.
- **SHA-512:** é o do arquivo inteiro, calculado no fim sobre o parcial completo. A conferência com o `.sha512` do
  Boletim de Urna continua igual (`bweb.baixar` usa o mesmo `baixar`).
- **Troca atômica:** `<zip>.parcial` → `<zip>` (mesma pasta), e a proveniência é gravada depois, como antes.

## Verificação

- **`test_microdados.py`, 3 testes novos** com uma CDN falsa que respeita `Range`/`If-Range` e derruba a conexão:
  - duas quedas, os pedidos continuam em `bytes=30000-` e `bytes=80000-`, e o SHA bate;
  - todas as tentativas caem, o parcial fica com 50 KB, e a próxima chamada continua dele;
  - parcial de outra versão é descartado; servidor que ignora `Range` recomeça sem misturar.
- **Sem a implementação**, os testes novos dão erro.
- **Ponta a ponta na CDN real** (`votacao_partido_munzona_2026`, 9,2 MB, sessão que derruba a 1ª conexão):
  - "conexão caiu com 4 MB … continuando de 4 MB";
  - pedidos `[sem Range, bytes=4194304-]`;
  - arquivo final com o **mesmo SHA-512** do download inteiro.
- **`conftest.py`:** zera a pausa entre tentativas, porque o teste de queda da rodada 40 passou a fazer novas
  tentativas e demoraria 20 s.
- `pytest -q -m "not e2e"`: 406 passados e 1 pulado.

## Observação

Durante o teste, o `votacao_partido_munzona_2026` estava com `Last-Modified` de 07/10 às 16h39 de Brasília: o TSE
o regerou de novo depois das 12h39. O cache ainda tem a versão das 12h39.
