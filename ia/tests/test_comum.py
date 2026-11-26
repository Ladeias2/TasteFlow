"""Testes da regra de composição (mesma da API) e da coerência das configurações."""
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from comum import areas_sem_sobreposicao, carregar_yaml, classes, percentuais_por_area  # noqa: E402


def test_sobreposicao_fica_com_maior_confianca():
    a = np.zeros((10, 10)); a[:, :6] = 1          # 60 px
    b = np.zeros((10, 10)); b[:, 4:] = 1          # 60 px, 20 px em comum
    areas = areas_sem_sobreposicao(np.stack([a, b]), np.array([0.9, 0.5]))
    assert list(areas) == [60, 40]                # os 20 px disputados ficam com "a"
    assert sum(areas) == 100                      # nenhum pixel contado duas vezes


def test_percentuais_agregam_porcoes_do_mesmo_alimento():
    itens = percentuais_por_area(["arroz_branco", "feijao", "feijao"], [50, 30, 20], [0.9, 0.8, 0.6])
    assert itens[0]["percentual"] == 50 and itens[1]["percentual"] == 50
    assert itens[1]["confianca"] == round((30 * 0.8 + 20 * 0.6) / 50, 3)


def test_classes_coincidem_com_o_cardapio_do_banco():
    seed = (Path(__file__).resolve().parents[2] / "database" / "05_seed.sql").read_text(encoding="utf-8")
    for rotulo in classes():
        assert f"'{rotulo}'" in seed, f"classe {rotulo} não está cadastrada no banco"


def test_configuracoes_referenciam_classes_validas():
    validas = set(classes())
    assert set(carregar_yaml("sintetico.yaml")["frequencia"]) <= validas
    for por_classe in carregar_yaml("texturas.yaml")["recortes"].values():
        assert set(por_classe) <= validas
    assert {"producao", "demonstracao"} <= set(carregar_yaml("treino.yaml"))
