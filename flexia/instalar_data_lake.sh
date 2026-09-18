# Conecta a FlexIA ao data lake. Rodar no Code Editor do workshop, dentro de ~/build-with-skills/SINIntelligence.
# Pré-requisito: a FlexIA v1 (workshop/flexia_agent_v1.sh) já aplicada e o lake publicado (pipeline/04_publicar.py).
bash <<'SCRIPT'
set -e
cd ~/build-with-skills/SINIntelligence
git add -A && git commit -qm "Estado antes de conectar a FlexIA ao data lake" || true

CONTA=$(aws sts get-caller-identity --query Account --output text)
aws s3 cp "s3://ons-datalake-${CONTA}/flexia/app/SINAgent/" app/SINAgent/ --recursive

python3 - <<'PY'
import re, pathlib
p = pathlib.Path("app/SINAgent/main.py")
s = p.read_text(encoding="utf-8")
if "data_lake_tools" not in s:
    s = s.replace(
        "from tools.system_tools import status_projeto",
        "from tools.system_tools import status_projeto\n"
        "from tools.data_lake_tools import listar_tabelas, descrever_tabela, consultar_sql\n"
        "from domain.regras_lake import PROMPT_DATA_LAKE",
    )
    s = s.replace("tools = [\n    status_projeto,\n]",
                  "tools = [\n    status_projeto,\n    listar_tabelas,\n    descrever_tabela,\n    consultar_sql,\n]")
    s = s.replace('implementadas.\n"""', 'implementadas.\n"""\n\nDEFAULT_SYSTEM_PROMPT += PROMPT_DATA_LAKE', 1)
    p.write_text(s, encoding="utf-8")
t = pathlib.Path("app/SINAgent/tools/system_tools.py")
u = t.read_text(encoding="utf-8")
u = u.replace("Integração ONS: ainda não implementada",
              "Integração ONS: IMPLEMENTADA (data lake no Athena: geração, carga, CMO, intercâmbio, constrained-off)")
u = u.replace("Integração meteorológica: ainda não implementada",
              "Integração meteorológica: IMPLEMENTADA (reanálise ERA5 horária 2023-2026)")
u = u.replace("Integração regulatória: ainda não implementada",
              "Integração regulatória: PARCIAL (tarifas ANEEL e cadastro SIGA; sem textos de resoluções)")
u = u.replace("Não existem dados operacionais reais conectados nesta etapa.",
              "Dados reais disponíveis via listar_tabelas / descrever_tabela / consultar_sql.")
t.write_text(u, encoding="utf-8")
PY

grep -q '^boto3' app/SINAgent/requirements.txt 2>/dev/null || echo "boto3" >> app/SINAgent/requirements.txt 2>/dev/null || true
python3 -m py_compile app/SINAgent/main.py app/SINAgent/tools/data_lake_tools.py app/SINAgent/domain/regras_lake.py
echo "FlexIA conectada ao data lake. Teste local:"
agentcore dev "Qual foi o volume total de corte (curtailment) eólico e solar em 2025, por razão da restrição? Use as ferramentas de dados."
SCRIPT
