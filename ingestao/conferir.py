"""Confere tabelas curadas: esquema, período, amostra e colunas sem descrição.

Uso: python ingestao/conferir.py tabela [tabela ...]
"""
import json
import sys
from pathlib import Path

import duckdb

BASE = Path(__file__).resolve().parent.parent
for t in sys.argv[1:]:
    pasta = BASE / "out" / "lake" / "curated" / t
    glob = f"{pasta.as_posix()}/**/*.parquet"
    con = duckdb.connect()
    cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob}', hive_partitioning=true)").fetchall()
    meta_p = BASE / "out" / "metadados" / f"{t}.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"colunas": {}}
    print(f"\n== {t}  linhas={con.execute(f'SELECT count(*) FROM read_parquet({chr(39)}{glob}{chr(39)})').fetchone()[0]:,}")
    print("   ", meta.get("descricao", "")[:160])
    for c in cols:
        d = meta["colunas"].get(c[0], "")
        print(f"    {c[0]:38s} {c[1]:10s} {'' if d else '(SEM DESCRIÇÃO)'} {d[:70]}")
    print("    amostra:", con.execute(f"SELECT * FROM read_parquet('{glob}', hive_partitioning=true) LIMIT 1").fetchall())
