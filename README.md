# Apuração eleitoral 2026 (RJ)

Suíte para acompanhar a apuração das eleições de 2026 sobre os dados abertos do TSE:
coleta em tempo real da divulgação de resultados, site local (painel, candidato, mapas por município,
bairro e local de votação, comparação com 2022, Perfil × voto, transferência de votos entre turnos),
projeção do resultado final e das cadeiras de deputado, boletins para a equipe, alertas, cópia de
segurança, vigia de processo e um portal com os sites no ar. Também ingere os microdados do TSE
(eleitorado, votação por seção) e gera planilhas por candidato.

Feito e ensaiado para o **Rio de Janeiro**; quase tudo aceita outra UF com `--uf` (ver
`docs/TODO.md`, item 18). Não é um produto oficial do TSE: os números vêm da divulgação pública do
TSE e dos microdados publicados depois do pleito.

## Requisitos

- **Linux ou WSL2** (testado no Ubuntu 24.04 sob WSL2);
- **Python 3.12** com o módulo `venv` (no Ubuntu: `sudo apt install python3.12 python3.12-venv`);
- **git**;
- acesso à internet para `resultados.tse.jus.br`, `cdn.tse.jus.br` e `servicodados.ibge.gov.br` / `geoftp.ibge.gov.br`;
- **espaço em disco**:
  - poucos MB para a noite da apuração;
  - **vários GB** se for usar os microdados (mapas por bairro e por local, Perfil × voto, comparação com 2022), que ficam em `cache_tse/`;
- **Google Chrome** (opcional): para `--abrir` e para os testes de navegador.

## Instalação (passo a passo)

```bash
# 1. clonar
git clone https://github.com/lgp-almeida/apuracao_eleitoral.git
cd apuracao_eleitoral

# 2. criar e ativar o ambiente virtual (venv)
python3.12 -m venv venv
source venv/bin/activate

# 3. instalar os pacotes Python
pip install --upgrade pip
pip install -r requirements.txt
#    (ou, para a instalação idêntica à testada, com todas as dependências indiretas:)
#    pip install -r requirements-lock.txt

# 4. conferir: testes offline (sem navegador) — devem passar todos
pytest -q -m "not e2e"
```

Em cada terminal novo, ative o venv antes de qualquer comando: `source venv/bin/activate`.

## Pacotes Python necessários

As versões estão **fixadas** em `requirements.txt`. Foram as que passaram nos testes e no ensaio
geral; o lock completo está em `requirements-lock.txt`.

| Pacote | Versão | Para quê |
|---|---|---|
| polars | 1.44.2 | leitura e cálculo sobre os dados do TSE (Parquet, CSV) |
| numpy | 2.5.1 | estatística (projeção, Perfil × voto, transferência entre turnos) |
| requests | 2.34.2 | downloads do TSE e do IBGE |
| urllib3 | 2.8.0 | via requests (2.7.0 tinha CVEs) |
| xlsxwriter | 3.2.9 | planilhas (boletim, eleitos projetados, planilha por candidato) |
| fastapi | 0.142.1 | API do site |
| uvicorn | 0.54.0 | servidor HTTP do site e do portal |
| geopandas | 1.1.4 | malhas do IBGE (bairros, setores), exportação de mapas |
| shapely | 2.1.2 | geometria (local de votação → bairro/setor) |
| pandas | 3.0.3 | via geopandas |
| matplotlib | 3.11.1 | mapas exportados em PNG/SVG/JPEG |
| pytest | 9.1.1 | testes |
| openpyxl | 3.1.5 | testes das planilhas |
| httpx | 0.28.1 | testes da API (TestClient) |
| playwright | 1.63.0 | testes de navegador (usa o Chrome instalado; não baixa navegador) |
| geobr | 2.1.1 | só o script legado `mapa_votacao_13713_rj.py` |

## Subir o serviço

### 1. Teste rápido, com o ambiente simulado do TSE

```bash
source venv/bin/activate
python site_apuracao.py --ambiente simulado --coletar
# abra http://localhost:8000  (Ctrl+C encerra)
```

`--coletar` roda o coletor junto, numa thread: a cada 60 s ele busca no TSE só o que mudou.
O site se atualiza sozinho. Os dados ficam em `dados_2026/simulado/`.

### 2. Preparação (uma vez, antes da eleição)

```bash
# resultado de 2022 no mesmo formato, para a aba Comparação (baixa os microdados de 2022: centenas de MB)
python importar_resultado_historico.py --ano 2022 --uf RJ --turno 1 2

# ensaio geral: a apuração real de 2022 refeita 30× mais rápido, com coletor, site e usuários (~15 min)
python ensaio_apuracao.py            # deve terminar em "RESULTADO DO ENSAIO: OK"

# prontidão: dependências, cache, hora, TSE, porta, diretório (véspera e dia da eleição)
python verificar_prontidao.py [--testes]
```

### 3. Noite da eleição (ambiente oficial)

```bash
source venv/bin/activate

# site + coletor, sob o vigia (reinicia se cair ou travar), com cópia de segurança em OUTRO disco
python vigiar_site.py -- python site_apuracao.py --ambiente oficial --coletar --abrir \
    --copia-dir /mnt/d/apuracao_copias/oficial

# (opcional, outro terminal) portal com os links de todos os sites no ar
python portal.py                     # http://localhost:8100
```

- **Site:** http://localhost:8000. **Na TV da sala:** http://localhost:8000/#painel?tv=1 (um cargo por vez; clique uma vez na página para a tela cheia).
- **Boletim para a equipe:** gravado sozinho a cada hora cheia e no fim, em `dados_2026/oficial/boletins/boletim_ultimo.html` e `.xlsx`.
- **Alertas** (coleta parada, bloqueio do TSE, apuração parada, mudança na projeção, deputados acompanhados): aparecem no site, com som, e no terminal.
- **Cópia de segurança:**
  - as parciais do TSE (`raw/`) a cada 5 min;
  - um instantâneo do resto por hora e no fim, em `--copia-dir` (use outro disco).
- **Para ver de outro computador:** não é recomendado (o site não tem senha nem HTTPS). Mande o boletim.
- **2º turno:** os mesmos comandos com `--turno 2`. Os dados vão para `dados_2026/oficial_t2`.
- **Encerrar:** Ctrl+C no terminal do vigia (encerra o site junto).

O passo a passo completo da noite — horários, o que fazer se o TSE bloquear, cair a rede ou o
processo, como restaurar a cópia e analisar as parciais depois — está em
[`docs/ROTEIRO_NOITE_DA_ELEICAO.md`](docs/ROTEIRO_NOITE_DA_ELEICAO.md).

### 4. Resultados de eleições passadas (só o site, sem coleta)

```bash
python site_apuracao.py --dados dados_2026/historico_2022_t1 --porta 8022
python site_apuracao.py --dados dados_2026/historico_2022_t2 --turno 2 --porta 8023
```

## Outros comandos úteis

```bash
python coletar_resultados.py --ambiente oficial --uma-vez          # um ciclo de coleta, sem site
python gerar_boletim.py --ambiente oficial [--vigiar]               # boletim agora (ou a cada hora e no fim)
python copiar_dados.py --dados dados_2026/oficial --destino <outro disco>/oficial [--vigiar]
python preparar_2026.py --vigiar                                    # baixa os microdados de 2026 quando o TSE publicar
python transferencia_turnos.py --ano 2022 --cargo presidente --nivel secao --saida saidas/t.xlsx
python planilha_candidato.py --ano 2022 --uf RJ --cargo "deputado estadual" --candidato 13713
python ingerir_eleitorado.py --ano 2026 --uf RJ --relatorio-geo
```

Cada script aceita `--help`.

## Testes

```bash
pytest -q                    # todos (offline; os de navegador usam o Chrome instalado e são pulados sem ele)
pytest -q -m "not e2e"       # sem os testes de navegador
```

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `*.py` (raiz) | linhas de comando (site, coletor, boletim, cópia, vigia, portal, ensaio, prontidão, importação, análises) e testes (`test_*.py`, `conftest.py`) |
| `votos_por_local_votacao.py` | núcleo de leitura dos microdados do TSE (download com cache, conversão para Parquet) |
| `apuracao/` | o pacote: `divulgacao/` (cliente, parse e coletor do tempo real), `web/` (API e página), cadeiras, projeção, boletim, alertas, mapas, Perfil × voto, transferência… |
| `docs/` | referência (normas, formato dos JSON do TSE, geoprocessamento) e o registro das rodadas de desenvolvimento — comece por [`docs/INDEX.md`](docs/INDEX.md); propostas em [`docs/TODO.md`](docs/TODO.md) |
| `tests/` | recortes reais dos JSON do TSE usados pelos testes |

Criadas na execução e fora do repositório (`.gitignore`): `venv/`, `cache_tse/` (downloads e
Parquet), `dados_2026/` (dados coletados, boletins, alertas, vigia), `saidas/` e `copias/`.

## Fontes

- **TSE:** divulgação de resultados (`resultados.tse.jus.br`) e dados abertos (`cdn.tse.jus.br`: votação por seção, eleitorado, candidatos, perfil do eleitorado).
- **IBGE:** malhas municipais, de bairros e de setores censitários, e agregados do Censo 2022.

O coletor respeita o limite de acessos do TSE (20 requisições/s, cache com ETag, pausa automática se bloqueado).
