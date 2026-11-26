"""Treina o modelo de segmentação de alimentos (YOLOv8-seg).

Uso:
  python scripts/treinar.py --perfil demonstracao     # CPU, pratos sintéticos
  python scripts/treinar.py --perfil producao         # fotos reais anotadas, GPU

O melhor peso é copiado para modelos/tasteflow-seg-<perfil>.pt
(o perfil demonstracao gera modelos/tasteflow-seg-demo.pt).
"""
import argparse
import shutil

import yaml
from ultralytics import YOLO

from comum import IA_DIR, caminho_dataset, carregar_yaml

NOME_SAIDA = {"demonstracao": "tasteflow-seg-demo.pt", "producao": "tasteflow-seg.pt"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perfil", default="demonstracao", choices=["demonstracao", "producao"])
    ap.add_argument("--epochs", type=int, help="sobrescreve o número de épocas do perfil")
    args = ap.parse_args()

    params = dict(carregar_yaml("treino.yaml")[args.perfil])
    base = params.pop("modelo_base")
    if args.epochs:
        params["epochs"] = args.epochs

    # O Ultralytics resolve `path` relativo à pasta de datasets dele, não ao YAML:
    # gravamos uma cópia com o caminho absoluto.
    dataset = carregar_yaml("dataset.yaml")
    dataset["path"] = str(caminho_dataset())
    resolvido = IA_DIR / "runs" / "dataset_resolvido.yaml"
    resolvido.parent.mkdir(exist_ok=True)
    resolvido.write_text(yaml.safe_dump(dataset, allow_unicode=True, sort_keys=False), encoding="utf-8")

    caminho_base = IA_DIR / base
    modelo = YOLO(str(caminho_base) if caminho_base.exists() else caminho_base.name)  # baixa o pré-treinado se faltar
    modelo.train(data=str(resolvido), project=str(IA_DIR / "runs"),
                 name=args.perfil, exist_ok=True, plots=True, verbose=False, **params)

    melhor = IA_DIR / "runs" / args.perfil / "weights" / "best.pt"
    destino = IA_DIR / "modelos" / NOME_SAIDA[args.perfil]
    destino.parent.mkdir(exist_ok=True)
    shutil.copy(melhor, destino)
    print(f"\nModelo salvo em {destino}")


if __name__ == "__main__":
    main()
