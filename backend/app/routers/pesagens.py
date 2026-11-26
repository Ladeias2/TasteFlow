"""Estação balança + câmera: pesagem, foto e composição do prato (módulo Mix e Custo)."""
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.engine import Connection

from ..config import settings
from ..database import execute, fetch_one, get_conn
from ..schemas import ComposicaoManualIn, PesagemIn
from ..services import visao
from ..services.regras import (exigir_aberta, gravar_composicao, obter_comanda,
                               preco_kg_do_dia, resumo_pesagem, salvar_upload)

router = APIRouter(tags=["Pesagens (Mix e Custo)"])


def _registrar(conn: Connection, id_comanda: str, peso: int, preco: Decimal | None,
               url_foto: str | None, versao: str | None, itens: list[dict]) -> dict:
    exigir_aberta(obter_comanda(conn, id_comanda))
    seq = fetch_one(conn, "SELECT COALESCE(MAX(sequencia_peso), 0) + 1 AS s "
                          "FROM pratos_kilo WHERE id_comanda = :c", c=id_comanda)["s"]
    id_pesagem = execute(conn,
                         "INSERT INTO pratos_kilo (id_comanda, peso_gramas, preco_kg_aplicado, "
                         "sequencia_peso) VALUES (:c, :p, :preco, :s)",
                         c=id_comanda, p=peso, preco=preco or preco_kg_do_dia(), s=seq)
    if url_foto:
        execute(conn, "INSERT INTO foto_prato (id_pesagem, url_foto, versao_modelo) "
                      "VALUES (:p, :u, :v)", p=id_pesagem, u=url_foto, v=versao)
    if itens:
        gravar_composicao(conn, id_pesagem, itens, origem="ia")
    return resumo_pesagem(conn, id_pesagem)


@router.post("/pesagens", status_code=status.HTTP_201_CREATED,
             summary="Registrar pesagem com a composição já identificada pela IA")
def registrar_pesagem(dados: PesagemIn, conn: Connection = Depends(get_conn)):
    """Usado quando a inferência roda na própria estação (borda).

    A API calcula a sequência do prato, aplica o preço do kg do dia (se não
    informado), normaliza os percentuais para 100%, congela o custo/kg de cada
    ingrediente e devolve o ICC do prato. Se a confiança média ficar abaixo de
    `CONFIANCA_MINIMA`, a resposta indica `revisao_necessaria = true`.
    """
    return _registrar(conn, dados.id_comanda, dados.peso_gramas, dados.preco_kg_aplicado,
                      dados.url_foto, dados.versao_modelo,
                      [i.model_dump() for i in dados.itens])


@router.post("/pesagens/foto", status_code=status.HTTP_201_CREATED,
             summary="Registrar pesagem enviando a foto (inferência no servidor)")
def registrar_pesagem_foto(id_comanda: str = Form(...),
                           peso_gramas: int = Form(..., gt=0, le=5000),
                           preco_kg_aplicado: Decimal | None = Form(None),
                           foto: UploadFile = File(...),
                           conn: Connection = Depends(get_conn)):
    try:
        visao._modelo()  # falha cedo, antes de gravar qualquer coisa
    except visao.VisaoIndisponivel as exc:
        raise HTTPException(status_code=503, detail=f"Visão computacional indisponível: {exc}")
    exigir_aberta(obter_comanda(conn, id_comanda))
    caminho = salvar_upload(foto, "pratos", id_comanda)
    itens = visao.classificar_imagem(caminho)
    return _registrar(conn, id_comanda, peso_gramas, preco_kg_aplicado,
                      caminho, settings.versao_modelo, itens)


@router.get("/pesagens/{id_pesagem}", summary="Pesagem com composição, ICC e margem")
def detalhar_pesagem(id_pesagem: int, conn: Connection = Depends(get_conn)):
    return resumo_pesagem(conn, id_pesagem)


@router.put("/pesagens/{id_pesagem}/composicao",
            summary="Corrigir manualmente a composição (baixa confiança da IA)")
def corrigir_composicao(id_pesagem: int, dados: ComposicaoManualIn,
                        conn: Connection = Depends(get_conn)):
    """Substitui a composição; os itens ficam com `origem_classificacao = 'manual'`
    e servem de dado rotulado para retreinar o modelo."""
    resumo_pesagem(conn, id_pesagem)  # 404 se não existir
    gravar_composicao(conn, id_pesagem, [i.model_dump() for i in dados.itens], origem="manual")
    return resumo_pesagem(conn, id_pesagem)
