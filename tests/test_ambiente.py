"""Confere que os scripts testados podem ser importados sem efeitos colaterais."""

import importlib

import pytest


@pytest.mark.parametrize("modulo", ["validacao_dados", "analise", "diagnostico_ordem"])
def test_script_importa(modulo):
    m = importlib.import_module(modulo)
    assert callable(m.main)
