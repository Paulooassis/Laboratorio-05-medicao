"""Testes da analise de interacao software x pipeline (interacao.py, H-6)."""

import numpy as np
import pandas as pd
import pytest

import interacao as it


def _celulas(n=10, efeitos=(0.0, 0.0, 0.0, 0.0), ruido=1.0, semente=1):
    """Dados 2x2: efeitos = medias de (Redis p1, Valkey p1, Redis p16, Valkey p16)."""
    rng = np.random.default_rng(semente)
    y, a, b = [], [], []
    for (sw, pp), mu in zip([(0, 0), (1, 0), (0, 1), (1, 1)], efeitos):
        y += list(mu + rng.normal(0, ruido, n))
        a += [sw] * n
        b += [pp] * n
    return np.array(y), np.array(a), np.array(b)


def _df(efeitos_por_cmd, n=10, ruido=1.0):
    linhas = []
    rng = np.random.default_rng(7)
    for cmd, efeitos in efeitos_por_cmd.items():
        for (sw, pp), mu in zip([("Redis", 1), ("Valkey", 1), ("Redis", 16), ("Valkey", 16)], efeitos):
            for v in mu + rng.normal(0, ruido, n):
                linhas.append(dict(software=sw, comando=cmd, pipeline=pp, taxa=0,
                                   ops_s=v, lat_p50_ms=v / 1000, lat_p99_ms=v / 500))
    return pd.DataFrame(linhas)


# --- ANOVA 2x2 -------------------------------------------------------------------

def test_anova_sem_ruido_isola_cada_efeito():
    # Celulas exatas com pequeno ruido: so a interacao existe.
    y, a, b = _celulas(efeitos=(0, 0, 0, 10), ruido=0.5)
    r = it.anova_2x2(y, a, b)
    assert r["interacao"]["p"] < 1e-6
    assert r["interacao"]["eta2p"] > 0.9


def test_anova_modelo_aditivo_nao_tem_interacao():
    # Valkey +5 e pipeline +20, sem interacao.
    y, a, b = _celulas(efeitos=(0, 5, 20, 25), ruido=1.0, semente=3)
    r = it.anova_2x2(y, a, b)
    assert r["software"]["p"] < 1e-6
    assert r["pipeline"]["p"] < 1e-6
    assert r["interacao"]["p"] > 0.05


def test_anova_balanceada_bate_com_formula_classica():
    # Em desenho balanceado, SS da interacao = n * soma((media_cel - media_lin - media_col + geral)^2)
    y, a, b = _celulas(n=6, efeitos=(1, 3, 2, 7), ruido=1.0, semente=5)
    geral = y.mean()
    ss = 0.0
    for i in (0, 1):
        for j in (0, 1):
            cel = y[(a == i) & (b == j)].mean()
            ss += 6 * (cel - y[a == i].mean() - y[b == j].mean() + geral) ** 2
    assert it.anova_2x2(y, a, b)["interacao"]["ss"] == pytest.approx(ss)


def test_anova_gl_do_erro():
    y, a, b = _celulas(n=8)
    assert it.anova_2x2(y, a, b)["_gl_erro"] == 4 * 8 - 4


# --- ART ---------------------------------------------------------------------------

def test_art_detecta_interacao_em_dados_assimetricos():
    # Ruido exponencial (cauda longa, como latencia): interacao so na celula Valkey p16.
    rng = np.random.default_rng(11)
    _, a, b = _celulas(n=15)
    y = rng.exponential(1.0, len(a)) + 3.0 * ((a == 1) & (b == 1))
    assert it.art_interacao(y, a, b)["p"] < 0.01


def test_art_nao_inventa_interacao_em_modelo_aditivo():
    y, a, b = _celulas(efeitos=(0, 5, 20, 25), ruido=1.0, semente=13)
    assert it.art_interacao(y, a, b)["p"] > 0.05


def test_art_e_invariante_a_transformacao_monotona_nas_celulas_sem_efeito():
    # Sem nenhum efeito, os postos alinhados nao dependem da escala do dado.
    y, a, b = _celulas(efeitos=(0, 0, 0, 0), ruido=1.0, semente=17)
    p1 = it.art_interacao(y, a, b)["p"]
    p2 = it.art_interacao(y * 1000 + 50, a, b)["p"]
    assert p1 == pytest.approx(p2)


# --- interacao() de ponta a ponta --------------------------------------------------

def test_interacao_aponta_so_o_comando_com_interacao():
    df = _df({"GET": (100, 100, 200, 200),   # Valkey igual nos dois pipelines
              "SET": (100, 100, 200, 260)})  # Valkey +30% so no pipeline 16
    res = it.interacao(df, b_boot=500).set_index(["metrica", "comando"])
    assert not res.loc[("M1", "GET"), "significativo_holm"]
    assert res.loc[("M1", "SET"), "significativo_holm"]
    assert res.loc[("M1", "SET"), "dif_das_dif_pp"] == pytest.approx(30, abs=3)
    assert res.loc[("M1", "SET"), "relevante_5pp"]
    assert set(res.loc["M1", "hipotese"]) == {"H-6"}
    assert set(res.loc["M2", "hipotese"]) == {"exploratória"}


def test_interacao_ic_contem_a_estimativa():
    df = _df({"GET": (100, 105, 200, 210)})
    r = it.interacao(df, b_boot=1000).iloc[0]
    assert r.dif_pct_baixo_ic_inf <= r.dif_pct_baixo <= r.dif_pct_baixo_ic_sup
    assert r.dif_pct_alto_ic_inf <= r.dif_pct_alto <= r.dif_pct_alto_ic_sup
    assert r.dif_das_dif_ic_inf <= r.dif_das_dif_pp <= r.dif_das_dif_ic_sup


def test_interacao_ignora_carga_fixa_e_celulas_pequenas():
    df = _df({"GET": (100, 100, 200, 200)})
    fixa = df[df["pipeline"] == 1].assign(taxa=50000, ops_s=50000)
    assert len(it.interacao(pd.concat([df, fixa]), b_boot=200)) == 3  # M1-M3, so GET saturado
    pequeno = df.groupby(["software", "pipeline"]).head(2)
    assert it.interacao(pequeno, b_boot=200).empty


def test_holm_dentro_de_cada_metrica():
    df = _df({"GET": (100, 100, 200, 200), "SET": (100, 100, 200, 260)})
    res = it.interacao(df, b_boot=200)
    for _, g in res.groupby("metrica"):
        p = g["p"].to_numpy()
        esperado = np.minimum(1, np.maximum.accumulate(np.sort(p) * [2, 1]))
        assert np.allclose(np.sort(g["p_holm"].to_numpy()), esperado)


@pytest.mark.parametrize("e, mag", [(0.005, "desprezível"), (0.03, "pequeno"), (0.1, "médio"), (0.2, "grande")])
def test_magnitude_eta2p(e, mag):
    assert it.magnitude_eta2p(e) == mag


@pytest.mark.parametrize("sig, dd, ic, esperado", [
    (True, 30, (25, 35), "relevante (≥ 5 p.p.)"),
    (True, 1, (0.5, 1.5), "irrelevante na prática"),
    (True, 1, (-3, 17), "relevância incerta"),
    (False, 0.2, (-2, 2), "sem interação relevante"),
    (False, 0.2, (-20, 20), "inconclusivo"),
])
def test_conclusao_usa_teste_relevancia_e_ic(sig, dd, ic, esperado):
    r = pd.Series(dict(significativo_holm=sig, relevante_5pp=abs(dd) >= 5,
                       ic_dentro_5pp=ic[0] > -5 and ic[1] < 5))
    assert esperado in it.conclusao(r)
