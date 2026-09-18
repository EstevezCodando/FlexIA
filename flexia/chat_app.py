"""Chat da FlexIA (Streamlit) com respostas em streaming.

Modos:
  FLEXIA_MODO=local      chama o agente direto neste processo (padrão; bom para desenvolver e demonstrar)
  FLEXIA_MODO=agentcore  chama o runtime implantado no Bedrock AgentCore (FLEXIA_RUNTIME_ARN)

Rodar:
  streamlit run flexia/chat_app.py
No Code Editor do workshop, abra a porta 8501 pela aba PORTS (ou /proxy/8501/).
"""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

MODO = os.environ.get("FLEXIA_MODO", "local")
REGIAO = os.environ.get("AWS_REGION", "us-east-1")

st.set_page_config(page_title="FlexIA", page_icon="⚡", layout="centered")
st.title("⚡ FlexIA")
st.caption("Copiloto do setor elétrico: dados do ONS, clima, tarifas, leis e notícias do setor.")

if "sessao" not in st.session_state:
    st.session_state.sessao = f"chat-{uuid.uuid4()}"
    st.session_state.mensagens = []

with st.sidebar:
    st.markdown(f"**Modo:** `{MODO}`")
    st.markdown("**Exemplos**")
    exemplos = [
        "Qual foi o CMO médio de cada subsistema em 2025?",
        "Quanto de energia eólica e solar foi cortada em 2025, por razão?",
        "O que a Lei 14.300 define sobre o sistema de compensação?",
        "Quais as últimas notícias da CCEE?",
        "Compare o corte eólico no Nordeste entre 2024 e 2025 e explique o contexto regulatório.",
    ]
    for ex in exemplos:
        if st.button(ex, use_container_width=True):
            st.session_state.pendente = ex
    if st.button("Nova conversa", type="secondary"):
        st.session_state.sessao = f"chat-{uuid.uuid4()}"
        st.session_state.mensagens = []
        st.rerun()


def _textos_local(pergunta: str):
    """Gera pedaços de texto do agente rodando neste processo."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "app" / "SINAgent"))
    import main  # noqa: PLC0415

    fila: list = []

    async def coletar():
        ctx = SimpleNamespace(session_id=st.session_state.sessao)
        async for ev in main.invoke({"prompt": pergunta}, ctx):
            fila.append(ev)

    loop = asyncio.new_event_loop()
    tarefa = loop.create_task(coletar())
    while not tarefa.done() or fila:
        loop.run_until_complete(asyncio.sleep(0.05)) if not tarefa.done() else None
        while fila:
            ev = fila.pop(0)["event"]
            delta = ev.get("contentBlockDelta", {}).get("delta", {})
            if "text" in delta:
                yield delta["text"]
            uso = ev.get("contentBlockStart", {}).get("start", {}).get("toolUse")
            if uso:
                yield f"\n\n`🔎 {uso['name']}`\n\n"
    tarefa.result()


def _textos_agentcore(pergunta: str):
    """Gera pedaços de texto do runtime implantado (streaming SSE do AgentCore)."""
    import boto3  # noqa: PLC0415

    cliente = boto3.client("bedrock-agentcore", region_name=REGIAO)
    resp = cliente.invoke_agent_runtime(
        agentRuntimeArn=os.environ["FLEXIA_RUNTIME_ARN"],
        runtimeSessionId=st.session_state.sessao,
        payload=json.dumps({"prompt": pergunta}).encode(),
    )
    for linha in resp["response"].iter_lines():
        if not linha or not linha.startswith(b"data:"):
            continue
        try:
            ev = json.loads(linha[5:].strip())
        except json.JSONDecodeError:
            continue
        ev = ev.get("event", {}) if isinstance(ev, dict) else {}
        delta = ev.get("contentBlockDelta", {}).get("delta", {})
        if "text" in delta:
            yield delta["text"]
        uso = ev.get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if uso:
            yield f"\n\n`🔎 {uso['name']}`\n\n"


for m in st.session_state.mensagens:
    with st.chat_message(m["papel"]):
        st.markdown(m["texto"])

pergunta = st.chat_input("Pergunte sobre o setor elétrico…") or st.session_state.pop("pendente", None)
if pergunta:
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        t0 = time.time()
        gerador = _textos_agentcore(pergunta) if MODO == "agentcore" else _textos_local(pergunta)
        try:
            resposta = st.write_stream(gerador)
        except Exception as e:  # noqa: BLE001
            resposta = f"Desculpe, ocorreu um erro: {e}"
            st.error(resposta)
        st.caption(f"{time.time() - t0:.1f} s")
    st.session_state.mensagens.append({"papel": "assistant", "texto": resposta if isinstance(resposta, str) else str(resposta)})
