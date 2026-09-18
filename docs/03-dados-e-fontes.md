# Dados e fontes

## 1. Layout do bucket `s3://ons-datalake-899110172465`

| prefixo | conteúdo | volume |
|---|---|---|
| `raw/` | arquivos originais únicos (canônicos) do acervo, mesma árvore de `data/raw/` | 3.831 arquivos, 2,52 GB |
| `curated/<tabela>/[ano=AAAA/]` | tabelas unificadas e tipadas (ONS, clima, ANEEL) | 146 arquivos, 1,27 GB |
| `analytics/<tabela>/` | tabelas silver/gold produzidas pela equipe | 15 arquivos, 0,79 GB |
| `catalogo/catalogo.json` | tabelas, caminhos, colunas, tipos, unidades, período, linhas e regras | 1 arquivo |
| `docs/raw/<fonte>/<sha16>.md` + `.json` | documentos coletados (Markdown limpo + metadados) | 392 documentos (384 versões atuais) |
| `docs/estado/<fonte>.json` | url → hash da versão atual (deduplicação da coleta) | 1 por fonte |
| `docs/index/<fonte>.jsonl.gz` + `.f32` + `.versao.json` | índice de busca (texto, vetores, assinatura) | 2.433 trechos |
| `flexia/app/SINAgent/` | código da FlexIA baixado pelo instalador do Code Editor | 7 arquivos |
| `deploy/coletor/` | código do coletor baixado pelo instalador do cron | 3 arquivos |
| `deploy/flexia-coletor.zip` | pacote da Lambda não implantável nesta conta (pode ser apagado) | 24 MB |

Bucket privado (Block Public Access), criptografado (SSE-S3) e versionado.

## 2. Tabelas (33)

Contagens idênticas à origem e conferidas lendo do S3 em 18/09/2026.

| tabela | camada | linhas | anos (partição) | descrição |
|---|---|---:|---|---|
| `aneel_siga_empreendimentos` | curated | 25.133 | — | ANEEL SIGA — cadastro nacional de empreendimentos de geração, com potência, fase, fonte e coordenadas |
| `aneel_tarifas_homologadas` | curated | 327.493 | — | ANEEL — tarifas homologadas (TUSD e TE) de todas as distribuidoras, 2010–2026 |
| `clima_era5_horario` | curated | 1.308.480 | 2023–2026 | Reanálise ERA5 horária em células de 0,25° nos polos eólicos/solares de BA, CE, MG, PB, PE, PI, RN |
| `clima_previsao_horaria` | curated | 360 | — | Previsão Open-Meteo 06–10/set/2026 em três células |
| `ons_balanco_energia_subsistema` | curated | 1.169.397 | 2000–2026 | Balanço horário por subsistema: geração por fonte, carga, intercâmbio (inclui linha `SIN`) |
| `ons_capacidade_geracao` | curated | 5.675 | — | Capacidade instalada por unidade geradora |
| `ons_cmo_semihorario` | curated | 460.992 | 2020–2026 | Custo Marginal de Operação semi-horário por subsistema (R$/MWh) |
| `ons_curva_carga` | curated | 935.512 | 2000–2026 | Carga horária por subsistema (MWmed) |
| `ons_geracao_usina_horaria` | curated | 81.325.046 | 2000–2026 | Geração verificada por usina, horária, todas as fontes |
| `ons_intercambio_nacional` | curated | 908.231 | 2000–2026 | Intercâmbio entre subsistemas, horário |
| `ons_modalidade_usina` | curated | 5.993 | — | Cadastro de usinas: modalidade, potência autorizada, ponto de conexão |
| `ons_programacao_fluxo_controlado` | curated | 1.349.952 | 2024–2026 | Programação diária de fluxo em elementos controlados |
| `ons_programacao_x_previsao` | curated | 18.139.920 | 2024–2026 | Programação diária (PDP) × previsão por usina, 48 patamares/dia |
| `ons_restricao_eolica_detalhe` | curated | 63.733.061 | 2023–2026 | Por usina eólica individual: vento, geração estimada e verificada |
| `ons_restricao_eolica_usina` | curated | 13.224.240 | 2021–2026 | Constrained-off eólico por usina/conjunto, semi-horário |
| `ons_restricao_fotovoltaica_detalhe` | curated | 19.223.000 | 2024–2026 | Por usina FV individual: irradiância, geração estimada e verificada |
| `ons_restricao_fotovoltaica_usina` | curated | 2.878.416 | 2024–2026 | Constrained-off fotovoltaico por usina/conjunto, semi-horário |
| `ons_usina_conjunto` | curated | 2.103 | — | Relação usina ↔ conjunto |
| `analytics_consumo_rj` | analytics | 1 | — | Consumo residencial do estado do RJ + população (EPE/IBGE) |
| `analytics_corte_detalhe` | analytics | 82.956.061 | — | Detalhe eólico por usina com vento tratado (`vento_confiavel`) |
| `analytics_corte_elemento` | analytics | 334 | — | Corte por equipamento de transmissão limitante (cobre ~53 % do volume) |
| `analytics_corte_mensal` | analytics | 3.054 | — | Corte por mês, fonte, subsistema, estado, razão e origem |
| `analytics_corte_usina` | analytics | 16.102.656 | — | **Fato central de corte** eólico+solar por usina e patamar; usar `corte_mwh` |
| `analytics_frota_ev_rio` | analytics | 4 | — | Frota plug-in da cidade do Rio (jan/25, jul/25, jan/26, jul/26) |
| `analytics_gabarito_ene_2026` | analytics | 11.952 | — | Corte ENE verificado 2026 (NE, SE, SIN) |
| `analytics_octopus_agile_amostra` | analytics | 100 | — | Octopus Agile (Reino Unido), preços semi-horários |
| `analytics_octopus_gsp` | analytics | 14 | — | Octopus, grupos de Grid Supply Point |
| `analytics_octopus_produtos` | analytics | 41 | — | Octopus, catálogo de produtos |
| `analytics_octopus_tarifas` | analytics | 494 | — | Octopus, tarifas por produto e GSP |
| `analytics_piso_ruido` | analytics | 90 | — | Viés da geração de referência sem restrição (barra de erro do corte) |
| `analytics_previsao_ene_ne_2026` | analytics | 11.952 | — | Previsão D+1 do corte ENE no NE em 2026 (modelo da equipe) × real |
| `analytics_tarifa_light` | analytics | 2.016 | — | Tarifas homologadas da Light |
| `analytics_usina_geo` | analytics | 1.620 | — | Geolocalização das usinas + célula ERA5 correspondente |

Descrições de cada coluna (com unidades): `pipeline/catalogo.py` e `catalogo/catalogo.json`.

### Arquivos brutos não transformados em tabela
Estão em `raw/` e podem ser curados depois: anuários e workbooks da EPE (`.xls/.xlsx` com layout
de relatório), frota SENATRAN por município (`.xlsx`), anuário DETRAN-RJ (`.pdf`/`.txt`), camadas
GeoJSON da EPE (linhas de transmissão e subestações), páginas raspadas da Octopus/Kraken (`.json`).

## 3. Regras de negócio (entram no prompt da FlexIA)

Fonte única: `pipeline/catalogo.py` → `REGRAS`.

1. MWmed é potência média no intervalo. Em tabela horária, soma de MWmed = MWh; em tabela semi-horária, MWh = MWmed × 0,5.
2. Volume de corte: usar `analytics_corte_usina.corte_mwh`. Nunca `gref − ger` sem filtrar `razao IS NOT NULL` (gref supera a geração em ~49 % dos patamares sem restrição).
3. `val_geracaolimitada`/`lim` nulo = sem limitação; zero = ordem de desligar.
4. `dsc_restricao`, `elemento_restricao` e `mecanismo` só existem a partir de 2025 e cobrem ~53 % do volume.
5. Vento: filtrar `vento_confiavel = true` (há outliers de até 1.374 m/s com flag válida).
6. Frota EV: `plugin` (bev+phev) é o que recarrega na rede.
7. Tarifa Light residencial padrão: `subclasse = 'Residencial'`.
8. `analytics_consumo_rj` é por estado, não por município.
9. Tabelas particionadas: filtrar por `ano`.
10. Chaves: `id_ons` entre tabelas ONS; `ceg` (ONS) = `codceg` (SIGA); `cel_lat/cel_lon` = `latitude/longitude` do ERA5.
11. Subsistemas N, NE, S, SE; SIN = soma dos quatro (e há linha `SIN` no balanço — não somar com os demais).
12. Toda conta e conversão de unidade dentro do SQL; nunca de cabeça.
13. Período coberto só pode ser afirmado após consultar `min/max(din_instante)`.

## 4. Fontes de documentos (Cavuca)

Situação após a primeira coleta completa (18/09/2026). "Documentos atuais" = versões vigentes
indexadas.

| id | órgão | tipo | frequência | situação | docs | trechos |
|---|---|---|---|---|---:|---:|
| `aneel_noticias` | ANEEL | notícias | diária | ativa | 5 | 16 |
| `mme_noticias` | MME | notícias | diária | ativa | 30 | 101 |
| `ccee_noticias` | CCEE | notícias | diária | ativa | 48 | 132 |
| `epe_noticias` | EPE | notícias | diária | ativa | 51 | 147 |
| `planalto_leis_setor` | Planalto | legislação | semanal | ativa | 8 | 426 |
| `aneel_procedimentos` | ANEEL | regulação | semanal | ativa | 5 | 35 |
| `ccee_regras_procedimentos` | CCEE | procedimentos | semanal | ativa | 2 | 36 |
| `epe_publicacoes` | EPE | publicações | mensal | ativa | 99 | 145 |
| `ons_sobre_sin` | ONS | publicações | mensal | ativa | 1 | 3 |
| `ons_dados_abertos` | ONS | dados abertos | semanal | ativa | 65 | 1.050 |
| `aneel_dados_abertos` | ANEEL | dados abertos | semanal | ativa | 36 | 224 |
| `ccee_dados_abertos` | CCEE | dados abertos | semanal | ativa | 34 | 118 |
| `ons_noticias` | ONS | notícias | diária | **inativa** — lista montada por JavaScript | — | — |
| `ons_procedimentos_rede` | ONS | procedimentos | semanal | **inativa** — página montada por JavaScript | — | — |
| `dou_energia` | Imprensa Nacional | legislação | diária | **inativa** — robots.txt proíbe; usar INLABS | — | — |

Leis coletadas do Planalto: Lei 9.427/1996 (ANEEL), Lei 9.648/1998, Lei 10.847/2004 (EPE),
Lei 10.848/2004 (comercialização/CCEE), Decreto 5.163/2004, Lei 14.120/2021, Lei 14.182/2021,
Lei 14.300/2022 (micro e minigeração distribuída).

### Limitações conhecidas da coleta
- **ANEEL notícias** traz poucos documentos por execução (5): o limite de páginas é consumido
  pelas páginas de listagem. Aumentar `max_paginas` ou coletar por ano.
- **Procedimentos ANEEL**: as páginas-índice foram coletadas, mas os PDFs dos módulos (PRODIST,
  PRORET) ainda não — os links ficam em outro domínio/padrão. Ajustar a regra `pdfs`.
- **Fontes com JavaScript** (ONS notícias e Procedimentos de Rede) exigem o modo navegador do
  Cavuca (`DynamicFetcher`/Chromium), viável na EC2 do Code Editor, não na Lambda.
- **Resoluções normativas da ANEEL** (ex.: REN 1.000/2021) ainda não estão no catálogo de fontes.
