"""Roteamento por pergunta com NVIDIA Nemotron (Bedrock).

O Nemotron Nano 3 30B classifica cada pergunta (~0,4 s) e o roteador escolhe o modelo que
responde. Perguntas simples ficam em modelos rápidos; cálculo e raciocínio longo vão para o Claude.

  rota          complexidade   modelo que responde
  conversa      -              nvidia.nemotron-nano-3-30b       (sem ferramentas)
  fora_escopo   -              claude haiku 4.5                 (com ferramentas; recusa só se confirmar)
  documentos    simples        claude haiku 4.5                 (buscar_documentos; fidelidade literal)
  dados         simples        claude haiku 4.5                 (SQL no lake)
  qualquer      complexa       claude sonnet 4.6                (todas as ferramentas)
  misto         -              claude sonnet 4.6
"""
import json
import os
import re
from dataclasses import dataclass

import boto3

REGIAO = os.environ.get("AWS_REGION", "us-east-1")
ROTEADOR = os.environ.get("FLEXIA_MODELO_ROTEADOR", "nvidia.nemotron-nano-3-30b")
MODELOS = {
    "rapido": os.environ.get("FLEXIA_MODELO_RAPIDO", "nvidia.nemotron-nano-3-30b"),
    # Nemotron Super foi testado aqui e inventou incisos da Lei 14.300 (mesmo entre aspas);
    # Claude Haiku 4.5 transcreveu o texto exato. Documentos exigem fidelidade literal.
    "documentos": os.environ.get("FLEXIA_MODELO_DOCUMENTOS", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "dados": os.environ.get("FLEXIA_MODELO_DADOS", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "raciocinio": os.environ.get("FLEXIA_MODELO_RACIOCINIO", "us.anthropic.claude-sonnet-4-6"),
}

_INSTRUCAO = """/no_think
Você é o roteador da FlexIA, assistente do setor elétrico brasileiro. Classifique a MENSAGEM do usuário.

rota:
- "dados": pede números/estatísticas de operação: geração, carga, CMO, intercâmbio, corte (constrained-off/curtailment), clima, tarifas, capacidade, frota de EV.
- "documentos": pede regulação, leis, resoluções, procedimentos, notícias, eventos, definições ou explicações textuais do setor.
- "misto": precisa de números E de contexto regulatório/notícias.
- "conversa": saudação, agradecimento, pergunta sobre a própria FlexIA.
- "fora_escopo": nada a ver com energia/setor elétrico (ex.: futebol, receitas, política geral).

São DO ESCOPO (nunca "fora_escopo"): mobilidade elétrica, veículos elétricos, frota plug-in, recarga,
tarifas de energia, consumo, clima/vento/irradiação, mercado livre, leilões, usinas, empresas do setor.

complexidade:
- "simples": uma consulta ou um fato direto.
- "complexa": comparação entre períodos/fontes, várias etapas, cálculo derivado, análise ou recomendação.

Responda SOMENTE com JSON: {"rota": "...", "complexidade": "..."}"""

_cliente = boto3.client("bedrock-runtime", region_name=REGIAO)


@dataclass
class Decisao:
    rota: str
    complexidade: str
    perfil: str  # chave de MODELOS
    usa_ferramentas: bool

    @property
    def modelo(self) -> str:
        return MODELOS[self.perfil]


def _perfil(rota: str, complexidade: str) -> tuple[str, bool]:
    if rota == "conversa":
        return "rapido", False
    if rota == "fora_escopo":
        # Não recusa no roteador: em teste, o Nemotron marcou "frota de veículos elétricos do Rio"
        # como fora de escopo em 2 de 6 tentativas. Um modelo com ferramentas confirma antes de recusar.
        return "dados", True
    if rota == "misto" or complexidade == "complexa":
        return "raciocinio", True
    if rota == "documentos":
        return "documentos", True
    return "dados", True


def classificar(mensagem: str) -> Decisao:
    """Classifica a pergunta; em qualquer falha usa o caminho mais capaz (Claude com ferramentas)."""
    try:
        r = _cliente.converse(
            modelId=ROTEADOR,
            system=[{"text": _INSTRUCAO}],
            messages=[{"role": "user", "content": [{"text": mensagem[:2000]}]}],
            inferenceConfig={"maxTokens": 60, "temperature": 0},
        )
        texto = " ".join(c.get("text", "") for c in r["output"]["message"]["content"])
        m = re.search(r"\{.*?\}", texto, re.S)
        d = json.loads(m.group(0)) if m else {}
        rota = d.get("rota") if d.get("rota") in ("dados", "documentos", "misto", "conversa", "fora_escopo") else "misto"
        comp = d.get("complexidade") if d.get("complexidade") in ("simples", "complexa") else "complexa"
    except Exception:  # noqa: BLE001
        rota, comp = "misto", "complexa"
    perfil, ferramentas = _perfil(rota, comp)
    return Decisao(rota, comp, perfil, ferramentas)
