# Reproduzir e operar

Passo a passo para reconstruir tudo do zero (inclusive em outra conta AWS) e para operar o sistema
no dia a dia. Comandos em PowerShell na máquina local, salvo quando indicado "Code Editor" (bash).

## 0. Pré-requisitos

| Item | Detalhe |
|---|---|
| Windows 10+ com Python 3.12+ | testado com Python 3.14 |
| Git | o projeto é um repositório git; commite antes de qualquer mudança |
| Acervo da equipe | `C:\Hackathon_ONS` (só é lido; mude com a variável `ORIGEM`) |
| Conta AWS em `us-east-1` | com acesso ao Bedrock (Claude Haiku 4.5, Claude Sonnet 4.6, NVIDIA Nemotron Nano 3 30B, Cohere Embed Multilingual v3) |
| Perfil AWS local | nome padrão `hackathon` (mude com `AWS_PROFILE`) |
| Espaço em disco | ~15 GB livres (origem 9 GB + lake 2 GB + temporários) |
| Memória | 16 GB+ (a curadoria usa até 16 GB no DuckDB) |

## 1. Ambiente local

```powershell
cd C:\Desenvolvimento\AWS
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
```

## 2. Credenciais AWS (conta do workshop)

As credenciais do Workshop Studio são **temporárias** (expiram em poucas horas). O próprio usuário
deve gravá-las; nenhum script deste projeto grava ou imprime credenciais.

1. No painel do evento, clique em **Get AWS CLI credentials** e copie o bloco PowerShell (`$Env:AWS_...`).
2. Cole no PowerShell e, **no mesmo terminal**, grave o perfil:
   ```powershell
   New-Item -ItemType Directory -Force "$HOME\.aws" | Out-Null; "[hackathon]`naws_access_key_id = $Env:AWS_ACCESS_KEY_ID`naws_secret_access_key = $Env:AWS_SECRET_ACCESS_KEY`naws_session_token = $Env:AWS_SESSION_TOKEN`nregion = us-east-1`n" | Set-Content -Encoding ascii "$HOME\.aws\credentials"
   ```
3. Teste (deve imprimir um ARN `...:assumed-role/WSParticipantRole/Participant`):
   ```powershell
   .venv\Scripts\python -c "import boto3;print(boto3.Session(profile_name='hackathon').client('sts').get_caller_identity()['Arn'])"
   ```
   `InvalidClientTokenId` = o arquivo foi gravado antes das variáveis ou com credenciais vencidas.
   Se o painel devolver sempre as mesmas chaves vencidas, gere-as no terminal do Code Editor com
   `aws configure export-credentials --format powershell`.

Em outra conta, use qualquer perfil com permissão de S3 e Bedrock.

## 3. Data lake

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python pipeline\01_inventario.py        # ~5 min: SHA-256 de 7.770 arquivos -> out\inventario.csv
.venv\Scripts\python pipeline\02_perfil_esquemas.py   # variações de esquema -> out\esquemas.json
.venv\Scripts\python pipeline\03_curar.py             # ~10 min: out\lake\curated e out\lake\analytics
```

- Para refazer só algumas tabelas: `pipeline\03_curar.py ons_curva_carga clima_era5_horario`.
- Saída esperada: 33 linhas `curated/...` e `analytics/...` com as contagens de
  [03-dados-e-fontes.md](03-dados-e-fontes.md).

### Publicar no S3

```powershell
$env:AWS_PROFILE = "hackathon"
.venv\Scripts\python pipeline\04_publicar.py            # bucket + upload + catalogo.json + validação
.venv\Scripts\python pipeline\04_publicar.py --sem-raw  # pula os brutos (2,5 GB)
.venv\Scripts\python pipeline\04_publicar.py --validar  # só confere as contagens lendo do S3
```

- Bucket: `ons-datalake-<conta>` (ou `BUCKET=...`), privado (Block Public Access), criptografado
  (SSE-S3) e versionado. O upload é incremental (pula arquivos já enviados com o mesmo tamanho).
- A validação deve terminar com `validação: tudo confere` (33 tabelas).
- `--permitir-runtimes` anexa às roles dos runtimes AgentCore a política **somente leitura** do
  lake. Use só depois do deploy da FlexIA e com decisão explícita.
- Depois de mudar `pipeline/catalogo.py`, rode `pipeline\05_gerar_flexia.py` para atualizar as
  regras do prompt, e `04_publicar.py --sem-raw` para atualizar o `catalogo.json` e o código no S3.

## 4. Coleta de documentos

### Teste local (sem S3)
```powershell
.venv\Scripts\python coleta\sondar_fontes.py                      # HTTP, robots.txt e tamanho por fonte
.venv\Scripts\python coleta\coletor.py --local out\docs_teste --max 8 --fonte aneel_noticias --fonte planalto_leis_setor
.venv\Scripts\python coleta\indexar.py --local out\docs_teste --fonte aneel_noticias --fonte planalto_leis_setor
```

### Coleta completa para o S3
```powershell
$env:AWS_PROFILE = "hackathon"; $env:FLEXIA_BUCKET = "ons-datalake-899110172465"
foreach ($f in 'diaria','semanal','mensal') { .venv\Scripts\python coleta\coletor.py --frequencia $f }
.venv\Scripts\python coleta\indexar.py
```
A primeira coleta completa leva ~45 min (os portais CKAN exigem 10 s entre páginas). Coletas
seguintes gravam só o que mudou; o indexador pula fontes sem mudança.

### Agendamento (Code Editor, bash)
Cole o conteúdo de [flexia/instalar_coletor_agendado.sh](../flexia/instalar_coletor_agendado.sh) no
terminal do Code Editor. Ele baixa o coletor do S3 (`deploy/coletor/`), cria um venv com o Cavuca,
testa a permissão da instância no bucket, instala o cron (horário de Brasília) e roda a coleta
diária uma vez:

| quando | o que |
|---|---|
| todo dia 06:00 | notícias ANEEL, MME, CCEE, EPE |
| segunda 07:00 | leis (Planalto), procedimentos ANEEL/CCEE, catálogos de dados abertos |
| dia 1 08:00 | publicações EPE, páginas institucionais ONS |

Logs: `~/flexia-coletor/logs/<frequencia>-AAAAMMDD.log`. Rodar à mão: `~/flexia-coletor/rodar.sh diaria`.

### Incluir uma fonte nova
1. Adicione um item em `coleta/fontes.py` (id, órgão, tipo, `urls`, `permitir`, `css`, frequência).
2. Verifique o robots.txt e o conteúdo: `coleta\sondar_fontes.py <id>`.
3. Ache o seletor do conteúdo principal (sem ele a página vem com menus).
4. Teste local com `--local`, confira os `.md` gerados, depois publique o código
   (`04_publicar.py --sem-raw`) e reinstale o coletor no Code Editor.

## 5. FlexIA

### Teste local
```powershell
$env:AWS_PROFILE = "hackathon"; $env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python flexia\testar_local.py "Oi, qual seu nome?" "Qual foi o CMO médio de cada subsistema em 2025?" "E em 2024, subiu ou caiu no Sudeste?"
```
Todas as perguntas de uma execução usam a mesma sessão (testa o contexto da conversa).

### Chat
```powershell
$env:AWS_PROFILE = "hackathon"
.venv\Scripts\streamlit run flexia\chat_app.py      # http://localhost:8501
```
Modo `agentcore` (depois do deploy): `$env:FLEXIA_MODO = "agentcore"; $env:FLEXIA_RUNTIME_ARN = "<arn do runtime>"`.

### Instalar e implantar no AgentCore (Code Editor, bash)
1. (Uma vez) cole [workshop/flexia_agent_v1.sh](../workshop/flexia_agent_v1.sh) se o projeto ainda
   estiver com o agente original do workshop.
2. Cole [flexia/instalar_flexia_v2.sh](../flexia/instalar_flexia_v2.sh): commita o estado atual,
   baixa o código do S3 (`flexia/app/SINAgent/`), inclui `boto3`, `duckdb` e `numpy` no
   `requirements.txt`, valida e faz um teste com `agentcore dev`.
3. `agentcore deploy`.
4. Na máquina local: `pipeline\04_publicar.py --sem-raw --permitir-runtimes` para dar ao runtime a
   leitura do lake (confira as roles listadas antes de confirmar).

### Variáveis de ambiente da FlexIA
| variável | padrão | uso |
|---|---|---|
| `FLEXIA_BUCKET` | `ons-datalake-<conta>` | bucket do lake |
| `FLEXIA_MODELO_ROTEADOR` | `nvidia.nemotron-nano-3-30b` | classificador |
| `FLEXIA_MODELO_RAPIDO` | `nvidia.nemotron-nano-3-30b` | conversa |
| `FLEXIA_MODELO_DADOS` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | dados simples, fora de escopo |
| `FLEXIA_MODELO_DOCUMENTOS` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | documentos |
| `FLEXIA_MODELO_RACIOCINIO` | `us.anthropic.claude-sonnet-4-6` | complexas, mistas e recuperação de falhas |

## 6. Avaliação
```powershell
.venv\Scripts\python avaliacao\avaliar_previsao.py                  # métricas da previsão D+1 -> avaliacao\resultados\previsao.{json,md}
.venv\Scripts\python avaliacao\avaliar_flexia.py --repeticoes 2     # roteador + 13 perguntas x 2 -> avaliacao\resultados\flexia.{json,md}
.venv\Scripts\python avaliacao\avaliar_flexia.py --so-roteador      # só o roteador (~30 s)
```
Rode `avaliar_flexia.py` depois de qualquer mudança no prompt, nas regras, no roteador ou na busca.

## 7. Problemas comuns

| sintoma | causa | solução |
|---|---|---|
| `InvalidClientTokenId` / `ExpiredToken` | credenciais do workshop vencidas | regravar o perfil (seção 2) |
| `AccessDeniedException ... glue/athena` | conta do workshop bloqueia | não use Glue/Athena; o lake é lido pelo DuckDB |
| primeira consulta demora ~40 s | instalação das extensões DuckDB | normal na 1ª execução; no agente o aquecimento roda na inicialização |
| `Permission Error ... file system operations are disabled` | isolamento do DuckDB | esperado para qualquer caminho fora do bucket |
| coletor salva páginas enormes com menu | falta `css` na fonte | definir o seletor do conteúdo principal |
| fonte sempre com 0 documentos | página montada por JavaScript ou regra `permitir` errada | ver links reais com `coleta\sondar_fontes.py`; páginas JS exigem coletor com navegador |
| chat mostra "None" repetido | expressão solta no código (magic do Streamlit) | não deixe expressões soltas em `chat_app.py` |
| `iam:PassRole` negado | conta do workshop | usar cron no Code Editor (seção 4) |

## 8. Custos (ordem de grandeza)
- S3: ~5 GB armazenados → centavos de dólar por mês.
- Bedrock: cada pergunta chama o Nemotron (classificação, ~100 tokens) + Claude Haiku ou Sonnet
  com 1–7 chamadas de ferramenta; embeddings Cohere na indexação (~2.400 trechos) e por pergunta de
  documentos. Na conta do workshop há um rastreador de custo do evento (`BedrockCostTracker`).
- Coleta: sem custo de computação extra (roda na EC2 do Code Editor, que já existe).
