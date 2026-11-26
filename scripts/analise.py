"""Analise dos dados validados do experimento Redis x Valkey.

Segue o plano de analise (docs/03-metricas-hipoteses-planos.md, secao 3.5):

1. Estatistica descritiva por tratamento (software x comando x pipeline x carga) para
   M1-M5: n, media, mediana, desvio padrao, CV, min, max, Q1, Q3, IQR e IC 95%
   da mediana por bootstrap (10.000 reamostragens).
2. Graficos: boxplot (com os pontos) de cada metrica por condicao, ECDF das
   latencias (M2 e M3) por condicao e grafico de interacao software x pipeline
   para a vazao.
3. Testes por condicao (Redis x Valkey): Shapiro-Wilk em cada grupo -> t de Welch
   (os dois normais) ou Mann-Whitney U (bilateral); tamanho do efeito (g de Hedges
   ou delta de Cliff); diferenca percentual das medianas; p ajustado por
   Holm-Bonferroni sobre a familia de testes:
   - com a condicao de carga fixa (taxa > 0, desenho da S02): M1-M4 nas 4
     condicoes saturadas e M5 so na carga fixa = 18 testes. Na carga saturada a
     CPU fica no teto (~100%) e nao discrimina; ela entra so na descritiva, como
     checagem de que o servidor saturou (docs/05, D2);
   - sem ela (piloto): M1-M5 nas 4 condicoes = 20 testes.

Na coleta piloto (n = 5 por grupo) os testes sao EXPLORATORIOS: servem para testar
o script e ver a ordem de grandeza dos efeitos, nao para concluir.

Saidas em results/<coleta>/:
  descritiva.csv / descritiva.md, testes.csv / testes.md,
  boxplot_<metrica>.png, ecdf_<latencia>.png, interacao_vazao.png

Uso:
    python3 scripts/analise.py --coleta piloto
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
    "ops_s": ("M1", "Vazão", "ops/s"),
    "lat_p50_ms": ("M2", "Latência p50", "ms"),
    "lat_p99_ms": ("M3", "Latência p99", "ms"),
    "mem_rss_mib": ("M4", "Memória residente", "MiB"),
    "cpu_medio_pct": ("M5", "CPU média", "% de 1 núcleo"),
}
SOFTWARES = ["Redis", "Valkey"]
CORES = {"Redis": "#c0392b", "Valkey": "#2471a3"}
ALFA = 0.05
SEMENTE = 20261119
CONDICAO = ["comando", "pipeline", "taxa"]


def com_taxa(df: pd.DataFrame) -> pd.DataFrame:
    """Coletas sem a coluna `taxa` (piloto) sao todas de carga saturada (taxa 0)."""
    df = df.copy()
    df["taxa"] = df["taxa"].fillna(0).astype(int) if "taxa" in df else 0
    return df


def rotulo_carga(taxa: int) -> str:
    return f"{taxa:,} ops/s".replace(",", ".") if taxa else "saturada"


def ic_mediana(x: np.ndarray, rng: np.random.Generator, b: int = 10_000) -> tuple[float, float]:
    amostras = rng.choice(x, size=(b, len(x)), replace=True)
    medianas = np.median(amostras, axis=1)
    return float(np.percentile(medianas, 2.5)), float(np.percentile(medianas, 97.5))


def descritiva(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEMENTE)
    df = com_taxa(df)
    linhas = []
    for (sw, cmd, pipe, taxa), g in df.groupby(["software", *CONDICAO]):
        for m, (mid, nome, unid) in METRICAS.items():
            x = g[m].to_numpy(dtype=float)
            q1, q3 = np.percentile(x, [25, 75])
            lo, hi = ic_mediana(x, rng)
            media = x.mean()
            dp = x.std(ddof=1) if len(x) > 1 else np.nan
            linhas.append(dict(
                metrica=mid, nome=nome, unidade=unid, software=sw, comando=cmd, pipeline=pipe,
                taxa=taxa, n=len(x), media=media, mediana=np.median(x), dp=dp, cv_pct=100 * dp / media,
                min=x.min(), max=x.max(), q1=q1, q3=q3, iqr=q3 - q1,
                ic95_mediana_inf=lo, ic95_mediana_sup=hi))
    return pd.DataFrame(linhas)


def cliff_delta(a: np.ndarray, b: np.ndarray) -> float:
    """delta = P(a > b) - P(a < b). Positivo: a (Valkey) tende a ser maior."""
    dif = a[:, None] - b[None, :]
    return float((np.sign(dif)).mean())


def hedges_g(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    j = 1 - 3 / (4 * (na + nb) - 9)
    return float(j * (a.mean() - b.mean()) / sp) if sp > 0 else float("nan")


def magnitude_cliff(d: float) -> str:
    d = abs(d)
    return "desprezível" if d < 0.147 else "pequeno" if d < 0.33 else "médio" if d < 0.474 else "grande"


def magnitude_g(g: float) -> str:
    g = abs(g)
    return "desprezível" if g < 0.2 else "pequeno" if g < 0.5 else "médio" if g < 0.8 else "grande"


def holm(p: np.ndarray) -> np.ndarray:
    ordem = np.argsort(p)
    m = len(p)
    ajust = np.empty(m)
    acum = 0.0
    for rank, i in enumerate(ordem):
        acum = max(acum, (m - rank) * p[i])
        ajust[i] = min(1.0, acum)
    return ajust


def metricas_testadas(taxa: int, tem_carga_fixa: bool) -> list[str]:
    """Hipoteses testadas em cada condicao (ver docstring do modulo)."""
    if taxa:
        return ["cpu_medio_pct"]
    return [m for m in METRICAS if not (tem_carga_fixa and m == "cpu_medio_pct")]


def testes(df: pd.DataFrame) -> pd.DataFrame:
    df = com_taxa(df)
    linhas = []
    tem_carga_fixa = bool((df["taxa"] > 0).any())
    for (cmd, pipe, taxa), g in df.groupby(CONDICAO):
        for m in metricas_testadas(taxa, tem_carga_fixa):
            mid, nome, _ = METRICAS[m]
            r = g.loc[g["software"] == "Redis", m].to_numpy(dtype=float)
            v = g.loc[g["software"] == "Valkey", m].to_numpy(dtype=float)
            if len(r) < 3 or len(v) < 3:
                continue
            p_sw_r = stats.shapiro(r).pvalue if np.ptp(r) > 0 else 0.0
            p_sw_v = stats.shapiro(v).pvalue if np.ptp(v) > 0 else 0.0
            normal = p_sw_r > ALFA and p_sw_v > ALFA
            if normal:
                teste, p = "t de Welch", stats.ttest_ind(v, r, equal_var=False).pvalue
                efeito, nome_ef = hedges_g(v, r), "g de Hedges"
                mag = magnitude_g(efeito)
            else:
                teste, p = "Mann-Whitney U", stats.mannwhitneyu(v, r, alternative="two-sided").pvalue
                efeito, nome_ef = cliff_delta(v, r), "delta de Cliff"
                mag = magnitude_cliff(efeito)
            med_r, med_v = np.median(r), np.median(v)
            linhas.append(dict(
                metrica=mid, nome=nome, comando=cmd, pipeline=pipe, taxa=taxa,
                n_redis=len(r), n_valkey=len(v),
                mediana_redis=med_r, mediana_valkey=med_v,
                dif_mediana_pct=100 * (med_v - med_r) / med_r,
                shapiro_p_redis=p_sw_r, shapiro_p_valkey=p_sw_v, teste=teste, p=p,
                tamanho_efeito=nome_ef, efeito=efeito, magnitude=mag,
                delta_cliff=cliff_delta(v, r)))
    res = pd.DataFrame(linhas)
    if not res.empty:
        res["p_holm"] = holm(res["p"].to_numpy())
        res["significativo_holm"] = res["p_holm"] < ALFA
        res["relevante_5pct"] = res["dif_mediana_pct"].abs() >= 5
    return res


def graficos(df: pd.DataFrame, saida: Path) -> list[Path]:
    df = com_taxa(df)
    arquivos = []
    condicoes = list(df.groupby(CONDICAO).groups)
    rng = np.random.default_rng(SEMENTE)
    for m, (mid, nome, unid) in METRICAS.items():
        fig, eixos = plt.subplots(1, len(condicoes), figsize=(3.2 * len(condicoes), 3.6))
        for ax, (cmd, pipe, taxa) in zip(np.atleast_1d(eixos), condicoes):
            g = df[(df["comando"] == cmd) & (df["pipeline"] == pipe) & (df["taxa"] == taxa)]
            dados = [g.loc[g["software"] == s, m].to_numpy() for s in SOFTWARES]
            bp = ax.boxplot(dados, widths=0.5, patch_artist=True, showfliers=False)
            for caixa, s in zip(bp["boxes"], SOFTWARES):
                caixa.set(facecolor=CORES[s], alpha=0.25, edgecolor=CORES[s])
            for med in bp["medians"]:
                med.set(color="black")
            for i, (s, x) in enumerate(zip(SOFTWARES, dados), 1):
                ax.scatter(i + rng.uniform(-0.12, 0.12, len(x)), x, s=16, color=CORES[s], zorder=3)
            ax.set_xticks([1, 2], SOFTWARES)
            ax.set_title(f"{cmd} · pipeline {pipe}" + (f"\n{rotulo_carga(taxa)}" if taxa else ""), fontsize=10)
            ax.grid(axis="y", alpha=0.3)
        np.atleast_1d(eixos)[0].set_ylabel(f"{nome} ({unid})")
        fig.suptitle(f"{mid} · {nome} por condição (n = {df.groupby(['software', *CONDICAO]).size().min()} por grupo)",
                     fontsize=11)
        fig.tight_layout()
        arq = saida / f"boxplot_{m}.png"
        fig.savefig(arq, dpi=130)
        plt.close(fig)
        arquivos.append(arq)

    # ECDF das latencias: mostra a distribuicao inteira, nao so mediana e quartis
    for m in ["lat_p50_ms", "lat_p99_ms"]:
        mid, nome, unid = METRICAS[m]
        fig, eixos = plt.subplots(1, len(condicoes), figsize=(3.2 * len(condicoes), 3.4), sharey=True)
        for ax, (cmd, pipe, taxa) in zip(np.atleast_1d(eixos), condicoes):
            g = df[(df["comando"] == cmd) & (df["pipeline"] == pipe) & (df["taxa"] == taxa)]
            for s in SOFTWARES:
                x = np.sort(g.loc[g["software"] == s, m].to_numpy())
                if not len(x):
                    continue
                # comeca em 0 no menor valor, para a curva subir de 0 a 1
                ax.step(np.r_[x[0], x], np.r_[0, np.arange(1, len(x) + 1) / len(x)], where="post",
                        color=CORES[s], label=s)
            ax.set_title(f"{cmd} · pipeline {pipe}" + (f"\n{rotulo_carga(taxa)}" if taxa else ""), fontsize=10)
            ax.set_xlabel(f"{nome} ({unid})", fontsize=9)
            ax.grid(alpha=0.3)
        np.atleast_1d(eixos)[0].set_ylabel("Proporção acumulada das execuções")
        np.atleast_1d(eixos)[0].legend(fontsize=8)
        fig.suptitle(f"{mid} · ECDF de {nome} por condição", fontsize=11)
        fig.tight_layout()
        arq = saida / f"ecdf_{m}.png"
        fig.savefig(arq, dpi=130)
        plt.close(fig)
        arquivos.append(arq)

    # Interacao software x pipeline (H-6) na vazao
    fig, eixos = plt.subplots(1, 2, figsize=(8, 3.6))
    for ax, cmd in zip(eixos, ["GET", "SET"]):
        for s in SOFTWARES:
            g = df[(df["comando"] == cmd) & (df["software"] == s) & (df["taxa"] == 0)].groupby("pipeline")["ops_s"].median()
            ax.plot(g.index.astype(str), g.values / 1000, marker="o", color=CORES[s], label=s)
        ax.set_title(f"{cmd}", fontsize=10)
        ax.set_xlabel("pipeline")
        ax.grid(alpha=0.3)
    eixos[0].set_ylabel("Vazão mediana (mil ops/s)")
    eixos[0].legend()
    fig.suptitle("Interação software × pipeline na vazão (H-6)", fontsize=11)
    fig.tight_layout()
    arq = saida / "interacao_vazao.png"
    fig.savefig(arq, dpi=130)
    plt.close(fig)
    arquivos.append(arq)
    return arquivos


def fmt(x: float, casas: int = 2) -> str:
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela_md(desc: pd.DataFrame, tst: pd.DataFrame, coleta: str) -> tuple[str, str]:
    d = ["# Estatística descritiva: coleta `" + coleta + "`", "",
         "| Métrica | Comando | Pipeline | Carga | Software | n | Média | Mediana | DP | CV (%) | Mín | Máx | IQR | IC 95% mediana |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in desc.sort_values(["metrica", *CONDICAO, "software"]).iterrows():
        d.append(f"| {r.metrica} {r.nome} ({r.unidade}) | {r.comando} | {r.pipeline} | {rotulo_carga(r.taxa)} | "
                 f"{r.software} | {r.n} | "
                 f"{fmt(r.media)} | {fmt(r.mediana)} | {fmt(r.dp)} | {fmt(r.cv_pct)} | {fmt(r['min'])} | "
                 f"{fmt(r['max'])} | {fmt(r.iqr)} | [{fmt(r.ic95_mediana_inf)}; {fmt(r.ic95_mediana_sup)}] |")
    t = ["# Testes Redis × Valkey: coleta `" + coleta + "`", "",
         "Diferença = (mediana Valkey − mediana Redis) / mediana Redis. Efeito positivo: Valkey maior.", "",
         "| Métrica | Comando | Pipeline | Carga | Med. Redis | Med. Valkey | Dif. (%) | Teste | p | p Holm | Efeito | Magnitude |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in (tst.sort_values(["metrica", *CONDICAO]) if not tst.empty else tst).iterrows():
        t.append(f"| {r.metrica} {r.nome} | {r.comando} | {r.pipeline} | {rotulo_carga(r.taxa)} | "
                 f"{fmt(r.mediana_redis)} | {fmt(r.mediana_valkey)} | {fmt(r.dif_mediana_pct, 1)} | {r.teste} | {fmt(r.p, 4)} | "
                 f"{fmt(r.p_holm, 4)} | {r.tamanho_efeito} = {fmt(r.efeito)} | {r.magnitude} |")
    return "\n".join(d) + "\n", "\n".join(t) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="piloto")
    args = ap.parse_args()

    entrada = RAIZ / "data" / "processed" / f"{args.coleta}_validado.csv"
    if not entrada.exists():
        print(f"ERRO: {entrada} nao encontrado. Rode antes o validacao_dados.py.", file=sys.stderr)
        return 1
    df = pd.read_csv(entrada)
    df = df[df["valido"]].copy()
    saida = RAIZ / "results" / args.coleta
    saida.mkdir(parents=True, exist_ok=True)

    desc = descritiva(df)
    tst = testes(df)
    desc.to_csv(saida / "descritiva.csv", index=False)
    tst.to_csv(saida / "testes.csv", index=False)
    md_d, md_t = tabela_md(desc, tst, args.coleta)
    (saida / "descritiva.md").write_text(md_d, encoding="utf-8")
    (saida / "testes.md").write_text(md_t, encoding="utf-8")
    arquivos = graficos(df, saida)

    print(md_t)
    print("Arquivos gerados:")
    for a in [saida / "descritiva.csv", saida / "descritiva.md", saida / "testes.csv", saida / "testes.md", *arquivos]:
        print("  ", a.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
