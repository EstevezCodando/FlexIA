"""Resumo do lake local: tabelas e linhas por fonte (prefixo do nome) e tamanho total em Parquet."""
import pathlib

import duckdb

BASE = pathlib.Path(__file__).resolve().parent.parent / "out" / "lake"
por = {}
for camada in ("curated", "analytics"):
    for d in sorted((BASE / camada).iterdir()):
        n = duckdb.sql(f"select count(*) from read_parquet('{d.as_posix()}/**/*.parquet')").fetchone()[0]
        t, l = por.get(d.name.split("_")[0], (0, 0))
        por[d.name.split("_")[0]] = (t + 1, l + n)
for fonte, (t, l) in sorted(por.items(), key=lambda kv: -kv[1][1]):
    print(f"{fonte:10s} {t:4d} tabelas {l:>14,} linhas")
print(f"TOTAL      {sum(t for t, _ in por.values()):4d} tabelas {sum(l for _, l in por.values()):>14,} linhas")
print(f"Parquet: {sum(f.stat().st_size for f in BASE.rglob('*.parquet')) / 1e9:.2f} GB")
