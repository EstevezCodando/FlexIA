"""Ferramentas da FlexIA para consultar o data lake do Hackathon ONS.

O motor é o DuckDB lendo Parquet direto do S3 (a conta do workshop não permite Glue/Athena).
Cada tabela do catálogo vira uma VIEW; tabelas grandes são particionadas por `ano`.

Isolamento: o DuckDB só acessa o prefixo do bucket do lake, a configuração é travada
e só SELECT/WITH é aceito.

Variáveis de ambiente:
  FLEXIA_BUCKET  bucket do lake (padrão: ons-datalake-<conta>)
  AWS_REGION     (padrão us-east-1)
"""
import json
import os
import re
import threading

import boto3
import duckdb
from strands import tool

REGIAO = os.environ.get("AWS_REGION", "us-east-1")
MAX_LINHAS = 200
TIMEOUT_S = 90

_PROIBIDO = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|copy|attach|detach|install|load|pragma|set|"
    r"export|import|call|checkpoint|vacuum|reset|use)\b",
    re.IGNORECASE,
)

_estado: dict = {}
_trava = threading.Lock()


def _bucket() -> str:
    b = os.environ.get("FLEXIA_BUCKET")
    if b:
        return b
    conta = boto3.client("sts", region_name=REGIAO).get_caller_identity()["Account"]
    return f"ons-datalake-{conta}"


def _iniciar() -> dict:
    """Carrega o catálogo e prepara a conexão DuckDB uma única vez por processo."""
    with _trava:
        if _estado:
            return _estado
        bucket = _bucket()
        corpo = boto3.client("s3", region_name=REGIAO).get_object(Bucket=bucket, Key="catalogo/catalogo.json")["Body"]
        catalogo = json.loads(corpo.read())

        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws;")
        con.execute(f"CREATE SECRET lake (TYPE s3, PROVIDER credential_chain, REGION '{REGIAO}')")
        con.execute("SET memory_limit='3GB'; SET threads=4;")
        for t in catalogo["tabelas"]:
            hive = "true" if t["particionada_por_ano"] else "false"
            con.execute(
                f"CREATE VIEW \"{t['nome']}\" AS SELECT * FROM read_parquet('{t['caminho']}', hive_partitioning={hive})"
            )
        con.execute(f"SET allowed_directories=['s3://{bucket}/']")
        con.execute("SET enable_external_access=false")
        con.execute("SET lock_configuration=true")

        _estado.update(con=con, catalogo=catalogo, tabelas={t["nome"]: t for t in catalogo["tabelas"]})
        return _estado


@tool
def listar_tabelas() -> str:
    """
    Lista as tabelas do data lake (ONS, clima ERA5, ANEEL e tabelas analíticas da equipe)
    com descrição, período coberto e número de linhas.

    Use SEMPRE antes de escrever SQL, para escolher a tabela certa.
    """
    st = _iniciar()
    linhas = []
    for t in st["catalogo"]["tabelas"]:
        anos = f" [anos {t['anos'][0]}–{t['anos'][1]}, particionada por ano]" if t["particionada_por_ano"] else ""
        linhas.append(f"- {t['nome']} ({t['linhas']:,} linhas){anos}: {t['descricao']}")
    return "\n".join(linhas)


@tool
def descrever_tabela(tabela: str) -> str:
    """
    Mostra as colunas de uma tabela do data lake com tipo, unidade e significado.

    Use antes de consultar uma tabela para saber nomes exatos de colunas e unidades.

    Args:
        tabela: nome da tabela, como retornado por listar_tabelas.
    """
    st = _iniciar()
    t = st["tabelas"].get(tabela)
    if not t:
        return f"Tabela '{tabela}' não existe. Use listar_tabelas."
    saida = [f"{t['nome']}: {t['descricao']}", ""]
    saida += [f"- {c['nome']} ({c['tipo']}): {c['descricao']}" for c in t["colunas"]]
    if t["particionada_por_ano"]:
        saida.append("- ano (BIGINT): partição; filtre por ano para ler menos dados")
    return "\n".join(saida)


@tool
def consultar_sql(sql: str) -> str:
    """
    Executa UMA consulta SQL somente leitura (dialeto DuckDB) no data lake e devolve até
    200 linhas em formato tabular. Use os nomes de tabela de listar_tabelas diretamente.

    Regras:
    - Apenas SELECT ou WITH ... SELECT. Um comando por chamada, sem ponto e vírgula.
    - Em tabelas particionadas, filtre por ano (ex.: WHERE ano = 2025): lê muito menos dados.
    - Agregue no SQL (sum, avg, count, group by) em vez de trazer linhas cruas.
    - Datas: TIMESTAMP '2025-01-01 00:00:00', DATE '2025-01-01', date_trunc('month', din_instante), year(...), hour(...).

    Args:
        sql: consulta SQL a executar.
    """
    consulta = sql.strip().rstrip(";").strip()
    if ";" in consulta:
        return "ERRO: envie apenas um comando SQL por chamada."
    if not re.match(r"^(select|with)\b", consulta, re.IGNORECASE) or _PROIBIDO.search(consulta):
        return "ERRO: apenas consultas SELECT/WITH somente leitura são permitidas."

    st = _iniciar()
    cur = st["con"].cursor()
    timer = threading.Timer(TIMEOUT_S, cur.interrupt)
    timer.start()
    try:
        rel = cur.execute(f"SELECT * FROM ({consulta}) AS q LIMIT {MAX_LINHAS + 1}")
        cols = [d[0] for d in rel.description]
        dados = rel.fetchall()
    except duckdb.InterruptException:
        return f"ERRO: consulta excedeu {TIMEOUT_S}s. Filtre por ano ou agregue mais."
    except duckdb.Error as e:
        return f"ERRO do DuckDB: {str(e)[:800]}"
    finally:
        timer.cancel()
        cur.close()

    if not dados:
        return "Consulta sem resultados."
    truncado = len(dados) > MAX_LINHAS
    dados = dados[:MAX_LINHAS]
    tabela = [" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in l) for l in dados]
    return "\n".join(tabela) + f"\n({len(dados)} linha(s){', TRUNCADO em 200' if truncado else ''})"
