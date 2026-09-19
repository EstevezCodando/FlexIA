"""Interface web da FlexIA (Streamlit).

Rodar:  streamlit run flexia/web/app.py
Modos:  FLEXIA_MODO=local (padrão; agente no mesmo processo) | agentcore (FLEXIA_RUNTIME_ARN)
No Code Editor do workshop, abra a porta 8501 pela aba PORTS.
"""
import html
import json
import os
import sys
import time
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config  # noqa: E402  (.env da raiz do projeto)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import aquecer_local, perguntar  # noqa: E402
from marca import AVATAR_IA, AVATAR_USUARIO, LOGO_SVG, data_uri  # noqa: E402
from tema import CSS  # noqa: E402

MODO = os.environ.get("FLEXIA_MODO", "local")
BASE = Path(__file__).resolve().parents[2]

FERRAMENTAS = {
    "listar_tabelas": "Mapeando as tabelas do lake",
    "descrever_tabela": "Lendo o dicionário de dados",
    "consultar_sql": "Consultando o data lake",
    "buscar_documentos": "Pesquisando leis, regulação e notícias",
    "status_projeto": "Verificando capacidades",
}
MODELOS = {
    "nvidia.nemotron-nano-3-30b": ("NVIDIA Nemotron Nano 3", "nvidia"),
    "nvidia.nemotron-super-3-120b": ("NVIDIA Nemotron Super 3", "nvidia"),
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": ("Claude Haiku 4.5", "claude"),
    "us.anthropic.claude-sonnet-4-6": ("Claude Sonnet 4.6", "claude"),
}
ROTAS = {"dados": "dados", "documentos": "documentos", "misto": "dados + documentos",
         "conversa": "conversa", "fora_escopo": "verificação de escopo"}
SUGESTOES = [
    (":material/query_stats:", "CMO médio de cada subsistema em 2025"),
    (":material/bolt:", "Quanto de energia eólica e solar foi cortada em 2025, por razão?"),
    (":material/gavel:", "O que a Lei 14.300 define como Sistema de Compensação de Energia Elétrica?"),
    (":material/compare_arrows:", "Compare o corte eólico no Nordeste entre 2024 e 2025 e explique o contexto regulatório"),
]

st.set_page_config(page_title="FlexIA", page_icon=data_uri(LOGO_SVG), layout="centered",
                   initial_sidebar_state="auto")  # recolhida em telas pequenas
st.markdown(CSS, unsafe_allow_html=True)

if "sessao" not in st.session_state:
    st.session_state.sessao = f"web-{uuid.uuid4()}"
    st.session_state.mensagens = []


# ------------------------------------------------------------------ dados da barra lateral
@st.cache_data(ttl=600, show_spinner=False)
def resumo_base() -> dict:
    """Tamanho do lake e do índice de documentos (catálogo local ou no S3)."""
    try:
        import boto3  # noqa: PLC0415
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        conta = boto3.client("sts").get_caller_identity()["Account"]
        bucket = os.environ.get("FLEXIA_BUCKET", f"ons-datalake-{conta}")
        local = BASE / "out" / "catalogo.json"
        cat = json.loads(local.read_text(encoding="utf-8")) if local.exists() else \
            json.loads(s3.get_object(Bucket=bucket, Key="catalogo/catalogo.json")["Body"].read())
        docs = trechos = fontes = 0
        for o in s3.list_objects_v2(Bucket=bucket, Prefix="docs/index/").get("Contents", []):
            if o["Key"].endswith(".versao.json"):
                v = json.loads(s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read())
                docs, trechos, fontes = docs + len(v["docs"]), trechos + v.get("trechos", 0), fontes + 1
        return {"tabelas": len(cat["tabelas"]), "linhas": sum(t["linhas"] for t in cat["tabelas"]),
                "docs": docs, "trechos": trechos, "fontes": fontes}
    except Exception:  # noqa: BLE001 - a interface funciona sem o resumo
        return {}


def milhar(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


with st.sidebar:
    st.markdown(f'<div class="fx-marca">{LOGO_SVG}<div><b>FlexIA</b><span>Setor elétrico · IA</span></div></div>',
                unsafe_allow_html=True)
    if st.button("Nova conversa", icon=":material/add:", use_container_width=True):
        st.session_state.sessao = f"web-{uuid.uuid4()}"
        st.session_state.mensagens = []
        st.rerun()

    r = resumo_base()
    if r:
        st.markdown('<div class="fx-rotulo">Base de conhecimento</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="fx-metrica">Tabelas de dados <b>{r["tabelas"]}</b></div>'
            f'<div class="fx-metrica">Registros <b>{r["linhas"] / 1e6:,.0f} mi</b></div>'
            f'<div class="fx-metrica">Documentos <b>{milhar(r["docs"])}</b></div>'
            f'<div class="fx-metrica">Fontes monitoradas <b>{r["fontes"]}</b></div>',
            unsafe_allow_html=True)

    st.markdown('<div class="fx-rotulo">Inteligência</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="fx-modelo"><span class="fx-ponto" style="background:#76B900"></span>NVIDIA Nemotron · roteamento</div>'
        '<div class="fx-modelo"><span class="fx-ponto" style="background:#D97757"></span>Claude Haiku 4.5 · respostas</div>'
        '<div class="fx-modelo"><span class="fx-ponto" style="background:#D97757"></span>Claude Sonnet 4.6 · análises</div>'
        '<div class="fx-modelo"><span class="fx-ponto" style="background:#60A5FA"></span>DuckDB + S3 · dados</div>'
        '<div class="fx-modelo"><span class="fx-ponto" style="background:#A78BFA"></span>Cavuca + Cohere · documentos</div>',
        unsafe_allow_html=True)
    st.markdown(
        '<div class="fx-rodape">Dados: ONS, ANEEL, EPE, CCEE, MME, Planalto, ERA5.<br>'
        'Toda resposta numérica vem de consulta aos dados; textos legais são citados literalmente.</div>',
        unsafe_allow_html=True)


# ------------------------------------------------------------------ renderização
def html_passos(passos: list[str], ativo: bool) -> str:
    if not passos:
        return ""
    itens = [f'<span class="fx-passo{" ativo" if ativo and i == len(passos) - 1 else ""}">{html.escape(p)}</span>'
             for i, p in enumerate(passos)]
    return f'<div class="fx-passos">{"".join(itens)}</div>'


def html_meta(m: dict) -> str:
    chips = ['<span class="fx-chip nvidia">roteado por NVIDIA Nemotron</span>']
    if m.get("decisao"):
        nome, familia = MODELOS.get(m["decisao"]["modelo"], (m["decisao"]["modelo"], ""))
        chips.append(f'<span class="fx-chip {familia}">{html.escape(nome)}</span>')
        chips.append(f'<span class="fx-chip">{ROTAS.get(m["decisao"]["rota"], m["decisao"]["rota"])}</span>')
    n = sum(1 for p in m.get("ferramentas", []) if p == "consultar_sql")
    if n:
        chips.append(f'<span class="fx-chip">{n} consulta{"s" if n > 1 else ""} SQL</span>')
    if "buscar_documentos" in m.get("ferramentas", []):
        chips.append('<span class="fx-chip">documentos citados</span>')
    if m.get("segundos"):
        chips.append(f'<span class="fx-chip">{m["segundos"]:.1f} s</span>'.replace(".", ","))
    return f'<div class="fx-meta">{"".join(chips)}</div>'


def mostrar_usuario(texto: str) -> None:
    with st.chat_message("user", avatar=AVATAR_USUARIO):
        st.markdown('<div class="fx-usuario"></div>', unsafe_allow_html=True)
        st.markdown(texto)


for m in st.session_state.mensagens:
    if m["papel"] == "user":
        mostrar_usuario(m["texto"])
    else:
        with st.chat_message("assistant", avatar=AVATAR_IA):
            st.markdown(m["texto"])
            st.markdown(html_meta(m), unsafe_allow_html=True)

pendente = None
if not st.session_state.mensagens:
    st.markdown(
        f'<div class="fx-hero">{LOGO_SVG}<h1>FlexIA</h1>'
        '<p>Pergunte sobre geração, carga, custo marginal, cortes de renováveis, tarifas, leis e notícias '
        'do setor elétrico. Respostas com dados do ONS e documentos oficiais, com a fonte citada.</p></div>',
        unsafe_allow_html=True)
    colunas = st.columns(2)
    for i, (icone, texto) in enumerate(SUGESTOES):
        if colunas[i % 2].button(texto, icon=icone, key=f"sug{i}", use_container_width=True):
            pendente = texto

pergunta = st.chat_input("Pergunte à FlexIA…") or pendente
if pergunta:
    if pendente:
        st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
        st.session_state.pendente_resposta = True
        st.rerun()
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
    mostrar_usuario(pergunta)
    st.session_state.pendente_resposta = True

if st.session_state.pop("pendente_resposta", False):
    pergunta = st.session_state.mensagens[-1]["texto"]
    if MODO == "local":
        with st.spinner("Iniciando a FlexIA…"):
            aquecer_local()
    with st.chat_message("assistant", avatar=AVATAR_IA):
        caixa_passos = st.empty()
        meta = {"ferramentas": [], "decisao": None}
        passos = ["Roteando com NVIDIA Nemotron"]
        caixa_passos.markdown(html_passos(passos, True), unsafe_allow_html=True)
        t0 = time.time()

        def texto():
            primeiro, emitiu = True, False
            for tipo, valor in perguntar(pergunta, st.session_state.sessao, MODO):
                if tipo == "ferramenta":
                    meta["ferramentas"].append(valor)
                    passos.append(FERRAMENTAS.get(valor, valor))
                    caixa_passos.markdown(html_passos(passos, True), unsafe_allow_html=True)
                    if emitiu:  # texto antes e depois de uma ferramenta são blocos separados
                        yield "\n\n"
                        emitiu = False
                elif tipo == "decisao":
                    meta["decisao"] = valor
                elif tipo == "texto":
                    if primeiro:
                        primeiro = False
                        caixa_passos.markdown(html_passos(passos, False), unsafe_allow_html=True)
                    emitiu = True
                    yield valor
            caixa_passos.empty()

        try:
            resposta = st.write_stream(texto())
        except Exception as e:  # noqa: BLE001
            caixa_passos.empty()
            resposta = f"Não consegui concluir a resposta: `{type(e).__name__}`. Tente novamente em instantes."
            st.markdown(resposta)
        meta["segundos"] = time.time() - t0
        st.markdown(html_meta(meta), unsafe_allow_html=True)
    st.session_state.mensagens.append({"papel": "assistant", "texto": resposta if isinstance(resposta, str) else str(resposta),
                                       **meta})
