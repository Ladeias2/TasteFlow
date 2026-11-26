"""Funções compartilhadas pelos scripts de IA do TasteFlow."""
from pathlib import Path

import numpy as np
import yaml

IA_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = IA_DIR / "config"


def carregar_yaml(nome: str) -> dict:
    with open(CONFIG_DIR / nome, encoding="utf-8") as f:
        return yaml.safe_load(f)


def caminho_config(relativo: str) -> Path:
    """Resolve caminhos escritos nos YAML (relativos à pasta config/)."""
    return (CONFIG_DIR / relativo).resolve()


def classes() -> list[str]:
    nomes = carregar_yaml("dataset.yaml")["names"]
    return [nomes[i] for i in sorted(nomes)]


def caminho_dataset() -> Path:
    return caminho_config(carregar_yaml("dataset.yaml")["path"])


# ------------------------------------------------------------------ composição
# Mesma regra de backend/app/services/visao.py: mantenha as duas em sincronia.
def areas_sem_sobreposicao(mascaras: np.ndarray, confiancas: np.ndarray) -> np.ndarray:
    """Área visível de cada instância (pixels), resolvendo sobreposições.

    Quando duas máscaras cobrem o mesmo pixel, ele fica com a instância de
    maior confiança — assim nenhum pixel é contado duas vezes.
    """
    if len(mascaras) == 0:
        return np.zeros(0)
    pesos = mascaras.astype(np.float32) * confiancas[:, None, None].astype(np.float32)
    vencedor = pesos.argmax(axis=0)
    coberto = mascaras.max(axis=0) > 0.5
    return np.array([np.count_nonzero((vencedor == i) & coberto) for i in range(len(mascaras))])


def percentuais_por_area(rotulos: list[str], areas, confiancas) -> list[dict]:
    """Agrega por alimento: percentual da área total e confiança média ponderada."""
    area, conf = {}, {}
    for r, a, c in zip(rotulos, areas, confiancas):
        if a <= 0:
            continue
        area[r] = area.get(r, 0.0) + float(a)
        conf[r] = conf.get(r, 0.0) + float(a) * float(c)
    total = sum(area.values())
    if total == 0:
        return []
    itens = [{"rotulo": r, "percentual": round(100 * a / total, 2), "confianca": round(conf[r] / a, 3)}
             for r, a in area.items()]
    return sorted(itens, key=lambda i: -i["percentual"])


def composicao_do_resultado(resultado) -> list[dict]:
    """Converte um resultado do Ultralytics (YOLOv8-seg) em composição do prato."""
    if resultado.masks is None or len(resultado.boxes) == 0:
        return []
    mascaras = resultado.masks.data.cpu().numpy()
    confs = resultado.boxes.conf.cpu().numpy()
    rotulos = [resultado.names[int(c)] for c in resultado.boxes.cls.cpu().numpy()]
    return percentuais_por_area(rotulos, areas_sem_sobreposicao(mascaras, confs), confs)


# ------------------------------------------------------------------ cores para visualização
def cor_da_classe(indice: int) -> tuple[int, int, int]:
    """Cor BGR estável por classe (para sobreposições e legendas)."""
    paleta = [(60, 180, 255), (40, 120, 200), (40, 60, 120), (80, 200, 230), (60, 220, 250),
              (60, 200, 60), (60, 60, 230), (120, 220, 160), (220, 220, 200), (100, 210, 240),
              (80, 140, 230), (120, 170, 230), (90, 130, 190), (70, 70, 170), (60, 90, 160),
              (90, 90, 210), (110, 60, 150), (150, 160, 250), (130, 200, 250)]
    return paleta[indice % len(paleta)]
