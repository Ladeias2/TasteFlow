"""Serviço de visão computacional (YOLOv8 de segmentação).

Fluxo: foto do prato → máscaras por alimento → área de cada classe →
percentual do prato. Os gramas são calculados depois, no banco, usando o peso
real da balança (ver vw_custo_pesagem).

O modelo é opcional: sem `ultralytics` instalado ou sem MODELO_VISAO_PATH,
os endpoints de foto respondem 503 e a estação deve enviar a composição pronta
em POST /pesagens (inferência na borda).
"""
from collections import defaultdict
from functools import lru_cache
from typing import Any

from ..config import settings


class VisaoIndisponivel(RuntimeError):
    pass


def percentuais_por_area(classes: list[str], areas: list[float],
                         confiancas: list[float]) -> list[dict]:
    """Converte as detecções em itens de composição.

    Agrega por classe (um prato pode ter dois pedaços de picanha), calcula a
    fração da área total e a confiança média ponderada pela área.
    """
    if not (len(classes) == len(areas) == len(confiancas)):
        raise ValueError("Listas de classes, áreas e confianças com tamanhos diferentes.")
    area = defaultdict(float)
    conf_pond = defaultdict(float)
    for c, a, p in zip(classes, areas, confiancas):
        if a <= 0:
            continue
        area[c] += a
        conf_pond[c] += a * p
    total = sum(area.values())
    if total == 0:
        return []
    itens = [{"rotulo": c,
              "percentual": round(100 * a / total, 2),
              "confianca": round(conf_pond[c] / a, 3)}
             for c, a in area.items()]
    return sorted(itens, key=lambda i: -i["percentual"])


@lru_cache(maxsize=1)
def _modelo() -> Any:
    if not settings.modelo_visao_path:
        raise VisaoIndisponivel("MODELO_VISAO_PATH não configurado.")
    try:
        from ultralytics import YOLO  # import tardio: dependência opcional
    except ImportError as exc:
        raise VisaoIndisponivel("Pacote 'ultralytics' não instalado.") from exc
    return YOLO(settings.modelo_visao_path)


def classificar_imagem(caminho_imagem: str, conf_min: float = 0.25) -> list[dict]:
    """Executa o YOLOv8-seg e devolve [{rotulo, percentual, confianca}, ...]."""
    modelo = _modelo()
    resultado = modelo.predict(caminho_imagem, conf=conf_min, imgsz=settings.imgsz_visao,
                               device="cpu", verbose=False)[0]
    if resultado.masks is None or len(resultado.boxes) == 0:
        return []
    nomes = resultado.names
    classes = [nomes[int(c)] for c in resultado.boxes.cls.tolist()]
    confs = resultado.boxes.conf.tolist()
    return percentuais_por_area(classes, areas_sem_sobreposicao(resultado.masks.data, resultado.boxes.conf), confs)


def areas_sem_sobreposicao(mascaras, confiancas) -> list[float]:
    """Área visível de cada máscara: um pixel coberto por duas máscaras fica com
    a de maior confiança, para não ser contado duas vezes. Mesma regra de
    ia/scripts/comum.py."""
    pesos = mascaras.float() * confiancas.float()[:, None, None]
    vencedor = pesos.argmax(dim=0)
    coberto = mascaras.max(dim=0).values > 0.5
    return [float(((vencedor == i) & coberto).sum()) for i in range(len(mascaras))]
