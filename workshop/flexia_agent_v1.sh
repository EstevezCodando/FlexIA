cd ~/build-with-skills/SINIntelligence && git add -A && git commit -m "Estado antes da FlexIA v1"

bash <<'SCRIPT'
cd ~/build-with-skills/SINIntelligence

set -e

echo "============================================================"
echo "1. BACKUP DO AGENTE ORIGINAL"
echo "============================================================"

# -n: não sobrescreve o backup se o script rodar de novo
cp -n app/SINAgent/main.py app/SINAgent/main.py.original


echo "============================================================"
echo "2. ESTRUTURA DO RUNTIME"
echo "============================================================"

mkdir -p \
  app/SINAgent/tools \
  app/SINAgent/services \
  app/SINAgent/domain

touch \
  app/SINAgent/tools/__init__.py \
  app/SINAgent/services/__init__.py \
  app/SINAgent/domain/__init__.py


echo "============================================================"
echo "3. CRIANDO TOOL DE TESTE"
echo "============================================================"

cat > app/SINAgent/tools/system_tools.py <<'PY'
from strands import tool


@tool
def status_projeto() -> str:
    """
    Retorna o estado atual das integrações da FlexIA.

    Use esta ferramenta quando o usuário perguntar sobre as capacidades
    atualmente implementadas no agente.
    """

    return """
FlexIA — estado atual

AgentCore Runtime: configurado
Framework Strands: configurado
Amazon Bedrock: configurado pelo workshop

Integração ONS: ainda não implementada
Integração meteorológica: ainda não implementada
Integração regulatória: ainda não implementada
Modelo de risco: ainda não implementado

IMPORTANTE:
Não existem dados operacionais reais conectados nesta etapa.
O agente não deve inventar valores do ONS, clima ou regulação.
""".strip()
PY


echo "============================================================"
echo "4. CRIANDO PRIMEIRA VERSÃO DA FLEXIA"
echo "============================================================"

cat > app/SINAgent/main.py <<'PY'
from typing import Any
from collections import OrderedDict

from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import (
    NullConversationManager,
)

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from model.load import load_model
from mcp_client.client import get_streamable_http_mcp_client
from tools.system_tools import status_projeto


# ============================================================
# AGENTCORE APPLICATION
# ============================================================

app = BedrockAgentCoreApp()
log = app.logger


# ============================================================
# SYSTEM PROMPT
# ============================================================

DEFAULT_SYSTEM_PROMPT = """
Você é a FlexIA, uma copiloto especializada no
Sistema Interligado Nacional brasileiro (SIN).

Quando perguntarem seu nome, responda que você é a FlexIA.

Seu objetivo é apoiar análise de:

- operação do Sistema Interligado Nacional;
- geração de energia;
- carga elétrica;
- geração eólica;
- geração fotovoltaica;
- meteorologia aplicada ao setor elétrico;
- restrições operacionais e constrained-off;
- documentos e regulação do setor elétrico brasileiro.

PRINCÍPIOS OBRIGATÓRIOS:

1. Nunca invente dados do ONS.

2. Nunca invente valores meteorológicos.

3. Nunca invente legislação, resolução, procedimento ou
   documento regulatório.

4. Quando houver ferramentas disponíveis, utilize-as para
   obter fatos e dados.

5. Diferencie explicitamente:

   DADO OBSERVADO
   PREVISÃO
   INDICADOR CALCULADO
   INFERÊNCIA
   HIPÓTESE

6. Não trate correlação como causalidade.

7. Sempre informe quando os dados forem insuficientes.

8. Valores numéricos futuros deverão ser produzidos por
   modelos, cálculos ou fontes apropriadas, e não pela
   imaginação do modelo de linguagem.

9. Sua função é interpretar evidências e auxiliar a tomada
   de decisão, não substituir os sistemas operacionais do ONS.

10. Responda preferencialmente em português brasileiro,
    salvo solicitação diferente do usuário.

Neste momento algumas integrações podem ainda estar em
desenvolvimento. Use a ferramenta status_projeto quando
precisar verificar quais capacidades estão realmente
implementadas.
"""


# ============================================================
# TOOLS
# ============================================================

tools = [
    status_projeto,
]


# ============================================================
# OPTIONAL MCP
# ============================================================

try:
    mcp_client = get_streamable_http_mcp_client()

    if mcp_client:
        tools.append(mcp_client)

except Exception as exc:
    log.warning(
        "MCP client não disponível nesta execução: %s",
        exc,
    )


# ============================================================
# CONVERSATION MANAGEMENT
# ============================================================

def _make_conversation_manager():
    return NullConversationManager()


def agent_factory():

    cache = OrderedDict()

    def get_or_create_agent(session_id):

        if session_id in cache:
            cache.move_to_end(session_id)
            return cache[session_id]

        if len(cache) >= 128:
            cache.popitem(last=False)

        cache[session_id] = Agent(
            model=load_model(),
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            tools=tools,
            conversation_manager=_make_conversation_manager(),
        )

        return cache[session_id]

    return get_or_create_agent


get_or_create_agent = agent_factory()


# ============================================================
# PAYLOAD HANDLING
# ============================================================

def strip_trailing_tool_use(messages: Any) -> list[dict]:

    if not isinstance(messages, list):
        raise ValueError("messages must be a list")

    messages = list(messages)

    while messages:

        last = messages[-1]

        if not isinstance(last, dict):
            raise ValueError("each message must be an object")

        original_content = last.get("content", [])

        if not isinstance(original_content, list):
            raise ValueError(
                "each message content value must be a list"
            )

        content = [
            block
            for block in original_content
            if isinstance(block, dict)
            and "toolUse" not in block
        ]

        if len(content) == len(original_content):
            break

        if content:

            messages[-1] = {
                **last,
                "content": content,
            }

            break

        messages.pop()

    return messages


def _extract_prompt(payload: dict):

    if not isinstance(payload, dict):
        raise ValueError(
            "payload must be a JSON object"
        )

    if "messages" in payload:
        return strip_trailing_tool_use(
            payload["messages"]
        )

    if "tool_results" in payload:

        tool_results = payload["tool_results"]

        if not isinstance(tool_results, list):
            raise ValueError(
                "tool_results must be a list"
            )

        return [
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": tr["toolUseId"],
                            "status": tr.get(
                                "status",
                                "success",
                            ),
                            "content": tr.get(
                                "content",
                                [],
                            ),
                        }
                    }
                    for tr in tool_results
                ],
            }
        ]

    prompt = payload.get("prompt", "")

    if not isinstance(prompt, str):
        raise ValueError(
            "prompt must be a string"
        )

    return prompt


# ============================================================
# AGENTCORE ENTRYPOINT
# ============================================================

@app.entrypoint
async def invoke(payload, context):

    log.info("Invoking FlexIA Agent")

    session_id = getattr(
        context,
        "session_id",
        "default-session",
    )

    agent = get_or_create_agent(
        session_id
    )

    prompt = _extract_prompt(
        payload
    )

    async for event in agent.stream_async(
        prompt
    ):

        if (
            not isinstance(event, dict)
            or "event" not in event
        ):
            continue

        content_block_start = (
            event["event"]
            .get("contentBlockStart")
        )

        if (
            content_block_start is not None
            and not content_block_start.get("start")
        ):
            continue

        yield event


# ============================================================
# LOCAL EXECUTION
# ============================================================

if __name__ == "__main__":
    app.run()
PY


echo
echo "============================================================"
echo "5. TESTANDO SINTAXE PYTHON"
echo "============================================================"

python3 -m py_compile \
  app/SINAgent/main.py \
  app/SINAgent/tools/system_tools.py

echo "Python: OK"


echo
echo "============================================================"
echo "6. VALIDANDO CONFIGURAÇÃO AGENTCORE"
echo "============================================================"

agentcore validate


echo
echo "============================================================"
echo "7. ESTRUTURA DO RUNTIME"
echo "============================================================"

find app/SINAgent \
  -maxdepth 3 \
  -type f \
  | sort


echo
echo "============================================================"
echo "8. PRIMEIRO TESTE LOCAL DA FLEXIA"
echo "============================================================"
echo

agentcore dev \
  "Use obrigatoriamente a ferramenta status_projeto e depois me diga seu nome, quais integrações já estão funcionando e quais ainda precisam ser implementadas."
SCRIPT
