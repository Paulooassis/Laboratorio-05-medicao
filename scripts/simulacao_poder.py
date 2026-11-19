"""Simulacao de erro tipo I e de poder do Mann-Whitney com a variancia do piloto.

Reaproveita a ideia do Lab04: em vez de confiar em formulas, simula o teste
muitas vezes e conta quantas vezes ele rejeita H0.

Modelo: cada metrica, em cada condicao (comando x pipeline), e simulada como
log-normal com o coeficiente de variacao (CV) observado no piloto. Usa-se o
MAIOR CV entre Redis e Valkey (cenario conservador). Um grupo tem mediana 1 e
o outro mediana 1 + efeito.

- Erro tipo I: efeito = 0, n = 30, alfa = 0,05 -> taxa de rejeicao deve ficar
  perto de 0,05.
- Poder: efeito = 5% (diferenca minima relevante do plano), n em 5..50, com
  alfa = 0,05 (nominal) e alfa = 0,05/20 = 0,0025 (pior caso do Holm com
  20 testes, equivalente a Bonferroni).

Saidas em results/<coleta>/:
  erro_tipo1.csv, poder.csv, poder.md, poder.png

Uso:
    python3 scripts/simulacao_poder.py --coleta piloto
    python3 scripts/simulacao_poder.py --coleta piloto --replicas 5000 --efeito 0.05
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
METRICAS = {
    "ops_s": "M1 Vazão",
    "lat_p50_ms": "M2 Latência p50",
    "lat_p99_ms": "M3 Latência p99",
    "mem_rss_mib": "M4 Memória",
    "cpu_medio_pct": "M5 CPU",
}
N_GRADE = [5, 10, 15, 20, 30, 40, 50]
ALFA = 0.05
N_TESTES = 20
N_PLANEJADO = 30
SEMENTE = 20261119


def taxa_rejeicao(cv: float, efeito: float, n: int, alfa: float, replicas: int,
                  rng: np.random.Generator) -> float:
    sigma = np.sqrt(np.log1p(max(cv, 1e-4) ** 2))  # evita CV = 0 (todos empatados)
    a = rng.lognormal(mean=0.0, sigma=sigma, size=(replicas, n))
    b = rng.lognormal(mean=np.log1p(efeito), sigma=sigma, size=(replicas, n))
    p = stats.mannwhitneyu(a, b, alternative="two-sided", axis=1, method="asymptotic").pvalue
    return float((p < alfa).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="piloto")
    ap.add_argument("--replicas", type=int, default=2000)
    ap.add_argument("--efeito", type=float, default=0.05, help="diferenca relativa minima relevante")
    args = ap.parse_args()

    entrada = RAIZ / "data" / "processed" / f"{args.coleta}_validado.csv"
    if not entrada.exists():
        print(f"ERRO: {entrada} nao encontrado. Rode antes o validacao_dados.py.", file=sys.stderr)
        return 1
    df = pd.read_csv(entrada)
    df = df[df["valido"]]
    rng = np.random.default_rng(SEMENTE)
    saida = RAIZ / "results" / args.coleta
    saida.mkdir(parents=True, exist_ok=True)

    # CV por metrica x condicao (maior CV entre os dois softwares)
    cvs = []
    for (cmd, pipe), g in df.groupby(["comando", "pipeline"]):
        for m, nome in METRICAS.items():
            cv_sw = g.groupby("software")[m].agg(lambda x: x.std(ddof=1) / x.mean())
            cvs.append(dict(metrica=nome, coluna=m, comando=cmd, pipeline=pipe,
                            cv_redis=cv_sw.get("Redis", np.nan), cv_valkey=cv_sw.get("Valkey", np.nan),
                            cv=float(cv_sw.max())))
    cvs = pd.DataFrame(cvs)

    # Erro tipo I (efeito 0) com n planejado
    erro1 = []
    for _, c in cvs.iterrows():
        erro1.append(dict(metrica=c.metrica, comando=c.comando, pipeline=c.pipeline, n=N_PLANEJADO,
                          alfa=ALFA, taxa_rejeicao_h0_verdadeira=taxa_rejeicao(
                              c.cv, 0.0, N_PLANEJADO, ALFA, args.replicas, rng)))
    erro1 = pd.DataFrame(erro1)
    erro1.to_csv(saida / "erro_tipo1.csv", index=False)

    # Poder para o efeito minimo relevante
    poder = []
    for _, c in cvs.iterrows():
        for n in N_GRADE:
            for rotulo, alfa in [("nominal", ALFA), ("holm_pior_caso", ALFA / N_TESTES)]:
                poder.append(dict(metrica=c.metrica, comando=c.comando, pipeline=c.pipeline, cv=c.cv,
                                  n=n, alfa_tipo=rotulo, alfa=alfa, efeito=args.efeito,
                                  poder=taxa_rejeicao(c.cv, args.efeito, n, alfa, args.replicas, rng)))
    poder = pd.DataFrame(poder)
    poder.to_csv(saida / "poder.csv", index=False)

    # Resumo: poder em n = 30 e menor n com poder >= 0,8 (alfa do pior caso do Holm)
    pior = poder[poder["alfa_tipo"] == "holm_pior_caso"]
    resumo = []
    for (met, cmd, pipe), g in pior.groupby(["metrica", "comando", "pipeline"], sort=False):
        ok = g[g["poder"] >= 0.8]["n"]
        resumo.append(dict(metrica=met, comando=cmd, pipeline=pipe, cv_pct=100 * g["cv"].iloc[0],
                           poder_n30=float(g.loc[g["n"] == N_PLANEJADO, "poder"].iloc[0]),
                           poder_n30_nominal=float(poder[(poder["metrica"] == met) & (poder["comando"] == cmd)
                                                         & (poder["pipeline"] == pipe) & (poder["n"] == N_PLANEJADO)
                                                         & (poder["alfa_tipo"] == "nominal")]["poder"].iloc[0]),
                           n_min_80=int(ok.min()) if len(ok) else None))
    resumo = pd.DataFrame(resumo)

    linhas = [f"# Simulação de poder e erro tipo I: coleta `{args.coleta}`", "",
              f"Mann-Whitney U bilateral, dados log-normais com o maior CV observado entre Redis e Valkey, "
              f"{args.replicas} réplicas por cenário, efeito = {100 * args.efeito:.0f}% na mediana.", "",
              "## Erro tipo I (H0 verdadeira, n = 30, α = 0,05)", "",
              f"Taxa de rejeição: mínima {erro1['taxa_rejeicao_h0_verdadeira'].min():.3f}, "
              f"média {erro1['taxa_rejeicao_h0_verdadeira'].mean():.3f}, "
              f"máxima {erro1['taxa_rejeicao_h0_verdadeira'].max():.3f} (esperado ≈ 0,05).", "",
              "## Poder para detectar 5% de diferença", "",
              "| Métrica | Comando | Pipeline | CV piloto (%) | Poder n=30 (α=0,05) | Poder n=30 (α=0,0025) | Menor n com poder ≥ 0,8 (α=0,0025) |",
              "|---|---|---|---|---|---|---|"]
    for _, r in resumo.iterrows():
        nmin = f"{r.n_min_80}" if pd.notna(r.n_min_80) else f"> {max(N_GRADE)}"
        linhas.append(f"| {r.metrica} | {r.comando} | {r.pipeline} | {r.cv_pct:.2f} | {r.poder_n30_nominal:.2f} | "
                      f"{r.poder_n30:.2f} | {nmin} |")
    insuf = resumo[resumo["poder_n30"] < 0.8]
    linhas += ["", "## Decisão", ""]
    if insuf.empty:
        linhas.append("Com α corrigido para 20 testes, n = 30 dá poder ≥ 0,8 em todas as métricas e condições. "
                      "**Mantém-se n = 30 por tratamento.**")
    else:
        linhas.append(f"{len(insuf)} de {len(resumo)} combinações métrica × condição ficam com poder < 0,8 "
                      "em n = 30 (α corrigido):")
        linhas += [f"- {r.metrica}, {r.comando} p={r.pipeline} (CV {r.cv_pct:.1f}%): poder {r.poder_n30:.2f}"
                   for _, r in insuf.iterrows()]
    md = "\n".join(linhas) + "\n"
    (saida / "poder.md").write_text(md, encoding="utf-8")

    # Grafico poder x n (alfa do pior caso do Holm)
    metricas = list(METRICAS.values())
    fig, eixos = plt.subplots(1, len(metricas), figsize=(3.3 * len(metricas), 3.4), sharey=True)
    for ax, met in zip(eixos, metricas):
        g = pior[pior["metrica"] == met]
        for (cmd, pipe), gg in g.groupby(["comando", "pipeline"]):
            ax.plot(gg["n"], gg["poder"], marker="o", ms=3, label=f"{cmd} p={pipe}")
        ax.axhline(0.8, color="gray", ls="--", lw=1)
        ax.axvline(N_PLANEJADO, color="gray", ls=":", lw=1)
        ax.set_title(met, fontsize=10)
        ax.set_xlabel("n por grupo")
        ax.grid(alpha=0.3)
    eixos[0].set_ylabel("Poder (α = 0,0025)")
    eixos[-1].legend(fontsize=8)
    fig.suptitle(f"Poder do Mann-Whitney para detectar {100 * args.efeito:.0f}% de diferença (CV do piloto)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(saida / "poder.png", dpi=130)
    plt.close(fig)

    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
