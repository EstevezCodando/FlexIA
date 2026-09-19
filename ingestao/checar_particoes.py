"""Roda em cada tabela particionada as consultas que o publicador faz, para achar a que quebra o DuckDB."""
import pathlib

import duckdb

BASE = pathlib.Path(__file__).resolve().parent.parent / "out" / "lake"
for camada in ("curated", "analytics"):
    for d in sorted((BASE / camada).iterdir()):
        if not any(p.is_dir() and p.name.startswith("ano=") for p in d.iterdir()):
            continue
        g = f"{d.as_posix()}/**/*.parquet"
        for sql in (f"describe select * from read_parquet('{g}', hive_partitioning=true)",
                    f"select min(ano), max(ano) from read_parquet('{g}', hive_partitioning=true)"):
            try:
                duckdb.sql(sql).fetchall()
            except Exception as e:  # noqa: BLE001
                print(f"ERRO {d.name}: {sql[:40]}... -> {str(e)[:100]}")
                esquemas = {}
                for f in sorted(d.rglob("*.parquet")):
                    cols = tuple(c[0] for c in duckdb.sql(f"describe select * from read_parquet('{f.as_posix()}', hive_partitioning=false)").fetchall())
                    esquemas.setdefault(cols, []).append(f.parent.name)
                for cols, anos in esquemas.items():
                    print(f"     {len(cols)} colunas em {anos[:5]}{'...' if len(anos) > 5 else ''}")
print("fim")
