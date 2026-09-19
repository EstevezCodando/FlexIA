"""Gera flexia/app/SINAgent/domain/regras_lake.py a partir de pipeline/catalogo.py (fonte única das regras)."""
from pathlib import Path

from catalogo import REGRAS

DESTINO = Path(__file__).resolve().parent.parent / "flexia" / "app" / "SINAgent" / "domain" / "regras_lake.py"

corpo = "\n".join(f"- {r}" for r in REGRAS)
DESTINO.parent.mkdir(parents=True, exist_ok=True)
DESTINO.write_text(
    '"""Gerado por pipeline/05_gerar_flexia.py a partir de pipeline/catalogo.py. Não edite à mão."""\n\n'
    f'PROMPT_DATA_LAKE = """\nDADOS DISPONÍVEIS (data lake do Hackathon ONS: Parquet no S3 consultado com DuckDB):\n\n'
    "Você tem ferramentas para consultar dados REAIS: listar_tabelas, descrever_tabela e consultar_sql.\n"
    "Fluxo obrigatório para perguntas com números: listar_tabelas(busca='palavras-chave') -> descrever_tabela -> consultar_sql.\n"
    "São cerca de 100 tabelas de ONS, ANEEL, CCEE, EPE e clima: sempre filtre listar_tabelas por busca ou tema.\n"
    "Todo número na resposta deve vir de uma consulta executada; cite a tabela usada e o período.\n"
    "Se a consulta falhar ou os dados não cobrirem a pergunta, diga isso em vez de estimar.\n\n"
    f"REGRAS DOS DADOS:\n{corpo}\n\"\"\"\n",
    encoding="utf-8",
)
print(f"gerado {DESTINO}")
