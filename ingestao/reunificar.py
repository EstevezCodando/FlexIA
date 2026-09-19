"""Regera uma tabela curada a partir dos arquivos já baixados em out/fontes, sem rede e sem Bedrock,
preservando as descrições de coluna de out/metadados (útil após corrigir regras de ingestao/unificar.py).

Uso: python ingestao/reunificar.py <tabela> <pasta em out/fontes> [padrão glob]
Ex.: python ingestao/reunificar.py aneel_samp_balanco aneel/samp-balanco "*.parquet"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ckan import opcoes_csv, para_utf8  # noqa: E402
from unificar import unificar  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
tabela, pasta = sys.argv[1], BASE / "out" / "fontes" / sys.argv[2]
padrao = sys.argv[3] if len(sys.argv) > 3 else "*"
arquivos = sorted(p for p in pasta.glob(padrao) if p.suffix.lower() in (".csv", ".parquet") and ".utf8." not in p.name)
arquivos = [para_utf8(p) if p.suffix.lower() == ".csv" else p for p in arquivos]
opcao = opcoes_csv(next(p for p in arquivos if p.suffix.lower() == ".csv")) if any(p.suffix.lower() == ".csv" for p in arquivos) else ""
resumo = unificar(arquivos, BASE / "out" / "lake" / "curated" / tabela, csv_opcoes=opcao)
meta_p = BASE / "out" / "metadados" / f"{tabela}.json"
meta = json.loads(meta_p.read_text(encoding="utf-8"))
meta.update({k: resumo[k] for k in ("linhas", "periodo", "coluna_tempo", "particionada_por_ano")})
meta["colunas"] = {c: meta["colunas"].get(c, "") for c in resumo["colunas"]}
meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({"tabela": tabela, **{k: resumo[k] for k in ("linhas", "periodo", "coluna_tempo", "particionada_por_ano")}},
                 ensure_ascii=False))
