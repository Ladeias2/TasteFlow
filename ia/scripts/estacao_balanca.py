"""Estação balança + câmera: inferência na borda e envio para a API.

Ciclo de cada prato:
  1. Leitor de código de barras lê a comanda do cliente (chega como teclado).
  2. A balança estabiliza (N leituras iguais dentro da tolerância).
  3. A câmera fotografa o prato; o modelo identifica os alimentos.
  4. POST /pesagens com peso + composição; a API devolve o ICC do prato.

Configuração em config/estacao_balanca.yaml. Modos de teste:
  python scripts/estacao_balanca.py --imagem foto.jpg          # sem câmera
  (balança 'simulada' pede o peso pelo teclado)
"""
import argparse
import re
import time
from datetime import datetime
from pathlib import Path

import cv2
import requests
from ultralytics import YOLO

from comum import caminho_config, carregar_yaml, composicao_do_resultado


class Balanca:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.serial = None
        if cfg["modo"] == "serial":
            import serial  # pyserial
            self.serial = serial.Serial(cfg["porta"], cfg["baudrate"], timeout=1)
        self.regex = re.compile(cfg["regex_peso"])

    def _ler_uma(self) -> int | None:
        if self.serial is None:
            valor = input("  peso na balança (g): ").strip()
            return int(valor) if valor.isdigit() else None
        linha = self.serial.readline().decode(errors="ignore")
        m = self.regex.search(linha)
        return round(float(m.group(1).replace(",", ".")) * 1000) if m else None

    def peso_estavel(self) -> int:
        """Espera o peso estabilizar acima do mínimo."""
        if self.serial is None:            # modo simulado: a leitura digitada já é estável
            while (p := self._ler_uma()) is None or p < self.cfg["peso_minimo_g"]:
                print("  peso inválido ou abaixo do mínimo")
            return p
        leituras: list[int] = []
        while True:
            p = self._ler_uma()
            if p is None or p < self.cfg["peso_minimo_g"]:
                leituras.clear()
                continue
            leituras = (leituras + [p])[-self.cfg["leituras_estaveis"]:]
            if len(leituras) == self.cfg["leituras_estaveis"] and \
                    max(leituras) - min(leituras) <= self.cfg["tolerancia_g"]:
                return round(sum(leituras) / len(leituras))


class Camera:
    def __init__(self, cfg: dict, imagem_fixa: str | None):
        self.cfg, self.imagem_fixa, self.cap = cfg, imagem_fixa, None
        if not imagem_fixa:
            self.cap = cv2.VideoCapture(cfg["indice"])
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["largura"])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["altura"])

    def foto(self):
        if self.imagem_fixa:
            img = cv2.imread(self.imagem_fixa)
        else:
            for _ in range(3):              # descarta quadros antigos do buffer
                self.cap.read()
            ok, img = self.cap.read()
            if not ok:
                raise RuntimeError("Falha ao capturar imagem da câmera.")
        if self.cfg.get("recorte_prato"):
            x1, y1, x2, y2 = self.cfg["recorte_prato"]
            img = img[y1:y2, x1:x2]
        return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--imagem", help="usa esta foto em vez da câmera (teste)")
    ap.add_argument("--uma-vez", action="store_true", help="processa um prato e sai")
    args = ap.parse_args()

    cfg = carregar_yaml("estacao_balanca.yaml")
    modelo = YOLO(str(caminho_config(cfg["modelo"]["caminho"])))
    balanca, camera = Balanca(cfg["balanca"]), Camera(cfg["camera"], args.imagem)
    pasta_fotos = caminho_config(cfg["salvar_fotos_em"])
    pasta_fotos.mkdir(parents=True, exist_ok=True)
    api = cfg["api"]["url"].rstrip("/")
    print(f"Estação pronta · API {api} · modelo {Path(cfg['modelo']['caminho']).name}")

    while True:
        comanda = input("\nLeia a comanda (ou ENTER para sair): ").strip()
        if not comanda:
            break
        peso = balanca.peso_estavel()
        inicio = time.perf_counter()
        img = camera.foto()
        res = modelo.predict(img, imgsz=cfg["modelo"]["imgsz"], conf=cfg["modelo"]["confianca_minima"],
                             device="cpu", verbose=False)[0]
        itens = composicao_do_resultado(res)
        ms = (time.perf_counter() - inicio) * 1000
        foto = pasta_fotos / f"{comanda}_{datetime.now():%Y%m%d%H%M%S}.jpg"
        cv2.imwrite(str(foto), img)

        print(f"  {peso} g · {len(itens)} alimentos identificados em {ms:.0f} ms")
        for i in itens:
            print(f"    {i['rotulo']:<15} {i['percentual']:5.1f}%  ({round(peso * i['percentual'] / 100)} g)")
        corpo = {"id_comanda": comanda, "peso_gramas": peso, "url_foto": str(foto),
                 "versao_modelo": Path(cfg["modelo"]["caminho"]).stem, "itens": itens}
        if cfg.get("preco_kg"):
            corpo["preco_kg_aplicado"] = cfg["preco_kg"]
        try:
            r = requests.post(f"{api}/pesagens", json=corpo, timeout=cfg["api"]["timeout_s"])
            if r.ok:
                d = r.json()
                aviso = "  ⚠ revisar composição" if d["revisao_necessaria"] else ""
                print(f"  ✔ pesagem {d['id_pesagem']}: R$ {d['valor_prato']} · custo R$ {d['icc']}{aviso}")
            else:
                print(f"  ✖ API {r.status_code}: {r.json().get('detail')}")
        except requests.RequestException as exc:
            print(f"  ✖ API indisponível: {exc}")
        if args.uma_vez:
            break


if __name__ == "__main__":
    main()
