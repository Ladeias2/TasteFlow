"""Pesquisa de satisfação por cartão raspadinha + brinde garantido (módulo Satisfação).

Fluxo: o cliente raspa uma bolinha por linha (0 a 5) e entrega o cartão no
caixa. O caixa lança as respostas (ou a urna com câmera faz a leitura
óptica) e a API emite na hora um cupom de brinde válido por 7 dias, que vai
impresso na nota. O brinde é o mesmo para todos e não depende das respostas,
o que evita sorteio (Lei 5.768/1971) e reduz o viés de nota alta.
"""
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.engine import Connection

from ..config import settings
from ..database import call_procedure, execute, fetch_all, fetch_one, get_conn
from ..errors import conflito, nao_encontrado
from ..schemas import AvaliacaoIn, LoteCartoesIn, ResgateIn
from ..services import leitura_cartao, sentimento
from ..services.regras import exigir_aberta, obter_comanda, salvar_upload

router = APIRouter(tags=["Satisfação (cartão e brinde)"])


def _codigo(prefixo: str) -> str:
    return f"{prefixo}{secrets.token_hex(5).upper()}"   # 11 caracteres


def _status_cupom(c: dict) -> str:
    if c["id_comanda_resgate"]:
        return "resgatado"
    return "vencido" if c["data_validade"] < date.today() else "ativo"


def _cupom(conn: Connection, codigo: str) -> dict:
    c = fetch_one(conn, "SELECT * FROM cupom_brinde WHERE codigo_cupom = :c", c=codigo)
    if c is None:
        raise nao_encontrado("Cupom")
    return {**c, "status": _status_cupom(c)}


def _registrar(conn: Connection, dados: AvaliacaoIn, origem: str, confianca: float | None) -> dict:
    obter_comanda(conn, dados.id_comanda)
    cartao = fetch_one(conn, "SELECT * FROM cartao_pesquisa WHERE codigo_cartao = :c", c=dados.codigo_cartao)
    if cartao is None:
        raise nao_encontrado("Cartão (código não cadastrado)")
    if fetch_one(conn, "SELECT 1 AS ok FROM avaliacao WHERE codigo_cartao = :c", c=dados.codigo_cartao):
        raise conflito("Este cartão já foi utilizado.")
    if fetch_one(conn, "SELECT 1 AS ok FROM avaliacao WHERE id_comanda = :c", c=dados.id_comanda):
        raise conflito("Esta comanda já foi avaliada.")

    rotulo, score = sentimento.analisar(dados.comentario)
    id_avaliacao = execute(
        conn,
        "INSERT INTO avaliacao (codigo_cartao, id_comanda, nota_comida, nota_ambiente, nota_atendimento, "
        "recomendaria, comentario, sentimento, score_sentimento, origem_registro, confianca_leitura) "
        "VALUES (:cart, :cmd, :co, :am, :at, :rec, :txt, :s, :sc, :orig, :conf)",
        cart=dados.codigo_cartao, cmd=dados.id_comanda, co=dados.nota_comida, am=dados.nota_ambiente,
        at=dados.nota_atendimento, rec=dados.recomendaria.value, txt=dados.comentario,
        s=rotulo, sc=score, orig=origem, conf=confianca)

    codigo_cupom = _codigo("B")
    execute(conn,
            "INSERT INTO cupom_brinde (codigo_cupom, id_avaliacao, descricao_brinde, custo_brinde, data_validade) "
            "VALUES (:c, :a, :d, :custo, :v)",
            c=codigo_cupom, a=id_avaliacao, d=settings.brinde_descricao, custo=settings.brinde_custo,
            v=date.today() + timedelta(days=settings.validade_cupom_dias))

    avaliacao = fetch_one(conn, "SELECT * FROM avaliacao WHERE id_avaliacao = :a", a=id_avaliacao)
    return {**avaliacao, "cupom": _cupom(conn, codigo_cupom)}


# ------------------------------------------------------------------ cartões
@router.post("/cartoes/lote", status_code=status.HTTP_201_CREATED,
             summary="Gerar códigos de um lote de cartões para impressão")
def gerar_lote(dados: LoteCartoesIn, conn: Connection = Depends(get_conn)):
    """Só cartões cadastrados geram brinde: cópias ou cartões inventados são recusados."""
    lote = dados.lote or f"L{date.today():%Y%m%d}"
    codigos = [_codigo("C") for _ in range(dados.quantidade)]
    for c in codigos:
        execute(conn, "INSERT INTO cartao_pesquisa (codigo_cartao, lote) VALUES (:c, :l)", c=c, l=lote)
    return {"lote": lote, "quantidade": len(codigos), "codigos": codigos}


@router.get("/cartoes/{codigo}", summary="Situação de um cartão")
def consultar_cartao(codigo: str, conn: Connection = Depends(get_conn)):
    cartao = fetch_one(conn, "SELECT * FROM cartao_pesquisa WHERE codigo_cartao = :c", c=codigo)
    if cartao is None:
        raise nao_encontrado("Cartão")
    usado = fetch_one(conn, "SELECT id_comanda FROM avaliacao WHERE codigo_cartao = :c", c=codigo)
    return {**cartao, "utilizado": usado is not None}


# ------------------------------------------------------------------ avaliações
@router.post("/avaliacoes", status_code=status.HTTP_201_CREATED,
             summary="Caixa lança o cartão raspadinha e emite o cupom de brinde")
def registrar_avaliacao(dados: AvaliacaoIn, conn: Connection = Depends(get_conn)):
    """Aceita comanda aberta (lançamento no fechamento) ou já paga. Regras:
    cartão cadastrado e não usado; uma avaliação por comanda."""
    return _registrar(conn, dados, origem="caixa", confianca=None)


@router.post("/avaliacoes/leitura-otica", status_code=status.HTTP_201_CREATED,
             summary="Urna com câmera lê o cartão automaticamente")
def registrar_por_leitura(codigo_cartao: str = Form(..., max_length=12),
                          id_comanda: str = Form(..., max_length=50),
                          foto: UploadFile = File(...),
                          conn: Connection = Depends(get_conn)):
    """Se alguma linha estiver em branco ou com duas bolinhas raspadas,
    responde 422 com o diagnóstico, e o caixa lança o cartão manualmente."""
    caminho = salvar_upload(foto, "cartoes", codigo_cartao)
    try:
        respostas, confianca, linhas = leitura_cartao.ler_cartao(caminho)
    except leitura_cartao.LeituraIndisponivel as exc:
        raise HTTPException(status_code=503, detail=f"Leitura óptica indisponível: {exc}")
    problemas = [{"campo": l.campo, "situacao": l.situacao} for l in linhas if l.situacao != "ok"]
    if problemas:
        raise HTTPException(status_code=422,
                            detail={"mensagem": "Cartão não lido com segurança; lançar pelo caixa.",
                                    "linhas": problemas})
    dados = AvaliacaoIn(codigo_cartao=codigo_cartao, id_comanda=id_comanda, **respostas)
    return _registrar(conn, dados, origem="leitura_otica", confianca=confianca)


@router.get("/avaliacoes/{id_comanda}", summary="Consultar a avaliação de uma comanda")
def obter_avaliacao(id_comanda: str, conn: Connection = Depends(get_conn)):
    a = fetch_one(conn, "SELECT * FROM avaliacao WHERE id_comanda = :c", c=id_comanda)
    if a is None:
        raise nao_encontrado("Avaliação")
    cupom = fetch_one(conn, "SELECT codigo_cupom FROM cupom_brinde WHERE id_avaliacao = :a",
                      a=a["id_avaliacao"])
    return {**a, "cupom": _cupom(conn, cupom["codigo_cupom"]) if cupom else None}


# ------------------------------------------------------------------ cupons
@router.get("/cupons/{codigo}", summary="Situação do cupom (ativo, resgatado ou vencido)")
def consultar_cupom(codigo: str, conn: Connection = Depends(get_conn)):
    return _cupom(conn, codigo)


@router.post("/cupons/{codigo}/resgatar", summary="Resgatar o brinde numa nova visita")
def resgatar_cupom(codigo: str, dados: ResgateIn, conn: Connection = Depends(get_conn)):
    """Chama `sp_resgatar_cupom`: o brinde entra na comanda como item de
    valor zero (não altera o fechamento) e o resgate mede a taxa de retorno."""
    exigir_aberta(obter_comanda(conn, dados.id_comanda))
    _cupom(conn, codigo)
    call_procedure(conn, "sp_resgatar_cupom", codigo, dados.id_comanda)
    cupom = _cupom(conn, codigo)
    item = fetch_all(conn, "SELECT * FROM pedidos_mesa WHERE id_comanda = :c AND item_consumo LIKE :l",
                     c=dados.id_comanda, l=f"Brinde (cupom {codigo})%")
    return {**cupom, "item_na_comanda": item[0] if item else None}
