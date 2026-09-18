# Instala a FlexIA v2 no projeto do Code Editor: roteamento NVIDIA Nemotron, data lake (DuckDB/S3)
# e busca em documentos (Cavuca). Colar no terminal do Code Editor.
cd ~/build-with-skills/SINIntelligence && git add -A && git commit -qm "Estado antes da FlexIA v2" || true

bash <<'SCRIPT'
set -e
cd ~/build-with-skills/SINIntelligence
CONTA=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ons-datalake-${CONTA}"

cp -n app/SINAgent/main.py app/SINAgent/main.py.original 2>/dev/null || true
aws s3 cp "s3://${BUCKET}/flexia/app/SINAgent/" app/SINAgent/ --recursive --quiet
find app/SINAgent -maxdepth 2 -name "*.py" | sort

for dep in boto3 duckdb numpy; do
  grep -qi "^${dep}" app/SINAgent/requirements.txt 2>/dev/null || echo "${dep}" >> app/SINAgent/requirements.txt
done
cat app/SINAgent/requirements.txt 2>/dev/null || true

python3 -m py_compile app/SINAgent/main.py app/SINAgent/domain/*.py app/SINAgent/tools/*.py
echo "Python: OK"
agentcore validate

echo "Teste local (dados + documentos + conversa):"
agentcore dev "Oi! Qual seu nome e o que você consegue fazer?"
SCRIPT
