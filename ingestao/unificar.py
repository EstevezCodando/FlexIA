"""Unificação genérica de arquivos de um mesmo conjunto de dados numa tabela Parquet tipada.

Serve para qualquer fonte (ONS, ANEEL, CCEE, EPE): recebe a lista de arquivos (Parquet ou CSV),
descobre o esquema de cada um e resolve conflitos de tipo entre arquivos, que são comuns nas
fontes públicas (o mesmo campo como texto num ano e número no outro, datas como texto etc.):

  - mesmo tipo em todos os arquivos          -> mantém
  - só tipos numéricos                        -> BIGINT (se todos inteiros) ou DOUBLE
  - texto + número, ou texto com cara de número (vírgula decimal) -> DOUBLE, se TODOS os valores
    não nulos de uma amostra convertem; senão VARCHAR
  - datas/horas misturadas ou em texto        -> TIMESTAMP (ou DATE), se todos convertem
Nomes de coluna viram minúsculos sem acento. Séries temporais grandes são particionadas por ano.
"""
import re
import shutil
import unicodedata
from pathlib import Path

import duckdb

NUMERICOS = {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER",
             "UBIGINT", "FLOAT", "DOUBLE", "DECIMAL"}
INTEIROS = NUMERICOS - {"FLOAT", "DOUBLE", "DECIMAL"}
TEMPORAIS = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_NS", "TIMESTAMP_MS", "TIMESTAMP_S"}
AMOSTRA = 200_000
LIMIAR_PARTICAO = 300_000  # linhas; acima disso, particiona por ano se houver coluna temporal


def nome_coluna(c: str) -> str:
    c = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", c).strip("_") or "coluna"


def base_tipo(t: str) -> str:
    return re.sub(r"\(.*\)", "", t).strip().upper()


def leitor(p: Path, csv_opcoes: str = "") -> str:
    if p.suffix.lower() == ".parquet":
        return f"read_parquet('{p.as_posix()}')"
    opcoes = csv_opcoes or "delim=';', header=true"
    return (f"read_csv('{p.as_posix()}', {opcoes}, all_varchar=true, ignore_errors=true, "
            f"null_padding=true, strict_mode=false)")


def _parece_data(nome: str) -> bool:
    return bool(re.match(r"^(din|dat|dt|data|dia|mes|ano_mes|periodo|hora)(_|$)", nome) or
                re.search(r"(_data|_dia|_inicio|_fim|_referencia|_instante)$", nome) or
                re.search(r"^(dat|data)", nome))


def _eh_codigo(nome: str) -> bool:
    return bool(re.match(r"^(id|cod|ceg|ide|sig|nom|dsc|num_cnpj|num_cpf|cnpj|cpf|cep|codigo|sgl|tip)(_|$)", nome) or
                re.search(r"(cnpj|cpf|_cep|codigo|_ceg|_id|_cod)$", nome))


def _num_expr(col: str) -> str:
    """Texto -> número aceitando '1.234,56', '1234,56', '1234.56' e espaços."""
    c = f'trim(CAST("{col}" AS VARCHAR))'
    return (f"TRY_CAST(CASE WHEN {c} LIKE '%,%' THEN replace(replace({c}, '.', ''), ',', '.') ELSE {c} END AS DOUBLE)")


def _data_expr(col: str) -> str:
    c = f'trim(CAST("{col}" AS VARCHAR))'
    return (f"COALESCE(TRY_CAST({c} AS TIMESTAMP), TRY_STRPTIME({c}, '%d/%m/%Y %H:%M:%S'), "
            f"TRY_STRPTIME({c}, '%d/%m/%Y %H:%M'), TRY_STRPTIME({c}, '%d/%m/%Y'), "
            f"TRY_STRPTIME({c}, '%Y%m%d'), TRY_STRPTIME({c}, '%m/%Y'), TRY_STRPTIME({c}, '%Y-%m'), "
            f"CASE WHEN length({c}) = 6 THEN TRY_STRPTIME({c}, '%Y%m') END)")


def unificar(arquivos: list[Path], destino: Path, csv_opcoes: str = "", log=print) -> dict:
    """Gera destino/ (Parquet ZSTD, particionado por ano quando grande). Retorna um resumo."""
    con = duckdb.connect()
    con.execute("SET memory_limit='12GB'; SET preserve_insertion_order=false")
    esquemas, ordem, originais = {}, [], {}
    for p in arquivos:
        cols = con.execute(f"DESCRIBE SELECT * FROM {leitor(p, csv_opcoes)}").fetchall()
        esquemas[p] = {}
        for c in cols:
            n = nome_coluna(c[0])
            esquemas[p][n] = (c[0], base_tipo(c[1]))
            if n not in ordem:
                ordem.append(n)

    alvo = {}
    for n in ordem:
        tipos = {esquemas[p][n][1] for p in arquivos if n in esquemas[p]}
        if len(tipos) == 1 and tipos <= (NUMERICOS | TEMPORAIS | {"BOOLEAN"}):
            alvo[n] = tipos.pop()
            continue
        if tipos <= NUMERICOS:
            alvo[n] = "BIGINT" if tipos <= INTEIROS else "DOUBLE"
            continue
        if (tipos & TEMPORAIS or _parece_data(n)) and _converte(con, arquivos, esquemas, n, _data_expr, csv_opcoes):
            alvo[n] = "TIMESTAMP"
            continue
        # nome com cara de data que não converte (ex.: pld_media_dia = valor em R$/MWh) segue as regras abaixo
        # códigos e identificadores ficam texto (preserva zeros à esquerda: CEG, CNPJ, códigos de usina)
        if _eh_codigo(n):
            alvo[n] = "VARCHAR"
            continue
        # texto (ou texto + número): numérico só se toda a amostra converter
        alvo[n] = "DOUBLE" if _converte(con, arquivos, esquemas, n, _num_expr, csv_opcoes) else "VARCHAR"

    selects = []
    for p in arquivos:
        partes = []
        for n in ordem:
            if n not in esquemas[p]:
                partes.append(f'CAST(NULL AS {alvo[n]}) AS "{n}"')
                continue
            orig, tipo = esquemas[p][n]
            if alvo[n] == tipo:
                partes.append(f'"{orig}" AS "{n}"')
            elif alvo[n] == "DOUBLE":
                partes.append(f'{_num_expr(orig)} AS "{n}"')
            elif alvo[n] == "TIMESTAMP":
                partes.append(f'{_data_expr(orig)} AS "{n}"')
            elif alvo[n] == "VARCHAR":
                partes.append(f'NULLIF(trim(CAST("{orig}" AS VARCHAR)), \'\') AS "{n}"')
            else:
                partes.append(f'TRY_CAST("{orig}" AS {alvo[n]}) AS "{n}"')
        selects.append(f"SELECT {', '.join(partes)} FROM {leitor(p, csv_opcoes)}")
    sql = "\nUNION ALL BY NAME\n".join(selects)

    # datas sem hora viram DATE (mais legível para o modelo)
    for n in [n for n in ordem if alvo[n] == "TIMESTAMP"]:
        so_data = con.execute(f"SELECT count(*) FILTER (WHERE \"{n}\" <> date_trunc('day', \"{n}\")) = 0 "
                              f"FROM (SELECT \"{n}\" FROM ({sql}) LIMIT {AMOSTRA})").fetchone()[0]
        if so_data:
            alvo[n] = "DATE"
    def coluna_final(n: str) -> str:
        if alvo[n] not in ("DATE", "TIMESTAMP"):
            return f'"{n}"'
        # 1900-01-01 e 1899-12-30 (marco zero do Excel) são marcadores de "sem data" nas fontes
        col = (f'CASE WHEN CAST("{n}" AS DATE) IN (DATE \'1900-01-01\', DATE \'1899-12-30\') '
               f'THEN NULL ELSE "{n}" END')
        return f'CAST({col} AS DATE) AS "{n}"' if alvo[n] == "DATE" else f'{col} AS "{n}"'

    final = ", ".join(coluna_final(n) for n in ordem)
    sql = f"SELECT {final} FROM ({sql})"

    linhas = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
    # coluna temporal principal: a data com mais valores distintos, evitando datas de geração do arquivo
    # datas de geração/processamento do arquivo não descrevem o período dos dados: nunca são a coluna temporal
    temporais = [n for n in ordem if alvo[n] in ("DATE", "TIMESTAMP") and n != "ano"
                 and not re.search(r"geracaoconjunto|processamento|atualiza|carga_dados|dataversao|versao", n)]
    tempo = None
    if temporais:
        distintos = con.execute("SELECT " + ", ".join(f'approx_count_distinct("{n}")' for n in temporais) +
                                f" FROM (SELECT * FROM ({sql}) LIMIT {AMOSTRA})").fetchone()
        tempo = max(zip(temporais, distintos), key=lambda nd: nd[1])[0]
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    particionar = bool(tempo) and linhas > LIMIAR_PARTICAO
    if particionar:
        con.execute(f"COPY (SELECT *, year(\"{tempo}\") AS ano FROM ({sql}) WHERE \"{tempo}\" IS NOT NULL) "
                    f"TO '{destino.as_posix()}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (ano), "
                    f"ROW_GROUP_SIZE 500000, FILENAME_PATTERN 'part_{{i}}')")
        sem_data = con.execute(f"SELECT count(*) FROM ({sql}) WHERE \"{tempo}\" IS NULL").fetchone()[0]
        if sem_data:
            log(f"    aviso: {sem_data} linhas sem {tempo} ficaram fora da partição")
    else:
        con.execute(f"COPY ({sql}) TO '{(destino / 'part_0.parquet').as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    periodo = None
    if tempo:
        periodo = [str(x) if x is not None else None for x in
                   con.execute(f"SELECT min(\"{tempo}\"), max(\"{tempo}\") FROM ({sql})").fetchone()]
    return {"linhas": linhas, "colunas": {n: alvo[n] for n in ordem}, "coluna_tempo": tempo,
            "particionada_por_ano": particionar, "periodo": periodo, "arquivos": len(arquivos)}


def _converte(con, arquivos, esquemas, n, expr, csv_opcoes) -> bool:
    """True se todo valor não nulo (numa amostra por arquivo) converte com expr."""
    for p in arquivos:
        if n not in esquemas[p]:
            continue
        orig = esquemas[p][n][0]
        falhas, validos = con.execute(
            f"SELECT count(*) FILTER (WHERE v IS NOT NULL AND trim(CAST(v AS VARCHAR)) <> '' AND conv IS NULL), "
            f"count(*) FILTER (WHERE conv IS NOT NULL) "
            f"FROM (SELECT \"{orig}\" AS v, {expr(orig)} AS conv FROM {leitor(p, csv_opcoes)} LIMIT {AMOSTRA})"
        ).fetchone()
        if falhas:
            return False
    return True
