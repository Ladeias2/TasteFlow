"""Roda o modelo em fotos de pratos, mostra a composição e salva a imagem anotada.

Opcionalmente envia a pesagem para a API (mesmo payload da estação da balança).

Uso:
  python scripts/inferir.py foto1.jpg foto2.jpg
  python scripts/inferir.py foto.jpg --enviar --comanda CMD-XXXX --peso 650
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
import requests
from ultralytics import YOLO

from comum import IA_DIR, carregar_yaml, composicao_do_resultado, cor_da_classe


def desenhar(img: np.ndarray, resultado, composicao: list[dict]) -> np.ndarray:
    saida = img.copy()
    if resultado.masks is not None:
        h, w = img.shape[:2]
        for mask, cls in zip(resultado.masks.data.cpu().numpy(), resultado.boxes.cls.cpu().numpy()):
            m = cv2.resize(mask, (w, h)) > 0.5
            cor = np.array(cor_da_classe(int(cls)), np.float32)
            saida[m] = (0.45 * saida[m] + 0.55 * cor).astype(np.uint8)
            contornos, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(saida, contornos, -1, cor.tolist(), 2)
    # legenda
    nomes = resultado.names
    idx = {v: k for k, v in nomes.items()}
    altura = 26 * (len(composicao) + 1) + 10
    painel = np.full((altura, saida.shape[1], 3), 30, np.uint8)
    cv2.putText(painel, "Composicao estimada", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    for i, item in enumerate(composicao):
        y = 26 * (i + 2)
        cv2.rectangle(painel, (10, y - 14), (26, y + 2), cor_da_classe(idx[item["rotulo"]]), -1)
        cv2.putText(painel, f"{item['rotulo']}: {item['percentual']:.1f}%  (conf {item['confianca']:.2f})",
                    (34, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1)
    return np.vstack([saida, painel])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("imagens", nargs="+")
    ap.add_argument("--modelo", default="modelos/tasteflow-seg-demo.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--saida", default="dados/inferencias")
    ap.add_argument("--enviar", action="store_true", help="envia POST /pesagens para a API")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--comanda")
    ap.add_argument("--peso", type=int, help="peso do prato em gramas")
    args = ap.parse_args()

    imgsz = args.imgsz or carregar_yaml("treino.yaml")["demonstracao"]["imgsz"]
    modelo = YOLO(str(IA_DIR / args.modelo))
    pasta = IA_DIR / args.saida
    pasta.mkdir(parents=True, exist_ok=True)

    for caminho in args.imagens:
        img = cv2.imread(caminho)
        if img is None:
            print(f"! não foi possível abrir {caminho}")
            continue
        res = modelo.predict(img, imgsz=imgsz, conf=args.conf, device="cpu", verbose=False)[0]
        comp = composicao_do_resultado(res)
        print(f"\n{caminho}")
        for item in comp:
            print(f"  {item['rotulo']:<15} {item['percentual']:5.1f}%   confiança {item['confianca']:.2f}")
        if not comp:
            print("  (nenhum alimento identificado)")
        destino = pasta / f"{Path(caminho).stem}_anotada.png"
        cv2.imwrite(str(destino), desenhar(img, res, comp))
        print(f"  imagem anotada: {destino}")

        if args.enviar:
            if not (args.comanda and args.peso):
                raise SystemExit("--enviar exige --comanda e --peso")
            r = requests.post(f"{args.api}/pesagens", timeout=10, json={
                "id_comanda": args.comanda, "peso_gramas": args.peso, "url_foto": str(destino),
                "versao_modelo": Path(args.modelo).stem, "itens": comp})
            print(f"  API → {r.status_code}: ICC R$ {r.json().get('icc')}" if r.ok else f"  API → {r.status_code}: {r.text}")


if __name__ == "__main__":
    main()
