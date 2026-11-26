"""TasteFlow — API REST.

Executar:  uvicorn app.main:app --reload
Documentação interativa:  http://localhost:8000/docs
"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Connection

from .config import settings
from .database import fetch_one, get_conn
from .errors import registrar_handlers
from .routers import (avaliacoes, cadastros, comandas, eventos, kpis, mesas,
                      pesagens, sobras)

DESCRICAO = """
API da plataforma **TasteFlow**. Recebe os dados das estações de
captura (balança + câmera, tablet do salão, leitores, cartão de satisfação) e
expõe os indicadores para o dashboard.

| Módulo | Endpoints |
|---|---|
| Comandas | `/comandas`, `/pedidos` |
| Mix e Custo | `/pesagens` |
| Fluxo | `/eventos` |
| Mesas | `/mesas` |
| Satisfação | `/avaliacoes`, `/cartoes`, `/cupons` |
| Sobras | `/sobras`, `/producao` |
| Indicadores | `/kpis` |
"""

app = FastAPI(title="TasteFlow API", version="1.0.0", description=DESCRICAO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origens.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
registrar_handlers(app)

for r in (comandas, pesagens, eventos, mesas, avaliacoes, sobras, cadastros, kpis):
    app.include_router(r.router)


@app.get("/saude", tags=["Infra"], summary="Verifica API e conexão com o banco")
def saude(conn: Connection = Depends(get_conn)):
    versao = fetch_one(conn, "SELECT VERSION() AS v")["v"]
    return {"status": "ok", "mysql": versao, "banco": settings.db_name}
