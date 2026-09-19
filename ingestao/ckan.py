"""Ingestão de conjuntos dos portais CKAN da ANEEL e da CCEE.

Respeita o robots.txt: /api/ é bloqueado nos dois portais, então os recursos são descobertos na
página HTML do conjunto (/dataset/<slug>), com 10 s entre requisições (Crawl-Delay do portal).
Arquivos CSV são baixados para out/fontes/<fonte>/<slug>/ (mais recentes primeiro, até o orçamento),
unificados numa tabela tipada e descritos a partir do dicionário de dados oficial do conjunto
(PDF/XLSX do próprio portal); quando o dicionário é um PDF sem estrutura, o Claude Haiku extrai as
definições do texto — sem inventar: coluna ausente no dicionário fica sem descrição.

Uso: python ingestao/ckan.py [--descobrir] [tabela ...]
"""
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import curl_cffi.requests as cr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unificar import unificar  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; FlexIA-Coletor/1.0; +hackathon ONS)"}
PORTAIS = {"ANEEL": "https://dadosabertos.aneel.gov.br", "CCEE": "https://dadosabertos.ccee.org.br"}
ATRASO_PORTAL = 10  # Crawl-Delay dos portais CKAN
ATRASO_DOWNLOAD = 3

# tabela -> (portal, slug, tema, orçamento MB, regex dos recursos de dados, regex do dicionário)
# Os regex separam recursos de estrutura diferente publicados no mesmo conjunto.
CONJUNTOS = {
    "aneel_geracao_distribuida": ("ANEEL", "relacao-de-empreendimentos-de-geracao-distribuida", "geracao", 1500,
                                  r"^empreendimento-geracao-distribuida\.parquet", r"^Dicion[áa]rio de dados PDF"),
    "aneel_bandeiras_acionamento": ("ANEEL", "bandeiras-tarifarias", "precos", 50, r"Acionamento CSV", r"Acionamento"),
    "aneel_bandeiras_adicional": ("ANEEL", "bandeiras-tarifarias", "precos", 50, r"Adicional CSV", r"Adicional"),
    "aneel_dec_fec": ("ANEEL", "indicadores-coletivos-de-continuidade-dec-e-fec", "qualidade", 900,
                      r"^indicadores-continuidade-coletivos-20\d\d-20\d\d", r"Continuidade"),
    "aneel_leiloes_geracao": ("ANEEL", "resultado-de-leiloes", "mercado", 100, r"leiloes-geracao", r"gera[çc][ãa]o"),
    "aneel_leiloes_transmissao": ("ANEEL", "resultado-de-leiloes", "mercado", 100, r"leiloes-transmissao", r"transmiss"),
    "aneel_componentes_tarifarias": ("ANEEL", "componentes-tarifarias", "precos", 400,
                                     r"componentes-tarifarias-\d{4}\.parquet", r"metadados"),
    "aneel_subsidios_tarifarios": ("ANEEL", "subsidios-tarifarios", "precos", 200, r"Subs[íi]dios", r"Dicion"),
    "aneel_ralie_usina": ("ANEEL", "ralie-relatorio-de-acompanhamento-da-expansao-da-oferta-de-geracao-de-energia-eletrica",
                          "geracao", 100, r"ralie-usina-atual", r"Usina"),
    "aneel_liberacao_operacao": ("ANEEL", "liberacao-para-operacao-comercial-de-empreendimentos-de-geracao", "geracao", 100,
                                 r"^resumido-.*CSV", r"Resumido"),
    "aneel_samp_balanco": ("ANEEL", "samp-balanco", "mercado", 400, r"samp-balanco\.parquet", r"Dicion"),
    "ccee_pld_horario": ("CCEE", "pld_horario", "precos", 400, r"pld_horario_20\d\d", None),
    "ccee_pld_media_diaria": ("CCEE", "pld_media_diaria", "precos", 50, r"pld_media_diaria_20\d\d", None),
    "ccee_pld_media_semanal": ("CCEE", "pld_media_semanal", "precos", 20, r"pld_media_semanal_20\d\d($|\s)", None),
    "ccee_pld_final_historico": ("CCEE", "pld_final_historico", "precos", 50, r"pld_final_historico", None),
    "ccee_contrato_montante_classe": ("CCEE", "contrato_montante_classe", "mercado", 100, r"contrato_montante_classe_20", None),
    "ccee_sumario_mensal_liquidacao": ("CCEE", "sumario_mensal_liquidacao", "mercado", 100, r"sumario_mensal_liquidacao_20", None),
    "ccee_garantia_fisica_sazo_lastro": ("CCEE", "garantia_fisica_sazo_lastro", "mercado", 200, r"garantia_fisica_sazo_lastro_20", None),
    # Desafio 1 (Copiloto Regulatório)
    "aneel_pautas_atas_diretoria": ("ANEEL", "pautas-e-atas-das-reunioes-publicas-da-diretoria", "regulacao", 300,
                                    r"pautas-atas", r"Dicion"),
}

PORTAIS["MME"] = "https://dadosabertos.mme.gov.br"

# Conjuntos com vários arquivos de estrutura diferente: cada arquivo vira uma tabela <prefixo>_<nome do arquivo>.
# prefixo -> (portal, slug, tema, orçamento MB por arquivo)
MULTI = {
    "aneel_siget": ("ANEEL", "sistema-de-gestao-da-transmissao-siget", "transmissao", 300),
    "mme_luz_para_todos": ("MME", "luz-para-todos", "mercado", 200),
    "mme_reidi": ("MME", "regime-especial-de-incentivos-para-o-desenvolvimento-da-infraestrutura-reidi", "transmissao", 200),
    "mme_sie": ("MME", "sistema-de-informacoes-energeticas", "planejamento", 300),
}


def expandir_multi(prefixo: str) -> dict:
    """Um item de CONJUNTOS por arquivo de dados do conjunto (nome da tabela derivado do nome do arquivo)."""
    portal, slug, tema, orc = MULTI[prefixo]
    info = descobrir(portal, slug)
    itens = {}
    for r in info["recursos"]:
        if not r["url"] or formato(r) not in ("csv", "parquet", "zip") or re.search(r"dicion|metadad", r["nome"], re.I):
            continue
        base = re.sub(r"\.(csv|parquet|zip)|\s+(CSV|PARQUET|ZIP)$", "", r["nome"], flags=re.I).strip()
        base = re.sub(r"^SIGET\s*-\s*", "", base, flags=re.I)
        sufixo = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", unicodedata_ascii(base).lower())).strip("_")[:40]
        tabela = f"{prefixo}_{sufixo}"
        if tabela in itens:
            continue
        # ancorado no nome inteiro: "Contrato Agente" não pode casar com "Resolução Contrato Agente"
        exato = r"^(SIGET\s*-\s*)?" + re.escape(base)
        itens[tabela] = (portal, slug, tema, orc, exato + r"(\.(csv|parquet|zip))?(\s+(CSV|PARQUET|ZIP))?\s",
                         exato + r"(\.pdf)?\s+PDF$")
    return itens


def unicodedata_ascii(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()

_ultimo: dict[str, float] = {}


def get(url: str, atraso: float, stream: bool = False):
    host = url.split("/")[2]
    espera = atraso - (time.time() - _ultimo.get(host, 0))
    if espera > 0:
        time.sleep(espera)
    r = cr.get(url, timeout=120, impersonate="chrome", headers=UA, stream=stream)
    _ultimo[host] = time.time()
    return r


def descobrir(portal: str, slug: str) -> dict:
    """Página do conjunto -> título, descrição e recursos (nome, url, formato)."""
    from cavuca.engines.toolbelt.custom import Response
    url = f"{PORTAIS[portal]}/dataset/{slug}"
    r = get(url, ATRASO_PORTAL)
    pag = Response(url=url, content=r.text, status=r.status_code, reason="", cookies={}, headers={}, request_headers={})
    titulo = (pag.css("h1::text").get() or slug).strip()
    notas = " ".join(t.strip() for t in pag.css(".notes ::text").getall() if t.strip())
    recursos = []
    for item in pag.css("li.resource-item"):
        nome = " ".join(t.strip() for t in item.css("a.heading ::text").getall() if t.strip()) or \
            (item.css("a::attr(title)").get() or "")
        fmt = (item.css("span.format-label::attr(data-format)").get() or
               item.css("span.format-label::text").get() or "").lower()
        links = [urljoin(url, h) for h in item.css("a::attr(href)").getall() if h]
        download = next((h for h in links if "/download" in h or "pda-download" in h), None)
        recursos.append({"nome": re.sub(r"\s+", " ", nome)[:160], "formato": fmt, "url": download,
                         "pagina": next((h for h in links if "/resource/" in h and "/download" not in h), None)})
    return {"titulo": titulo, "descricao": notas, "recursos": recursos, "url": url}


def formato(rec: dict) -> str:
    alvo = (rec["formato"] or "") + " " + (rec["url"] or "") + " " + rec["nome"]
    for f in ("csv", "xlsx", "pdf", "json", "xml", "zip"):
        if re.search(rf"\b{f}\b|\.{f}", alvo, re.I):
            return f
    return rec["formato"] or "?"


def baixar(url: str, destino: Path, atraso: float) -> Path:
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    r = get(url, atraso, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} em {url}")
    nome = re.search(r'filename="?([^";]+)', r.headers.get("content-disposition", "") or "")
    if nome and destino.suffix == "":
        destino = destino.with_name(nome.group(1))
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    with open(tmp, "wb") as f:
        for bloco in r.iter_content(chunk_size=1 << 20):
            f.write(bloco)
    tmp.replace(destino)
    return destino


def para_utf8(p: Path) -> Path:
    """CSV fora de UTF-8 (Windows-1252 nos portais) é convertido para UTF-8: o leitor 'latin-1' do
    DuckDB rejeita os caracteres 0x80–0x9F do Windows-1252 (aspas tipográficas, travessão etc.)."""
    try:
        p.read_bytes().decode("utf-8")
        return p
    except UnicodeDecodeError:
        destino = p.with_name(p.stem + ".utf8.csv")
        if not destino.exists() or destino.stat().st_mtime < p.stat().st_mtime:
            destino.write_text(p.read_bytes().decode("cp1252", errors="replace"), encoding="utf-8")
        return destino


def opcoes_csv(p: Path) -> str:
    """Separador pelo cabeçalho; a codificação já é UTF-8 (ver para_utf8)."""
    primeira = p.open("rb").read(1 << 16).split(b"\n", 1)[0]
    sep = ";" if primeira.count(b";") >= primeira.count(b",") else ","
    return f"delim='{sep}', header=true, encoding='utf-8', quote='\"'"


def texto_dicionario(recursos: list[dict], pasta: Path, dic_regex: str | None) -> str:
    """Texto do dicionário de dados oficial do recurso (PDF ou planilha), se houver."""
    for rec in recursos:
        if not rec["url"]:
            continue
        casa_regex = bool(dic_regex and re.search(dic_regex, rec["nome"], re.I))
        # PDF com o mesmo nome do arquivo de dados é o dicionário dele (ex.: "SIGET - Contrato Agente PDF")
        if not (re.search(r"dicion|metadad|layout|DM -", rec["nome"] + rec["url"], re.I) or
                (casa_regex and formato(rec) == "pdf")):
            continue
        if dic_regex and not casa_regex:
            continue
        fmt = formato(rec)
        try:
            nome = re.sub(r"[^A-Za-z0-9]+", "_", rec["nome"])[:60]
            p = baixar(rec["url"], pasta / f"dicionario_{nome}.{fmt}", ATRASO_PORTAL)
            if fmt == "pdf":
                from pypdf import PdfReader
                return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages[:15])
            if fmt == "xlsx":
                import openpyxl
                wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                return "\n".join(" | ".join(str(c) for c in row if c is not None)
                                 for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            print(f"    aviso: dicionário indisponível ({e})", flush=True)
    return ""


def descrever_colunas(colunas: list[str], texto: str, titulo: str, oficial: bool = True, amostra: dict | None = None) -> dict:
    """Descrição de cada coluna com o Claude Haiku.

    oficial=True: extrai do texto do dicionário de dados oficial, sem inventar (ausente -> vazio).
    oficial=False: não há dicionário; descreve pelo nome, pela amostra e pela descrição do conjunto,
    com prefixo "[inferido]" para a FlexIA não tratar como definição oficial.
    """
    if oficial and not texto.strip():
        return {}
    import boto3
    cliente = boto3.client("bedrock-runtime", region_name="us-east-1")
    if oficial:
        pedido = (
            f"Dicionário de dados oficial do conjunto '{titulo}':\n<dicionario>\n{texto[:60000]}\n</dicionario>\n\n"
            f"Colunas da tabela (nomes normalizados em minúsculas, sem acento): {json.dumps(colunas, ensure_ascii=False)}\n\n"
            "Para cada coluna, copie a descrição correspondente do dicionário (inclua a unidade se o dicionário "
            "informar). Se a coluna não aparecer no dicionário, use string vazia. NÃO invente descrições. "
            "Responda SOMENTE com um objeto JSON {\"coluna\": \"descrição\"}.")
    else:
        pedido = (
            f"Conjunto de dados '{titulo}'. Descrição oficial do conjunto: {texto[:4000]}\n"
            f"Uma linha de exemplo: {json.dumps(amostra or {}, ensure_ascii=False, default=str)}\n\n"
            "Não existe dicionário de dados. Para cada coluna, escreva uma descrição curta (até 15 palavras) do que "
            "ela provavelmente contém, com a unidade só se for evidente (ex.: PLD em R$/MWh). Seja conservador. "
            "Responda SOMENTE com um objeto JSON {\"coluna\": \"descrição\"}.")
    r = cliente.converse(modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                         messages=[{"role": "user", "content": [{"text": pedido}]}],
                         inferenceConfig={"maxTokens": 4000, "temperature": 0})
    saida = r["output"]["message"]["content"][0]["text"]
    m = re.search(r"\{.*\}", saida, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}
    prefixo = "" if oficial else "[inferido] "
    return {c: (prefixo + str(d.get(c, "") or "").strip()) if d.get(c) else "" for c in colunas}


def extrair_zip(p: Path) -> list[Path]:
    """Extrai CSV/Parquet de um ZIP (ao lado do arquivo) e devolve os caminhos extraídos."""
    import zipfile
    saida = []
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            if info.filename.lower().endswith((".csv", ".parquet")) and not info.is_dir():
                destino = p.parent / (p.stem + "__" + Path(info.filename).name)
                if not destino.exists() or destino.stat().st_size != info.file_size:
                    with z.open(info) as src, open(destino, "wb") as dst:
                        while bloco := src.read(1 << 20):
                            dst.write(bloco)
                saida.append(destino)
    return saida


def ingerir(tabela: str) -> dict:
    portal, slug, tema, orc_mb, filtro, dic_regex = CONJUNTOS[tabela]
    info = descobrir(portal, slug)
    pasta = BASE / "out" / "fontes" / portal.lower() / slug
    pasta.mkdir(parents=True, exist_ok=True)
    candidatos = [r for r in info["recursos"] if r["url"] and formato(r) in ("csv", "parquet", "zip")
                  and not re.search(r"dicion|metadad|layout|^DM -", r["nome"], re.I)
                  and re.search(filtro, r["nome"] + " " + r["url"].split("/")[-1], re.I)]
    # mesmo recurso em vários formatos: Parquet > ZIP > CSV (a chave é o nome sem extensão/formato)
    por_chave = {}
    for r in candidatos:
        chave = re.sub(r"\.(csv|parquet|zip)|\s+(CSV|PARQUET|ZIP)$", "", r["nome"], flags=re.I).strip().lower()
        pref = {"parquet": 0, "zip": 1, "csv": 2}[formato(r)]
        if chave not in por_chave or pref < por_chave[chave][0]:
            por_chave[chave] = (pref, r)
    escolhidos = [r for _, r in por_chave.values()]
    if not escolhidos:
        return {"tabela": tabela, "status": "nenhum recurso de dados encontrado", "recursos": len(info["recursos"])}
    # mais recentes primeiro (nomes com ano), até o orçamento
    escolhidos.sort(key=lambda r: re.findall(r"20\d\d", r["nome"] + r["url"])[-1:] or ["0"], reverse=True)
    arquivos, total = [], 0
    for rec in escolhidos:
        nome = re.sub(r"[^A-Za-z0-9._-]+", "_", rec["url"].rstrip("/").split("/")[-1])
        if nome in ("content", "download") or "." not in nome:
            nome = re.sub(r"[^A-Za-z0-9._-]+", "_", rec["nome"])[:80] + "." + formato(rec)
        try:
            p = baixar(rec["url"], pasta / nome, ATRASO_DOWNLOAD if portal == "CCEE" else ATRASO_PORTAL)
        except Exception as e:  # noqa: BLE001
            print(f"    aviso: {rec['nome']}: {e}", flush=True)
            continue
        total += p.stat().st_size
        arquivos += extrair_zip(p) if p.suffix.lower() == ".zip" else [p]
        if total > orc_mb * 1e6:
            print(f"    orçamento de {orc_mb} MB atingido; recursos mais antigos ficaram de fora", flush=True)
            break
    if not arquivos:
        return {"tabela": tabela, "status": "downloads falharam"}
    # arquivos de um mesmo conjunto podem ter separadores/codificações diferentes: agrupa pelo padrão
    # (Parquet não tem opção de CSV e entra em qualquer grupo; CSVs se agrupam pelo padrão detectado)
    parquets = [p for p in arquivos if p.suffix.lower() == ".parquet"]
    por_opcao = {}
    for p in arquivos:
        if p.suffix.lower() == ".csv":
            p = para_utf8(p)
            por_opcao.setdefault(opcoes_csv(p), []).append(p)
    opcao, grupo = max(por_opcao.items(), key=lambda kv: sum(x.stat().st_size for x in kv[1])) if por_opcao else ("", [])
    grupo = sorted(grupo + parquets)
    resumo = unificar(grupo, BASE / "out" / "lake" / "curated" / tabela, csv_opcoes=opcao)
    colunas = list(resumo["colunas"])
    dic = texto_dicionario(info["recursos"], pasta, dic_regex) if dic_regex else ""
    oficial = bool(dic.strip())
    amostra = None
    if not oficial:
        import duckdb
        glob = (BASE / "out" / "lake" / "curated" / tabela).as_posix() + "/**/*.parquet"
        r = duckdb.sql(f"SELECT * FROM read_parquet('{glob}') LIMIT 1")
        amostra = dict(zip(r.columns, r.fetchone()))
    desc = descrever_colunas(colunas, dic if oficial else info["descricao"], info["titulo"], oficial, amostra)
    meta = {"tabela": tabela, "fonte": portal, "tema": tema, "titulo": info["titulo"],
            "descricao": f"{portal} — {info['titulo']}. {info['descricao'][:1200]}".strip(),
            "origem": info["url"],
            "dicionario": ("oficial do portal (descrições extraídas do dicionário pelo Claude Haiku)" if oficial
                           else "sem dicionário oficial: descrições [inferido] a partir do nome e da amostra"),
            "colunas": {c: desc.get(c, "") for c in colunas},
            **{k: resumo[k] for k in ("linhas", "periodo", "coluna_tempo", "particionada_por_ano")},
            "arquivos_fonte": len(grupo)}
    (BASE / "out" / "metadados").mkdir(parents=True, exist_ok=True)
    (BASE / "out" / "metadados" / f"{tabela}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"tabela": tabela, "linhas": resumo["linhas"], "arquivos": len(grupo), "mb": round(total / 1e6),
            "periodo": resumo["periodo"], "colunas": len(colunas),
            "colunas_sem_descricao": sum(1 for v in meta["colunas"].values() if not v)}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # nomes de MULTI viram uma tabela por arquivo do conjunto
    for prefixo in [a for a in args if a in MULTI] + ([] if args else list(MULTI)):
        novos = expandir_multi(prefixo)
        print(f"{prefixo}: {len(novos)} tabelas -> {list(novos)}", flush=True)
        CONJUNTOS.update(novos)
        args = [a for a in args if a != prefixo] + list(novos) if args else args
    alvo = args or list(CONJUNTOS)
    if "--descobrir" in sys.argv:
        for t in alvo:
            portal, slug, *_ = CONJUNTOS[t]
            info = descobrir(portal, slug)
            print(f"\n== {t}: {info['titulo']} ({len(info['recursos'])} recursos)", flush=True)
            for r in info["recursos"][:12]:
                print(f"   [{formato(r)}] {r['nome'][:70]}  {'(sem link)' if not r['url'] else ''}", flush=True)
        sys.exit()
    for t in alvo:
        try:
            print(json.dumps(ingerir(t), ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"tabela": t, "erro": f"{type(e).__name__}: {str(e)[:300]}"}, ensure_ascii=False), flush=True)
