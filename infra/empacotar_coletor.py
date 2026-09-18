"""Gera out/flexia-coletor.zip para AWS Lambda (python3.13, x86_64).

Instala o Cavuca (do clone local, CAVUCA_DIR) e as dependências em wheels manylinux e remove os
drivers Node do Playwright/Patchright: o coletor só usa as requisições HTTP do Cavuca e nunca abre
navegador, então o pacote cabe no limite de 250 MB da Lambda.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BUILD = BASE / "out" / "lambda_build"
ZIP = BASE / "out" / "flexia-coletor.zip"
CAVUCA = Path(os.environ["CAVUCA_DIR"])
PLATAFORMA = ["--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_17_x86_64",
              "--platform", "manylinux_2_28_x86_64", "--python-version", "3.13", "--only-binary=:all:"]
DEPENDENCIAS = [
    # núcleo do Cavuca + extra [fetchers] + markdownify (extra [rag]); boto3 já vem no runtime da Lambda
    "lxml>=6.1.1", "cssselect>=1.5.0", "orjson>=3.11.8", "tld>=0.13.2", "w3lib>=2.4.1", "typing_extensions",
    "click>=8.3.0", "curl_cffi>=0.16.1", "playwright>=1.62.0", "patchright>=1.62.1", "browserforge>=1.2.4",
    "apify-fingerprint-datapoints>=0.15.0", "msgspec>=0.21.1", "anyio>=4.14.0", "markdownify", "pypdf",
]


def pip(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--target", str(BUILD), *args], check=True)


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)
    pip(*PLATAFORMA, *DEPENDENCIAS)
    pip("--no-deps", str(CAVUCA))
    for pacote in ("playwright", "patchright"):
        shutil.rmtree(BUILD / pacote / "driver", ignore_errors=True)
    for lixo in list(BUILD.rglob("__pycache__")) + list(BUILD.glob("*.dist-info/RECORD")):
        shutil.rmtree(lixo, ignore_errors=True) if lixo.is_dir() else lixo.unlink()
    for arq in ("coletor.py", "fontes.py", "indexar.py", "lambda_handler.py"):
        shutil.copy(BASE / "coleta" / arq, BUILD / arq)

    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in BUILD.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(BUILD).as_posix())
    bruto = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    print(f"{ZIP}: {ZIP.stat().st_size/1e6:.1f} MB zip, {bruto/1e6:.1f} MB descompactado (limite 250 MB)")


if __name__ == "__main__":
    main()
