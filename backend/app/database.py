"""Acesso ao MySQL.

Usa SQLAlchemy Core (consultas SQL explícitas, sem ORM): as regras de negócio
mais importantes já estão no banco (trigger, procedures, colunas geradas e
views), e a API apenas orquestra e valida.
"""
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from .config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)
    return _engine


def set_engine(engine: Engine) -> None:
    """Permite trocar o banco (usado nos testes)."""
    global _engine
    _engine = engine


def get_conn() -> Iterator[Connection]:
    """Dependência do FastAPI: uma transação por requisição.
    Commit ao final; rollback automático se ocorrer exceção."""
    with get_engine().begin() as conn:
        yield conn


def _tempo(td: timedelta) -> str:
    """Colunas TIME chegam como timedelta; devolvemos 'HH:MM:SS' como no MySQL."""
    total = int(td.total_seconds())
    sinal = "-" if total < 0 else ""
    h, resto = divmod(abs(total), 3600)
    m, s = divmod(resto, 60)
    return f"{sinal}{h:02d}:{m:02d}:{s:02d}"


def _linha(row: Any) -> dict:
    return {k: (_tempo(v) if isinstance(v, timedelta) else v) for k, v in dict(row).items()}


def fetch_one(conn: Connection, sql: str, **params: Any) -> dict | None:
    row = conn.execute(text(sql), params).mappings().first()
    return _linha(row) if row else None


def fetch_all(conn: Connection, sql: str, **params: Any) -> list[dict]:
    return [_linha(r) for r in conn.execute(text(sql), params).mappings().all()]


def execute(conn: Connection, sql: str, **params: Any) -> int:
    """Executa um comando e devolve o lastrowid (útil após INSERT)."""
    return conn.execute(text(sql), params).lastrowid


def call_procedure(conn: Connection, nome: str, *args: Any) -> list[dict]:
    """Chama uma stored procedure e devolve o primeiro result set (se houver).

    Usa o cursor do driver diretamente porque CALL pode devolver vários
    result sets; todos são consumidos para não deixar a conexão dessincronizada.
    """
    cursor = conn.connection.cursor()
    try:
        cursor.callproc(nome, args)
        linhas: list[dict] = []
        primeiro = True
        while True:
            if cursor.description and primeiro:
                cols = [c[0] for c in cursor.description]
                linhas = [_linha(zip(cols, r)) for r in cursor.fetchall()]
                primeiro = False
            else:
                cursor.fetchall()
            if not cursor.nextset():
                break
        return linhas
    finally:
        cursor.close()
