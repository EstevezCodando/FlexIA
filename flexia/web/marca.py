"""Identidade visual da FlexIA: símbolo abstrato, avatares e paleta.

O símbolo são dois arcos de energia em sentidos opostos (o fluxo que a rede precisa equilibrar),
um núcleo (a decisão) e um ponto em órbita (o dado em movimento), num gradiente turquesa → azul → violeta.
"""
import base64

TURQUESA, AZUL, VIOLETA = "#5EEAD4", "#60A5FA", "#A78BFA"
FUNDO, SUPERFICIE, BORDA = "#070B14", "#0E1524", "#1C2740"
TEXTO, TEXTO_SUAVE = "#E6EAF2", "#8B97AE"

_GRADIENTE = f"""<linearGradient id="fx" x1="8" y1="6" x2="58" y2="58" gradientUnits="userSpaceOnUse">
  <stop offset="0" stop-color="{TURQUESA}"/><stop offset=".55" stop-color="{AZUL}"/><stop offset="1" stop-color="{VIOLETA}"/>
</linearGradient>
<radialGradient id="brilho" cx="32" cy="32" r="30" gradientUnits="userSpaceOnUse">
  <stop offset="0" stop-color="{AZUL}" stop-opacity=".28"/><stop offset="1" stop-color="{AZUL}" stop-opacity="0"/>
</radialGradient>"""

_SIMBOLO = """<circle cx="32" cy="32" r="30" fill="url(#brilho)"/>
<path d="M32 6 A26 26 0 1 1 9.48 19" fill="none" stroke="url(#fx)" stroke-width="3.4" stroke-linecap="round"/>
<path d="M32 47 A15 15 0 1 1 44.99 24.5" fill="none" stroke="url(#fx)" stroke-width="3.4" stroke-linecap="round" opacity=".9"/>
<circle cx="32" cy="32" r="4.2" fill="url(#fx)"/>
<circle cx="9.48" cy="19" r="2.8" fill="#A78BFA"/>"""

LOGO_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="FlexIA">
<defs>{_GRADIENTE}</defs>{_SIMBOLO}</svg>"""

AVATAR_IA_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs>{_GRADIENTE}</defs><rect width="64" height="64" rx="18" fill="{SUPERFICIE}"/>
<g transform="translate(6 6) scale(.8125)">{_SIMBOLO}</g></svg>"""

AVATAR_USUARIO_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="18" fill="#141C2E"/>
<circle cx="32" cy="26" r="8" fill="none" stroke="{TEXTO_SUAVE}" stroke-width="3"/>
<path d="M17 49 C19 40 25 37 32 37 C39 37 45 40 47 49" fill="none" stroke="{TEXTO_SUAVE}" stroke-width="3" stroke-linecap="round"/>
</svg>"""


def data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


AVATAR_IA = data_uri(AVATAR_IA_SVG)
AVATAR_USUARIO = data_uri(AVATAR_USUARIO_SVG)
