"""Simulacao de erro tipo I e de poder do Mann-Whitney com a variancia do piloto.

Reaproveita a ideia do Lab04: em vez de confiar em formulas, simula o teste
muitas vezes e conta quantas vezes ele rejeita H0.

Modelo: cada metrica, em cada condicao (comando x pipeline), e simulada como
log-normal com o coeficiente de variacao (CV) observado no piloto. Usa-se o
MAIOR CV entre Redis e Valkey (cenario conservador). Um grupo tem mediana 1 e
o outro mediana 1 + efeito.

- Erro tipo I: efeito = 0, n = 30, alfa = 0,05 -> taxa de rejeicao deve ficar
  perto de 0,05.
- Poder: efeito = 5% (diferenca minima relevante do plano), n em 5..100, com
  alfa = 0,05 (nominal) e alfa = 0,05/18 = 0,0028 (pior caso do Holm com os
  18 testes da S02, equivalente a Bonferroni).
- Cenarios: o mesmo poder numa grade de CVs, sem depender da coleta. Diz ate
  que CV o n planejado ainda da poder >= 0,8.

Decisao (docs/05, D3): o n planejado (--n-planejado, padrao 50) basta se der
poder >= 0,8 com alfa corrigido nas hipoteses-alvo: H-1 e H-2 (M1 e M2, carga
saturada), H-4 (M4) e H-5 (M5, carga fixa; na coleta sem carga fixa, M5
saturada). H-3 (p99) e testada, mas nao e alvo de poder: a cauda tem CV de 8 a
16% mesmo sem deriva, e o n para 5% passaria de 100 por tratamento.

Saidas em results/<coleta>/:
  erro_tipo1.csv, poder.csv, poder_cenarios.csv, poder.md, poder.png

Uso:
    python3 scripts/simulacao_poder.py --coleta minipiloto
    python3 scripts/simulacao_poder.py --coleta piloto --replicas 5000 --efeito 0.05 --n-planejado 50
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
N_GRADE = [5, 10, 15, 20, 30, 40, 50, 60, 80, 100]
CV_GRADE = [0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]
ALFA = 0.05
N_TESTES = 18  # familia do Holm na S02: M1-M4 x 4 condicoes saturadas + M5 x 2 de carga fixa (analise.py)
N_PLANEJADO = 50
ALVO = ["M1 Vazão", "M2 Latência p50", "M4 Memória", "M5 CPU"]  # H-3 (p99) fica fora: ver docstring
PODER_MIN = 0.8
SEMENTE = 20261119


def taxa_rejeicao(cv: float, efeito: float, n: int, alfa: float, replicas: int,
                  rng: np.random.Generator) -> float:
    sigma = np.sqrt(np.log1p(max(cv, 1e-4) ** 2))  # evita CV = 0 (todos empatados)
    a = rng.lognormal(mean=0.0, sigma=sigma, size=(replicas, n))
    b = rng.lognormal(mean=np.log1p(efeito), sigma=sigma, size=(replicas, n))
    p = stats.mannwhitneyu(a, b, alternative="two-sided", axis=1, method="asymptotic").pvalue
    return float((p < alfa).mean())


def com_taxa(df: pd.DataFrame) -> pd.DataFrame:
    """Coletas sem a coluna `taxa` (piloto) sao todas de carga saturada (taxa 0)."""
    df = df.copy()
    df["taxa"] = df["taxa"].fillna(0).astype(int) if "taxa" in df else 0
    return df


def alvo(metrica: str, taxa: int, tem_carga_fixa: bool) -> bool:
    """A combinacao metrica x condicao entra na decisao do n? (mesma familia do analise.py)"""
    if taxa:
        return metrica == "M5 CPU"
    if metrica == "M5 CPU":
        return not tem_carga_fixa  # na carga saturada a CPU fica no teto (docs/05, D2)
    return metrica in ALVO


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="piloto")
    ap.add_argument("--replicas", type=int, default=2000)
    ap.add_argument("--efeito", type=float, default=0.05, help="diferenca relativa minima relevante")
    ap.add_argument("--n-planejado", type=int, default=N_PLANEJADO, help="execucoes por tratamento a conferir")
    args = ap.parse_args()
    n_plan = args.n_planejado
    n_grade = sorted(set(N_GRADE) | {n_plan})
    alfa_holm = ALFA / N_TESTES

    entrada = RAIZ / "data" / "processed" / f"{args.coleta}_validado.csv"
    if not entrada.exists():
        print(f"ERRO: {entrada} nao encontrado. Rode antes o validacao_dados.py.", file=sys.stderr)
        return 1
    df = com_taxa(pd.read_csv(entrada))
    df = df[df["valido"]]
    tem_carga_fixa = bool((df["taxa"] > 0).any())
    rng = np.random.default_rng(SEMENTE)
    saida = RAIZ / "results" / args.coleta
    saida.mkdir(parents=True, exist_ok=True)

    # CV por metrica x condicao (maior CV entre os dois softwares)
    cvs = []
    for (cmd, pipe, taxa), g in df.groupby(["comando", "pipeline", "taxa"]):
        for m, nome in METRICAS.items():
            if taxa and m == "ops_s":
                continue  # na carga fixa a vazao e a propria taxa, nao uma resposta
            cv_sw = g.groupby("software")[m].agg(lambda x: x.std(ddof=1) / x.mean())
            cvs.append(dict(metrica=nome, coluna=m, comando=cmd, pipeline=pipe, taxa=taxa,
                            alvo=alvo(nome, taxa, tem_carga_fixa), cv_redis=cv_sw.get("Redis", np.nan), cv_valkey=cv_sw.get("Valkey", np.nan),
                            cv=float(cv_sw.max())))
    cvs = pd.DataFrame(cvs)

    # Erro tipo I (efeito 0) com n planejado
    erro1 = []
    for _, c in cvs.iterrows():
        erro1.append(dict(metrica=c.metrica, comando=c.comando, pipeline=c.pipeline, taxa=c.taxa, n=n_plan,
                          alfa=ALFA, taxa_rejeicao_h0_verdadeira=taxa_rejeicao(
                              c.cv, 0.0, n_plan, ALFA, args.replicas, rng)))
    erro1 = pd.DataFrame(erro1)
    erro1.to_csv(saida / "erro_tipo1.csv", index=False)

    # Poder para o efeito minimo relevante
    poder = []
    for _, c in cvs.iterrows():
        for n in n_grade:
            for rotulo, alfa in [("nominal", ALFA), ("holm_pior_caso", alfa_holm)]:
                poder.append(dict(metrica=c.metrica, comando=c.comando, pipeline=c.pipeline, taxa=c.taxa,
                                  alvo=c.alvo, cv=c.cv, n=n, alfa_tipo=rotulo, alfa=alfa, efeito=args.efeito,
                                  poder=taxa_rejeicao(c.cv, args.efeito, n, alfa, args.replicas, rng)))
    poder = pd.DataFrame(poder)
    poder.to_csv(saida / "poder.csv", index=False)

    # Cenarios: poder x CV, independente da coleta (alfa do pior caso do Holm)
    cenarios = pd.DataFrame([dict(cv=cv, n=n, alfa=alfa_holm, efeito=args.efeito,
                                  poder=taxa_rejeicao(cv, args.efeito, n, alfa_holm, args.replicas, rng))
                             for cv in CV_GRADE for n in n_grade])
    cenarios.to_csv(saida / "poder_cenarios.csv", index=False)
    ok_plan = cenarios[(cenarios["n"] == n_plan) & (cenarios["poder"] >= PODER_MIN)]["cv"]
    cv_max = float(ok_plan.max()) if len(ok_plan) else None

    # Resumo: poder no n planejado e menor n com poder >= 0,8 (alfa do pior caso do Holm)
    pior = poder[poder["alfa_tipo"] == "holm_pior_caso"]
    nominal = poder[poder["alfa_tipo"] == "nominal"]
    resumo = []
    for (met, cmd, pipe, taxa), g in pior.groupby(["metrica", "comando", "pipeline", "taxa"], sort=False):
        ok = g[g["poder"] >= PODER_MIN]["n"]
        gn = nominal[(nominal["metrica"] == met) & (nominal["comando"] == cmd) & (nominal["pipeline"] == pipe)
                     & (nominal["taxa"] == taxa) & (nominal["n"] == n_plan)]
        resumo.append(dict(metrica=met, comando=cmd, pipeline=pipe, taxa=taxa, alvo=bool(g["alvo"].iloc[0]),
                           cv_pct=100 * g["cv"].iloc[0],
                           poder_nplan=float(g.loc[g["n"] == n_plan, "poder"].iloc[0]),
                           poder_nplan_nominal=float(gn["poder"].iloc[0]),
                           n_min_80=int(ok.min()) if len(ok) else None))
    resumo = pd.DataFrame(resumo)

    def carga(taxa: int) -> str:
        return f"{taxa} ops/s" if taxa else "saturada"

    a_txt = f"{alfa_holm:.4f}".replace(".", ",")
    p_txt = f"{PODER_MIN:g}".replace(".", ",")
    linhas = [f"# Simulação de poder e erro tipo I: coleta `{args.coleta}`", "",
              f"Mann-Whitney U bilateral, dados log-normais com o maior CV observado entre Redis e Valkey, "
              f"{args.replicas} réplicas por cenário, efeito = {100 * args.efeito:.0f}% na mediana. "
              f"α corrigido = 0,05 / {N_TESTES} = {a_txt} (pior caso do Holm).", "",
              f"## Erro tipo I (H0 verdadeira, n = {n_plan}, α = 0,05)", "",
              f"Taxa de rejeição: mínima {erro1['taxa_rejeicao_h0_verdadeira'].min():.3f}, "
              f"média {erro1['taxa_rejeicao_h0_verdadeira'].mean():.3f}, "
              f"máxima {erro1['taxa_rejeicao_h0_verdadeira'].max():.3f} (esperado ≈ 0,05).", "",
              f"## Poder para detectar {100 * args.efeito:.0f}% de diferença", "",
              f"Alvo = entra na decisão do n (H-1, H-2, H-4 e H-5; ver docs/05, D3).", "",
              f"| Métrica | Comando | Pipeline | Carga | Alvo | CV (%) | Poder n={n_plan} (α=0,05) | "
              f"Poder n={n_plan} (α={a_txt}) | Menor n com poder ≥ {p_txt} (α={a_txt}) |",
              "|---|---|---|---|---|---|---|---|---|"]
    for _, r in resumo.iterrows():
        nmin = f"{int(r.n_min_80)}" if pd.notna(r.n_min_80) else f"> {max(n_grade)}"
        linhas.append(f"| {r.metrica} | {r.comando} | {r.pipeline} | {carga(r.taxa)} | {'sim' if r.alvo else 'não'} | "
                      f"{r.cv_pct:.2f} | {r.poder_nplan_nominal:.2f} | {r.poder_nplan:.2f} | {nmin} |")

    linhas += ["", f"## Cenários: poder × CV (α = {a_txt}, efeito {100 * args.efeito:.0f}%)", "",
               "| CV (%) | " + " | ".join(f"n={n}" for n in n_grade) + " |",
               "|---|" + "---|" * len(n_grade)]
    for cv, g in cenarios.groupby("cv"):
        linhas.append(f"| {100 * cv:.0f} | " + " | ".join(f"{x:.2f}" for x in g.sort_values("n")["poder"]) + " |")
    linhas += ["", f"Com n = {n_plan}, o poder fica ≥ {p_txt} até CV = "
               + (f"{100 * cv_max:.0f}%." if cv_max is not None else "– (nenhum CV da grade).")]

    insuf = resumo[resumo["alvo"] & (resumo["poder_nplan"] < PODER_MIN)]
    fora = resumo[~resumo["alvo"] & (resumo["poder_nplan"] < PODER_MIN)]
    linhas += ["", "## Decisão", ""]
    if insuf.empty:
        linhas.append(f"**APROVADO:** com α corrigido para {N_TESTES} testes, n = {n_plan} dá poder ≥ {p_txt} "
                      f"em todas as hipóteses-alvo. **Mantém-se n = {n_plan} por tratamento.**")
    else:
        linhas.append(f"**REPROVADO:** {len(insuf)} combinação(ões) alvo ficam com poder < {p_txt} em "
                      f"n = {n_plan} (α corrigido). Não aumentar o n além do orçamento: corrigir o ambiente "
                      "(docs/05, D1) e repetir o mini-piloto.")
        linhas += [f"- {r.metrica}, {r.comando} p={r.pipeline} {carga(r.taxa)} (CV {r.cv_pct:.1f}%): "
                   f"poder {r.poder_nplan:.2f}" for _, r in insuf.iterrows()]
    if not fora.empty:
        linhas += ["", f"Fora do alvo, com poder < {p_txt} (testadas, mas uma não rejeição não é evidência de "
                   "igualdade):"]
        linhas += [f"- {r.metrica}, {r.comando} p={r.pipeline} {carga(r.taxa)} (CV {r.cv_pct:.1f}%): "
                   f"poder {r.poder_nplan:.2f}" for _, r in fora.iterrows()]
    md = "\n".join(linhas) + "\n"
    (saida / "poder.md").write_text(md, encoding="utf-8")

    # Grafico poder x n (alfa do pior caso do Holm)
    metricas = list(METRICAS.values())
    fig, eixos = plt.subplots(1, len(metricas), figsize=(3.3 * len(metricas), 3.4), sharey=True)
    for ax, met in zip(eixos, metricas):
        g = pior[pior["metrica"] == met]
        for (cmd, pipe, taxa), gg in g.groupby(["comando", "pipeline", "taxa"]):
            ax.plot(gg["n"], gg["poder"], marker="o", ms=3,
                    label=f"{cmd} p={pipe}" + (" fixa" if taxa else ""))
        ax.axhline(PODER_MIN, color="gray", ls="--", lw=1)
        ax.axvline(n_plan, color="gray", ls=":", lw=1)
        ax.set_title(met, fontsize=10)
        ax.set_xlabel("n por grupo")
        ax.grid(alpha=0.3)
    eixos[0].set_ylabel(f"Poder (α = {a_txt})")
    eixos[-1].legend(fontsize=8)
    fig.suptitle(f"Poder do Mann-Whitney para detectar {100 * args.efeito:.0f}% de diferença "
                 f"(CV da coleta {args.coleta})", fontsize=11)
    fig.tight_layout()
    fig.savefig(saida / "poder.png", dpi=130)
    plt.close(fig)

    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
