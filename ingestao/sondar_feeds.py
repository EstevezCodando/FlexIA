"""Testa feeds RSS de mídias do setor e páginas regulatórias candidatas (status, itens, robots)."""
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import curl_cffi.requests as cr

UA = {"User-Agent": "Mozilla/5.0 (compatible; FlexIA-Coletor/1.0; +hackathon ONS)"}
FEEDS = ["https://www.canalenergia.com.br/feed", "https://megawhat.energy/feed/", "https://agenciainfra.com/blog/feed/",
         "https://epbr.com.br/feed/", "https://www.absolar.org.br/feed/", "https://abeeolica.org.br/feed/",
         "https://www.poder360.com.br/energia/feed/", "https://www.infomoney.com.br/tudo-sobre/energia-eletrica/feed/"]
PAGINAS = ["https://www.gov.br/aneel/pt-br/assuntos/governanca-regulatoria/agenda-regulatoria",
           "https://www.gov.br/aneel/pt-br/reunioes-publicas",
           "https://www.gov.br/aneel/pt-br/centrais-de-conteudos/legislacao",
           "https://www.gov.br/mme/pt-br/acesso-a-informacao/legislacao/portarias",
           "https://www.gov.br/mme/pt-br/acesso-a-informacao/legislacao/resolucoes",
           "https://www.gov.br/mme/pt-br/assuntos/conselhos-e-comites/cnpe/resolucoes-do-cnpe/2025",
           "https://www.ccee.org.br/web/guest/dados-e-analises/dados-mercado-mensal",
           "https://www.ccee.org.br/web/guest/mercado/infomercado"]

for f in FEEDS:
    try:
        r = cr.get(f, timeout=30, impersonate="chrome", headers=UA)
        itens = list(ET.fromstring(r.content).iter("item"))
        rb = cr.get(f"https://{urlparse(f).netloc}/robots.txt", timeout=20, impersonate="chrome", headers=UA)
        bloqueia_feed = bool(re.search(r"Disallow:\s*/(feed|\*/feed)", rb.text, re.I))
        print(f"feed {f}: {r.status_code}, {len(itens)} itens, robots bloqueia feed: {bloqueia_feed}; "
              f"ex.: {itens[0].findtext('title')[:70] if itens else '-'}")
    except Exception as e:  # noqa: BLE001
        print(f"feed {f}: ERRO {type(e).__name__} {str(e)[:80]}")
    time.sleep(1)

for p in PAGINAS:
    try:
        r = cr.get(p, timeout=30, impersonate="chrome", headers=UA)
        pdfs = len(set(re.findall(r'href="([^"]+\.pdf)"', r.text, re.I)))
        print(f"pagina {p}: {r.status_code}, {len(r.text)} bytes, {pdfs} PDFs")
    except Exception as e:  # noqa: BLE001
        print(f"pagina {p}: ERRO {type(e).__name__}")
    time.sleep(1)
