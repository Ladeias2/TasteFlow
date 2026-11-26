"""Cadastros de apoio: garçons e ingredientes."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.engine import Connection

from ..database import execute, fetch_all, fetch_one, get_conn
from ..errors import nao_encontrado
from ..schemas import GarcomIn, IngredienteIn, IngredienteUpdate

router = APIRouter(tags=["Cadastros"])


@router.get("/garcons", summary="Listar funcionários")
def listar_garcons(apenas_ativos: bool = True, conn: Connection = Depends(get_conn)):
    sql = "SELECT * FROM garcom" + (" WHERE ativo" if apenas_ativos else "") + " ORDER BY nome"
    return fetch_all(conn, sql)


@router.post("/garcons", status_code=status.HTTP_201_CREATED, summary="Cadastrar funcionário")
def cadastrar_garcom(dados: GarcomIn, conn: Connection = Depends(get_conn)):
    id_garcom = execute(conn, "INSERT INTO garcom (nome, ativo) VALUES (:n, :a)",
                        n=dados.nome, a=dados.ativo)
    return fetch_one(conn, "SELECT * FROM garcom WHERE id_garcom = :g", g=id_garcom)


@router.get("/ingredientes", summary="Listar ingredientes e custo/kg")
def listar_ingredientes(conn: Connection = Depends(get_conn)):
    return fetch_all(conn, "SELECT * FROM ingrediente ORDER BY categoria, nome_ingrediente")


@router.post("/ingredientes", status_code=status.HTTP_201_CREATED,
             summary="Cadastrar ingrediente (nova classe do modelo de IA)")
def cadastrar_ingrediente(dados: IngredienteIn, conn: Connection = Depends(get_conn)):
    id_ing = execute(conn,
                     "INSERT INTO ingrediente (nome_ingrediente, rotulo_ia, categoria, estacao, custo_kg) "
                     "VALUES (:n, :r, :c, :e, :k)",
                     n=dados.nome_ingrediente, r=dados.rotulo_ia, c=dados.categoria.value,
                     e=dados.estacao.value, k=dados.custo_kg)
    return fetch_one(conn, "SELECT * FROM ingrediente WHERE id_ingrediente = :i", i=id_ing)


@router.patch("/ingredientes/{rotulo}", summary="Atualizar custo/kg ou desativar ingrediente")
def atualizar_ingrediente(rotulo: str, dados: IngredienteUpdate, conn: Connection = Depends(get_conn)):
    """O novo custo vale só para pesagens futuras: as anteriores mantêm o
    `custo_kg_aplicado` congelado, preservando o histórico do CRC."""
    atual = fetch_one(conn, "SELECT * FROM ingrediente WHERE rotulo_ia = :r", r=rotulo)
    if atual is None:
        raise nao_encontrado("Ingrediente")
    execute(conn, "UPDATE ingrediente SET custo_kg = COALESCE(:k, custo_kg), "
                  "ativo = COALESCE(:a, ativo) WHERE rotulo_ia = :r",
            k=dados.custo_kg, a=dados.ativo, r=rotulo)
    return fetch_one(conn, "SELECT * FROM ingrediente WHERE rotulo_ia = :r", r=rotulo)
