"""CSS da interface da FlexIA (aplicado sobre o tema escuro de .streamlit/config.toml)."""
from marca import AZUL, BORDA, FUNDO, SUPERFICIE, TEXTO, TEXTO_SUAVE, TURQUESA, VIOLETA

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
  --fx-fundo: {FUNDO}; --fx-superficie: {SUPERFICIE}; --fx-borda: {BORDA};
  --fx-texto: {TEXTO}; --fx-suave: {TEXTO_SUAVE};
  --fx-grad: linear-gradient(135deg, {TURQUESA} 0%, {AZUL} 55%, {VIOLETA} 100%);
}}

html, body, [class*="css"], .stMarkdown, .stChatInput textarea, button {{
  font-family: 'Inter', system-ui, sans-serif !important;
}}
.stApp {{
  background:
    radial-gradient(1200px 600px at 85% -10%, rgba(167,139,250,.10), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(94,234,212,.07), transparent 60%),
    var(--fx-fundo);
}}

/* cromo do Streamlit */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 860px; padding-top: 2.2rem; padding-bottom: 7rem; }}

/* barra lateral */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #0A1120 0%, #070B14 100%);
  border-right: 1px solid var(--fx-borda);
}}
.fx-marca {{ display: flex; align-items: center; gap: .7rem; margin: .2rem 0 1.4rem; }}
.fx-marca svg {{ width: 38px; height: 38px; filter: drop-shadow(0 0 12px rgba(96,165,250,.35)); }}
.fx-marca b {{ font-size: 1.35rem; font-weight: 700; letter-spacing: -.02em; color: var(--fx-texto); }}
.fx-marca span {{ display: block; font-size: .72rem; color: var(--fx-suave); letter-spacing: .08em; text-transform: uppercase; }}
.fx-rotulo {{ font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--fx-suave); margin: 1.4rem 0 .6rem; }}
.fx-metrica {{ display: flex; justify-content: space-between; align-items: baseline; padding: .55rem .1rem;
  border-bottom: 1px solid rgba(28,39,64,.7); font-size: .86rem; color: var(--fx-suave); }}
.fx-metrica b {{ color: var(--fx-texto); font-weight: 600; font-variant-numeric: tabular-nums; }}
.fx-modelo {{ display: flex; gap: .55rem; align-items: center; font-size: .82rem; color: var(--fx-suave); padding: .3rem 0; }}
.fx-ponto {{ width: 7px; height: 7px; border-radius: 50%; flex: none; }}
.fx-rodape {{ font-size: .72rem; color: #56627A; margin-top: 1.6rem; line-height: 1.5; }}

/* tela inicial */
.fx-hero {{ text-align: center; padding: 3.2rem 0 1.6rem; }}
.fx-hero svg {{ width: 92px; height: 92px; filter: drop-shadow(0 0 28px rgba(96,165,250,.45));
  animation: fx-pulso 6s ease-in-out infinite; }}
@keyframes fx-pulso {{ 0%,100% {{ transform: scale(1) rotate(0deg); }} 50% {{ transform: scale(1.04) rotate(6deg); }} }}
.fx-hero h1 {{ font-size: 2.6rem; font-weight: 700; letter-spacing: -.035em; margin: 1.1rem 0 .4rem;
  background: var(--fx-grad); -webkit-background-clip: text; background-clip: text; color: transparent; }}
.fx-hero p {{ color: var(--fx-suave); font-size: 1.02rem; max-width: 560px; margin: 0 auto; line-height: 1.6; }}

/* cartões de sugestão */
div[data-testid="stHorizontalBlock"] button[kind="secondary"] {{
  width: 100%; min-height: 92px; text-align: left; white-space: normal; justify-content: flex-start;
  background: rgba(14,21,36,.72); border: 1px solid var(--fx-borda); border-radius: 16px;
  color: var(--fx-texto); padding: .9rem 1rem; transition: all .18s ease;
}}
div[data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {{
  border-color: rgba(96,165,250,.55); transform: translateY(-2px);
  box-shadow: 0 10px 30px -12px rgba(96,165,250,.45);
}}
div[data-testid="stHorizontalBlock"] button[kind="secondary"] * {{
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }}
div[data-testid="stHorizontalBlock"] button[kind="secondary"] > div,
div[data-testid="stHorizontalBlock"] button[kind="secondary"] > div > span {{
  display: flex; justify-content: flex-start; align-items: flex-start; gap: .75rem; width: 100%; text-align: left; }}
div[data-testid="stHorizontalBlock"] button[kind="secondary"] p {{ font-size: .9rem; line-height: 1.45; text-align: left; margin: 0; }}
div[data-testid="stHorizontalBlock"] button[kind="secondary"] span[data-testid="stIconMaterial"] {{
  color: {AZUL}; font-size: 1.25rem; margin-top: .05rem; }}

/* mensagens */
[data-testid="stChatMessage"] {{ background: transparent; padding: .6rem 0; gap: .9rem; }}
[data-testid="stChatMessage"] img {{ border-radius: 12px; }}
.fx-usuario {{ display: flex; justify-content: flex-end; }}
[data-testid="stChatMessage"]:has(.fx-usuario) {{ flex-direction: row-reverse; }}
[data-testid="stChatMessage"]:has(.fx-usuario) [data-testid="stChatMessageContent"] {{
  background: linear-gradient(135deg, rgba(96,165,250,.16), rgba(167,139,250,.16));
  border: 1px solid rgba(96,165,250,.28); border-radius: 18px 18px 4px 18px; padding: .7rem 1rem;
  max-width: 80%; margin-left: auto;
}}
[data-testid="stChatMessage"]:not(:has(.fx-usuario)) [data-testid="stChatMessageContent"] {{
  background: rgba(14,21,36,.78); border: 1px solid var(--fx-borda);
  border-radius: 4px 18px 18px 18px; padding: .9rem 1.15rem; backdrop-filter: blur(6px);
}}
[data-testid="stChatMessageContent"] p, [data-testid="stChatMessageContent"] li {{ line-height: 1.65; color: var(--fx-texto); }}
[data-testid="stChatMessageContent"] h1, [data-testid="stChatMessageContent"] h2, [data-testid="stChatMessageContent"] h3 {{
  font-size: 1.05rem; font-weight: 600; letter-spacing: -.01em; margin: .9rem 0 .4rem; }}
[data-testid="stChatMessageContent"] table {{ border-collapse: collapse; margin: .6rem 0; font-size: .88rem; width: 100%; }}
[data-testid="stChatMessageContent"] th {{ text-align: left; color: var(--fx-suave); font-weight: 500;
  border-bottom: 1px solid var(--fx-borda); padding: .45rem .6rem; }}
[data-testid="stChatMessageContent"] td {{ border-bottom: 1px solid rgba(28,39,64,.55); padding: .45rem .6rem;
  font-variant-numeric: tabular-nums; }}
[data-testid="stChatMessageContent"] code {{ font-family: 'JetBrains Mono', monospace; font-size: .82em;
  background: rgba(96,165,250,.10); color: #BFD6FF; border-radius: 6px; padding: .1em .35em; }}
[data-testid="stChatMessageContent"] blockquote {{ border-left: 2px solid {AZUL}; margin: .6rem 0; padding: .1rem .9rem;
  color: #C9D3E6; background: rgba(96,165,250,.05); border-radius: 0 8px 8px 0; }}
[data-testid="stChatMessageContent"] a {{ color: {AZUL}; text-decoration: none; border-bottom: 1px solid rgba(96,165,250,.35); }}

/* passos e metadados da resposta */
.fx-passos {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .55rem; }}
.fx-passo {{ display: inline-flex; align-items: center; gap: .4rem; font-size: .74rem; color: var(--fx-suave);
  border: 1px solid var(--fx-borda); border-radius: 999px; padding: .2rem .65rem; background: rgba(7,11,20,.6); }}
.fx-passo.ativo {{ color: #CFE3FF; border-color: rgba(96,165,250,.5); }}
.fx-passo.ativo::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: {AZUL};
  animation: fx-piscar 1s ease-in-out infinite; }}
@keyframes fx-piscar {{ 50% {{ opacity: .25; }} }}
.fx-meta {{ display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .75rem; padding-top: .6rem;
  border-top: 1px solid rgba(28,39,64,.6); font-size: .72rem; color: #6B778F; }}
.fx-chip {{ border-radius: 999px; padding: .15rem .6rem; border: 1px solid var(--fx-borda); }}
.fx-chip.nvidia {{ color: #9BE15D; border-color: rgba(118,185,0,.45); }}
.fx-chip.claude {{ color: #F2B999; border-color: rgba(217,119,87,.45); }}

/* campo de pergunta */
[data-testid="stBottom"] > div {{ background: linear-gradient(180deg, transparent, {FUNDO} 35%); }}
[data-testid="stChatInput"] {{ border-radius: 18px !important; border: 1px solid var(--fx-borda) !important;
  background: rgba(14,21,36,.92) !important; box-shadow: 0 14px 40px -18px rgba(0,0,0,.8); }}
[data-testid="stChatInput"]:focus-within {{ border-color: rgba(96,165,250,.6) !important;
  box-shadow: 0 0 0 3px rgba(96,165,250,.12), 0 14px 40px -18px rgba(0,0,0,.8); }}
[data-testid="stChatInputSubmitButton"] {{ background: var(--fx-grad) !important; border-radius: 12px !important; }}
[data-testid="stChatInputSubmitButton"] svg {{ color: #0B1020 !important; }}

/* botões da barra lateral */
section[data-testid="stSidebar"] button {{ border-radius: 12px; border: 1px solid var(--fx-borda);
  background: rgba(14,21,36,.7); color: var(--fx-texto); }}
section[data-testid="stSidebar"] button:hover {{ border-color: rgba(96,165,250,.5); color: #fff; }}
</style>
"""
