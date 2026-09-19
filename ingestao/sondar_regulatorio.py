"""Sonda fontes regulatórias do Desafio 1 (robots.txt, estrutura, recursos) antes de configurar a coleta."""
import re
import sys
import time
from pathlib import Path

import curl_cffi.requests as cr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ckan import PORTAIS, descobrir, formato  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; FlexIA-Coletor/1.0; +hackathon ONS)"}


def robots(host: str) -> str:
    try:
        r = cr.get(f"https://{host}/robots.txt", timeout=20, impersonate="chrome", headers=UA)
        linhas = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("#")]
        return f"{r.status_code} | " + " | ".join(linhas[:10])[:300]
    except Exception as e:  # noqa: BLE001
        return f"erro {type(e).__name__}"


PORTAIS["MME"] = "https://dadosabertos.mme.gov.br"
for portal, slug in [("ANEEL", "sistema-de-gestao-da-transmissao-siget"),
                     ("ANEEL", "pautas-e-atas-das-reunioes-publicas-da-diretoria")]:
    info = descobrir(portal, slug)
    print(f"\n== {portal}/{slug}: {info['titulo']} ({len(info['recursos'])} recursos)\n   {info['descricao'][:300]}")
    for r in info["recursos"][:20]:
        print(f"   [{formato(r)}] {r['nome'][:90]}")

r = cr.get("https://dadosabertos.mme.gov.br/dataset/", timeout=30, impersonate="chrome", headers=UA)
print("\n== MME CKAN conjuntos:", sorted(set(re.findall(r'href="/dataset/([a-z0-9_-]+)"', r.text)))[:40])

for host in ["dadosabertos.mme.gov.br", "biblioteca.aneel.gov.br", "www2.aneel.gov.br", "www.ccee.org.br"]:
    print(f"\nrobots {host}: {robots(host)}")
    time.sleep(1)

for url in ["https://www.gov.br/mme/pt-br/assuntos/conselhos-e-comites/cnpe/resolucoes-do-cnpe",
            "https://biblioteca.aneel.gov.br/",
            "https://www.gov.br/aneel/pt-br/assuntos/agenda-regulatoria"]:
    try:
        r = cr.get(url, timeout=30, impersonate="chrome", headers=UA)
        links = sorted(set(re.findall(r'href="([^"#]+)"', r.text)))
        print(f"\n== {url} -> {r.status_code}, {len(r.text)} bytes, {len(links)} links")
        print("   ", [l for l in links if re.search(r"resolu|cnpe|20\d\d|agenda|pdf|sophia|busca|legisla", l, re.I)][:25])
    except Exception as e:  # noqa: BLE001
        print(url, "erro", e)
    time.sleep(2)
