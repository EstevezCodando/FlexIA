"""Avaliação independente da previsão D+1 de corte energético (ENE) do Nordeste, 2026.

Fonte: analytics_previsao_ene_ne_2026 (modelo da equipe: HistGradientBoosting treinado com dados
até 31/12/2025; previsão para 2026, fora da amostra) e analytics_gabarito_ene_2026.

Métodos comparados:
  modelo        previsão da equipe
  climatologia  média histórica por mês/semana/patamar (coluna clima_ne)
  persistencia  mesmo patamar do dia anterior (t-24 h) — otimista: em operação o dia D ainda não
                terminou quando se prevê D+1
  persistencia_realista  previsão emitida às 12h de D: manhã de D (t-24 h) e tarde de D-1 (t-48 h)
  semanal       mesmo patamar 7 dias antes (t-168 h)

Métricas:
  regressão      MAE, RMSE, viés, WAPE, R², correlação, MAE só nos patamares com corte
  binária        por limiar (200/500/1000/2000 MWmed): matriz de confusão, acurácia, precisão,
                 revocação, especificidade, F1, acurácia balanceada
  sinal 3 níveis VERMELHO < 200 <= AMARELO < 1000 <= VERDE (limiares de ev/sinal.py da equipe):
                 matriz 3x3, acurácia, precisão/revocação/F1 por nível, F1 macro, kappa de Cohen
  energia diária, hora de pico, por mês

Saída: avaliacao/resultados/previsao.json e avaliacao/resultados/previsao.md
"""
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

BASE = Path(__file__).resolve().parent.parent
LAKE = BASE / "out" / "lake" / "analytics"
PREV = (LAKE / "analytics_previsao_ene_ne_2026" / "*.parquet").as_posix()
GAB = (LAKE / "analytics_gabarito_ene_2026" / "*.parquet").as_posix()
SAIDA = BASE / "avaliacao" / "resultados"
LIMIARES = [200, 500, 1000, 2000]
NIVEIS = [("VERMELHO", None, 200), ("AMARELO", 200, 1000), ("VERDE", 1000, None)]
METODOS = [("modelo", "previsto"), ("climatologia", "clima_ne"), ("persistencia_d1", "d1"),
           ("persistencia_realista", "d1r"), ("semanal_d7", "d7")]
FILTRO = "d7 IS NOT NULL"  # mesma base para todos os métodos (exclui a 1ª semana)

con = duckdb.connect()
con.execute(f"""
CREATE VIEW p AS
SELECT din_instante, real_ne, previsto, clima_ne,
       lag(real_ne, 48)  OVER (ORDER BY din_instante) AS d1,
       lag(real_ne, 336) OVER (ORDER BY din_instante) AS d7,
       -- previsão emitida ao meio-dia de D: manhã de D já observada, tarde de D ainda não
       CASE WHEN hour(din_instante) < 12 THEN lag(real_ne, 48) OVER (ORDER BY din_instante)
            ELSE lag(real_ne, 96) OVER (ORDER BY din_instante) END AS d1r
FROM read_parquet('{PREV}')
""")


def um(sql: str):
    return con.execute(sql).fetchone()


def r(x, n=1):
    return None if x is None else round(float(x), n)


def regressao(col: str) -> dict:
    mae, rmse, vies, wape, corr, r2, mae_pos = um(f"""
        SELECT avg(abs(real_ne - {col})), sqrt(avg(pow(real_ne - {col}, 2))), avg({col} - real_ne),
               sum(abs(real_ne - {col})) / sum(real_ne) * 100, corr(real_ne, {col}),
               1 - sum(pow(real_ne - {col}, 2)) / sum(pow(real_ne - (SELECT avg(real_ne) FROM p WHERE {FILTRO}), 2)),
               avg(abs(real_ne - {col})) FILTER (WHERE real_ne > 0)
        FROM p WHERE {FILTRO}""")
    return {"mae_mw": r(mae), "rmse_mw": r(rmse), "vies_mw": r(vies), "wape_pct": r(wape), "r2": r(r2, 3),
            "correlacao": r(corr, 3), "mae_quando_ha_corte_mw": r(mae_pos)}


def binaria(col: str, lim: float) -> dict:
    vp, fp, fn, vn = um(f"""
        SELECT count(*) FILTER (WHERE {col} >= {lim} AND real_ne >= {lim}),
               count(*) FILTER (WHERE {col} >= {lim} AND real_ne <  {lim}),
               count(*) FILTER (WHERE {col} <  {lim} AND real_ne >= {lim}),
               count(*) FILTER (WHERE {col} <  {lim} AND real_ne <  {lim})
        FROM p WHERE {FILTRO}""")
    prec = vp / (vp + fp) if vp + fp else 0
    rev = vp / (vp + fn) if vp + fn else 0
    esp = vn / (vn + fp) if vn + fp else 0
    return {"vp": vp, "fp": fp, "fn": fn, "vn": vn,
            "acuracia_pct": r((vp + vn) / (vp + fp + fn + vn) * 100),
            "precisao_pct": r(prec * 100), "revocacao_pct": r(rev * 100), "especificidade_pct": r(esp * 100),
            "f1_pct": r(2 * prec * rev / (prec + rev) * 100 if prec + rev else 0),
            "acuracia_balanceada_pct": r((rev + esp) / 2 * 100),
            "prevalencia_pct": r((vp + fn) / (vp + fp + fn + vn) * 100)}


def nivel_sql(col: str) -> str:
    return f"CASE WHEN {col} >= 1000 THEN 'VERDE' WHEN {col} >= 200 THEN 'AMARELO' ELSE 'VERMELHO' END"


def tres_niveis(col: str) -> dict:
    linhas = con.execute(f"""
        SELECT {nivel_sql('real_ne')} AS real, {nivel_sql(col)} AS prev, count(*)
        FROM p WHERE {FILTRO} GROUP BY 1, 2""").fetchall()
    nomes = [n for n, _, _ in NIVEIS]
    m = {a: {b: 0 for b in nomes} for a in nomes}
    for real, prev, n in linhas:
        m[real][prev] = n
    total = sum(n for _, _, n in linhas)
    acertos = sum(m[n][n] for n in nomes)
    por_nivel, f1s = {}, []
    for n in nomes:
        vp = m[n][n]
        prev_n = sum(m[a][n] for a in nomes)
        real_n = sum(m[n].values())
        prec = vp / prev_n if prev_n else 0
        rev = vp / real_n if real_n else 0
        f1 = 2 * prec * rev / (prec + rev) if prec + rev else 0
        f1s.append(f1)
        por_nivel[n] = {"precisao_pct": r(prec * 100), "revocacao_pct": r(rev * 100), "f1_pct": r(f1 * 100),
                        "patamares_reais": real_n}
    po = acertos / total
    pe = sum(sum(m[n].values()) * sum(m[a][n] for a in nomes) for n in nomes) / total ** 2
    return {"matriz_real_x_previsto": m, "acuracia_pct": r(po * 100), "f1_macro_pct": r(sum(f1s) / 3 * 100),
            "kappa_cohen": r((po - pe) / (1 - pe), 3), "por_nivel": por_nivel}


res = {"cobertura": dict(zip(["patamares", "inicio", "fim"],
                             um("SELECT count(*), min(din_instante)::VARCHAR, max(din_instante)::VARCHAR FROM p"))),
       "patamares_avaliados": um(f"SELECT count(*) FROM p WHERE {FILTRO}")[0],
       "conferencia_real_vs_gabarito_max_dif": um(f"""
           SELECT max(abs(p.real_ne - g.ene_ne)) FROM p JOIN read_parquet('{GAB}') g USING (din_instante)""")[0]}
res["regressao"] = {nome: regressao(col) for nome, col in METODOS}
res["ganho_mae_modelo_pct"] = {k: r((1 - res["regressao"]["modelo"]["mae_mw"] / res["regressao"][k]["mae_mw"]) * 100)
                               for k, _ in METODOS[1:]}
res["binaria"] = {str(lim): {nome: binaria(col, lim) for nome, col in METODOS} for lim in LIMIARES}
res["sinal_3_niveis"] = {nome: tres_niveis(col) for nome, col in METODOS}

d = um("""
    WITH d AS (SELECT date_trunc('day', din_instante) dia, sum(real_ne) * 0.5 real_mwh, sum(previsto) * 0.5 prev_mwh,
                      sum(clima_ne) * 0.5 clima_mwh FROM p GROUP BY 1)
    SELECT count(*), avg(abs(real_mwh - prev_mwh)), avg(abs(real_mwh - clima_mwh)),
           sum(abs(real_mwh - prev_mwh)) / sum(real_mwh) * 100, corr(real_mwh, prev_mwh), avg(real_mwh),
           1 - sum(pow(real_mwh - prev_mwh, 2)) / sum(pow(real_mwh - (SELECT avg(real_mwh) FROM d), 2))
    FROM d""")
res["energia_diaria"] = {"dias": d[0], "mae_modelo_mwh": r(d[1], 0), "mae_climatologia_mwh": r(d[2], 0),
                         "wape_modelo_pct": r(d[3]), "correlacao": r(d[4], 3), "r2": r(d[6], 3),
                         "media_real_mwh_dia": r(d[5], 0)}
t = um("""
    WITH h AS (SELECT date_trunc('day', din_instante) dia, hour(din_instante) hora, sum(real_ne) r, sum(previsto) pr
               FROM p GROUP BY 1, 2),
         k AS (SELECT dia, arg_max(hora, r) h_real, arg_max(hora, pr) h_prev, max(r) mr FROM h GROUP BY 1)
    SELECT count(*) FILTER (WHERE mr > 0), count(*) FILTER (WHERE mr > 0 AND h_real = h_prev),
           count(*) FILTER (WHERE mr > 0 AND abs(h_real - h_prev) <= 1),
           count(*) FILTER (WHERE mr > 0 AND abs(h_real - h_prev) <= 2) FROM k""")
res["hora_de_pico"] = {"dias_com_corte": t[0], "exata_pct": r(t[1] / t[0] * 100),
                       "mais_menos_1h_pct": r(t[2] / t[0] * 100), "mais_menos_2h_pct": r(t[3] / t[0] * 100)}
res["por_mes"] = [{"mes": m, "mae_modelo_mw": r(a, 0), "mae_climatologia_mw": r(b, 0), "real_medio_mw": r(c, 0)}
                  for m, a, b, c in con.execute("""
                      SELECT month(din_instante), avg(abs(real_ne - previsto)), avg(abs(real_ne - clima_ne)), avg(real_ne)
                      FROM p GROUP BY 1 ORDER BY 1""").fetchall()]

SAIDA.mkdir(parents=True, exist_ok=True)
(SAIDA / "previsao.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- relatório Markdown
def fmt(x, casas: int = 1) -> str:
    """Número no padrão brasileiro. casas=3 para R², correlação e kappa."""
    if x is None:
        return "—"
    if isinstance(x, int) or (casas == 1 and float(x).is_integer() and abs(x) >= 100):
        return f"{int(x):,}".replace(",", ".")
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


nomes = {"modelo": "**modelo**", "climatologia": "climatologia", "persistencia_d1": "persistência D-1 (otimista)", "persistencia_realista": "persistência realista (emitida às 12h de D)",
         "semanal_d7": "semanal D-7"}
md = [f"# Resultados — previsão D+1 de corte ENE no Nordeste",
      "",
      f"Gerado por `avaliacao/avaliar_previsao.py`. Período: {res['cobertura']['inicio'][:10]} a "
      f"{res['cobertura']['fim'][:10]} ({fmt(res['cobertura']['patamares'])} patamares de 30 min; "
      f"{fmt(res['patamares_avaliados'])} avaliados, excluída a 1ª semana para todos os métodos terem comparação).",
      "",
      "## Regressão (MWmed por patamar)", "",
      "| método | MAE | RMSE | viés | WAPE % | R² | correlação | MAE quando há corte |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
for k, v in res["regressao"].items():
    md.append(f"| {nomes[k]} | {fmt(v['mae_mw'])} | {fmt(v['rmse_mw'])} | {fmt(v['vies_mw'])} | {fmt(v['wape_pct'])} | "
              f"{fmt(v['r2'], 3)} | {fmt(v['correlacao'], 3)} | {fmt(v['mae_quando_ha_corte_mw'])} |")
g = res["ganho_mae_modelo_pct"]
md += ["", f"Redução de MAE do modelo: {fmt(g['climatologia'])} % vs climatologia, {fmt(g['persistencia_d1'])} % vs "
           f"persistência D-1 (otimista), {fmt(g['persistencia_realista'])} % vs persistência realista, "
           f"{fmt(g['semanal_d7'])} % vs semanal D-7.", "",
       "## Classificação binária: \"haverá corte ≥ limiar neste patamar?\"", ""]
for lim in LIMIARES:
    b = res["binaria"][str(lim)]
    md += [f"### Limiar {fmt(lim)} MWmed (prevalência real: {fmt(b['modelo']['prevalencia_pct'])} % dos patamares)", "",
           "| método | VP | FP | FN | VN | acurácia % | precisão % | revocação % | especificidade % | F1 % | acurácia balanceada % |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, v in b.items():
        md.append(f"| {nomes[k]} | {fmt(v['vp'])} | {fmt(v['fp'])} | {fmt(v['fn'])} | {fmt(v['vn'])} | {fmt(v['acuracia_pct'])} | "
                  f"{fmt(v['precisao_pct'])} | {fmt(v['revocacao_pct'])} | {fmt(v['especificidade_pct'])} | {fmt(v['f1_pct'])} | "
                  f"{fmt(v['acuracia_balanceada_pct'])} |")
    md.append("")
md += ["## Sinal de três níveis (VERMELHO < 200 ≤ AMARELO < 1.000 ≤ VERDE, limiares da equipe)", "",
       "| método | acurácia % | F1 macro % | kappa | F1 VERMELHO % | F1 AMARELO % | F1 VERDE % |",
       "|---|---:|---:|---:|---:|---:|---:|"]
for k, v in res["sinal_3_niveis"].items():
    pn = v["por_nivel"]
    md.append(f"| {nomes[k]} | {fmt(v['acuracia_pct'])} | {fmt(v['f1_macro_pct'])} | {fmt(v['kappa_cohen'], 3)} | "
              f"{fmt(pn['VERMELHO']['f1_pct'])} | {fmt(pn['AMARELO']['f1_pct'])} | {fmt(pn['VERDE']['f1_pct'])} |")
mm = res["sinal_3_niveis"]["modelo"]
md += ["", "Matriz de confusão do modelo (linhas = real, colunas = previsto):", "",
       "| real \\ previsto | VERMELHO | AMARELO | VERDE | precisão % | revocação % |", "|---|---:|---:|---:|---:|---:|"]
for n in ("VERMELHO", "AMARELO", "VERDE"):
    lin = mm["matriz_real_x_previsto"][n]
    md.append(f"| {n} | {fmt(lin['VERMELHO'])} | {fmt(lin['AMARELO'])} | {fmt(lin['VERDE'])} | "
              f"{fmt(mm['por_nivel'][n]['precisao_pct'])} | {fmt(mm['por_nivel'][n]['revocacao_pct'])} |")
e, h = res["energia_diaria"], res["hora_de_pico"]
md += ["", "## Energia do dia e hora de pico", "",
       f"- Energia diária ({e['dias']} dias): MAE {fmt(e['mae_modelo_mwh'])} MWh/dia (climatologia {fmt(e['mae_climatologia_mwh'])}), "
       f"WAPE {fmt(e['wape_modelo_pct'])} %, R² {fmt(e['r2'], 3)}, correlação {fmt(e['correlacao'], 3)}; média real {fmt(e['media_real_mwh_dia'])} MWh/dia.",
       f"- Hora de maior corte ({h['dias_com_corte']} dias com corte): exata em {fmt(h['exata_pct'])} %, "
       f"±1 h em {fmt(h['mais_menos_1h_pct'])} %, ±2 h em {fmt(h['mais_menos_2h_pct'])} %.",
       "", "## Por mês (MAE em MWmed)", "", "| mês | modelo | climatologia | corte real médio |", "|---|---:|---:|---:|"]
for m in res["por_mes"]:
    md.append(f"| {m['mes']:02d}/2026 | {fmt(m['mae_modelo_mw'])} | {fmt(m['mae_climatologia_mw'])} | {fmt(m['real_medio_mw'])} |")
(SAIDA / "previsao.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(md))
