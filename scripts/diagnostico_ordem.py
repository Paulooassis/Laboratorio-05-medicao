"""Diagnostico de deriva temporal: o desempenho muda ao longo da coleta?

O desenho sorteia a ordem das execucoes para que uma interferencia passageira
(frequencia da CPU, processo em segundo plano, aquecimento da maquina) se
espalhe entre os tratamentos em vez de favorecer um deles. Este script verifica
se essa interferencia existiu e se ela mexe nas conclusoes (problema P1 de
docs/04-coleta-piloto.md):

1. Desvio de cada execucao em relacao a mediana do seu tratamento:
       desvio % = 100 x (valor - mediana do tratamento) / mediana do tratamento
   Assim as 8 condicoes ficam na mesma escala e podem ser vistas juntas.
2. Tendencia: correlacao de Spearman entre a ordem de execucao e o desvio, em
   todas as execucoes validas e por software (rho perto de 0 = sem deriva).
3. Episodios: execucoes com vazao (M1) pelo menos `--limiar`% abaixo da mediana
   do tratamento. Execucoes sinalizadas em sequencia formam um episodio.
4. Sensibilidade: diferenca % das medianas (Valkey x Redis) de M1-M5 por
   condicao, com todas as execucoes e sem as sinalizadas. Se a diferenca mudar
   muito, a conclusao depende de poucas execucoes afetadas.
5. Criterio de aceite (mini-piloto e coleta completa, docs/05, D1): APROVADO se
   nenhuma execucao for sinalizada e nenhuma tendencia de M1-M3, com todas as
   execucoes juntas, tiver |rho| > --rho-max (padrao 0,3) e p < 0,05. A
   tendencia por software so e informativa: com ~20 execucoes por software,
   |rho| = 0,3 aparece por acaso (simulado: o criterio so com |rho| > 0,3 em
   todos os grupos reprova 79% das coletas sem deriva; este, 13%).

Nada e removido da analise principal (analise.py): este e um diagnostico, para
discussao das ameacas a validade e para conferir o mini-piloto da S02 (A1).

Saidas em results/<coleta>/:
  ordem_desvios.csv     uma linha por execucao valida, com o desvio de M1-M5
  ordem.md              criterio de aceite, tendencia, episodios e sensibilidade
  ordem_desvios.png     desvio x ordem de execucao, por metrica

Uso:
    python3 scripts/diagnostico_ordem.py --coleta piloto
    python3 scripts/diagnostico_ordem.py --coleta piloto --limiar 10
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
TRATAMENTO = ["software", "comando", "pipeline", "taxa"]
METRICAS_CRITERIO = ["ops_s", "lat_p50_ms", "lat_p99_ms"]
ALFA_TENDENCIA = 0.05
SOFTWARES = ["Redis", "Valkey"]
CORES = {"Redis": "#c0392b", "Valkey": "#2471a3"}


def com_taxa(df: pd.DataFrame) -> pd.DataFrame:
    """Coletas sem a coluna `taxa` (piloto) sao todas de carga saturada (taxa 0)."""
    df = df.copy()
    df["taxa"] = df["taxa"].fillna(0).astype(int) if "taxa" in df else 0
    return df


def desvios(df: pd.DataFrame) -> pd.DataFrame:
    df = com_taxa(df)
    out = df[["run_id", "ordem", "inicio", *TRATAMENTO]].copy()
    for m in METRICAS:
        med = df.groupby(TRATAMENTO)[m].transform("median")
        out[f"desvio_{m}_pct"] = 100 * (df[m] - med) / med
    return out.sort_values("ordem").reset_index(drop=True)


def tendencia(dv: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for m, nome in METRICAS.items():
        col = f"desvio_{m}_pct"
        for grupo, g in [("Todos", dv), *[(s, dv[dv["software"] == s]) for s in SOFTWARES]]:
            if len(g) < 3 or g[col].nunique() < 2:
                rho, p = np.nan, np.nan
            else:
                r = stats.spearmanr(g["ordem"], g[col])
                rho, p = float(r.statistic), float(r.pvalue)
            linhas.append(dict(metrica=nome, grupo=grupo, n=len(g), rho=rho, p=p))
    return pd.DataFrame(linhas)


def episodios(dv: pd.DataFrame, limiar: float) -> list[pd.DataFrame]:
    """Agrupa execucoes sinalizadas que sao vizinhas na sequencia de execucoes validas."""
    dv = dv.reset_index(drop=True)
    sinal = dv["desvio_ops_s_pct"] <= -limiar
    blocos = (sinal != sinal.shift()).cumsum()
    return [g for _, g in dv[sinal].groupby(blocos[sinal])]


def sensibilidade(df: pd.DataFrame, excluir: set[str]) -> pd.DataFrame:
    def dif(d: pd.DataFrame, m: str) -> float:
        r = d.loc[d["software"] == "Redis", m].median()
        v = d.loc[d["software"] == "Valkey", m].median()
        return 100 * (v - r) / r

    linhas = []
    df = com_taxa(df)
    sem = df[~df["run_id"].isin(excluir)]
    for (cmd, pipe, taxa), g in df.groupby(["comando", "pipeline", "taxa"]):
        g_sem = sem[(sem["comando"] == cmd) & (sem["pipeline"] == pipe) & (sem["taxa"] == taxa)]
        for m, nome in METRICAS.items():
            a, b = dif(g, m), dif(g_sem, m)
            linhas.append(dict(metrica=nome, comando=cmd, pipeline=pipe, taxa=taxa,
                               n_excluidas=int(len(g) - len(g_sem)),
                               dif_todas_pct=a, dif_sem_sinalizadas_pct=b, variacao_pp=b - a))
    return pd.DataFrame(linhas).sort_values(["metrica", "comando", "pipeline", "taxa"]).reset_index(drop=True)


def criterio(tend: pd.DataFrame, eps: list[pd.DataFrame], rho_max: float) -> tuple[bool, list[str]]:
    """Aceite da coleta quanto a deriva: sem episodios e sem tendencia geral forte em M1-M3."""
    falhas = [f"{len(g)} execução(ões) sinalizada(s) na ordem {g['ordem'].min()}–{g['ordem'].max()}"
              for g in eps]
    nomes = [METRICAS[m] for m in METRICAS_CRITERIO]
    fortes = tend[tend["metrica"].isin(nomes) & (tend["grupo"] == "Todos")
                  & (tend["rho"].abs() > rho_max) & (tend["p"] < ALFA_TENDENCIA)]
    falhas += [f"tendência em {r.metrica} ({r.grupo}): ρ = {fmt(r.rho)}, p = {fmt(r.p, 4)}"
               for r in fortes.itertuples()]
    return not falhas, falhas


def grafico(dv: pd.DataFrame, sinalizadas: set[str], limiar: float, arq: Path) -> None:
    fig, eixos = plt.subplots(len(METRICAS), 1, figsize=(9, 2.1 * len(METRICAS)), sharex=True)
    for ax, (m, nome) in zip(eixos, METRICAS.items()):
        col = f"desvio_{m}_pct"
        for s in SOFTWARES:
            g = dv[dv["software"] == s]
            ax.scatter(g["ordem"], g[col], s=18, color=CORES[s], label=s, zorder=3)
        marc = dv[dv["run_id"].isin(sinalizadas)]
        ax.scatter(marc["ordem"], marc[f"desvio_{m}_pct"], s=90, facecolors="none",
                   edgecolors="black", linewidths=1, zorder=4,
                   label="vazão ≥ " + f"{limiar:g}% abaixo da mediana")
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_ylabel(f"{nome}\ndesvio (%)", fontsize=9)
        ax.grid(alpha=0.3)
    eixos[0].legend(fontsize=8, loc="lower right", ncol=3)
    eixos[-1].set_xlabel("ordem de execução")
    fig.suptitle("Desvio de cada execução em relação à mediana do seu tratamento", fontsize=11)
    fig.tight_layout()
    fig.savefig(arq, dpi=130)
    plt.close(fig)


def fmt(x: float, casas: int = 2) -> str:
    if pd.isna(x):
        return "–"
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def em_markdown(coleta: str, limiar: float, tend: pd.DataFrame, eps: list[pd.DataFrame],
                sens: pd.DataFrame, rho_max: float) -> str:
    aprovado, falhas = criterio(tend, eps, rho_max)
    l = [f"# Diagnóstico de deriva temporal: coleta `{coleta}`", "",
         "Desvio % = (valor − mediana do tratamento) / mediana do tratamento. "
         "Gráfico: [ordem_desvios.png](ordem_desvios.png).", "",
         "## Critério de aceite", "",
         f"Nenhuma execução com vazão ≥ {fmt(limiar, 0)}% abaixo da mediana do tratamento e nenhuma "
         f"tendência em M1–M3, com todas as execuções juntas, com |ρ| > {fmt(rho_max)} e p < "
         f"{fmt(ALFA_TENDENCIA)}. A tendência por software (tabela abaixo) é só informativa.", "",
         f"**Resultado: {'APROVADO' if aprovado else 'REPROVADO'}**", ""]
    l += [f"- {f}" for f in falhas]
    l += ["", "## Tendência ao longo da coleta (Spearman: ordem × desvio)", "",
         "| Métrica | Grupo | n | ρ | p |", "|---|---|---|---|---|"]
    l += [f"| {r.metrica} | {r.grupo} | {r.n} | {fmt(r.rho)} | {fmt(r.p, 4)} |" for r in tend.itertuples()]

    l += ["", f"## Episódios (vazão ≥ {fmt(limiar, 0)}% abaixo da mediana do tratamento)", ""]
    if not eps:
        l.append("Nenhuma execução sinalizada.")
    for i, g in enumerate(eps, 1):
        sw = ", ".join(sorted(g["software"].unique()))
        l.append(f"**Episódio {i}:** ordem {g['ordem'].min()}–{g['ordem'].max()} "
                 f"({g['inicio'].min()[11:16]}–{g['inicio'].max()[11:16]} UTC), {len(g)} execução(ões), "
                 f"software: {sw}.")
        l += ["", "| Execução | Vazão | Lat. p50 | Lat. p99 | Memória | CPU |", "|---|---|---|---|---|---|"]
        l += [f"| `{r.run_id}` | {fmt(r.desvio_ops_s_pct, 1)}% | {fmt(r.desvio_lat_p50_ms_pct, 1)}% | "
              f"{fmt(r.desvio_lat_p99_ms_pct, 1)}% | {fmt(r.desvio_mem_rss_mib_pct, 1)}% | "
              f"{fmt(r.desvio_cpu_medio_pct_pct, 1)}% |" for r in g.itertuples()]
        l.append("")

    l += ["## Sensibilidade: diferença Valkey × Redis sem as execuções sinalizadas", "",
          "Diferença = (mediana Valkey − mediana Redis) / mediana Redis. "
          "Variação em pontos percentuais (p.p.).", "",
          "| Métrica | Comando | Pipeline | Carga (ops/s) | Excluídas | Dif. todas (%) | Dif. sem sinalizadas (%) "
          "| Variação (p.p.) |",
          "|---|---|---|---|---|---|---|---|"]
    l += [f"| {r.metrica} | {r.comando} | {r.pipeline} | {r.taxa or 'saturada'} | {r.n_excluidas} | {fmt(r.dif_todas_pct, 1)} | "
          f"{fmt(r.dif_sem_sinalizadas_pct, 1)} | {fmt(r.variacao_pp, 1)} |" for r in sens.itertuples()]
    return "\n".join(l) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="piloto")
    ap.add_argument("--limiar", type=float, default=10.0,
                    help="queda de vazão (%% abaixo da mediana do tratamento) que sinaliza a execução")
    ap.add_argument("--rho-max", type=float, default=0.3,
                    help="maior |rho| de Spearman (ordem x desvio, todas as execucoes) aceito em M1-M3")
    args = ap.parse_args()

    entrada = RAIZ / "data" / "processed" / f"{args.coleta}_validado.csv"
    if not entrada.exists():
        print(f"ERRO: {entrada} nao encontrado. Rode antes o validacao_dados.py.", file=sys.stderr)
        return 1
    df = pd.read_csv(entrada)
    df = df[df["valido"]].copy()
    saida = RAIZ / "results" / args.coleta
    saida.mkdir(parents=True, exist_ok=True)

    dv = desvios(df)
    tend = tendencia(dv)
    eps = episodios(dv, args.limiar)
    sinalizadas = set(pd.concat(eps)["run_id"]) if eps else set()
    sens = sensibilidade(df, sinalizadas)

    dv["sinalizada"] = dv["run_id"].isin(sinalizadas)
    dv.to_csv(saida / "ordem_desvios.csv", index=False)
    grafico(dv, sinalizadas, args.limiar, saida / "ordem_desvios.png")
    md = em_markdown(args.coleta, args.limiar, tend, eps, sens, args.rho_max)
    (saida / "ordem.md").write_text(md, encoding="utf-8")

    print(md)
    print("Arquivos gerados:")
    for a in ["ordem_desvios.csv", "ordem.md", "ordem_desvios.png"]:
        print("  ", (saida / a).relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
