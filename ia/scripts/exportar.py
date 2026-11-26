"""Exporta o modelo para ONNX, formato leve para rodar na estação da balança
(mini PC sem GPU, ou Raspberry Pi com ONNX Runtime).

Uso:  python scripts/exportar.py --modelo modelos/tasteflow-seg-demo.pt
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from comum import IA_DIR, carregar_yaml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="modelos/tasteflow-seg-demo.pt")
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--formato", default="onnx", help="onnx | openvino | torchscript ...")
    args = ap.parse_args()

    imgsz = args.imgsz or carregar_yaml("treino.yaml")["demonstracao"]["imgsz"]
    origem = IA_DIR / args.modelo
    arquivo = YOLO(str(origem)).export(format=args.formato, imgsz=imgsz, simplify=False, dynamic=False)
    destino = IA_DIR / "modelos" / Path(arquivo).name
    if Path(arquivo).resolve() != destino.resolve():
        shutil.move(arquivo, destino)
    print(f"Exportado: {destino}")


if __name__ == "__main__":
    main()
