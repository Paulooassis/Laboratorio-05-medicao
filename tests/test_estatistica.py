"""Testes das funcoes estatisticas do analise.py e do diagnostico_ordem.py.

Os valores esperados foram calculados a mao (ver comentarios) ou conferidos
com uma implementacao independente do scipy.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import analise
import diagnostico_ordem as diag

# --- Holm-Bonferroni -------------------------------------------------------------


def test_holm_exemplo_a_mao():
    # ordenados: 0,005 x 4 = 0,02 | 0,01 x 3 = 0,03 | 0,03 x 2 = 0,06 | 0,04 x 1 = 0,04 -> max acumulado 0,06
    p = np.array([0.01, 0.04, 0.03, 0.005])
    np.testing.assert_allclose(analise.holm(p), [0.03, 0.06, 0.06, 0.02])


def test_holm_limita_em_1_e_preserva_a_ordem():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 20)
    aj = analise.holm(p)
    assert (aj >= p).all() and (aj <= 1).all()
    ordem = np.argsort(p)
    assert (np.diff(aj[ordem]) >= 0).all()  # monotono: p menor nunca fica com ajuste maior


def test_holm_com_um_teste_nao_muda_nada():
    np.testing.assert_allclose(analise.holm(np.array([0.03])), [0.03])


def test_holm_decide_como_o_procedimento_sequencial():
    """Rejeitar p_holm < alfa deve ser o mesmo que o passo a passo de Holm."""
    rng = np.random.default_rng(7)
    for _ in range(200):
        p = rng.uniform(0, 0.02, 20)
        alfa, m = 0.05, len(p)
        rejeita = np.zeros(m, dtype=bool)
        for k, i in enumerate(np.argsort(p)):
            if p[i] >= alfa / (m - k):
                break
            rejeita[i] = True
        np.testing.assert_array_equal(analise.holm(p) < alfa, rejeita)


# --- delta de Cliff ----------------------------------------------------------------


@pytest.mark.parametrize("a, b, esperado", [
    ([1, 2, 3], [1, 2, 3], 0.0),
    ([4, 5], [1, 2], 1.0),
    ([1, 2], [4, 5], -1.0),
    ([1, 2], [2, 3], -0.75),  # pares: (1,2)- (1,3)- (2,2)0 (2,3)- -> -3/4
])
def test_cliff_delta_a_mao(a, b, esperado):
    assert analise.cliff_delta(np.array(a, float), np.array(b, float)) == pytest.approx(esperado)


def test_cliff_delta_igual_ao_u_de_mann_whitney():
    """delta = 2U / (n1 n2) - 1."""
    rng = np.random.default_rng(3)
    a, b = rng.normal(0, 1, 30), rng.normal(0.4, 1, 25)
    u = stats.mannwhitneyu(a, b).statistic
    assert analise.cliff_delta(a, b) == pytest.approx(2 * u / (len(a) * len(b)) - 1)


@pytest.mark.parametrize("d, magnitude", [
    (0.0, "desprezível"), (0.146, "desprezível"), (0.147, "pequeno"), (-0.32, "pequeno"),
    (0.33, "médio"), (0.473, "médio"), (0.474, "grande"), (-1.0, "grande"),
])
def test_magnitude_cliff(d, magnitude):
    assert analise.magnitude_cliff(d) == magnitude


# --- g de Hedges -----------------------------------------------------------------


def test_hedges_g_a_mao():
    # medias 2 e 3, variancias 1 e 1 -> sp = 1, d = -1; J = 1 - 3 / (4*6 - 9) = 0,8 -> g = -0,8
    assert analise.hedges_g(np.array([1., 2, 3]), np.array([2., 3, 4])) == pytest.approx(-0.8)


def test_hedges_g_sem_variancia_e_nan():
    assert np.isnan(analise.hedges_g(np.array([1., 1, 1]), np.array([2., 2, 2])))


def test_hedges_g_antissimetrico():
    rng = np.random.default_rng(5)
    a, b = rng.normal(10, 2, 12), rng.normal(11, 3, 9)
    assert analise.hedges_g(a, b) == pytest.approx(-analise.hedges_g(b, a))


@pytest.mark.parametrize("g, magnitude", [
    (0.19, "desprezível"), (0.2, "pequeno"), (-0.49, "pequeno"),
    (0.5, "médio"), (0.79, "médio"), (-0.8, "grande"),
])
def test_magnitude_g(g, magnitude):
    assert analise.magnitude_g(g) == magnitude


# --- IC da mediana e descritiva --------------------------------------------------


def test_ic_mediana_contem_a_mediana_e_e_reprodutivel():
    x = np.random.default_rng(9).lognormal(0, 0.1, 30)
    lo, hi = analise.ic_mediana(x, np.random.default_rng(0), b=2000)
    assert lo <= np.median(x) <= hi
    assert (lo, hi) == analise.ic_mediana(x, np.random.default_rng(0), b=2000)


def dados_sinteticos(n=6, efeito_mem=-0.2, semente=0) -> pd.DataFrame:
    """Execucoes validas nos 8 tratamentos; o Valkey usa 20% menos memoria, o resto e igual."""
    rng = np.random.default_rng(semente)
    linhas, ordem = [], 0
    for sw in analise.SOFTWARES:
        for cmd in ["GET", "SET"]:
            for pipe in [1, 16]:
                for rep in range(n):
                    ordem += 1
                    mem = 60 * (1 + (efeito_mem if sw == "Valkey" else 0))
                    linhas.append(dict(
                        run_id=f"{ordem:04d}", ordem=ordem, inicio=f"2026-11-19T17:{ordem % 60:02d}:00+00:00",
                        software=sw, comando=cmd, pipeline=pipe, repeticao=rep,
                        ops_s=rng.normal(118_000 * (5 if pipe == 16 else 1), 2_000),
                        lat_p50_ms=rng.normal(1.5, 0.03), lat_p99_ms=rng.normal(3.6, 0.1),
                        mem_rss_mib=rng.normal(mem, 0.1), cpu_medio_pct=rng.normal(101, 0.2)))
    return pd.DataFrame(linhas)


def test_descritiva_uma_linha_por_tratamento_e_metrica():
    desc = analise.descritiva(dados_sinteticos())
    assert len(desc) == 8 * len(analise.METRICAS)
    assert (desc["n"] == 6).all()
    assert (desc["min"] <= desc["q1"]).all() and (desc["q3"] <= desc["max"]).all()
    assert np.allclose(desc["cv_pct"], 100 * desc["dp"] / desc["media"])


def test_testes_detecta_so_a_memoria():
    tst = analise.testes(dados_sinteticos(n=30))
    assert len(tst) == 20  # 5 metricas x 4 condicoes, como no plano
    mem = tst[tst["metrica"] == "M4"]
    assert mem["significativo_holm"].all()
    assert np.allclose(mem["dif_mediana_pct"], -20, atol=0.5)
    assert not tst.loc[tst["metrica"] != "M4", "relevante_5pct"].any()


def test_testes_escolhe_mann_whitney_quando_nao_e_normal():
    df = dados_sinteticos(n=30)
    assimetrica = (df["software"] == "Redis") & (df["comando"] == "GET") & (df["pipeline"] == 1)
    df.loc[assimetrica, "lat_p99_ms"] = np.random.default_rng(2).exponential(1, assimetrica.sum()) + 3
    tst = analise.testes(df)
    linha = tst[(tst["metrica"] == "M3") & (tst["comando"] == "GET") & (tst["pipeline"] == 1)].iloc[0]
    assert linha["teste"] == "Mann-Whitney U"
    assert linha["tamanho_efeito"] == "delta de Cliff"


def test_testes_pula_grupo_com_menos_de_3():
    df = dados_sinteticos(n=2)
    assert analise.testes(df).empty


# --- diagnostico_ordem ---------------------------------------------------------


def test_desvios_ficam_zero_na_mediana_do_tratamento():
    dv = diag.desvios(dados_sinteticos(n=5))
    for m in diag.METRICAS:
        medianas = dv.groupby(diag.TRATAMENTO)[f"desvio_{m}_pct"].median()
        np.testing.assert_allclose(medianas, 0, atol=1e-9)
    assert dv["ordem"].is_monotonic_increasing


def test_episodios_agrupa_vizinhas_e_separa_distantes():
    df = dados_sinteticos(n=5)
    df.loc[df["ordem"].isin([3, 4, 30]), "ops_s"] *= 0.8  # 3 e 4 seguidas, 30 isolada
    eps = diag.episodios(diag.desvios(df), limiar=10)
    assert [list(g["ordem"]) for g in eps] == [[3, 4], [30]]


def test_sem_episodios_quando_nada_cai():
    assert diag.episodios(diag.desvios(dados_sinteticos(n=5)), limiar=10) == []


def test_sensibilidade_sem_exclusao_nao_muda_a_diferenca():
    sens = diag.sensibilidade(dados_sinteticos(n=5), excluir=set())
    assert len(sens) == 20
    assert (sens["n_excluidas"] == 0).all()
    np.testing.assert_allclose(sens["variacao_pp"], 0)


def test_tendencia_detecta_deriva_crescente():
    # A ordem precisa ser sorteada, como no coletor: se cada tratamento rodasse em bloco,
    # a mediana do tratamento absorveria a deriva e nao haveria o que detectar.
    df = dados_sinteticos(n=5)
    df["ordem"] = np.random.default_rng(4).permutation(len(df)) + 1
    df["lat_p50_ms"] *= 1 + 0.005 * df["ordem"]  # latencia piora ao longo da coleta
    tend = diag.tendencia(diag.desvios(df))
    todos = tend[(tend["metrica"] == "M2 Latência p50") & (tend["grupo"] == "Todos")].iloc[0]
    assert todos["rho"] > 0.5 and todos["p"] < 0.01
