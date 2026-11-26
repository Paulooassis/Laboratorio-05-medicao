"""Valida os dados coletados pelo coleta_experimento.py antes da analise.

Regras de validacao (uma execucao e DESCARTADA se violar qualquer uma):

  V1  status da execucao diferente de "ok" (erro, vazao zero, erro de conexao...)
  V2  execucao de aquecimento (so serve para aquecer, nao entra na analise)
  V3  valor nulo em alguma metrica M1-M5
  V4  run_id duplicado (mantem a primeira ocorrencia)
  V5  tratamento + repeticao duplicado entre as validas (mantem a primeira)
  V6  valor fora do esperado:
        ops_s <= 0 | latencias <= 0 | p50 > p99 ou p99 > p99.9
        erros_conexao > 0 | mem_rss_mib <= 0
        cpu_medio_pct fora de [0, 100 x n de CPUs do servidor]
  V7  versao reportada pelo servidor diferente da versao do tratamento
  V8  GET com misses > 0 (a base nao foi populada corretamente)
  V9  menos amostras de CPU que metade da janela esperada
  V10 carga fixa (taxa > 0) com vazao fora de +-5% da taxa: a carga nao foi a
      planejada e a CPU deixa de ser comparavel entre os softwares

Coletas sem a coluna `taxa` (piloto) sao lidas como carga saturada (taxa 0).

Outliers NAO sao removidos (regra do plano de coleta): valores fora de
[Q1 - 1,5*IQR, Q3 + 1,5*IQR] dentro de cada tratamento sao apenas sinalizados na
coluna `outliers`, para discussao.

Saidas:
  data/processed/<coleta>_validado.csv   todas as linhas + valido, motivo, outliers
  results/<coleta>/validacao.json        resumo (total, validas, descartadas, motivos)
  results/<coleta>/validacao.md          o mesmo resumo em Markdown

Uso:
    python3 scripts/validacao_dados.py --coleta piloto
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
METRICAS = ["ops_s", "lat_p50_ms", "lat_p99_ms", "mem_rss_mib", "cpu_medio_pct"]
TRATAMENTO = ["software", "comando", "pipeline", "taxa"]
TOLERANCIA_TAXA = 0.05


def n_cpus(cpuset: str) -> int:
    total = 0
    for parte in cpuset.split(","):
        if "-" in parte:
            a, b = parte.split("-")
            total += int(b) - int(a) + 1
        elif parte:
            total += 1
    return total


def validar(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    params = meta.get("parametros", {})
    cpu_max = 100 * n_cpus(params.get("cpus_servidor", "0,4"))
    min_amostras = max(1, (params.get("duracao_s", 30) - 2) // 2)

    df = df.copy()
    df["taxa"] = df["taxa"].fillna(0).astype(int) if "taxa" in df else 0
    df["aquecimento"] = df["aquecimento"].astype(str).str.lower() == "true"
    motivos: list[list[str]] = [[] for _ in range(len(df))]

    def marcar(mascara: pd.Series, motivo: str) -> None:
        for i in mascara[mascara].index:
            motivos[df.index.get_loc(i)].append(motivo)

    marcar(df["status"] != "ok", "V1 status != ok")
    marcar(df["aquecimento"], "V2 aquecimento")
    marcar(df[METRICAS].isna().any(axis=1), "V3 metrica nula")
    marcar(df["run_id"].duplicated(keep="first"), "V4 run_id duplicado")
    marcar((df["ops_s"] <= 0)
           | (df[["lat_p50_ms", "lat_p99_ms", "lat_p999_ms"]] <= 0).any(axis=1)
           | (df["lat_p50_ms"] > df["lat_p99_ms"]) | (df["lat_p99_ms"] > df["lat_p999_ms"])
           | (df["erros_conexao"].fillna(0) > 0) | (df["mem_rss_mib"] <= 0)
           | (df["cpu_medio_pct"] < 0) | (df["cpu_medio_pct"] > cpu_max),
           "V6 valor fora do esperado")
    marcar(df["versao_reportada"].astype(str) != df["versao"].astype(str), "V7 versao divergente")
    marcar((df["comando"] == "GET") & (df["misses_s"].fillna(0) > 0), "V8 GET com misses")
    marcar(df["cpu_amostras"].fillna(0) < min_amostras, "V9 poucas amostras de CPU")
    marcar((df["taxa"] > 0) & ((df["ops_s"] / df["taxa"] - 1).abs() > TOLERANCIA_TAXA),
           "V10 carga fixa fora da taxa")

    df["motivo_descarte"] = ["; ".join(m) for m in motivos]
    df["valido"] = df["motivo_descarte"] == ""

    # V5: duplicidade de tratamento + repeticao entre as validas
    repetidas = df[df["valido"]].duplicated(subset=TRATAMENTO + ["repeticao"], keep="first")
    dup = repetidas[repetidas].index
    df.loc[dup, "motivo_descarte"] = "V5 repeticao duplicada"
    df.loc[dup, "valido"] = False

    # Outliers (apenas sinalizados)
    df["outliers"] = ""
    for _, g in df[df["valido"]].groupby(TRATAMENTO):
        for m in METRICAS:
            q1, q3 = g[m].quantile([0.25, 0.75])
            iqr = q3 - q1
            fora = g[(g[m] < q1 - 1.5 * iqr) | (g[m] > q3 + 1.5 * iqr)].index
            for i in fora:
                df.at[i, "outliers"] = (df.at[i, "outliers"] + " " + m).strip()
    return df


def resumo(df: pd.DataFrame, meta: dict) -> dict:
    esperado = meta.get("parametros", {}).get("repeticoes")
    validas = df[df["valido"]]
    por_trat = (validas.groupby(TRATAMENTO).size().rename("validas").reset_index())
    motivos = (df.loc[~df["valido"], "motivo_descarte"].str.split("; ").explode()
               .value_counts().to_dict())
    return {
        "coleta": meta.get("coleta"),
        "total_registros": int(len(df)),
        "aquecimento": int(df["aquecimento"].sum()),
        "validos": int(len(validas)),
        "descartados": int((~df["valido"]).sum()),
        "descartados_exceto_aquecimento": int(((~df["valido"]) & ~df["aquecimento"]).sum()),
        "motivos_descarte": {k: int(v) for k, v in motivos.items()},
        "repeticoes_esperadas_por_tratamento": esperado,
        "validas_por_tratamento": por_trat.to_dict(orient="records"),
        "tratamentos_incompletos": por_trat[por_trat["validas"] < (esperado or 0)].to_dict(orient="records"),
        "outliers_sinalizados": int((validas["outliers"] != "").sum()),
        "outliers_detalhe": validas.loc[validas["outliers"] != "", ["run_id", "outliers"]].to_dict(orient="records"),
        "descartados_detalhe": df.loc[~df["valido"] & ~df["aquecimento"],
                                      ["run_id", "motivo_descarte"]].to_dict(orient="records"),
    }


def em_markdown(r: dict) -> str:
    linhas = [
        f"# Validacao dos dados: coleta `{r['coleta']}`", "",
        "| Item | Quantidade |", "|---|---|",
        f"| Registros no CSV | {r['total_registros']} |",
        f"| Execucoes de aquecimento (descartadas por desenho) | {r['aquecimento']} |",
        f"| Execucoes validas | {r['validos']} |",
        f"| Execucoes descartadas por problema | {r['descartados_exceto_aquecimento']} |",
        f"| Outliers sinalizados (nao removidos) | {r['outliers_sinalizados']} |", "",
        "## Motivos de descarte", "",
    ]
    linhas += [f"- {k}: {v}" for k, v in r["motivos_descarte"].items()] or ["- nenhum"]
    linhas += ["", f"## Execucoes validas por tratamento (esperado: {r['repeticoes_esperadas_por_tratamento']})", "",
               "| Software | Comando | Pipeline | Carga | Validas |", "|---|---|---|---|---|"]
    linhas += [f"| {t['software']} | {t['comando']} | {t['pipeline']} | "
               f"{str(t['taxa']) + ' ops/s' if t['taxa'] else 'saturada'} | {t['validas']} |"
               for t in r["validas_por_tratamento"]]
    linhas += ["", "## Execucoes descartadas por problema (exceto aquecimento)", ""]
    if r.get("descartados_detalhe"):
        linhas += ["| Execucao | Motivo |", "|---|---|"]
        linhas += [f"| `{d['run_id']}` | {d['motivo_descarte']} |" for d in r["descartados_detalhe"]]
        linhas += ["", "Cada execucao invalida e repetida pelo coletor (`--tentativas`); a tentativa valida "
                   "fica no CSV com o mesmo tratamento e repeticao."]
    else:
        linhas.append("Nenhuma.")
    if r["outliers_detalhe"]:
        linhas += ["", "## Outliers sinalizados", "", "| Execucao | Metricas |", "|---|---|"]
        linhas += [f"| `{o['run_id']}` | {o['outliers']} |" for o in r["outliers_detalhe"]]
    return "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="piloto")
    args = ap.parse_args()

    entrada = RAIZ / "data" / "processed" / f"{args.coleta}_execucoes.csv"
    if not entrada.exists():
        print(f"ERRO: {entrada} nao encontrado. Rode antes o coleta_experimento.py.", file=sys.stderr)
        return 1
    meta_path = RAIZ / "data" / "raw" / args.coleta / "metadados.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"coleta": args.coleta}

    df = validar(pd.read_csv(entrada), meta)
    saida = RAIZ / "data" / "processed" / f"{args.coleta}_validado.csv"
    df.to_csv(saida, index=False)

    r = resumo(df, meta)
    dir_res = RAIZ / "results" / args.coleta
    dir_res.mkdir(parents=True, exist_ok=True)
    (dir_res / "validacao.json").write_text(json.dumps(r, indent=2, ensure_ascii=False))
    md = em_markdown(r)
    (dir_res / "validacao.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"Arquivo validado: {saida.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
