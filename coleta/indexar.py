"""Indexa os documentos coletados para busca semântica (RAG) da FlexIA.

Para cada fonte com documentos novos: divide o Markdown em trechos, gera embeddings
(Cohere Embed Multilingual v3 no Bedrock, 1024 dimensões, bom para português) e grava
docs/index/<fonte>.jsonl.gz (texto e metadados) + docs/index/<fonte>.f32 (vetores float32).
Só entram as versões atuais de cada URL (docs/estado/<fonte>.json). A FlexIA carrega os vetores
em memória e busca por similaridade de cosseno com numpy, sem banco vetorial (OpenSearch e
S3 Vectors estão bloqueados na conta do workshop).

Uso:
  python coleta/indexar.py [--local out/docs] [--fonte ID ...]
"""
import argparse
import gzip
import json
import os
import re
import sys
from array import array
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coletor import Destino  # noqa: E402
from fontes import FONTES  # noqa: E402

MODELO_EMBED = "cohere.embed-multilingual-v3"
DIM = 1024
TAM_TRECHO = 1500
SOBREPOSICAO = 200
LOTE = 96  # máximo de textos por chamada do Cohere Embed
REGIAO = os.environ.get("AWS_REGION", "us-east-1")


def trechos(texto: str) -> list[str]:
    """Divide respeitando títulos e parágrafos; trechos de ~1500 caracteres com 200 de sobreposição."""
    corpo = texto.split("\n---\n", 1)[-1] if texto.startswith("---") else texto
    blocos = [b.strip() for b in re.split(r"\n(?=#{1,6} )|\n{2,}", corpo) if b.strip()]
    saida, atual = [], ""
    for b in blocos:
        while len(b) > TAM_TRECHO:  # parágrafo gigante (ex.: texto de lei)
            corte = b.rfind(" ", 0, TAM_TRECHO)
            corte = corte if corte > TAM_TRECHO // 2 else TAM_TRECHO
            if atual:
                saida.append(atual)
                atual = ""
            saida.append(b[:corte])
            b = b[max(corte - SOBREPOSICAO, 0):]
        if len(atual) + len(b) + 2 > TAM_TRECHO and atual:
            saida.append(atual)
            atual = atual[-SOBREPOSICAO:] + "\n\n" + b
        else:
            atual = f"{atual}\n\n{b}" if atual else b
    if atual:
        saida.append(atual)
    return saida


def embed(bedrock, textos: list[str], tipo: str = "search_document") -> list[list[float]]:
    vetores = []
    for i in range(0, len(textos), LOTE):
        corpo = json.dumps({"texts": [t[:2048] for t in textos[i:i + LOTE]], "input_type": tipo, "truncate": "END"})
        r = bedrock.invoke_model(modelId=MODELO_EMBED, body=corpo)
        vetores += json.loads(r["body"].read())["embeddings"]
    return vetores


class Leitor:
    """Lista e lê objetos em docs/raw no S3 ou numa pasta local."""

    def __init__(self, destino: Destino):
        self.d = destino

    def listar(self, prefixo: str) -> list[str]:
        if self.d.bucket:
            chaves = []
            for pag in self.d.s3.get_paginator("list_objects_v2").paginate(Bucket=self.d.bucket, Prefix=prefixo):
                chaves += [o["Key"] for o in pag.get("Contents", [])]
            return chaves
        base = self.d.pasta / prefixo
        return [p.relative_to(self.d.pasta).as_posix() for p in base.rglob("*")] if base.exists() else []

    def ler(self, chave: str) -> bytes:
        if self.d.bucket:
            return self.d.s3.get_object(Bucket=self.d.bucket, Key=chave)["Body"].read()
        return (self.d.pasta / chave).read_bytes()


def indexar_fonte(fonte_id: str, destino: Destino, bedrock) -> dict:
    leitor = Leitor(destino)
    estado = destino.ler_json(f"docs/estado/{fonte_id}.json")
    atuais = {sha[:16] for sha in estado.values()}
    metas = [c for c in leitor.listar(f"docs/raw/{fonte_id}/") if c.endswith(".json")]
    metas = [c for c in metas if Path(c).stem in atuais]
    chave_idx = f"docs/index/{fonte_id}"
    marca = f"docs/index/{fonte_id}.versao.json"
    assinatura = sorted(atuais)
    if destino.ler_json(marca).get("docs") == assinatura:
        return {"fonte": fonte_id, "status": "sem mudança", "documentos": len(metas)}

    linhas = []
    for c in metas:
        meta = json.loads(leitor.ler(c))
        texto = leitor.ler(c[:-5] + ".md").decode("utf-8")
        for i, t in enumerate(trechos(texto)):
            linhas.append({"doc_id": meta["sha256"][:16], "trecho": i, "texto": t, "url": meta["url"],
                           "titulo": meta["titulo"], "orgao": meta["orgao"], "tipo": meta["tipo"],
                           "fonte": meta["fonte"], "coletado_em": meta["coletado_em"]})
    if not linhas:
        return {"fonte": fonte_id, "status": "sem documentos"}
    # O título entra no texto embutido para dar contexto ao trecho.
    vetores = embed(bedrock, [f"{l['titulo']}\n{l['texto']}" for l in linhas])
    # Formato sem pyarrow (cabe na Lambda): metadados em JSONL.gz e vetores float32 contíguos,
    # linha i do JSONL <-> vetor i do .f32.
    jsonl = "\n".join(json.dumps(l, ensure_ascii=False) for l in linhas).encode("utf-8")
    matriz = array("f", (x for v in vetores for x in v))
    if sys.byteorder != "little":
        matriz.byteswap()
    destino.gravar(chave_idx + ".jsonl.gz", gzip.compress(jsonl), "application/gzip")
    destino.gravar(chave_idx + ".f32", matriz.tobytes(), "application/octet-stream")
    destino.gravar(marca, json.dumps({"docs": assinatura, "trechos": len(linhas), "dim": DIM}).encode(),
                   "application/json")
    return {"fonte": fonte_id, "status": "indexada", "documentos": len(metas), "trechos": len(linhas)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", action="append")
    ap.add_argument("--local")
    a = ap.parse_args()
    destino = Destino(pasta=a.local) if a.local else Destino(bucket=os.environ["FLEXIA_BUCKET"])
    bedrock = boto3.client("bedrock-runtime", region_name=REGIAO)
    for fid in a.fonte or [f["id"] for f in FONTES if f["ativa"]]:
        print(json.dumps(indexar_fonte(fid, destino, bedrock), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
