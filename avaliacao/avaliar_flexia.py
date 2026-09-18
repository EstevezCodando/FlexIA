"""Avaliação de exatidão das respostas da FlexIA.

Para cada pergunta, o gabarito é calculado direto nos dados (SQL no lake local) ou é um trecho
literal esperado no documento-fonte. A FlexIA responde em uma sessão nova e a resposta é
considerada correta se contiver o valor do gabarito (tolerância relativa) ou o trecho esperado.

Uso: python avaliacao/avaliar_flexia.py      (usa AWS_PROFILE para Bedrock/S3)
Saída: out/avaliacao_flexia.json
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import duckdb

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "flexia" / "app" / "SINAgent"))
import main  # noqa: E402
from domain.roteador import classificar  # noqa: E402

L = (BASE / "out" / "lake").as_posix()
con = duckdb.connect()


def q(sql: str):
    return con.execute(sql.replace("$L", L)).fetchone()[0]


CASOS = [
    {"pergunta": "Qual foi o CMO médio do subsistema Sudeste em 2025, em R$/MWh?",
     "valor": q("select avg(val_cmo) from read_parquet('$L/curated/ons_cmo_semihorario/**/*.parquet', hive_partitioning=true) where ano=2025 and id_subsistema='SE'"),
     "tol": 0.01},
    {"pergunta": "Qual foi a carga média do Nordeste em 2024, em MWmed?",
     "valor": q("select avg(val_cargaenergiahomwmed) from read_parquet('$L/curated/ons_curva_carga/**/*.parquet', hive_partitioning=true) where ano=2024 and id_subsistema='NE'"),
     "tol": 0.01},
    {"pergunta": "Quantos TWh de energia eólica foram cortados (curtailment) no Brasil em 2025, somando todas as razões?",
     "valor": q("select sum(corte_mwh)/1e6 from '$L/analytics/analytics_corte_usina/*.parquet' where fonte='EOLICA' and year(din_instante)=2025"),
     "tol": 0.02},
    {"pergunta": "Qual foi a geração solar total do SIN em 2025, em TWh, segundo o balanço de energia do ONS?",
     "valor": q("select sum(val_gersolar)/1e6 from read_parquet('$L/curated/ons_balanco_energia_subsistema/**/*.parquet', hive_partitioning=true) where ano=2025 and id_subsistema='SIN'"),
     "tol": 0.02},
    {"pergunta": "Qual a potência fiscalizada total, em GW, das usinas eólicas (EOL) em operação no cadastro SIGA da ANEEL?",
     "valor": q("select sum(mdapotenciafiscalizadakw)/1e6 from '$L/curated/aneel_siga_empreendimentos/*.parquet' where sigtipogeracao='EOL' and dscfaseusina='Operação'"),
     "tol": 0.02},
    {"pergunta": "Quantos veículos plug-in (BEV + PHEV) havia na cidade do Rio de Janeiro em julho de 2026?",
     "valor": q("select plugin from '$L/analytics/analytics_frota_ev_rio/*.parquet' where month(mes)=7 and year(mes)=2026"),
     "tol": 0.001},
    {"pergunta": "Em que mês de 2025 o corte eólico no Nordeste foi o maior? Responda o nome do mês.",
     "texto": ["outubro"]},
    {"pergunta": "Segundo a Lei 14.300, o que é o Sistema de Compensação de Energia Elétrica (SCEE)?",
     "texto": ["empréstimo gratuito"]},
    {"pergunta": "Qual lei autorizou a criação da Empresa de Pesquisa Energética (EPE)?",
     "texto": ["10.847"]},
    {"pergunta": "Qual o potencial de resposta da demanda no Brasil estimado pela EPE no cenário de referência?",
     "texto": ["8,8 GW", "8.8 GW"]},
]


def numeros(texto: str) -> list[float]:
    """Extrai números em formato brasileiro (1.234,5) ou internacional (1234.5)."""
    saida = []
    for t in re.findall(r"\d[\d.,]*", texto):
        t = t.rstrip(".,")
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
        try:
            saida.append(float(t))
        except ValueError:
            pass
    return saida


async def responder(pergunta: str, i: int) -> str:
    partes = []
    async for ev in main.invoke({"prompt": pergunta}, SimpleNamespace(session_id=f"avaliacao-{i}-{time.time()}")):
        d = ev["event"].get("contentBlockDelta", {}).get("delta", {})
        if "text" in d:
            partes.append(d["text"])
    return "".join(partes)


async def rodar():
    resultados = []
    for i, c in enumerate(CASOS):
        rota = classificar(c["pergunta"])
        t0 = time.time()
        resp = await responder(c["pergunta"], i)
        dt = time.time() - t0
        if "valor" in c:
            ok = any(abs(n - c["valor"]) <= c["tol"] * abs(c["valor"]) for n in numeros(resp))
            esperado = round(c["valor"], 3)
        else:
            ok = any(t.lower() in resp.lower() for t in c["texto"])
            esperado = c["texto"]
        resultados.append({"pergunta": c["pergunta"], "esperado": esperado, "correta": ok, "segundos": round(dt, 1),
                           "rota": rota.rota, "modelo": rota.modelo, "resposta": resp[-600:]})
        print(f"{'OK  ' if ok else 'ERRO'} {dt:5.1f}s {rota.modelo:45s} {c['pergunta'][:70]}  (esperado {esperado})", flush=True)
    acertos = sum(r["correta"] for r in resultados)
    resumo = {"acertos": acertos, "total": len(resultados),
              "tempo_medio_s": round(sum(r["segundos"] for r in resultados) / len(resultados), 1),
              "casos": resultados}
    (BASE / "out" / "avaliacao_flexia.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nacertos: {acertos}/{len(resultados)}  tempo médio {resumo['tempo_medio_s']} s")


if __name__ == "__main__":
    asyncio.run(rodar())
