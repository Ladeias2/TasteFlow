"""Recorta texturas reais de alimentos e de fundos a partir de config/texturas.yaml.

Uso:  python scripts/extrair_texturas.py
Saída: dados/texturas/<rotulo>/*.png  e  dados/texturas/_fundos/*.png
"""
import cv2

from comum import caminho_config, carregar_yaml, classes


def main() -> None:
    cfg = carregar_yaml("texturas.yaml")
    fotos_dir = caminho_config(cfg["fotos_dir"])
    saida = caminho_config(cfg["saida_dir"])
    validas = set(classes())
    total = 0

    def recortar(foto: str, caixas, destino):
        nonlocal total
        img = cv2.imread(str(fotos_dir / foto))
        if img is None:
            print(f"  ! foto não encontrada: {foto}")
            return
        destino.mkdir(parents=True, exist_ok=True)
        for i, (x1, y1, x2, y2) in enumerate(caixas):
            recorte = img[y1:y2, x1:x2]
            if recorte.size == 0:
                print(f"  ! caixa vazia em {foto}: {[x1, y1, x2, y2]}")
                continue
            cv2.imwrite(str(destino / f"{foto.rsplit('.', 1)[0]}_{i}.png"), recorte)
            total += 1

    for foto, por_classe in cfg["recortes"].items():
        for rotulo, caixas in por_classe.items():
            if rotulo not in validas:
                raise SystemExit(f"Rótulo '{rotulo}' não existe em dataset.yaml")
            recortar(foto, caixas, saida / rotulo)
    for foto, caixas in cfg.get("fundos", {}).items():
        recortar(foto, caixas, saida / "_fundos")

    com_textura = sorted(p.name for p in saida.iterdir() if p.is_dir() and not p.name.startswith("_"))
    print(f"{total} recortes salvos em {saida}")
    print(f"Alimentos com textura real ({len(com_textura)}): {', '.join(com_textura)}")
    print(f"Alimentos com textura procedural: {', '.join(sorted(validas - set(com_textura)))}")


if __name__ == "__main__":
    main()
