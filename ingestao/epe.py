"""Ingestão das planilhas de dados abertos da EPE (https://www.epe.gov.br/pt/publicacoes-dados-abertos/dados-abertos).

Cada aba tabular vira uma tabela; abas de tabela dinâmica ("ANALISE ...") são ignoradas. A coluna
Data em AAAAMMDD vira DATE; DataExcel (duplicata) é descartada. Tabelas do PDE 2035 são PROJEÇÕES e
são descritas assim no catálogo. A EPE não publica dicionário de dados: descrições de coluna são
inferidas (prefixo "[inferido]").

Uso: python ingestao/epe.py [--baixar]
"""
import json
import sys
import time
from pathlib import Path

import curl_cffi.requests as cr
import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402  (.env da raiz do projeto)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ckan import descrever_colunas  # noqa: E402
from unificar import nome_coluna, unificar  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; FlexIA-Coletor/1.0; +hackathon ONS)"}
RAIZ = "https://www.epe.gov.br/sites-pt/publicacoes-dados-abertos/dados-abertos/Documents/"
PAGINA = "https://www.epe.gov.br/pt/publicacoes-dados-abertos/dados-abertos/"

# arquivo -> [(aba, tabela, tema, descrição)]
PLANILHAS = {
    "Dados_abertos_Consumo_Mensal.xlsx": [
        ("CONSUMO E NUMCONS SAM", "epe_consumo_mensal_regiao", "carga",
         "EPE — consumo mensal de energia elétrica (MWh) e número de consumidores por região, sistema, classe e tipo de consumidor (cativo/livre)."),
        ("CONSUMO E NUMCONS SAM UF", "epe_consumo_mensal_uf", "carga",
         "EPE — consumo mensal de energia elétrica (MWh) e número de consumidores por UF, região, sistema, classe e tipo de consumidor."),
        ("SETOR INDUSTRIAL POR RG", "epe_consumo_industrial_regiao", "carga",
         "EPE — consumo mensal de energia elétrica da indústria (MWh) por setor industrial (CNAE) e região."),
        ("SETOR INDUSTRIAL POR UF", "epe_consumo_industrial_uf", "carga",
         "EPE — consumo mensal de energia elétrica da indústria (MWh) por setor industrial (CNAE) e UF."),
        ("CONSUMO_BEN_RG_1970-1989", "epe_consumo_historico_1970_1989", "carga",
         "EPE — série histórica anual de consumo de energia elétrica por região e classe, 1970–1989 (Balanço Energético Nacional)."),
        ("CONSUMO_ELETROBRAS_1990-2003", "epe_consumo_historico_1990_2003", "carga",
         "EPE — série histórica mensal de consumo de energia elétrica e consumidores por região e classe, 1990–2003 (base Eletrobras)."),
    ],
    "Dados_abertos_Mercado_Distribuicao.xlsx": [
        ("MERCADO DISTRIBUICAO", "epe_mercado_distribuicao_regiao", "mercado",
         "EPE — mercado de distribuição por região, sistema, classe e tipo de consumidor: consumo, energia injetada por MMGD e perdas (GWh); histórico e projeção (coluna tipovalor)."),
        ("MERCADO DISTRIBUICAO UF", "epe_mercado_distribuicao_uf", "mercado",
         "EPE — mercado de distribuição por UF: consumo, energia injetada por MMGD e perdas (GWh); histórico e projeção (coluna tipovalor)."),
    ],
    "Dados_brutos.xlsx": [
        ("Sheet1", "epe_anuario_consumo_detalhado", "carga",
         "EPE — dados brutos do Anuário Estatístico de Energia Elétrica: consumo mensal por UF, sistema, tipo de consumidor, setor econômico, nível de tensão e faixa de consumo."),
    ],
    "PDE_2035_Painel_de_Resultados_Dados_Abertos.xlsx": [
        ("Matrizes", "epe_pde2035_matrizes", "planejamento", "EPE — PROJEÇÃO do Plano Decenal de Expansão de Energia 2035: matrizes energéticas (mil tep) por ano, fonte e componente."),
        ("Geração eletrica", "epe_pde2035_geracao", "planejamento", "EPE — PROJEÇÃO do PDE 2035: geração elétrica (TWh) por fonte e tipo (centralizada, GD, autoprodução)."),
        ("Capacidade instalada total", "epe_pde2035_capacidade", "planejamento", "EPE — PROJEÇÃO do PDE 2035: capacidade instalada (GW) por fonte e tipo (centralizada, GD, autoprodução)."),
        ("Investimento por setor", "epe_pde2035_investimento", "planejamento", "EPE — PROJEÇÃO do PDE 2035: investimentos (R$ bilhões) por setor e segmento no decênio."),
        ("Macroeconomia", "epe_pde2035_macroeconomia", "planejamento", "EPE — PROJEÇÃO do PDE 2035: premissas macroeconômicas e demográficas por ano."),
        ("Emissões", "epe_pde2035_emissoes", "planejamento", "EPE — PROJEÇÃO do PDE 2035: emissões de gases de efeito estufa (MtCO2eq) por setor."),
        ("Expansão incremental", "epe_pde2035_expansao", "planejamento", "EPE — PROJEÇÃO do PDE 2035: expansão incremental de capacidade (MW) por tipo de expansão e fonte."),
    ],
}


def baixar(pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in PLANILHAS:
        url = RAIZ + nome.replace("PDE_2035_Painel_de_Resultados_Dados_Abertos", "PDE%202035_Painel%20de%20Resultados_Dados%20Abertos") \
            .replace("Dados_brutos", "Dados%20brutos")
        r = cr.get(url, timeout=180, impersonate="chrome", headers=UA)
        r.raise_for_status()
        (pasta / nome).write_bytes(r.content)
        time.sleep(3)


def aba_para_parquet(xlsx: Path, aba: str, destino: Path) -> None:
    df = pd.read_excel(xlsx, sheet_name=aba, engine="openpyxl")
    df.columns = [nome_coluna(str(c)) for c in df.columns]
    df = df.drop(columns=[c for c in df.columns if c == "dataexcel"], errors="ignore")
    df = df.dropna(how="all")
    if "data" in df.columns:
        s = pd.to_numeric(df["data"], errors="coerce")
        if s.dropna().between(19000101, 21001231).all() and s.notna().any():
            df["data"] = pd.to_datetime(s.astype("Int64").astype(str), format="%Y%m%d", errors="coerce").dt.date
        elif s.dropna().between(1900, 2100).all() and s.notna().any():
            df = df.rename(columns={"data": "ano"})
    for c in df.columns:  # texto com espaços de recuo (ex.: '    EXPORTAÇÃO')
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
    con = duckdb.connect()
    con.register("df", df)
    con.execute(f"COPY df TO '{destino.as_posix()}' (FORMAT parquet)")


def main() -> None:
    pasta = BASE / "out" / "fontes" / "epe"
    if "--baixar" in sys.argv or not all((pasta / n).exists() for n in PLANILHAS):
        baixar(pasta)
    for arquivo, abas in PLANILHAS.items():
        for aba, tabela, tema, descricao in abas:
            tmp = pasta / f"{tabela}.parquet"
            aba_para_parquet(pasta / arquivo, aba, tmp)
            resumo = unificar([tmp], BASE / "out" / "lake" / "curated" / tabela)
            colunas = list(resumo["colunas"])
            glob = (BASE / "out" / "lake" / "curated" / tabela).as_posix() + "/**/*.parquet"
            r = duckdb.sql(f"SELECT * FROM read_parquet('{glob}') LIMIT 1")
            amostra = dict(zip(r.columns, r.fetchone()))
            desc = descrever_colunas(colunas, descricao, tabela, oficial=False, amostra=amostra)
            meta = {"tabela": tabela, "fonte": "EPE", "tema": tema, "titulo": f"{arquivo} / {aba}",
                    "descricao": descricao, "origem": PAGINA,
                    "dicionario": "sem dicionário oficial: descrições [inferido] a partir do nome e da amostra",
                    "colunas": {c: desc.get(c, "") for c in colunas},
                    **{k: resumo[k] for k in ("linhas", "periodo", "coluna_tempo", "particionada_por_ano")},
                    "arquivos_fonte": 1}
            (BASE / "out" / "metadados").mkdir(parents=True, exist_ok=True)
            (BASE / "out" / "metadados" / f"{tabela}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                                                     encoding="utf-8")
            print(json.dumps({"tabela": tabela, "linhas": resumo["linhas"], "periodo": resumo["periodo"],
                              "colunas": len(colunas)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
