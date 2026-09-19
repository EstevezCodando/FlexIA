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

import boto3

INSTANCIA = os.environ.get("CODE_EDITOR_INSTANCIA", "i-06fea3e9706a6044b")
USUARIO = "participant"


def executar(script: str, timeout_s: int = 3600) -> tuple[int, str, str]:
    ssm = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "hackathon"), region_name="us-east-1").client("ssm")
    # roda como o usuário do Code Editor, com login shell (PATH do agentcore, uv, node etc.)
    comando = f"sudo -u {USUARIO} -i bash <<'__FLEXIA__'\nset -o pipefail\n{script}\n__FLEXIA__"
    cid = ssm.send_command(InstanceIds=[INSTANCIA], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": [comando], "executionTimeout": [str(timeout_s)]},
                           TimeoutSeconds=600)["Command"]["CommandId"]
    while True:
        time.sleep(3)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=INSTANCIA)
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
    sys.stdout.reconfigure(encoding="utf-8")
    print(saida)
    if erro.strip():
        print("--- stderr ---\n" + erro[-4000:])
    print(f"--- código de retorno: {codigo}")
    sys.exit(0 if codigo == 0 else 1)
