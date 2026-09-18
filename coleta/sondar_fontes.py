"""Testa cada ponto de partida do catálogo: status HTTP, robots.txt e tamanho do Markdown extraído."""
import sys
import urllib.robotparser
from urllib.parse import urlparse

from cavuca.fetchers import Fetcher

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from fontes import FONTES  # noqa: E402

UA = "FlexIA-Coletor/1.0 (+hackathon ONS)"


def robots_ok(url: str) -> str:
    p = urlparse(url)
    rp = urllib.robotparser.RobotFileParser(f"{p.scheme}://{p.netloc}/robots.txt")
    try:
        rp.read()
        return "sim" if rp.can_fetch(UA, url) else "NAO"
    except Exception:  # noqa: BLE001
        return "?"


def sondar(f: dict) -> tuple:
    url = f["urls"][0]
    if f["modo"] == "ckan":
        url = url.rstrip("/") + "/api/3/action/package_list"
    r = Fetcher.get(url, timeout=20)
    tam = len(r.body) if f["modo"] == "ckan" else len(r.markdown(css_selector=f["css"], main_content_only=True))
    return url, r.status, tam


if __name__ == "__main__":
    import os
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as Esgotado

    somente = set(sys.argv[1:])
    pool = ThreadPoolExecutor(max_workers=4)
    for f in FONTES:
        if somente and f["id"] not in somente:
            continue
        fut = pool.submit(sondar, f)
        try:
            url, status, tam = fut.result(timeout=45)
        except Esgotado:
            url, status, tam = f["urls"][0], "TIMEOUT", 0
        except Exception as e:  # noqa: BLE001
            url, status, tam = f["urls"][0], f"ERRO {type(e).__name__}", 0
        print(f"{f['id']:28s} status={status!s:>7} robots={robots_ok(url):3s} conteudo={tam:>8,}  {url}", flush=True)
    os._exit(0)
