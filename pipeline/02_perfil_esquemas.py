"""Compara o esquema (colunas/tipos) de todos os arquivos de cada conjunto ONS.

Saída: out/esquemas.json — por conjunto, a lista de assinaturas distintas e quais arquivos têm cada uma.
"""
import json
import os
from collections import defaultdict
from pathlib import Path

import duckdb

ORIGEM = Path(os.environ.get("ORIGEM", r"C:\Hackathon_ONS")) / "data" / "raw" / "ons"
SAIDA = Path(__file__).resolve().parent.parent / "out" / "esquemas.json"


def leitor(p: Path) -> str:
    if p.suffix == ".parquet":
        return f"read_parquet('{p.as_posix()}')"
    return f"read_csv('{p.as_posix()}', delim=';', header=true, all_varchar=false, sample_size=-1)"


def main() -> None:
    con = duckdb.connect()
    resultado = {}
    for ds in sorted(d for d in ORIGEM.iterdir() if d.is_dir()):
        assinaturas = defaultdict(list)
        linhas = 0
        for p in sorted(ds.iterdir()):
            if p.suffix not in (".parquet", ".csv"):
                continue
            cols = con.sql(f"describe select * from {leitor(p)}").fetchall()
            assinaturas[json.dumps([[c[0].lower(), c[1]] for c in cols])].append(p.name)
            linhas += con.sql(f"select count(*) from {leitor(p)}").fetchone()[0]
        resultado[ds.name] = {
            "linhas": linhas,
            "variantes": [{"colunas": json.loads(k), "arquivos": v} for k, v in assinaturas.items()],
        }
        print(f"{ds.name:40s} linhas={linhas:>12,}  variantes_de_esquema={len(assinaturas)}")
    SAIDA.write_text(json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
