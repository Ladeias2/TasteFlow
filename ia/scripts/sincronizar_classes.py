"""Mantém config/dataset.yaml alinhado com os ingredientes cadastrados no banco.

Lê GET /ingredientes da API. Ingredientes novos entram no FIM da lista (as
classes existentes não mudam de número, para não invalidar anotações e pesos
já treinados). Ingredientes que sumiram do banco são apenas avisados.

Uso:  python scripts/sincronizar_classes.py --api http://localhost:8000
"""
import argparse

import requests
import yaml

from comum import CONFIG_DIR, carregar_yaml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()

    ativos = [i["rotulo_ia"] for i in requests.get(f"{args.api}/ingredientes", timeout=10).json() if i["ativo"]]
    cfg = carregar_yaml("dataset.yaml")
    atuais = [cfg["names"][i] for i in sorted(cfg["names"])]
    novos = [r for r in ativos if r not in atuais]
    sumidos = [r for r in atuais if r not in ativos]

    if novos:
        cfg["names"] = {i: n for i, n in enumerate(atuais + novos)}
        texto = (CONFIG_DIR / "dataset.yaml").read_text(encoding="utf-8")
        cabecalho = texto[:texto.index("path:")]
        corpo = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
        (CONFIG_DIR / "dataset.yaml").write_text(cabecalho + corpo, encoding="utf-8")
        print(f"Classes adicionadas: {', '.join(novos)} (o modelo precisa ser retreinado)")
    else:
        print("dataset.yaml já está alinhado com o banco.")
    if sumidos:
        print(f"Atenção: inativos ou removidos do banco: {', '.join(sumidos)} (mantidos no modelo)")


if __name__ == "__main__":
    main()
