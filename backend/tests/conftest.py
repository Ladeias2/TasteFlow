"""Cria um banco de teste do zero a partir dos scripts de database/ e aponta a API para ele.

Requer o cliente `mysql` no PATH (os scripts usam DELIMITER) e um usuário com
permissão de criar bancos. Variáveis: TEST_DB_HOST, TEST_DB_PORT, TEST_DB_USER,
TEST_DB_PASSWORD, TEST_DB_NAME (padrão: restaurante_teste).
"""
import os
import subprocess
from pathlib import Path

# Os testes não usam o modelo de visão do .env (há um teste específico para ele)
os.environ["MODELO_VISAO_PATH"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import database
from app.main import app

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = ["01_schema_base.sql", "02_schema_extensao.sql",
           "03_procedures_triggers.sql", "04_views_kpis.sql"]

HOST = os.getenv("TEST_DB_HOST", "127.0.0.1")
PORT = os.getenv("TEST_DB_PORT", "3306")
USER = os.getenv("TEST_DB_USER", "tasteflow")
SENHA = os.getenv("TEST_DB_PASSWORD", "tasteflow123")
NOME = os.getenv("TEST_DB_NAME", "restaurante_teste")

CADASTROS = """
INSERT INTO garcom (nome) VALUES ('Ana Souza'), ('Bruno Lima'), ('Elisa Rocha');
INSERT INTO mesa (numero_mesa, capacidade) VALUES (1, 4), (2, 2), (3, 6);
INSERT INTO ingrediente (nome_ingrediente, rotulo_ia, categoria, estacao, custo_kg) VALUES
  ('Arroz branco', 'arroz_branco', 'guarnicao', 'buffet', 6.50),
  ('Feijão', 'feijao', 'guarnicao', 'buffet', 9.20),
  ('Salada de folhas', 'salada_folhas', 'salada', 'buffet', 12.00),
  ('Abobrinha', 'abobrinha', 'legume', 'buffet', 8.00),
  ('Picanha', 'picanha', 'carne', 'churrasqueira', 72.00),
  ('Filé mignon', 'file_mignon', 'carne', 'churrasqueira', 78.00);
"""


def _mysql(sql: str | None = None, arquivo: Path | None = None, banco: str | None = None) -> None:
    cmd = ["mysql", f"-h{HOST}", f"-P{PORT}", f"-u{USER}", "--protocol=TCP",
           "--default-character-set=utf8mb4"]
    if banco:
        cmd.append(banco)
    entrada = arquivo.read_text(encoding="utf-8") if arquivo else sql
    env = {**os.environ, "MYSQL_PWD": SENHA}
    subprocess.run(cmd, input=entrada, text=True, check=True, env=env, capture_output=True)


@pytest.fixture(scope="session")
def client():
    _mysql(f"DROP DATABASE IF EXISTS {NOME}; CREATE DATABASE {NOME} CHARACTER SET utf8mb4;")
    for s in SCRIPTS:
        _mysql(arquivo=RAIZ / "database" / s, banco=NOME)
    _mysql(CADASTROS, banco=NOME)

    url = f"mysql+pymysql://{USER}:{SENHA}@{HOST}:{PORT}/{NOME}?charset=utf8mb4"
    database.set_engine(create_engine(url, pool_pre_ping=True))
    with TestClient(app) as c:
        yield c
    database.get_engine().dispose()
    _mysql(f"DROP DATABASE IF EXISTS {NOME};")
