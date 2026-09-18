# FlexIA — data lake do setor elétrico e copiloto de IA na AWS

Projeto do Hackathon ONS. Reúne os dados do acervo da equipe (ONS, clima, ANEEL, EPE, SENATRAN e
análises próprias) num data lake no Amazon S3, coleta periodicamente documentos públicos do setor
(leis, regulação, notícias, catálogos de dados abertos) com o [Cavuca](https://github.com/EstevezCodando/Cavuca)
e expõe tudo por meio da **FlexIA**, uma assistente em chat que responde com números consultados
nos dados e trechos citados dos documentos, usando **NVIDIA Nemotron** para decidir e rotear cada
pergunta e **Claude** (Amazon Bedrock) para responder.

> Estado em 18/09/2026: tudo abaixo roda **na conta temporária do AWS Workshop Studio**
> (899110172465, us-east-1). Quando o evento terminar, os recursos da conta deixam de existir; o
> código deste repositório reproduz tudo em outra conta (ver [docs/02-reproduzir-e-operar.md](docs/02-reproduzir-e-operar.md)).

## O que foi entregue

| Entrega | Situação | Evidência |
|---|---|---|
| Deduplicação do acervo `C:\Hackathon_ONS` | Feita | `dados/` era cópia integral de `data/`: 3.898 arquivos (3,7 GB) duplicados por SHA-256 |
| Camada curada (33 tabelas, ~300 M linhas, Parquet ZSTD particionado por ano) | Feita | 8,9 GB → 2,1 GB; contagem por tabela idêntica à origem |
| Publicação no S3 + dicionário de dados | Feita | `s3://ons-datalake-899110172465`; contagens conferidas lendo do S3 (33/33) |
| Coletor Cavuca de 15 fontes do setor, respeitando robots.txt | Feito (12 fontes ativas) | 392 documentos coletados; 384 versões atuais indexadas em 2.433 trechos |
| Busca semântica em documentos (RAG) | Feita | Cohere Embed Multilingual v3 + busca híbrida em memória |
| FlexIA v2 (Strands + AgentCore) com roteamento NVIDIA Nemotron | Feita e testada localmente | 10/10 na avaliação de exatidão, 17,6 s em média |
| Chat web (Streamlit) com streaming | Feito (roda local) | `streamlit run flexia/chat_app.py` |
| Avaliação da previsão D+1 de corte ENE (modelo da equipe) | Feita | MAE 1.310 MWmed; 16,7 % melhor que a climatologia |
| Implantação da FlexIA no AgentCore | **Pendente** — o usuário cola 2 scripts no Code Editor e roda `agentcore deploy` | [flexia/instalar_flexia_v2.sh](flexia/instalar_flexia_v2.sh) |
| Coleta agendada (cron) | **Pendente** — mesmo motivo | [flexia/instalar_coletor_agendado.sh](flexia/instalar_coletor_agendado.sh) |
| Link público para terceiros | **Não entregue** — a conta bloqueia CloudFront, API Gateway e Lambda com role própria | ver [docs/01-arquitetura-e-decisoes.md](docs/01-arquitetura-e-decisoes.md#8-acesso-externo) |

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/01-arquitetura-e-decisoes.md](docs/01-arquitetura-e-decisoes.md) | Arquitetura, cada escolha feita, alternativas descartadas e por quê |
| [docs/02-reproduzir-e-operar.md](docs/02-reproduzir-e-operar.md) | Passo a passo do zero: ambiente, curadoria, publicação, coleta, índice, FlexIA, chat, deploy, cron, renovação de credenciais, problemas comuns |
| [docs/03-dados-e-fontes.md](docs/03-dados-e-fontes.md) | Tabelas do lake, layout do bucket, regras de negócio, fontes coletadas e situação de cada uma |
| [docs/04-avaliacao.md](docs/04-avaliacao.md) | Precisão da previsão D+1 com dados históricos e exatidão das respostas da FlexIA, com o histórico de falhas e correções |

## Estrutura do repositório

```
pipeline/          curadoria e publicação do lake
  01_inventario.py     inventário + deduplicação por SHA-256 (somente leitura na origem)
  02_perfil_esquemas.py variação de esquema por arquivo em cada conjunto ONS
  03_curar.py          camada curada (curated/ e analytics/) em out/lake
  04_publicar.py       S3 + catalogo.json + validação de contagens lendo do S3
  05_gerar_flexia.py   gera as regras de negócio do prompt a partir do catálogo
  catalogo.py          dicionário de dados (tabelas, colunas, unidades) e regras — fonte única
coleta/            coleta de documentos com o Cavuca
  fontes.py            catálogo das 15 fontes (URLs, regras de link, seletores, frequência)
  coletor.py           coleta, limpeza, deduplicação por hash, extração de PDF
  indexar.py           trechos + embeddings (Cohere) -> docs/index/
  sondar_fontes.py     diagnóstico de fonte (HTTP, robots.txt, tamanho)
  lambda_handler.py    handler para Lambda (não implantável nesta conta; mantido para outra conta)
flexia/            a assistente
  app/SINAgent/        código que vai para o runtime AgentCore (main.py, domain/, tools/)
  chat_app.py          chat Streamlit (modo local ou AgentCore)
  testar_local.py      teste de linha de comando com streaming
  instalar_flexia_v2.sh, instalar_coletor_agendado.sh   scripts para o Code Editor
avaliacao/         avaliar_previsao.py e avaliar_flexia.py
infra/             empacotamento e implantação da Lambda (para contas que permitem PassRole)
workshop/          script da FlexIA v1 (primeira versão, sem dados)
out/               artefatos gerados (ignorado pelo git)
```

## Início rápido (máquina local com o perfil AWS `hackathon`)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:AWS_PROFILE = "hackathon"
.venv\Scripts\python flexia\testar_local.py "Qual foi o CMO médio de cada subsistema em 2025?"
.venv\Scripts\streamlit run flexia\chat_app.py      # abre o chat em http://localhost:8501
```
