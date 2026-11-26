"""Gera pratos sintéticos fotografados de cima, já anotados para YOLOv8-seg.

Cada prato é montado sobre um fundo real (mesa, toalha), com um prato branco
e de 3 a 6 alimentos em porções irregulares. Alimentos com textura real
(extraída por extrair_texturas.py) usam recortes de fotos; os demais usam
textura procedural. Os rótulos são calculados a partir da área VISÍVEL de
cada alimento (porções de cima cobrem as de baixo), e a composição real de
cada prato é salva em composicao.json para avaliar o modelo.

Uso:  python scripts/gerar_dataset_sintetico.py
"""
import json
import math
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

from comum import caminho_config, caminho_dataset, carregar_yaml, classes

# Textura procedural: (cor base BGR, padrão)
PROCEDURAL = {
    "arroz_branco": ((225, 232, 236), "grao"),
    "arroz_integral": ((120, 160, 190), "grao"),
    "feijao": ((40, 60, 110), "grao_grande"),
    "farofa": ((90, 170, 215), "grao"),
    "batata_frita": ((70, 190, 235), "palito"),
    "salada_folhas": ((60, 170, 80), "folha"),
    "tomate": ((50, 60, 210), "pedaco"),
    "abobrinha": ((110, 200, 170), "pedaco"),
    "couve_flor": ((205, 225, 235), "grao_grande"),
    "macarrao": ((110, 200, 235), "palito"),
    "lasanha": ((70, 120, 205), "liso"),
    "frango": ((120, 175, 215), "pedaco"),
    "strogonoff": ((110, 150, 200), "liso"),
    "linguica": ((70, 80, 170), "pedaco"),
    "alcatra": ((60, 80, 120), "pedaco"),
    "picanha": ((80, 95, 150), "pedaco"),
    "file_mignon": ((55, 70, 110), "pedaco"),
    "camarao": ((120, 150, 245), "pedaco"),
    "pudim": ((90, 185, 230), "liso"),
}


def textura_procedural(rotulo: str, tam: int, rng: np.random.Generator) -> np.ndarray:
    cor, padrao = PROCEDURAL[rotulo]
    base = np.full((tam, tam, 3), cor, np.float32)
    base += rng.normal(0, 10, (tam, tam, 1))
    img = base.copy()
    escuro = np.clip(np.array(cor, np.float32) * 0.6, 0, 255)
    claro = np.clip(np.array(cor, np.float32) * 1.15 + 15, 0, 255)
    n = tam * tam // 60
    if padrao in ("grao", "grao_grande"):
        r = 2 if padrao == "grao" else 5
        for _ in range(n // (1 if padrao == "grao" else 4)):
            x, y = rng.integers(0, tam, 2)
            ang = int(rng.integers(0, 180))
            cv2.ellipse(img, (int(x), int(y)), (r + 1, r), ang, 0, 360,
                        (claro if rng.random() < 0.6 else escuro).tolist(), -1)
    elif padrao == "palito":
        for _ in range(n // 6):
            x, y = rng.integers(0, tam, 2)
            ang = rng.uniform(0, math.pi)
            dx, dy = int(18 * math.cos(ang)), int(18 * math.sin(ang))
            cv2.line(img, (int(x) - dx, int(y) - dy), (int(x) + dx, int(y) + dy),
                     (claro if rng.random() < 0.7 else escuro).tolist(), 5)
    elif padrao == "folha":
        for _ in range(n // 8):
            x, y = rng.integers(0, tam, 2)
            cv2.ellipse(img, (int(x), int(y)), (int(rng.integers(6, 16)), int(rng.integers(3, 7))),
                        int(rng.integers(0, 180)), 0, 360,
                        (claro if rng.random() < 0.5 else escuro).tolist(), -1)
    elif padrao == "pedaco":
        for _ in range(n // 30):
            x, y = rng.integers(0, tam, 2)
            s = int(rng.integers(10, 22))
            pts = np.array([[x + rng.integers(-s, s), y + rng.integers(-s, s)] for _ in range(5)], np.int32)
            cv2.fillPoly(img, [cv2.convexHull(pts)], (claro if rng.random() < 0.5 else escuro).tolist())
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return np.clip(img, 0, 255).astype(np.uint8)


class BancoTexturas:
    def __init__(self, pasta: Path, rng: np.random.Generator):
        self.rng = rng
        self.reais: dict[str, list[np.ndarray]] = {}
        self.fundos: list[np.ndarray] = []
        if pasta.exists():
            for d in pasta.iterdir():
                imgs = [cv2.imread(str(p)) for p in sorted(d.glob("*.png"))]
                imgs = [i for i in imgs if i is not None]
                if d.name == "_fundos":
                    self.fundos = imgs
                elif imgs:
                    self.reais[d.name] = imgs

    def _patch(self, rotulo: str, escala: float) -> np.ndarray:
        patch = self.reais[rotulo][self.rng.integers(len(self.reais[rotulo]))]
        patch = cv2.resize(patch, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
        patch = np.rot90(patch, int(self.rng.integers(4)))
        if self.rng.random() < 0.5:
            patch = patch[:, ::-1]
        return np.ascontiguousarray(patch).astype(np.float32)

    def textura(self, rotulo: str, w: int, h: int, escala: float) -> np.ndarray:
        """Preenche w×h com recortes reais emendados por mistura suave (quilting),
        mantendo o tamanho natural dos grãos; sem textura real, usa a procedural."""
        if rotulo in self.reais and self.rng.random() < 0.9:
            tela = np.zeros((h, w, 3), np.float32)
            peso = np.full((h, w), 1e-6, np.float32)
            menor = min(min(p.shape[:2]) for p in self.reais[rotulo])
            passo = max(8, int(menor * escala * 0.9 * 0.5))   # garante sobreposição entre recortes
            for y in range(-passo // 2, h, passo):
                for x in range(-passo // 2, w, passo):
                    q = self._patch(rotulo, escala * self.rng.uniform(0.9, 1.1))
                    qh, qw = q.shape[:2]
                    jan = np.outer(np.hanning(qh + 2)[1:-1], np.hanning(qw + 2)[1:-1]).astype(np.float32)
                    y0 = y + int(self.rng.integers(-passo // 4, passo // 4 + 1))
                    x0 = x + int(self.rng.integers(-passo // 4, passo // 4 + 1))
                    ya, yb, xa, xb = max(0, y0), min(h, y0 + qh), max(0, x0), min(w, x0 + qw)
                    if ya >= yb or xa >= xb:
                        continue
                    tela[ya:yb, xa:xb] += q[ya - y0:yb - y0, xa - x0:xb - x0] * jan[ya - y0:yb - y0, xa - x0:xb - x0, None]
                    peso[ya:yb, xa:xb] += jan[ya - y0:yb - y0, xa - x0:xb - x0]
            saida = tela / peso[..., None]
            vazio = peso < 0.05                       # cobre eventuais frestas com a cor média
            if vazio.any():
                saida[vazio] = saida[~vazio].mean(axis=0) if (~vazio).any() else 128
            return np.clip(saida, 0, 255).astype(np.uint8)
        tex = textura_procedural(rotulo, 256, self.rng)
        reps = (h // 256 + 1, w // 256 + 1, 1)
        return np.tile(tex, reps)[:h, :w]

    def fundo(self, tam: int) -> np.ndarray:
        if self.fundos and self.rng.random() < 0.8:
            f = self.fundos[self.rng.integers(len(self.fundos))]
            f = cv2.resize(f, (tam, tam), interpolation=cv2.INTER_CUBIC)
            if self.rng.random() < 0.5:
                f = f[::-1]
            return np.ascontiguousarray(f)
        cor = self.rng.integers(60, 200, 3)
        img = np.full((tam, tam, 3), cor, np.uint8).astype(np.float32)
        img += self.rng.normal(0, 8, img.shape)
        return np.clip(img, 0, 255).astype(np.uint8)


def mancha(cx: float, cy: float, raio: float, tam: int, rng: np.random.Generator) -> np.ndarray:
    """Máscara irregular (porção de comida)."""
    n = 18
    fases = rng.uniform(0, 2 * math.pi, 3)
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        r = raio * (1 + 0.18 * math.sin(2 * a + fases[0]) + 0.12 * math.sin(3 * a + fases[1])
                    + rng.uniform(-0.08, 0.08))
        pts.append([cx + r * math.cos(a), cy + r * 0.92 * math.sin(a)])
    m = np.zeros((tam, tam), np.uint8)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 255)
    m = cv2.GaussianBlur(m, (9, 9), 0)
    return m > 127


def montar_prato(banco: BancoTexturas, nomes: list[str], cfg: dict, rng: np.random.Generator):
    tam = cfg["tamanho"]
    img = banco.fundo(tam).astype(np.float32)

    # prato branco com sombra e borda
    cx, cy = tam / 2 + rng.uniform(-30, 30), tam / 2 + rng.uniform(-30, 30)
    R = tam * rng.uniform(0.40, 0.47)
    sombra = np.zeros((tam, tam), np.float32)
    cv2.circle(sombra, (int(cx + 8), int(cy + 10)), int(R), 1.0, -1)
    sombra = cv2.GaussianBlur(sombra, (41, 41), 0)
    img *= (1 - 0.35 * sombra[..., None])
    branco = float(rng.uniform(228, 250))
    prato = np.zeros((tam, tam), np.uint8)
    cv2.circle(prato, (int(cx), int(cy)), int(R), 255, -1)
    img[prato > 0] = branco
    cv2.circle(img, (int(cx), int(cy)), int(R), (branco - 25,) * 3, 3)
    cv2.circle(img, (int(cx), int(cy)), int(R * 0.80), (branco - 12,) * 3, 1)

    # escolhe os alimentos
    freq = cfg["frequencia"]
    k_min, k_max = cfg["itens_por_prato"]
    k = int(rng.integers(k_min, k_max + 1))
    candidatos = [n for n in nomes if freq.get(n, 0) > 0]
    pesos = np.array([freq[n] for n in candidatos])
    escolhidos = list(rng.choice(candidatos, size=min(k, len(candidatos)), replace=False, p=pesos / pesos.sum()))

    rotulos = np.full((tam, tam), -1, np.int16)
    base = rng.uniform(0, 2 * math.pi)
    escala_tex = (R / 230) * rng.uniform(0.8, 1.2)   # pratos das fotos têm raio de ~200 a 300 px
    for i, rotulo in enumerate(escolhidos):
        ang = base + 2 * math.pi * i / len(escolhidos) + rng.uniform(-0.25, 0.25)
        dist = R * rng.uniform(0.28, 0.50)
        raio = R * rng.uniform(0.30, 0.46)
        m = mancha(cx + dist * math.cos(ang), cy + dist * math.sin(ang), raio, tam, rng)
        m &= prato > 0
        ys, xs = np.where(m)
        if len(xs) == 0:
            continue
        x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        tex = banco.textura(rotulo, x2 - x1, y2 - y1, escala_tex).astype(np.float32)
        tex *= rng.uniform(0.9, 1.1)
        regiao = m[y1:y2, x1:x2]
        # leve sombra na borda da porção
        borda = cv2.GaussianBlur(regiao.astype(np.float32), (11, 11), 0)
        fator = 0.75 + 0.25 * borda
        bloco = img[y1:y2, x1:x2]
        bloco[regiao] = (tex * fator[..., None])[regiao]
        rotulos[y1:y2, x1:x2][regiao] = nomes.index(rotulo)

    # iluminação e ruído de câmera
    img = img * rng.uniform(0.85, 1.12) + rng.uniform(-12, 12)
    img += np.array([rng.uniform(-8, 8), 0, rng.uniform(-8, 8)])
    img += rng.normal(0, 3, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        img = cv2.GaussianBlur(img, (3, 3), 0)
    return img, rotulos


def rotulos_yolo(rotulos: np.ndarray, area_min: int) -> tuple[list[str], dict[str, int]]:
    """Polígonos normalizados (um por região visível) e área visível por classe."""
    h, w = rotulos.shape
    linhas, areas = [], {}
    for cls in np.unique(rotulos):
        if cls < 0:
            continue
        m = (rotulos == cls).astype(np.uint8)
        n, comp, stats, _ = cv2.connectedComponentsWithStats(m)
        for j in range(1, n):
            if stats[j, cv2.CC_STAT_AREA] < area_min:
                continue
            reg = (comp == j).astype(np.uint8)
            contornos, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            c = max(contornos, key=cv2.contourArea)
            c = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2)
            if len(c) < 3:
                continue
            coords = " ".join(f"{x / w:.5f} {y / h:.5f}" for x, y in c)
            linhas.append(f"{int(cls)} {coords}")
            areas[int(cls)] = areas.get(int(cls), 0) + int(stats[j, cv2.CC_STAT_AREA])
    return linhas, areas


def main() -> None:
    cfg = carregar_yaml("sintetico.yaml")
    tex_dir = caminho_config(carregar_yaml("texturas.yaml")["saida_dir"])
    nomes = classes()
    rng = np.random.default_rng(cfg["semente"])
    random.seed(cfg["semente"])
    banco = BancoTexturas(tex_dir, rng)
    print(f"Texturas reais: {sorted(banco.reais)} · fundos: {len(banco.fundos)}")

    destino = caminho_dataset()
    if destino.exists():
        shutil.rmtree(destino)
    composicao = {}
    for split, qtd in (("train", cfg["imagens_treino"]), ("val", cfg["imagens_validacao"]),
                       ("test", cfg["imagens_teste"])):
        (destino / "images" / split).mkdir(parents=True)
        (destino / "labels" / split).mkdir(parents=True)
        for i in range(qtd):
            img, rot = montar_prato(banco, nomes, cfg, rng)
            linhas, areas = rotulos_yolo(rot, cfg["area_minima_px"])
            nome = f"{split}_{i:04d}"
            cv2.imwrite(str(destino / "images" / split / f"{nome}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (destino / "labels" / split / f"{nome}.txt").write_text("\n".join(linhas))
            total = sum(areas.values()) or 1
            composicao[f"{split}/{nome}.jpg"] = {nomes[c]: round(100 * a / total, 2) for c, a in areas.items()}
        print(f"  {split}: {qtd} imagens")
    (destino / "composicao.json").write_text(json.dumps(composicao, indent=1, ensure_ascii=False))
    print(f"Dataset salvo em {destino}")


if __name__ == "__main__":
    main()
