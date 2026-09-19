"""Executa comandos na máquina do Code Editor do workshop via AWS Systems Manager (Run Command).

Substitui colar scripts no terminal do Code Editor: o comando roda como o usuário 'participant',
no diretório do projeto, com a role da própria instância (a que tem permissão de implantar no
AgentCore). Saída e código de retorno voltam para cá.

Uso:
  python infra/code_editor.py "comando bash"            # executa e espera
  python infra/code_editor.py --arquivo script.sh        # executa um script local
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

USUARIO = "participant"


def instancia_code_editor(ssm) -> str:
    """CODE_EDITOR_INSTANCIA do .env ou, se vazio, a única instância Linux online no Systems Manager."""
    if os.environ.get("CODE_EDITOR_INSTANCIA"):
        return os.environ["CODE_EDITOR_INSTANCIA"]
    ids = [i["InstanceId"] for i in ssm.describe_instance_information()["InstanceInformationList"]
           if i.get("PlatformType") == "Linux" and i.get("PingStatus") == "Online"]
    if len(ids) != 1:
        raise SystemExit(f"defina CODE_EDITOR_INSTANCIA no .env (instâncias online: {ids})")
    os.environ["CODE_EDITOR_INSTANCIA"] = ids[0]
    return ids[0]


def executar(script: str, timeout_s: int = 3600) -> tuple[int, str, str]:
    ssm = config.sessao("us-east-1").client("ssm")
    instancia = instancia_code_editor(ssm)
    # roda como o usuário do Code Editor, com login shell; ~/.local/bin (uv) só entra no PATH pelo .bashrc,
    # que um shell não interativo não lê
    comando = (f"sudo -u {USUARIO} -i bash <<'__FLEXIA__'\nset -o pipefail\n"
               f'export PATH="$HOME/.local/bin:$PATH"\n{script}\n__FLEXIA__')
    cid = ssm.send_command(InstanceIds=[instancia], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": [comando], "executionTimeout": [str(timeout_s)]},
                           TimeoutSeconds=600)["Command"]["CommandId"]
    while True:
        time.sleep(3)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=instancia)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            return r["ResponseCode"], r["StandardOutputContent"], r["StandardErrorContent"]


if __name__ == "__main__":
    if sys.argv[1] == "--arquivo":
        script = open(sys.argv[2], encoding="utf-8").read()
    else:
        script = sys.argv[1]
    codigo, saida, erro = executar(script)
    print(saida)
    if erro.strip():
        print("--- stderr ---\n" + erro[-4000:])
    print(f"--- código de retorno: {codigo}")
    sys.exit(0 if codigo == 0 else 1)
