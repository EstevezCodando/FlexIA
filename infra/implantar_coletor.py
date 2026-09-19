"""Implanta a coleta agendada da FlexIA: role IAM mínima + Lambda flexia-coletor + regras EventBridge.

Sem --aplicar, só mostra o que seria feito. Conta do workshop: EventBridge Scheduler está bloqueado,
então o agendamento usa regras cron do EventBridge (horários em UTC; Brasília = UTC-3).

  diária   06:00 BRT todos os dias           notícias ANEEL/MME/CCEE/EPE
  semanal  07:00 BRT às segundas             leis, procedimentos e catálogos de dados abertos
  mensal   08:00 BRT no dia 1                publicações EPE, páginas institucionais ONS

Uso: python infra/implantar_coletor.py [--aplicar]
"""
import json
import os
import sys
import time
from pathlib import Path

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

REGIAO = "us-east-1"
BASE = Path(__file__).resolve().parent.parent
FUNCAO = "flexia-coletor"
ROLE = "flexia-coletor-lambda"
REGRAS = {
    "flexia-coleta-diaria": ("cron(0 9 * * ? *)", "diaria"),
    "flexia-coleta-semanal": ("cron(0 10 ? * MON *)", "semanal"),
    "flexia-coleta-mensal": ("cron(0 11 1 * ? *)", "mensal"),
}

sessao = config.sessao(REGIAO)
CONTA = sessao.client("sts").get_caller_identity()["Account"]
BUCKET = f"ons-datalake-{CONTA}"
APLICAR = "--aplicar" in sys.argv
iam, lam, ev, s3 = (sessao.client(s) for s in ("iam", "lambda", "events", "s3"))
ARN_FUNCAO = f"arn:aws:lambda:{REGIAO}:{CONTA}:function:{FUNCAO}"

CONFIANCA = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
POLITICA = {"Version": "2012-10-17", "Statement": [
    {"Sid": "Logs", "Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
     "Resource": f"arn:aws:logs:{REGIAO}:{CONTA}:log-group:/aws/lambda/{FUNCAO}*"},
    {"Sid": "ListarDocs", "Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{BUCKET}",
     "Condition": {"StringLike": {"s3:prefix": ["docs/*"]}}},
    {"Sid": "LerGravarDocs", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
     "Resource": f"arn:aws:s3:::{BUCKET}/docs/*"},
    {"Sid": "Embeddings", "Effect": "Allow", "Action": "bedrock:InvokeModel",
     "Resource": f"arn:aws:bedrock:{REGIAO}::foundation-model/cohere.embed-multilingual-v3"},
    {"Sid": "FanOut", "Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": ARN_FUNCAO},
]}


def passo(msg: str) -> bool:
    print(("APLICANDO  " if APLICAR else "PLANO      ") + msg)
    return APLICAR


def garantir_role() -> str:
    try:
        arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
        if passo(f"atualizar política da role {ROLE}"):
            iam.put_role_policy(RoleName=ROLE, PolicyName="flexia-coletor", PolicyDocument=json.dumps(POLITICA))
        return arn
    except iam.exceptions.NoSuchEntityException:
        if not passo(f"criar role {ROLE} (S3 docs/* do {BUCKET}, embeddings Cohere, logs, auto-invocação)"):
            return f"arn:aws:iam::{CONTA}:role/{ROLE}"
        arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(CONFIANCA),
                              Description="Coletor agendado da FlexIA (Cavuca)")["Role"]["Arn"]
        iam.put_role_policy(RoleName=ROLE, PolicyName="flexia-coletor", PolicyDocument=json.dumps(POLITICA))
        time.sleep(12)  # propagação da role antes de a Lambda poder assumi-la
        return arn


def garantir_funcao(role_arn: str) -> None:
    pacote = BASE / "out" / "flexia-coletor.zip"
    chave = "deploy/flexia-coletor.zip"
    if passo(f"enviar {pacote.name} ({pacote.stat().st_size/1e6:.0f} MB) para s3://{BUCKET}/{chave}"):
        s3.upload_file(str(pacote), BUCKET, chave)
    cfg = dict(Runtime="python3.13", Handler="lambda_handler.handler", Role=role_arn, Timeout=900, MemorySize=1536,
               Environment={"Variables": {"FLEXIA_BUCKET": BUCKET}}, Architectures=["x86_64"])
    try:
        lam.get_function(FunctionName=FUNCAO)
        if passo(f"atualizar código e configuração da Lambda {FUNCAO}"):
            lam.update_function_code(FunctionName=FUNCAO, S3Bucket=BUCKET, S3Key=chave)
            lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCAO)
            cfg.pop("Architectures")
            lam.update_function_configuration(FunctionName=FUNCAO, **cfg)
    except lam.exceptions.ResourceNotFoundException:
        if passo(f"criar Lambda {FUNCAO} (python3.13, 15 min, 1,5 GB)"):
            for tentativa in range(5):
                try:
                    lam.create_function(FunctionName=FUNCAO, Code={"S3Bucket": BUCKET, "S3Key": chave},
                                        Description="FlexIA: coleta Cavuca + indexação", **cfg)
                    break
                except ClientError as e:
                    if "cannot be assumed" not in str(e) or tentativa == 4:
                        raise
                    time.sleep(8)
    if APLICAR:
        lam.get_waiter("function_active_v2").wait(FunctionName=FUNCAO)


def garantir_regras() -> None:
    for nome, (cron, freq) in REGRAS.items():
        if not passo(f"regra {nome} {cron} -> {FUNCAO} {{'frequencia': '{freq}'}}"):
            continue
        arn_regra = ev.put_rule(Name=nome, ScheduleExpression=cron, State="ENABLED",
                                Description=f"FlexIA: coleta {freq}")["RuleArn"]
        ev.put_targets(Rule=nome, Targets=[{"Id": "coletor", "Arn": ARN_FUNCAO,
                                            "Input": json.dumps({"frequencia": freq})}])
        try:
            lam.add_permission(FunctionName=FUNCAO, StatementId=f"evento-{nome}", Action="lambda:InvokeFunction",
                               Principal="events.amazonaws.com", SourceArn=arn_regra)
        except lam.exceptions.ResourceConflictException:
            pass


def main() -> None:
    print(f"conta {CONTA}  bucket {BUCKET}  modo {'APLICAR' if APLICAR else 'simulação'}")
    garantir_funcao(garantir_role())
    garantir_regras()
    if not APLICAR:
        print("\nNada foi alterado. Rode com --aplicar para implantar.")


if __name__ == "__main__":
    main()
