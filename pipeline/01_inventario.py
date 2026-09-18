"""Inventaria C:\\Hackathon_ONS (somente leitura) e detecta arquivos duplicados por conteúdo.

Saída: out/inventario.csv com uma linha por arquivo, hash SHA-256 e o caminho canônico
do grupo de duplicatas. Hash só é calculado para arquivos cujo tamanho se repete.
"""
import csv
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path

ORIGEM = Path(os.environ.get("ORIGEM", r"C:\Hackathon_ONS"))
SAIDA = Path(__file__).resolve().parent.parent / "out" / "inventario.csv"
IGNORAR_DIRS = {".git", "node_modules", "__pycache__", ".venv"}

# Ordem de preferência para escolher o caminho canônico de um grupo duplicado.
PREFERENCIA = ["data/", "dados/ons/", "dados/rio_ev/", "dados/data/"]


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def prioridade(rel: str) -> tuple:
    for i, prefixo in enumerate(PREFERENCIA):
        if rel.startswith(prefixo):
            return (i, len(rel), rel)
    return (len(PREFERENCIA), len(rel), rel)


def main() -> None:
    arquivos = []
    for raiz, dirs, nomes in os.walk(ORIGEM):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIRS]
        for nome in nomes:
            p = Path(raiz) / nome
            arquivos.append((p, p.stat().st_size))

    por_tamanho = defaultdict(list)
    for p, tam in arquivos:
        por_tamanho[tam].append(p)

    hashes = {}
    candidatos = [p for grupo in por_tamanho.values() if len(grupo) > 1 for p in grupo]
    for i, p in enumerate(candidatos, 1):
        hashes[p] = sha256(p)
        if i % 500 == 0:
            print(f"  hash {i}/{len(candidatos)}", file=sys.stderr)

    grupos = defaultdict(list)
    for p, _ in arquivos:
        rel = p.relative_to(ORIGEM).as_posix()
        grupos[hashes.get(p, "unico:" + rel)].append(rel)

    canonico = {}
    for chave, rels in grupos.items():
        escolhido = min(rels, key=prioridade)
        for rel in rels:
            canonico[rel] = escolhido

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SAIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["caminho", "extensao", "bytes", "sha256", "canonico", "duplicado"])
        for p, tam in sorted(arquivos):
            rel = p.relative_to(ORIGEM).as_posix()
            w.writerow([rel, p.suffix.lower(), tam, hashes.get(p, ""), canonico[rel], rel != canonico[rel]])

    dup = [(p, t) for p, t in arquivos if p.relative_to(ORIGEM).as_posix() != canonico[p.relative_to(ORIGEM).as_posix()]]
    total = sum(t for _, t in arquivos)
    dup_bytes = sum(t for _, t in dup)
    print(f"arquivos: {len(arquivos)}  total: {total/1e9:.2f} GB")
    print(f"duplicados: {len(dup)}  ({dup_bytes/1e9:.2f} GB)  -> únicos: {len(arquivos)-len(dup)} ({(total-dup_bytes)/1e9:.2f} GB)")
    print(f"inventário: {SAIDA}")


if __name__ == "__main__":
    main()
