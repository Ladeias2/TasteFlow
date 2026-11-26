"""Converte fotos reais anotadas (exportação COCO de CVAT, Label Studio ou Roboflow)
para o formato YOLOv8-seg e divide em treino, validação e teste.

Fluxo para o modelo de produção:
  1. Fotografe os pratos de cima, na balança, com a câmera da estação.
  2. Anote os alimentos com polígonos numa ferramenta como o CVAT, usando
     exatamente os nomes de config/dataset.yaml (ex.: arroz_branco, feijao).
  3. Exporte em "COCO 1.0" e rode:
       python scripts/coco_para_yolo.py --coco anotacoes.json --imagens pasta_fotos/
  4. Treine:  python scripts/treinar.py --perfil producao

A divisão é feita por foto, de forma reprodutível (semente fixa).
"""
import argparse
import json
import random
import shutil
from pathlib import Path

from comum import caminho_dataset, classes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco", required=True, help="arquivo JSON no formato COCO")
    ap.add_argument("--imagens", required=True, help="pasta com as fotos referenciadas no JSON")
    ap.add_argument("--val", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.10)
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--anexar", action="store_true", help="não apaga o dataset atual (soma às imagens)")
    args = ap.parse_args()

    coco = json.loads(Path(args.coco).read_text(encoding="utf-8"))
    nomes = classes()
    categorias = {c["id"]: c["name"] for c in coco["categories"]}
    desconhecidas = sorted(set(categorias.values()) - set(nomes))
    if desconhecidas:
        raise SystemExit(f"Categorias sem classe em dataset.yaml: {desconhecidas}. "
                         "Renomeie na ferramenta de anotação ou rode sincronizar_classes.py.")

    por_imagem: dict[int, list] = {}
    for a in coco["annotations"]:
        por_imagem.setdefault(a["image_id"], []).append(a)

    imagens = [im for im in coco["images"] if im["id"] in por_imagem]
    random.Random(args.semente).shuffle(imagens)
    n = len(imagens)
    n_test, n_val = int(n * args.test), int(n * args.val)
    divisao = {"test": imagens[:n_test], "val": imagens[n_test:n_test + n_val],
               "train": imagens[n_test + n_val:]}

    destino = caminho_dataset()
    if destino.exists() and not args.anexar:
        shutil.rmtree(destino)
    ignoradas = 0
    for split, lista in divisao.items():
        (destino / "images" / split).mkdir(parents=True, exist_ok=True)
        (destino / "labels" / split).mkdir(parents=True, exist_ok=True)
        for im in lista:
            origem = Path(args.imagens) / Path(im["file_name"]).name
            if not origem.exists():
                ignoradas += 1
                continue
            w, h = im["width"], im["height"]
            linhas = []
            for a in por_imagem[im["id"]]:
                cls = nomes.index(categorias[a["category_id"]])
                segs = a.get("segmentation")
                if not isinstance(segs, list):      # RLE (máscara) não suportado: anote com polígonos
                    continue
                for seg in segs:
                    if len(seg) < 6:
                        continue
                    pts = " ".join(f"{seg[i] / w:.5f} {seg[i + 1] / h:.5f}" for i in range(0, len(seg), 2))
                    linhas.append(f"{cls} {pts}")
            shutil.copy(origem, destino / "images" / split / origem.name)
            (destino / "labels" / split / f"{origem.stem}.txt").write_text("\n".join(linhas))
        print(f"  {split}: {len(lista)} imagens")
    if ignoradas:
        print(f"  ! {ignoradas} imagens do JSON não foram encontradas em {args.imagens}")
    print(f"Dataset salvo em {destino}")


if __name__ == "__main__":
    main()
