"""Busca semântica da FlexIA nos documentos do setor elétrico coletados pelo Cavuca.

Índice: s3://<bucket>/docs/index/*.parquet (texto, metadados e embedding Cohere Multilingual v3).
O índice é carregado em memória no DuckDB e recarregado a cada 30 minutos, para refletir as
coletas agendadas sem reiniciar o agente.
"""
import json
import os
import threading
import time

import boto3
from strands import tool

from tools.data_lake_tools import _bucket, _iniciar

REGIAO = os.environ.get("AWS_REGION", "us-east-1")
MODELO_EMBED = "cohere.embed-multilingual-v3"
RECARREGAR_S = 30 * 60

_bedrock = boto3.client("bedrock-runtime", region_name=REGIAO)
_trava = threading.Lock()
_carregado_em = 0.0


def _garantir_indice(con) -> None:
    global _carregado_em
    with _trava:
        if time.time() - _carregado_em < RECARREGAR_S:
            return
        con.execute(
            f"CREATE OR REPLACE TABLE docs_indice AS "
            f"SELECT * FROM read_parquet('s3://{_bucket()}/docs/index/*.parquet', union_by_name=true)"
        )
        _carregado_em = time.time()


@tool
def buscar_documentos(pergunta: str, orgao: str = "", tipo: str = "", quantidade: int = 6) -> str:
    """
    Busca trechos relevantes em documentos públicos do setor elétrico coletados periodicamente:
    notícias (ANEEL, MME, CCEE, EPE), leis e decretos do setor (Planalto), procedimentos
    regulatórios (ANEEL/CCEE), publicações da EPE e catálogos de dados abertos (ONS, ANEEL, CCEE).

    Use para perguntas sobre regulação, legislação, notícias, eventos, definições e contexto.
    Para números de operação (geração, carga, CMO, corte), use consultar_sql.
    Cite sempre o título e a URL dos trechos usados.

    Args:
        pergunta: a pergunta ou o tema a buscar, em linguagem natural.
        orgao: filtro opcional: ANEEL, MME, CCEE, EPE, ONS ou "Presidência (Planalto)".
        tipo: filtro opcional: noticias, legislacao, regulacao, procedimentos, publicacoes, dados_abertos.
        quantidade: número de trechos (1 a 10).
    """
    st = _iniciar()
    con = st["con"]
    try:
        _garantir_indice(con)
    except Exception as e:  # noqa: BLE001
        return f"ERRO: índice de documentos indisponível ({str(e)[:200]})."
    corpo = json.dumps({"texts": [pergunta[:2000]], "input_type": "search_query"})
    vetor = json.loads(_bedrock.invoke_model(modelId=MODELO_EMBED, body=corpo)["body"].read())["embeddings"][0]

    filtros, params = [], [vetor]
    if orgao:
        filtros.append("orgao ILIKE ?")
        params.append(f"%{orgao}%")
    if tipo:
        filtros.append("tipo = ?")
        params.append(tipo)
    where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    k = max(1, min(int(quantidade), 10))
    cur = con.cursor()
    try:
        linhas = cur.execute(
            f"SELECT list_cosine_similarity(embedding, ?::FLOAT[]) AS score, titulo, orgao, tipo, url, "
            f"coletado_em, texto FROM docs_indice {where} ORDER BY score DESC LIMIT {k}",
            params,
        ).fetchall()
    finally:
        cur.close()
    if not linhas:
        return "Nenhum documento encontrado com esses filtros."
    blocos = []
    for i, (score, titulo, org, tp, url, coletado, texto) in enumerate(linhas, 1):
        blocos.append(f"[{i}] {titulo} — {org} ({tp}), coletado em {coletado[:10]}, relevância {score:.2f}\n"
                      f"URL: {url}\n{texto}")
    return "\n\n---\n\n".join(blocos)
