"""Estação de descarte e produção das cubas (módulo Sobras)."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.engine import Connection

from ..database import execute, fetch_all, fetch_one, get_conn
from ..errors import conflito, nao_encontrado
from ..schemas import ProducaoIn, SobraIn
from ..services import visao
from ..services.regras import mapear_rotulos, salvar_upload

router = APIRouter(tags=["Sobras e Produção"])


def _registrar_sobra(conn: Connection, id_pesagem: int, peso: int, url_foto: str | None,
                     itens: list[dict]) -> dict:
    pesagem = fetch_one(conn, "SELECT peso_gramas FROM pratos_kilo WHERE id_pesagem = :p", p=id_pesagem)
    if pesagem is None:
        raise nao_encontrado("Pesagem")
    if peso > pesagem["peso_gramas"]:
        raise conflito(f"Sobra ({peso} g) maior que o prato servido ({pesagem['peso_gramas']} g).")
    if fetch_one(conn, "SELECT 1 AS ok FROM sobra_prato WHERE id_pesagem = :p", p=id_pesagem):
        raise conflito("Sobra desta pesagem já registrada.")

    # Converte percentuais em gramas; gramas informados não podem passar do total
    gramas = []
    for i in itens:
        g = i["peso_gramas"] if i.get("peso_gramas") is not None else round(peso * i["percentual"] / 100)
        gramas.append((i["rotulo"], g, i.get("confianca")))
    if sum(g for _, g, _ in gramas) > peso:
        raise HTTPException(status_code=422, detail="Soma dos itens maior que o peso da sobra.")
    mapa = mapear_rotulos(conn, [r for r, _, _ in gramas])

    id_sobra = execute(conn, "INSERT INTO sobra_prato (id_pesagem, peso_sobra_gramas, url_foto) "
                             "VALUES (:p, :g, :u)", p=id_pesagem, g=peso, u=url_foto)
    for rotulo, g, conf in gramas:
        execute(conn, "INSERT INTO composicao_sobra (id_sobra, id_ingrediente, peso_gramas, confianca_ia) "
                      "VALUES (:s, :i, :g, :c)",
                s=id_sobra, i=mapa[rotulo]["id_ingrediente"], g=g, c=conf)
    return _detalhe(conn, id_sobra)


def _detalhe(conn: Connection, id_sobra: int) -> dict:
    sobra = fetch_one(conn, "SELECT * FROM sobra_prato WHERE id_sobra = :s", s=id_sobra)
    sobra["itens"] = fetch_all(conn,
                               "SELECT i.rotulo_ia AS rotulo, i.nome_ingrediente, cs.peso_gramas, "
                               "       ROUND(cs.peso_gramas / 1000 * i.custo_kg, 2) AS custo, cs.confianca_ia "
                               "FROM composicao_sobra cs JOIN ingrediente i USING (id_ingrediente) "
                               "WHERE cs.id_sobra = :s ORDER BY cs.peso_gramas DESC", s=id_sobra)
    sobra["custo_sobra"] = sum((i["custo"] for i in sobra["itens"]), 0)
    return sobra


@router.post("/sobras", status_code=status.HTTP_201_CREATED,
             summary="Registrar sobra do prato (composição já identificada)")
def registrar_sobra(dados: SobraIn, conn: Connection = Depends(get_conn)):
    return _registrar_sobra(conn, dados.id_pesagem, dados.peso_sobra_gramas, dados.url_foto,
                            [i.model_dump() for i in dados.itens])


@router.post("/sobras/foto", status_code=status.HTTP_201_CREATED,
             summary="Registrar sobra enviando a foto (inferência no servidor)")
def registrar_sobra_foto(id_pesagem: int = Form(...),
                         peso_sobra_gramas: int = Form(..., ge=0),
                         foto: UploadFile = File(...),
                         conn: Connection = Depends(get_conn)):
    try:
        visao._modelo()
    except visao.VisaoIndisponivel as exc:
        raise HTTPException(status_code=503, detail=f"Visão computacional indisponível: {exc}")
    caminho = salvar_upload(foto, "sobras", str(id_pesagem))
    itens = visao.classificar_imagem(caminho)
    return _registrar_sobra(conn, id_pesagem, peso_sobra_gramas, caminho, itens)


@router.post("/producao", summary="Registrar produção e descarte da cuba (fim do turno)")
def registrar_producao(dados: ProducaoIn, conn: Connection = Depends(get_conn)):
    """Grava ou atualiza (mesmo dia + turno + ingrediente)."""
    ing = mapear_rotulos(conn, [dados.rotulo])[dados.rotulo]
    execute(conn,
            "INSERT INTO producao_cuba (data_producao, turno, id_ingrediente, "
            "peso_produzido_gramas, peso_descartado_gramas) VALUES (:d, :t, :i, :p, :x) "
            "ON DUPLICATE KEY UPDATE peso_produzido_gramas = VALUES(peso_produzido_gramas), "
            "peso_descartado_gramas = VALUES(peso_descartado_gramas)",
            d=dados.data_producao, t=dados.turno.value, i=ing["id_ingrediente"],
            p=dados.peso_produzido_gramas, x=dados.peso_descartado_gramas)
    return fetch_one(conn,
                     "SELECT pc.*, i.rotulo_ia AS rotulo, i.nome_ingrediente FROM producao_cuba pc "
                     "JOIN ingrediente i USING (id_ingrediente) "
                     "WHERE data_producao = :d AND turno = :t AND pc.id_ingrediente = :i",
                     d=dados.data_producao, t=dados.turno.value, i=ing["id_ingrediente"])
