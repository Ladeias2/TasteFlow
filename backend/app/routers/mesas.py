"""Mapa do salão operado pela equipe (tablet): ocupação, limpeza e painel (módulo Mesas).

O cliente não interage com nada: o garçom toca na mesa quando o grupo senta,
e os funcionários tocam de novo para marcar saída, início e fim da limpeza.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.engine import Connection

from ..database import call_procedure, execute, fetch_all, fetch_one, get_conn
from ..errors import conflito, nao_encontrado
from ..schemas import AvancarIn, MesaIn, OcuparIn, VincularIn
from ..services.regras import exigir_aberta, obter_comanda

router = APIRouter(tags=["Mesas"])


def _mesa(conn: Connection, numero: int) -> dict:
    mesa = fetch_one(conn, "SELECT * FROM mesa WHERE numero_mesa = :n", n=numero)
    if mesa is None:
        raise nao_encontrado("Mesa")
    return mesa


def _ciclo_atual(conn: Connection, id_mesa: int) -> dict | None:
    ciclo = fetch_one(conn,
                      "SELECT * FROM ocupacao_mesa WHERE id_mesa = :m "
                      "ORDER BY data_hora_ocupada DESC, id_ocupacao DESC LIMIT 1", m=id_mesa)
    if ciclo:
        ciclo["comandas"] = [r["id_comanda"] for r in fetch_all(
            conn, "SELECT id_comanda FROM ocupacao_comanda WHERE id_ocupacao = :o",
            o=ciclo["id_ocupacao"])]
    return ciclo


def _vincular(conn: Connection, ciclo: dict, id_comanda: str) -> None:
    exigir_aberta(obter_comanda(conn, id_comanda))
    outra = fetch_one(conn,
                      "SELECT m.numero_mesa FROM ocupacao_comanda oc "
                      "JOIN ocupacao_mesa o ON o.id_ocupacao = oc.id_ocupacao "
                      "JOIN mesa m ON m.id_mesa = o.id_mesa "
                      "WHERE oc.id_comanda = :c AND o.status_mesa = 'ocupada' AND o.id_ocupacao <> :o",
                      c=id_comanda, o=ciclo["id_ocupacao"])
    if outra:
        raise conflito(f"Comanda {id_comanda} já está vinculada à mesa {outra['numero_mesa']}.")
    execute(conn, "INSERT IGNORE INTO ocupacao_comanda (id_ocupacao, id_comanda) VALUES (:o, :c)",
            o=ciclo["id_ocupacao"], c=id_comanda)


def _garcom_existe(conn: Connection, id_garcom: int | None) -> None:
    if id_garcom is not None and fetch_one(conn, "SELECT 1 AS ok FROM garcom WHERE id_garcom = :g",
                                           g=id_garcom) is None:
        raise nao_encontrado("Funcionário")


@router.get("/mesas", summary="Mapa do salão em tempo real (verde / amarelo / vermelho)")
def painel_mesas(conn: Connection = Depends(get_conn)):
    """Lê `vw_mesas_agora`. `alerta_limpeza = 1` quando a mesa está suja há mais de 5 min."""
    mesas = fetch_all(conn, "SELECT * FROM vw_mesas_agora ORDER BY numero_mesa")
    resumo = {cor: sum(1 for m in mesas if m["cor"] == cor) for cor in ("verde", "amarelo", "vermelho")}
    return {"resumo": resumo,
            "alertas": [m["numero_mesa"] for m in mesas if m["alerta_limpeza"]],
            "mesas": mesas}


@router.post("/mesas", status_code=status.HTTP_201_CREATED, summary="Cadastrar mesa")
def cadastrar_mesa(dados: MesaIn, conn: Connection = Depends(get_conn)):
    execute(conn, "INSERT INTO mesa (numero_mesa, capacidade) VALUES (:n, :c)",
            n=dados.numero_mesa, c=dados.capacidade)
    return _mesa(conn, dados.numero_mesa)


@router.get("/mesas/{numero}", summary="Mesa e ciclo atual")
def detalhar_mesa(numero: int, conn: Connection = Depends(get_conn)):
    mesa = _mesa(conn, numero)
    return {**mesa, "ciclo_atual": _ciclo_atual(conn, mesa["id_mesa"])}


@router.post("/mesas/{numero}/ocupar", summary="Garçom registra a chegada do grupo")
def ocupar(numero: int, dados: OcuparIn | None = None, conn: Connection = Depends(get_conn)):
    """Chama `sp_ocupar_mesa`. Recusa (409) se a mesa estiver ocupada ou
    aguardando limpeza. Vincular as comandas do grupo é opcional."""
    dados = dados or OcuparIn()
    mesa = _mesa(conn, numero)
    if dados.qtd_pessoas > mesa["capacidade"] + 2:
        raise conflito(f"Grupo de {dados.qtd_pessoas} excede a capacidade da mesa ({mesa['capacidade']}).")
    _garcom_existe(conn, dados.id_garcom)
    call_procedure(conn, "sp_ocupar_mesa", numero, dados.qtd_pessoas, dados.id_garcom)
    ciclo = _ciclo_atual(conn, mesa["id_mesa"])
    for id_comanda in dict.fromkeys(dados.comandas):
        _vincular(conn, ciclo, id_comanda)
    return {**mesa, "ciclo_atual": _ciclo_atual(conn, mesa["id_mesa"])}


@router.post("/mesas/{numero}/comandas", summary="Vincular comanda ao grupo (opcional)")
def vincular_comanda(numero: int, dados: VincularIn, conn: Connection = Depends(get_conn)):
    mesa = _mesa(conn, numero)
    ciclo = _ciclo_atual(conn, mesa["id_mesa"])
    if not ciclo or ciclo["status_mesa"] != "ocupada":
        raise conflito("Mesa não está ocupada.")
    _vincular(conn, ciclo, dados.id_comanda)
    return {**mesa, "ciclo_atual": _ciclo_atual(conn, mesa["id_mesa"])}


@router.post("/mesas/{numero}/avancar", summary="Funcionário avança o ciclo uma etapa")
def avancar(numero: int, dados: AvancarIn | None = None, conn: Connection = Depends(get_conn)):
    """Chama `sp_avancar_status_mesa`: ocupada → desocupada → limpeza → pronta.
    O funcionário informado na etapa de limpeza fica registrado como responsável."""
    mesa = _mesa(conn, numero)
    id_garcom = dados.id_garcom if dados else None
    _garcom_existe(conn, id_garcom)
    call_procedure(conn, "sp_avancar_status_mesa", numero, id_garcom)
    return {**mesa, "ciclo_atual": _ciclo_atual(conn, mesa["id_mesa"])}
