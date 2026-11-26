"""Testes das regras de validacao V1-V10 do validacao_dados.py.

Cada regra tem um caso que deve ser descartado e a execucao-base, que deve
passar. Os parametros seguem o piloto: servidor em "0,4" (2 CPUs, CPU maxima
200%) e 30 s de carga (minimo de (30 - 2) // 2 = 14 amostras de CPU).
"""

import io

import pandas as pd
import pytest

from validacao_dados import em_markdown, n_cpus, resumo, validar

META = {"coleta": "teste", "parametros": {"cpus_servidor": "0,4", "duracao_s": 30, "repeticoes": 1}}


def execucao(**campos) -> dict:
    """Uma execucao valida (GET, Redis, pipeline 1); `campos` sobrescreve o que o teste quer quebrar."""
    base = dict(
        run_id="0001-redis-get-p1-t1", ordem=1, tentativa=1, aquecimento=False,
        software="Redis", versao="8.10.3", versao_reportada="8.10.3",
        comando="GET", pipeline=1, repeticao=1,
        ops_s=118_000.0, lat_media_ms=1.7, lat_p50_ms=1.5, lat_p99_ms=3.6, lat_p999_ms=5.8,
        erros_conexao=0, misses_s=0.0, mem_rss_mib=60.4, mem_usada_mib=36.4,
        cpu_medio_pct=101.0, cpu_amostras=28, status="ok", erro="",
    )
    base.update(campos)
    return base


def como_csv(*execucoes: dict) -> pd.DataFrame:
    """Passa as execucoes por CSV, como o coletor grava: celula vazia vira NaN, booleanos viram texto."""
    buf = io.StringIO()
    pd.DataFrame(list(execucoes)).to_csv(buf, index=False)
    buf.seek(0)
    return pd.read_csv(buf)


def validar_uma(**campos) -> pd.Series:
    return validar(como_csv(execucao(**campos)), META).iloc[0]


# --- n_cpus -----------------------------------------------------------------

@pytest.mark.parametrize("cpuset, esperado", [
    ("0", 1), ("0,4", 2), ("0-1", 2), ("1-3,5-7", 6), ("0-3", 4), ("0,4,", 2),
])
def test_n_cpus(cpuset, esperado):
    assert n_cpus(cpuset) == esperado


# --- execucao valida ----------------------------------------------------------

def test_execucao_base_e_valida():
    r = validar_uma()
    assert r["valido"]
    assert r["motivo_descarte"] == ""


def test_aquecimento_lido_como_texto():
    """O CSV do coletor grava 'True'/'False' como texto."""
    assert not validar_uma(aquecimento="True")["valido"]
    assert validar_uma(aquecimento="False")["valido"]


# --- regras de descarte ---------------------------------------------------------

@pytest.mark.parametrize("campos, regra", [
    ({"status": "erro"}, "V1"),
    ({"aquecimento": True}, "V2"),
    ({"ops_s": None}, "V3"),
    ({"lat_p50_ms": None}, "V3"),
    ({"lat_p99_ms": None}, "V3"),
    ({"mem_rss_mib": None}, "V3"),
    ({"cpu_medio_pct": None}, "V3"),
    ({"ops_s": 0.0}, "V6"),
    ({"lat_p50_ms": 0.0}, "V6"),
    ({"lat_p999_ms": -1.0}, "V6"),
    ({"lat_p50_ms": 4.0}, "V6"),              # p50 > p99
    ({"lat_p99_ms": 6.0}, "V6"),              # p99 > p99,9
    ({"erros_conexao": 3}, "V6"),
    ({"mem_rss_mib": 0.0}, "V6"),
    ({"cpu_medio_pct": -0.1}, "V6"),
    ({"cpu_medio_pct": 200.1}, "V6"),         # acima de 100 x 2 CPUs
    ({"versao_reportada": "8.10.2"}, "V7"),
    ({"misses_s": 12.5}, "V8"),
    ({"cpu_amostras": 13}, "V9"),
    ({"cpu_amostras": None}, "V9"),
])
def test_regra_descarta(campos, regra):
    r = validar_uma(**campos)
    assert not r["valido"]
    assert regra in r["motivo_descarte"]


@pytest.mark.parametrize("campos", [
    {"cpu_medio_pct": 200.0},                 # exatamente no limite
    {"cpu_medio_pct": 0.0},
    {"cpu_amostras": 14},                     # exatamente o minimo
    {"lat_p50_ms": 3.6, "lat_p99_ms": 3.6},   # p50 = p99 e permitido
    {"comando": "SET", "misses_s": 12.5},     # misses so contam no GET
    {"erros_conexao": None},                  # ausente conta como 0
])
def test_limites_aceitos(campos):
    assert validar_uma(**campos)["valido"]


def test_limite_de_cpu_segue_o_cpuset():
    meta = {"parametros": {"cpus_servidor": "0", "duracao_s": 30}}
    r = validar(como_csv(execucao(cpu_medio_pct=150.0)), meta).iloc[0]
    assert "V6" in r["motivo_descarte"]


def test_minimo_de_amostras_segue_a_duracao():
    meta = {"parametros": {"cpus_servidor": "0,4", "duracao_s": 60}}  # minimo 29
    r = validar(como_csv(execucao(cpu_amostras=28)), meta).iloc[0]
    assert "V9" in r["motivo_descarte"]


def test_varios_motivos_sao_acumulados():
    r = validar_uma(status="erro", versao_reportada="7.2.4")
    assert r["motivo_descarte"] == "V1 status != ok; V7 versao divergente"


# --- duplicidades (V4 e V5) ----------------------------------------------------

def test_v4_run_id_duplicado_mantem_o_primeiro():
    df = como_csv(execucao(), execucao(repeticao=2))
    r = validar(df, META)
    assert list(r["valido"]) == [True, False]
    assert "V4" in r.iloc[1]["motivo_descarte"]


def test_v5_repeticao_duplicada_entre_validas():
    df = como_csv(execucao(run_id="a"), execucao(run_id="b"))
    r = validar(df, META)
    assert list(r["valido"]) == [True, False]
    assert r.iloc[1]["motivo_descarte"] == "V5 repeticao duplicada"


def test_v5_ignora_tentativa_invalida_anterior():
    """Uma tentativa com erro seguida da repeticao refeita nao e duplicidade."""
    df = como_csv(execucao(run_id="a", status="erro"), execucao(run_id="b", tentativa=2))
    r = validar(df, META)
    assert list(r["valido"]) == [False, True]


def test_v5_outro_tratamento_nao_e_duplicidade():
    df = como_csv(execucao(run_id="a"),
                  execucao(run_id="b", software="Valkey", versao="9.1.3", versao_reportada="9.1.3"))
    assert validar(df, META)["valido"].all()


# --- outliers ---------------------------------------------------------------------

def test_outlier_e_sinalizado_mas_nao_removido():
    vazoes = [118_000, 118_500, 117_800, 118_200, 90_000]
    df = como_csv(*[execucao(run_id=f"r{i}", repeticao=i, ops_s=v) for i, v in enumerate(vazoes)])
    r = validar(df, META)
    assert r["valido"].all()
    assert r.iloc[4]["outliers"] == "ops_s"
    assert (r.iloc[:4]["outliers"] == "").all()


def test_outliers_so_entre_execucoes_validas():
    """Um aquecimento com valor extremo nao entra no calculo nem e sinalizado."""
    df = como_csv(*[execucao(run_id=f"r{i}", repeticao=i) for i in range(4)],
                  execucao(run_id="aq", repeticao=0, aquecimento=True, ops_s=1.0))
    r = validar(df, META)
    assert (r["outliers"] == "").all()


# --- resumo -------------------------------------------------------------------------

def test_resumo_conta_descartes_e_tratamentos_incompletos():
    df = como_csv(
        execucao(run_id="aq", aquecimento=True, repeticao=0),
        execucao(run_id="ok"),
        execucao(run_id="erro", software="Valkey", versao="9.1.3", versao_reportada="9.1.3", status="erro"),
    )
    r = resumo(validar(df, META), META)
    assert r["total_registros"] == 3
    assert r["aquecimento"] == 1
    assert r["validos"] == 1
    assert r["descartados_exceto_aquecimento"] == 1
    assert r["motivos_descarte"] == {"V2 aquecimento": 1, "V1 status != ok": 1}
    assert r["tratamentos_incompletos"] == []  # o Valkey nao tem nenhuma valida, entao nem aparece


def test_resumo_lista_cada_descarte_com_motivo_sem_o_aquecimento():
    df = como_csv(
        execucao(run_id="aq", aquecimento=True, repeticao=0),
        execucao(run_id="ok"),
        execucao(run_id="erro", repeticao=2, status="erro"),
    )
    r = resumo(validar(df, META), META)
    assert r["descartados_detalhe"] == [{"run_id": "erro", "motivo_descarte": "V1 status != ok"}]
    md = em_markdown(r)
    assert "| `erro` | V1 status != ok |" in md
    assert "`aq`" not in md.split("## Execucoes descartadas por problema")[1].split("##")[0]


def test_markdown_diz_nenhuma_quando_nao_ha_descarte():
    r = resumo(validar(como_csv(execucao()), META), META)
    assert r["descartados_detalhe"] == []
    assert "Nenhuma." in em_markdown(r)


def test_resumo_aponta_tratamento_com_menos_repeticoes():
    meta = {**META, "parametros": {**META["parametros"], "repeticoes": 2}}
    r = resumo(validar(como_csv(execucao()), meta), meta)
    assert r["tratamentos_incompletos"] == [
        {"software": "Redis", "comando": "GET", "pipeline": 1, "taxa": 0, "validas": 1}]


# --- carga fixa (V10) ------------------------------------------------------------

@pytest.mark.parametrize("ops_s, valido", [
    (50_000.0, True), (47_600.0, True), (52_400.0, True),  # dentro de +-5% da taxa
    (47_400.0, False), (52_600.0, False),
    (30_000.0, False),                                     # servidor nao deu conta da taxa
])
def test_v10_carga_fixa_precisa_atingir_a_taxa(ops_s, valido):
    r = validar_uma(taxa=50_000, ops_s=ops_s)
    assert r["valido"] == valido
    assert ("V10" in r["motivo_descarte"]) == (not valido)


def test_sem_coluna_taxa_e_carga_saturada():
    """O CSV do piloto nao tem a coluna `taxa`: tudo e carga saturada e V10 nao se aplica."""
    r = validar(como_csv(execucao()), META)
    assert (r["taxa"] == 0).all() and r["valido"].all()


def test_carga_fixa_e_saturada_sao_tratamentos_diferentes():
    """A mesma repeticao em carga fixa e saturada nao e duplicidade (V5)."""
    df = como_csv(execucao(run_id="a", taxa=0), execucao(run_id="b", taxa=50_000, ops_s=50_000.0))
    assert validar(df, META)["valido"].all()
