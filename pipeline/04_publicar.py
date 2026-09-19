"""Publica o lake na AWS: S3 (Parquet particionado) + catálogo JSON. Idempotente.

A conta do workshop não permite Glue/Athena; a consulta é feita pelo DuckDB lendo o Parquet
direto do S3. O dicionário de dados vai para s3://<bucket>/catalogo/catalogo.json.

Pré-requisito: credenciais AWS no .env (ver .env.example / configurar.ps1). Bucket com Block Public Access.

Uso:
  python pipeline/04_publicar.py                       # tudo
  python pipeline/04_publicar.py --sem-raw             # pula o upload dos brutos
  python pipeline/04_publicar.py --validar             # só confere contagens lendo do S3
  python pipeline/04_publicar.py --permitir-runtimes   # também dá leitura do lake às roles AgentCore
  python pipeline/04_publicar.py --validar --permitir-runtimes   # só a permissão + conferência, sem reenviar
  python pipeline/04_publicar.py --sem-raw --remover-antigos     # apaga do S3 arquivos de tabelas regeradas
                                                                 # (bucket versionado: recuperável)
"""
import csv
import json
import os
import sys
from pathlib import Path

import duckdb
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalogo import REGRAS, TABELAS  # noqa: E402

REGIAO = config.REGIAO
BASE = Path(__file__).resolve().parent.parent
LAKE = BASE / "out" / "lake"
ORIGEM = Path(os.environ.get("ORIGEM", r"C:\Hackathon_ONS"))
EXCLUIR_RAW = (".duckdb",)

sessao = config.sessao()
s3 = sessao.client("s3")
CONTA = sessao.client("sts").get_caller_identity()["Account"]
BUCKET = os.environ.get("FLEXIA_BUCKET") or f"ons-datalake-{CONTA}"
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
        pares = [(p, f"{camada}/{p.relative_to(base).as_posix()}") for p in base.rglob("*.parquet")]
        enviar(pares, camada)
        # tabela regerada com outro particionamento: arquivos antigos no S3 somariam linhas em dobro.
        # Só remove dentro de tabelas que existem localmente; o bucket é versionado (recuperável).
        locais = {k for _, k in pares}
        tabelas = {d.name for d in base.iterdir() if d.is_dir()}
        orfaos = [k for k in existentes(camada + "/")
                  if k not in locais and k.split("/")[1] in tabelas and k.endswith(".parquet")]
        if not orfaos:
            continue
        if "--remover-antigos" not in sys.argv:
            print(f"{camada}: {len(orfaos)} arquivos antigos no S3 sem cópia local (ex.: {orfaos[0]}); "
                  "rode com --remover-antigos para apagá-los")
            continue
        for i in range(0, len(orfaos), 1000):
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in orfaos[i:i + 1000]]})
        print(f"{camada}: {len(orfaos)} arquivos antigos removidos do S3 (ex.: {orfaos[0]})")


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


def tabelas_locais():
    for camada in ("curated", "analytics"):
        for pasta in sorted((LAKE / camada).iterdir()):
            yield camada, pasta


FONTE_POR_PREFIXO = {"ons": "ONS", "aneel": "ANEEL", "ccee": "CCEE", "epe": "EPE", "clima": "ERA5/Open-Meteo",
                     "analytics": "Equipe (análises)"}
TEMA_MANUAL = {"ons_cmo": "precos", "ons_restricao": "restricao", "ons_geracao": "geracao", "ons_balanco": "geracao",
               "ons_curva": "carga", "ons_intercambio": "intercambio", "ons_programacao": "operacao",
               "ons_capacidade": "cadastro", "ons_modalidade": "cadastro", "ons_usina": "cadastro",
               "aneel_tarifas": "precos", "aneel_siga": "cadastro", "clima": "clima", "analytics_corte": "restricao",
               "analytics_tarifa": "precos", "analytics_frota": "mobilidade", "analytics_octopus": "precos"}


def metadados_automaticos() -> dict:
    """Metadados gerados pelos ingestores (ingestao/*.py): descrição oficial, colunas, origem, tema."""
    pasta = BASE / "out" / "metadados"
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in pasta.glob("*.json")} if pasta.exists() else {}


def publicar_catalogo() -> None:
    """catalogo.json: o que a FlexIA lê para saber tabelas, colunas, unidades, caminhos e regras.
    Descrições manuais (pipeline/catalogo.py) têm prioridade sobre as automáticas (out/metadados)."""
    con = duckdb.connect()
    ref = TABELAS["clima_era5_horario"]["colunas"]
    auto = metadados_automaticos()
    tabelas = []
    for camada, pasta in tabelas_locais():
        nome = pasta.name
        a = auto.get(nome, {})
        meta = TABELAS.get(nome) or {"descricao": a.get("descricao", ""), "colunas": a.get("colunas", {})}
        desc_cols = meta["colunas"] or (ref if nome.startswith("clima_") else {})
        particionada = any(d.name.startswith("ano=") for d in pasta.iterdir())
        hive = any(d.is_dir() and "=" in d.name for d in pasta.iterdir())  # ano=, data_emissao= ...
        glob = f"{pasta.as_posix()}/**/*.parquet"
        cols = con.sql(f"describe select * from read_parquet('{glob}', hive_partitioning={str(hive).lower()})").fetchall()
        faixa = None
        if particionada:
            faixa = [int(x) for x in con.sql(
                f"select min(ano), max(ano) from read_parquet('{glob}', hive_partitioning=true)").fetchone()]
        prefixo = nome.split("_")[0]
        tema = a.get("tema") or next((t for p, t in sorted(TEMA_MANUAL.items(), key=lambda kv: -len(kv[0]))
                                      if nome.startswith(p)), "outros")
        tabelas.append({
            "nome": nome,
            "camada": camada,
            "fonte": a.get("fonte") or FONTE_POR_PREFIXO.get(prefixo, prefixo.upper()),
            "tema": tema,
            "origem": a.get("origem", ""),
            "dicionario": a.get("dicionario", "manual (pipeline/catalogo.py)" if nome in TABELAS else ""),
            "descricao": meta["descricao"],
            "caminho": f"s3://{BUCKET}/{camada}/{nome}/**/*.parquet",
            "particionada_por_ano": particionada,
            "hive": hive,
            "anos": faixa,
            "periodo": a.get("periodo"),
            "coluna_tempo": a.get("coluna_tempo"),
            "linhas": con.sql(f"select count(*) from read_parquet('{glob}')").fetchone()[0],
            "colunas": [{"nome": c[0], "tipo": c[1], "descricao": desc_cols.get(c[0], "")} for c in cols],
        })
    doc = {"bucket": BUCKET, "regras": REGRAS, "tabelas": tabelas}
    s3.put_object(Bucket=BUCKET, Key="catalogo/catalogo.json", ContentType="application/json",
                  Body=json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"))
    (BASE / "out" / "catalogo.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"catálogo: {len(tabelas)} tabelas em s3://{BUCKET}/catalogo/catalogo.json")


def enviar_flexia() -> None:
    """Código da FlexIA que o Code Editor baixa com flexia/instalar_data_lake.sh."""
    base = BASE / "flexia" / "app"
    pares = [(p, f"flexia/app/{p.relative_to(base).as_posix()}") for p in base.rglob("*.py")
             if "__pycache__" not in p.parts]
    # coletor agendado (baixado por flexia/instalar_coletor_agendado.sh)
    pares += [(BASE / "coleta" / n, f"deploy/coletor/{n}") for n in ("coletor.py", "fontes.py", "indexar.py")]
    pares += [(p, f"deploy/coletor/sementes/{p.name}") for p in (BASE / "coleta" / "sementes").glob("*.json")]
    pares += [(BASE / "ingestao" / "previsao_clima.py", "deploy/coletor/previsao_clima.py")]
    for p, k in pares:
        s3.upload_file(str(p), BUCKET, k)
    print(f"flexia + coletor: {len(pares)} arquivos enviados")


def politica_leitura_lake() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "ListarLake", "Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
             "Resource": f"arn:aws:s3:::{BUCKET}"},
            {"Sid": "LerLake", "Effect": "Allow", "Action": ["s3:GetObject"],
             "Resource": [f"arn:aws:s3:::{BUCKET}/curated/*", f"arn:aws:s3:::{BUCKET}/analytics/*",
                          f"arn:aws:s3:::{BUCKET}/catalogo/*", f"arn:aws:s3:::{BUCKET}/docs/*"]},
        ],
    }


def permitir_runtimes() -> None:
    """Anexa a política SOMENTE LEITURA do lake às roles dos runtimes AgentCore da conta."""
    iam = sessao.client("iam")
    roles = set()
    # o runtime é implantado pelo CDK do Code Editor (us-west-2), não na região do lake
    for regiao in dict.fromkeys([REGIAO, os.environ.get("FLEXIA_REGIAO_AGENTCORE", "us-west-2")]):
        try:
            ctl = sessao.client("bedrock-agentcore-control", region_name=regiao)
            for r in ctl.list_agent_runtimes().get("agentRuntimes", []):
                det = ctl.get_agent_runtime(agentRuntimeId=r["agentRuntimeId"])
                roles.add(det["roleArn"].split("/")[-1])
                print(f"  runtime {r['agentRuntimeName']} ({regiao}) -> role {det['roleArn'].split('/')[-1]}")
        except Exception as e:  # noqa: BLE001
            print(f"  aviso: não consegui listar runtimes AgentCore em {regiao} ({e})")
    roles.update(r for r in os.environ.get("ROLES_EXTRAS", "").split(",") if r)
    if not roles:
        print("  nenhuma role de runtime encontrada; implante a FlexIA e rode de novo")
    doc = json.dumps(politica_leitura_lake())
    for role in sorted(roles):
        iam.put_role_policy(RoleName=role, PolicyName="FlexIALeituraDataLake", PolicyDocument=doc)
        print(f"  política FlexIALeituraDataLake aplicada em {role}")


def validar() -> None:
    """Conta as linhas de cada tabela lendo do S3 e compara com a cópia local."""
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws;")
    perfil = "" if os.environ.get("AWS_ACCESS_KEY_ID") else f"PROFILE '{os.environ['AWS_PROFILE']}', "
    con.sql(f"CREATE SECRET s (TYPE s3, PROVIDER credential_chain, {perfil}REGION '{REGIAO}')")
    erros = 0
    for camada, pasta in tabelas_locais():
        local = con.sql(f"select count(*) from read_parquet('{pasta.as_posix()}/**/*.parquet')").fetchone()[0]
        remoto = con.sql(f"select count(*) from read_parquet('s3://{BUCKET}/{camada}/{pasta.name}/**/*.parquet')").fetchone()[0]
        ok = "ok " if local == remoto else "ERRO"
        erros += local != remoto
        print(f"  {ok} {pasta.name:40s} local={local:>12,} s3={remoto:>12,}", flush=True)
    print("validação:", "tudo confere" if not erros else f"{erros} tabela(s) divergente(s)")


def main() -> None:
    print(f"conta {CONTA}  região {REGIAO}  bucket {BUCKET}")
    if "--validar" not in sys.argv:
        criar_bucket()
        enviar_lake()
        if "--sem-raw" not in sys.argv:
            enviar_raw()
        publicar_catalogo()
        enviar_flexia()
    # Concessão de IAM só com aprovação explícita (flag); com --validar, não reenvia nada.
    if "--permitir-runtimes" in sys.argv:
        permitir_runtimes()
    elif "--validar" not in sys.argv:
        print("IAM: nada alterado. Rode com --permitir-runtimes para dar à FlexIA leitura do lake.")
    validar()


if __name__ == "__main__":
    main()
