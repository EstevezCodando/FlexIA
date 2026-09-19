# Implanta a FlexIA v2 no Bedrock AgentCore a partir da máquina do Code Editor.
# Executado remotamente por: python infra/code_editor.py --arquivo flexia/implantar_flexia.sh
# (ou colado no terminal do Code Editor). Idempotente.
set -e
exec > >(tee ~/flexia-implantar.log) 2>&1
source ~/.nvm/nvm.sh
[ -f ~/workshop-env.sh ] && source ~/workshop-env.sh
cd ~/build-with-skills/SINIntelligence
CONTA=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ons-datalake-${CONTA}"

echo "== 1. commit do estado atual (regra do projeto)"
git add -A && git -c user.name='FlexIA' -c user.email='flexia@local' commit -qm "Estado antes de implantar a FlexIA v2" || true

echo "== 2. código da FlexIA v2 (bucket em us-east-1)"
aws s3 cp "s3://${BUCKET}/flexia/app/SINAgent/" app/SINAgent/ --recursive --quiet --region us-east-1
find app/SINAgent -name "*.py" -not -path "*/.venv/*" -newer agentcore/agentcore.json | sort

echo "== 3. dependências no pyproject.toml"
python3 - <<'PY'
import re, pathlib
p = pathlib.Path("app/SINAgent/pyproject.toml")
s = p.read_text()
for dep in ('"duckdb >= 1.5.0"', '"numpy >= 2.0"', '"boto3 >= 1.40.0"'):
    nome = dep.split()[0].strip('"')
    if not re.search(rf'"{nome}\b', s):
        s = s.replace('dependencies = [', f'dependencies = [\n    {dep},', 1)
p.write_text(s)
print(re.search(r"dependencies = \[.*?\]", s, re.S).group(0))
PY

echo "== 4. sintaxe e validação"
python3 -m py_compile app/SINAgent/main.py app/SINAgent/domain/*.py app/SINAgent/tools/*.py
agentcore validate

echo "== 5. alvo de implantação (conta e região do workshop)"
if [ "$(cat agentcore/aws-targets.json | tr -d ' \n')" = "[]" ]; then
  printf '[{"name":"default","account":"%s","region":"%s"}]\n' "$CONTA" "${AWS_REGION:-us-west-2}" > agentcore/aws-targets.json
fi
cat agentcore/aws-targets.json

echo "== 6. deploy (CDK)"
agentcore deploy --target default --yes --json

echo "== 7. status"
agentcore status

git add -A && git -c user.name='FlexIA' -c user.email='flexia@local' commit -qm "FlexIA v2 implantada no AgentCore" || true
