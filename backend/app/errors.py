"""Tradução dos erros do MySQL para respostas HTTP claras.

| Código MySQL | Situação                                     | HTTP |
|--------------|----------------------------------------------|------|
| 1644         | SIGNAL nas procedures/trigger (regra de negócio) | 409 |
| 1062         | Chave duplicada (ex.: 2ª avaliação da comanda)   | 409 |
| 1451 / 1452  | Chave estrangeira inexistente ou em uso          | 422 |
| 3819         | Violação de CHECK constraint                     | 422 |
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

try:  # erros diretos do driver (usados em call_procedure)
    import pymysql
    _DRIVER_ERRORS: tuple = (pymysql.err.MySQLError,)
except ImportError:  # pragma: no cover
    _DRIVER_ERRORS = ()


def _codigo_e_mensagem(exc: Exception) -> tuple[int | None, str]:
    orig = getattr(exc, "orig", exc)
    args = getattr(orig, "args", ())
    if len(args) >= 2 and isinstance(args[0], int):
        return args[0], str(args[1])
    return None, str(orig)


def _resposta(exc: Exception) -> JSONResponse:
    codigo, msg = _codigo_e_mensagem(exc)
    if codigo == 1644:
        return JSONResponse(status_code=409, content={"detail": msg, "regra": "negocio"})
    if codigo == 1062:
        return JSONResponse(status_code=409, content={"detail": "Registro duplicado.", "mysql": msg})
    if codigo in (1451, 1452):
        return JSONResponse(status_code=422, content={"detail": "Referência inválida.", "mysql": msg})
    if codigo == 3819:
        return JSONResponse(status_code=422, content={"detail": "Valor fora das regras do banco.", "mysql": msg})
    return JSONResponse(status_code=500, content={"detail": "Erro no banco de dados.", "mysql": msg})


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError):
        return _resposta(exc)

    for tipo in _DRIVER_ERRORS:
        @app.exception_handler(tipo)
        async def _driver_error(_: Request, exc: Exception):
            return _resposta(exc)


def nao_encontrado(oque: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{oque} não encontrado(a).")


def conflito(msg: str) -> HTTPException:
    return HTTPException(status_code=409, detail=msg)
