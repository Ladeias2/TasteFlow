"""Eventos de fluxo: churrasqueira, chamado do garçom e saída (módulo Fluxo)."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.engine import Connection

from ..database import execute, fetch_one, get_conn
from ..errors import conflito
from ..schemas import EventoIn, TipoEvento
from ..services.regras import exigir_aberta, exigir_paga, obter_comanda

router = APIRouter(tags=["Eventos (Fluxo)"])


def _contar(conn: Connection, id_comanda: str, tipo: str) -> int:
    return fetch_one(conn, "SELECT COUNT(*) AS n FROM evento_comanda "
                           "WHERE id_comanda = :c AND tipo_evento = :t",
                     c=id_comanda, t=tipo)["n"]


@router.post("/eventos", status_code=status.HTTP_201_CREATED,
             summary="Registrar evento de leitor/sensor")
def registrar_evento(dados: EventoIn, conn: Connection = Depends(get_conn)):
    """Valida a sequência lógica antes de gravar:

    * `chegada_churrasqueira`: a comanda deve estar aberta e não estar já na fila;
    * `atendido_churrasqueira`: precisa de uma chegada pendente;
    * `chamado_garcom`: a comanda deve estar aberta;
    * `saida`: a comanda deve estar paga e só pode sair uma vez (catraca).
    """
    comanda = obter_comanda(conn, dados.id_comanda)
    tipo = dados.tipo_evento
    chegadas = _contar(conn, dados.id_comanda, TipoEvento.chegada_churrasqueira.value)
    atendidos = _contar(conn, dados.id_comanda, TipoEvento.atendido_churrasqueira.value)

    if tipo in (TipoEvento.chegada_churrasqueira, TipoEvento.chamado_garcom):
        exigir_aberta(comanda)
    if tipo == TipoEvento.chegada_churrasqueira and chegadas > atendidos:
        raise conflito("Cliente já está na fila da churrasqueira.")
    if tipo == TipoEvento.atendido_churrasqueira and chegadas <= atendidos:
        raise conflito("Não há chegada pendente na churrasqueira para esta comanda.")
    if tipo == TipoEvento.saida:
        exigir_paga(comanda)
        if _contar(conn, dados.id_comanda, TipoEvento.saida.value):
            raise conflito("Saída já registrada para esta comanda.")

    id_evento = execute(conn,
                        "INSERT INTO evento_comanda (id_comanda, tipo_evento, data_hora_evento, "
                        "origem_evento, id_garcom) "
                        "VALUES (:c, :t, COALESCE(:dh, NOW()), :o, :g)",
                        c=dados.id_comanda, t=tipo.value, dh=dados.data_hora_evento,
                        o=dados.origem_evento.value, g=dados.id_garcom)
    return fetch_one(conn, "SELECT * FROM evento_comanda WHERE id_evento = :e", e=id_evento)
