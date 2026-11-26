"""Gera a foto de um cartão raspadinha para testar a leitura óptica.

Bolinha intacta = camada prateada (cinza claro); raspada = tinta escura.
"""
from pathlib import Path

from app.services.leitura_cartao import GABARITO, RAIO_RELATIVO


def desenhar_cartao(destino: Path, marcas: dict, largura: int = 1000, altura: int = 600) -> str:
    """`marcas`: campo → opção raspada, lista de opções (ambígua) ou None (em branco)."""
    import cv2
    import numpy as np

    img = np.full((altura, largura), 245, dtype=np.uint8)          # papel
    raio = int(RAIO_RELATIVO * largura)
    for campo, cfg in GABARITO.items():
        escolhidas = marcas.get(campo)
        if not isinstance(escolhidas, list):
            escolhidas = [] if escolhidas is None else [escolhidas]
        cy = int(cfg["y"] * altura)
        for opcao, x in zip(cfg["opcoes"], cfg["xs"]):
            cor = 45 if opcao in escolhidas else 195                 # raspada × prateada
            cv2.circle(img, (int(x * largura), cy), raio, cor, -1)
    ruido = np.random.default_rng(7).normal(0, 6, img.shape)
    img = np.clip(img + ruido, 0, 255).astype(np.uint8)
    cv2.imwrite(str(destino), img)
    return str(destino)
