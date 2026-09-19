"""Busca semântica da FlexIA nos documentos do setor elétrico coletados pelo Cavuca.

Índice por fonte em s3://<bucket>/docs/index/:
  <fonte>.jsonl.gz   uma linha por trecho (texto e metadados)
  <fonte>.f32        vetores float32 (Cohere Multilingual v3, 1024 dim), na mesma ordem
Os vetores ficam em memória (numpy) e são recarregados a cada 30 minutos, para refletir as
coletas agendadas sem reiniciar o agente.
"""
import gzip
import json
import os
import re
import threading
import time
import unicodedata

import boto3
import numpy as np
from strands import tool

from tools.data_lake_tools import _bucket

# região do lake e dos modelos; independe da região onde o runtime roda (o AgentCore define AWS_REGION)
REGIAO = os.environ.get("FLEXIA_REGIAO", "us-east-1")
MODELO_EMBED = "cohere.embed-multilingual-v3"
DIM = 1024
RECARREGAR_S = 30 * 60

_s3 = boto3.client("s3", region_name=REGIAO)
_bedrock = boto3.client("bedrock-runtime", region_name=REGIAO)
_trava = threading.Lock()
_indice: dict = {"carregado_em": 0.0, "meta": [], "vetores": np.zeros((0, DIM), dtype=np.float32)}


def _carregar() -> dict:
    with _trava:
        if time.time() - _indice["carregado_em"] < RECARREGAR_S:
            return _indice
        bucket = _bucket()
        chaves = []
        for pag in _s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="docs/index/"):
            chaves += [o["Key"] for o in pag.get("Contents", []) if o["Key"].endswith(".jsonl.gz")]
        metas, blocos = [], []
        for k in chaves:
            base = k[: -len(".jsonl.gz")]
            linhas = gzip.decompress(_s3.get_object(Bucket=bucket, Key=k)["Body"].read()).decode("utf-8").splitlines()
            vet = np.frombuffer(_s3.get_object(Bucket=bucket, Key=base + ".f32")["Body"].read(), dtype="<f4")
            vet = vet.reshape(-1, DIM)
            if len(vet) != len(linhas):  # índice sendo reescrito: ignora esta fonte até a próxima carga
                continue
            for l in linhas:
                m = json.loads(l)
                m["_norm"] = _normalizar(f"{m['titulo']} {m['texto']}")
                metas.append(m)
            blocos.append(vet)
        vetores = np.vstack(blocos) if blocos else np.zeros((0, DIM), dtype=np.float32)
        vetores = vetores / np.maximum(np.linalg.norm(vetores, axis=1, keepdims=True), 1e-9)
        _indice.update(carregado_em=time.time(), meta=metas, vetores=vetores.astype(np.float32))
        return _indice


_VAZIAS = {"sobre", "quais", "qual", "como", "quando", "onde", "define", "definicao", "diz", "para", "pelo",
            "pela", "entre", "segundo", "ultimas", "noticias", "energia", "eletrica", "setor", "lei"}


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def _termos(pergunta: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9.º°/-]*", _normalizar(pergunta))
    return list(dict.fromkeys(t.strip(".") for t in tokens
                              if (len(t) >= 5 or any(c.isdigit() for c in t)) and t not in _VAZIAS))


def aquecer() -> int:
    return len(_carregar()["meta"])


@tool
def buscar_documentos(pergunta: str, orgao: str = "", tipo: str = "", quantidade: int = 8) -> str:
    """
    Busca trechos relevantes em documentos públicos do setor elétrico coletados periodicamente:
    - Procedimentos de Rede do ONS (159 submódulos vigentes, texto integral; orgao="ONS", tipo="procedimentos")
    - decisões das Reuniões Públicas da Diretoria da ANEEL (processo, relator, assunto, decisão, ato)
    - leis e decretos do setor (Planalto), resoluções do CNPE, agenda regulatória e procedimentos da ANEEL,
      regras de comercialização da CCEE
    - notícias (ANEEL, MME, CCEE, EPE), publicações da EPE, catálogos de dados abertos (ONS, ANEEL, CCEE)
    - manchetes de mídias do setor (só título, data, veículo e link: cite como manchete, com o link)

    Use para perguntas sobre regulação, legislação, notícias, eventos, definições e contexto.
    Para números de operação (geração, carga, CMO, corte), use consultar_sql.
    Cite sempre o título e a URL dos trechos usados.

    Filtros: comece SEM o filtro `tipo` — notícias costumam trazer os números e conclusões das
    publicações e notas técnicas. Se a resposta não aparecer nos trechos, repita a busca sem
    nenhum filtro e com outras palavras antes de concluir que a informação não existe.

    Args:
        pergunta: a pergunta ou o tema a buscar, em linguagem natural.
        orgao: filtro opcional: ANEEL, MME, CCEE, EPE, ONS ou Planalto.
        tipo: filtro opcional: noticias, legislacao, regulacao, procedimentos, publicacoes, dados_abertos.
        quantidade: número de trechos (1 a 10).
    """
    try:
        idx = _carregar()
    except Exception as e:  # noqa: BLE001
        return f"ERRO: índice de documentos indisponível ({str(e)[:200]})."
    if not idx["meta"]:
        return "O índice de documentos ainda está vazio (nenhuma coleta concluída)."

    corpo = json.dumps({"texts": [pergunta[:2000]], "input_type": "search_query"})
    q = np.asarray(json.loads(_bedrock.invoke_model(modelId=MODELO_EMBED, body=corpo)["body"].read())["embeddings"][0],
                   dtype=np.float32)
    scores = idx["vetores"] @ (q / max(np.linalg.norm(q), 1e-9))
    # Busca híbrida: bônus léxico para termos distintivos da pergunta (números de lei/artigo,
    # siglas, palavras longas) que aparecem literalmente no trecho.
    termos = _termos(pergunta)
    if termos:
        lexico = np.array([sum(t in m["_norm"] for t in termos) / len(termos) for m in idx["meta"]],
                          dtype=np.float32)
        scores = scores + 0.15 * lexico

    mascara = np.ones(len(scores), dtype=bool)
    if orgao or tipo:
        mascara = np.array([(not orgao or orgao.lower() in m["orgao"].lower()) and (not tipo or m["tipo"] == tipo)
                            for m in idx["meta"]])
    candidatos = np.where(mascara)[0]
    if not len(candidatos):
        return "Nenhum documento encontrado com esses filtros."
    k = max(1, min(int(quantidade), 10))
    # Diversidade: no máximo 3 trechos por documento, para uma página longa não ocupar todo o
    # resultado e esconder a notícia/lei que tem a resposta.
    melhores, por_doc = [], {}
    for j in candidatos[np.argsort(-scores[candidatos])]:
        doc = idx["meta"][j]["doc_id"]
        if por_doc.get(doc, 0) < 3:
            melhores.append(j)
            por_doc[doc] = por_doc.get(doc, 0) + 1
        if len(melhores) == k:
            break

    blocos = []
    for i, j in enumerate(melhores, 1):
        m = idx["meta"][j]
        blocos.append(f"[{i}] {m['titulo']} — {m['orgao']} ({m['tipo']}), coletado em {m['coletado_em'][:10]}, "
                      f"relevância {scores[j]:.2f}\nURL: {m['url']}\n{m['texto']}")
    return "\n\n---\n\n".join(blocos)
