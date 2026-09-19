"""Confere se o ambiente está pronto e completa o .env com o que dá para descobrir sozinho.

Checagens: credenciais (STS), bucket do lake e catálogo, modelos do Bedrock (Nemotron e Claude,
uma chamada mínima cada), instância do Code Editor no Systems Manager e runtime da FlexIA no
AgentCore. Campos vazios do .env que forem descobertos (FLEXIA_BUCKET, CODE_EDITOR_INSTANCIA,
FLEXIA_RUNTIME_ARN) são gravados nele. Não altera nada na AWS.

Uso: python infra/verificar.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

sys.path.insert(0, str(config.RAIZ / "flexia" / "app" / "SINAgent"))
from domain.roteador import MODELOS, ROTEADOR  # noqa: E402

REGIAO_AGENTCORE = os.environ.get("FLEXIA_REGIAO_AGENTCORE", "us-west-2")  # região do CDK no Code Editor
falhas = 0


def resultado(ok: bool, rotulo: str, detalhe: str = "") -> bool:
    global falhas
    falhas += not ok
    print(f"  {'OK   ' if ok else 'FALHA'} {rotulo}{'  ' + detalhe if detalhe else ''}")
    return ok


def gravar_env(chave: str, valor: str) -> None:
    """Preenche a chave no .env só se ela estiver vazia (nunca sobrescreve o que o usuário pôs)."""
    texto = config.ARQUIVO_ENV.read_text(encoding="utf-8") if config.ARQUIVO_ENV.exists() else ""
    if re.search(rf"^{chave}=\S", texto, re.M):
        return
    if re.search(rf"^{chave}=\s*$", texto, re.M):
        texto = re.sub(rf"^{chave}=\s*$", f"{chave}={valor}", texto, count=1, flags=re.M)
    else:
        texto += f"\n{chave}={valor}\n"
    config.ARQUIVO_ENV.write_text(texto, encoding="utf-8")
    print(f"        .env: {chave}={valor}")


def main() -> None:
    origem = "chaves do .env/ambiente" if os.environ.get("AWS_ACCESS_KEY_ID") else f"perfil {os.environ['AWS_PROFILE']}"
    print(f"credenciais: {origem}   região: {config.REGIAO}")
    sessao = config.sessao()
    try:
        ident = sessao.client("sts").get_caller_identity()
    except Exception as e:  # noqa: BLE001
        resultado(False, "credenciais AWS", str(e)[:160])
        print("\nAtualize as chaves (painel do evento > Get AWS CLI credentials) e rode .\\configurar.ps1 -SalvarCredenciais")
        sys.exit(1)
    resultado(True, "credenciais AWS", ident["Arn"])

    bucket = config.bucket()
    s3 = sessao.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
        resultado(True, "bucket do lake", f"s3://{bucket}")
        gravar_env("FLEXIA_BUCKET", bucket)
        try:
            tam = s3.head_object(Bucket=bucket, Key="catalogo/catalogo.json")["ContentLength"]
            resultado(True, "catálogo", f"{tam/1e3:.0f} kB")
        except Exception:  # noqa: BLE001
            resultado(False, "catálogo", "ausente: rode python pipeline/04_publicar.py")
    except Exception as e:  # noqa: BLE001
        resultado(False, "bucket do lake", f"{bucket}: {str(e)[:100]} (python pipeline/04_publicar.py cria)")

    bedrock = sessao.client("bedrock-runtime")
    for modelo in dict.fromkeys([ROTEADOR, *MODELOS.values()]):
        try:
            bedrock.converse(modelId=modelo, messages=[{"role": "user", "content": [{"text": "ok"}]}],
                             inferenceConfig={"maxTokens": 5})
            resultado(True, "Bedrock", modelo)
        except Exception as e:  # noqa: BLE001
            resultado(False, "Bedrock", f"{modelo}: {str(e)[:120]}")

    try:
        sys.path.insert(0, str(config.RAIZ / "infra"))
        from code_editor import instancia_code_editor  # noqa: PLC0415
        instancia = instancia_code_editor(sessao.client("ssm", region_name="us-east-1"))
        resultado(True, "Code Editor (SSM)", instancia)
        gravar_env("CODE_EDITOR_INSTANCIA", instancia)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        resultado(False, "Code Editor (SSM)", str(e)[:140])

    try:
        ctl = sessao.client("bedrock-agentcore-control", region_name=REGIAO_AGENTCORE)
        runtimes = ctl.list_agent_runtimes()["agentRuntimes"]
        flexia = [r for r in runtimes if "SINAgent" in r["agentRuntimeName"] or "flexia" in r["agentRuntimeName"].lower()]
        if flexia:
            r = max(flexia, key=lambda r: r["lastUpdatedAt"])
            resultado(True, "runtime AgentCore", f"{r['agentRuntimeName']} ({r['status']})")
            gravar_env("FLEXIA_RUNTIME_ARN", r["agentRuntimeArn"])
        else:
            print(f"  --    runtime AgentCore  nenhum em {REGIAO_AGENTCORE} ainda (.\\configurar.ps1 -Implantar)")
    except Exception as e:  # noqa: BLE001
        print(f"  --    runtime AgentCore  não verificado ({str(e)[:100]})")

    print(f"\n{'Tudo certo.' if not falhas else f'{falhas} falha(s).'}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
