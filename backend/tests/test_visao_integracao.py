"""Integração ponta a ponta com o modelo de visão treinado (ia/modelos).

Envia a foto de um prato sintético para POST /pesagens/foto e confere que a
API devolve a composição e o custo. É pulado se o Ultralytics ou o modelo
não estiverem disponíveis.
"""
import dataclasses
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MODELO = RAIZ / "ia" / "modelos" / "tasteflow-seg-demo.pt"
FOTO = RAIZ / "ia" / "dados" / "dataset" / "images" / "test" / "test_0000.jpg"


@pytest.fixture
def com_modelo(monkeypatch):
    pytest.importorskip("ultralytics")
    if not MODELO.exists() or not FOTO.exists():
        pytest.skip("modelo de demonstração ou dataset sintético ausente (rode os scripts de ia/)")
    from app.services import visao
    monkeypatch.setattr(visao, "settings", dataclasses.replace(visao.settings, modelo_visao_path=str(MODELO)))
    visao._modelo.cache_clear()
    yield
    visao._modelo.cache_clear()


def test_pesagem_por_foto_com_modelo_treinado(client, com_modelo):
    import yaml
    classes = yaml.safe_load((RAIZ / "ia" / "config" / "dataset.yaml").read_text(encoding="utf-8"))["names"].values()
    existentes = {i["rotulo_ia"] for i in client.get("/ingredientes").json()}
    for rotulo in set(classes) - existentes:           # o banco de teste só tem parte do cardápio
        client.post("/ingredientes", json={"nome_ingrediente": rotulo.replace("_", " ").title(),
                                           "rotulo_ia": rotulo, "categoria": "guarnicao", "custo_kg": "10.00"})
    cmd = client.post("/comandas").json()["id_comanda_aleatoria"]
    with open(FOTO, "rb") as f:
        r = client.post("/pesagens/foto", data={"id_comanda": cmd, "peso_gramas": "600"},
                        files={"foto": ("prato.jpg", f, "image/jpeg")})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["composicao"], "o modelo deveria identificar alimentos no prato"
    assert sum(float(i["percentual"]) for i in p["composicao"]) == pytest.approx(100, abs=0.1)
    assert float(p["icc"]) > 0
    assert {i["origem_classificacao"] for i in p["composicao"]} == {"ia"}
