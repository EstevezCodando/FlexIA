"""Ingestão de conjuntos do ONS a partir do bucket público oficial s3://ons-aws-prod-opendata
(Registro de Dados Abertos da AWS — o mesmo destino dos links de download do portal dados.ons.org.br).

Para cada conjunto: lista os arquivos, escolhe por período o melhor formato (Parquet > CSV), baixa
para out/fontes/ons/<slug>/, unifica numa tabela tipada em out/lake/curated/<tabela>/ e grava os
metadados oficiais (título e descrição do PDF do dicionário; descrição de cada coluna do JSON
"dicionario_simplificado") em out/metadados/<tabela>.json.

Uso: python ingestao/ons.py [tabela ...]
"""
import io
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unificar import nome_coluna, unificar  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
BUCKET_ONS = "ons-aws-prod-opendata"
URL_ONS = f"https://{BUCKET_ONS}.s3.amazonaws.com/"
ORC_MB = 900  # teto de download por conjunto; CSV antigos são descartados primeiro

# tabela -> (slug no bucket, tema)
CONJUNTOS = {
    "ons_ear_subsistema_diaria": ("ear_subsistema_di", "hidrologia"),
    "ons_ear_bacia_diaria": ("ear_bacia_di", "hidrologia"),
    "ons_ear_ree_diaria": ("ear_ree_di", "hidrologia"),
    "ons_ear_reservatorio_diaria": ("ear_reservatorio_di", "hidrologia"),
    "ons_ena_subsistema_diaria": ("ena_subsistema_di", "hidrologia"),
    "ons_ena_bacia_diaria": ("ena_bacia_di", "hidrologia"),
    "ons_ena_ree_diaria": ("ena_ree_di", "hidrologia"),
    "ons_ena_reservatorio_diaria": ("ena_reservatorio_di", "hidrologia"),
    "ons_hidrologia_reservatorio_diaria": ("dados_hidrologicos_di", "hidrologia"),
    "ons_reservatorio_cadastro": ("reservatorio", "hidrologia"),
    "ons_carga_energia_diaria": ("carga_energia_di", "carga"),
    "ons_carga_energia_mensal": ("carga_energia_me", "carga"),
    "ons_demanda_maxima_diaria": ("demanda_maxima_di", "carga"),
    "ons_interrupcao_carga": ("interrupcao_carga", "confiabilidade"),
    "ons_cmo_semanal": ("cmo_se", "precos"),
    "ons_cvu_termica_semanal": ("cvu_usitermica_se", "precos"),
    "ons_geracao_termica_despacho_horaria": ("geracao_termica_despacho_2_ho", "geracao"),
    "ons_fator_capacidade_diario": ("fator_capacidade_2_di", "geracao"),
    "ons_energia_vertida_turbinavel_horaria": ("energia_vertida_turbinavel_ho", "geracao"),
    "ons_geracao_itaipu": ("geracao_itaipu", "geracao"),
    "ons_disponibilidade_usina_horaria": ("disponibilidade_usina_ho", "geracao"),
    "ons_taxa_teif_teip": ("taxa_teif_teip", "confiabilidade"),
    "ons_intercambio_internacional_horario": ("intercambio_internacional_ho", "intercambio"),
    "ons_intercambio_modalidade_horario": ("intercambio_modalidade_ho", "intercambio"),
    "ons_exportacao_internacional_horaria": ("geracao_exportacao_internacional_ho", "intercambio"),
    "ons_importacao_comercial_horaria": ("importacaoenergia-comercial-2-ho", "intercambio"),
    "ons_linha_transmissao": ("linha_transmissao", "transmissao"),
    "ons_subestacao": ("subestacao", "transmissao"),
    "ons_oferta_resposta_demanda": ("oferta_respostademanda", "mercado"),
}

s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))


def listar(slug: str) -> list[dict]:
    """Só os arquivos da própria pasta: há subpastas de OUTROS conjuntos dentro de algumas pastas
    (ex.: dataset/ear_subsistema_di/precipitacao_estacao_di/)."""
    prefixo = f"dataset/{slug}/"
    objs = []
    for pag in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET_ONS, Prefix=prefixo):
        objs += [o for o in pag.get("Contents", []) if o["Key"] != prefixo and "/" not in o["Key"][len(prefixo):]]
    return objs


def escolher(objs: list[dict]) -> list[dict]:
    """Por período (nome sem extensão), Parquet se existir, senão CSV; respeita o orçamento."""
    por_periodo = {}
    for o in objs:
        stem, ext = o["Key"].rsplit(".", 1)
        ext = ext.lower()
        if ext not in ("parquet", "csv"):
            continue
        atual = por_periodo.get(stem)
        if atual is None or (ext == "parquet" and atual["Key"].endswith(".csv")):
            por_periodo[stem] = o
    escolhidos = sorted(por_periodo.values(), key=lambda o: o["Key"], reverse=True)  # mais recentes primeiro
    total, saida = 0, []
    for o in escolhidos:
        if total + o["Size"] > ORC_MB * 1e6 and saida:
            continue
        total += o["Size"]
        saida.append(o)
    return sorted(saida, key=lambda o: o["Key"])


def metadados_oficiais(objs: list[dict], colunas: dict, tabela: str, slug: str, tema: str) -> dict:
    desc_col, titulo, descricao = {}, slug, ""
    js = [o["Key"] for o in objs if o["Key"].lower().endswith(".json")]
    if js:
        d = json.loads(s3.get_object(Bucket=BUCKET_ONS, Key=js[0])["Body"].read().decode("utf-8-sig"))
        for item in d.get("dicionario_simplificado", []):
            desc_col[nome_coluna(item.get("codigo", ""))] = item.get("descricao", "").strip()
    pdfs = [o["Key"] for o in objs if o["Key"].lower().endswith(".pdf")]
    if pdfs:
        from pypdf import PdfReader
        texto = "\n".join(p.extract_text() or "" for p in
                          PdfReader(io.BytesIO(s3.get_object(Bucket=BUCKET_ONS, Key=pdfs[0])["Body"].read())).pages[:2])
        linhas = [l.strip() for l in texto.splitlines() if l.strip()]
        cab = [l for l in linhas if l.isupper() and len(l) > 12 and "PÁGINA" not in l.upper()[:6]]
        titulo = cab[0].title() if cab else slug
        m = re.search(r"Descrição do Dado:\s*(.+?)(?:\n\s*\n|Descrição Código|Descrição\s+Código)", texto, re.S)
        descricao = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return {"tabela": tabela, "fonte": "ONS", "tema": tema, "titulo": titulo,
            "descricao": f"ONS — {titulo}. {descricao}".strip(),
            "origem": f"{URL_ONS}dataset/{slug}/", "dicionario": "oficial ONS (JSON dicionario_simplificado)",
            "colunas": {c: desc_col.get(c, "") for c in colunas}}


def baixar(o: dict, pasta: Path, objs: list[dict]) -> Path | None:
    """Baixa o arquivo; se o objeto estiver bloqueado (403), tenta o mesmo período em outro formato."""
    from botocore.exceptions import ClientError
    stem = o["Key"].rsplit(".", 1)[0]
    candidatos = [o] + [x for x in objs if x["Key"].rsplit(".", 1)[0] == stem and x["Key"] != o["Key"]
                        and x["Key"].lower().endswith((".parquet", ".csv"))]
    for c in candidatos:
        destino = pasta / c["Key"].rsplit("/", 1)[-1]
        try:
            if not destino.exists() or destino.stat().st_size != c["Size"]:
                s3.download_file(BUCKET_ONS, c["Key"], str(destino))
            return destino
        except ClientError as e:
            print(f"    aviso: {c['Key']} indisponível ({e.response['Error'].get('Code')})", flush=True)
            destino.unlink(missing_ok=True)
    return None


def ingerir(tabela: str) -> dict:
    slug, tema = CONJUNTOS[tabela]
    objs = listar(slug)
    dados = escolher(objs)
    if not dados:
        return {"tabela": tabela, "status": "sem arquivos de dados"}
    pasta = BASE / "out" / "fontes" / "ons" / slug
    pasta.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(8) as ex:
        arquivos = sorted(p for p in ex.map(lambda o: baixar(o, pasta, objs), dados) if p)
    mb = sum(o["Size"] for o in dados) / 1e6
    resumo = unificar(arquivos, BASE / "out" / "lake" / "curated" / tabela)
    meta = metadados_oficiais(objs, resumo["colunas"], tabela, slug, tema)
    meta.update({k: resumo[k] for k in ("linhas", "periodo", "coluna_tempo", "particionada_por_ano")})
    meta["arquivos_fonte"] = len(arquivos)
    (BASE / "out" / "metadados").mkdir(parents=True, exist_ok=True)
    (BASE / "out" / "metadados" / f"{tabela}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
    sem_desc = sum(1 for v in meta["colunas"].values() if not v)
    return {"tabela": tabela, "linhas": resumo["linhas"], "arquivos": len(arquivos), "mb_baixados": round(mb),
            "periodo": resumo["periodo"], "colunas": len(resumo["colunas"]), "colunas_sem_descricao": sem_desc}


if __name__ == "__main__":
    alvo = sys.argv[1:] or list(CONJUNTOS)
    for t in alvo:
        try:
            print(json.dumps(ingerir(t), ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"tabela": t, "erro": f"{type(e).__name__}: {str(e)[:300]}"}, ensure_ascii=False), flush=True)
