# Anexo I — Atualizações ao Comparativo TSE 2022 × 2026

Sep 29, 2026 · @Luiz Almeida

## Objetivo e convenção

A verificação nos sites do TSE em 29/09/2026 (cinco dias antes do 1º turno) encontrou 7 blocos de mudança no documento inicial *"Eleições TSE 2022 vs 2026: Normas, Quocientes e Acesso Programático aos Dados"*. As mais críticas para o pipeline são os novos códigos de eleição e o novo esquema de URLs de resultados.tse.jus.br (A6) e a manutenção da distribuição de vagas por UF de 2022 (A4).

Cada item abaixo usa uma marca e aponta o trecho do documento inicial que altera:

- **\[ATUALIZADO\]** — o trecho original continua válido na essência, mas um dado, número ou referência muda.
- **\[EXCLUÍDO\]** — o trecho original deve ser desconsiderado (incorreto ou superado).
- **\[INCLUÍDO\]** — informação nova, sem correspondente no documento inicial.

| Bloco | Seção do documento inicial | Marcas | O que muda |
| --- | --- | --- | --- |
| A1 | Key Findings §1 — Datas e cargos | INCLUÍDO | Conselho Distrital de Fernando de Noronha; vagas, eleitorado, seções e zonas de 2026 |
| A2 | Details §1 — Captação | ATUALIZADO, INCLUÍDO | Res. 23.759, 23.767 e 23.769/2026; regra de IA 72h/24h |
| A3 | Details §2 — Totalização | ATUALIZADO, EXCLUÍDO | Vaga sem suplente não cita Senado; item (iii) não localizado no texto |
| A4 | Details §3 — Quocientes | INCLUÍDO, ATUALIZADO | Vagas por UF de 2022 mantidas (ADO 38); art. 12-A; cláusula de desempenho 2026 |
| A5 | Details §4 — Divulgação | ATUALIZADO | Simulados já realizados; carga no data center em 3/10; \~2,5 milhões de arquivos |
| A6 | Details §5 — Acesso programático | ATUALIZADO, EXCLUÍDO, INCLUÍDO | Códigos 6257/6259/6261; URLs `-u.json`/`-ab.json`; datasets 2026 no CKAN |
| A7 | Recommendations e Caveats | ATUALIZADO, EXCLUÍDO | Itens condicionais já resolvidos; novos cuidados |

## A1 — Datas, cargos, vagas e números do pleito

**Referência no documento inicial:** Key Findings §1 ("Datas e cargos").

**\[ATUALIZADO\] Datas confirmadas.** As datas de 4/10/2026 (1º turno) e 25/10/2026 (2º turno) estão confirmadas no art. 2º da [Res.-TSE nº 23.751/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-751-de-26-de-fevereiro-de-2026). Votação das 8h às 17h, horário de Brasília, em todo o país. Nenhuma correção de data é necessária.

**\[INCLUÍDO\] Conselho Distrital de Fernando de Noronha.** No mesmo dia do 1º turno ocorre a eleição do Conselho Distrital do Arquipélago de Fernando de Noronha (PE), prevista na Res. 23.751/2026. O documento inicial listava apenas os cargos federais e estaduais. Para o pipeline, isso gera uma terceira eleição no arquivo de configuração (código 6261, ver A6) e o cargo "Conselheiro Distrital" nos simulados.

**\[INCLUÍDO\] Vagas e números oficiais de 2026** ([CDE 2026 / TSE](https://www.tse.jus.br/eleicoes/cde-2026)):

| Item | 2026 |
| --- | --- |
| Deputados federais | 513 |
| Deputados estaduais | 1.035 |
| Deputados distritais | 24 |
| Senadores (2/3 do Senado, 2 por UF) | 54 |
| Governadores | 27 |
| Eleitorado apto | 158.765.543 |
| Seções eleitorais | 516.785 |
| Zonas eleitorais | 2.641 |
| Mesários convocados/voluntários | 1.922.579 |

**\[INCLUÍDO\] Ordem de votação na urna em 2026:** deputado federal → deputado estadual/distrital → senador (1ª vaga) → senador (2ª vaga) → governador → presidente. A dupla escolha de senador é tratada como **um único cargo com duas vagas** nos arquivos de resultados (ver A6).

## A2 — Captação de votos

**Referência no documento inicial:** Details §1 ("Normatização da captação dos votos") e Recommendation 1.

O núcleo normativo de 2026 (Res. 23.751/2026) não mudou de arquitetura, mas recebeu alterações em agosto que o documento inicial não registra. A lista oficial de [resoluções de 2026](https://www.tse.jus.br/legislacao/compilada/res/2026) vai hoje até a nº 23.777.

**\[INCLUÍDO\] Resoluções posteriores a 4/03/2026 que afetam captação e auditoria:**

| Resolução | Data | Altera | Efeito relevante |
| --- | --- | --- | --- |
| [23.767/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-767-de-3-de-agosto-de-2026) | 03/08/2026 (DJE 07/08) | Res. 23.751/2026 (atos gerais) | Inclui o JE-Connect no art. 4º; transporte a eleitores com deficiência em transferência temporária; fones de ouvido descartáveis por local de votação |
| [23.769/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-769-de-3-de-agosto-de-2026) | 03/08/2026 (DJE 07/08) | Res. 23.673/2021 (auditoria) | Relatório da auditoria de funcionamento das urnas em até 5 dias úteis após cada turno ao TRE; relatórios ao TSE em até 10 dias úteis; publicação em até 30 dias após o 2º turno |
| 23.771/2026 | 03/08/2026 | Res. 23.760/2026 (calendário) | Ajustes no calendário eleitoral |
| 23.763/2026 | 09/06/2026 | — | Política de Segurança da Informação da Justiça Eleitoral |
| 23.766/2026 | 01/07/2026 | — | Limites de gastos de 2026, mantidos nos valores de 2022 |

**\[INCLUÍDO\] Res. 23.759/2026 ("estatuto da cidadania eleitoral").** Consolida pela primeira vez, num só texto, as regras destinadas ao eleitor: documentos aceitos, proibição de celular na cabine, acessibilidade, nome social. Não constava no par de resoluções do documento inicial.

**\[ATUALIZADO\] Regra de IA na propaganda (Res. 23.755/2026).** Além da rotulagem de conteúdo sintético já citada, fica proibido publicar, republicar ou impulsionar **novo** conteúdo sintético nas 72 horas antes e nas 24 horas depois do pleito ([CDE 2026](https://www.tse.jus.br/eleicoes/cde-2026)).

**\[ATUALIZADO\] Recommendation 1 (pares de resoluções).** Acrescentar ao par "auditoria/biometria" a Res. 23.769/2026, e ao par "captação" a Res. 23.767/2026. As íntegras não estão só no DJE extra nº 30 de 04/03/2026: as alterações de agosto estão no DJE-TSE nº 131, de 07/08/2026.

Não verificado nesta rodada (mantém-se como no documento inicial, sem confirmação nova): números de urnas por modelo em 2026 e o Edital TSE nº 1/2026 da urna de 2028.

## A3 — Totalização

**Referência no documento inicial:** Details §2, parágrafo "2026 — Res.-TSE nº 23.748", itens (i), (ii) e (iii).

A leitura do texto consolidado da [Res.-TSE nº 23.748/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-748-de-26-de-fevereiro-de-2026) exige uma correção, uma exclusão e três inclusões.

**\[ATUALIZADO\] Item (i) — vaga sem suplente.** O documento inicial diz "Senado e Câmara". O novo art. 15 da Res. 23.677/2021 fala em **Câmara dos Deputados, Assembleias Legislativas e Câmara Legislativa do DF**, não no Senado. Nova eleição só se faltarem 15 meses ou mais para o fim do mandato. Para Câmaras Municipais vale a Lei Orgânica do município.

**\[ATUALIZADO\] Item (ii) — desfiliação.** Confirmado: é o novo § 1º-A do art. 29, citando a TutCautAnt nº 0613340-16.2024.6.00.0000.

**\[EXCLUÍDO\] Item (iii) — "TREs devem comunicar imediatamente o TSE para recálculo da Câmara".** Esse dispositivo não aparece no texto consolidado da Res. 23.748/2026 consultado. Até que se localize a fonte, retirar o item do documento.

**\[INCLUÍDO\] Dispositivos da Res. 23.748/2026 relevantes para quem totaliza dados:**

- **Art. 7º §§ 1º e 2º** — vagas de deputado federal pela LC 78/1993; vagas estaduais/distritais = 3 × bancada federal até 36, mais uma por deputado federal acima de 12.
- **Art. 22 § 5º e art. 27** — votos "anulados sub judice" não impedem a distribuição de vagas nem a proclamação no sistema proporcional. Nos cálculos entram só os votos válidos e as legendas em situação equivalente.
- **Art. 29 caput e § 1º** — qualquer mudança na situação jurídica de partido, federação ou candidato que altere o resultado obriga a nova totalização. Idem na passagem de "anulado sub judice" para "anulado definitivo".

Implicação prática: o campo de destinação do voto (válido, anulado sub judice, anulado) muda depois do pleito. Um snapshot tirado na noite da eleição não é o resultado final. Os simulados de setembro incluíram exatamente esses casos (ver A6).

## A4 — Quociente eleitoral e partidário

**Referência no documento inicial:** Details §3 ("Base legal" e "A diferença central entre 2022 e 2026") e Recommendation 2.

A regra de 2026 para deputados federais e estaduais está agora escrita na própria resolução, e o número de vagas por UF é o mesmo de 2022.

**\[INCLUÍDO\] Vagas por UF congeladas nos números de 2022 (ADO 38).** O documento inicial não trata do tamanho das bancadas. O Congresso aprovou o PLP 177/2023 (513 → 531 deputados), mas o presidente o [vetou integralmente em julho de 2025](https://www.camara.leg.br/noticias/1181279-lula-veta-projeto-que-aumenta-de-513-para-531-o-numero-de-deputados-federais/). Em 29/09/2025 o ministro Fux concedeu cautelar mantendo, para 2026, o número de vagas por UF de 2022; o plenário do STF referendou por unanimidade ([STF](https://noticias.stf.jus.br/postsnoticias/supremo-mantem-numero-de-deputados-federais-para-2026/)). A redistribuição fica para 2030.

Consequência para o cálculo: o denominador do QE por UF é o mesmo de 2022 (ex.: SP = 70 federais e 94 estaduais, segundo o [TRE-SP](https://www.tre-sp.jus.br/comunicacao/noticias/2026/Junho/quociente-eleitoral-e-partidario-explica-por-que-o-mais-votado-pode-nao-ser-eleito)). Sem a cautelar, o RJ teria perdido 4 cadeiras federais. O pipeline pode reutilizar a tabela de vagas de 2022 e cruzar com o arquivo de vagas do dataset `candidatos-2026`.

**\[ATUALIZADO\] Regra das sobras agora positivada.** O documento inicial descreve a regra pós-STF apenas como jurisprudência. A Res. 23.748/2026 reescreveu o art. 12-A da Res. 23.677/2021 em duas fases:

1. Primeiro, as sobras vão para partidos e federações com pelo menos 80% do QE que tenham candidato com votação nominal de pelo menos 20% do QE.
2. Depois, as cadeiras restantes vão para **todos** os partidos e federações que disputaram, ocupadas independentemente de votação mínima do candidato.

As duas fases usam a maior média. A variante "pós-STF" da Recommendation 2 deve implementar exatamente essa sequência, e não só "todos os partidos nas sobras".

**\[INCLUÍDO\] Cláusula de desempenho partidário em 2026.** O documento inicial cita só os parâmetros de 2022. Em 2026 o partido precisa de 2,5% dos votos válidos para a Câmara, em pelo menos 1/3 das UFs, com mínimo de 1,5% em cada uma. A alternativa é eleger 15 deputados federais em pelo menos 1/3 das UFs ([Agência Câmara](https://www.camara.leg.br/noticias/1300504-deputados-sao-eleitos-pelo-voto-proporcional-entenda-a-logica-desse-sistema)). A cláusula não afeta a distribuição de cadeiras, apenas fundo partidário e tempo de TV.

**\[ATUALIZADO\] Observação sobre extração de microdados de 2022.** Além do recálculo de 2025 já citado, o TSE publicou tabelas de representação na Câmara que consideram novas totalizações ocorridas até 20/07/2026 ([Eleições 2026 / TSE](https://www.tse.jus.br/eleicoes/eleicoes-2026-content)). A data de corte da extração continua sendo metadado obrigatório.

## A5 — Disponibilização dos resultados

**Referência no documento inicial:** Details §4, parágrafo "2026" ("testes simulados previstos para setembro/2026").

Os simulados de setembro já ocorreram, e o TSE detalhou o cronograma da noite da eleição.

**\[ATUALIZADO\] Etapas da preparação** ([Informações técnicas 2026](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados); [notícia TSE de 06/07/2026](https://www.tse.jus.br/comunicacao/noticias/2026/Julho/tse-fara-simulados-com-veiculos-de-imprensa-para-testar-divulgacao-dos-resultados-das-eleicoes-2026)):

| Data | Etapa | Situação em 29/09 |
| --- | --- | --- |
| 04/10/2026, 17h | Início da totalização e da divulgação | Previsto |
| 03/10/2026 | Inserção dos parâmetros oficiais no data center do TSE | Previsto |
| 28–29/09/2026, 15h–17h | 3ª janela de simulado (semana extra; horário alterado) | Em curso / concluída hoje |
| 22–24/09/2026, 9h–12h e 14h–17h | 2ª janela de simulado | Realizada |
| 15–17/09/2026, 9h–12h e 14h–17h | 1ª janela de simulado | Realizada |
| 06/07/2026 | Audiência técnica (art. 266 da Res. 23.751), 140 participantes de mais de 20 instituições | Realizada |

**\[INCLUÍDO\] Escala e integridade.** O TSE estima quase 2,5 milhões de arquivos por ciclo eleitoral. BU e RDV são publicados como saem das urnas, sem alteração. É vedado às empresas alterar qualquer conteúdo distribuído ou cobrar a mais pelos dados, que são públicos e gratuitos.

**\[INCLUÍDO\] Acesso sem cadastro.** Não é preciso cadastro, autorização nem convênio para consumir os arquivos, e não haverá whitelist de IP. Cada consumidor pode usar só as UFs e cargos de interesse.

**\[INCLUÍDO\] Sem histórico nos arquivos parciais.** Na documentação de 2024, o TSE informa que os arquivos de resultado são sobrescritos a cada atualização. Quem quiser a série temporal da apuração precisa gravar os próprios snapshots.

Mantém-se do documento inicial: publicação dos microdados consolidados no Portal de Dados Abertos alguns dias após o pleito, e diplomação até 18/12/2026 (não reverificada).

## A6 — Acesso programático aos dados

**Referência no documento inicial:** Details §5, subseções (A) Portal de Dados Abertos e (B) resultados.tse.jus.br, incluindo o exemplo Python "resultados em tempo real (histórico 2022)".

O portal CKAN já tem os datasets de 2026, e o TSE publicou os códigos e o esquema de URLs de 2026, que diferem dos exemplos de 2022 do documento inicial.

### (A) Portal de Dados Abertos

**\[INCLUÍDO\] Datasets de 2026 já publicados** ([filtro "Ano 2026"](https://dadosabertos.tse.jus.br/dataset/?tags=Ano+2026)):

| Slug | Conteúdo | Arquivo confirmado na CDN |
| --- | --- | --- |
| [`candidatos-2026`](https://dadosabertos.tse.jus.br/dataset/candidatos-2026) | Candidatos, bens, coligações, vagas, cassação, redes sociais, fotos por UF, propostas de governo, histórico | `consulta_cand/consulta_cand_2026.zip`, `bem_candidato/bem_candidato_2026.zip`, `consulta_cand/rede_social_candidato_2026.zip`, `proposta_governo/proposta_governo_2026_BR.zip` |
| [`eleitorado-2026`](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026) | Eleitorado, perfil com deficiência, eleitorado por local de votação, perfil por seção | Nome não aberto nesta verificação |
| [`prestacao-de-contas-eleitorais-2026`](https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais-2026) | Contas de órgãos partidários e candidatos, CNPJ de campanha, extratos | — |

`resultados-2026` ainda não existe: depende do pleito. Os recursos de 2026 continuam exibindo "Não há visões criadas para este recurso ainda", o que reforça a estratégia `package_show` → `resources[].url` → CDN.

**\[INCLUÍDO\] Ligação com os scripts do projeto.** O `eleitorado-2026` (local de votação, coordenadas, agregação de seções) já pode alimentar `votos_por_local_votacao.py --ano 2026 --com-eleitorado`, antes mesmo dos votos. Confirmar o nome do ZIP via `package_show` antes de assumir `eleitorado_local_votacao_2026.zip`.

### (B) resultados.tse.jus.br

**\[EXCLUÍDO\] Como referência para 2026:** o padrão `…/oficial/ele2022/<cod>/dados-simplificados/<uf>/<uf>-c<mun>-e<cod>-r.json`, os códigos 544/546 e o caminho `arquivo-urna/406/…`. São de 2022. Também o exemplo que lê `cfg["pl"]` com chaves `cd`/`dt`, cuja estrutura para 2026 deve ser tirada da especificação EA11.

**\[ATUALIZADO\] Parâmetros oficiais de 2026** ([Informações técnicas 2026](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)):

| Ambiente | URL base | `ambiente` | Pleito | Eleições |
| --- | --- | --- | --- | --- |
| Oficial (1º turno, 04/10) | `https://resultados.tse.jus.br` | `oficial` | 3220 | 6257 Federal (Presidente) · 6259 Estaduais (Gov., Sen., Dep. Fed., Dep. Est./Dist.) · 6261 Conselho Distrital |
| Simulado | `https://resultados-sim.tse.jus.br/simulado` | `simulado2026` | 17801 | 21270 Federal · 21272 Estadual · 21274 Municipal |

O `ciclo` (ex.: `ele2026`) e os códigos do 2º turno devem ser lidos do `ele-c.json`, segundo o FAQ do TSE.

**\[ATUALIZADO\] Esquema de URLs** (inferido dos exemplos oficiais do simulado; `e` com 6 dígitos, cargo com 4, município TSE com 5):

| Arquivo | Especificação | Caminho relativo a `<base>/<ambiente>/` |
| --- | --- | --- |
| Configuração de eleições | EA11 | `comum/config/ele-c.json` |
| Configuração de municípios | EA12 | `<ciclo>/<e>/config/mun-e<e:06>-cm.json` |
| Acompanhamento Brasil | EA14 | `<ciclo>/<e>/dados/br/br-e<e:06>-ab.json` |
| Acompanhamento UF | EA15 | `<ciclo>/<e>/dados/<uf>/<uf>-e<e:06>-ab.json` |
| Resultado unificado (UF ou BR) | EA20 | `<ciclo>/<e>/dados/<uf>/<uf>-c<cargo:04>-e<e:06>-u.json` |
| Resultado unificado (município) | EA20 | `<ciclo>/<e>/dados/<uf>/<uf><mun:05>-c<cargo:04>-e<e:06>-u.json` |
| Eleitos | EA10 | sufixo `-e.json`; caminho exato na especificação |
| Configuração de seções / auxiliar de seção | EA16 / EA18 | caminho exato na especificação |

Cargos confirmados pelos exemplos: 0001 Presidente, 0003 Governador, 0005 Senador. Os demais códigos de cargo devem ser conferidos no EA11/EA12. O código de município no nome do arquivo é o **código TSE**, não o IBGE: a tabela de-para do projeto continua necessária.

**\[ATUALIZADO\] Regras operacionais, agora confirmadas para 2026** (o documento inicial as tratava como parâmetro de 2024):

- Até 100 requisições por segundo por IP. Estourou: bloqueio de 10 minutos, reiniciado a cada nova tentativa durante o bloqueio.
- Respostas HTTP 304 (ETag / Last-Modified) também contam no limite.
- Vários 404 podem bloquear o IP, sem limiar divulgado. Não é possível listar arquivos no servidor.
- Código de município sempre com 5 dígitos e zeros à esquerda.
- As mesmas restrições valeram nos simulados.

**\[INCLUÍDO\] Detalhes de modelo que afetam o parser:**

- **Sem arquivos de índice.** Para detectar mudanças, use as datas/horas de totalização do EA14 (UFs) e do EA15 (municípios) e só então busque o EA20. No EA16, os atributos `da`/`ha` indicam a chegada dos arquivos de urna de cada seção.
- **IDG não é versão.** É um identificador único por arquivo gerado; não serve para ordenar atualizações.
- **EA10** só existe após a primeira totalização final de uma UF; antes disso retorna 404. Presidente não tem EA10: o resultado vem do EA20 de abrangência BR.
- **Senador** é um único cargo com duas vagas; os eleitos saem no mesmo registro.
- **Campo `and=f`:** Presidente segue a regra de eleição federal (UF final quando `snt=0`); os demais cargos seguem a regra estadual (UF final só com totalização final).
- **Arquivos assinados:** o TSE publicou um manual de verificação dos arquivos JWS; validar a assinatura é recomendável em pipeline de auditoria.
- **Polling:** o TSE não fixou intervalo recomendado.

**\[ATUALIZADO\] Exemplo Python** — substitui o exemplo "resultados em tempo real (histórico 2022)". Usa apenas os caminhos acima e respeita o limite. Não foi executado contra o TSE: o ambiente de teste não acessa `tse.jus.br`.

```python
"""Cliente mínimo da divulgação 2026 (TSE): EA11/EA12/EA14/EA15/EA20 com ETag."""
from __future__ import annotations

import time

import requests

AMBIENTES = {
    "oficial": ("https://resultados.tse.jus.br", "oficial"),
    "simulado": ("https://resultados-sim.tse.jus.br/simulado", "simulado2026"),
}
HEADERS = {"User-Agent": "estudo-eleitoral-python/1.0 (contato: seu-email)"}
INTERVALO_MIN_S = 0.05  # no máximo ~20 req/s, bem abaixo do teto de 100 req/s por IP


class ClienteDivulgacao:
    def __init__(self, ambiente: str = "oficial", ciclo: str = "ele2026") -> None:
        self.base, self.amb = AMBIENTES[ambiente]
        self.ciclo = ciclo  # conferir no ele-c.json (EA11)
        self.sessao = requests.Session()
        self.sessao.headers.update(HEADERS)
        self._etag: dict[str, str] = {}
        self._cache: dict[str, dict] = {}
        self._ultimo = 0.0

    def _get(self, caminho: str) -> dict | None:
        espera = INTERVALO_MIN_S - (time.monotonic() - self._ultimo)
        if espera > 0:
            time.sleep(espera)
        url = f"{self.base}/{self.amb}/{caminho}"
        cab = {"If-None-Match": self._etag[url]} if url in self._etag else {}
        resp = self.sessao.get(url, headers=cab, timeout=30)
        self._ultimo = time.monotonic()
        if resp.status_code == 304:
            return self._cache[url]
        if resp.status_code == 404:
            return None  # ex.: EA10 antes da 1ª totalização final. Não repetir em laço.
        resp.raise_for_status()
        if "ETag" in resp.headers:
            self._etag[url] = resp.headers["ETag"]
        self._cache[url] = resp.json()
        return self._cache[url]

    def config_eleicoes(self) -> dict | None:  # EA11
        return self._get("comum/config/ele-c.json")

    def config_municipios(self, eleicao: int) -> dict | None:  # EA12
        return self._get(f"{self.ciclo}/{eleicao}/config/mun-e{eleicao:06d}-cm.json")

    def acompanhamento(self, eleicao: int, uf: str = "br") -> dict | None:  # EA14 (br) / EA15 (uf)
        uf = uf.lower()
        return self._get(f"{self.ciclo}/{eleicao}/dados/{uf}/{uf}-e{eleicao:06d}-ab.json")

    def resultado(self, eleicao: int, uf: str, cargo: int,
                  cd_municipio_tse: int | None = None) -> dict | None:  # EA20
        uf = uf.lower()
        abrang = uf if cd_municipio_tse is None else f"{uf}{cd_municipio_tse:05d}"
        return self._get(
            f"{self.ciclo}/{eleicao}/dados/{uf}/{abrang}-c{cargo:04d}-e{eleicao:06d}-u.json"
        )


if __name__ == "__main__":
    cli = ClienteDivulgacao("simulado")
    print(cli.config_eleicoes())                       # confirmar ciclo, pleito e eleições
    pres_br = cli.resultado(21270, "br", 1)            # Presidente, Brasil
    sen_rio = cli.resultado(21272, "rj", 5, 60011)     # Senador, Rio de Janeiro (código TSE)
    # No ambiente oficial: ClienteDivulgacao("oficial"), eleições 6257 (federal) e 6259 (estaduais).
```

## A7 — Recomendações e ressalvas

**Referência no documento inicial:** seções "Recommendations" (itens 1 a 5) e "Caveats".

Três itens condicionais do documento inicial já se resolveram: as especificações EA de 2026 saíram, não houve lei nova sobre sobras até 5/03/2026, e os limites de acesso foram confirmados.

**Recommendations**

| Item original | Marca | Nova redação |
| --- | --- | --- |
| 1 — Pares de resoluções | ATUALIZADO | Incluir 23.767/2026 (atos gerais), 23.769/2026 (auditoria), 23.771/2026 (calendário) e 23.759/2026 (eleitor). Ver A2 |
| 2 — Duas variantes de quociente | ATUALIZADO | Variante "pós-STF" = art. 12-A em duas fases; vagas por UF de 2022 (ADO 38). Ver A4 |
| 3 — Pipeline de dados abertos | Mantido | Vale também para os datasets de 2026 já publicados. Ver A6 (A) |
| 4 — "Participe do simulado de setembro" | EXCLUÍDO | Simulados já realizados (15/09 a 29/09) |
| 4 — "Use as specs EA de 2024 até a publicação das de 2026" | EXCLUÍDO | Specs de 2026 publicadas: EA10 (26/03), Instruções v1.0 (25/05), EA11/EA20 (23/06), além de EA12, EA14, EA15, EA16, EA18 e manual JWS |
| 4 — Limite de 100 req/IP/s "de 2024" | ATUALIZADO | Confirmado para 2026, com bloqueio de 10 min reiniciável. Ver A6 (B) |
| 5 — "Se o TSE publicar specs divergentes, refaça o parser" | ATUALIZADO | Modelo "bastante semelhante" a 2024, mas com ajustes: revisar o parser contra a documentação de 2026 |
| 5 — "Se houver lei nova sobre sobras até 5/03" | EXCLUÍDO | Não houve; a regra foi positivada na Res. 23.748/2026 |
| — | INCLUÍDO | Gravar snapshots próprios na noite da eleição: arquivos parciais são sobrescritos e a destinação de votos muda depois (A3, A5) |

**Caveats**

- **\[EXCLUÍDO\]** "As URLs exatas de resultados.tse.jus.br para 2026 ainda serão divulgadas." Já foram, para o 1º turno.
- **\[EXCLUÍDO\]** "Rate limits citados referem-se a 2024." Confirmados para 2026.
- **\[ATUALIZADO\]** "As Eleições 2026 ainda não ocorreram": continua válido em 29/09/2026, a cinco dias do 1º turno. Normas pós-março já foram editadas (A2).
- **\[Mantido\]** DataStore do CKAN não testado ao vivo.
- **\[INCLUÍDO\]** Os códigos de eleição do 2º turno (25/10) ainda não estão na página técnica; ler do `ele-c.json`.
- **\[INCLUÍDO\]** O esquema de URLs de A6 foi inferido dos exemplos do simulado. Códigos de cargo além de 0001, 0003 e 0005 não foram confirmados.
- **\[INCLUÍDO\]** O arquivo "Instruções para download" de 2026 retornou HTTP 410 no acesso desta verificação; os demais documentos EA não foram abertos um a um.
- **\[INCLUÍDO\]** O item (iii) de Details §2 foi excluído por não constar do texto consolidado consultado. Se houver outra fonte, reincluir com a referência.

## Fontes consultadas (29/09/2026)

Páginas oficiais abertas nesta verificação:

- [TSE — Informações técnicas sobre a divulgação de resultados 2026](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados) (abas Informações, Simulados, FAQ, Documentos)
- [TSE — Eleições 2026: TSE fará simulados com veículos de imprensa (06/07/2026, atualizada 14/07)](https://www.tse.jus.br/comunicacao/noticias/2026/Julho/tse-fara-simulados-com-veiculos-de-imprensa-para-testar-divulgacao-dos-resultados-das-eleicoes-2026)
- [TSE — CDE 2026 (números do pleito, vagas, novidades)](https://www.tse.jus.br/eleicoes/cde-2026)
- [TSE — Resoluções de 2026 (legislação compilada)](https://www.tse.jus.br/legislacao/compilada/res/2026)
- [Res.-TSE nº 23.748/2026 (texto consolidado)](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-748-de-26-de-fevereiro-de-2026)
- [Res.-TSE nº 23.767/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-767-de-3-de-agosto-de-2026)
- [Res.-TSE nº 23.769/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-769-de-3-de-agosto-de-2026)

Consultadas por resultado de busca (sem abrir a página inteira):

- [Res.-TSE nº 23.751/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-751-de-26-de-fevereiro-de-2026) e [Res.-TSE nº 23.760/2026](https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-760-de-2-de-marco-de-2026)
- [Portal de Dados Abertos — Candidatos 2026](https://dadosabertos.tse.jus.br/dataset/candidatos-2026), [Eleitorado 2026](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026), [Prestação de Contas 2026](https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais-2026)
- [STF — Supremo mantém número de deputados federais para 2026](https://noticias.stf.jus.br/postsnoticias/supremo-mantem-numero-de-deputados-federais-para-2026/)
- [Câmara — Lula veta projeto que aumenta de 513 para 531 deputados](https://www.camara.leg.br/noticias/1181279-lula-veta-projeto-que-aumenta-de-513-para-531-o-numero-de-deputados-federais/)
- [Câmara — Deputados são eleitos pelo voto proporcional (27/08/2026)](https://www.camara.leg.br/noticias/1300504-deputados-sao-eleitos-pelo-voto-proporcional-entenda-a-logica-desse-sistema)
- [TRE-SP — Quociente eleitoral e partidário (06/2026)](https://www.tre-sp.jus.br/comunicacao/noticias/2026/Junho/quociente-eleitoral-e-partidario-explica-por-que-o-mais-votado-pode-nao-ser-eleito)
