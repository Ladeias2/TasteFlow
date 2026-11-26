"""Avalia o modelo em duas camadas:

1. Métricas de segmentação do Ultralytics (mAP das máscaras) no conjunto de teste.
2. Métrica de negócio: erro da COMPOSIÇÃO estimada do prato, que é o que entra
   no cálculo do custo (ICC). Compara o percentual de cada alimento previsto com
   o real, em pontos percentuais (p.p.), e verifica se o alimento dominante do
   prato foi acertado.

A composição real vem de dados/dataset/composicao.json (gerado pelo dataset
sintético) ou, para fotos reais, pode ser calculada das anotações.

Uso:  python scripts/avaliar.py --modelo modelos/tasteflow-seg-demo.pt
"""
import argparse
import json
from collections import defaultdict

import yaml
from ultralytics import YOLO

from comum import IA_DIR, caminho_dataset, carregar_yaml, composicao_do_resultado


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="modelos/tasteflow-seg-demo.pt")
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--split", default="test")
    args = ap.parse_args()

    imgsz = args.imgsz or carregar_yaml("treino.yaml")["demonstracao"]["imgsz"]
    modelo = YOLO(str(IA_DIR / args.modelo))
    base = caminho_dataset()

    # 1) métricas de segmentação
    dataset = carregar_yaml("dataset.yaml")
    dataset["path"] = str(base)
    resolvido = IA_DIR / "runs" / "dataset_resolvido.yaml"
    resolvido.parent.mkdir(exist_ok=True)
    resolvido.write_text(yaml.safe_dump(dataset, allow_unicode=True, sort_keys=False), encoding="utf-8")
    m = modelo.val(data=str(resolvido), split=args.split, imgsz=imgsz, device="cpu",
                   project=str(IA_DIR / "runs"), name="avaliacao", exist_ok=True, plots=False, verbose=False)
    print("\n=== Segmentação (máscaras) ===")
    print(f"mAP50     : {m.seg.map50:.3f}")
    print(f"mAP50-95  : {m.seg.map:.3f}")

    # 2) erro de composição
    gabarito_arq = base / "composicao.json"
    if not gabarito_arq.exists():
        print("\n(sem composicao.json: pulando a avaliação de composição)")
        return
    gabarito = json.loads(gabarito_arq.read_text(encoding="utf-8"))
    chaves = [k for k in gabarito if k.startswith(f"{args.split}/")]
    erros_por_classe = defaultdict(list)
    erros_prato, dominante_ok = [], 0
    for chave in chaves:
        res = modelo.predict(str(base / "images" / chave), imgsz=imgsz, conf=0.25, device="cpu", verbose=False)[0]
        prevista = {i["rotulo"]: i["percentual"] for i in composicao_do_resultado(res)}
        real = gabarito[chave]
        todos = set(real) | set(prevista)
        erros = [abs(real.get(c, 0) - prevista.get(c, 0)) for c in todos]
        for c in todos:
            erros_por_classe[c].append(abs(real.get(c, 0) - prevista.get(c, 0)))
        erros_prato.append(sum(erros) / 2)           # % do prato atribuída ao alimento errado
        if prevista and max(prevista, key=prevista.get) == max(real, key=real.get):
            dominante_ok += 1

    n = len(chaves)
    print(f"\n=== Composição do prato ({n} imagens de {args.split}) ===")
    print(f"Parcela do prato classificada errada (média): {sum(erros_prato) / n:.1f}%")
    print(f"Alimento dominante correto                  : {100 * dominante_ok / n:.1f}%")
    print("\nErro médio por alimento (p.p.):")
    for c, e in sorted(erros_por_classe.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        print(f"  {c:<15} {sum(e) / len(e):5.1f}   ({len(e)} pratos)")


if __name__ == "__main__":
    main()
