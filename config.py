"""Configuração central do projeto: carrega o arquivo .env e define os padrões usados por todos os scripts.

Todo script de entrada importa este módulo antes de qualquer outra coisa. Ordem de prioridade de cada
variável: ambiente do terminal > .env > padrão abaixo. Credenciais AWS podem vir do .env
(AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN) ou de um perfil (AWS_PROFILE).
Modelo comentado de todas as variáveis: .env.example.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARQUIVO_ENV = RAIZ / ".env"


def _carregar_env(caminho: Path) -> None:
    """Lê KEY=VALOR (ignora comentários e linhas vazias); não sobrescreve o que já está no ambiente."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip().removeprefix("export ").strip(), valor.strip().strip('"').strip("'")
        if chave and valor and chave not in os.environ:
            os.environ[chave] = valor


_carregar_env(ARQUIVO_ENV)

PADROES = {
    "AWS_REGION": "us-east-1",
    "FLEXIA_REGIAO": os.environ.get("AWS_REGION", "us-east-1"),  # região do bucket e do Bedrock
    "ORIGEM": r"C:\Hackathon_ONS",                                   # acervo original da equipe
    "PYTHONIOENCODING": "utf-8",
}
for chave, valor in PADROES.items():
    os.environ.setdefault(chave, valor)
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ["AWS_REGION"])
if not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_PROFILE"):
    os.environ["AWS_PROFILE"] = "hackathon"  # compatibilidade com o perfil usado no início do projeto

for fluxo in (sys.stdout, sys.stderr):  # acentos no console do Windows
    try:
        fluxo.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

REGIAO = os.environ["FLEXIA_REGIAO"]


def sessao(regiao: str | None = None):
    """Sessão boto3: chaves do .env/ambiente têm prioridade; senão, o perfil AWS_PROFILE."""
    import boto3
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return boto3.Session(region_name=regiao or REGIAO)
    return boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name=regiao or REGIAO)


def bucket() -> str:
    """Bucket do lake: FLEXIA_BUCKET ou ons-datalake-<conta>. Também exporta FLEXIA_BUCKET."""
    if not os.environ.get("FLEXIA_BUCKET"):
        conta = sessao().client("sts").get_caller_identity()["Account"]
        os.environ["FLEXIA_BUCKET"] = f"ons-datalake-{conta}"
    return os.environ["FLEXIA_BUCKET"]
