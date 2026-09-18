"""Dicionário de dados do lake: descrição de tabelas e colunas (vai para o Glue Data Catalog)
e regras de negócio que o assistente de IA deve respeitar ao gerar SQL.

Fontes das definições: dicionários do ONS Dados Abertos, ANEEL, Open-Meteo e o README do acervo
da equipe (C:/Hackathon_ONS/analise_rio/README_acervo_original.md).
"""

SUBSISTEMA = "Subsistema do SIN: N (Norte), NE (Nordeste), S (Sul), SE (Sudeste/Centro-Oeste)"
USINA = {
    "nom_usina": "Nome da usina ou conjunto de usinas",
    "id_ons": "Código da usina/conjunto no ONS (chave para cruzar tabelas ONS)",
    "ceg": "Código Único de Empreendimentos de Geração da ANEEL (chave para cruzar com aneel_siga_empreendimentos.codceg); nulo para conjuntos",
    "id_subsistema": SUBSISTEMA,
    "nom_subsistema": "Nome do subsistema",
    "id_estado": "UF (sigla do estado)",
    "nom_estado": "Nome do estado",
}
RESTRICAO_USINA = {
    **USINA,
    "din_instante": "Início do patamar semi-horário (30 min)",
    "val_geracao": "Geração verificada (SCADA) no patamar, MWmed",
    "val_geracaolimitada": "Limite de geração imposto pelo ONS, MWmed. NULO = sem limitação; ZERO = ordem de desligar",
    "val_disponibilidade": "Disponibilidade eletromecânica, MWmed",
    "val_geracaoreferencia": "Geração de referência (ESTIMATIVA do que seria gerado sem restrição), MWmed — tem viés, ver regras",
    "val_geracaoreferenciafinal": "Geração de referência final (após ajustes do ONS), MWmed",
    "cod_razaorestricao": "Razão da restrição: ENE (energética / excesso de oferta), CNF (confiabilidade elétrica), REL (indisponibilidade externa), PAR (parecer de acesso). Nulo = sem restrição",
    "cod_origemrestricao": "Origem da restrição: LOC (local) ou SIS (sistêmica)",
    "dsc_restricao": "Texto livre que nomeia o equipamento de transmissão limitante (existe a partir de 2025)",
    "id_pontoconexao": "Código do ponto de conexão (a partir de 2026)",
    "nom_pontoconexao": "Nome do ponto de conexão (a partir de 2026)",
    "nom_agenteoperador": "Agente operador da usina (a partir de 2026)",
    "val_geracaonaorealizadaapurada": "Geração não realizada apurada pelo ONS no patamar, MWmed (a partir de 2026)",
    "num_minutos_rel": "Minutos do patamar sob restrição REL (a partir de 2026)",
    "num_minutos_cnf": "Minutos do patamar sob restrição CNF (a partir de 2026)",
    "num_minutos_ene": "Minutos do patamar sob restrição ENE (a partir de 2026)",
    "num_minutos_restricao": "Minutos totais do patamar sob restrição (a partir de 2026)",
}
RESTRICAO_DETALHE = {
    **USINA,
    "nom_modalidadeoperacao": "Modalidade de operação da usina no ONS",
    "nom_conjuntousina": "Nome do conjunto ao qual a usina pertence",
    "id_ons_conjuntousina": "Código ONS do conjunto (a partir de 2026)",
    "din_instante": "Início do patamar semi-horário (30 min)",
    "val_geracaoestimada": "Geração estimada pela curva recurso×potência, MWmed",
    "val_geracaoverificada": "Geração verificada, MWmed",
    "val_geracaoreferenciafinal": "Geração de referência final, MWmed (a partir de 2026)",
    "nom_origemgeracaoreferencia": "Origem do dado da geração de referência (a partir de 2026)",
    "flg_geracaorestrita": "1 se o patamar estava sob restrição (a partir de 2026)",
}
TEMPO = {"ano": "Ano (partição). SEMPRE filtre por ano quando possível para reduzir custo e tempo da consulta"}

TABELAS = {
    # ---------------- ONS ----------------
    "ons_geracao_usina_horaria": {
        "descricao": "ONS — geração verificada por usina em base horária, jan/2000 a set/2026, todas as fontes (81 M linhas).",
        "colunas": {
            **USINA, **TEMPO,
            "din_instante": "Início da hora",
            "cod_modalidadeoperacao": "Modalidade de operação: TIPO I, TIPO II-A, TIPO II-B, TIPO II-C, TIPO III",
            "nom_tipousina": "Tipo de usina: HIDROELÉTRICA, TÉRMICA, EOLIELÉTRICA, FOTOVOLTAICA, NUCLEAR",
            "nom_tipocombustivel": "Combustível/fonte primária",
            "val_geracao": "Geração verificada na hora, MWmed (numericamente igual a MWh na hora)",
        },
    },
    "ons_balanco_energia_subsistema": {
        "descricao": "ONS — balanço de energia horário por subsistema: geração por fonte, carga e intercâmbio, 2000–2026.",
        "colunas": {
            **TEMPO,
            "id_subsistema": SUBSISTEMA + "; também traz a linha SIN (total nacional) — não some SIN com os subsistemas", "nom_subsistema": "Nome do subsistema",
            "din_instante": "Início da hora",
            "val_gerhidraulica": "Geração hidráulica, MWmed", "val_gertermica": "Geração térmica, MWmed",
            "val_gereolica": "Geração eólica, MWmed", "val_gersolar": "Geração solar, MWmed",
            "val_carga": "Carga do subsistema, MWmed",
            "val_intercambio": "Intercâmbio líquido = geração - carga, MWmed (positivo = exportação, negativo = importação)",
        },
    },
    "ons_curva_carga": {
        "descricao": "ONS — curva de carga horária por subsistema, 2000–2026.",
        "colunas": {**TEMPO, "id_subsistema": SUBSISTEMA, "nom_subsistema": "Nome do subsistema",
                    "din_instante": "Início da hora", "val_cargaenergiahomwmed": "Carga de energia na hora, MWmed"},
    },
    "ons_cmo_semihorario": {
        "descricao": "ONS — Custo Marginal de Operação (CMO) semi-horário por subsistema, 2020–2026.",
        "colunas": {**TEMPO, "id_subsistema": SUBSISTEMA, "nom_subsistema": "Nome do subsistema",
                    "din_instante": "Início do patamar de 30 min", "val_cmo": "CMO, R$/MWh"},
    },
    "ons_intercambio_nacional": {
        "descricao": "ONS — intercâmbio de energia entre subsistemas, horário, 2000–2026.",
        "colunas": {
            **TEMPO, "din_instante": "Início da hora",
            "id_subsistema_origem": "Subsistema de origem", "nom_subsistema_origem": "Nome do subsistema de origem",
            "id_subsistema_destino": "Subsistema de destino", "nom_subsistema_destino": "Nome do subsistema de destino",
            "val_intercambiomwmed": "Intercâmbio verificado, MWmed",
            "val_intercambioprogmwmed": "Intercâmbio programado, MWmed (só a partir de 2026)",
        },
    },
    "ons_restricao_eolica_usina": {
        "descricao": "ONS — restrição de operação por constrained-off de usinas EÓLICAS, semi-horário por usina/conjunto, out/2021–set/2026. Base oficial para corte (curtailment) eólico.",
        "colunas": {**RESTRICAO_USINA, **TEMPO},
    },
    "ons_restricao_fotovoltaica_usina": {
        "descricao": "ONS — restrição de operação por constrained-off de usinas FOTOVOLTAICAS, semi-horário por usina/conjunto, abr/2024–set/2026.",
        "colunas": {**RESTRICAO_USINA, **TEMPO},
    },
    "ons_restricao_eolica_detalhe": {
        "descricao": "ONS — detalhamento por usina eólica individual: vento medido, geração estimada e verificada, semi-horário, jan/2023–set/2026 (64 M linhas).",
        "colunas": {
            **RESTRICAO_DETALHE, **TEMPO,
            "val_ventoverificado": "Velocidade do vento verificada na usina, m/s (tem outliers — ver regras)",
            "flg_dadoventoinvalido": "1 se o ONS marcou o dado de vento como inválido",
            "flg_dadoventosupervisaoinvalido": "1 se o dado de vento da supervisão é inválido (a partir de 2026)",
            "nom_origemvento": "Origem do dado de vento (a partir de 2026)",
        },
    },
    "ons_restricao_fotovoltaica_detalhe": {
        "descricao": "ONS — detalhamento por usina fotovoltaica individual: irradiância, geração estimada e verificada, semi-horário, abr/2024–set/2026.",
        "colunas": {
            **RESTRICAO_DETALHE, **TEMPO,
            "val_irradianciaverificado": "Irradiância verificada na usina, W/m²",
            "flg_dadoirradianciainvalido": "1 se o ONS marcou a irradiância como inválida",
            "flg_dadoirradianciasupervisaoinvalido": "1 se a irradiância da supervisão é inválida (a partir de 2026)",
            "nom_origemirradiancia": "Origem do dado de irradiância (a partir de 2026)",
        },
    },
    "ons_programacao_x_previsao": {
        "descricao": "ONS — programação diária (PDP) versus previsão de geração por usina, 48 patamares semi-horários por dia, out/2024–set/2026.",
        "colunas": {
            **TEMPO, "dat_programacao": "Dia da programação", "num_patamar": "Patamar semi-horário do dia (1 = 00:00–00:30 ... 48 = 23:30–24:00)",
            "cod_usinapdp": "Código da usina na PDP", "nom_usinapdp": "Nome da usina na PDP",
            "val_previsao": "Geração prevista, MWmed", "val_programado": "Geração programada pelo ONS, MWmed",
        },
    },
    "ons_programacao_fluxo_controlado": {
        "descricao": "ONS — programação diária de fluxo em elementos de transmissão controlados, por patamar semi-horário, out/2024–set/2026.",
        "colunas": {
            **TEMPO, "din_programacaodia": "Dia da programação", "num_patamar": "Patamar semi-horário do dia (1..48)",
            "nom_elementofluxocontrolado": "Nome do elemento de fluxo controlado", "dsc_elementofluxocontrolado": "Descrição do elemento",
            "tip_terminal": "Terminal de referência do fluxo", "cod_submercado": "Submercado", "val_carga": "Fluxo programado, MW",
        },
    },
    "ons_capacidade_geracao": {
        "descricao": "ONS — cadastro de capacidade instalada por unidade geradora (potência efetiva, datas de operação).",
        "colunas": {
            **USINA, "nom_modalidadeoperacao": "Modalidade de operação", "nom_agenteproprietario": "Agente proprietário",
            "nom_agenteoperador": "Agente operador", "nom_tipousina": "Tipo de usina", "nom_unidadegeradora": "Nome da unidade geradora",
            "cod_equipamento": "Código do equipamento", "num_unidadegeradora": "Número da unidade geradora", "nom_combustivel": "Combustível",
            "dat_entradateste": "Data de entrada em teste (texto)", "dat_entradaoperacao": "Data de entrada em operação comercial (texto)",
            "dat_desativacao": "Data de desativação (texto; nulo = ativa)", "val_potenciaefetiva": "Potência efetiva da unidade, MW",
        },
    },
    "ons_modalidade_usina": {
        "descricao": "ONS — cadastro de usinas com modalidade de operação, potência autorizada e ponto de conexão.",
        "colunas": {
            **USINA, "nom_modalidadeoperacao": "Modalidade de operação", "val_potenciaautorizada": "Potência autorizada, MW",
            "sgl_centrooperacao": "Centro de operação do ONS responsável", "nom_pontoconexao": "Ponto de conexão",
            "sts_aneel": "Situação na ANEEL",
        },
    },
    "ons_usina_conjunto": {
        "descricao": "ONS — relacionamento entre usinas individuais e conjuntos de usinas (use para ligar tabelas por usina a tabelas por conjunto).",
        "colunas": {
            **USINA, "estad_id": "UF", "id_tipousina": "Código do tipo de usina", "nom_tipousina": "Tipo de usina",
            "id_conjuntousina": "Código numérico do conjunto", "id_ons_conjunto": "Código ONS do conjunto",
            "id_ons_usina": "Código ONS da usina", "nom_conjunto": "Nome do conjunto",
            "dat_iniciorelacionamento": "Início do vínculo (texto)", "dat_fimrelacionamento": "Fim do vínculo (texto; nulo = vigente)",
        },
    },
    # ---------------- Clima ----------------
    "clima_era5_horario": {
        "descricao": "Reanálise ERA5 (Open-Meteo) horária em células de 0,25° próximas a polos eólicos/solares de BA, CE, MG, PB, PE, PI, RN; 2023–set/2026 (e polos nomeados jan–mar/2025).",
        "colunas": {
            **TEMPO, "polo": "Identificador do ponto: UF_LAT_LON (célula) ou UF_NOME (polo nomeado)", "uf": "UF",
            "latitude": "Latitude", "longitude": "Longitude", "din_instante": "Hora (UTC)",
            "vento_100m_kmh": "Velocidade do vento a 100 m, km/h", "direcao_vento_100m_graus": "Direção do vento a 100 m, graus",
            "rajada_10m_kmh": "Rajada a 10 m, km/h", "vento_10m_kmh": "Velocidade do vento a 10 m, km/h",
            "radiacao_global_wm2": "Radiação de onda curta (global), W/m²", "radiacao_direta_wm2": "Radiação direta, W/m²",
            "temperatura_2m_c": "Temperatura a 2 m, °C", "pressao_superficie_hpa": "Pressão à superfície, hPa",
        },
    },
    "clima_previsao_horaria": {
        "descricao": "Previsão meteorológica horária (Open-Meteo) para 06–10/set/2026 em três células (MG, RN).",
        "colunas": {},  # mesmas colunas de clima_era5_horario
    },
    # ---------------- ANEEL ----------------
    "aneel_tarifas_homologadas": {
        "descricao": "ANEEL — tarifas homologadas de todas as distribuidoras (TUSD e TE), por subgrupo, modalidade, classe, posto e vigência, 2010–2026.",
        "colunas": {
            "datgeracaoconjuntodados": "Data de geração do conjunto de dados", "dscreh": "Resolução homologatória",
            "sigagente": "Distribuidora (sigla)", "numcnpjdistribuidora": "CNPJ da distribuidora",
            "datiniciovigencia": "Início da vigência", "datfimvigencia": "Fim da vigência",
            "dscbasetarifaria": "Base tarifária: 'Tarifa de Aplicação' (a que o consumidor paga) ou 'Base Econômica'",
            "dscsubgrupo": "Subgrupo tarifário (A1..A4, AS, B1, B2, B3, B4)", "dscmodalidadetarifaria": "Modalidade: Convencional, Branca, Azul, Verde...",
            "dscclasse": "Classe de consumo", "dscsubclasse": "Subclasse de consumo", "dscdetalhe": "Detalhe",
            "nompostotarifario": "Posto tarifário: Ponta, Fora ponta, Intermediário, Não se aplica",
            "dscunidadeterciaria": "Unidade do valor: MWh ou kW", "sigagenteacessante": "Agente acessante",
            "vlrtusd": "Tarifa de Uso do Sistema de Distribuição, R$ por unidade (dscunidadeterciaria)",
            "vlrte": "Tarifa de Energia, R$ por unidade (dscunidadeterciaria)",
        },
    },
    "aneel_siga_empreendimentos": {
        "descricao": "ANEEL SIGA — cadastro nacional de empreendimentos de geração, com potência, fase, fonte e coordenadas.",
        "colunas": {
            "nomempreendimento": "Nome do empreendimento", "codceg": "Código CEG (chave para ceg nas tabelas ONS)",
            "idenucleoceg": "Núcleo do CEG", "sigufprincipal": "UF", "sigtipogeracao": "Tipo: UHE, PCH, CGH, UTE, EOL, UFV, UTN",
            "dscfaseusina": "Fase: Operação, Construção, Construção não iniciada", "dscorigemcombustivel": "Origem do combustível",
            "dscfontecombustivel": "Fonte do combustível", "dsctipooutorga": "Tipo de outorga", "nomfontecombustivel": "Fonte",
            "datentradaoperacao": "Data de entrada em operação", "mdapotenciaoutorgadakw": "Potência outorgada, kW",
            "mdapotenciafiscalizadakw": "Potência fiscalizada, kW", "mdagarantiafisicakw": "Garantia física, kW",
            "idcgeracaoqualificada": "Geração qualificada (Sim/Não)", "numcoordnempreendimento": "Latitude",
            "numcoordeempreendimento": "Longitude", "dscsubbacia": "Sub-bacia hidrográfica", "dscmuninicpios": "Municípios",
            "dscpropriregimepariticipacao": "Proprietários e regime de participação",
        },
    },
    # ---------------- Analytics (produzidos pela equipe) ----------------
    "analytics_corte_usina": {
        "descricao": "Fato central de CORTE (curtailment) eólico+solar por usina/conjunto e patamar de 30 min, out/2021–set/2026. PREFIRA esta tabela para perguntas de volume de corte.",
        "colunas": {
            "fonte": "EOLICA ou SOLAR", "id_subsistema": SUBSISTEMA, "id_estado": "UF", "nom_usina": "Usina/conjunto",
            "id_ons": "Código ONS", "ceg": "CEG ANEEL (nulo em conjuntos)", "din_instante": "Início do patamar de 30 min",
            "ger": "Geração verificada, MWmed", "lim": "Limite imposto; NULO = sem limitação, ZERO = desligar",
            "disp": "Disponibilidade, MWmed", "gref": "Geração de referência (estimativa com viés), MWmed",
            "gref_final": "Geração de referência final, MWmed", "razao": "ENE, CNF, REL ou PAR; nulo = sem restrição",
            "origem": "LOC ou SIS", "dsc_restricao": "Texto do equipamento limitante (a partir de 2025)",
            "tipo_controle": "Tipo de controle extraído de dsc_restricao", "elemento_restricao": "Equipamento de transmissão extraído de dsc_restricao",
            "ref_operativa": "Referência operativa extraída de dsc_restricao", "mecanismo": "Mecanismo de restrição extraído de dsc_restricao",
            "restrito": "true se o patamar estava sob restrição declarada",
            "corte_mwmed": "Corte apurado, MWmed (zero quando não há restrição declarada)",
            "corte_mwh": "Corte apurado, MWh no patamar de 30 min (= corte_mwmed × 0,5). Some esta coluna para volume de corte",
        },
    },
    "analytics_corte_detalhe": {
        "descricao": "Detalhe por usina eólica individual com vento tratado, jan/2023–set/2026 (83 M linhas).",
        "colunas": {
            "fonte": "EOLICA ou SOLAR", "vento_ms": "Vento medido na usina, m/s", "vento_invalido": "Flag de qualidade do ONS",
            "vento_confiavel": "USE ESTA: true se flag válida E 0 < vento_ms <= 40", "ger_estimada": "Geração estimada, MWmed",
            "ger_verificada": "Geração verificada, MWmed", "conjunto": "Conjunto", "modalidade": "Modalidade de operação",
        },
    },
    "analytics_usina_geo": {
        "descricao": "Geolocalização de 1.620 usinas eólicas/solares, com célula ERA5 correspondente (cel_lat/cel_lon) para cruzar com clima_era5_horario.",
        "colunas": {"coord_valida": "false para coordenadas (0,0)", "mw_fiscalizada": "Potência fiscalizada, MW",
                    "cel_lat": "Latitude da célula ERA5 de 0,25°", "cel_lon": "Longitude da célula ERA5 de 0,25°"},
    },
    "analytics_corte_mensal": {
        "descricao": "Corte agregado por mês, fonte, subsistema, estado, razão e origem.",
        "colunas": {"mes": "Primeiro dia do mês", "patamares": "Nº de patamares de 30 min", "usinas": "Nº de usinas",
                    "mwh_cortado": "Energia cortada, MWh", "mwh_gerado": "Energia gerada, MWh"},
    },
    "analytics_corte_elemento": {
        "descricao": "Corte agregado por equipamento de transmissão limitante (elemento_restricao), com usinas afetadas e dias ativos. Cobre ~53% do volume (dsc_restricao só existe a partir de 2025).",
        "colunas": {"primeiro": "Primeiro patamar com restrição", "ultimo": "Último patamar", "dias_ativos": "Dias com restrição",
                    "usinas_afetadas": "Nº de usinas afetadas", "mwh_cortado": "Energia cortada, MWh"},
    },
    "analytics_piso_ruido": {
        "descricao": "Viés da geração de referência medido em patamares SEM restrição (onde o corte deveria ser zero). Use como barra de erro dos números de corte.",
        "colunas": {"mes": "Mês", "patamares_livres": "Patamares sem restrição", "frac_gref_maior": "Fração em que gref > geração verificada",
                    "erro_rel_p50": "Erro relativo mediano", "erro_rel_p90": "Erro relativo p90", "mwh_fantasma": "Corte aparente (inexistente) se gref-ger fosse usado sem filtro, MWh"},
    },
    "analytics_gabarito_ene_2026": {
        "descricao": "Gabarito (valor real) do corte energético (ENE) 2026 por instante, NE, SE e SIN.",
        "colunas": {"ene_ne": "Corte ENE Nordeste", "ene_se": "Corte ENE Sudeste", "ene_sin": "Corte ENE SIN"},
    },
    "analytics_previsao_ene_ne_2026": {
        "descricao": "Previsão D+1 do corte energético (ENE) no Nordeste em 2026 pelo modelo da equipe, versus real.",
        "colunas": {"real_ne": "Corte real NE", "previsto": "Corte previsto pelo modelo", "clima_ne": "Variável climática de entrada"},
    },
    "analytics_frota_ev_rio": {
        "descricao": "Frota de veículos plug-in da cidade do Rio de Janeiro (SENATRAN), 4 meses: jan/25, jul/25, jan/26, jul/26.",
        "colunas": {"mes": "Mês de referência", "bev": "100% elétricos", "phev": "Híbridos plug-in",
                    "plugin": "bev + phev (o que recarrega na rede)", "frota_total": "Frota total da cidade"},
    },
    "analytics_tarifa_light": {
        "descricao": "Tarifas homologadas da Light (distribuidora do Rio), todas as modalidades e vigências.",
        "colunas": {"te_mwh": "TE, R$/MWh", "tusd_mwh": "TUSD, R$/MWh", "preco_kwh": "TE+TUSD, R$/kWh, sem tributos",
                    "subclasse": "Filtre subclasse='Residencial' para a tarifa residencial padrão"},
    },
    "analytics_consumo_rj": {
        "descricao": "Consumo residencial de energia do ESTADO do RJ (EPE) com população da capital e do estado (IBGE 2022).",
        "colunas": {},
    },
    "analytics_octopus_tarifas": {"descricao": "Octopus Energy (Reino Unido) — tarifas por produto e GSP, em pence com VAT.", "colunas": {}},
    "analytics_octopus_produtos": {"descricao": "Octopus Energy (Reino Unido) — catálogo de produtos tarifários.", "colunas": {}},
    "analytics_octopus_agile_amostra": {"descricao": "Octopus Agile (Reino Unido) — amostra de preços semi-horários dinâmicos, pence/kWh.", "colunas": {}},
    "analytics_octopus_gsp": {"descricao": "Octopus (Reino Unido) — grupos de Grid Supply Point.", "colunas": {}},
}

# Regras que entram no prompt do assistente para evitar respostas erradas.
REGRAS = [
    "Unidades: MWmed é potência média no intervalo. Em tabela horária, soma de MWmed = MWh. Em tabela semi-horária (30 min), MWh = MWmed × 0,5.",
    "Para volume de corte (curtailment), use analytics_corte_usina.corte_mwh (já filtrado por restrição declarada). Nunca calcule gref - ger sem filtrar razao IS NOT NULL: gref supera a geração em ~49% dos patamares SEM restrição.",
    "val_geracaolimitada / lim NULO significa sem limitação; ZERO significa ordem de desligar. Não trate nulo como zero.",
    "dsc_restricao, elemento_restricao e mecanismo só existem a partir de 2025 e cobrem ~53% do volume de corte; declare essa cobertura ao responder.",
    "Vento: filtre analytics_corte_detalhe por vento_confiavel = true; há outliers de até 1.374 m/s mesmo com flag válida.",
    "analytics_frota_ev_rio.plugin (bev+phev) é a frota que recarrega na rede; não conte híbridos sem tomada.",
    "analytics_tarifa_light: para tarifa residencial padrão filtre subclasse = 'Residencial'.",
    "analytics_consumo_rj é por estado, não por município.",
    "Tabelas particionadas por ano: sempre inclua filtro em ano quando a pergunta tiver período, para reduzir custo.",
    "Chaves de junção: id_ons entre tabelas ONS; ceg (ONS) = codceg (ANEEL SIGA); analytics_usina_geo.cel_lat/cel_lon = clima_era5_horario.latitude/longitude.",
    "Subsistemas: N, NE, S, SE. SIN = soma dos quatro.",
    "Faça TODA conta e conversão de unidade dentro do SQL (ex.: sum(val_gersolar)/1e6 AS twh, round(...)); nunca converta, divida ou some números de cabeça na resposta — copie o valor que a consulta retornou.",
    "Não afirme o período coberto (ex.: 'até setembro') sem consultá-lo: use min(din_instante)/max(din_instante) na mesma consulta.",
]
