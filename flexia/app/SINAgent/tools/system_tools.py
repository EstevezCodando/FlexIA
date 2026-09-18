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
Roteamento por pergunta: NVIDIA Nemotron Nano 3 30B escolhe o modelo
  (Nemotron Nano, Nemotron Super 3 120B, Claude Haiku 4.5 ou Claude Sonnet 4.6)

Integração ONS: IMPLEMENTADA — data lake no S3 via DuckDB (geração por usina, balanço,
  carga, CMO, intercâmbio, constrained-off eólico e solar, programação diária, cadastros)
Integração meteorológica: IMPLEMENTADA — reanálise ERA5 horária 2023–2026 nos polos eólicos/solares
Integração regulatória: IMPLEMENTADA — tarifas ANEEL, cadastro SIGA, leis do setor (Planalto),
  procedimentos regulatórios ANEEL/CCEE e notícias ANEEL/MME/CCEE/EPE, com coleta agendada (Cavuca)
Diário Oficial da União: PENDENTE — exige cadastro no INLABS
Notícias e Procedimentos de Rede do ONS: PENDENTE — páginas dependem de navegador
Modelo de risco: ainda não implementado
""".strip()
