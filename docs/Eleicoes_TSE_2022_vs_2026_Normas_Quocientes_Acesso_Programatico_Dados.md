# Comparativo TSE 2022 × 2026: Captação, Totalização, Quocientes, Divulgação e Acesso Programático aos Dados

## TL;DR
- As Eleições 2026 (1º turno em 4/out; 2º em 25/out) mantêm a mesma arquitetura normativa e tecnológica de 2022, mas com renumeração das resoluções: a Res.-TSE nº 23.669/2021 (atos gerais/captação) é substituída pela Res.-TSE nº 23.751/2026, e a Res.-TSE nº 23.677/2021 (sistemas/totalização) foi atualizada e republicada como Res.-TSE nº 23.748/2026.
- No cálculo proporcional (deputados federais e estaduais), a mudança estrutural entre 2022 e 2026 não veio de nova lei, mas do STF: a "regra 80/20" da Lei 14.211/2021 para as "sobras das sobras" foi declarada inconstitucional em 28/02/2024 (ADIs 7228, 7263 e 7325, por 7 votos a 4) e, em 13/03/2025, passou a valer inclusive retroativamente para 2022 — de modo que 2026 será a primeira eleição geral planejada já sob a regra de que todos os partidos participam da última fase de sobras.
- O acesso programático permanece dual e estável: dados históricos/consolidados via Portal de Dados Abertos (CKAN 2.9.3, com download dos ZIP/CSV hospedados em cdn.tse.jus.br), e resultados em tempo real via arquivos JSON em resultados.tse.jus.br; o modelo de dados JSON de 2026 "permanece bastante semelhante" ao de 2024.

## Key Findings

**1. Datas e cargos.** 2022: 1º turno em 2/out, 2º em 30/out. 2026: 1º turno em 4/out, 2º em 25/out (datas fixadas pela Constituição — 1º e último domingos de outubro). Ambas elegem presidente, governador, senador, deputado federal, estadual e distrital. Diferença: em 2022 elegeu-se 1 vaga de senador por estado; em 2026 são 2 vagas de senador.\[1\]

**2. Captação de votos.** Regidas por resoluções de "atos gerais": Res.-TSE nº 23.669/2021 (2022) e Res.-TSE nº 23.751/2026 (2026). Estrutura idêntica (votação das 8h às 17h horário de Brasília, urna eletrônica exclusiva, zerésima, boletim de urna). Novidades 2026: programa "Seu Voto Importa" (transporte gratuito); incorporação normativa do Teste de Integridade com Biometria à Res. 23.673/2021 (via Res. 23.758/2026); regulamentação do uso de IA na propaganda.

**3. Totalização.** Res.-TSE nº 23.677/2021 (2022), atualizada pela Res.-TSE nº 23.748/2026. Sistemas SISTOT/JE-Connect, transmissão a partir dos cartórios/TREs, BUs públicos em tempo real (inovação consolidada em 2022). Novidade 2026: previsão de recálculo imediato da composição da Câmara pelo TSE em caso de reprocessamento e regras sobre desfiliação.

**4. Quociente eleitoral e partidário.** Base legal inalterada: Código Eleitoral arts. 106-109 e Lei 9.504/97, com cláusula de barreira individual de 10% do QE (art. 108) e regra 80/20 para sobras (art. 109). A grande diferença 2022→2026 é jurisprudencial: a exigência de 80% do QE na última fase das sobras caiu (STF, ADI 7228 e conexas), valendo para 2026.

**5. Acesso a dados.** Portal de Dados Abertos (CKAN) para dados consolidados + resultados.tse.jus.br (JSON) para tempo real. Testes práticos em Python via requests/ckanapi/pandas.

## Details

### 1. Normatização da captação dos votos: 2022 × 2026

**2022 — Res.-TSE nº 23.669, de 14/12/2021** ("Dispõe sobre os atos gerais do processo eleitoral para as Eleições 2022"). O art. 1º abrange atos preparatórios, fluxo de votação, apuração, totalização, diplomação. Art. 2º fixou 2/out (1º turno) e 30/out (2º turno). Art. 4º: uso exclusivo de sistemas do TSE e da urna eletrônica. A votação inicia às 8h e encerra às 17h (horário de Brasília, uniformizado nacionalmente). O presidente da mesa emite a zerésima antes do início e o Boletim de Urna (BU) ao final. A resolução sofreu ajustes: em março de 2022 o art. 230 foi alterado para antecipar a disponibilização dos BUs (antes em até 3 dias após o fim da totalização; passaram a ficar acessíveis ao longo de todo o recebimento dos dados). Resoluções correlatas de 2022: 23.673/2021 (fiscalização e auditoria), 23.674/2021 (calendário), 23.677/2021 (sistemas/totalização), 23.670/2021 (federações).

**2026 — Res.-TSE nº 23.751, de 26/02/2026 (publicada em 4/03/2026)** ("atos gerais do processo eleitoral para as Eleições 2026", Instrução nº 0600281-87.2026.6.00.0000).\[2\] Aprovada junto com as demais 14 resoluções (sessões de 26/02 e 02/03/2026,\[2\] relator ministro Nunes Marques; publicação em edição extra do DJE nº 30 de 04/03/2026,\[2\] cumprindo o prazo do art. 105 da Lei 9.504/97 que exige publicação até 5/mar do ano eleitoral).\[2\] Mantém a mesma sistemática de votação (art. 142 trata da ordem de votação na urna). A votação da urna mostra nome, foto, cargo e sigla do partido.

**Novidades introduzidas em 2026 (captação/segurança):**
- **Programa "Seu Voto Importa" (Res. 23.753/2026):** transporte individual gratuito no dia do pleito para eleitores com deficiência/mobilidade reduzida, indígenas, quilombolas e comunidades tradicionais; solicitação até 20 dias antes, confirmação até 48h antes.
- **Teste de Integridade com Biometria (Res. 23.758/2026, que altera a Res. 23.673/2021):** incorporação definitiva do teste ao texto da norma (antes vinha de alteração pela Res. 23.722/2023). O teste com biometria é realizado em local próximo ao de votação, com eleitores voluntários que consentem no uso da biometria para habilitar a urna. Passou a exigir acessibilidade dos locais e divulgação imediata e detalhada na internet da relação de urnas auditadas. O Teste de Integridade "clássico" (ambiente controlado, cédulas preenchidas digitadas na urna, previsto no §6º do art. 66 da Lei 9.504/97) existe desde 2002; em 2022 foram ampliadas de 100 para 641 as urnas testadas — desse total, 58 urnas, em 19 estados e no DF, foram testadas no projeto-piloto com biometria.
- **Uso de IA na propaganda (Res. 23.755/2026, altera a Res. 23.610/2019):** proibição de conteúdo sintético (deepfakes) sem rotulagem, vedação à violência política contra a mulher.

**Urnas eletrônicas.** Em 2022 estrearam as urnas modelo UE2020 (224.999 unidades entregues pela Positivo Tecnologia em 22/07/2022; das ~577 mil urnas usadas no país em 2022, 224.999 foram do modelo mais atual, correspondendo a 21,6% de todas as 1.042.118 urnas fabricadas desde 1996), com bateria de lítio-ferro-fosfato,\[3\] tela sensível ao toque para o mesário,\[4\] intérprete de Libras na tela\[5\] e capacidade de processamento ~18× maior.\[4\] Para 2026 estarão em uso quatro gerações — UE2013, UE2015, UE2020 e UE2022 — todas testadas em simulados (amostra de 6% para UE2013 e 2,5% para os demais).\[6\] A UE2022 (219.998 unidades, fabricadas a partir de maio de 2023 e estreadas em 2024, com algoritmo criptográfico E521/EdDSA) é tecnicamente igual à UE2020,\[3\] com reforço de segurança criptográfica.\[4\] Uma nova geração de urna está em consulta pública (Edital TSE nº 1/2026) apenas para 2028\[7\] — logo, 2026 não terá novo modelo de hardware.

### 2. Normatização da totalização dos votos: 2022 × 2026

**2022 — Res.-TSE nº 23.677, de 16/12/2021** ("Dispõe sobre os sistemas eleitorais, a destinação dos votos na totalização, a proclamação dos resultados, a diplomação e as ações decorrentes do processo eleitoral nas eleições gerais e municipais").\[8\] Principais pontos: totalização gerenciada pelo SISTOT; transmissão pela rede JE-Connect a partir dos cartórios/TREs; votos válidos = os dados a chapas deferidas ou sub judice (registro não indeferido/cancelado); votos nulos = chapas com registro indeferido, cancelado, não conhecido, cassado ou irregular entre o fechamento do CAND e o dia da eleição. O TSE totaliza e divulga presidente; os TREs, os demais cargos.\[9\] Novidade de 2022: uniformização do horário de início/fim da votação pelo horário de Brasília em todo o país.

**2026 — Res.-TSE nº 23.748, de 26/02/2026 (publicada em 4/03/2026)** (Instrução nº 0600592-54.2021.6.00.0000; atualiza a Res. 23.677/2021). Mudanças: (i) em caso de vaga sem suplente, haverá eleição, salvo se faltarem menos de 15 meses para o fim do mandato no Senado e na Câmara; (ii) o reprocessamento do resultado passa a ser antecedido de verificação de desfiliação partidária (validação/cancelamento de diplomas — Acórdão TutCautAnt 0613340-16.2024.6.00.0000, incluído pela Res. 23.748/2026); (iii) havendo reprocessamento que altere a composição da Câmara dos Deputados, os TREs devem comunicar imediatamente o TSE para recálculo. A arquitetura de totalização (SISTOT, BU, transmissão) permanece a mesma.

### 3. Quociente eleitoral e partidário — deputados federais e estaduais

**Base legal (comum a 2022 e 2026):**
- **Quociente Eleitoral (QE):** votos válidos ÷ vagas em disputa,\[10\] desprezando fração ≤ 0,5 e arredondando para cima se > 0,5 (Código Eleitoral art. 106; arts. 8º-9º da Res. 23.677/2021). Votos válidos excluem brancos e nulos. Exemplo real: em São Paulo, nas Municipais de 2024, 5.781.049 votos válidos para vereador ÷ 55 cadeiras = 105.109,98, arredondado para QE = 105.110.
- **Quociente Partidário (QP):** votos do partido/federação ÷ QE, desprezada a fração (art. 107). Define quantas cadeiras a legenda ocupa diretamente.
- **Cláusula de desempenho individual (art. 108, redação da Lei 14.211/2021):** só ocupa a vaga pelo QP o candidato com votos ≥ 10% do QE.\[11\]
- **Sobras (art. 109):** distribuídas pela maior média (votos do partido ÷ (cadeiras obtidas + 1)).
- **Federações partidárias (Lei 14.208/2021; Res. 23.670/2021):** contam como um único partido nos cálculos (art. 10 da Res. 23.677/2021); somam votos e permanecem unidas por no mínimo 4 anos. Vigoram desde 2022.
- **Fim das coligações proporcionais (EC 97/2017):** aplicado a deputados desde 2022; coligações só valem para cargos majoritários. A EC 97/2017 também trouxe cláusula de desempenho progressiva (em 2022: 2% dos votos válidos e 11 deputados federais eleitos, para acesso a fundo partidário e tempo de TV).
- **EC 111/2021:** contagem em dobro dos votos de mulheres e negros à Câmara (2022-2030) para distribuição de fundos; fidelidade partidária; mudança das datas de posse (governadores para 6/jan; presidente para 5/jan).
- **Número de candidatos por legenda:** reduzido pela Lei 14.211/2021 para 100% das vagas + 1 (antes 150%/200%).

**A diferença central entre 2022 e 2026 (jurisprudencial, não legislativa):**
A "regra 80/20" da Lei 14.211/2021 exigia, para participar da distribuição das sobras, que o partido/federação tivesse ≥ 80% do QE e candidatos com ≥ 20% do QE.\[12\] O STF, ao julgar a **ADI 7228 (Rede Sustentabilidade), a ADI 7263 (PSB) e a ADI 7325 (PP), com julgamento concluído em 28/02/2024 por 7 votos a 4**, declarou inconstitucional a exigência de 80% na **última fase** ("sobras das sobras") — permitindo que todos os partidos participem\[13\] — e derrubou o art. 111 do Código Eleitoral (que previa que, caso nenhum partido alcançasse o QE, as vagas seriam preenchidas pelos candidatos mais votados) e o art. 13 da Res. 23.677/2021. Inicialmente a Corte modulou a decisão para valer a partir de 2024, sem afetar 2022 (aplicando o princípio da anualidade do art. 16 da CF). Contudo, **em 13/03/2025 (embargos de declaração nas ADIs 7228 e 7263 pelo Podemos e PSB; acórdão publicado em 14/05/2025), o STF decidiu, por maioria, que o entendimento vale a partir das eleições de 2022** — provocando a perda de mandato de **sete deputados federais**, substituídos por: Prof. Goreth (PDT-AP), Silvia Waiãpi (PL-AP), Sonize Barbosa (PL-AP), Dr. Pupio (MDB-AP), Gilvan Máximo (Republicanos-DF), Lebrão (União-RO) e Lázaro Botelho (PP-TO).

> **\[CORRIGIDO em 30/09/2026 — rodada 20\]** A frase acima inverte quem saiu e quem entrou. Os sete nomes listados são os que **perderam** o mandato. Nos microdados oficiais do TSE (`votacao_candidato_munzona_2022`, regerado em 30/09/2026, já com o recálculo), todos constam como SUPLENTE ou NÃO ELEITO. Os que **entraram**, todos "ELEITO POR MÉDIA" na fase final das sobras, aberta a todos os partidos, foram:
> - Professora Marcivania (PC do B-AP);
> - Aline Gurgel (Republicanos-AP);
> - Paulo Lemos (PSOL-AP);
> - André Abdon (PP-AP);
> - Rodrigo Rollemberg (PSB-DF);
> - Rafael Fera (Podemos-RO);
> - Tiago Dimas (Podemos-TO).
>
> O cálculo de `apuracao/cadeiras.py` reproduz exatamente esse resultado; ver `RODADA_20_2026-09-30_cadeiras_de_deputado.md`. Portanto, **2026 será a primeira eleição geral já planejada sob a regra de que todos os partidos participam da última fase de sobras**, enquanto o pleito de 2022 foi realizado sob a regra 80/20 e depois recalculado.

Observação para o cientista de dados: ao comparar 2022 e 2026, os resultados oficiais de 2022 originalmente divulgados refletem a regra 80/20; os dados pós-recálculo (2025) refletem a nova regra. Convém verificar a data de extração dos microdados.

### 4. Disponibilização dos resultados (1º e 2º turnos): 2022 × 2026

**2022.** Divulgação a partir das 17h (horário de Brasília) do dia do pleito, em tempo real, por múltiplos canais: site **Divulga** (detalhado), site e app **Resultados** (resumido), **Portal de Dados Abertos** e **Sistema de Estatísticas Eleitorais (SEE)**. Inovação de 2022: a disponibilização dos registros das mais de 472 mil urnas ocorreu ainda no próprio domingo (2/out), praticamente em tempo real, à medida que os dados chegavam ao TSE para totalização (BU, RDV e Log de Urna por seção). App **Boletim na Mão**: leitura do QR Code do BU para conferência. O TSE divulga presidente; TREs, demais cargos.

**2026.** Mesmo modelo: divulgação a partir das 17h, site e app **Resultados** (resultados.tse.jus.br), com resultados de novo por arquivos JSON.\[14\] As entidades interessadas devem seguir os arts. 264-269 da Res. 23.751/2026.\[15\] Cronograma: audiência técnica realizada em 6/07/2026; testes simulados previstos para setembro/2026; o "modelo de dados para 2026 permanece bastante semelhante ao modelo de dados de 2024".\[14\] Diplomação até 18/12/2026.\[1\]

**Formatos e prazos de dados abertos.** Os microdados consolidados (resultados por seção, BUs, candidatos, logs) começam a ser publicados no Portal de Dados Abertos em até 5 dias após o pleito.\[16\] Em 2024, os dados de divulgação em tempo real ficaram disponíveis no data center do TSE de 6 a 19/out (1º turno) e 27/out a 8/nov (2º turno).\[15\]

### 5. Acesso programático aos dados do TSE — guia prático (Python)

Há **dois sistemas distintos**, com propósitos diferentes:

#### (A) Portal de Dados Abertos — dados consolidados (CKAN 2.9.3)
- URL: https://dadosabertos.tse.jus.br — substituiu o antigo Repositório de Dados Eleitorais (RDE), descontinuado em janeiro de 2022.
- API CKAN Action, versão 3: `https://dadosabertos.tse.jus.br/api/3/action/<ação>`.
- Ações úteis: `package_list` (lista todos os slugs de datasets), `package_show?id=<slug>` (metadados + lista de `resources` com URLs de download), `package_search` (busca), `organization_list`.
- Resposta JSON padrão CKAN com chaves `help`, `success` (boolean) e `result`. Sempre checar `success` além do HTTP 200.
- **Importante:** os arquivos (ZIP/CSV) **não** ficam no CKAN — os `resources[].url` apontam para a CDN **cdn.tse.jus.br** (ex.: `https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2022.zip`). O DataStore (`datastore_search`) **não** está populado para os dados eleitorais do TSE — a estratégia correta é `package_show` → ler `resources[].url` → baixar o ZIP da CDN. (As páginas de recurso exibem "Não há visões criadas para este recurso ainda", confirmando ausência de preview/DataStore.)
- Organização gestora: **TSE/AGEL** (Assessoria de Gestão Eleitoral); fonte "Sistemas: CAND, Candex e DivulgaCand"; licença **Creative Commons Atribuição (CC-BY)**; atualização diária.
- Slugs relevantes de 2022: `candidatos-2022`, `resultados-2022` (inclui votação por seção eleitoral, votação nominal/partido por município e zona, detalhe da apuração, histórico de totalização Presidente), `resultados-2022-boletim-de-urna`, `eleitorado-2022`, `prestacao-de-contas-eleitorais-2022`. Padrão análogo para outros anos (`candidatos-2024`, `resultados-2024`, etc.). Etiquetas no portal já incluem "Ano 2026".
- Padrões de arquivo na CDN: candidatos = `consulta_cand_<ano>.zip`; votação por seção = `votacao_secao_<ano>_<UF>.zip` e `..._BR.zip` (o arquivo BR contém a zona ZZ do exterior e o cargo de presidente; os arquivos por UF trazem governador, senador, deputado federal e estadual); votação nominal por município/zona = `votacao_candidato_munzona_<ano>.zip`; BU web = `bweb_1t_<UF>_<timestamp>.zip` / `bweb_2t_...`, com `.sha512` de verificação; fotos = `foto_cand2022_<UF>_div.zip`. Formatos: CSV, PDF, JPEG, .sha512.
- Alerta operacional do próprio TSE: arquivos CSV/TXT muito grandes podem exceder o limite de 1.048.576 linhas do Excel; usar ferramentas apropriadas (pandas, DuckDB).\[17\]

**Exemplo Python (requests) — listar datasets e baixar um recurso:**
```python
import requests, io, zipfile
import pandas as pd

BASE = "https://dadosabertos.tse.jus.br/api/3/action"

# 1) Listar datasets
r = requests.get(f"{BASE}/package_list", timeout=60,
                 headers={"User-Agent": "pesquisa-eleitoral/1.0"})
r.raise_for_status()
pkgs = r.json()
assert pkgs["success"] is True
print(len(pkgs["result"]), "datasets")

# 2) Metadados e recursos de um dataset
meta = requests.get(f"{BASE}/package_show",
                    params={"id": "resultados-2022"}, timeout=60).json()
assert meta["success"]
for res in meta["result"]["resources"]:
    print(res["format"], res["name"], res["url"])

# 3) Baixar um ZIP da CDN e ler o CSV com pandas
url = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2022_AC.zip"
z = zipfile.ZipFile(io.BytesIO(requests.get(url, timeout=300).content))
nome_csv = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
df = pd.read_csv(z.open(nome_csv), sep=";", encoding="latin-1")
print(df.shape)
```

**Exemplo com ckanapi:**
```python
from ckanapi import RemoteCKAN
tse = RemoteCKAN("https://dadosabertos.tse.jus.br", user_agent="pesquisa/1.0")
slugs = tse.action.package_list()
pkg = tse.action.package_show(id="candidatos-2022")
urls = [r["url"] for r in pkg["resources"]]
```
Boas práticas: usar `User-Agent` identificável (o servidor pode bloquear clientes automatizados anônimos); validar hashes `.sha512`; tratar `success:false`/`error`; paginar em `package_search` com `rows`/`start`; separador `;` e encoding `latin-1` (ISO-8859-1) nos CSV do TSE.

#### (B) resultados.tse.jus.br — resultados em tempo real (JSON)
Estrutura conhecida (usada por desenvolvedores em 2022):
- Configuração geral: `https://resultados.tse.jus.br/oficial/comum/config/ele-c.json` — retorna o identificador do ciclo (`"c":"ele2022"`) e a lista de pleitos (`pl`), com códigos como 544 (Federal 1º turno), 546 (Estadual 1º turno), 548 (Municipal).\[18\] Os códigos de eleição (ex.: 544/545 federal 1º/2º turno; 546/547 estadual) são a chave para montar as demais URLs.
- Dados simplificados: `https://resultados.tse.jus.br/oficial/ele2022/<cod>/dados-simplificados/<uf>/<uf>-c<mun>-e<cod>-r.json`.
- Configuração de municípios: `https://resultados.tse.jus.br/oficial/ele2022/544/config/mun-e000544-cm.json`. \[19\]
- Arquivos de urna (bu, imgbu, rdv, logjez, vscmr): sob `https://resultados.tse.jus.br/oficial/ele2022/arquivo-urna/406/dados/<uf>/<mun>/<zona>/<secao>/...`. \[19\]
- Especificações oficiais dos JSON: página "arquivos" do TSE (EA10 resultado de eleitos, configuração de eleições/municípios/seções,\[20\] EA20 resultado unificado — este último criado em 2024, substituindo os arquivos EA01/EA02/EA04, que deixaram de ser gerados).

Para 2024 (referência para 2026), o ambiente oficial teve limites: **máximo de 100 requisições por IP por segundo**, sob pena de bloqueio de 10 minutos;\[16\] múltiplos erros 404 também bloqueiam o IP.\[15\] A CDN suporta ETag/Last-Modified (HTTP 304 para arquivos não alterados, mas contam para o rate limit).\[14\] Ambiente de simulado usa host separado (ex.: `resultados-sim.tse.jus.br`). Para 2026 as URLs exatas serão divulgadas oportunamente; recomenda-se usar as especificações de 2024 como base.

**Exemplo Python — resultados em tempo real (histórico 2022):**
```python
import requests
cfg = requests.get("https://resultados.tse.jus.br/oficial/comum/config/ele-c.json",
                   timeout=30, headers={"User-Agent": "pesquisa/1.0"}).json()
print(cfg["c"])  # 'ele2022'
for pleito in cfg["pl"]:
    print(pleito.get("cd"), pleito.get("dt"))  # código e data do pleito
```
Boas práticas para tempo real: respeitar o polling recomendado (não ultrapassar o rate limit), usar requisições condicionais (If-None-Match/ETag), construir URLs corretas para evitar 404, e preferir os arquivos `dados-simplificados` para acompanhamento leve.

## Recommendations

1. **Para replicar a comparação normativa:** trabalhe com o par de resoluções por tema — captação: 23.669/2021 vs 23.751/2026; sistemas/totalização: 23.677/2021 vs 23.748/2026; auditoria/biometria: 23.673/2021 vs 23.758/2026; calendário: 23.674/2021 vs 23.760/2026; propaganda/IA: 23.610/2019 vs 23.755/2026; registro de candidaturas: 23.609/2019 vs 23.754/2026. Baixe as íntegras do DJE edição extra nº 30 de 04/03/2026.
2. **Para os quocientes:** implemente o cálculo em duas variantes — "regra 80/20" (estado original de 2022) e "pós-STF" (todos os partidos nas sobras; válida para 2024, 2026 e retroativa a 2022). Use os microdados de `votacao_candidato_munzona` e `detalhe_votacao_munzona`. Sinalize a data de extração porque os resultados de 2022 foram recalculados em 2025 (perda de 7 mandatos federais).
3. **Para o pipeline de dados abertos:** priorize `package_show` → `resources[].url` → download da CDN cdn.tse.jus.br; não dependa de `datastore_search` para dados eleitorais do TSE; valide `.sha512`; leia CSV com `sep=";"`, `encoding="latin-1"`; envie `User-Agent` identificável.
4. **Para tempo real em 2026:** acompanhe a página "Informações técnicas sobre a divulgação de resultados"; participe do simulado de setembro/2026; implemente ETag/HTTP 304 e respeite o limite de 100 req/IP/s (parâmetro de 2024); use as specs EA de 2024 como base até a publicação das de 2026.
5. **Benchmarks que mudam a decisão:** se o TSE publicar novas especificações EA para 2026 divergentes de 2024, refaça o parser; se houver nova lei/EC alterando sobras ou cláusula de barreira antes de 5/mar/2026 (prazo do art. 105), revise o cálculo; se surgir novo modelo de urna, isso só afetará 2028.

## Caveats
- As Eleições 2026 ainda não ocorreram; toda análise de 2026 baseia-se em resoluções e planejamentos oficiais já publicados (fev-mar/2026) e pode ser ajustada por resoluções complementares ou decisões do STF até outubro/2026.
- As URLs exatas de resultados.tse.jus.br para 2026 e as especificações técnicas finais ainda serão divulgadas; o texto usa o ciclo 2024 como referência declarada pelo próprio TSE.
- A conclusão de que o DataStore não está populado para dados eleitorais é inferência forte (baseada em "Não há visões criadas para este recurso ainda" e no uso de URLs externas à CDN), não testada ao vivo; convém validar com uma chamada `datastore_search` real.
- Números de resolução de 2026 aparecem com datas de 26/02 ou 04/03/2026 conforme a fonte (aprovação vs. publicação); todas foram publicadas no DJE extra de 04/03/2026.
- Rate limits e regras operacionais citados (100 req/IP/s) referem-se a 2024; podem ser alterados para 2026.

## Sources

1. [Confira as principais datas do calendário eleitoral — Tribunal Regional Eleitoral do Paraná](https://www.tre-pr.jus.br/comunicacao/noticias/2026/Junho/confira-as-principais-datas-do-calendario-eleitoral)
2. [Eleições 2026: TSE publica todas as resoluções que orientarão o pleito](https://www.tse.jus.br/comunicacao/noticias/2026/Marco/eleicoes-2026-tse-publica-todas-as-resolucoes-que-orientarao-o-pleito)
3. [Detalhes técnicos das urnas eletrônicas 2020 e 2022](https://www.justicaeleitoral.jus.br/urna-eletronica/detalhes-tecnicos-da-urna.html)
4. [Urna eletrônica chega aos 30 anos garantindo segurança e transparência para o processo de votação — Tribunal Regional Eleitoral do Paraná](https://www.tre-pr.jus.br/comunicacao/noticias/2026/Maio/urna-eletronica-chega-aos-30-anos-garantindo-seguranca-e-transparencia-para-o-processo-de-votacao)
5. [Confira as principais novidades da nova urna eletrônica para as Eleições 2022 — Tribunal Superior Eleitoral](https://www.tse.jus.br/comunicacao/noticias/2021/Dezembro/confira-as-principais-mudancas-do-novo-modelo-de-urna-eletronica-a-ser-utilizado-nas-eleicoes-2022)
6. [Urnas eletrônicas estão sendo testadas para as eleições 2026 — Tribunal Regional Eleitoral do Maranhão](https://www.tre-ma.jus.br/comunicacao/noticias/2025/Outubro/urnas-eletronicas-estao-sendo-testadas-para-as-eleicoes-2026)
7. [TSE abre consulta pública para definir modelo da nova urna eletrônica das Eleições de 2028 - Jornal Cidade RC](https://www.jornalcidade.net/rc/tse-abre-consulta-publica-para-definir-modelo-da-nova-urna-eletronica-das-eleicoes-de-2028/291302/)
8. [Manual de Legislação Eleitoral e Partidária - Eleições 2022 — Tribunal Regional Eleitoral do Ceará](https://www.tre-ce.jus.br/eleicao/eleicoes-2022/manual-de-legislacao-eleitoral-e-partidaria-eleicoes-2022)
9. [Divulgação dos resultados das eleições — Tribunal Superior Eleitoral](https://www.tse.jus.br/eleicoes/historia/processo-eleitoral-brasileiro/divulgacao-de-resultados/divulgacao-dos-resultados-das-eleicoes)
10. [Supremo invalida regra sobre distribuição de sobras eleitorais em eleições proporcionais](https://portal.stf.jus.br/noticias/verNoticiaDetalhe.asp?idConteudo=528283&ori=1)
11. [Entenda a regra das sobras eleitorais julgada pelo Supremo Tribunal Federal | Jusbrasil](https://www.jusbrasil.com.br/artigos/entenda-a-regra-das-sobras-eleitorais-julgada-pelo-supremo-tribunal-federal/2230056774)
12. [Entenda: STF volta a analisar ação sobre distribuição de sobras eleitorais](https://portal.stf.jus.br/noticias/verNoticiaDetalhe.asp?idConteudo=527541&ori=1)
13. [Regra de divisão das sobras eleitorais vale para eleições de 2022](https://www.conjur.com.br/2025-mar-13/regra-de-divisao-das-sobras-eleitorais-vale-para-eleicoes-de-2022-diz-stf/)
14. [Informações técnicas sobre a divulgação de resultados 2026 — Tribunal Superior Eleitoral](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)
15. [Informações técnicas sobre a divulgação de resultados - 2024 — Tribunal Superior Eleitoral](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados-2024)
16. [TRE-MT reforça orientações técnicas sobre divulgação de resultados das Eleições Municipais de 2024 — Tribunal Regional Eleitoral de Mato Grosso](https://www.tre-mt.jus.br/comunicacao/noticias/2024/Outubro/tre-mt-reforca-orientacoes-tecnicas-sobre-divulgacao-de-resultados-das-eleicoes-municipais-de-2024)
17. [Resultados - 2022 - Conjunto de dados - Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br/dataset/resultados-2022)
18. [urnas-br/README.md at main · doccaz/urnas-br](https://github.com/doccaz/urnas-br/blob/main/README.md)
19. [Eleicao2022/README.md at master · clzanella/Eleicao2022](https://github.com/clzanella/Eleicao2022/blob/master/Documentacao/README.md)
20. [arquivos — Tribunal Superior Eleitoral](https://www.tse.jus.br/eleicoes/arquivos)
