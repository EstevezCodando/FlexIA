<#
.SYNOPSIS
  Configuração inicial da FlexIA: ambiente Python, arquivo .env e verificação da conta AWS.
  As etapas opcionais publicam o lake, coletam documentos, implantam o agente e agendam a coleta.

.EXAMPLE
  .\configurar.ps1                       # venv + dependências + .env + verificação
  .\configurar.ps1 -SalvarCredenciais    # grava no .env as chaves AWS_* coladas neste terminal
  .\configurar.ps1 -Tudo                 # tudo acima + publicar, coletar, implantar e agendar
  .\configurar.ps1 -Chat                 # abre a interface de chat

  Chaves do Workshop Studio: painel do evento > "Get AWS CLI credentials" > bloco PowerShell.
  Cole o bloco ($Env:AWS_ACCESS_KEY_ID=... etc.) neste terminal e rode com -SalvarCredenciais.
  Elas expiram em poucas horas: ao ver ExpiredToken, repita só esse passo.
#>
param(
    [switch]$SalvarCredenciais,  # copia $Env:AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN para o .env
    [switch]$Publicar,           # envia lake + catálogo + código da FlexIA para o S3
    [switch]$Coletar,            # coleta as fontes regulatórias e reindexa os documentos
    [switch]$Implantar,          # implanta a FlexIA no AgentCore (via Code Editor/SSM) e dá à role do
                                 # runtime leitura do lake (política IAM FlexIALeituraDataLake, só leitura)
    [switch]$Agendar,            # instala a coleta agendada (cron no Code Editor)
    [switch]$Tudo,               # Publicar + Coletar + Implantar + Agendar
    [switch]$Chat,               # abre o chat (Streamlit) ao final
    [switch]$SemInstalar         # pula venv/pip (ambiente já pronto)
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
if ($Tudo) { $Publicar = $Coletar = $Implantar = $Agendar = $true }
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Etapa($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Rodar {
    & $py @args
    if ($LASTEXITCODE -ne 0) { throw "falhou: python $($args -join ' ')" }
}

# 1. Python e dependências ------------------------------------------------------------
if (-not $SemInstalar) {
    Etapa "1. ambiente Python (.venv)"
    if (-not (Test-Path $py)) {
        $base = (Get-Command py -ErrorAction SilentlyContinue)
        if ($base) { & py -3 -m venv .venv } else { & python -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw "não foi possível criar a .venv (instale Python 3.12+ e o Git)" }
    }
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install falhou" }
    & $py --version
}

# 2. Arquivo .env ---------------------------------------------------------------------
Etapa "2. arquivo .env"
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "criado .env a partir de .env.example"
}
if ($SalvarCredenciais) {
    $chaves = "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"
    $faltando = $chaves | Where-Object { -not (Test-Path "Env:$_") }
    if ($faltando) { throw "cole antes o bloco `$Env:AWS_... do painel do evento; faltando: $($faltando -join ', ')" }
    $linhas = [System.Collections.Generic.List[string]](Get-Content .env -Encoding UTF8)
    foreach ($c in $chaves) {
        $valor = (Get-Item "Env:$c").Value
        $i = $linhas.FindIndex([Predicate[string]]{ param($l) $l -match "^$c=" })
        if ($i -ge 0) { $linhas[$i] = "$c=$valor" } else { $linhas.Add("$c=$valor") }
    }
    [System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), $linhas, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "chaves AWS gravadas no .env (fora do git)"
}

# 3. Verificação ----------------------------------------------------------------------
Etapa "3. verificação da conta (credenciais, bucket, modelos, Code Editor, runtime)"
& $py infra\verificar.py
$verificado = ($LASTEXITCODE -eq 0)

# 4. Etapas opcionais -----------------------------------------------------------------
if ($Publicar) {
    Etapa "4a. publicar lake, catálogo e código no S3"
    Rodar pipeline\05_gerar_flexia.py
    Rodar pipeline\04_publicar.py --sem-raw
}
if ($Coletar) {
    Etapa "4b. coletar fontes regulatórias e indexar documentos"
    $fontes = "ons_procedimentos_rede", "cnpe_resolucoes", "aneel_agenda_regulatoria", "aneel_decisoes_diretoria", "midia_manchetes"
    $args_fontes = $fontes | ForEach-Object { "--fonte"; $_ }
    Rodar coleta\coletor.py @args_fontes
    Rodar coleta\indexar.py @args_fontes
}
if ($Implantar) {
    Etapa "4c. implantar a FlexIA no AgentCore (Code Editor via SSM)"
    Rodar infra\code_editor.py --arquivo flexia\implantar_flexia.sh
    Rodar pipeline\04_publicar.py --validar --permitir-runtimes  # IAM: leitura do lake para as roles do runtime
    & $py infra\verificar.py  # grava FLEXIA_RUNTIME_ARN no .env
}
if ($Agendar) {
    Etapa "4d. agendar coleta diária/semanal/mensal (cron no Code Editor)"
    Rodar infra\code_editor.py --arquivo flexia\instalar_coletor_agendado.sh
}

Etapa "pronto"
if (-not $verificado) { Write-Host "Há falhas na verificação acima; corrija o .env e rode de novo." -ForegroundColor Yellow }
Write-Host "Chat:        .\configurar.ps1 -SemInstalar -Chat   (ou: .venv\Scripts\streamlit run flexia\web\app.py)"
Write-Host "Modo do chat: FLEXIA_MODO=local (padrão) ou agentcore no .env"
if ($Chat) { & (Join-Path $PSScriptRoot ".venv\Scripts\streamlit.exe") run flexia\web\app.py }
