"""
Mapa coroplético — % de votos do candidato 13713 (Deputado Estadual)
sobre os votos válidos, por município do Rio de Janeiro — Eleições 2022

Fluxo:
  1) Baixar a malha de municípios do RJ (geobr -> IBGE)
  2) Baixar dados de votação por candidato/município/zona (TSE - dados abertos)
  3) Baixar dados de "detalhe da apuração" por município/zona (TSE) -> votos válidos
  4) Fazer o de-para código TSE <-> código IBGE (as bases usam códigos diferentes!)
  5) Agregar, calcular o percentual e unir com a geometria
  6) Plotar o mapa coroplético

IMPORTANTE:
  Este script precisa de acesso à internet a estes domínios:
    - cdn.tse.jus.br            (dados de votação do TSE)
    - dadosabertos.tse.jus.br   (opcional, para explorar metadados via API CKAN)
    - IBGE (via pacote geobr)
    - raw.githubusercontent.com (tabela de correspondência TSE <-> IBGE)
  Rode-o no seu ambiente local (não dentro de sandboxes com rede restrita).

Requisitos:
    pip install geopandas geobr matplotlib requests pandas
"""

import io
import zipfile
import requests
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# --------------------------------------------------------------------------
# 0) CONFIGURAÇÃO
# --------------------------------------------------------------------------
ANO = 2022
UF = "RJ"
CARGO_ALVO = "Deputado Estadual"     # DS_CARGO usa texto capitalizado no TSE
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


# --------------------------------------------------------------------------
# 1) FUNÇÃO AUXILIAR: baixar um ZIP do TSE e devolver o CSV como DataFrame,
#    já filtrado por UF (os arquivos nacionais são grandes, então filtramos
#    em chunks para não estourar memória)
# --------------------------------------------------------------------------
def carregar_csv_zip_tse(url: str, uf: str, usecols=None, chunksize: int = 300_000) -> pd.DataFrame:
    print(f"Baixando: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=300)
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    # Pega o primeiro .csv dentro do zip (o TSE também inclui um leiame .pdf)
    nome_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
    print(f"  -> arquivo interno: {nome_csv}")

    partes = []
    with zf.open(nome_csv) as f:
        leitor = pd.read_csv(
            f,
            sep=";",
            encoding="latin-1",
            usecols=usecols,
            dtype=str,          # tudo como string por segurança; convertemos depois
            chunksize=chunksize,
        )
        for chunk in leitor:
            partes.append(chunk[chunk["SG_UF"] == uf])

    df = pd.concat(partes, ignore_index=True)
    print(f"  -> {len(df):,} linhas para UF={uf}")
    return df


# --------------------------------------------------------------------------
# 2) VOTOS DO CANDIDATO 13713 POR MUNICÍPIO
# --------------------------------------------------------------------------
def votos_do_candidato() -> pd.DataFrame:
    cols = [
        "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_TURNO",
        "DS_CARGO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "QT_VOTOS_NOMINAIS",
    ]
    df = carregar_csv_zip_tse(URL_VOTACAO_CANDIDATO, UF, usecols=cols)

    df["QT_VOTOS_NOMINAIS"] = pd.to_numeric(df["QT_VOTOS_NOMINAIS"], errors="coerce").fillna(0)
    df["NR_TURNO"] = df["NR_TURNO"].astype(str)

    filtro = (
        (df["NR_TURNO"] == str(TURNO))
        & (df["DS_CARGO"].str.upper() == CARGO_ALVO.upper())
        & (df["NR_CANDIDATO"] == NUMERO_CANDIDATO)
    )
    cand = df.loc[filtro]

    if cand.empty:
        # ajuda de diagnóstico: mostra cargos e nº de candidato disponíveis
        print("ATENÇÃO: nenhuma linha encontrada para o candidato/cargo informados.")
        print("Cargos disponíveis:", df["DS_CARGO"].unique()[:20])
        raise SystemExit(1)

    agregado = (
        cand.groupby(["CD_MUNICIPIO", "NM_MUNICIPIO"], as_index=False)["QT_VOTOS_NOMINAIS"]
        .sum()
        .rename(columns={"QT_VOTOS_NOMINAIS": "votos_candidato"})
    )
    return agregado


# --------------------------------------------------------------------------
# 3) TOTAL DE VOTOS VÁLIDOS (nominais + de legenda) POR MUNICÍPIO,
#    para o cargo de Deputado Estadual — vem do arquivo "detalhe da apuração"
# --------------------------------------------------------------------------
def votos_validos_por_municipio() -> pd.DataFrame:
    cols = [
        "SG_UF", "CD_MUNICIPIO", "NR_TURNO", "DS_CARGO",
        "QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA_VALIDOS",
    ]
    df = carregar_csv_zip_tse(URL_DETALHE_APURACAO, UF, usecols=cols)

    for c in ["QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_LEGENDA_VALIDOS"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["NR_TURNO"] = df["NR_TURNO"].astype(str)

    filtro = (df["NR_TURNO"] == str(TURNO)) & (df["DS_CARGO"].str.upper() == CARGO_ALVO.upper())
    det = df.loc[filtro].copy()
    det["votos_validos"] = det["QT_VOTOS_NOMINAIS_VALIDOS"] + det["QT_VOTOS_LEGENDA_VALIDOS"]

    agregado = det.groupby("CD_MUNICIPIO", as_index=False)["votos_validos"].sum()
    return agregado


# --------------------------------------------------------------------------
# 4) TABELA DE-PARA: código de município TSE <-> código IBGE (7 dígitos)
# --------------------------------------------------------------------------
def carregar_depara_tse_ibge() -> pd.DataFrame:
    print(f"Baixando tabela de correspondência TSE <-> IBGE: {URL_DEPARA_TSE_IBGE}")
    depara = pd.read_csv(URL_DEPARA_TSE_IBGE, dtype=str)
    depara = depara.rename(columns={"codigo_tse": "CD_MUNICIPIO", "codigo_ibge": "code_muni"})
    depara["code_muni"] = depara["code_muni"].astype("Int64")  # inteiro anulável (evita erro em merges com NaN)
    return depara[["CD_MUNICIPIO", "code_muni", "uf"]]


# --------------------------------------------------------------------------
# 5) MALHA GEOGRÁFICA DOS MUNICÍPIOS DO RJ (geobr -> IBGE)
# --------------------------------------------------------------------------
def carregar_malha_rj() -> gpd.GeoDataFrame:
    import geobr
    print("Baixando malha de municípios do RJ (geobr)...")
    gdf = geobr.read_municipality(code_muni="RJ", year=2022)
    # geobr devolve code_muni como float64 (ex.: 3300100.0) -> padroniza como inteiro
    gdf["code_muni"] = gdf["code_muni"].astype(int)
    return gdf


# --------------------------------------------------------------------------
# 6) PIPELINE PRINCIPAL
# --------------------------------------------------------------------------
def main():
    votos_cand = votos_do_candidato()
    votos_val = votos_validos_por_municipio()
    depara = carregar_depara_tse_ibge()

    # une votos do candidato + votos válidos pelo código do TSE
    base = votos_cand.merge(votos_val, on="CD_MUNICIPIO", how="left")
    base["votos_validos"] = base["votos_validos"].fillna(0)

    # traduz código TSE -> código IBGE
    base = base.merge(depara, on="CD_MUNICIPIO", how="left")
    if base["code_muni"].isna().any():
        faltantes = base.loc[base["code_muni"].isna(), "NM_MUNICIPIO"].tolist()
        print(f"Aviso: {len(faltantes)} município(s) sem correspondência IBGE: {faltantes}")

    # calcula o percentual (evita divisão por zero)
    base["pct_13713"] = (base["votos_candidato"] / base["votos_validos"].replace(0, pd.NA)) * 100

    # une com a geometria
    malha = carregar_malha_rj()
    gdf = malha.merge(base, on="code_muni", how="left")

    # --------------------------------------------------------------------
    # 7) PLOT COROPLÉTICO
    # --------------------------------------------------------------------
    fig, ax = plt.subplots(1, 1, figsize=(10, 12))

    gdf.plot(
        column="pct_13713",
        cmap="YlOrRd",
        linewidth=0.3,
        edgecolor="grey",
        legend=True,
        legend_kwds={
            "label": f"% de votos válidos para o candidato {NUMERO_CANDIDATO}",
            "orientation": "horizontal",
            "shrink": 0.6,
        },
        missing_kwds={"color": "lightgrey", "label": "Sem dado"},
        ax=ax,
    )

    ax.set_title(
        f"Votação do candidato {NUMERO_CANDIDATO} a Deputado Estadual (RJ, {ANO}, {TURNO}º turno)\n"
        f"% sobre os votos válidos, por município",
        fontsize=13,
    )
    ax.axis("off")

    saida = f"mapa_candidato_{NUMERO_CANDIDATO}_rj_{ANO}.png"
    plt.savefig(saida, dpi=200, bbox_inches="tight")
    print(f"Mapa salvo em: {saida}")

    # também salva a tabela usada, para conferência
    tabela_saida = f"tabela_candidato_{NUMERO_CANDIDATO}_rj_{ANO}.csv"
    base.sort_values("pct_13713", ascending=False).to_csv(tabela_saida, index=False)
    print(f"Tabela salva em: {tabela_saida}")

    plt.show()


if __name__ == "__main__":
    main()
