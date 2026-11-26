"""Comandas individuais e pedidos à mesa (sistema original)."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.engine import Connection

from ..database import call_procedure, execute, fetch_all, fetch_one, get_conn
from ..errors import conflito
from ..schemas import ComandaIn, PedidoIn
from ..services.regras import (exigir_aberta, gerar_id_comanda, obter_comanda,
                               resumo_pesagem)

router = APIRouter(tags=["Comandas"])


@router.post("/comandas", status_code=status.HTTP_201_CREATED,
             summary="Gerar comanda na entrada do cliente")
def criar_comanda(dados: ComandaIn | None = None, conn: Connection = Depends(get_conn)):
    id_comanda = (dados.id_comanda_aleatoria if dados and dados.id_comanda_aleatoria
                  else gerar_id_comanda())
    execute(conn, "INSERT INTO comanda (id_comanda_aleatoria) VALUES (:id)", id=id_comanda)
    return obter_comanda(conn, id_comanda)


@router.get("/comandas/{id_comanda}", summary="Detalhe completo da comanda (cliente)")
def detalhar_comanda(id_comanda: str, conn: Connection = Depends(get_conn)):
    comanda = obter_comanda(conn, id_comanda)
    ids = fetch_all(conn, "SELECT id_pesagem FROM pratos_kilo WHERE id_comanda = :c "
                          "ORDER BY sequencia_peso", c=id_comanda)
    pesagens = [resumo_pesagem(conn, r["id_pesagem"]) for r in ids]
    pedidos = fetch_all(conn, "SELECT * FROM pedidos_mesa WHERE id_comanda = :c "
                              "ORDER BY data_hora_pedido", c=id_comanda)
    eventos = fetch_all(conn, "SELECT * FROM evento_comanda WHERE id_comanda = :c "
                              "ORDER BY data_hora_evento", c=id_comanda)
    mesa = fetch_one(conn,
                     "SELECT m.numero_mesa, o.id_ocupacao, o.status_mesa, o.data_hora_ocupada "
                     "FROM ocupacao_comanda oc "
                     "JOIN ocupacao_mesa o ON o.id_ocupacao = oc.id_ocupacao "
                     "JOIN mesa m ON m.id_mesa = o.id_mesa "
                     "WHERE oc.id_comanda = :c ORDER BY o.data_hora_ocupada DESC LIMIT 1",
                     c=id_comanda)
    tempos = fetch_one(conn, "SELECT * FROM vw_tempos_comanda WHERE id_comanda = :c", c=id_comanda)
    avaliada = fetch_one(conn, "SELECT 1 AS ok FROM avaliacao WHERE id_comanda = :c", c=id_comanda)

    crc = sum((p["icc"] for p in pesagens if p["icc"] is not None), 0)
    receita_buffet = sum((p["valor_prato"] for p in pesagens), 0)
    return {
        **comanda,
        "status": "paga" if comanda["data_hora_pago"] else "aberta",
        "mesa": mesa,
        "receita_buffet": receita_buffet,
        "receita_mesa": sum((p["quantidade"] * p["valor_unitario"] for p in pedidos), 0),
        "crc": crc,
        "tempos": tempos,
        "avaliada": avaliada is not None,
        "pesagens": pesagens,
        "pedidos": pedidos,
        "eventos": eventos,
    }


@router.post("/comandas/{id_comanda}/fechar", summary="Fechar comanda no caixa")
def fechar_comanda(id_comanda: str, conn: Connection = Depends(get_conn)):
    """Executa `sp_fechar_comanda` (consulta de fechamento original da equipe):
    grava o horário de pagamento e soma pesagens + pedidos."""
    comanda = obter_comanda(conn, id_comanda)
    exigir_aberta(comanda)
    tem_consumo = fetch_one(conn,
                            "SELECT (SELECT COUNT(*) FROM pratos_kilo WHERE id_comanda = :c) + "
                            "(SELECT COUNT(*) FROM pedidos_mesa WHERE id_comanda = :c) AS n",
                            c=id_comanda)
    if not tem_consumo["n"]:
        raise conflito("Comanda sem consumo: nada a cobrar.")
    call_procedure(conn, "sp_fechar_comanda", id_comanda)
    fechada = obter_comanda(conn, id_comanda)
    cupom = fetch_one(conn, "SELECT cb.codigo_cupom, cb.descricao_brinde, cb.data_validade "
                            "FROM cupom_brinde cb JOIN avaliacao a USING (id_avaliacao) "
                            "WHERE a.id_comanda = :c", c=id_comanda)
    return {**fechada, "cupom_brinde": cupom}   # impresso na nota, se o cliente devolveu o cartão


@router.post("/pedidos", status_code=status.HTTP_201_CREATED, tags=["Comandas"],
             summary="Registrar pedido à mesa (garçom)")
def registrar_pedido(dados: PedidoIn, conn: Connection = Depends(get_conn)):
    exigir_aberta(obter_comanda(conn, dados.id_comanda))
    if dados.id_garcom is not None:
        g = fetch_one(conn, "SELECT ativo FROM garcom WHERE id_garcom = :g", g=dados.id_garcom)
        if g is None or not g["ativo"]:
            raise conflito("Garçom inexistente ou inativo.")
    id_pedido = execute(conn,
                        "INSERT INTO pedidos_mesa (id_comanda, id_garcom, item_consumo, "
                        "quantidade, valor_unitario) VALUES (:c, :g, :i, :q, :v)",
                        c=dados.id_comanda, g=dados.id_garcom, i=dados.item_consumo,
                        q=dados.quantidade, v=dados.valor_unitario)
    return fetch_one(conn, "SELECT * FROM pedidos_mesa WHERE id_pedido = :p", p=id_pedido)
