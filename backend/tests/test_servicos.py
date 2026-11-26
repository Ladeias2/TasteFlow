"""Testes unitários dos serviços (não precisam de banco)."""
import pytest

from app.services.regras import normalizar_percentuais
from app.services.sentimento import analisar
from app.services.visao import percentuais_por_area


@pytest.mark.parametrize("texto, esperado", [
    ("Comida ótima, voltarei!", "positivo"),
    ("Ótimo atendimento", "positivo"),
    ("Carne fria", "negativo"),
    ("Mesa suja quando sentei", "negativo"),
    ("Demorou para ser atendido", "negativo"),
    ("A comida não estava boa", "negativo"),
    ("Não foi ruim", "positivo"),
    ("Ok, nada de especial", "neutro"),
])
def test_sentimento(texto, esperado):
    assert analisar(texto)[0] == esperado


def test_sentimento_vazio():
    assert analisar(None) == (None, None)
    assert analisar("   ") == (None, None)


def test_score_dentro_da_faixa():
    _, score = analisar("muito muito muito excelente maravilhoso perfeito")
    assert -1 <= score <= 1


def test_percentuais_por_area_agrega_classes():
    itens = percentuais_por_area(["arroz", "picanha", "picanha"], [500, 300, 200], [0.9, 0.8, 0.6])
    assert itens[0] == {"rotulo": "arroz", "percentual": 50.0, "confianca": 0.9}
    assert itens[1]["rotulo"] == "picanha" and itens[1]["percentual"] == 50.0
    assert itens[1]["confianca"] == pytest.approx((300 * 0.8 + 200 * 0.6) / 500, abs=1e-3)


def test_percentuais_por_area_vazio():
    assert percentuais_por_area([], [], []) == []


def test_normalizar_percentuais():
    saida = normalizar_percentuais([{"rotulo": "a", "percentual": 49.0},
                                    {"rotulo": "b", "percentual": 49.0}])
    assert [i["percentual"] for i in saida] == [50.0, 50.0]


# ------------------------------------------------------------------ leitura óptica do cartão
from app.services.leitura_cartao import decidir_marcacoes


def _linhas(comida, ambiente, atendimento, recomenda):
    return {"nota_comida": comida, "nota_ambiente": ambiente,
            "nota_atendimento": atendimento, "recomendaria": recomenda}


def test_decidir_marcacoes_ok():
    claro = [0.2] * 6
    r = decidir_marcacoes(_linhas([0.2, 0.2, 0.2, 0.2, 0.85, 0.2], claro[:4] + [0.8, 0.2],
                                  [0.9] + [0.2] * 5, [0.2, 0.2, 0.8]))
    assert [l.valor for l in r] == [4, 4, 0, "nao"]
    assert all(l.situacao == "ok" for l in r)


def test_decidir_marcacoes_branco_e_ambigua():
    r = decidir_marcacoes(_linhas([0.2] * 6, [0.8, 0.75, 0.2, 0.2, 0.2, 0.2],
                                  [0.2] * 5 + [0.8], [0.8, 0.2, 0.2]))
    situacoes = {l.campo: l.situacao for l in r}
    assert situacoes["nota_comida"] == "em_branco"
    assert situacoes["nota_ambiente"] == "ambigua"
    assert situacoes["nota_atendimento"] == "ok"
