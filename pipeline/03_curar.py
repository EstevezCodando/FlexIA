"""Constrói a camada curada do data lake em out/lake/ a partir de C:\\Hackathon_ONS (somente leitura).

Layout (espelhado no S3):
  curated/<tabela>/ano=YYYY/*.parquet   séries temporais, esquema unificado e tipado
  curated/<tabela>/*.parquet            cadastros / tabelas pequenas
  analytics/<tabela>/*.parquet          tabelas silver/gold já produzidas pela equipe

Uso: python pipeline/03_curar.py [tabela ...]   (sem argumentos, gera todas)
"""
import os
import shutil
import sys
from pathlib import Path

import duckdb

ORIGEM = Path(os.environ.get("ORIGEM", r"C:\Hackathon_ONS")) / "data"
RAW = ORIGEM / "raw"
LAKE = Path(__file__).resolve().parent.parent / "out" / "lake"

# tabela curada -> (pasta de origem, particionar por ano?)
ONS = {
    "ons_geracao_usina_horaria": ("ons/geracao-usina-2", True),
    "ons_balanco_energia_subsistema": ("ons/balanco-energia-subsistema", True),
    "ons_curva_carga": ("ons/curva-carga", True),
    "ons_cmo_semihorario": ("ons/cmo-semi-horario", True),
    "ons_intercambio_nacional": ("ons/intercambio-nacional", True),
    "ons_restricao_eolica_usina": ("ons/restricao_coff_eolica_usi", True),
    "ons_restricao_eolica_detalhe": ("ons/restricao_coff_eolica_detail", True),
    "ons_restricao_fotovoltaica_usina": ("ons/restricao_coff_fotovoltaica", True),
    "ons_restricao_fotovoltaica_detalhe": ("ons/restricao_coff_fotovoltaica_detail", True),
    "ons_programacao_fluxo_controlado": ("ons/programacao_fluxo_controlado", True),
    "ons_programacao_x_previsao": ("ons/programacao_x_previsao", True),
    "ons_capacidade_geracao": ("ons/capacidade-geracao", False),
    "ons_modalidade_usina": ("ons/modalidade-usina", False),
    "ons_usina_conjunto": ("ons/usina_conjunto", False),
}

ANALYTICS = {
    "analytics_corte_usina": "lake/silver/silver_corte.parquet",
    "analytics_corte_detalhe": "lake/silver/silver_detalhe.parquet",
    "analytics_usina_geo": "lake/silver/silver_usina_geo.parquet",
    "analytics_corte_elemento": "lake/gold/gold_corte_elemento.parquet",
    "analytics_corte_mensal": "lake/gold/gold_corte_mensal.parquet",
    "analytics_piso_ruido": "lake/gold/gold_piso_ruido.parquet",
    "analytics_gabarito_ene_2026": "lake/ev/gabarito_ene_2026.parquet",
    "analytics_previsao_ene_ne_2026": "lake/ev/previsao_ene_ne_2026.parquet",
    "analytics_consumo_rj": "lake/silver_consumo_rj.parquet",
    "analytics_frota_ev_rio": "lake/silver_frota_rio.parquet",
    "analytics_tarifa_light": "lake/silver_tarifa_light.parquet",
    "analytics_octopus_tarifas": "lake/silver_tarifas_eletricas.parquet",
    "analytics_octopus_produtos": "lake/silver_produtos.parquet",
    "analytics_octopus_agile_amostra": "lake/silver_agile_amostra.parquet",
    "analytics_octopus_gsp": "lake/silver_gsp.parquet",
}


def tipo_alvo(col: str) -> str:
    if col in ("din_instante",):
        return "TIMESTAMP"
    if col in ("din_programacaodia", "dat_programacao"):
        return "DATE"
    if col.startswith("num_minutos"):
        return "BIGINT"
    if col.startswith("val_"):
        return "DOUBLE"
    if col.startswith("flg_") or col in ("num_patamar", "tip_terminal", "id_conjuntousina"):
        return "INTEGER"
    return "VARCHAR"


def expr(col: str, tipo_origem: str, alvo: str) -> str:
    c = f'"{col}"'
    if alvo == "DATE" and col == "dat_programacao":
        return f"strptime(CAST({c} AS VARCHAR), '%Y%m%d')::DATE"
    if alvo == "DOUBLE" and tipo_origem == "VARCHAR":
        return f"TRY_CAST(replace({c}, ',', '.') AS DOUBLE)"
    if alvo == "INTEGER" and tipo_origem == "BOOLEAN":
        return f"CAST({c} AS INTEGER)"
    return f"TRY_CAST({c} AS {alvo})"


def leitor(p: Path) -> str:
    if p.suffix == ".parquet":
        return f"read_parquet('{p.as_posix()}')"
    return f"read_csv('{p.as_posix()}', delim=';', header=true, sample_size=-1)"


def fonte_unificada(con, pasta: Path) -> str:
    arquivos = sorted(p for p in pasta.iterdir() if p.suffix in (".parquet", ".csv"))
    esquemas = {}
    ordem = []
    for p in arquivos:
        cols = {c[0].lower(): (c[0], c[1]) for c in con.sql(f"describe select * from {leitor(p)}").fetchall()}
        esquemas[p] = cols
        for c in cols:
            if c not in ordem:
                ordem.append(c)
    selects = []
    for p in arquivos:
        partes = []
        for c in ordem:
            alvo = tipo_alvo(c)
            if c in esquemas[p]:
                nome_original, tipo = esquemas[p][c]
                partes.append(f"{expr(nome_original, tipo, alvo)} AS {c}")
            else:
                partes.append(f"CAST(NULL AS {alvo}) AS {c}")
        selects.append(f"SELECT {', '.join(partes)} FROM {leitor(p)}")
    return "\nUNION ALL\n".join(selects)


def coluna_tempo(con, sql: str) -> str | None:
    cols = [c[0] for c in con.sql(f"describe select * from ({sql})").fetchall()]
    for c in ("din_instante", "din_programacaodia", "dat_programacao"):
        if c in cols:
            return c
    return None


def gravar(con, nome: str, sql: str, particionar: bool, camada: str = "curated") -> None:
    destino = LAKE / camada / nome
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    tempo = coluna_tempo(con, sql) if particionar else None
    if tempo:
        con.sql(
            # sem ORDER BY global: os arquivos de origem já são cronológicos e não se sobrepõem
            f"COPY (SELECT *, year({tempo}) AS ano FROM ({sql})) "
            f"TO '{destino.as_posix()}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (ano), "
            f"ROW_GROUP_SIZE 500000, FILENAME_PATTERN 'part_{{i}}')"
        )
    else:
        con.sql(
            f"COPY ({sql}) TO '{(destino / 'part_0.parquet').as_posix()}' (FORMAT parquet, COMPRESSION zstd)"
        )
    n = con.sql(f"select count(*) from read_parquet('{destino.as_posix()}/**/*.parquet')").fetchone()[0]
    mb = sum(f.stat().st_size for f in destino.rglob("*.parquet")) / 1e6
    print(f"{camada}/{nome:40s} {n:>12,} linhas  {mb:8.1f} MB", flush=True)


def sql_clima(pasta: Path) -> str:
    return (
        f"SELECT polo, split_part(polo, '_', 1) AS uf, latitude, longitude, "
        f"CAST(\"time\" AS TIMESTAMP) AS din_instante, "
        f"\"wind_speed_100m (km/h)\" AS vento_100m_kmh, \"wind_direction_100m (°)\" AS direcao_vento_100m_graus, "
        f"\"wind_gusts_10m (km/h)\" AS rajada_10m_kmh, \"wind_speed_10m (km/h)\" AS vento_10m_kmh, "
        f"\"shortwave_radiation (W/m²)\" AS radiacao_global_wm2, \"direct_radiation (W/m²)\" AS radiacao_direta_wm2, "
        f"\"temperature_2m (°C)\" AS temperatura_2m_c, \"surface_pressure (hPa)\" AS pressao_superficie_hpa "
        f"FROM read_csv('{pasta.as_posix()}/*.csv', header=true, union_by_name=true)"
    )


def sql_aneel_csv(caminho: Path, numericas: list[str], datas: list[str]) -> str:
    """CSV da ANEEL: ';', decimal com vírgula, UTF-8. Converte numéricas e datas."""
    con = duckdb.connect()
    cols = [c[0] for c in con.sql(
        f"describe select * from read_csv('{caminho.as_posix()}', delim=';', header=true, all_varchar=true)").fetchall()]
    partes = []
    for c in cols:
        if c in numericas:
            partes.append(f"TRY_CAST(replace(replace(\"{c}\", '.', ''), ',', '.') AS DOUBLE) AS \"{c}\"")
        elif c in datas:
            partes.append(f"TRY_CAST(\"{c}\" AS DATE) AS \"{c}\"")
        else:
            partes.append(f"NULLIF(trim(\"{c}\"), '') AS \"{c}\"")
    return (f"SELECT {', '.join(partes)} FROM read_csv('{caminho.as_posix()}', delim=';', header=true, "
            f"all_varchar=true, quote='\"')")


def main() -> None:
    filtro = set(sys.argv[1:])
    tmp = LAKE.parent / "tmp_duckdb"
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql(f"SET memory_limit='16GB'; SET temp_directory='{tmp.as_posix()}'; SET preserve_insertion_order=false")

    def quer(nome):
        return not filtro or nome in filtro

    for nome, (pasta, particionar) in ONS.items():
        if quer(nome):
            gravar(con, nome, fonte_unificada(con, RAW / pasta), particionar)

    if quer("clima_era5_horario"):
        gravar(con, "clima_era5_horario", sql_clima(RAW / "clima/open_meteo"), True)
    if quer("clima_previsao_horaria"):
        gravar(con, "clima_previsao_horaria", sql_clima(RAW / "clima/previsao"), False)

    if quer("aneel_tarifas_homologadas"):
        gravar(con, "aneel_tarifas_homologadas", sql_aneel_csv(
            RAW / "aneel/tarifas-homologadas-distribuidoras-energia-eletrica.csv",
            numericas=["VlrTUSD", "VlrTE"],
            datas=["DatGeracaoConjuntoDados", "DatInicioVigencia", "DatFimVigencia"]), False)
    if quer("aneel_siga_empreendimentos"):
        gravar(con, "aneel_siga_empreendimentos", sql_aneel_csv(
            RAW / "geo/siga_empreendimentos_geracao.csv",
            numericas=["MdaPotenciaOutorgadaKw", "MdaPotenciaFiscalizadaKw", "MdaGarantiaFisicaKw",
                       "NumCoordNEmpreendimento", "NumCoordEEmpreendimento"],
            datas=["DatGeracaoConjuntoDados", "DatEntradaOperacao", "DatInicioVigencia", "DatFimVigencia"]), False)

    for nome, rel in ANALYTICS.items():
        if quer(nome):
            gravar(con, nome, f"SELECT * FROM read_parquet('{(ORIGEM / rel).as_posix()}')", False, "analytics")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
