# Geoprocessamento de Resultados Eleitorais Brasileiros (TSE + IBGE) com Python

> Documento de referência consolidando as respostas dadas neste chat sobre
> ferramentas, formatos, fontes de dados e pipelines para mapear resultados
> eleitorais do TSE em diferentes granularidades geográficas do IBGE — do
> setor censitário ao estado.

---

## 1. Ferramentas Python para mapas eleitorais

| Biblioteca | Para que serve | Observações |
|---|---|---|
| **GeoPandas** | Leitura de shapefile/GeoJSON/GeoPackage, join com dados tabulares, plot coroplético básico | `gdf.plot(column='votos_pct', legend=True)` |
| **`geobr`** | Baixa direto em Python as malhas do IBGE (estados, municípios, regiões, setores censitários, distritos) já como `GeoDataFrame` | `pip install geobr`; evita baixar shapefile manualmente |
| **Matplotlib / Contextily** | Renderização estática + basemap (tiles OSM/Stamen) | `contextily` adiciona mapa de fundo tipo Google Maps |
| **Plotly** (`choropleth_mapbox` / `px.choropleth`) | Mapas interativos, zoom, hover por município/bairro | Aceita GeoJSON diretamente |
| **Folium** (wrapper do Leaflet.js) | Mapas interativos em HTML, bom para muitos polígonos | `folium.Choropleth()` |
| **Bokeh** | Alternativa interativa com mais controle de callbacks | Menos comum que Folium/Plotly |
| **PySAL / `mapclassify`** | Classificação estatística (quantis, Fisher-Jenks) para colorir faixas | Combina com GeoPandas |
| **Kepler.gl** (`keplergl` pacote Python) | Visualização de grandes volumes (nível seção eleitoral) | Bom para o Brasil inteiro em nível de seção |
| **DataShader** | Renderização por agregação quando o volume é muito grande | Evita travar com centenas de milhares de pontos |

Fluxo típico:
```
malha geográfica (shapefile/GeoJSON/GeoPackage do IBGE)
        +
dados de votação (CSV do TSE, agregados por município/zona/seção)
        =  merge por código IBGE / código do TSE (⚠️ não são o mesmo código!)
        →  GeoPandas / Plotly / Folium para plotar
```

## 2. Formatos de arquivo geoespacial

| Formato | Extensão | Prós/contras |
|---|---|---|
| **Shapefile** | `.shp` + `.shx` + `.dbf` + `.prj` | Formato tradicional do IBGE; limite de 10 caracteres em nomes de campo |
| **GeoJSON** | `.geojson` | Leve, texto puro, ótimo para web (Plotly/Folium); pesado em escala Brasil-setor-censitário |
| **GeoPackage** | `.gpkg` | Formato moderno (SQLite), um único arquivo, sem limite de nome de campo |
| **TopoJSON** | `.topojson` | Comprime geometrias compartilhando topologia — mapas web leves |
| **KML/KMZ** | `.kml`/`.kmz` | Google Earth; não ideal para análise |

Todos lidos nativamente por `geopandas.read_file()`.

## 3. Onde baixar malhas geográficas do Brasil (fontes livres)

- **IBGE — Malhas Territoriais**: `ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html` — municípios, regiões geográficas imediatas/intermediárias, UF, país, em Shapefile.
- **IBGE — Malha de Setores Censitários**: `ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/26565-malhas-de-setores-censitarios-divisoes-intramunicipais.html` — a menor unidade oficial nacional.
- **Pacote `geobr`**: espelha as malhas do IBGE em GeoDataFrame pronto (hospedado em GitHub Releases); é o caminho mais simples em Python.
- **TSE — Portal de Dados Abertos**: `dadosabertos.tse.jus.br` (API CKAN) — dados de votação, não geometria.
- **Geoaplicada** (`geoaplicada.com/dados`) — shapefiles do IBGE redistribuídos, organizados por estado.
- **Forest-GIS** — agregador de links de shapefiles brasileiros.
- **OpenStreetMap** — limites de bairro "populares" que não existem oficialmente no IBGE (via Overpass API/Geofabrik).
- **Base dos Dados** (`basedosdados.org`) — datasets eleitorais do TSE já tratados, via BigQuery/Python.

**Observação sobre granularidade:** o Brasil não tem um "bairro" oficial padronizado nacionalmente — bairro é definido por lei municipal. Abaixo do município, os caminhos livres são: (1) setor censitário do IBGE, (2) geoportal da prefeitura específica, (3) OpenStreetMap.

## 4. O que é um mapa coroplético

Mapa temático em que áreas (países, estados, municípios, setores censitários) são coloridas conforme o valor de uma variável — quanto mais intensa a cor, maior o valor. Do grego *choros* (lugar) + *plethos* (quantidade). Exemplo usado neste chat: cada município do RJ colorido pelo percentual de votos de um candidato sobre os votos válidos.

## 5. Pipeline nível Município — TSE + geobr

**Fontes usadas:**
- `votacao_candidato_munzona_<ano>.zip` (CDN do TSE) — votos por candidato/município/zona.
- `detalhe_votacao_munzona_<ano>.zip` (CDN do TSE) — totais de votos válidos por município/cargo.
- Tabela de correspondência **TSE ↔ IBGE** (comunidade, GitHub): `raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/master/municipios_brasileiros_tse.csv` — colunas `codigo_tse`, `uf`, `nome_municipio`, `codigo_ibge`. **Testada e validada**: bate 92/92 com os municípios do RJ retornados pelo `geobr`.
- `geobr.read_municipality(code_muni="RJ", year=2022)` — malha de municípios.

**Armadilha crítica (testada e confirmada):** o `CD_MUNICIPIO` do TSE **não é** o código IBGE de 7 dígitos — é preciso a tabela de-para acima para o merge funcionar. Outra pegadinha real encontrada em teste: `geobr` devolve `code_muni` como `float64` (ex.: `3300100.0`), não como texto — é preciso `.astype(int)` (ou `Int64` anulável na tabela de-para, para tolerar municípios sem correspondência) antes do merge.

```python
"""
Mapa coroplético — % de votos do candidato 13713 (Deputado Estadual)
sobre os votos válidos, por município do Rio de Janeiro — Eleições 2022
"""

import io
import zipfile
import requests
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

ANO = 2022
UF = "RJ"
CARGO_ALVO = "Deputado Estadual"
NUMERO_CANDIDATO = "13713"
TURNO = 1

CDN_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_VOTACAO_CANDIDATO = f"{CDN_BASE}/votacao_candidato_munzona/votacao_candidato_munzona_{ANO}.zip"
URL_DETALHE_APURACAO = f"{CDN_BASE}/detalhe_votacao_munzona/detalhe_votacao_munzona_{ANO}.zip"
URL_DEPARA_TSE_IBGE = (
    "https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE"
    "/master/municipios_brasileiros_tse.csv"
)
HEADERS = {"User-Agent": "estudo-eleitoral-python/1.0"}


def carregar_csv_zip_tse(url: str, uf: str, usecols=None, chunksize: int = 300_000) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, timeout=300)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    nome_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
    partes = []
    with zf.open(nome_csv) as f:
        leitor = pd.read_csv(f, sep=";", encoding="latin-1", usecols=usecols,
                              dtype=str, chunksize=chunksize)
        for chunk in leitor:
            partes.append(chunk[chunk["SG_UF"] == uf])
    return pd.concat(partes, ignore_index=True)


def votos_do_candidato() -> pd.DataFrame:
    cols = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_TURNO",
            "DS_CARGO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "QT_VOTOS_NOMINAIS"]
    df = carregar_csv_zip_tse(URL_VOTACAO_CANDIDATO, UF, usecols=cols)
    df["QT_VOTOS_NOMINAIS"] = pd.to_numeric(df["QT_VOTOS_NOMINAIS"], errors="coerce").fillna(0)
    df["NR_TURNO"] = df["NR_TURNO"].astype(str)
    filtro = ((df["NR_TURNO"] == str(TURNO)) &
              (df["DS_CARGO"].str.upper() == CARGO_ALVO.upper()) &
              (df["NR_CANDIDATO"] == NUMERO_CANDIDATO))
    cand = df.loc[filtro]
    return (cand.groupby(["CD_MUNICIPIO", "NM_MUNICIPIO"], as_index=False)["QT_VOTOS_NOMINAIS"]
            .sum().rename(columns={"QT_VOTOS_NOMINAIS": "votos_candidato"}))


def votos_validos_por_municipio() -> pd.DataFrame:
    cols = ["SG_UF", "CD_MUNICIPIO", "NR_TURNO", "DS_CARGO",
            "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA_VALIDOS"]
    df = carregar_csv_zip_tse(URL_DETALHE_APURACAO, UF, usecols=cols)
    for c in ["QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA_VALIDOS"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["NR_TURNO"] = df["NR_TURNO"].astype(str)
    filtro = (df["NR_TURNO"] == str(TURNO)) & (df["DS_CARGO"].str.upper() == CARGO_ALVO.upper())
    det = df.loc[filtro].copy()
    det["votos_validos"] = det["QT_VOTOS_NOMINAIS_VALIDOS"] + det["QT_VOTOS_LEGENDA_VALIDOS"]
    return det.groupby("CD_MUNICIPIO", as_index=False)["votos_validos"].sum()


def carregar_depara_tse_ibge() -> pd.DataFrame:
    depara = pd.read_csv(URL_DEPARA_TSE_IBGE, dtype=str)
    depara = depara.rename(columns={"codigo_tse": "CD_MUNICIPIO", "codigo_ibge": "code_muni"})
    depara["code_muni"] = depara["code_muni"].astype("Int64")  # inteiro anulável
    return depara[["CD_MUNICIPIO", "code_muni", "uf"]]


def carregar_malha_rj() -> gpd.GeoDataFrame:
    import geobr
    gdf = geobr.read_municipality(code_muni="RJ", year=2022)
    gdf["code_muni"] = gdf["code_muni"].astype(int)  # geobr devolve float64
    return gdf


def main():
    votos_cand = votos_do_candidato()
    votos_val = votos_validos_por_municipio()
    depara = carregar_depara_tse_ibge()

    base = votos_cand.merge(votos_val, on="CD_MUNICIPIO", how="left")
    base["votos_validos"] = base["votos_validos"].fillna(0)
    base = base.merge(depara, on="CD_MUNICIPIO", how="left")
    base["pct_13713"] = (base["votos_candidato"] / base["votos_validos"].replace(0, pd.NA)) * 100

    gdf = carregar_malha_rj().merge(base, on="code_muni", how="left")

    fig, ax = plt.subplots(1, 1, figsize=(10, 12))
    gdf.plot(column="pct_13713", cmap="YlOrRd", linewidth=0.3, edgecolor="grey",
              legend=True, legend_kwds={"label": "% de votos válidos", "orientation": "horizontal"},
              missing_kwds={"color": "lightgrey", "label": "Sem dado"}, ax=ax)
    ax.set_title(f"Votação do candidato {NUMERO_CANDIDATO} (RJ, {ANO}, {TURNO}º turno)")
    ax.axis("off")
    plt.savefig(f"mapa_candidato_{NUMERO_CANDIDATO}_rj_{ANO}.png", dpi=200, bbox_inches="tight")


if __name__ == "__main__":
    main()
```

*(Este pipeline foi validado neste chat: a tabela de-para e a malha do `geobr` foram efetivamente baixadas e o merge resultou em 92/92 municípios do RJ casados sem nulos; o download real do TSE não pôde ser testado no sandbox por restrição de rede — `cdn.tse.jus.br` não está liberado nesse ambiente.)*

## 6. Relacionando CEP a dados do IBGE

CEP **não é uma unidade geográfica do IBGE** — é um código logístico dos Correios (ECT), que nem sempre respeita limites de setor censitário, bairro oficial ou até município. Três estratégias, por nível de precisão:

### 6.1 CEP → Município (rápido, gratuito)

**ViaCEP:**
```python
import requests

def cep_para_municipio_viacep(cep: str) -> dict:
    cep = cep.replace("-", "").strip()
    r = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("erro"):
        return None
    return {
        "cep": cep, "municipio": data["localidade"], "uf": data["uf"],
        "bairro": data.get("bairro"), "codigo_ibge": data.get("ibge"),
    }
```

**BrasilAPI** (agrega várias fontes, com fallback automático):
```python
r = requests.get("https://brasilapi.com.br/api/cep/v2/20040020", timeout=10)
```

Limitação: o `bairro` retornado é o bairro "postal" dos Correios, sem correspondência com nenhuma malha oficial do IBGE.

### 6.2 CEP → Setor Censitário (via CNEFE)

O **CNEFE — Cadastro Nacional de Endereços para Fins Estatísticos** (Censo 2022) é o único cadastro nacional, gratuito e oficial que traz **CEP, logradouro, número, setor censitário e coordenadas na mesma linha**.

```python
import pandas as pd

cols = ["COD_MUNICIPIO", "COD_SETOR", "CEP", "LATITUDE", "LONGITUDE"]
cnefe_rj = pd.read_csv("cnefe_rj.csv", sep=";", encoding="latin-1", usecols=cols, dtype=str)

cep_para_setor = (
    cnefe_rj.groupby("CEP")["COD_SETOR"]
    .agg(lambda x: x.value_counts().idxmax())  # setor mais frequente daquele CEP
    .reset_index()
)
```

**Por que "moda" e não valor único?** Um CEP pode abranger mais de um setor censitário — a relação CEP→setor não é estritamente 1:1.

**Alerta importante confirmado via documentação do IBGE:** o próprio IBGE reconhece que só municípios de **"CEP único"** tiveram o campo CEP totalmente verificado no CNEFE; em cidades de **"CEP por logradouro"** (a maioria das cidades médias/grandes) o CEP pode não estar padronizado. Por isso, casar **apenas por CEP** é a estratégia menos confiável — melhor usar CEP + logradouro + número (ver seção 7).

### 6.3 CEP → coordenadas → *spatial join* com a malha do IBGE

```python
import geopandas as gpd
from shapely.geometry import Point

locais = gpd.GeoDataFrame(
    df_locais,
    geometry=[Point(lon, lat) for lon, lat in zip(df_locais.lon, df_locais.lat)],
    crs="EPSG:4326",
)
setores = gpd.read_file("setores_censitarios_rj.shp").to_crs("EPSG:4326")
locais_com_setor = gpd.sjoin(locais, setores, how="left", predicate="within")
```

Método mais preciso e flexível (funciona para qualquer malha), mas depende de coordenadas confiáveis — geocodificar via Nominatim/OSM (gratuito, rate limit ~1 req/s) ou usar as coordenadas que já vêm no próprio CNEFE.

### 6.4 Resumo de decisão

| Precisão necessária | Caminho |
|---|---|
| Só município | ViaCEP/BrasilAPI — campo `ibge` direto |
| Setor censitário | CNEFE — já traz CEP + setor + coordenadas juntos |
| Bairro, zona eleitoral, malha customizada | Geocodificar → `geopandas.sjoin` |

## 7. Pipeline nível Setor Censitário — casamento CEP + logradouro + número via CNEFE

Esta é a granularidade **máxima** disponível gratuitamente no Brasil. Fontes confirmadas por download real neste chat:

- **CNEFE completo por UF** (todos os atributos): `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/<código>_<UF>.zip` (ex.: `33_RJ.zip`).
- **CNEFE agregado por CEP** (produto pronto do IBGE, sem precisar processar 106,8 milhões de endereços): pasta `Agregados_por_CEP/` no mesmo diretório.
- **CNEFE por município, versão mais leve** (coordenadas): `.../Coordenadas_enderecos/Municipio/<UF_num>_<UF_sigla>/<código_ibge>.zip` (ex.: `51_MT/5100102.zip`) — confirmado via listagem real do FTP.
- Colunas confirmadas do CNEFE completo: `COD_UNICO_ENDERECO`, `COD_UF`, `COD_MUNICIPIO`, `COD_DISTRITO`, `COD_SUBDISTRITO`, `COD_SETOR`, `NUM_QUADRA`, `NUM_FACE`, `CEP`, `DSC_LOCALIDADE`, `NOM_TIPO_SEGLOGR`, `NOM_TITULO_SEGLOGR`, `NOM_SEGLOGR`, `NUM_ENDERECO`, `DSC_MODIFICADOR`, `LATITUDE`, `LONGITUDE`, `COD_ESPECIE`, `DSC_ESTABELECIMENTO`.
- `geobr.read_census_tract(code_tract=<código_ibge_município>, year=2022)` — malha de setores censitários; coluna de merge é `code_tract` (também `float64`, mesmo cuidado de conversão do item 5).

**Estratégia de casamento em 3 camadas** (testada com dados sintéticos neste chat — os 4 cenários possíveis se comportaram corretamente):

| Camada | Critério | Confiabilidade |
|---|---|---|
| A — exato | CEP + logradouro normalizado + número | Alta |
| B — por logradouro | CEP + logradouro normalizado (número não bateu) | Boa |
| C — por CEP | Só CEP, setor mais frequente | Baixa em cidades "CEP por logradouro" |

```python
"""
Mapa coroplético por SETOR CENSITÁRIO — casamento CEP + logradouro + número
com o CNEFE (Censo 2022).
"""

import io
import re
import zipfile
import unicodedata
import requests
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

ANO_CENSO = 2022
UF_NUM = "33"
UF_SIGLA = "RJ"

ARQUIVO_LOCAIS = "locais_votacao.csv"
COL_CEP, COL_LOGRADOURO, COL_NUMERO = "CEP", "DS_ENDERECO", "NR_LOCAL"
COL_MUNICIPIO_IBGE, COL_VOTOS = "CD_MUNICIPIO_IBGE", "votos_candidato"

URL_CNEFE_UF = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos"
    f"/Censo_Demografico_{ANO_CENSO}/Arquivos_CNEFE/CSV/UF/{UF_NUM}_{UF_SIGLA}.zip"
)
HEADERS = {"User-Agent": "estudo-eleitoral-python/1.0"}

ABREVIACOES = {
    r"\bR\.?\b": "RUA", r"\bAV\.?\b": "AVENIDA", r"\bTRAV\.?\b": "TRAVESSA",
    r"\bAL\.?\b": "ALAMEDA", r"\bPC\.?\b": "PRACA", r"\bPCA\.?\b": "PRACA",
    r"\bEST\.?\b": "ESTRADA", r"\bROD\.?\b": "RODOVIA", r"\bPROF\.?\b": "PROFESSOR",
    r"\bGAL\.?\b": "GENERAL", r"\bDR\.?\b": "DOUTOR", r"\bSTA\.?\b": "SANTA", r"\bSTO\.?\b": "SANTO",
}


def normalizar_endereco(txt) -> str:
    if pd.isna(txt):
        return ""
    txt = str(txt).upper().strip()
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    for padrao, troca in ABREVIACOES.items():
        txt = re.sub(padrao, troca, txt)
    txt = re.sub(r"[^A-Z0-9 ]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def normalizar_cep(cep) -> str:
    return "" if pd.isna(cep) else re.sub(r"\D", "", str(cep)).zfill(8)


def normalizar_numero(num) -> str:
    if pd.isna(num):
        return ""
    m = re.search(r"\d+", str(num))
    return m.group(0) if m else ""


def carregar_locais_votacao() -> pd.DataFrame:
    df = pd.read_csv(ARQUIVO_LOCAIS, sep=";", encoding="utf-8", dtype=str)
    df["cep_norm"] = df[COL_CEP].apply(normalizar_cep)
    df["logradouro_norm"] = df[COL_LOGRADOURO].apply(normalizar_endereco)
    df["numero_norm"] = df[COL_NUMERO].apply(normalizar_numero)
    df[COL_VOTOS] = pd.to_numeric(df[COL_VOTOS], errors="coerce").fillna(0)
    return df


def carregar_cnefe(municipios_ibge: set, chunksize: int = 500_000) -> pd.DataFrame:
    resp = requests.get(URL_CNEFE_UF, headers=HEADERS, timeout=600, stream=True)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    nome_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
    cols = ["COD_MUNICIPIO", "COD_SETOR", "CEP", "NOM_TIPO_SEGLOGR",
            "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO"]
    partes = []
    with zf.open(nome_csv) as f:
        leitor = pd.read_csv(f, sep=",", encoding="utf-8", usecols=cols, dtype=str, chunksize=chunksize)
        for chunk in leitor:
            partes.append(chunk[chunk["COD_MUNICIPIO"].isin(municipios_ibge)])
    cnefe = pd.concat(partes, ignore_index=True)
    cnefe["logradouro_completo"] = (cnefe["NOM_TIPO_SEGLOGR"].fillna("") + " " +
                                     cnefe["NOM_TITULO_SEGLOGR"].fillna("") + " " +
                                     cnefe["NOM_SEGLOGR"].fillna(""))
    cnefe["logradouro_norm"] = cnefe["logradouro_completo"].apply(normalizar_endereco)
    cnefe["cep_norm"] = cnefe["CEP"].apply(normalizar_cep)
    cnefe["numero_norm"] = cnefe["NUM_ENDERECO"].apply(normalizar_numero)
    return cnefe


def moda(serie: pd.Series):
    return None if serie.empty else serie.value_counts().idxmax()


def casar_com_setor(locais: pd.DataFrame, cnefe: pd.DataFrame) -> pd.DataFrame:
    idx_cep_log_num = cnefe.groupby(["cep_norm", "logradouro_norm", "numero_norm"])["COD_SETOR"]
    idx_cep_log = cnefe.groupby(["cep_norm", "logradouro_norm"])["COD_SETOR"]
    idx_cep = cnefe.groupby("cep_norm")["COD_SETOR"]

    resultado = []
    for _, local in locais.iterrows():
        chave = (local["cep_norm"], local["logradouro_norm"], local["numero_norm"])
        setor, qualidade = None, "sem_match"
        if chave in idx_cep_log_num.groups:
            setor = moda(cnefe.loc[idx_cep_log_num.groups[chave], "COD_SETOR"])
            qualidade = "exato"
        else:
            chave_b = (local["cep_norm"], local["logradouro_norm"])
            if chave_b in idx_cep_log.groups:
                setor = moda(cnefe.loc[idx_cep_log.groups[chave_b], "COD_SETOR"])
                qualidade = "por_logradouro"
            elif local["cep_norm"] in idx_cep.groups:
                setor = moda(cnefe.loc[idx_cep.groups[local["cep_norm"]], "COD_SETOR"])
                qualidade = "por_cep"
        resultado.append({**local.to_dict(), "COD_SETOR": setor, "qualidade_match": qualidade})
    return pd.DataFrame(resultado)


def carregar_malha_setores(municipios_ibge: set) -> gpd.GeoDataFrame:
    import geobr
    partes = [geobr.read_census_tract(code_tract=int(m), year=ANO_CENSO) for m in municipios_ibge]
    malha = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=partes[0].crs)
    malha["code_tract"] = malha["code_tract"].astype("int64").astype(str)
    return malha


def main():
    locais = carregar_locais_votacao()
    municipios = set(locais[COL_MUNICIPIO_IBGE].dropna().unique())
    cnefe = carregar_cnefe(municipios)
    locais_com_setor = casar_com_setor(locais, cnefe)

    com_setor = locais_com_setor.dropna(subset=["COD_SETOR"])
    votos_por_setor = com_setor.groupby("COD_SETOR", as_index=False)[COL_VOTOS].sum()

    malha = carregar_malha_setores(municipios)
    gdf = malha.merge(votos_por_setor, left_on="code_tract", right_on="COD_SETOR", how="left")
    gdf[COL_VOTOS] = gdf[COL_VOTOS].fillna(0)

    fig, ax = plt.subplots(1, 1, figsize=(10, 12))
    gdf.plot(column=COL_VOTOS, cmap="YlOrRd", linewidth=0.05, edgecolor="grey",
              legend=True, missing_kwds={"color": "lightgrey"}, ax=ax)
    ax.set_title("Votação por Setor Censitário (via CNEFE)")
    ax.axis("off")
    plt.savefig("mapa_votacao_setor_censitario.png", dpi=250, bbox_inches="tight")


if __name__ == "__main__":
    main()
```

*(Testado neste chat com dados sintéticos: as 4 combinações possíveis — exato, por_logradouro, por_cep, sem_match — funcionaram corretamente; a malha real de setores censitários de um município do RJ foi baixada via `geobr` e o merge/plot final rodou sem erros. Download real do CNEFE não pôde ser testado no sandbox — `ftp.ibge.gov.br` não está no allowlist desse ambiente.)*

---

## Glossário técnico

### Geoprocessamento / GIS

| Termo | Definição |
|---|---|
| **Mapa coroplético** | Mapa temático em que áreas são coloridas conforme o valor de uma variável (do grego *choros* = lugar + *plethos* = quantidade). |
| **GeoDataFrame** | Estrutura de dados do GeoPandas — um DataFrame do pandas com uma coluna de geometria, permitindo operações espaciais. |
| **Geometria (geometry)** | Coluna especial de um GeoDataFrame contendo pontos, linhas ou polígonos (via biblioteca `shapely`). |
| **Shapefile (.shp)** | Formato vetorial da ESRI, o mais tradicional em GIS; na prática é um conjunto de 3–4 arquivos (`.shp`, `.shx`, `.dbf`, `.prj`). |
| **GeoJSON** | Formato de geometria vetorial em JSON puro, leve e ideal para web. |
| **GeoPackage (.gpkg)** | Formato moderno baseado em SQLite, arquivo único, sem as limitações de nome de campo do shapefile. |
| **TopoJSON** | Extensão do GeoJSON que compartilha topologia entre polígonos vizinhos, reduzindo o tamanho do arquivo. |
| **KML/KMZ** | Formato do Google Earth para geometria e anotações. |
| **CRS (Coordinate Reference System)** | Sistema de referência de coordenadas — define como coordenadas (lat/lon ou projetadas) se relacionam com posições reais na Terra. Ex.: `EPSG:4326` (WGS84, lat/lon em graus). |
| **EPSG** | Código numérico padronizado que identifica um CRS específico (ex.: EPSG:4326, EPSG:31983). |
| **Geocodificação** | Processo de converter um endereço textual (ou CEP) em coordenadas geográficas (lat/lon). |
| **Spatial join (`sjoin`)** | Operação que combina duas camadas geoespaciais com base em relação espacial (ex.: "ponto está dentro do polígono"), em vez de uma chave comum de tabela. |
| **Point-in-polygon** | Teste geométrico que verifica se um ponto está contido dentro de um polígono — base do spatial join usado para achar em qual setor censitário um endereço cai. |
| **Malha territorial** | Conjunto de polígonos que representam uma divisão administrativa ou estatística do território (municípios, setores censitários, UFs). |
| **`geobr`** | Pacote Python (e R) que baixa malhas territoriais oficiais do IBGE já prontas como GeoDataFrame. |
| **Basemap / tile layer** | Camada de mapa de fundo (ruas, satélite) sobre a qual se sobrepõem os dados — usada por Contextily, Folium, Plotly. |
| **Choropleth Mapbox** | Tipo de mapa coroplético interativo do Plotly que usa tiles do Mapbox/OSM como fundo. |

### Divisão territorial / estatística (IBGE)

| Termo | Definição |
|---|---|
| **Setor Censitário** | Menor unidade territorial do Censo do IBGE — a maior granularidade geográfica oficial e gratuita disponível no Brasil, menor que bairro em áreas urbanas densas. |
| **Distrito / Subdistrito** | Subdivisões administrativas intramunicipais usadas pelo IBGE na hierarquia acima do setor censitário. |
| **`code_muni` / `code_tract`** | Nomes das colunas de código IBGE de município e de setor censitário, respectivamente, nos GeoDataFrames devolvidos pelo `geobr`. Atenção: vêm como `float64`, exigindo conversão para inteiro antes de qualquer merge. |
| **CD_MUNICIPIO (TSE)** | Código de município usado internamente pelo TSE — **diferente** do código IBGE de 7 dígitos; requer tabela de correspondência (de-para) para cruzar com malhas geográficas. |
| **De-para (crosswalk)** | Tabela de correspondência entre dois sistemas de códigos diferentes para o mesmo conjunto de entidades (ex.: município no TSE ↔ município no IBGE). |

### CEP e endereçamento

| Termo | Definição |
|---|---|
| **CEP (Código de Endereçamento Postal)** | Código logístico de propriedade dos Correios (ECT) para roteamento de entregas; **não é** uma unidade geográfica do IBGE e não respeita necessariamente limites administrativos ou estatísticos. |
| **CEP único** | Classificação do IBGE para municípios (geralmente pequenos) em que todo o território tem um único CEP — nesses casos, o campo CEP do CNEFE foi totalmente verificado. |
| **CEP por logradouro** | Classificação para municípios (geralmente médios/grandes) em que cada rua tem seu próprio CEP — nesses casos, o IBGE não garante que o campo CEP do CNEFE esteja atualizado/correto, tornando o CEP isolado uma chave de casamento menos confiável. |
| **CNEFE (Cadastro Nacional de Endereços para Fins Estatísticos)** | Cadastro nacional do IBGE, atualizado a cada Censo, com um registro por endereço contendo logradouro, número, CEP, setor censitário e coordenadas geográficas — a base mais granular e gratuita para ligar endereço a setor censitário. |
| **Logradouro** | Nome de uma via pública (rua, avenida, travessa etc.); no CNEFE é dividido em `NOM_TIPO_SEGLOGR` (tipo: Rua/Av.), `NOM_TITULO_SEGLOGR` (título) e `NOM_SEGLOGR` (nome propriamente dito). |
| **Normalização de endereço** | Processo de padronizar texto de endereço (maiúsculas, sem acento, abreviações expandidas — "R." → "RUA") para permitir comparação/casamento entre bases de origens diferentes. |
| **ViaCEP / BrasilAPI** | APIs públicas e gratuitas que convertem CEP em endereço estruturado, incluindo o código IBGE do município. |

### Eleitoral / TSE

| Termo | Definição |
|---|---|
| **Portal de Dados Abertos do TSE** | Portal (`dadosabertos.tse.jus.br`) baseado em CKAN que disponibiliza os microdados eleitorais para download. |
| **CKAN** | Software de portal de dados abertos (usado pelo TSE) com uma API REST padronizada (`package_list`, `package_show`, `package_search`). |
| **`votacao_candidato_munzona`** | Arquivo do TSE com votos por candidato, agregados por município e zona eleitoral. |
| **`detalhe_votacao_munzona`** | Arquivo do TSE com totais agregados (votos válidos, nulos, brancos) por município/zona/cargo. |
| **Votos válidos** | Soma de votos nominais (no candidato) + votos de legenda (no partido), excluindo brancos e nulos — é o denominador padrão para calcular percentual de votação de um candidato. |
| **Voto nominal** | Voto dado diretamente a um candidato (não ao partido). |
| **Voto de legenda** | Voto dado apenas ao partido/número de partido, sem especificar candidato — típico do sistema proporcional. |

---

## Referências e fontes citadas neste chat

- IBGE — Malhas Territoriais: https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html
- IBGE — Malha de Setores Censitários: https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/26565-malhas-de-setores-censitarios-divisoes-intramunicipais.html
- IBGE — CNEFE (página institucional): https://www.ibge.gov.br/estatisticas/sociais/populacao/38734-cadastro-nacional-de-enderecos-para-fins-estatisticos.html
- IBGE — FTP do CNEFE (Censo 2022): https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/
- TSE — Portal de Dados Abertos: https://dadosabertos.tse.jus.br
- TSE — CDN de arquivos: https://cdn.tse.jus.br/estatistica/sead/odsele
- Tabela de-para TSE ↔ IBGE (comunidade): https://github.com/betafcc/Municipios-Brasileiros-TSE
- `geobr` (pacote Python/R): https://github.com/ipeaGIT/geobr
- ViaCEP: https://viacep.com.br
- BrasilAPI: https://brasilapi.com.br
- Base dos Dados: https://basedosdados.org
- Geoaplicada: https://geoaplicada.com/dados
