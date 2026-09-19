# Reproduzir e operar

Passo a passo para reconstruir tudo do zero (inclusive em outra conta AWS) e para operar o sistema
no dia a dia. Comandos em PowerShell na máquina local, salvo quando indicado "Code Editor" (bash).

## 0. Pré-requisitos

| Item | Detalhe |
|---|---|
| Windows 10+ com Python 3.12+ | testado com Python 3.14 |
| Git | o projeto é um repositório git; commite antes de qualquer mudança |
| Acervo da equipe | `C:\Hackathon_ONS` (só é lido; mude `ORIGEM` no `.env`) |
| Conta AWS em `us-east-1` | com acesso ao Bedrock (Claude Haiku 4.5, Claude Sonnet 4.6, NVIDIA Nemotron Nano 3 30B, Cohere Embed Multilingual v3) |
| Espaço em disco | ~15 GB livres (origem 9 GB + lake 3 GB + temporários) |
| Memória | 16 GB+ (a curadoria usa até 16 GB no DuckDB) |

## 1. Configuração inicial (um comando)

Toda a configuração fica num único arquivo, **`.env`** na raiz (fora do git). O modelo comentado
de todas as variáveis está em [`.env.example`](../.env.example); o [`config.py`](../config.py) carrega
o `.env` em todos os scripts (prioridade: variável do terminal > `.env` > padrão).

```powershell
git clone <repositório> C:\Desenvolvimento\AWS; cd C:\Desenvolvimento\AWS
Set-ExecutionPolicy -Scope Process Bypass        # só nesta janela, para rodar o .ps1
.\configurar.ps1
```

O [`configurar.ps1`](../configurar.ps1) faz, nesta ordem:

| etapa | o que faz |
|---|---|
| 1 | cria `.venv` e instala `requirements.txt` (inclui o Cavuca do GitHub) |
| 2 | cria `.env` a partir de `.env.example`, se não existir |
| 3 | roda [`infra/verificar.py`](../infra/verificar.py): credenciais (STS), bucket e catálogo, uma chamada mínima a cada modelo do Bedrock, instância do Code Editor (SSM) e runtime AgentCore. Preenche no `.env` o que descobrir e estiver vazio (`FLEXIA_BUCKET`, `CODE_EDITOR_INSTANCIA`, `FLEXIA_RUNTIME_ARN`). Não altera nada na AWS |

Opções (combináveis):

| opção | o que faz |
|---|---|
| `-SalvarCredenciais` | grava no `.env` as chaves `$Env:AWS_*` coladas no terminal |
| `-Publicar` | `05_gerar_flexia.py` + `04_publicar.py --sem-raw` (lake, catálogo, código da FlexIA e do coletor no S3) |
| `-Coletar` | coleta as fontes regulatórias do Desafio 1 e reindexa os documentos |
| `-Implantar` | implanta a FlexIA no AgentCore pelo Code Editor (SSM), dá à role do runtime **leitura** do lake e grava o ARN no `.env` |
| `-Agendar` | instala a coleta agendada (cron) no Code Editor |
| `-Tudo` | `-Publicar -Coletar -Implantar -Agendar` |
| `-Chat` | abre o chat no final (`http://localhost:8501`) |
| `-SemInstalar` | pula venv/pip |

Sequência completa numa conta nova: `.\configurar.ps1 -SalvarCredenciais -Tudo -Chat`
(o lake local em `out\lake` precisa existir: seção 3).

## 2. Credenciais AWS

**Conta do workshop (chaves temporárias, expiram em poucas horas):**

1. No painel do evento, clique em **Get AWS CLI credentials** e copie o bloco PowerShell (`$Env:AWS_...`).
2. Cole no PowerShell e, **no mesmo terminal**, rode:
   ```powershell
   .\configurar.ps1 -SemInstalar -SalvarCredenciais
   ```
   As três chaves vão para o `.env`, e a verificação deve mostrar
   `OK credenciais AWS arn:aws:sts::<conta>:assumed-role/WSParticipantRole/Participant`.
3. Ao ver `ExpiredToken`, repita os passos 1 e 2. Se o painel devolver sempre chaves vencidas,
   gere-as no terminal do Code Editor com `aws configure export-credentials --format powershell`.

**Outra conta:** deixe as chaves vazias e ponha em `AWS_PROFILE` o nome de um perfil do
`~/.aws/credentials` com permissão de S3 e Bedrock (sem chaves nem perfil, o padrão é `hackathon`).

Nenhum script imprime credenciais, e o `.env` está no `.gitignore`. Antes de publicar o repositório,
confira com `git status` que o `.env` não aparece.

## 3. Data lake

```powershell
.venv\Scripts\python pipeline\01_inventario.py        # ~5 min: SHA-256 de 7.770 arquivos -> out\inventario.csv
.venv\Scripts\python pipeline\02_perfil_esquemas.py   # variações de esquema -> out\esquemas.json
.venv\Scripts\python pipeline\03_curar.py             # ~10 min: out\lake\curated e out\lake\analytics
```

- Para refazer só algumas tabelas: `pipeline\03_curar.py ons_curva_carga clima_era5_horario`.
- Saída esperada: 33 linhas `curated/...` e `analytics/...` com as contagens de
  [03-dados-e-fontes.md](03-dados-e-fontes.md).

### Publicar no S3

```powershell
.venv\Scripts\python pipeline\04_publicar.py            # bucket + upload + catalogo.json + validação
.venv\Scripts\python pipeline\04_publicar.py --sem-raw  # pula os brutos (2,5 GB)
.venv\Scripts\python pipeline\04_publicar.py --validar  # só confere as contagens lendo do S3
```

- Bucket: `ons-datalake-<conta>` (ou `FLEXIA_BUCKET` no `.env`), privado (Block Public Access), criptografado
  (SSE-S3) e versionado. O upload é incremental (pula arquivos já enviados com o mesmo tamanho).
- A validação deve terminar com `validação: tudo confere` (116 tabelas).
- `--permitir-runtimes` anexa às roles dos runtimes AgentCore a política **somente leitura** do
  lake. Use só depois do deploy da FlexIA e com decisão explícita. `--validar --permitir-runtimes`
  aplica só a permissão e confere, sem reenviar nada.
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
foreach ($f in 'diaria','semanal','mensal') { .venv\Scripts\python coleta\coletor.py --frequencia $f }
.venv\Scripts\python coleta\indexar.py
```
A primeira coleta completa leva ~45 min (os portais CKAN exigem 10 s entre páginas). Coletas
seguintes gravam só o que mudou; o indexador pula fontes sem mudança.

### Agendamento (Code Editor)
`.\configurar.ps1 -SemInstalar -Agendar` executa [flexia/instalar_coletor_agendado.sh](../flexia/instalar_coletor_agendado.sh)
no Code Editor via SSM (ou cole o script no terminal do Code Editor). Ele baixa o coletor do S3 (`deploy/coletor/`), cria um venv com o Cavuca,
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
.venv\Scripts\python flexia\testar_local.py "Oi, qual seu nome?" "Qual foi o CMO médio de cada subsistema em 2025?" "E em 2024, subiu ou caiu no Sudeste?"
```
Todas as perguntas de uma execução usam a mesma sessão (testa o contexto da conversa).

### Chat
```powershell
.venv\Scripts\streamlit run flexia\web\app.py      # http://localhost:8501
```
Ao mudar o CSS ou o símbolo (`flexia/web/tema.py`, `marca.py`), reinicie o Streamlit: módulos importados não recarregam sozinhos.
Modo `agentcore` (depois do deploy): `FLEXIA_MODO=agentcore` no `.env` (o `FLEXIA_RUNTIME_ARN` é preenchido pelo `configurar.ps1 -Implantar`).

### Implantar no AgentCore

Da máquina local, sem abrir o Code Editor: `.\configurar.ps1 -SemInstalar -Publicar -Implantar`.
Por baixo, [`infra/code_editor.py`](../infra/code_editor.py) envia
[`flexia/implantar_flexia.sh`](../flexia/implantar_flexia.sh) para a instância do Code Editor via
Systems Manager (Run Command, como o usuário `participant`, com a role da instância). O script:

1. commita o estado atual do projeto `~/build-with-skills/SINIntelligence`;
2. baixa o código da FlexIA do S3 (`flexia/app/SINAgent/`);
3. inclui `duckdb`, `numpy` e `boto3` nas dependências do `pyproject.toml` (o projeto usa `uv`);
4. compila os `.py` e roda `agentcore validate`;
5. preenche `agentcore/aws-targets.json` com a conta e a região do CDK (`us-west-2`), se estiver vazio;
6. roda `agentcore deploy --target default --yes` e `agentcore status`, e commita o resultado.

Depois, `04_publicar.py --validar --permitir-runtimes` anexa às roles dos runtimes a política
somente leitura do lake, e `infra/verificar.py` grava o ARN do runtime no `.env`.

Outros comandos no Code Editor: `.venv\Scripts\python infra\code_editor.py "agentcore status"`.
Se o projeto ainda estiver com o agente original do workshop, rode antes
[workshop/flexia_agent_v1.sh](../workshop/flexia_agent_v1.sh) do mesmo jeito (`--arquivo`).

### Variáveis de ambiente da FlexIA (todas no `.env`)
| variável | padrão | uso |
|---|---|---|
| `FLEXIA_BUCKET` | `ons-datalake-<conta>` | bucket do lake |
| `FLEXIA_REGIAO` | `AWS_REGION` (`us-east-1`) | região do bucket e do Bedrock (o runtime roda em `us-west-2`) |
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
| `InvalidClientTokenId` / `ExpiredToken` | credenciais do workshop vencidas | `.\configurar.ps1 -SemInstalar -SalvarCredenciais` (seção 2) |
| `AccessDeniedException ... glue/athena` | conta do workshop bloqueia | não use Glue/Athena; o lake é lido pelo DuckDB |
| primeira consulta demora ~40 s | instalação das extensões DuckDB | normal na 1ª execução; no agente o aquecimento roda na inicialização |
| `Permission Error ... file system operations are disabled` | isolamento do DuckDB | esperado para qualquer caminho fora do bucket |
| coletor salva páginas enormes com menu | falta `css` na fonte | definir o seletor do conteúdo principal |
| fonte sempre com 0 documentos | página montada por JavaScript ou regra `permitir` errada | ver links reais com `coleta\sondar_fontes.py`; páginas JS exigem coletor com navegador |
| chat mostra "None" repetido | expressão solta no código (magic do Streamlit) | não deixe expressões soltas em `flexia/web/*.py` |
| `iam:PassRole` negado | conta do workshop | usar cron no Code Editor (seção 4) |

## 8. Custos (ordem de grandeza)
- S3: ~5 GB armazenados → centavos de dólar por mês.
- Bedrock: cada pergunta chama o Nemotron (classificação, ~100 tokens) + Claude Haiku ou Sonnet
  com 1–7 chamadas de ferramenta; embeddings Cohere na indexação (~2.400 trechos) e por pergunta de
  documentos. Na conta do workshop há um rastreador de custo do evento (`BedrockCostTracker`).
- Coleta: sem custo de computação extra (roda na EC2 do Code Editor, que já existe).
