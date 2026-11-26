"""Analise da interacao software x pipeline (H-6, pergunta Q4).

H-6 (docs/03, secao 3.3): a diferenca Valkey - Redis na vazao (M1) nao depende do
pipeline (H0) x depende (H1). M2 e M3 sao analisadas do mesmo jeito, mas como
analise EXPLORATORIA (Q4 pede M1-M3 estratificadas; so M1 tem hipotese formal).

So entram as execucoes de carga saturada (taxa 0): na carga fixa o pipeline e
sempre 1, entao nao ha o que cruzar.

Para cada metrica e cada comando (GET, SET), segue o plano de analise (docs/03,
secao 3.5, "Interacao (H-6)"):

1. ANOVA fatorial 2 x 2 (software x pipeline), tipo III (codificacao de efeitos
   -1/+1, vale tambem para grupos de tamanhos diferentes).
2. Shapiro-Wilk nos residuos da ANOVA. Residuos normais -> fica a ANOVA.
   Nao normais -> ANOVA com Aligned Rank Transform (ART; Wobbrock et al., 2011),
   alinhando os dados para o termo de interacao e rodando a ANOVA nos postos.
3. Tamanho do efeito: eta^2 parcial do termo de interacao
   (0,01 pequeno; 0,06 medio; 0,14 grande).
4. Relevancia pratica: diferenca % das medianas (Valkey - Redis) / Redis em cada
   pipeline, com IC 95% por bootstrap, e a "diferenca das diferencas"
   (pipeline 16 - pipeline 1, em pontos percentuais), tambem com IC 95%.
5. p-valor ajustado por Holm-Bonferroni dentro de cada metrica (2 testes: GET e SET).
   A familia de H-6 (M1) e separada da familia de H-1 a H-5 do analise.py.

Saidas em results/<coleta>/:
  interacao.csv / interacao.md, interacao_<metrica>.png

Uso:
    python3 scripts/interacao.py --coleta completa
    python3 scripts/interacao.py --coleta piloto --bootstrap 2000
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analise import CORES, SEMENTE, com_taxa, fmt, holm  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
METRICAS = {
    "ops_s": ("M1", "Vazão", True),          # (id, nome, hipotese formal H-6)
    "lat_p50_ms": ("M2", "Latência p50", False),
    "lat_p99_ms": ("M3", "Latência p99", False),
}
ALFA = 0.05
RELEVANCIA_PCT = 5.0
TERMOS = ["software", "pipeline", "interacao"]


def anova_2x2(y: np.ndarray, a: np.ndarray, b: np.ndarray) -> dict[str, dict[str, float]]:
    """ANOVA 2 x 2 tipo III. `a` e `b` sao 0/1 (fator software e fator pipeline).

    Cada termo e testado comparando o modelo completo com o modelo sem ele.
    Retorna, por termo: ss, f, p e eta2p (eta^2 parcial). Inclui os residuos.
    """
    y = np.asarray(y, dtype=float)
    ea = np.where(np.asarray(a) == 1, 1.0, -1.0)
    eb = np.where(np.asarray(b) == 1, 1.0, -1.0)
    x = np.column_stack([np.ones_like(y), ea, eb, ea * eb])

    def sse(cols: list[int]) -> tuple[float, np.ndarray]:
        coef, *_ = np.linalg.lstsq(x[:, cols], y, rcond=None)
        res = y - x[:, cols] @ coef
        return float(res @ res), res

    sse_full, residuos = sse([0, 1, 2, 3])
    gl_erro = len(y) - 4
    saida: dict[str, dict[str, float]] = {}
    for nome, col in zip(TERMOS, [1, 2, 3]):
        sse_red, _ = sse([c for c in range(4) if c != col])
        ss = sse_red - sse_full
        f = (ss / 1) / (sse_full / gl_erro) if sse_full > 0 else float("inf")
        saida[nome] = dict(ss=ss, f=f, p=float(stats.f.sf(f, 1, gl_erro)),
                           eta2p=ss / (ss + sse_full) if (ss + sse_full) > 0 else 0.0)
    saida["_residuos"] = residuos  # type: ignore[assignment]
    saida["_gl_erro"] = gl_erro  # type: ignore[assignment]
    return saida


def art_interacao(y: np.ndarray, a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """ART para o termo de interacao (Wobbrock et al., 2011).

    alinhado = residuo (y - media da celula) + efeito estimado da interacao
               (media da celula - media da linha - media da coluna + media geral)
    Os alinhados viram postos (empates pela media) e roda-se a ANOVA 2 x 2 nos
    postos; so o termo de interacao e interpretado.
    """
    y = np.asarray(y, dtype=float)
    a = np.asarray(a)
    b = np.asarray(b)
    geral = y.mean()
    media_a = {k: y[a == k].mean() for k in np.unique(a)}
    media_b = {k: y[b == k].mean() for k in np.unique(b)}
    media_ab = {(i, j): y[(a == i) & (b == j)].mean() for i in np.unique(a) for j in np.unique(b)}
    cel = np.array([media_ab[(i, j)] for i, j in zip(a, b)])
    efeito_ab = cel - np.array([media_a[i] for i in a]) - np.array([media_b[j] for j in b]) + geral
    alinhado = (y - cel) + efeito_ab
    postos = stats.rankdata(alinhado)
    return anova_2x2(postos, a, b)["interacao"]


def magnitude_eta2p(e: float) -> str:
    return "desprezível" if e < 0.01 else "pequeno" if e < 0.06 else "médio" if e < 0.14 else "grande"


def dif_pct_boot(r: np.ndarray, v: np.ndarray, rng: np.random.Generator, b: int) -> np.ndarray:
    """Distribuicao bootstrap de 100 * (mediana Valkey - mediana Redis) / mediana Redis."""
    med_r = np.median(rng.choice(r, size=(b, len(r)), replace=True), axis=1)
    med_v = np.median(rng.choice(v, size=(b, len(v)), replace=True), axis=1)
    return 100 * (med_v - med_r) / med_r


def interacao(df: pd.DataFrame, b_boot: int = 10_000) -> pd.DataFrame:
    df = com_taxa(df)
    df = df[df["taxa"] == 0]
    rng = np.random.default_rng(SEMENTE)
    linhas = []
    for m, (mid, nome, formal) in METRICAS.items():
        for cmd, g in df.groupby("comando"):
            pipes = sorted(g["pipeline"].unique())
            if len(pipes) != 2 or g.groupby(["software", "pipeline"]).size().min() < 3:
                continue
            p_baixo, p_alto = pipes
            y = g[m].to_numpy(dtype=float)
            a = (g["software"] == "Valkey").astype(int).to_numpy()
            bb = (g["pipeline"] == p_alto).astype(int).to_numpy()

            an = anova_2x2(y, a, bb)
            res = an["_residuos"]
            p_shapiro = float(stats.shapiro(res).pvalue) if np.ptp(res) > 0 else 0.0
            if p_shapiro > ALFA:
                metodo, termo = "ANOVA 2×2", an["interacao"]
            else:
                metodo, termo = "ART ANOVA", art_interacao(y, a, bb)

            dif, boot = {}, {}
            for p in pipes:
                gp = g[g["pipeline"] == p]
                r = gp.loc[gp["software"] == "Redis", m].to_numpy(dtype=float)
                v = gp.loc[gp["software"] == "Valkey", m].to_numpy(dtype=float)
                dif[p] = 100 * (np.median(v) - np.median(r)) / np.median(r)
                boot[p] = dif_pct_boot(r, v, rng, b_boot)
            dd_boot = boot[p_alto] - boot[p_baixo]
            linhas.append(dict(
                metrica=mid, nome=nome, hipotese="H-6" if formal else "exploratória", comando=cmd,
                n=len(y), pipeline_baixo=p_baixo, pipeline_alto=p_alto,
                dif_pct_baixo=dif[p_baixo],
                dif_pct_baixo_ic_inf=float(np.percentile(boot[p_baixo], 2.5)),
                dif_pct_baixo_ic_sup=float(np.percentile(boot[p_baixo], 97.5)),
                dif_pct_alto=dif[p_alto],
                dif_pct_alto_ic_inf=float(np.percentile(boot[p_alto], 2.5)),
                dif_pct_alto_ic_sup=float(np.percentile(boot[p_alto], 97.5)),
                dif_das_dif_pp=dif[p_alto] - dif[p_baixo],
                dif_das_dif_ic_inf=float(np.percentile(dd_boot, 2.5)),
                dif_das_dif_ic_sup=float(np.percentile(dd_boot, 97.5)),
                shapiro_p_residuos=p_shapiro, metodo=metodo,
                f_interacao=termo["f"], gl_erro=int(an["_gl_erro"]), p=termo["p"],
                eta2p=termo["eta2p"], magnitude=magnitude_eta2p(termo["eta2p"]),
                f_software=an["software"]["f"], p_software=an["software"]["p"],
                f_pipeline=an["pipeline"]["f"], p_pipeline=an["pipeline"]["p"]))
    out = pd.DataFrame(linhas)
    if out.empty:
        return out
    out["p_holm"] = np.nan
    for _, idx in out.groupby("metrica").groups.items():
        out.loc[idx, "p_holm"] = holm(out.loc[idx, "p"].to_numpy())
    out["significativo_holm"] = out["p_holm"] < ALFA
    out["relevante_5pp"] = out["dif_das_dif_pp"].abs() >= RELEVANCIA_PCT
    out["ic_dentro_5pp"] = ((out["dif_das_dif_ic_inf"] > -RELEVANCIA_PCT)
                            & (out["dif_das_dif_ic_sup"] < RELEVANCIA_PCT))
    return out


def conclusao(r: pd.Series) -> str:
    """Combina o teste (p Holm) com a relevancia pratica (+-5 p.p.) e o IC."""
    if r.significativo_holm:
        if r.relevante_5pp:
            return "interação significativa e relevante (≥ 5 p.p.)"
        if r.ic_dentro_5pp:
            return "interação significativa, mas irrelevante na prática (IC dentro de ±5 p.p.)"
        return "interação significativa; relevância incerta (estimativa < 5 p.p., IC passa de ±5 p.p.)"
    if r.ic_dentro_5pp:
        return "sem interação relevante (IC dentro de ±5 p.p.)"
    return "sem evidência de interação; inconclusivo (IC passa de ±5 p.p.)"


def em_markdown(res: pd.DataFrame, coleta: str) -> str:
    linhas = [
        f"# Interação software × pipeline: coleta `{coleta}`", "",
        "H-6: a diferença Valkey − Redis na vazão (M1) **não depende** do *pipeline* (H0). "
        "M2 e M3 são exploratórias. Só carga saturada.", "",
        "Diferença = (mediana Valkey − mediana Redis) / mediana Redis, em %, com IC 95% por *bootstrap*. "
        "Diferença das diferenças = pipeline alto − pipeline baixo, em pontos percentuais (p.p.). "
        "Método: ANOVA 2×2 tipo III se os resíduos forem normais (Shapiro-Wilk), senão ART ANOVA. "
        "p ajustado por Holm dentro de cada métrica (GET e SET).", "",
        "| Métrica | Hipótese | Comando | Dif. p=1 (%) | Dif. p=16 (%) | Dif. das dif. (p.p.) | Método | F | p | p Holm | η²p | Conclusão |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in res.iterrows():
        linhas.append(
            f"| {r.metrica} {r.nome} | {r.hipotese} | {r.comando} | "
            f"{fmt(r.dif_pct_baixo, 1)} [{fmt(r.dif_pct_baixo_ic_inf, 1)}; {fmt(r.dif_pct_baixo_ic_sup, 1)}] | "
            f"{fmt(r.dif_pct_alto, 1)} [{fmt(r.dif_pct_alto_ic_inf, 1)}; {fmt(r.dif_pct_alto_ic_sup, 1)}] | "
            f"{fmt(r.dif_das_dif_pp, 1)} [{fmt(r.dif_das_dif_ic_inf, 1)}; {fmt(r.dif_das_dif_ic_sup, 1)}] | "
            f"{r.metodo} | F(1, {r.gl_erro}) = {fmt(r.f_interacao)} | {fmt(r.p, 4)} | {fmt(r.p_holm, 4)} | "
            f"{fmt(r.eta2p, 3)} ({r.magnitude}) | {conclusao(r)} |")
    h6 = res[res["hipotese"] == "H-6"]
    linhas += ["", "## Decisão sobre H-6", ""]
    if h6.empty:
        linhas.append("Sem dados suficientes para testar H-6.")
    else:
        for _, r in h6.iterrows():
            decisao = "rejeita-se H0" if r.significativo_holm else "não se rejeita H0"
            linhas.append(f"- **{r.comando}:** {decisao} (p Holm = {fmt(r.p_holm, 4)}, η²p = {fmt(r.eta2p, 3)}). "
                          f"A diferença Valkey − Redis vai de {fmt(r.dif_pct_baixo, 1)}% (p={r.pipeline_baixo}) "
                          f"para {fmt(r.dif_pct_alto, 1)}% (p={r.pipeline_alto}): {conclusao(r)}.")
        linhas.append("")
        linhas.append("Não rejeitar H0 não prova que não há interação: veja o IC da diferença das diferenças. "
                      "Se ele ficar inteiro dentro de ±5 p.p., uma interação relevante é improvável.")
    return "\n".join(linhas) + "\n"


def grafico(res: pd.DataFrame, saida: Path) -> list[Path]:
    arquivos = []
    for mid, g in res.groupby("metrica", sort=False):
        nome = g["nome"].iloc[0]
        coluna = next(k for k, v in METRICAS.items() if v[0] == mid)
        fig, eixos = plt.subplots(1, len(g), figsize=(4 * len(g), 3.6), sharey=True)
        for ax, (_, r) in zip(np.atleast_1d(eixos), g.iterrows()):
            xs = [str(r.pipeline_baixo), str(r.pipeline_alto)]
            ys = [r.dif_pct_baixo, r.dif_pct_alto]
            err = [[r.dif_pct_baixo - r.dif_pct_baixo_ic_inf, r.dif_pct_alto - r.dif_pct_alto_ic_inf],
                   [r.dif_pct_baixo_ic_sup - r.dif_pct_baixo, r.dif_pct_alto_ic_sup - r.dif_pct_alto]]
            ax.axhspan(-RELEVANCIA_PCT, RELEVANCIA_PCT, color="gray", alpha=0.12, label="±5% (irrelevante)")
            ax.axhline(0, color="gray", lw=1)
            ax.errorbar(xs, ys, yerr=err, marker="o", capsize=5, color=CORES["Valkey"], lw=1.5)
            ax.set_title(f"{r.comando} · {r.metodo}\np Holm = {fmt(r.p_holm, 3)} · η²p = {fmt(r.eta2p, 3)}",
                         fontsize=10)
            ax.set_xlabel("pipeline")
            ax.grid(alpha=0.3)
        np.atleast_1d(eixos)[0].set_ylabel(f"Valkey vs. Redis em {nome} (%)")
        np.atleast_1d(eixos)[0].legend(fontsize=8, loc="best")
        fig.suptitle(f"{mid} · Diferença Valkey − Redis por pipeline (IC 95%)", fontsize=11)
        fig.tight_layout()
        arq = saida / f"interacao_{coluna}.png"
        fig.savefig(arq, dpi=130)
        plt.close(fig)
        arquivos.append(arq)
    return arquivos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="completa")
    ap.add_argument("--bootstrap", type=int, default=10_000, help="reamostragens do bootstrap")
    args = ap.parse_args()

    entrada = RAIZ / "data" / "processed" / f"{args.coleta}_validado.csv"
    if not entrada.exists():
        print(f"ERRO: {entrada} nao encontrado. Rode antes o validacao_dados.py.", file=sys.stderr)
        return 1
    df = pd.read_csv(entrada)
    df = df[df["valido"]].copy()
    res = interacao(df, args.bootstrap)
    if res.empty:
        print("ERRO: dados insuficientes (precisa de 2 pipelines e >= 3 execucoes por celula).", file=sys.stderr)
        return 1
    saida = RAIZ / "results" / args.coleta
    saida.mkdir(parents=True, exist_ok=True)
    res.to_csv(saida / "interacao.csv", index=False)
    md = em_markdown(res, args.coleta)
    (saida / "interacao.md").write_text(md, encoding="utf-8")
    arquivos = grafico(res, saida)
    print(md)
    print("Arquivos gerados:")
    for a in [saida / "interacao.csv", saida / "interacao.md", *arquivos]:
        print("  ", a.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
