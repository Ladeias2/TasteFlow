"""Regras de negócio compartilhadas entre os routers."""
import secrets
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.engine import Connection

from ..config import settings
from ..database import execute, fetch_all, fetch_one
from ..errors import conflito, nao_encontrado


# ---------------------------------------------------------------- comandas
def gerar_id_comanda() -> str:
    """Código não sequencial (12 hex) — impossível de adivinhar no QR da nota."""
    return f"CMD-{secrets.token_hex(6).upper()}"


def obter_comanda(conn: Connection, id_comanda: str) -> dict:
    comanda = fetch_one(conn, "SELECT * FROM comanda WHERE id_comanda_aleatoria = :id", id=id_comanda)
    if comanda is None:
        raise nao_encontrado("Comanda")
    return comanda


def exigir_aberta(comanda: dict) -> None:
    if comanda["data_hora_pago"] is not None:
        raise conflito("Comanda já foi paga.")


def exigir_paga(comanda: dict) -> None:
    if comanda["data_hora_pago"] is None:
        raise conflito("Comanda ainda não foi paga.")


def preco_kg_do_dia(dia: date | None = None) -> Decimal:
    dia = dia or date.today()
    return settings.preco_kg_fim_semana if dia.weekday() >= 5 else settings.preco_kg_semana


# ---------------------------------------------------------------- ingredientes
def mapear_rotulos(conn: Connection, rotulos: list[str]) -> dict[str, dict]:
    """rótulo da IA → {id_ingrediente, custo_kg}. 422 se algum não existir."""
    if not rotulos:
        return {}
    params = {f"r{n}": r for n, r in enumerate(rotulos)}
    linhas = fetch_all(
        conn,
        "SELECT id_ingrediente, rotulo_ia, custo_kg FROM ingrediente "
        f"WHERE ativo AND rotulo_ia IN ({', '.join(':' + k for k in params)})",
        **params)
    mapa = {r["rotulo_ia"]: r for r in linhas}
    faltando = sorted(set(rotulos) - mapa.keys())
    if faltando:
        raise HTTPException(status_code=422,
                            detail=f"Rótulos sem ingrediente ativo cadastrado: {', '.join(faltando)}")
    return mapa


def normalizar_percentuais(itens: list[dict]) -> list[dict]:
    """Garante soma 100 (a IA pode devolver 98,7% por arredondamento)."""
    total = sum(i["percentual"] for i in itens)
    if total <= 0:
        return []
    saida = [{**i, "percentual": round(100 * i["percentual"] / total, 2)} for i in itens]
    return [i for i in saida if i["percentual"] > 0]


def gravar_composicao(conn: Connection, id_pesagem: int, itens: list[dict], origem: str) -> list[dict]:
    """Substitui a composição de uma pesagem, congelando o custo/kg atual."""
    itens = normalizar_percentuais(itens)
    mapa = mapear_rotulos(conn, [i["rotulo"] for i in itens])
    execute(conn, "DELETE FROM composicao_prato WHERE id_pesagem = :p", p=id_pesagem)
    for item in itens:
        ing = mapa[item["rotulo"]]
        execute(conn,
                "INSERT INTO composicao_prato (id_pesagem, id_ingrediente, percentual, "
                "custo_kg_aplicado, confianca_ia, origem_classificacao) "
                "VALUES (:p, :i, :pct, :custo, :conf, :origem)",
                p=id_pesagem, i=ing["id_ingrediente"], pct=item["percentual"],
                custo=ing["custo_kg"], conf=item.get("confianca"), origem=origem)
    return itens


def resumo_pesagem(conn: Connection, id_pesagem: int) -> dict:
    """Pesagem + ICC + composição em gramas e custo."""
    pesagem = fetch_one(conn, "SELECT * FROM pratos_kilo WHERE id_pesagem = :p", p=id_pesagem)
    if pesagem is None:
        raise nao_encontrado("Pesagem")
    itens = fetch_all(
        conn,
        "SELECT i.rotulo_ia AS rotulo, i.nome_ingrediente, i.categoria, cp.percentual, "
        "       ROUND(pk.peso_gramas * cp.percentual / 100) AS gramas_estimados, "
        "       cp.custo_kg_aplicado, "
        "       ROUND(pk.peso_gramas * cp.percentual / 100 / 1000 * cp.custo_kg_aplicado, 2) AS custo, "
        "       cp.confianca_ia, cp.origem_classificacao "
        "FROM composicao_prato cp "
        "JOIN pratos_kilo pk ON pk.id_pesagem = cp.id_pesagem "
        "JOIN ingrediente i ON i.id_ingrediente = cp.id_ingrediente "
        "WHERE cp.id_pesagem = :p ORDER BY cp.percentual DESC", p=id_pesagem)
    icc = sum((i["custo"] for i in itens), Decimal("0"))
    confs = [float(i["confianca_ia"]) for i in itens if i["confianca_ia"] is not None]
    conf_media = round(sum(confs) / len(confs), 3) if confs else None
    revisao = (not itens) or (conf_media is not None and conf_media < settings.confianca_minima)
    return {
        **pesagem,
        "icc": icc if itens else None,
        "margem": (pesagem["valor_prato"] - icc) if itens else None,
        "confianca_media": conf_media,
        "revisao_necessaria": revisao,
        "composicao": itens,
    }


# ---------------------------------------------------------------- arquivos
def salvar_upload(arquivo: UploadFile, subpasta: str, nome_base: str) -> str:
    """Grava a foto em PASTA_FOTOS/<subpasta>/ e devolve o caminho relativo."""
    ext = Path(arquivo.filename or "").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=415, detail="Formato de imagem não suportado.")
    destino_dir = Path(settings.pasta_fotos) / subpasta
    destino_dir.mkdir(parents=True, exist_ok=True)
    nome = f"{nome_base}-{datetime.now():%Y%m%d%H%M%S}{ext}"
    destino = destino_dir / nome
    with destino.open("wb") as f:
        shutil.copyfileobj(arquivo.file, f)
    return str(destino)
