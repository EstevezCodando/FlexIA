"""Handler da Lambda flexia-coletor.

Eventos:
  {"frequencia": "diaria"|"semanal"|"mensal"}  (EventBridge) -> dispara uma invocação assíncrona por fonte
  {"fonte": "<id>"}                                            -> coleta a fonte e reindexa o que mudou
"""
import json
import logging
import os

import boto3

from coletor import Destino, coletar_fonte
from fontes import FONTES, POR_ID
from indexar import indexar_fonte

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("cavuca").setLevel(logging.WARNING)
BUCKET = os.environ["FLEXIA_BUCKET"]
REGIAO = os.environ.get("AWS_REGION", "us-east-1")


def handler(event, context):
    if "frequencia" in event:
        cliente = boto3.client("lambda", region_name=REGIAO)
        fontes = [f["id"] for f in FONTES if f["frequencia"] == event["frequencia"] and f["ativa"]]
        for fid in fontes:
            cliente.invoke(FunctionName=context.function_name, InvocationType="Event",
                           Payload=json.dumps({"fonte": fid}).encode())
        return {"disparadas": fontes}

    fonte = POR_ID[event["fonte"]]
    destino = Destino(bucket=BUCKET)
    coleta = coletar_fonte(fonte, destino)
    indice = indexar_fonte(fonte["id"], destino, boto3.client("bedrock-runtime", region_name=REGIAO))
    resultado = {"coleta": coleta, "indice": indice}
    logging.info(json.dumps(resultado, ensure_ascii=False))
    return resultado
