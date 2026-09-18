"""Catálogo de fontes do setor elétrico que a FlexIA coleta periodicamente com o Cavuca.

Cada fonte vira arquivos Markdown + metadados em s3://<bucket>/docs/raw/<id>/<AAAA-MM-DD>/.

Campos:
  id          identificador estável (prefixo no S3)
  orgao       instituição de origem
  tipo        noticias | legislacao | publicacoes | dados_abertos | procedimentos
  modo        pagina   -> converte só as URLs listadas
              crawl    -> segue links dentro de `permitir` até `max_paginas`
              ckan     -> lista pacotes via API CKAN (metadados dos conjuntos de dados)
  urls        pontos de partida
  permitir    regex de URLs que o crawl pode seguir (vazio = qualquer uma do domínio)
  negar       regex de URLs a ignorar
  css         seletor do conteúdo principal (reduz ruído de menu/rodapé)
  frequencia  diaria | semanal | mensal (define qual regra agendada roda a fonte)
"""

NEGAR_PADRAO = [r"/login", r"/busca", r"\?print", r"/rss", r"\.(jpg|jpeg|png|gif|zip|mp4)$",
                r"/@@", r"/sendto", r"/view$", r"facebook|twitter|linkedin|whatsapp|youtube"]

FONTES = [
    # ---------------- Notícias (diárias) ----------------
    {"id": "aneel_noticias", "orgao": "ANEEL", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.gov.br/aneel/pt-br/assuntos/noticias"],
     "permitir": [r"gov\.br/aneel/pt-br/assuntos/noticias/20\d\d/"], "css": "#content", "max_paginas": 60},
    {"id": "mme_noticias", "orgao": "MME", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.gov.br/mme/pt-br/assuntos/noticias"],
     "permitir": [r"gov\.br/mme/pt-br/assuntos/noticias/"], "css": "#content", "max_paginas": 60},
    {"id": "ons_noticias", "orgao": "ONS", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.ons.org.br/Paginas/Noticias/Noticias.aspx"],
     "permitir": [r"ons\.org\.br/Paginas/Noticias/"], "max_paginas": 60},
    {"id": "ccee_noticias", "orgao": "CCEE", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.ccee.org.br/web/guest/noticias"],
     "permitir": [r"ccee\.org\.br/.*/noticias/"], "max_paginas": 60},
    {"id": "epe_noticias", "orgao": "EPE", "tipo": "noticias", "modo": "crawl", "frequencia": "diaria",
     "urls": ["https://www.epe.gov.br/pt/imprensa/noticias"],
     "permitir": [r"epe\.gov\.br/pt/imprensa/noticias/"], "max_paginas": 60},
    {"id": "dou_energia", "orgao": "Imprensa Nacional (DOU)", "tipo": "legislacao", "modo": "dou", "frequencia": "diaria",
     "termos": ["energia elétrica", "ANEEL", "Operador Nacional do Sistema Elétrico", "CCEE",
                "Ministério de Minas e Energia", "geração distribuída", "constrained-off", "curtailment",
                "transmissão de energia", "leilão de energia", "resposta da demanda"],
     "urls": ["https://www.in.gov.br/consulta/-/buscar/dou"]},
    # ---------------- Legislação e regulação (semanal) ----------------
    {"id": "planalto_leis_setor", "orgao": "Presidência (Planalto)", "tipo": "legislacao", "modo": "pagina", "frequencia": "semanal",
     "urls": [
         "https://www.planalto.gov.br/ccivil_03/leis/l9427cons.htm",          # cria a ANEEL
         "https://www.planalto.gov.br/ccivil_03/leis/l9648cons.htm",          # cria o ONS / reestruturação
         "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l10.848.htm",  # comercialização / CCEE
         "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/decreto/d5163.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l10.847.htm",  # cria a EPE
         "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14300.htm",   # micro e minigeração distribuída
         "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14120.htm",
         "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14182.htm",
     ]},
    {"id": "aneel_normas_destaque", "orgao": "ANEEL", "tipo": "legislacao", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://www.gov.br/aneel/pt-br/centrais-de-conteudos/procedimentos-regulatorios"],
     "permitir": [r"gov\.br/aneel/pt-br/centrais-de-conteudos/procedimentos-regulatorios"], "css": "#content", "max_paginas": 80},
    {"id": "ons_procedimentos_rede", "orgao": "ONS", "tipo": "procedimentos", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://www.ons.org.br/paginas/sobre-o-ons/procedimentos-de-rede/vigentes"],
     "permitir": [r"ons\.org\.br/paginas/sobre-o-ons/procedimentos-de-rede/"], "max_paginas": 40},
    {"id": "ccee_regras_procedimentos", "orgao": "CCEE", "tipo": "procedimentos", "modo": "crawl", "frequencia": "semanal",
     "urls": ["https://www.ccee.org.br/web/guest/regras-de-comercializacao"],
     "permitir": [r"ccee\.org\.br/.*(regras|procedimentos)"], "max_paginas": 40},
    # ---------------- Publicações e planejamento (mensal) ----------------
    {"id": "epe_publicacoes", "orgao": "EPE", "tipo": "publicacoes", "modo": "crawl", "frequencia": "mensal",
     "urls": ["https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes"],
     "permitir": [r"epe\.gov\.br/pt/publicacoes-dados-abertos/publicacoes/"], "max_paginas": 120},
    {"id": "ons_sobre_sin", "orgao": "ONS", "tipo": "publicacoes", "modo": "crawl", "frequencia": "mensal",
     "urls": ["https://www.ons.org.br/paginas/sobre-o-sin/o-que-e-o-sin"],
     "permitir": [r"ons\.org\.br/paginas/sobre-o-sin/"], "max_paginas": 30},
    # ---------------- Catálogos de dados abertos (semanal) ----------------
    {"id": "ons_dados_abertos", "orgao": "ONS", "tipo": "dados_abertos", "modo": "ckan", "frequencia": "semanal",
     "urls": ["https://dados.ons.org.br"]},
    {"id": "aneel_dados_abertos", "orgao": "ANEEL", "tipo": "dados_abertos", "modo": "ckan", "frequencia": "semanal",
     "urls": ["https://dadosabertos.aneel.gov.br"]},
    {"id": "ccee_dados_abertos", "orgao": "CCEE", "tipo": "dados_abertos", "modo": "ckan", "frequencia": "semanal",
     "urls": ["https://dadosabertos.ccee.org.br"]},
]

for f in FONTES:
    f.setdefault("negar", NEGAR_PADRAO)
    f.setdefault("permitir", [])
    f.setdefault("css", None)
    f.setdefault("max_paginas", 50)
