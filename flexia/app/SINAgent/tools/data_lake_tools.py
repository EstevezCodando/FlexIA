"""Ferramentas da FlexIA para consultar o data lake do Hackathon ONS (Glue + Athena).

Somente leitura: apenas SELECT/WITH, um comando por chamada, resultado limitado.
Configuração por variáveis de ambiente:
  FLEXIA_DATABASE   (padrão ons_lake)
  FLEXIA_WORKGROUP  (padrão ons-lake; o workgroup define o local de resultados e o limite de bytes)
  AWS_REGION        (padrão us-east-1)
"""
import os
import re
import time

import boto3
from strands import tool

DATABASE = os.environ.get("FLEXIA_DATABASE", "ons_lake")
WORKGROUP = os.environ.get("FLEXIA_WORKGROUP", "ons-lake")
REGIAO = os.environ.get("AWS_REGION", "us-east-1")
MAX_LINHAS = 200
TIMEOUT_S = 120

_glue = boto3.client("glue", region_name=REGIAO)
_athena = boto3.client("athena", region_name=REGIAO)

_PROIBIDO = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|msck|unload|call|vacuum|optimize)\b",
    re.IGNORECASE,
)


@tool
def listar_tabelas() -> str:
    """
    Lista as tabelas do data lake (dados ONS, clima ERA5, ANEEL e tabelas analíticas
    da equipe) com a descrição de cada uma.

    Use SEMPRE antes de escrever SQL, para escolher a tabela certa.
    """
    linhas = []
    for pag in _glue.get_paginator("get_tables").paginate(DatabaseName=DATABASE):
        for t in pag["TableList"]:
            part = " [particionada por ano]" if t.get("PartitionKeys") else ""
            linhas.append(f"- {t['Name']}{part}: {t.get('Description', '')}")
    return "\n".join(sorted(linhas))


@tool
def descrever_tabela(tabela: str) -> str:
    """
    Mostra as colunas de uma tabela do data lake com tipo, unidade e significado.

    Use antes de consultar uma tabela para saber nomes exatos de colunas e unidades.

    Args:
        tabela: nome da tabela, como retornado por listar_tabelas.
    """
    t = _glue.get_table(DatabaseName=DATABASE, Name=tabela)["Table"]
    cols = t["StorageDescriptor"]["Columns"] + t.get("PartitionKeys", [])
    saida = [f"{t['Name']}: {t.get('Description', '')}", ""]
    saida += [f"- {c['Name']} ({c['Type']}): {c.get('Comment', '')}" for c in cols]
    return "\n".join(saida)


@tool
def consultar_sql(sql: str) -> str:
    """
    Executa UMA consulta SQL somente leitura (Amazon Athena / Trino) no data lake
    e devolve até 200 linhas em formato tabular.

    Regras:
    - Apenas SELECT ou WITH ... SELECT. Um comando por chamada, sem ponto e vírgula.
    - Em tabelas particionadas, filtre por ano (ex.: WHERE ano = 2025) para reduzir custo.
    - Agregue no SQL (sum, avg, count, group by) em vez de trazer linhas cruas.
    - Datas: use TIMESTAMP '2025-01-01 00:00:00' ou DATE '2025-01-01'.

    Args:
        sql: consulta SQL a executar.
    """
    consulta = sql.strip().rstrip(";").strip()
    if ";" in consulta:
        return "ERRO: envie apenas um comando SQL por chamada."
    if not re.match(r"^(select|with)\b", consulta, re.IGNORECASE) or _PROIBIDO.search(consulta):
        return "ERRO: apenas consultas SELECT/WITH somente leitura são permitidas."

    qid = _athena.start_query_execution(
        QueryString=consulta,
        WorkGroup=WORKGROUP,
        QueryExecutionContext={"Database": DATABASE},
    )["QueryExecutionId"]

    inicio = time.time()
    while True:
        info = _athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        estado = info["Status"]["State"]
        if estado in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.time() - inicio > TIMEOUT_S:
            _athena.stop_query_execution(QueryExecutionId=qid)
            return f"ERRO: consulta excedeu {TIMEOUT_S}s. Filtre por ano ou agregue mais."
        time.sleep(1)

    if estado != "SUCCEEDED":
        return f"ERRO do Athena: {info['Status'].get('StateChangeReason', estado)}"

    res = _athena.get_query_results(QueryExecutionId=qid, MaxResults=MAX_LINHAS + 1)
    linhas = [[c.get("VarCharValue", "") for c in r["Data"]] for r in res["ResultSet"]["Rows"]]
    if not linhas:
        return "Consulta sem resultados."
    cabecalho, dados = linhas[0], linhas[1:]
    truncado = res.get("NextToken") is not None
    mb = info.get("Statistics", {}).get("DataScannedInBytes", 0) / 1e6

    tabela = [" | ".join(cabecalho)] + [" | ".join(l) for l in dados]
    rodape = f"\n({len(dados)} linha(s){', TRUNCADO em 200' if truncado else ''}; {mb:.1f} MB lidos; query_id={qid})"
    return "\n".join(tabela) + rodape
