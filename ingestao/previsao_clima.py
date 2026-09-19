"""Previsão meteorológica para os polos de geração eólica e solar.

Dois provedores, mesma tabela de saída (curated/clima_previsao_horaria_emissoes, uma partição por
data de emissão, para que previsões antigas possam ser comparadas com o observado depois):

  open-meteo   (padrão, funciona já) API pública da Open-Meteo, modelos numéricos (ECMWF/GFS/ICON "best
               match"), 16 dias, horário. Uso não comercial gratuito; atribuição: Open-Meteo.com.
  weathernext  Google DeepMind WeatherNext 3 via BigQuery. Exige conta Google na lista de acesso
               (formulário em developers.google.com/weathernext) e credenciais do Google Cloud
               (GOOGLE_APPLICATION_CREDENTIALS ou `gcloud auth application-default login`).
               Configure WEATHERNEXT_TABELA (ex.: projeto.conjunto.tabela, conforme o guia de acesso)
               e rode `python ingestao/previsao_clima.py --provedor weathernext --esquema` para ver as
               colunas antes da primeira carga.

Pontos: células de 0,25° das usinas eólicas e solares (analytics_usina_geo.cel_lat/cel_lon).

Uso: python ingestao/previsao_clima.py [--provedor open-meteo|weathernext] [--esquema]
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import curl_cffi.requests as cr
import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import config  # noqa: E402,F401  (.env da raiz; ausente no Code Editor, onde o ambiente já vem pronto)
except ImportError:
    pass

BASE = Path(__file__).resolve().parent.parent
LAKE = BASE / "out" / "lake"
TABELA = "clima_previsao_horaria_emissoes"
UA = {"User-Agent": "Mozilla/5.0 (compatible; FlexIA-Coletor/1.0; +hackathon ONS)"}
VARIAVEIS = {  # Open-Meteo -> coluna
    "wind_speed_100m": "vento_100m_kmh", "wind_direction_100m": "direcao_vento_100m_graus",
    "wind_speed_10m": "vento_10m_kmh", "wind_gusts_10m": "rajada_10m_kmh",
    "shortwave_radiation": "radiacao_global_wm2", "direct_radiation": "radiacao_direta_wm2",
    "temperature_2m": "temperatura_2m_c", "precipitation": "precipitacao_mm", "cloud_cover": "nebulosidade_pct",
}


def _conexao_s3() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws;")
    con.execute(f"CREATE SECRET s (TYPE s3, PROVIDER credential_chain, REGION '{os.environ.get('AWS_REGION', 'us-east-1')}')")
    return con


def pontos() -> pd.DataFrame:
    """Células das usinas: cópia local do lake ou, na nuvem (cron do Code Editor), o Parquet no S3."""
    local = LAKE / "analytics" / "analytics_usina_geo"
    con = duckdb.connect() if local.exists() else _conexao_s3()
    glob = f"{local.as_posix()}/*.parquet" if local.exists() else \
        f"s3://{os.environ['FLEXIA_BUCKET']}/analytics/analytics_usina_geo/*.parquet"
    return con.sql(f"""
        SELECT cel_lat AS latitude, cel_lon AS longitude, any_value(uf_ons) AS uf,
               count(*) FILTER (WHERE fonte = 'EOLICA') AS usinas_eolicas,
               count(*) FILTER (WHERE fonte <> 'EOLICA') AS usinas_solares,
               round(sum(mw_fiscalizada), 1) AS mw_fiscalizados
        FROM read_parquet('{glob}') WHERE coord_valida AND cel_lat IS NOT NULL
        GROUP BY 1, 2 ORDER BY mw_fiscalizados DESC""").df()


def open_meteo(pts: pd.DataFrame) -> pd.DataFrame:
    """Uma chamada por lote de 50 pontos (a API aceita listas de coordenadas)."""
    quadros = []
    for i in range(0, len(pts), 50):
        lote = pts.iloc[i:i + 50]
        url = ("https://api.open-meteo.com/v1/forecast?"
               f"latitude={','.join(f'{v:.2f}' for v in lote.latitude)}&longitude={','.join(f'{v:.2f}' for v in lote.longitude)}"
               f"&hourly={','.join(VARIAVEIS)}&forecast_days=16&timezone=UTC&wind_speed_unit=kmh")
        r = cr.get(url, timeout=120, impersonate="chrome", headers=UA)
        r.raise_for_status()
        dados = r.json()
        dados = dados if isinstance(dados, list) else [dados]
        for (_, p), d in zip(lote.iterrows(), dados):
            h = pd.DataFrame(d["hourly"]).rename(columns={"time": "din_instante", **VARIAVEIS})
            h["din_instante"] = pd.to_datetime(h["din_instante"])
            h["latitude"], h["longitude"], h["uf"] = p.latitude, p.longitude, p.uf
            quadros.append(h)
        time.sleep(1)
    df = pd.concat(quadros, ignore_index=True)
    df["provedor"] = "open-meteo (best match: ECMWF/GFS/ICON)"
    return df


def weathernext(pts: pd.DataFrame, so_esquema: bool) -> pd.DataFrame | None:
    """WeatherNext 3 no BigQuery. As colunas exatas dependem da tabela liberada; por isso o
    mapeamento abaixo é configurável (WEATHERNEXT_COLUNAS, JSON coluna_bq -> coluna_flexia)."""
    try:
        from google.cloud import bigquery
    except ImportError:
        sys.exit("Instale o cliente: pip install google-cloud-bigquery db-dtypes")
    tabela = os.environ.get("WEATHERNEXT_TABELA")
    if not tabela:
        sys.exit("Defina WEATHERNEXT_TABELA com a tabela liberada (ver developers.google.com/weathernext/guides/access-forecast).")
    cliente = bigquery.Client(project=os.environ.get("WEATHERNEXT_PROJETO"))
    t = cliente.get_table(tabela)
    if so_esquema:
        for campo in t.schema:
            print(f"{campo.name:40s} {campo.field_type:12s} {campo.description or ''}")
        return None
    mapa = json.loads(os.environ.get("WEATHERNEXT_COLUNAS", "{}"))
    if not mapa:
        sys.exit("Defina WEATHERNEXT_COLUNAS (JSON) mapeando as colunas do BigQuery para as da FlexIA; "
                 "rode antes com --esquema para ver os nomes.")
    pontos_sql = ", ".join(f"ST_GEOGPOINT({p.longitude}, {p.latitude})" for p in pts.itertuples())
    geo = os.environ.get("WEATHERNEXT_COLUNA_GEO", "geography")
    sel = ", ".join(f"{bq} AS {fx}" for bq, fx in mapa.items())
    sql = (f"SELECT {sel}, ST_Y({geo}) AS latitude, ST_X({geo}) AS longitude FROM `{tabela}` "
           f"WHERE ST_DWITHIN({geo}, ANY_VALUE(ST_UNION([{pontos_sql}])), 10000)")
    df = cliente.query(sql).to_dataframe()
    df["provedor"] = "Google DeepMind WeatherNext 3 (experimental; não é previsão oficial)"
    return df


def gravar(df: pd.DataFrame) -> dict:
    emissao = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    df["data_emissao"] = pd.Timestamp(emissao).date()
    destino = LAKE / "curated" / TABELA / f"data_emissao={emissao}"
    destino.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("df", df.drop(columns=["data_emissao"]))
    arquivo = destino / "part_0.parquet"
    con.execute(f"COPY df TO '{arquivo.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    if os.environ.get("FLEXIA_BUCKET"):  # na nuvem: a partição nova vai direto para o lake
        import boto3
        boto3.client("s3").upload_file(str(arquivo), os.environ["FLEXIA_BUCKET"],
                                       f"curated/{TABELA}/data_emissao={emissao}/part_0.parquet")
    meta = {"tabela": TABELA, "fonte": "Open-Meteo / WeatherNext", "tema": "clima",
            "titulo": "Previsão meteorológica horária nos polos eólicos e solares",
            "descricao": ("PREVISÃO meteorológica horária de 16 dias nas células de 0,25° das usinas eólicas e solares, "
                          "uma partição por data de emissão (data_emissao). Provedor na coluna 'provedor' "
                          "(Open-Meteo, modelos numéricos; ou Google DeepMind WeatherNext 3 quando habilitado). "
                          "É previsão, não dado observado: o observado está em clima_era5_horario."),
            "origem": "https://open-meteo.com/ · https://developers.google.com/weathernext",
            "dicionario": "manual (ingestao/previsao_clima.py)",
            "colunas": {"din_instante": "Hora prevista (UTC)", "latitude": "Latitude da célula ERA5 de 0,25°",
                        "longitude": "Longitude da célula ERA5 de 0,25°", "uf": "UF",
                        "vento_100m_kmh": "Vento previsto a 100 m, km/h", "direcao_vento_100m_graus": "Direção do vento a 100 m, graus",
                        "vento_10m_kmh": "Vento previsto a 10 m, km/h", "rajada_10m_kmh": "Rajada prevista a 10 m, km/h",
                        "radiacao_global_wm2": "Radiação solar global prevista, W/m²", "radiacao_direta_wm2": "Radiação direta prevista, W/m²",
                        "temperatura_2m_c": "Temperatura prevista a 2 m, °C", "precipitacao_mm": "Precipitação prevista na hora, mm",
                        "nebulosidade_pct": "Cobertura de nuvens prevista, %", "provedor": "Modelo/provedor da previsão",
                        "data_emissao": "Data em que a previsão foi obtida (partição)"},
            "linhas": len(df), "periodo": [str(df.din_instante.min()), str(df.din_instante.max())],
            "coluna_tempo": "din_instante", "particionada_por_ano": False}
    (BASE / "out" / "metadados").mkdir(parents=True, exist_ok=True)
    (BASE / "out" / "metadados" / f"{TABELA}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"tabela": TABELA, "emissao": emissao, "linhas": len(df), "pontos": df[["latitude", "longitude"]].drop_duplicates().shape[0],
            "periodo": meta["periodo"]}


if __name__ == "__main__":
    provedor = sys.argv[sys.argv.index("--provedor") + 1] if "--provedor" in sys.argv else "open-meteo"
    pts = pontos()
    if provedor == "weathernext":
        df = weathernext(pts, "--esquema" in sys.argv)
        if df is None:
            sys.exit()
    else:
        df = open_meteo(pts)
    print(json.dumps(gravar(df), ensure_ascii=False))
