"""Leitura óptica do cartão raspadinha (OMR — Optical Mark Recognition).

O cartão é depositado numa urna com encaixe fixo e uma câmera fotografa a
face raspada. Cada bolinha tem uma posição conhecida (gabarito). Raspar a
camada prateada revela a tinta escura por baixo, então uma bolinha raspada
fica bem mais escura que as demais.

Etapas:
1. `extrair_intensidades`: recorta cada bolinha da foto e mede o quanto
   ela está escura (0 = branca, 1 = preta). Usa OpenCV (opcional).
2. `decidir_marcacoes`: em cada linha escolhe a bolinha raspada e detecta
   linhas em branco ou ambíguas (duas bolinhas raspadas). Lógica pura,
   testável sem câmera.

Se alguma linha não for lida com segurança, o cartão volta para o caixa,
que digita as notas.
"""
from dataclasses import dataclass

# ------------------------------------------------------------------ gabarito
# Coordenadas normalizadas (0–1) do centro de cada bolinha na foto do cartão
# já enquadrado pela urna. Devem refletir a arte impressa do cartão.
OPCOES_NOTA = [0, 1, 2, 3, 4, 5]
OPCOES_RECOMENDA = ["sim", "talvez", "nao"]

GABARITO: dict[str, dict] = {
    "nota_comida":      {"y": 0.35, "xs": [0.40 + 0.09 * i for i in range(6)], "opcoes": OPCOES_NOTA},
    "nota_ambiente":    {"y": 0.50, "xs": [0.40 + 0.09 * i for i in range(6)], "opcoes": OPCOES_NOTA},
    "nota_atendimento": {"y": 0.65, "xs": [0.40 + 0.09 * i for i in range(6)], "opcoes": OPCOES_NOTA},
    "recomendaria":     {"y": 0.80, "xs": [0.40, 0.58, 0.76],                  "opcoes": OPCOES_RECOMENDA},
}
RAIO_RELATIVO = 0.025          # raio da bolinha em fração da largura da foto

LIMIAR_MARCADA = 0.45          # escuridão mínima para considerar raspada
MARGEM_MINIMA = 0.15           # diferença mínima para a 2ª mais escura


class LeituraIndisponivel(RuntimeError):
    pass


@dataclass
class ResultadoLinha:
    campo: str
    valor: int | str | None
    situacao: str               # 'ok' | 'em_branco' | 'ambigua'
    confianca: float


def decidir_marcacoes(intensidades: dict[str, list[float]]) -> list[ResultadoLinha]:
    """Escolhe a marcação de cada linha a partir da escuridão das bolinhas."""
    resultado = []
    for campo, cfg in GABARITO.items():
        valores = intensidades[campo]
        if len(valores) != len(cfg["opcoes"]):
            raise ValueError(f"Linha {campo}: esperadas {len(cfg['opcoes'])} bolinhas.")
        ordem = sorted(range(len(valores)), key=lambda i: valores[i], reverse=True)
        maior, segundo = valores[ordem[0]], valores[ordem[1]]
        margem = maior - segundo
        if maior < LIMIAR_MARCADA:
            resultado.append(ResultadoLinha(campo, None, "em_branco", 0.0))
        elif margem < MARGEM_MINIMA:
            resultado.append(ResultadoLinha(campo, None, "ambigua", round(max(margem, 0.0), 3)))
        else:
            conf = min(1.0, 0.5 + margem)            # margem 0,5 ou mais → confiança 1
            resultado.append(ResultadoLinha(campo, cfg["opcoes"][ordem[0]], "ok", round(conf, 3)))
    return resultado


def extrair_intensidades(caminho_imagem: str) -> dict[str, list[float]]:
    """Mede a escuridão média de cada bolinha do gabarito na foto."""
    try:
        import cv2  # dependência opcional
    except ImportError as exc:
        raise LeituraIndisponivel("Pacote 'opencv-python-headless' não instalado.") from exc

    img = cv2.imread(caminho_imagem, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Não foi possível abrir a imagem do cartão.")
    img = cv2.GaussianBlur(img, (5, 5), 0)
    altura, largura = img.shape
    raio = max(2, int(RAIO_RELATIVO * largura))

    intensidades: dict[str, list[float]] = {}
    for campo, cfg in GABARITO.items():
        cy = int(cfg["y"] * altura)
        linha = []
        for x in cfg["xs"]:
            cx = int(x * largura)
            roi = img[max(0, cy - raio):cy + raio, max(0, cx - raio):cx + raio]
            linha.append(round(1 - float(roi.mean()) / 255, 3))
        intensidades[campo] = linha
    return intensidades


def ler_cartao(caminho_imagem: str) -> tuple[dict, float, list[ResultadoLinha]]:
    """Devolve (respostas, confiança mínima, detalhes por linha)."""
    linhas = decidir_marcacoes(extrair_intensidades(caminho_imagem))
    respostas = {l.campo: l.valor for l in linhas}
    confianca = min(l.confianca for l in linhas)
    return respostas, confianca, linhas
