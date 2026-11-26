"""Análise de sentimento dos comentários escritos no cartão de satisfação.

Implementação de referência baseada em léxico do português com tratamento de
negação e intensificadores. A interface `analisar(texto) -> (rotulo, score)`
é a mesma que um modelo de linguagem pré-treinado (ex.: BERTimbau ajustado
para sentimento) deve oferecer, para que a troca seja transparente.
"""
import re
import unicodedata

_POSITIVAS = {
    "otimo": 1.0, "otima": 1.0, "excelente": 1.0, "maravilhoso": 1.0, "maravilhosa": 1.0,
    "perfeito": 1.0, "perfeita": 1.0, "delicioso": 0.9, "deliciosa": 0.9, "saboroso": 0.8,
    "saborosa": 0.8, "bom": 0.6, "boa": 0.6, "gostoso": 0.7, "gostosa": 0.7, "agradavel": 0.7,
    "limpo": 0.6, "limpa": 0.6, "rapido": 0.6, "rapida": 0.6, "atencioso": 0.8, "atenciosa": 0.8,
    "educado": 0.6, "educada": 0.6, "simpatico": 0.7, "simpatica": 0.7, "recomendo": 0.9,
    "voltarei": 0.8, "adorei": 1.0, "amei": 1.0, "gostei": 0.7, "ponto": 0.3, "fresco": 0.6,
    "fresca": 0.6, "quentinho": 0.6, "quentinha": 0.6, "variedade": 0.5, "aconchegante": 0.7,
}
_NEGATIVAS = {
    "ruim": -0.8, "pessimo": -1.0, "pessima": -1.0, "horrivel": -1.0, "frio": -0.7, "fria": -0.7,
    "sujo": -0.9, "suja": -0.9, "demorou": -0.7, "demora": -0.7, "demorado": -0.7, "lento": -0.6,
    "lenta": -0.6, "fila": -0.4, "enorme": -0.3, "caro": -0.5, "cara": -0.4, "salgado": -0.5,
    "salgada": -0.5, "cru": -0.6, "crua": -0.6, "duro": -0.6, "dura": -0.6, "seco": -0.5,
    "seca": -0.5, "barulho": -0.5, "barulhento": -0.6, "grosso": -0.8, "grossa": -0.8,
    "mal": -0.6, "decepcionante": -0.9, "decepcao": -0.9, "insosso": -0.6, "insossa": -0.6,
    "queimado": -0.7, "queimada": -0.7, "faltou": -0.5, "abafado": -0.5, "quente": -0.2,
}
_NEGACOES = {"nao", "nunca", "nem", "sem", "jamais"}
_INTENSIFICADORES = {"muito": 1.5, "super": 1.5, "bem": 1.3, "bastante": 1.3, "extremamente": 1.8,
                     "pouco": 0.5, "meio": 0.6}
_LIMIAR = 0.15


def _normalizar(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.findall(r"[a-z]+", sem_acento)


def analisar(texto: str | None) -> tuple[str | None, float | None]:
    """Devolve (sentimento, score) com score em [-1, 1]; (None, None) se vazio."""
    if not texto or not texto.strip():
        return None, None
    tokens = _normalizar(texto)
    soma, acertos = 0.0, 0
    for i, tok in enumerate(tokens):
        peso = _POSITIVAS.get(tok, _NEGATIVAS.get(tok))
        if peso is None:
            continue
        janela = tokens[max(0, i - 3):i]
        for anterior in reversed(janela):
            if anterior in _INTENSIFICADORES:
                peso *= _INTENSIFICADORES[anterior]
                break
        if any(t in _NEGACOES for t in janela):
            peso *= -0.8
        soma += peso
        acertos += 1
    if acertos == 0:
        return "neutro", 0.0
    score = max(-1.0, min(1.0, soma / acertos))
    rotulo = "positivo" if score > _LIMIAR else "negativo" if score < -_LIMIAR else "neutro"
    return rotulo, round(score, 3)
