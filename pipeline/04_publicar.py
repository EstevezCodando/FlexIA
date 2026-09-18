"""Publica o lake na AWS: S3 + Glue Data Catalog + Athena. Idempotente.

Pré-requisito: credenciais da conta do workshop em um perfil (padrão: AWS_PROFILE=hackathon)
ou em variáveis de ambiente. Nada aqui é público: bucket com Block Public Access.

Uso:
  python pipeline/04_publicar.py            # tudo
  python pipeline/04_publicar.py --sem-raw  # pula o upload dos brutos (~5 GB)
  python pipeline/04_publicar.py --validar  # só confere contagens no Athena
"""
import csv
import os
import sys
import time
from pathlib import Path

import boto3
import duckdb
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalogo import TABELAS  # noqa: E402

REGIAO = os.environ.get("AWS_REGION", "us-east-1")
PERFIL = os.environ.get("AWS_PROFILE", "hackathon")
BASE = Path(__file__).resolve().parent.parent
LAKE = BASE / "out" / "lake"
ORIGEM = Path(os.environ.get("ORIGEM", r"C:\Hackathon_ONS"))
DATABASE = "ons_lake"
WORKGROUP = "ons-lake"
LIMITE_BYTES_CONSULTA = 20 * 1024**3  # 20 GB por consulta (proteção de custo)
EXCLUIR_RAW = (".duckdb",)

TIPO_GLUE = {"VARCHAR": "string", "DOUBLE": "double", "BIGINT": "bigint", "INTEGER": "int",
             "TIMESTAMP": "timestamp", "DATE": "date", "BOOLEAN": "boolean", "FLOAT": "float"}

sessao = boto3.Session(profile_name=PERFIL if PERFIL else None, region_name=REGIAO) \
    if PERFIL in boto3.Session().available_profiles else boto3.Session(region_name=REGIAO)
s3 = sessao.client("s3")
glue = sessao.client("glue")
athena = sessao.client("athena")
CONTA = sessao.client("sts").get_caller_identity()["Account"]
BUCKET = os.environ.get("BUCKET", f"ons-datalake-{CONTA}")
TRANSFER = TransferConfig(multipart_threshold=64 * 1024**2, max_concurrency=16)


def criar_bucket() -> None:
    try:
        s3.head_bucket(Bucket=BUCKET)
        print(f"bucket s3://{BUCKET} já existe")
    except ClientError:
        kw = {} if REGIAO == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": REGIAO}}
        s3.create_bucket(Bucket=BUCKET, **kw)
        print(f"bucket s3://{BUCKET} criado")
    s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=BUCKET, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})


def existentes(prefixo: str) -> dict:
    out = {}
    for pag in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefixo):
        for o in pag.get("Contents", []):
            out[o["Key"]] = o["Size"]
    return out


def enviar(pares: list[tuple[Path, str]], rotulo: str) -> None:
    ja = existentes(rotulo + "/")
    pend = [(p, k) for p, k in pares if ja.get(k) != p.stat().st_size]
    total = sum(p.stat().st_size for p, _ in pend)
    print(f"{rotulo}: {len(pares)} arquivos, {len(pend)} a enviar ({total/1e9:.2f} GB)")
    for i, (p, k) in enumerate(pend, 1):
        s3.upload_file(str(p), BUCKET, k, Config=TRANSFER)
        if i % 200 == 0 or i == len(pend):
            print(f"  {i}/{len(pend)}", flush=True)


def enviar_lake() -> None:
    for camada in ("curated", "analytics"):
        base = LAKE / camada
        enviar([(p, f"{camada}/{p.relative_to(base).as_posix()}") for p in base.rglob("*.parquet")], camada)


def enviar_raw() -> None:
    """Brutos deduplicados: só o caminho canônico de cada grupo de duplicatas, sob data/raw/."""
    pares = []
    with open(BASE / "out" / "inventario.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["duplicado"] == "True" or not r["caminho"].startswith("data/raw/"):
                continue
            if r["caminho"].endswith(EXCLUIR_RAW):
                continue
            pares.append((ORIGEM / r["caminho"], "raw/" + r["caminho"][len("data/raw/"):]))
    enviar(pares, "raw")


def colunas_locais(pasta: Path) -> list[tuple[str, str]]:
    con = duckdb.connect()
    arquivo = next(pasta.rglob("*.parquet")).as_posix()
    return [(c[0], TIPO_GLUE[c[1]]) for c in con.sql(f"describe select * from read_parquet('{arquivo}')").fetchall()]


def criar_catalogo() -> None:
    try:
        glue.create_database(DatabaseInput={
            "Name": DATABASE,
            "Description": "Data lake do Hackathon ONS: dados ONS, clima ERA5, ANEEL e tabelas analíticas da equipe."})
        print(f"database {DATABASE} criado")
    except glue.exceptions.AlreadyExistsException:
        pass

    ref = TABELAS["clima_era5_horario"]["colunas"]
    for camada in ("curated", "analytics"):
        for pasta in sorted((LAKE / camada).iterdir()):
            nome = pasta.name
            meta = TABELAS.get(nome, {"descricao": "", "colunas": {}})
            desc_cols = meta["colunas"] or (ref if nome.startswith("clima_") else {})
            particionada = any(d.name.startswith("ano=") for d in pasta.iterdir())
            cols = [{"Name": c, "Type": t, "Comment": desc_cols.get(c, "")[:255]} for c, t in colunas_locais(pasta)]
            local = f"s3://{BUCKET}/{camada}/{nome}/"
            params = {"classification": "parquet", "camada": camada, "EXTERNAL": "TRUE"}
            chaves = []
            if particionada:
                chaves = [{"Name": "ano", "Type": "int", "Comment": desc_cols.get("ano", "Ano (partição)")[:255]}]
                params.update({
                    "projection.enabled": "true",
                    "projection.ano.type": "integer",
                    "projection.ano.range": "2000,2030",
                    "storage.location.template": local + "ano=${ano}/",
                })
            entrada = {
                "Name": nome,
                "Description": meta["descricao"][:2048],
                "TableType": "EXTERNAL_TABLE",
                "Parameters": params,
                "PartitionKeys": chaves,
                "StorageDescriptor": {
                    "Columns": cols,
                    "Location": local,
                    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                    "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"},
                },
            }
            try:
                glue.create_table(DatabaseName=DATABASE, TableInput=entrada)
                acao = "criada"
            except glue.exceptions.AlreadyExistsException:
                glue.update_table(DatabaseName=DATABASE, TableInput=entrada)
                acao = "atualizada"
            print(f"  glue {DATABASE}.{nome} {acao}{' (particionada por ano)' if particionada else ''}")


def criar_workgroup() -> None:
    cfg = {
        "ResultConfiguration": {"OutputLocation": f"s3://{BUCKET}/athena-results/"},
        "EnforceWorkGroupConfiguration": True,
        "PublishCloudWatchMetricsEnabled": True,
        "BytesScannedCutoffPerQuery": LIMITE_BYTES_CONSULTA,
        "EngineVersion": {"SelectedEngineVersion": "Athena engine version 3"},
    }
    try:
        athena.create_work_group(Name=WORKGROUP, Configuration=cfg,
                                 Description="Consultas ao data lake do Hackathon ONS")
        print(f"workgroup {WORKGROUP} criado")
    except ClientError as e:
        if "already" not in str(e).lower():
            raise
        athena.update_work_group(WorkGroup=WORKGROUP, ConfigurationUpdates={
            "ResultConfigurationUpdates": cfg["ResultConfiguration"],
            "EnforceWorkGroupConfiguration": True,
            "BytesScannedCutoffPerQuery": LIMITE_BYTES_CONSULTA})


def consultar(sql: str) -> list:
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP,
                                       QueryExecutionContext={"Database": DATABASE})["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if st["State"] != "SUCCEEDED":
        raise RuntimeError(st.get("StateChangeReason", st["State"]))
    linhas = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    return [[c.get("VarCharValue") for c in r["Data"]] for r in linhas[1:]]


def validar() -> None:
    con = duckdb.connect()
    erros = 0
    for camada in ("curated", "analytics"):
        for pasta in sorted((LAKE / camada).iterdir()):
            local = con.sql(f"select count(*) from read_parquet('{pasta.as_posix()}/**/*.parquet')").fetchone()[0]
            remoto = int(consultar(f'SELECT count(*) FROM "{pasta.name}"')[0][0])
            ok = "ok " if local == remoto else "ERRO"
            erros += local != remoto
            print(f"  {ok} {pasta.name:40s} local={local:>12,} athena={remoto:>12,}")
    print("validação:", "tudo confere" if not erros else f"{erros} tabela(s) divergente(s)")


def main() -> None:
    print(f"conta {CONTA}  região {REGIAO}  bucket {BUCKET}")
    if "--validar" not in sys.argv:
        criar_bucket()
        enviar_lake()
        if "--sem-raw" not in sys.argv:
            enviar_raw()
        criar_catalogo()
        criar_workgroup()
    validar()


if __name__ == "__main__":
    main()
