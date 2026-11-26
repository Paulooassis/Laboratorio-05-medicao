"""Testes do sorteio da ordem e da checagem de ambiente do coleta_experimento.py."""

import argparse
import json
from collections import Counter
from pathlib import Path

import pytest

import coleta_experimento as coleta

RAIZ = Path(__file__).resolve().parent.parent
CHAVE = ("software", "comando", "pipeline", "taxa")


def plano(**campos) -> list[dict]:
    base = dict(coleta="teste", semente=20261119, repeticoes=5, aquecimento=True,
                ordem="blocos", taxa_fixa=coleta.TAXA_FIXA)
    base.update(campos)
    return coleta.montar_plano(argparse.Namespace(**base))


def trat(e: dict) -> tuple:
    return tuple(e[k] for k in CHAVE)


# --- tratamentos -------------------------------------------------------------------

def test_tratamentos_com_e_sem_carga_fixa():
    assert len(coleta.tratamentos(0)) == 8
    trats = coleta.tratamentos(50_000)
    assert len(trats) == 12
    fixa = [t for t in trats if t["taxa"]]
    assert len(fixa) == 4 and all(t["pipeline"] == 1 for t in fixa)


# --- ordem em blocos ---------------------------------------------------------------

def test_cada_bloco_tem_cada_tratamento_uma_vez():
    p = plano(repeticoes=4)
    medidas = [e for e in p if not e["aquecimento"]]
    assert len(medidas) == 4 * 12
    for b in range(1, 5):
        bloco = [e for e in medidas if e["bloco"] == b]
        assert Counter(trat(e) for e in bloco) == Counter(trat(t) for t in coleta.tratamentos(coleta.TAXA_FIXA))
        assert {e["repeticao"] for e in bloco} == {b}


def test_blocos_em_sequencia_e_aquecimento_primeiro():
    p = plano(repeticoes=3)
    assert [e["ordem"] for e in p] == list(range(1, len(p) + 1))
    assert all(e["aquecimento"] and e["bloco"] == 0 for e in p[:12])
    blocos = [e["bloco"] for e in p[12:]]
    assert blocos == sorted(blocos)


def test_ordem_dentro_do_bloco_e_sorteada():
    p = plano(repeticoes=3)
    ordens = {tuple(trat(e) for e in p if e["bloco"] == b) for b in (1, 2, 3)}
    assert len(ordens) == 3  # cada bloco com uma ordem diferente


def test_mesma_semente_mesmo_plano():
    assert plano() == plano()
    assert plano() != plano(semente=1)


def test_sorteio_livre_reproduz_o_plano_do_piloto():
    meta = json.loads((RAIZ / "data" / "raw" / "piloto" / "metadados.json").read_text())
    p = plano(semente=meta["semente"], repeticoes=5, ordem="sorteio", taxa_fixa=0)
    campos = ("ordem", "software", "comando", "pipeline", "repeticao", "aquecimento")
    assert [{k: e[k] for k in campos} for e in p] == meta["plano"]


# --- checagem de ambiente (A1 do piloto) ----------------------------------------

@pytest.mark.parametrize("amb, n_problemas", [
    ({"governador_cpu": "performance", "na_tomada": {"AC": True}}, 0),
    ({"governador_cpu": "powersave", "na_tomada": {"AC": True}}, 1),
    ({"governador_cpu": "performance", "na_tomada": {"AC": False}}, 1),
    ({"governador_cpu": "powersave", "na_tomada": {"AC": False}}, 2),  # como no piloto
    ({"governador_cpu": "performance", "na_tomada": {"AC": False, "USB": True}}, 0),
    ({"governador_cpu": "", "na_tomada": {}}, 0),  # fora do Linux: nao da para conferir
])
def test_problemas_ambiente(amb, n_problemas):
    assert len(coleta.problemas_ambiente(amb)) == n_problemas


def sys_falso(raiz: Path, governador: str, fontes: dict[str, tuple[str, str]]) -> Path:
    """Monta um /sys minimo: governador e fontes de energia {nome: (type, online)}."""
    gov = raiz / "devices/system/cpu/cpu0/cpufreq/scaling_governor"
    gov.parent.mkdir(parents=True)
    gov.write_text(governador + "\n")
    for nome, (tipo, online) in fontes.items():
        d = raiz / "class/power_supply" / nome
        d.mkdir(parents=True)
        (d / "type").write_text(tipo + "\n")
        (d / "online").write_text(online + "\n")
    return raiz


def test_energia_so_conta_carregador(tmp_path):
    """Na bateria, um mouse sem fio com `online` = 1 nao pode fazer parecer que esta na tomada."""
    amb = coleta.energia(sys_falso(tmp_path, "performance",
                                   {"AC": ("Mains", "0"), "hidpp_battery_0": ("Battery", "1")}))
    assert amb["governador_cpu"] == "performance"
    assert amb["na_tomada"] == {"AC": False}
    assert coleta.problemas_ambiente(amb) == ["maquina fora da tomada (na bateria)"]


def test_energia_na_tomada(tmp_path):
    amb = coleta.energia(sys_falso(tmp_path, "performance", {"ADP1": ("Mains", "1"), "BAT0": ("Battery", "0")}))
    assert amb["na_tomada"] == {"ADP1": True}
    assert coleta.problemas_ambiente(amb) == []
