"""Conexão da interface com a FlexIA: agente local (mesmo processo) ou runtime no Bedrock AgentCore.

Os dois modos produzem a mesma sequência de eventos simples:
  ("texto", str)          pedaço da resposta
  ("ferramenta", nome)    o agente começou a usar uma ferramenta
  ("decisao", dict)       rota e modelo escolhidos pelo roteador (só no modo local)
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

AGENTE = Path(__file__).resolve().parent.parent / "app" / "SINAgent"


def _evento_agente(ev: dict):
    """Converte um evento do Strands/AgentCore em evento simples (ou None)."""
    ev = ev.get("event", {}) if isinstance(ev, dict) else {}
    delta = ev.get("contentBlockDelta", {}).get("delta", {})
    if "text" in delta:
        return ("texto", delta["text"])
    uso = ev.get("contentBlockStart", {}).get("start", {}).get("toolUse")
    if uso:
        return ("ferramenta", uso["name"])
    return None


def perguntar_local(pergunta: str, sessao: str) -> Iterator[tuple]:
    if str(AGENTE) not in sys.path:
        sys.path.insert(0, str(AGENTE))
    import main  # noqa: PLC0415

    loop = asyncio.new_event_loop()
    fluxo = main.invoke({"prompt": pergunta}, SimpleNamespace(session_id=sessao))
    try:
        while True:
            try:
                ev = loop.run_until_complete(fluxo.__anext__())
            except StopAsyncIteration:
                break
            simples = _evento_agente(ev)
            if simples:
                yield simples
    finally:
        loop.close()
    if sessao in main.ULTIMAS_DECISOES:
        yield ("decisao", main.ULTIMAS_DECISOES[sessao])


def perguntar_agentcore(pergunta: str, sessao: str) -> Iterator[tuple]:
    import boto3  # noqa: PLC0415

    arn = os.environ["FLEXIA_RUNTIME_ARN"]
    cliente = boto3.client("bedrock-agentcore", region_name=arn.split(":")[3])  # região do runtime, não a do lake
    resp = cliente.invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=sessao,
        payload=json.dumps({"prompt": pergunta}).encode(),
    )
    for linha in resp["response"].iter_lines():
        if not linha or not linha.startswith(b"data:"):
            continue
        try:
            simples = _evento_agente(json.loads(linha[5:].strip()))
        except json.JSONDecodeError:
            continue
        if simples:
            yield simples


def perguntar(pergunta: str, sessao: str, modo: str) -> Iterator[tuple]:
    return perguntar_agentcore(pergunta, sessao) if modo == "agentcore" else perguntar_local(pergunta, sessao)


def aquecer_local() -> None:
    """Carrega o agente (DuckDB, catálogo e índice) antes da primeira pergunta."""
    if str(AGENTE) not in sys.path:
        sys.path.insert(0, str(AGENTE))
    import main  # noqa: PLC0415, F401
