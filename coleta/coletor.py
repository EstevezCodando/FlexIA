"""Coletor de documentos do setor elétrico com o Cavuca.

Para cada fonte de coleta/fontes.py: baixa páginas (e PDFs, quando configurado), converte para
Markdown limpo (o Cavuca remove scripts, menus ocultos e conteúdo invisível usado em prompt injection)
e grava somente documentos novos ou alterados:

  docs/raw/<fonte>/<sha16>.md     texto em Markdown com cabeçalho de metadados
  docs/raw/<fonte>/<sha16>.json   metadados (url, título, órgão, tipo, datas, hash)
  docs/estado/<fonte>.json        url -> sha256 da última versão coletada (deduplicação)

Uso:
  python coleta/coletor.py --fonte aneel_noticias [--local out/docs] [--max 5]
  python coleta/coletor.py --frequencia diaria           # todas as fontes ativas da frequência
Destino: --local <pasta> ou variável FLEXIA_BUCKET (S3).
"""
import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fontes import FONTES, POR_ID  # noqa: E402

UA = "Mozilla/5.0 (compatible; FlexIA-Coletor/1.0; +hackathon ONS)"
MIN_CHARS = 300
MAX_DOC_CHARS = 80_000
MAX_PDF_PAGINAS = 150
MAX_PDF_BYTES = 40 * 1024 * 1024
log = logging.getLogger("coletor")


# ---------------------------------------------------------------- destino
class Destino:
    """Grava no S3 (bucket) ou numa pasta local, com a mesma estrutura de chaves."""

    def __init__(self, bucket: str | None = None, pasta: str | None = None):
        self.bucket, self.pasta = bucket, Path(pasta) if pasta else None
        if bucket:
            import boto3
            self.s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    def gravar(self, chave: str, dados: bytes, tipo: str) -> None:
        if self.bucket:
            self.s3.put_object(Bucket=self.bucket, Key=chave, Body=dados, ContentType=tipo)
        else:
            p = self.pasta / chave
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(dados)

    def ler_json(self, chave: str) -> dict:
        try:
            if self.bucket:
                return json.loads(self.s3.get_object(Bucket=self.bucket, Key=chave)["Body"].read())
            return json.loads((self.pasta / chave).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - estado inexistente na primeira coleta
            return {}


# ---------------------------------------------------------------- conversões
def pdf_para_texto(dados: bytes) -> str:
    from pypdf import PdfReader
    leitor = PdfReader(io.BytesIO(dados))
    partes = []
    for i, pag in enumerate(leitor.pages):
        if i >= MAX_PDF_PAGINAS:
            partes.append(f"\n[... PDF truncado em {MAX_PDF_PAGINAS} páginas ...]")
            break
        partes.append(pag.extract_text() or "")
    return re.sub(r"[ \t]+\n", "\n", "\n".join(partes)).strip()


def html_para_markdown(url: str, html: str, css: str | None) -> tuple[str, str]:
    """Converte HTML já decodificado em Markdown com a limpeza do Cavuca."""
    from cavuca.engines.toolbelt.custom import Response
    def resp(conteudo: str):
        return Response(url=url, content=conteudo, status=200, reason="OK", cookies={}, headers={}, request_headers={})

    r = resp(html)
    titulo = str(r.css("title::text").get() or "").strip()
    md = ""
    if css:
        # Recorta o bloco ANTES da limpeza: em alguns portais (ex.: CCEE) o contêiner da matéria fica
        # dentro de um elemento marcado como oculto e seria descartado inteiro. A limpeza do Cavuca
        # (scripts, ocultos, anti prompt injection) continua sendo aplicada ao recorte.
        # Sem o bloco esperado a página não é uma matéria (é listagem/filtro): descarta em vez de
        # gravar o site inteiro com menus.
        recorte = "".join(e.html_content for e in r.css(css))
        if recorte:
            md = resp(f"<html><body>{recorte}</body></html>").markdown(main_content_only=True)
        return titulo, md
    return titulo, r.markdown(main_content_only=True)


def decodificar(conteudo: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I) or \
        re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', conteudo[:4000], re.I)
    charset = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    for enc in (charset, "utf-8", "cp1252"):
        try:
            return conteudo.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return conteudo.decode("utf-8", errors="replace")


_RUIDO = re.compile(
    r"^[^\n]*(facebook\.com/sharer|twitter\.com/share|linkedin\.com/shareArticle|api\.whatsapp\.com/send"
    r"|link para Copiar|^Compartilhe:)[^\n]*$",
    re.I | re.M,
)


def limpar(texto: str) -> str:
    """Remove botões de compartilhamento e linhas em branco repetidas."""
    texto = _RUIDO.sub("", texto)
    # junta linhas quebradas no meio da frase (ex.: HTML do Planalto), preservando parágrafos,
    # listas, títulos e tabelas Markdown
    texto = re.sub(r"(?<=[^\n|])\n(?=[^\n|#*>\-])", " ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


# ---------------------------------------------------------------- gravação com deduplicação
class Gravador:
    def __init__(self, destino: Destino, fonte: dict):
        self.destino, self.fonte = destino, fonte
        self.chave_estado = f"docs/estado/{fonte['id']}.json"
        self.estado = destino.ler_json(self.chave_estado)
        self.novos = self.iguais = self.curtos = 0

    def salvar(self, url: str, titulo: str, texto: str, formato: str) -> None:
        texto = limpar(texto)
        max_chars = self.fonte.get("max_chars", MAX_DOC_CHARS)
        if len(texto) > max_chars:  # ex.: páginas CKAN com centenas de arquivos listados
            texto = texto[:max_chars] + f"\n\n[... documento truncado em {max_chars:,} caracteres ...]"
        if len(texto) < self.fonte.get("min_chars", MIN_CHARS):
            self.curtos += 1
            return
        sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        if self.estado.get(url) == sha:
            self.iguais += 1
            return
        titulo = re.sub(r"\s+", " ", titulo or "").strip()
        if len(titulo) < 12 or re.fullmatch(r"[A-Za-z]?\d+\w*", titulo):
            # títulos pobres (ex.: "L14300" no Planalto): usa a primeira linha que identifica o ato
            m = re.search(r"\b((?:LEI|DECRETO|MEDIDA PROVIS[ÓO]RIA|RESOLU[ÇC][ÃA]O NORMATIVA|PORTARIA)"
                          r"(?: COMPLEMENTAR)?\s+N[º°o.]\s*[\d.]+,?\s+DE\s+\d{1,2}[º°]?\s+DE\s+\w+\s+DE\s+\d{4})",
                          re.sub(r"[*_\[\]\s]+", " ", texto))
            titulo = m.group(1).strip() if m else titulo
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta = {"url": url, "titulo": titulo or url, "orgao": self.fonte["orgao"], "tipo": self.fonte["tipo"],
                "fonte": self.fonte["id"], "formato": formato, "coletado_em": agora, "sha256": sha,
                "caracteres": len(texto)}
        cabecalho = "\n".join(f"{k}: {v}" for k, v in meta.items() if k in ("titulo", "orgao", "tipo", "url", "coletado_em"))
        base = f"docs/raw/{self.fonte['id']}/{sha[:16]}"
        self.destino.gravar(base + ".md", f"---\n{cabecalho}\n---\n\n{texto}\n".encode("utf-8"), "text/markdown; charset=utf-8")
        self.destino.gravar(base + ".json", json.dumps(meta, ensure_ascii=False).encode("utf-8"), "application/json")
        self.estado[url] = sha
        self.novos += 1

    def fechar(self) -> dict:
        self.destino.gravar(self.chave_estado, json.dumps(self.estado, ensure_ascii=False).encode("utf-8"), "application/json")
        return {"fonte": self.fonte["id"], "novos_ou_alterados": self.novos, "sem_mudanca": self.iguais,
                "descartados_curtos": self.curtos, "urls_conhecidas": len(self.estado)}


# ---------------------------------------------------------------- modos de coleta
def coletar_paginas(fonte: dict, gravador: Gravador, limite: int | None) -> None:
    import curl_cffi.requests as cr
    for url in fonte["urls"][:limite]:
        try:
            r = cr.get(url, timeout=40, impersonate="chrome", headers={"User-Agent": UA})
            if r.status_code != 200:
                log.warning("HTTP %s em %s", r.status_code, url)
                continue
            titulo, md = html_para_markdown(url, decodificar(r.content, r.headers.get("content-type", "")), fonte["css"])
            gravador.salvar(url, titulo, md, "html")
        except Exception as e:  # noqa: BLE001
            log.warning("falha em %s: %s", url, e)


def coletar_crawl(fonte: dict, gravador: Gravador, limite: int | None) -> None:
    from cavuca.spiders import Spider

    permitir = [re.compile(p, re.I) for p in fonte["permitir"]]
    pdfs = [re.compile(p, re.I) for p in fonte["pdfs"]]
    negar = [re.compile(p, re.I) for p in fonte["negar"]]
    indices = [re.compile(p, re.I) for p in fonte["indices"]]
    max_paginas = limite or fonte["max_paginas"]
    dominios = {urlparse(u).netloc for u in fonte["urls"]}
    if pdfs:  # PDFs às vezes ficam em domínio irmão (ex.: www2.aneel.gov.br)
        dominios |= {".".join(d.split(".")[-3:]) for d in dominios}

    class ColetorSpider(Spider):
        name = fonte["id"]
        start_urls = fonte["urls"]
        allowed_domains = dominios
        robots_txt_obey = True
        download_delay = fonte["atraso"]
        concurrent_requests = 2
        logging_level = logging.WARNING

        def __init__(self):
            super().__init__()
            self.vistas = 0
            self.enfileiradas = set()

        def _seguir(self, response, href: str):
            url = urljoin(response.url, href).split("#")[0]
            if url in self.enfileiradas or any(n.search(url) for n in negar):
                return None
            if any(p.search(url) for p in pdfs):
                self.enfileiradas.add(url)
                return response.follow(url, callback=self.parse_pdf)
            if any(p.search(url) for p in permitir) and len(self.enfileiradas) < max_paginas * 3:
                self.enfileiradas.add(url)
                return response.follow(url)
            return None

        async def parse(self, response):
            if self.vistas >= max_paginas:
                return
            self.vistas += 1
            if response.body[:5] == b"%PDF-":
                async for x in self.parse_pdf(response):
                    yield x
                return
            # páginas de índice/listagem só servem para descobrir links: não viram documento
            if not any(i.search(response.url) for i in indices):
                try:
                    titulo, md = html_para_markdown(response.url, decodificar(response.body, ""), fonte["css"])
                    gravador.salvar(response.url, titulo, md, "html")
                except Exception as e:  # noqa: BLE001
                    log.warning("conversão falhou em %s: %s", response.url, e)
            for href in response.css("a::attr(href)").getall():
                req = self._seguir(response, href or "")
                if req is not None:
                    yield req

        async def parse_pdf(self, response):
            if self.vistas >= max_paginas:
                return
            self.vistas += 1
            if len(response.body) > MAX_PDF_BYTES or response.body[:5] != b"%PDF-":
                return
            try:
                nome = urlparse(response.url).path.rsplit("/", 1)[-1]
                gravador.salvar(response.url, nome, pdf_para_texto(response.body), "pdf")
            except Exception as e:  # noqa: BLE001
                log.warning("PDF ilegível %s: %s", response.url, e)
            if False:  # mantém a função como gerador assíncrono
                yield None

    ColetorSpider().start()


def coletar_lista(fonte: dict, gravador: "Gravador", limite: int | None) -> None:
    """Lista fixa de documentos (semente JSON), para páginas montadas por JavaScript cujos arquivos
    têm URL estável (ex.: Procedimentos de Rede do ONS)."""
    import time
    from urllib.parse import quote

    import curl_cffi.requests as cr
    semente = json.loads((Path(__file__).resolve().parent / "sementes" / fonte["semente"]).read_text(encoding="utf-8"))
    for nome in semente["arquivos"][:limite]:
        url = semente["url_base"] + quote(nome)
        try:
            r = cr.get(url, timeout=120, impersonate="chrome", headers={"User-Agent": UA})
            if r.status_code != 200 or r.content[:5] != b"%PDF-":
                log.warning("HTTP %s / não-PDF em %s", r.status_code, nome)
                continue
            titulo = f"{fonte['titulo_prefixo']} {Path(nome).stem.replace('Súbmodulo', 'Submódulo')}"
            gravador.salvar(url, titulo, pdf_para_texto(r.content), "pdf")
        except Exception as e:  # noqa: BLE001
            log.warning("falha em %s: %s", nome, e)
        time.sleep(fonte["atraso"])


def coletar_rss(fonte: dict, gravador: "Gravador", limite: int | None) -> None:
    """Mídias do setor: guarda SÓ manchete, data, veículo e link (regra do desafio: 'apenas manchete, com link')."""
    import xml.etree.ElementTree as ET

    import curl_cffi.requests as cr
    for feed in fonte["urls"]:
        try:
            r = cr.get(feed, timeout=40, impersonate="chrome", headers={"User-Agent": UA})
            raiz = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            log.warning("feed %s indisponível: %s", feed, e)
            continue
        veiculo = (raiz.findtext("channel/title") or urlparse(feed).netloc).strip()
        filtro = re.compile(fonte["filtro_titulo"], re.I) if fonte.get("filtro_titulo") else None
        for item in raiz.iter("item"):
            titulo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            data = (item.findtext("pubDate") or "").strip()
            if filtro and not filtro.search(titulo):  # veículos generalistas: só o setor elétrico
                continue
            if titulo and link:
                gravador.salvar(link, titulo, f"Manchete: {titulo}\nVeículo: {veiculo}\nPublicada em: {data}\n"
                                               f"Link para a matéria original: {link}", "manchete")


def coletar_tabela(fonte: dict, gravador: "Gravador", limite: int | None) -> None:
    """Transforma cada linha de uma tabela textual do lake (ex.: pautas e decisões da diretoria da ANEEL)
    num documento pesquisável. Lê a cópia local do lake ou, na nuvem, o Parquet no S3."""
    import duckdb
    local = Path(__file__).resolve().parent.parent / "out" / "lake" / "curated" / fonte["tabela"]
    con = duckdb.connect()
    if local.exists():
        origem = f"read_parquet('{local.as_posix()}/**/*.parquet')"
    else:
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws;")
        con.execute(f"CREATE SECRET s (TYPE s3, PROVIDER credential_chain, REGION '{os.environ.get('AWS_REGION', 'us-east-1')}')")
        origem = f"read_parquet('s3://{os.environ['FLEXIA_BUCKET']}/curated/{fonte['tabela']}/**/*.parquet')"
    rel = con.execute(f"SELECT * FROM {origem} {fonte.get('filtro_sql', '')} LIMIT {limite or 10_000_000}")
    colunas = [d[0] for d in rel.description]
    for linha in rel.fetchall():
        v = {c: ("" if x is None else (str(int(x)) if isinstance(x, float) and x.is_integer() else str(x)))
             for c, x in zip(colunas, linha)}
        gravador.salvar(fonte["url_item"].format(**v), fonte["titulo_item"].format(**v)[:300],
                        fonte["texto_item"].format(**v), "registro")


def coletar_fonte(fonte: dict, destino: Destino, limite: int | None = None) -> dict:
    if not fonte["ativa"]:
        return {"fonte": fonte["id"], "ignorada": fonte.get("obs", "inativa")}
    g = Gravador(destino, fonte)
    if fonte["modo"] == "pagina":
        coletar_paginas(fonte, g, limite)
    elif fonte["modo"] == "crawl":
        coletar_crawl(fonte, g, limite)
    elif fonte["modo"] == "lista":
        coletar_lista(fonte, g, limite)
    elif fonte["modo"] == "rss":
        coletar_rss(fonte, g, limite)
    elif fonte["modo"] == "tabela":
        coletar_tabela(fonte, g, limite)
    else:
        return {"fonte": fonte["id"], "ignorada": f"modo {fonte['modo']} não implementado"}
    return g.fechar()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", action="append")
    ap.add_argument("--frequencia", choices=["diaria", "semanal", "mensal"])
    ap.add_argument("--local")
    ap.add_argument("--max", type=int)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("cavuca").setLevel(logging.WARNING)
    destino = Destino(pasta=a.local) if a.local else Destino(bucket=os.environ["FLEXIA_BUCKET"])
    alvo = [POR_ID[i] for i in a.fonte] if a.fonte else [f for f in FONTES if f["frequencia"] == a.frequencia]
    for f in alvo:
        print(json.dumps(coletar_fonte(f, destino, a.max), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
