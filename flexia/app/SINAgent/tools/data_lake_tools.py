"""Ferramentas da FlexIA para consultar o data lake do Hackathon ONS.

O motor é o DuckDB lendo Parquet direto do S3 (a conta do workshop não permite Glue/Athena).
Cada tabela do catálogo vira uma VIEW; tabelas grandes são particionadas por `ano`.

Isolamento: o DuckDB só acessa o prefixo do bucket do lake, a configuração é travada
e só SELECT/WITH é aceito.

Variáveis de ambiente:
  FLEXIA_BUCKET  bucket do lake (padrão: ons-datalake-<conta>)
  FLEXIA_REGIAO  região do bucket e do Bedrock (padrão us-east-1; o runtime pode estar em outra região)
"""
import json
import os
import re
import threading

import boto3
import duckdb
from strands import tool

# região do lake e dos modelos; independe da região onde o runtime roda (o AgentCore define AWS_REGION)
REGIAO = os.environ.get("FLEXIA_REGIAO", "us-east-1")
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
        # no contêiner do AgentCore o diretório pessoal pode ser somente leitura: extensões no temporário
        import tempfile
        pasta_ext = os.path.join(tempfile.gettempdir(), "duckdb_ext").replace("\\", "/")
        con.execute(f"SET extension_directory='{pasta_ext}'")
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws;")
        con.execute(f"CREATE SECRET lake (TYPE s3, PROVIDER credential_chain, REGION '{REGIAO}')")
        con.execute("SET memory_limit='3GB'; SET threads=4;")
        for t in catalogo["tabelas"]:
            hive = "true" if t.get("hive", t["particionada_por_ano"]) else "false"
            con.execute(
                f"CREATE VIEW \"{t['nome']}\" AS SELECT * FROM read_parquet('{t['caminho']}', hive_partitioning={hive})"
            )
        con.execute(f"SET allowed_directories=['s3://{bucket}/']")
        con.execute("SET enable_external_access=false")
        con.execute("SET lock_configuration=true")

        _estado.update(con=con, catalogo=catalogo, tabelas={t["nome"]: t for t in catalogo["tabelas"]})
        return _estado


def _normalizar(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


@tool
def listar_tabelas(busca: str = "", tema: str = "") -> str:
    """
    Lista as tabelas do data lake — cerca de 100, de ONS, ANEEL, CCEE, EPE, clima ERA5 e análises
    da equipe — com fonte, período, número de linhas e descrição, agrupadas por fonte.

    Use SEMPRE antes de escrever SQL. Com muitas tabelas, FILTRE:
      busca: palavras-chave (ex.: "reservatorio", "pld", "consumo industrial", "geracao distribuida").
             Retorna tabelas cujo nome ou descrição contém TODAS as palavras.
      tema:  um de hidrologia, carga, precos, geracao, restricao, intercambio, transmissao, mercado,
             qualidade, confiabilidade, planejamento, cadastro, clima, mobilidade, operacao.
    Sem filtros, devolve só nome, fonte e período de cada tabela (visão geral).
    """
    st = _iniciar()
    termos = _normalizar(busca).split()
    detalhado = bool(termos or tema)
    por_fonte: dict[str, list[str]] = {}
    for t in st["catalogo"]["tabelas"]:
        alvo = _normalizar(f"{t['nome']} {t['descricao']} {t.get('tema', '')}")
        if termos and not all(x in alvo for x in termos):
            continue
        if tema and _normalizar(tema) != _normalizar(t.get("tema", "")):
            continue
        per = t.get("periodo") or (t["anos"] and [str(t["anos"][0]), str(t["anos"][1])])
        per_txt = f" · {str(per[0])[:10]} a {str(per[1])[:10]}" if per and per[0] else ""
        part = " · particionada por ano" if t["particionada_por_ano"] else ""
        if detalhado:
            linha = f"- {t['nome']} ({t['linhas']:,} linhas{per_txt}{part}): {t['descricao'][:400]}"
        else:
            linha = f"- {t['nome']} [{t.get('tema', '')}] ({t['linhas']:,} linhas{per_txt})"
        por_fonte.setdefault(t.get("fonte", "?"), []).append(linha)
    if not por_fonte:
        return "Nenhuma tabela encontrada. Tente outras palavras ou liste sem filtros."
    saida = []
    for fonte, linhas in sorted(por_fonte.items()):
        saida.append(f"## {fonte} ({len(linhas)})")
        saida += linhas
    if not detalhado:
        saida.append("\nUse listar_tabelas(busca=...) para ver descrições, e descrever_tabela para as colunas.")
    return "\n".join(saida)


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
    saida = [f"{t['nome']}: {t['descricao']}"]
    if t.get("fonte"):
        saida.append(f"Fonte: {t['fonte']} · dicionário: {t.get('dicionario') or 'n/d'}"
                     + (f" · origem: {t['origem']}" if t.get("origem") else ""))
    if t.get("periodo") and t["periodo"][0]:
        saida.append(f"Período: {t['periodo'][0]} a {t['periodo'][1]} (coluna {t.get('coluna_tempo')})")
    saida.append("")
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
