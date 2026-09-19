"""Avaliação de exatidão das respostas da FlexIA e do roteador NVIDIA Nemotron.

Parte 1 — respostas (ponta a ponta): para cada pergunta, o gabarito é calculado direto nos dados
(SQL no lake local) ou é um trecho literal esperado no documento-fonte. Perguntas "sem resposta"
pedem dados que não existem no lake; a resposta correta é admitir a falta de dados. Cada pergunta
roda numa sessão nova; o conjunto roda N vezes (--repeticoes) para medir variação.

Parte 2 — roteador: perguntas rotuladas com as rotas aceitáveis, repetidas 3 vezes; mede acurácia,
estabilidade e matriz de confusão.

Uso: python avaliacao/avaliar_flexia.py [--repeticoes 2] [--so-roteador]
Saída: avaliacao/resultados/flexia.json e avaliacao/resultados/flexia.md
"""
import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import duckdb

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "flexia" / "app" / "SINAgent"))
from domain.roteador import classificar  # noqa: E402

SAIDA = BASE / "avaliacao" / "resultados"
L = (BASE / "out" / "lake").as_posix()
con = duckdb.connect()


def q(sql: str):
    return con.execute(sql.replace("$L", L)).fetchone()[0]


ADMITE = re.compile(
    r"n[ãa]o (h[áa]|possu|disp[õo]|dispon|encontr|cobre|constam|existem|tenho|consegui|est[áa] dispon)|sem dados|"
    r"indispon[íi]vel|fora do per[íi]odo|a partir de (abr|2020|2024)|come[çc]a(m)? em|inicia(m)? em|n[ãa]o inclui",
    re.I)

CASOS = [
    # ---------- numéricas (gabarito por SQL) ----------
    {"cat": "numerica", "pergunta": "Qual foi o CMO médio do subsistema Sudeste em 2025, em R$/MWh?",
     "valor": q("select avg(val_cmo) from read_parquet('$L/curated/ons_cmo_semihorario/**/*.parquet', hive_partitioning=true) where ano=2025 and id_subsistema='SE'"), "tol": 0.01},
    {"cat": "numerica", "pergunta": "Qual foi a carga média do Nordeste em 2024, em MWmed?",
     "valor": q("select avg(val_cargaenergiahomwmed) from read_parquet('$L/curated/ons_curva_carga/**/*.parquet', hive_partitioning=true) where ano=2024 and id_subsistema='NE'"), "tol": 0.01},
    {"cat": "numerica", "pergunta": "Quantos TWh de energia eólica foram cortados (curtailment) no Brasil em 2025, somando todas as razões?",
     "valor": q("select sum(corte_mwh)/1e6 from '$L/analytics/analytics_corte_usina/*.parquet' where fonte='EOLICA' and year(din_instante)=2025"), "tol": 0.02},
    {"cat": "numerica", "pergunta": "Qual foi a geração solar total do SIN em 2025, em TWh, segundo o balanço de energia do ONS?",
     "valor": q("select sum(val_gersolar)/1e6 from read_parquet('$L/curated/ons_balanco_energia_subsistema/**/*.parquet', hive_partitioning=true) where ano=2025 and id_subsistema='SIN'"), "tol": 0.02},
    {"cat": "numerica", "pergunta": "Qual a potência fiscalizada total, em GW, das usinas eólicas (EOL) em operação no cadastro SIGA da ANEEL?",
     "valor": q("select sum(mdapotenciafiscalizadakw)/1e6 from '$L/curated/aneel_siga_empreendimentos/*.parquet' where sigtipogeracao='EOL' and dscfaseusina='Operação'"), "tol": 0.02},
    {"cat": "numerica", "pergunta": "Quantos veículos plug-in (BEV + PHEV) havia na cidade do Rio de Janeiro em julho de 2026?",
     "valor": q("select plugin from '$L/analytics/analytics_frota_ev_rio/*.parquet' where month(mes)=7 and year(mes)=2026"), "tol": 0.001},
    {"cat": "numerica", "pergunta": "Em que mês de 2025 o corte eólico no Nordeste foi o maior? Responda o nome do mês.",
     "texto": ["outubro"]},
    # ---------- documentos (trecho literal esperado) ----------
    {"cat": "documento", "pergunta": "Segundo a Lei 14.300, o que é o Sistema de Compensação de Energia Elétrica (SCEE)?",
     "texto": ["empréstimo gratuito"]},
    {"cat": "documento", "pergunta": "Qual lei autorizou a criação da Empresa de Pesquisa Energética (EPE)?",
     "texto": ["10.847"]},
    {"cat": "documento", "pergunta": "Qual o potencial de resposta da demanda no Brasil estimado pela EPE no cenário de referência?",
     "texto": ["8,8 GW", "8.8 GW"]},
    # ---------- sem resposta nos dados (deve admitir) ----------
    {"cat": "sem_resposta", "pergunta": "Qual foi o CMO médio do Sudeste em 2018?", "admitir": True},
    {"cat": "sem_resposta", "pergunta": "Quanta energia solar foi cortada (constrained-off) no Brasil em 2022?", "admitir": True},
    {"cat": "sem_resposta", "pergunta": "Qual será a carga média do Nordeste em 2030?", "admitir": True},
]

ROTEADOR = [
    ("Oi, tudo bem?", {"conversa"}), ("Obrigado pela ajuda!", {"conversa"}), ("Qual é o seu nome?", {"conversa"}),
    ("O que você consegue fazer?", {"conversa", "documentos"}),
    ("Qual foi o CMO médio do Sudeste em 2025?", {"dados"}),
    ("Quantos MW de capacidade solar existem na Bahia?", {"dados"}),
    ("Qual foi a geração eólica do Nordeste em agosto de 2026?", {"dados"}),
    ("Quantos veículos elétricos há no Rio de Janeiro?", {"dados"}),
    ("Qual a tarifa residencial da Light?", {"dados", "documentos"}),
    ("Qual a carga do SIN ontem às 18h?", {"dados"}),
    ("O que a Lei 14.300 diz sobre compensação de energia?", {"documentos"}),
    ("Quais as últimas notícias da CCEE?", {"documentos"}),
    ("O que é o PRODIST?", {"documentos"}),
    ("Qual lei criou a ANEEL?", {"documentos"}),
    ("O que a EPE publicou sobre resposta da demanda?", {"documentos"}),
    ("Compare o corte eólico do Nordeste em 2024 e 2025 e explique as causas regulatórias", {"misto"}),
    ("O corte de energia aumentou depois das novas regras de ressarcimento? Mostre os números.", {"misto"}),
    ("Quanto foi cortado em 2025 e o que o MME está fazendo sobre isso?", {"misto"}),
    ("Quem ganhou a copa de 2022?", {"fora_escopo"}), ("Me passe uma receita de bolo de cenoura", {"fora_escopo"}),
    ("Qual a capital da Austrália?", {"fora_escopo"}),
    ("Qual foi a evolução mensal do CMO do Nordeste em 2025 e em quais meses ficou acima de 300 R$/MWh?", {"dados", "misto"}),
    ("Quais usinas eólicas tiveram mais corte em 2025?", {"dados"}),
    ("Existe relação entre vento forte e corte eólico no Nordeste?", {"dados", "misto"}),
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


def correta(c: dict, resp: str) -> bool:
    if "valor" in c:
        return any(abs(n - c["valor"]) <= c["tol"] * abs(c["valor"]) for n in numeros(resp))
    if "texto" in c:
        return any(t.lower() in resp.lower() for t in c["texto"])
    return bool(ADMITE.search(resp))


async def responder(main, pergunta: str, sessao: str) -> str:
    partes = []
    async for ev in main.invoke({"prompt": pergunta}, SimpleNamespace(session_id=sessao)):
        d = ev["event"].get("contentBlockDelta", {}).get("delta", {})
        if "text" in d:
            partes.append(d["text"])
    return "".join(partes)


async def ponta_a_ponta(repeticoes: int) -> dict:
    import main  # noqa: PLC0415  (carrega o agente só quando necessário)
    main._aquecer()  # mede as respostas sem o custo de inicialização
    execucoes = []
    for rep in range(repeticoes):
        for i, c in enumerate(CASOS):
            t0 = time.time()
            resp = await responder(main, c["pergunta"], f"aval-{rep}-{i}-{time.time()}")
            ok = correta(c, resp)
            execucoes.append({"rodada": rep + 1, "cat": c["cat"], "pergunta": c["pergunta"], "correta": ok,
                              "segundos": round(time.time() - t0, 1), "resposta_final": resp[-500:],
                              "esperado": round(c["valor"], 3) if "valor" in c else c.get("texto", "admitir falta de dados")})
            print(f"r{rep + 1} {'OK  ' if ok else 'ERRO'} {execucoes[-1]['segundos']:5.1f}s [{c['cat']}] {c['pergunta'][:80]}", flush=True)
    tempos = sorted(e["segundos"] for e in execucoes)
    por_cat = {}
    for cat in ("numerica", "documento", "sem_resposta"):
        es = [e for e in execucoes if e["cat"] == cat]
        por_cat[cat] = {"acertos": sum(e["correta"] for e in es), "total": len(es),
                        "acuracia_pct": round(sum(e["correta"] for e in es) / len(es) * 100, 1)}
    por_rodada = [round(sum(e["correta"] for e in execucoes if e["rodada"] == r) / len(CASOS) * 100, 1)
                  for r in range(1, repeticoes + 1)]
    return {"repeticoes": repeticoes, "perguntas": len(CASOS),
            "acuracia_pct": round(sum(e["correta"] for e in execucoes) / len(execucoes) * 100, 1),
            "acuracia_por_rodada_pct": por_rodada, "por_categoria": por_cat,
            "latencia_s": {"media": round(statistics.mean(tempos), 1), "p50": tempos[len(tempos) // 2],
                           "p90": tempos[int(len(tempos) * 0.9) - 1], "max": tempos[-1]},
            "execucoes": execucoes}


def roteador(rep: int = 3) -> dict:
    rotas = ["conversa", "dados", "documentos", "misto", "fora_escopo"]
    registros, tempos = [], []
    for pergunta, aceitas in ROTEADOR:
        obtidas, sem_ferramentas = [], 0
        for _ in range(rep):
            t0 = time.time()
            d = classificar(pergunta)
            tempos.append(time.time() - t0)
            obtidas.append(d.rota)
            # risco real: pergunta que precisa de dados/documentos respondida sem ferramentas
            sem_ferramentas += (not d.usa_ferramentas) and "conversa" not in aceitas
        registros.append({"pergunta": pergunta, "aceitas": sorted(aceitas), "obtidas": obtidas,
                          "acertos": sum(o in aceitas for o in obtidas), "estavel": len(set(obtidas)) == 1,
                          "sem_ferramentas_indevido": sem_ferramentas})
    total = len(ROTEADOR) * rep
    confusao = {a: Counter() for a in rotas}
    for (pergunta, aceitas), reg in zip(ROTEADOR, registros):
        esperado = sorted(aceitas)[0] if len(aceitas) == 1 else "/".join(sorted(aceitas))
        confusao.setdefault(esperado, Counter())
        for o in reg["obtidas"]:
            confusao[esperado][o] += 1
    tempos.sort()
    return {"perguntas": len(ROTEADOR), "repeticoes": rep,
            "acuracia_pct": round(sum(r["acertos"] for r in registros) / total * 100, 1),
            "estabilidade_pct": round(sum(r["estavel"] for r in registros) / len(registros) * 100, 1),
            "recusas_indevidas": sum(o == "fora_escopo" for r in registros if "fora_escopo" not in r["aceitas"] for o in r["obtidas"]),
            "respondidas_sem_ferramentas_indevidamente": sum(r["sem_ferramentas_indevido"] for r in registros),
            "latencia_s": {"media": round(statistics.mean(tempos), 2), "p50": round(tempos[len(tempos) // 2], 2),
                           "p90": round(tempos[int(len(tempos) * 0.9) - 1], 2)},
            "confusao": {k: dict(v) for k, v in confusao.items() if v}, "registros": registros}


def relatorio(res: dict) -> str:
    md = ["# Resultados — FlexIA", "", "Gerado por `avaliacao/avaliar_flexia.py`.", ""]
    if "respostas" in res:
        a = res["respostas"]
        md += ["## Exatidão das respostas (ponta a ponta)", "",
               f"{a['perguntas']} perguntas × {a['repeticoes']} rodadas = {a['perguntas'] * a['repeticoes']} execuções. "
               f"**Acurácia geral: {a['acuracia_pct']} %** (por rodada: {', '.join(f'{x} %' for x in a['acuracia_por_rodada_pct'])}).", "",
               "| categoria | acertos | acurácia % |", "|---|---:|---:|"]
        nomes = {"numerica": "numéricas (gabarito SQL)", "documento": "documentos (trecho literal)",
                 "sem_resposta": "sem resposta nos dados (deve admitir)"}
        for k, v in a["por_categoria"].items():
            md.append(f"| {nomes[k]} | {v['acertos']}/{v['total']} | {v['acuracia_pct']} |")
        lt = a["latencia_s"]
        md += ["", f"Latência por resposta: média {lt['media']} s, mediana {lt['p50']} s, p90 {lt['p90']} s, máxima {lt['max']} s.", "",
               "| rodada | resultado | tempo | categoria | pergunta | esperado |", "|---:|---|---:|---|---|---|"]
        for e in a["execucoes"]:
            md.append(f"| {e['rodada']} | {'✅' if e['correta'] else '❌'} | {e['segundos']} s | {e['cat']} | {e['pergunta']} | {e['esperado']} |")
        md.append("")
    if "roteador" in res:
        r = res["roteador"]
        md += ["## Roteador NVIDIA Nemotron Nano 3 30B", "",
               f"{r['perguntas']} perguntas rotuladas × {r['repeticoes']} repetições. **Acurácia: {r['acuracia_pct']} %**; "
               f"estabilidade (mesma rota nas {r['repeticoes']} vezes): {r['estabilidade_pct']} %; "
               f"classificações indevidas como fora de escopo: {r['recusas_indevidas']}; "
               f"perguntas de dados/documentos que iriam para um modelo **sem ferramentas**: "
               f"{r['respondidas_sem_ferramentas_indevidamente']} de {r['perguntas'] * r['repeticoes']}; "
               f"latência média {r['latencia_s']['media']} s (p90 {r['latencia_s']['p90']} s).", "",
               "Matriz (linhas = rota esperada, colunas = rota obtida):", ""]
        cols = ["conversa", "dados", "documentos", "misto", "fora_escopo"]
        md += ["| esperada \\ obtida | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
        for esp, cont in r["confusao"].items():
            md.append(f"| {esp} | " + " | ".join(str(cont.get(c, 0)) for c in cols) + " |")
        md += ["", "| pergunta | aceitas | obtidas |", "|---|---|---|"]
        for g in r["registros"]:
            marca = "" if g["acertos"] == len(g["obtidas"]) else " ⚠️"
            md.append(f"| {g['pergunta']}{marca} | {', '.join(g['aceitas'])} | {', '.join(g['obtidas'])} |")
    return "\n".join(md) + "\n"


def main_cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeticoes", type=int, default=2)
    ap.add_argument("--so-roteador", action="store_true")
    a = ap.parse_args()
    anterior = SAIDA / "flexia.json"
    res = json.loads(anterior.read_text(encoding="utf-8")) if a.so_roteador and anterior.exists() else {}
    res["roteador"] = roteador()
    print(f"roteador: acurácia {res['roteador']['acuracia_pct']} %, estabilidade {res['roteador']['estabilidade_pct']} %", flush=True)
    if not a.so_roteador:
        res["respostas"] = asyncio.run(ponta_a_ponta(a.repeticoes))
        print(f"respostas: acurácia {res['respostas']['acuracia_pct']} % {res['respostas']['por_categoria']}", flush=True)
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "flexia.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / "flexia.md").write_text(relatorio(res), encoding="utf-8")


if __name__ == "__main__":
    main_cli()
