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


# --- IC da diferenca e leitura pratica --------------------------------------------


def test_ic_dif_mediana_contem_a_diferenca_e_e_reprodutivel():
    rng = np.random.default_rng(11)
    r, v = rng.lognormal(0, 0.03, 50), rng.lognormal(np.log(0.8), 0.03, 50)
    lo, hi = analise.ic_dif_mediana_pct(v, r, np.random.default_rng(0), b=2000)
    dif = 100 * (np.median(v) - np.median(r)) / np.median(r)
    assert lo <= dif <= hi
    assert -23 < lo < hi < -17  # efeito verdadeiro de -20%, ruido de 3%
    assert (lo, hi) == analise.ic_dif_mediana_pct(v, r, np.random.default_rng(0), b=2000)


def test_ic_dif_mediana_cobre_o_zero_sem_efeito():
    """Sem efeito, o IC 95% deve conter 0 em ~95% das amostras."""
    rng = np.random.default_rng(12)
    cobre = 0
    for _ in range(200):
        r, v = rng.lognormal(0, 0.05, 30), rng.lognormal(0, 0.05, 30)
        lo, hi = analise.ic_dif_mediana_pct(v, r, rng, b=1000)
        cobre += lo <= 0 <= hi
    assert 0.88 <= cobre / 200 <= 1.0


@pytest.mark.parametrize("ic, leitura", [
    ((-24.0, -18.0), "relevante"), ((5.0, 9.0), "relevante"), ((6.0, 7.0), "relevante"),
    ((-2.0, 3.0), "irrelevante"), ((-4.9, 4.9), "irrelevante"),
    ((-7.0, -2.0), "inconclusivo"), ((-6.0, 6.0), "inconclusivo"), ((4.0, 8.0), "inconclusivo"),
])
def test_leitura_pratica(ic, leitura):
    assert analise.leitura_pratica(*ic) == leitura


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
    assert (mem["leitura_pratica"] == "relevante").all()
    assert (mem["ic95_dif_inf_pct"] <= mem["dif_mediana_pct"]).all()
    assert (mem["dif_mediana_pct"] <= mem["ic95_dif_sup_pct"]).all()
    assert (tst.loc[tst["metrica"] != "M4", "leitura_pratica"] == "irrelevante").all()


def com_carga_fixa(df: pd.DataFrame, n: int, semente: int = 1) -> pd.DataFrame:
    """Acrescenta a carga fixa (GET e SET, pipeline 1, 50 mil ops/s): o Valkey gasta 10% menos CPU."""
    rng = np.random.default_rng(semente)
    linhas, ordem = [], len(df)
    for sw in analise.SOFTWARES:
        for cmd in ["GET", "SET"]:
            for rep in range(n):
                ordem += 1
                linhas.append(dict(
                    run_id=f"{ordem:04d}", ordem=ordem, inicio=f"2026-11-19T18:{ordem % 60:02d}:00+00:00",
                    software=sw, comando=cmd, pipeline=1, taxa=50_000, repeticao=rep,
                    ops_s=rng.normal(50_000, 50), lat_p50_ms=rng.normal(0.4, 0.01),
                    lat_p99_ms=rng.normal(0.9, 0.03), mem_rss_mib=rng.normal(60, 0.1),
                    cpu_medio_pct=rng.normal(45 * (0.9 if sw == "Valkey" else 1), 0.5)))
    return pd.concat([df.assign(taxa=0), pd.DataFrame(linhas)], ignore_index=True)


def test_testes_com_carga_fixa_testa_cpu_so_na_carga_fixa():
    tst = analise.testes(com_carga_fixa(dados_sinteticos(n=30), n=30))
    assert len(tst) == 18  # M1-M4 x 4 condicoes saturadas + M5 x 2 de carga fixa (docs/05, D2)
    cpu = tst[tst["metrica"] == "M5"]
    assert (cpu["taxa"] == 50_000).all() and len(cpu) == 2
    assert cpu["significativo_holm"].all()
    assert np.allclose(cpu["dif_mediana_pct"], -10, atol=0.5)
    assert (tst.loc[tst["metrica"] != "M5", "taxa"] == 0).all()


def test_descritiva_separa_carga_fixa_e_saturada():
    desc = analise.descritiva(com_carga_fixa(dados_sinteticos(), n=6))
    assert len(desc) == 12 * len(analise.METRICAS)  # 8 tratamentos saturados + 4 de carga fixa


def test_graficos_geram_boxplot_ecdf_e_interacao(tmp_path):
    arquivos = analise.graficos(com_carga_fixa(dados_sinteticos(), n=6), tmp_path)
    nomes = {a.name for a in arquivos}
    assert {f"boxplot_{m}.png" for m in analise.METRICAS} <= nomes
    assert {"ecdf_lat_p50_ms.png", "ecdf_lat_p99_ms.png", "interacao_vazao.png"} <= nomes
    assert {f"qq_{m}.png" for m in analise.METRICAS} <= nomes
    assert all(a.stat().st_size > 0 for a in arquivos)


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


def test_criterio_aprova_coleta_sem_deriva():
    # Semente sem falso alarme: o criterio reprova ~13% das coletas sem deriva (docs/05, D1)
    df = dados_sinteticos(n=5)
    df["ordem"] = np.random.default_rng(1).permutation(len(df)) + 1
    dv = diag.desvios(df)
    aprovado, falhas = diag.criterio(diag.tendencia(dv), diag.episodios(dv, limiar=10), rho_max=0.3)
    assert aprovado and falhas == []


def test_criterio_reprova_episodio_e_tendencia():
    df = dados_sinteticos(n=5)
    df["ordem"] = np.random.default_rng(4).permutation(len(df)) + 1
    df.loc[df["ordem"].isin([10, 11]), "ops_s"] *= 0.8
    df["lat_p50_ms"] *= 1 + 0.005 * df["ordem"]
    dv = diag.desvios(df)
    aprovado, falhas = diag.criterio(diag.tendencia(dv), diag.episodios(dv, limiar=10), rho_max=0.3)
    assert not aprovado
    assert any("sinalizada" in f for f in falhas)
    assert any("M2 Latência p50 (Todos)" in f for f in falhas)


def test_criterio_ignora_tendencia_so_de_um_software():
    """|rho| alto num grupo de ~20 execucoes aparece por acaso: so a tendencia geral reprova."""
    tend = pd.DataFrame([
        dict(metrica="M1 Vazão", grupo="Todos", n=40, rho=-0.20, p=0.21),
        dict(metrica="M1 Vazão", grupo="Valkey", n=20, rho=-0.58, p=0.008),  # como no piloto
        dict(metrica="M2 Latência p50", grupo="Todos", n=40, rho=0.35, p=0.08),  # forte, mas nao significativa
    ])
    assert diag.criterio(tend, [], rho_max=0.3) == (True, [])
    tend.loc[2, "p"] = 0.01
    aprovado, falhas = diag.criterio(tend, [], rho_max=0.3)
    assert not aprovado and len(falhas) == 1 and "M2 Latência p50 (Todos)" in falhas[0]


def test_tendencia_detecta_deriva_crescente():
    # A ordem precisa ser sorteada, como no coletor: se cada tratamento rodasse em bloco,
    # a mediana do tratamento absorveria a deriva e nao haveria o que detectar.
    df = dados_sinteticos(n=5)
    df["ordem"] = np.random.default_rng(4).permutation(len(df)) + 1
    df["lat_p50_ms"] *= 1 + 0.005 * df["ordem"]  # latencia piora ao longo da coleta
    tend = diag.tendencia(diag.desvios(df))
    todos = tend[(tend["metrica"] == "M2 Latência p50") & (tend["grupo"] == "Todos")].iloc[0]
    assert todos["rho"] > 0.5 and todos["p"] < 0.01
