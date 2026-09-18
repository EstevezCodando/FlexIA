"""Catálogo de fontes do setor elétrico que a FlexIA coleta periodicamente com o Cavuca.

Cada documento vira s3://<bucket>/docs/raw/<id>/<sha16>.md + .json (metadados). O robots.txt de
todas as fontes é respeitado (verificado em 18/09/2026 com coleta/sondar_fontes.py):
  - in.gov.br (DOU): "Disallow: /"  -> NÃO raspamos; usar INLABS (XML oficial, exige cadastro)
  - dados*.org.br / *.gov.br (CKAN): "/api/" bloqueado, "Crawl-Delay: 10" -> páginas /dataset com 10 s
  - epe.gov.br: bloqueia "*.aspx"
  - ccee.org.br, gov.br, ons.org.br, planalto.gov.br: sem restrição para estes caminhos

Campos:
  id          identificador estável (prefixo no S3)
  orgao       instituição de origem
  tipo        noticias | legislacao | regulacao | publicacoes | dados_abertos | procedimentos
  modo        pagina -> converte só as URLs listadas
              crawl  -> segue links dentro de `permitir` até `max_paginas`
  urls        pontos de partida
  permitir    regex de URLs HTML que o crawl pode seguir
  pdfs        regex de links para PDF a baixar e extrair texto (vazio = não baixa PDF)
  negar       regex de URLs a ignorar
  css         seletor do conteúdo principal (reduz ruído de menu/rodapé)
  atraso      segundos entre requisições (respeita Crawl-Delay)
  frequencia  diaria | semanal | mensal
  ativa       False = não roda (motivo em `obs`)
"""

NEGAR_PADRAO = [r"/login", r"/busca", r"\?print", r"/rss", r"\.(jpg|jpeg|png|gif|zip|mp4|xlsx?|csv)$",
                r"/@@", r"sendto_form", r"folder_factories", r"facebook|twitter|linkedin|whatsapp|youtube|instagram"]
CKAN_NEGAR = [r"/api/", r"/dataset/rate/", r"/revision/", r"/history", r"res_format=", r"tags=", r"groups=",
              r"organization=", r"license_id=", r"/resource/"]

FONTES = [
    # ---------------- Notícias (diárias) ----------------
    {"id": "aneel_noticias", "orgao": "ANEEL", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.gov.br/aneel/pt-br/assuntos/noticias"],
     "permitir": [r"gov\.br/aneel/pt-br/assuntos/noticias(/20\d\d/.*)?(\?b_start:int=\d+)?$"], "css": "#content", "max_paginas": 60},
    {"id": "mme_noticias", "orgao": "MME", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.gov.br/mme/pt-br/assuntos/noticias"],
     "permitir": [r"gov\.br/mme/pt-br/assuntos/noticias(/.*)?$"], "css": "#content", "max_paginas": 60},
    {"id": "ons_noticias", "orgao": "ONS", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "ativa": False, "obs": "lista de notícias montada por JavaScript (SharePoint); exige coletor com navegador (fase 2)",
     "urls": ["https://www.ons.org.br/paginas/imprensa/noticias"],
     "permitir": [r"ons\.org\.br/paginas/imprensa/noticias", r"ons\.org\.br/Paginas/Noticias/"], "max_paginas": 60},
    {"id": "ccee_noticias", "orgao": "CCEE", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.ccee.org.br/web/guest/noticias"],
     "permitir": [r"ccee\.org\.br/web/guest/noticias", r"ccee\.org\.br/web/guest/-/"], "css": ".news-content",
     "max_paginas": 60},
    {"id": "epe_noticias", "orgao": "EPE", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.epe.gov.br/pt/imprensa/noticias"],
     "permitir": [r"epe\.gov\.br/pt/imprensa/noticias"], "negar_extra": [r"\.aspx"], "css": ".ms-rtestate-field",
     "max_paginas": 60},
    {"id": "dou_energia", "orgao": "Imprensa Nacional (DOU)", "tipo": "legislacao", "modo": "inlabs", "frequencia": "diaria",
     "ativa": False, "obs": "in.gov.br proíbe robôs; usar INLABS (XML oficial) após cadastro do usuário",
     "termos": ["energia elétrica", "ANEEL", "Operador Nacional do Sistema Elétrico", "Câmara de Comercialização",
                "Ministério de Minas e Energia", "geração distribuída", "leilão de energia", "resposta da demanda"],
     "urls": ["https://inlabs.in.gov.br"]},
    # ---------------- Legislação e regulação (semanal) ----------------
    {"id": "planalto_leis_setor", "orgao": "Presidência (Planalto)", "tipo": "legislacao", "modo": "pagina", "frequencia": "semanal",
     "urls": [
         "https://www.planalto.gov.br/ccivil_03/leis/l9427cons.htm",
         "https://www.planalto.gov.br/ccivil_03/leis/l9648cons.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l10.848.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/decreto/d5163.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l10.847.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14300.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14120.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14182.htm",
     ]},
    {"id": "aneel_procedimentos", "orgao": "ANEEL", "tipo": "regulacao", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://www.gov.br/aneel/pt-br/centrais-de-conteudos/procedimentos-regulatorios"],
     "permitir": [r"gov\.br/aneel/pt-br/centrais-de-conteudos/procedimentos-regulatorios"],
     "pdfs": [r"gov\.br/aneel/.*\.pdf", r"aneel\.gov\.br/.*\.pdf"], "css": "#content", "max_paginas": 80},
    {"id": "ccee_regras_procedimentos", "orgao": "CCEE", "tipo": "procedimentos", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://www.ccee.org.br/web/guest/regras-de-comercializacao"],
     "permitir": [r"ccee\.org\.br/.*(regras|procedimentos)"], "max_paginas": 40},
    {"id": "ons_procedimentos_rede", "orgao": "ONS", "tipo": "procedimentos", "modo": "crawl", "frequencia": "semanal",
     "ativa": False, "obs": "página montada por JavaScript; exige coletor com navegador (fase 2)",
     "urls": ["https://www.ons.org.br/paginas/sobre-o-ons/procedimentos-de-rede/vigentes"]},
    # ---------------- Publicações e planejamento (mensal) ----------------
    {"id": "epe_publicacoes", "orgao": "EPE", "tipo": "publicacoes", "modo": "crawl", "frequencia": "mensal",
     "urls": ["https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes"],
     "permitir": [r"epe\.gov\.br/pt/publicacoes-dados-abertos/publicacoes"], "negar_extra": [r"\.aspx"],
     "css": ".ms-rtestate-field", "max_paginas": 120},
    {"id": "ons_sobre_sin", "orgao": "ONS", "tipo": "publicacoes", "modo": "crawl", "frequencia": "mensal",
     "urls": ["https://www.ons.org.br/paginas/sobre-o-sin/o-que-e-o-sin"],
     "permitir": [r"ons\.org\.br/paginas/sobre-o-sin/"], "max_paginas": 30},
    # ---------------- Catálogos de dados abertos (semanal, 10 s entre páginas) ----------------
    {"id": "ons_dados_abertos", "orgao": "ONS", "tipo": "dados_abertos", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://dados.ons.org.br/dataset/"], "permitir": [r"dados\.ons\.org\.br/dataset/"],
     "negar_extra": CKAN_NEGAR, "atraso": 10, "max_paginas": 70},
    {"id": "aneel_dados_abertos", "orgao": "ANEEL", "tipo": "dados_abertos", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://dadosabertos.aneel.gov.br/dataset/"], "permitir": [r"dadosabertos\.aneel\.gov\.br/dataset/"],
     "negar_extra": CKAN_NEGAR, "atraso": 10, "max_paginas": 70},
    {"id": "ccee_dados_abertos", "orgao": "CCEE", "tipo": "dados_abertos", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://dadosabertos.ccee.org.br/dataset/"], "permitir": [r"dadosabertos\.ccee\.org\.br/dataset/"],
     "negar_extra": CKAN_NEGAR, "atraso": 10, "max_paginas": 70},
]

for f in FONTES:
    if f["tipo"] == "dados_abertos":
        f.setdefault("css", "article.module")  # corpo do conjunto de dados no CKAN
    f["negar"] = NEGAR_PADRAO + f.pop("negar_extra", [])
    f.setdefault("permitir", [])
    f.setdefault("pdfs", [])
    f.setdefault("css", None)
    f.setdefault("atraso", 1.5)
    f.setdefault("max_paginas", 50)
    f.setdefault("ativa", True)
    # URLs de listagem: o crawl passa por elas para achar links, mas não as grava como documento
    f.setdefault("indices", [r"[?&](b_start|page|pagina|p_p_id)[:=]", r"/noticias/?$", r"/noticias/area-\d+",
                             r"/dataset/?(\?.*)?$",
                             r"/publicacoes/?$", r"/procedimentos-regulatorios/?$"])

POR_ID = {f["id"]: f for f in FONTES}
