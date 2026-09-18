"""Teste local da FlexIA v2: chama o entrypoint como o AgentCore faria e imprime a resposta em streaming.

Uso: python flexia/testar_local.py "pergunta 1" "pergunta 2" ...
(usa as credenciais do perfil AWS_PROFILE; mesma sessão para todas as perguntas)
"""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent / "app" / "SINAgent"))
import main  # noqa: E402


async def perguntar(q: str, ctx) -> None:
    t0 = time.time()
    primeiro = None
    print(f"\n>>> {q}")
    async for ev in main.invoke({"prompt": q}, ctx):
        delta = ev["event"].get("contentBlockDelta", {}).get("delta", {})
        if "text" in delta:
            primeiro = primeiro or time.time() - t0
            print(delta["text"], end="", flush=True)
        uso = ev["event"].get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if uso:
            print(f"\n  [ferramenta: {uso['name']}]", flush=True)
    print(f"\n<<< primeiro texto em {primeiro or 0:.1f}s, total {time.time() - t0:.1f}s")


async def rodar(perguntas):
    ctx = SimpleNamespace(session_id="teste-local")
    for q in perguntas:
        await perguntar(q, ctx)


if __name__ == "__main__":
    asyncio.run(rodar(sys.argv[1:]))
