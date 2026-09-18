"""Avaliação independente da previsão D+1 de corte energético (ENE) do Nordeste, 2026.

Fonte: analytics_previsao_ene_ne_2026 (saída do modelo da equipe: HistGradientBoosting treinado
com dados até 31/12/2025, previsão para 2026 fora da amostra) e analytics_gabarito_ene_2026.

Métricas contra três comparadores ingênuos:
  climatologia  média histórica por mês/semana/patamar (coluna clima_ne, do próprio modelo)
  persistência  mesmo patamar do dia anterior (t-24 h)  — otimista: em operação o dia D ainda
                não terminou quando se prevê D+1
  semanal       mesmo patamar 7 dias antes (t-168 h)
Saída: out/avaliacao_previsao.json e texto no terminal.
"""
import json
from pathlib import Path

import duckdb

BASE = Path(__file__).resolve().parent.parent
LAKE = BASE / "out" / "lake" / "analytics"
PREV = (LAKE / "analytics_previsao_ene_ne_2026" / "*.parquet").as_posix()
GAB = (LAKE / "analytics_gabarito_ene_2026" / "*.parquet").as_posix()
LIMIAR_MW = 500  # "há corte relevante" no patamar

con = duckdb.connect()
con.execute(f"""
CREATE VIEW p AS
SELECT din_instante, real_ne, previsto, clima_ne,
       lag(real_ne, 48)  OVER (ORDER BY din_instante) AS d1,
       lag(real_ne, 336) OVER (ORDER BY din_instante) AS d7
FROM read_parquet('{PREV}')
""")

res = {}
res["cobertura"] = dict(zip(["patamares", "inicio", "fim"],
                            con.execute("SELECT count(*), min(din_instante)::VARCHAR, max(din_instante)::VARCHAR FROM p").fetchone()))
res["conferencia_gabarito"] = con.execute(f"""
    SELECT max(abs(p.real_ne - g.ene_ne)) FROM p JOIN read_parquet('{GAB}') g USING (din_instante)""").fetchone()[0]


def metricas(col: str, filtro: str = "d7 IS NOT NULL") -> dict:
    mae, rmse, vies, wape, corr = con.execute(f"""
        SELECT avg(abs(real_ne - {col})), sqrt(avg(pow(real_ne - {col}, 2))), avg({col} - real_ne),
               sum(abs(real_ne - {col})) / sum(real_ne) * 100, corr(real_ne, {col})
        FROM p WHERE {filtro}""").fetchone()
    return {"mae_mw": round(mae, 1), "rmse_mw": round(rmse, 1), "vies_mw": round(vies, 1),
            "wape_pct": round(wape, 1), "correlacao": round(corr, 3)}


res["patamar_30min"] = {nome: metricas(col) for nome, col in
                        [("modelo", "previsto"), ("climatologia", "clima_ne"), ("persistencia_d1", "d1"), ("semanal_d7", "d7")]}
m = res["patamar_30min"]
res["ganho_mae_pct"] = {k: round((1 - m["modelo"]["mae_mw"] / m[k]["mae_mw"]) * 100, 1)
                        for k in ("climatologia", "persistencia_d1", "semanal_d7")}

# Energia diária (o que importa para planejar recarga/armazenamento num dia)
dia = con.execute("""
    WITH d AS (SELECT date_trunc('day', din_instante) dia, sum(real_ne) * 0.5 real_mwh, sum(previsto) * 0.5 prev_mwh,
                      sum(clima_ne) * 0.5 clima_mwh FROM p GROUP BY 1)
    SELECT count(*), avg(abs(real_mwh - prev_mwh)), avg(abs(real_mwh - clima_mwh)),
           sum(abs(real_mwh - prev_mwh)) / sum(real_mwh) * 100, corr(real_mwh, prev_mwh), avg(real_mwh)
    FROM d""").fetchone()
res["energia_diaria"] = {"dias": dia[0], "mae_modelo_mwh": round(dia[1]), "mae_climatologia_mwh": round(dia[2]),
                         "wape_modelo_pct": round(dia[3], 1), "correlacao": round(dia[4], 3),
                         "media_real_mwh_dia": round(dia[5])}

# Acerto como classificador: "vai haver corte > 500 MWmed neste patamar?"
vp, fp, fn, vn = con.execute(f"""
    SELECT count(*) FILTER (WHERE previsto >= {LIMIAR_MW} AND real_ne >= {LIMIAR_MW}),
           count(*) FILTER (WHERE previsto >= {LIMIAR_MW} AND real_ne <  {LIMIAR_MW}),
           count(*) FILTER (WHERE previsto <  {LIMIAR_MW} AND real_ne >= {LIMIAR_MW}),
           count(*) FILTER (WHERE previsto <  {LIMIAR_MW} AND real_ne <  {LIMIAR_MW}) FROM p""").fetchone()
res["classificacao_corte_500mw"] = {
    "precisao_pct": round(vp / (vp + fp) * 100, 1), "revocacao_pct": round(vp / (vp + fn) * 100, 1),
    "acuracia_pct": round((vp + vn) / (vp + fp + fn + vn) * 100, 1),
    "patamares_com_corte_real_pct": round((vp + fn) / (vp + fp + fn + vn) * 100, 1)}

# Ranking das melhores horas do dia (uso do agendador): a hora de maior corte previsto
# coincide com a hora de maior corte real?
top = con.execute("""
    WITH h AS (SELECT date_trunc('day', din_instante) dia, hour(din_instante) hora,
                      sum(real_ne) r, sum(previsto) pr FROM p GROUP BY 1, 2),
         k AS (SELECT dia, arg_max(hora, r) h_real, arg_max(hora, pr) h_prev, max(r) mr FROM h GROUP BY 1)
    SELECT count(*) FILTER (WHERE mr > 0), count(*) FILTER (WHERE mr > 0 AND abs(h_real - h_prev) <= 1) FROM k""").fetchone()
res["hora_de_pico_acertada_mais_menos_1h_pct"] = round(top[1] / top[0] * 100, 1) if top[0] else None

res["por_mes"] = [dict(zip(["mes", "mae_modelo", "mae_climatologia", "real_medio"], [r[0], round(r[1]), round(r[2]), round(r[3])]))
                  for r in con.execute("""SELECT month(din_instante), avg(abs(real_ne - previsto)), avg(abs(real_ne - clima_ne)),
                                                 avg(real_ne) FROM p GROUP BY 1 ORDER BY 1""").fetchall()]

(BASE / "out" / "avaliacao_previsao.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
