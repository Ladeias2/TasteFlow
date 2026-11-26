"""Indicadores: exposição das views de 04_views_kpis.sql para o dashboard."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Connection

from ..database import fetch_all, get_conn
from ..errors import nao_encontrado

router = APIRouter(prefix="/kpis", tags=["Indicadores (KPIs)"])

# Lista fechada: o nome da view nunca é interpolado sem passar por aqui
VIEWS: dict[str, dict] = {
    "custo-pesagem":           {"view": "vw_custo_pesagem",             "data": "DATE(datahora_pesou)",
                                "descricao": "ICC de cada prato pesado"},
    "custo-comanda":           {"view": "vw_custo_comanda",             "data": "data",
                                "descricao": "Custo Real por Cliente (CRC) e margem"},
    "rentabilidade-ingrediente": {"view": "vw_rentabilidade_ingrediente", "data": None,
                                "descricao": "% do peso servido × % do custo por ingrediente"},
    "tempos-comanda":          {"view": "vw_tempos_comanda",            "data": "data",
                                "descricao": "Tempos de fila, espera e permanência por cliente"},
    "fluxo-por-hora":          {"view": "vw_fluxo_por_hora",            "data": None,
                                "descricao": "Mapa de calor de gargalos (dia da semana × hora)"},
    "desempenho-garcom":       {"view": "vw_desempenho_garcom",         "data": None,
                                "descricao": "Pedidos, espera média e CSAT de atendimento por garçom"},
    "ciclo-mesa":              {"view": "vw_ciclo_mesa",                "data": "data",
                                "descricao": "Permanência, espera de limpeza, limpeza e liberação"},
    "mesa-diario":             {"view": "vw_mesa_kpis_diario",          "data": "data",
                                "descricao": "Giro e tempos médios das mesas por dia"},
    "mesas-agora":             {"view": "vw_mesas_agora",               "data": None,
                                "descricao": "Estado atual de cada mesa"},
    "satisfacao-diaria":       {"view": "vw_satisfacao_diaria",         "data": "data",
                                "descricao": "CSAT (comida, ambiente, atendimento), recomendação e taxa de resposta"},
    "satisfacao-por-fila":     {"view": "vw_satisfacao_por_fila",       "data": None,
                                "descricao": "CSAT e índice de recomendação por faixa de tempo de fila"},
    "cupons-diario":           {"view": "vw_cupons_diario",             "data": "data_emissao",
                                "descricao": "Cupons de brinde emitidos e resgatados (taxa de retorno e custo)"},
    "desperdicio-ingrediente": {"view": "vw_desperdicio_ingrediente",   "data": None,
                                "descricao": "Food Waste Index e custo do desperdício"},
    "resumo-diario":           {"view": "vw_resumo_diario",             "data": "data",
                                "descricao": "Cartões-resumo do dashboard"},
}


@router.get("", summary="Catálogo de indicadores disponíveis")
def catalogo():
    return [{"nome": nome, "view": v["view"], "descricao": v["descricao"],
             "filtro_por_data": v["data"] is not None} for nome, v in VIEWS.items()]


@router.get("/{nome}", summary="Consultar um indicador")
def consultar(nome: str,
              data_inicio: date | None = Query(None, description="Só para indicadores com data"),
              data_fim: date | None = Query(None),
              limite: int = Query(1000, ge=1, le=10000),
              conn: Connection = Depends(get_conn)):
    v = VIEWS.get(nome)
    if v is None:
        raise nao_encontrado("Indicador")
    filtros, params = [], {"limite": limite}
    if v["data"] and data_inicio:
        filtros.append(f"{v['data']} >= :ini")
        params["ini"] = data_inicio
    if v["data"] and data_fim:
        filtros.append(f"{v['data']} <= :fim")
        params["fim"] = data_fim
    where = f" WHERE {' AND '.join(filtros)}" if filtros else ""
    linhas = fetch_all(conn, f"SELECT * FROM {v['view']}{where} LIMIT :limite", **params)
    return {"indicador": nome, "descricao": v["descricao"], "total": len(linhas), "dados": linhas}
