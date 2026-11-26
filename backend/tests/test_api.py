"""Testes de ponta a ponta: a jornada completa de um grupo no restaurante,
mais os casos de erro de cada regra de negócio."""
import pytest

ITENS_PRATO = [  # saída típica da IA para um prato de 850 g
    {"rotulo": "file_mignon", "percentual": 50, "confianca": 0.88},
    {"rotulo": "arroz_branco", "percentual": 20, "confianca": 0.94},
    {"rotulo": "salada_folhas", "percentual": 20, "confianca": 0.86},
    {"rotulo": "feijao", "percentual": 10, "confianca": 0.91},
]


@pytest.fixture(scope="module")
def grupo(client):
    """Duas pessoas chegam, se servem e sentam na mesa 1."""
    ana = client.post("/comandas").json()["id_comanda_aleatoria"]
    beto = client.post("/comandas", json={"id_comanda_aleatoria": "CMD-TESTE-BETO"}).json()["id_comanda_aleatoria"]
    return {"ana": ana, "beto": beto}


# ------------------------------------------------------------------ infra
def test_saude(client):
    r = client.get("/saude")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_openapi_lista_endpoints_da_especificacao(client):
    rotas = client.get("/openapi.json").json()["paths"]
    for rota in ["/pesagens", "/mesas/{numero}/ocupar", "/mesas/{numero}/avancar", "/eventos",
                 "/comandas/{id_comanda}/fechar", "/avaliacoes", "/avaliacoes/leitura-otica",
                 "/cartoes/lote", "/cupons/{codigo}/resgatar", "/sobras", "/producao",
                 "/kpis/{nome}"]:
        assert rota in rotas


# ------------------------------------------------------------------ comandas
def test_comanda_gerada_tem_codigo_aleatorio(client, grupo):
    assert grupo["ana"].startswith("CMD-") and len(grupo["ana"]) == 16
    assert client.get(f"/comandas/{grupo['ana']}").json()["status"] == "aberta"


def test_comanda_inexistente_404(client):
    assert client.get("/comandas/NAO-EXISTE").status_code == 404


def test_fechar_sem_consumo_409(client):
    vazia = client.post("/comandas").json()["id_comanda_aleatoria"]
    assert client.post(f"/comandas/{vazia}/fechar").status_code == 409


# ------------------------------------------------------------------ pesagens (mix e custo)
def test_pesagem_calcula_icc_exemplo_da_documentacao(client, grupo):
    r = client.post("/pesagens", json={"id_comanda": grupo["ana"], "peso_gramas": 850,
                                       "preco_kg_aplicado": "89.90", "url_foto": "storage/pratos/x.jpg",
                                       "itens": ITENS_PRATO})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["sequencia_peso"] == 1
    assert float(p["valor_prato"]) == 76.42            # 0,850 × 89,90
    assert float(p["icc"]) == pytest.approx(37.08, abs=0.02)  # exemplo da Seção 10.2
    assert p["revisao_necessaria"] is False
    assert p["composicao"][0]["rotulo"] == "file_mignon"
    assert p["composicao"][0]["gramas_estimados"] == 425


def test_segunda_pesagem_incrementa_sequencia_e_normaliza(client, grupo):
    r = client.post("/pesagens", json={"id_comanda": grupo["ana"], "peso_gramas": 200,
                                       "itens": [{"rotulo": "picanha", "percentual": 60, "confianca": 0.4},
                                                 {"rotulo": "abobrinha", "percentual": 30, "confianca": 0.5}]})
    p = r.json()
    assert p["sequencia_peso"] == 2
    assert sum(float(i["percentual"]) for i in p["composicao"]) == pytest.approx(100, abs=0.02)
    assert p["revisao_necessaria"] is True               # confiança média 0,45 < 0,60


def test_correcao_manual_da_composicao(client, grupo):
    pid = client.get(f"/comandas/{grupo['ana']}").json()["pesagens"][1]["id_pesagem"]
    r = client.put(f"/pesagens/{pid}/composicao",
                   json={"itens": [{"rotulo": "picanha", "percentual": 70},
                                   {"rotulo": "abobrinha", "percentual": 30}]})
    assert r.status_code == 200
    assert {i["origem_classificacao"] for i in r.json()["composicao"]} == {"manual"}


def test_pesagem_com_rotulo_desconhecido_422(client, grupo):
    r = client.post("/pesagens", json={"id_comanda": grupo["beto"], "peso_gramas": 300,
                                       "itens": [{"rotulo": "lagosta", "percentual": 100}]})
    assert r.status_code == 422 and "lagosta" in r.json()["detail"]
    # nada foi gravado (transação desfeita)
    assert client.get(f"/comandas/{grupo['beto']}").json()["pesagens"] == []


def test_pesagem_rotulo_repetido_422(client, grupo):
    r = client.post("/pesagens", json={"id_comanda": grupo["beto"], "peso_gramas": 300,
                                       "itens": [{"rotulo": "feijao", "percentual": 50},
                                                 {"rotulo": "feijao", "percentual": 50}]})
    assert r.status_code == 422


def test_pesagem_beto_e_foto_sem_modelo_503(client, grupo):
    r = client.post("/pesagens", json={"id_comanda": grupo["beto"], "peso_gramas": 500,
                                       "itens": [{"rotulo": "arroz_branco", "percentual": 70, "confianca": 0.9},
                                                 {"rotulo": "feijao", "percentual": 30, "confianca": 0.9}]})
    assert r.status_code == 201
    r = client.post("/pesagens/foto", data={"id_comanda": grupo["beto"], "peso_gramas": "300"},
                    files={"foto": ("prato.jpg", b"fake", "image/jpeg")})
    assert r.status_code == 503


# ------------------------------------------------------------------ mesas (tablet da equipe)
def test_garcom_ocupa_mesa_e_vincula_grupo(client, grupo):
    r = client.post("/mesas/1/ocupar", json={"qtd_pessoas": 2, "id_garcom": 1, "comandas": [grupo["ana"]]})
    assert r.status_code == 200, r.text
    ciclo = r.json()["ciclo_atual"]
    assert ciclo["status_mesa"] == "ocupada" and ciclo["qtd_pessoas"] == 2
    assert ciclo["id_garcom_abertura"] == 1
    r = client.post("/mesas/1/comandas", json={"id_comanda": grupo["beto"]})
    assert set(r.json()["ciclo_atual"]["comandas"]) == {grupo["ana"], grupo["beto"]}


def test_ocupar_sem_corpo_e_mesa_ocupada_409(client):
    assert client.post("/mesas/1/ocupar").status_code == 409          # já ocupada
    assert client.post("/mesas/3/ocupar").status_code == 200          # padrão: 1 pessoa
    client.post("/mesas/3/avancar"); client.post("/mesas/3/avancar"); client.post("/mesas/3/avancar")


def test_vincular_comanda_em_duas_mesas_409(client, grupo):
    client.post("/mesas/2/ocupar", json={"qtd_pessoas": 1})
    assert client.post("/mesas/2/comandas", json={"id_comanda": grupo["ana"]}).status_code == 409


def test_grupo_maior_que_a_mesa_409(client):
    assert client.post("/mesas/3/ocupar", json={"qtd_pessoas": 15}).status_code == 409


def test_mesa_inexistente_404(client):
    assert client.post("/mesas/99/ocupar").status_code == 404


def test_painel_mostra_mesas_ocupadas(client):
    painel = client.get("/mesas").json()
    assert painel["resumo"]["vermelho"] == 2
    assert next(m for m in painel["mesas"] if m["numero_mesa"] == 1)["cor"] == "vermelho"


# ------------------------------------------------------------------ eventos e pedidos
def test_fluxo_churrasqueira(client, grupo):
    c = grupo["ana"]
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "atendido_churrasqueira"}).status_code == 409
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "chegada_churrasqueira",
                                         "origem_evento": "leitor"}).status_code == 201
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "chegada_churrasqueira"}).status_code == 409
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "atendido_churrasqueira"}).status_code == 201


def test_chamado_e_pedido_ao_garcom(client, grupo):
    c = grupo["ana"]
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "chamado_garcom",
                                         "origem_evento": "botao"}).status_code == 201
    r = client.post("/pedidos", json={"id_comanda": c, "id_garcom": 1, "item_consumo": "Suco natural",
                                      "quantidade": 2, "valor_unitario": "9.90"})
    assert r.status_code == 201
    tempos = client.get(f"/comandas/{c}").json()["tempos"]
    assert tempos["min_espera_garcom"] is not None


def test_saida_antes_de_pagar_409(client, grupo):
    r = client.post("/eventos", json={"id_comanda": grupo["ana"], "tipo_evento": "saida"})
    assert r.status_code == 409


def test_tipo_de_evento_invalido_422(client, grupo):
    r = client.post("/eventos", json={"id_comanda": grupo["ana"], "tipo_evento": "teleporte"})
    assert r.status_code == 422


# ------------------------------------------------------------------ fechamento
def test_fechar_comanda_soma_pesagens_e_pedidos(client, grupo):
    r = client.post(f"/comandas/{grupo['ana']}/fechar")
    assert r.status_code == 200, r.text
    c = r.json()
    soma = client.get(f"/comandas/{grupo['ana']}").json()
    esperado = float(soma["receita_buffet"]) + float(soma["receita_mesa"])
    assert float(c["valor_total_comanda"]) == pytest.approx(esperado)
    assert c["data_hora_pago"] is not None and c["delta_tempo_uso"] is not None


def test_comanda_paga_nao_aceita_mais_consumo(client, grupo):
    c = grupo["ana"]
    assert client.post(f"/comandas/{c}/fechar").status_code == 409
    assert client.post("/pesagens", json={"id_comanda": c, "peso_gramas": 100}).status_code == 409
    assert client.post("/pedidos", json={"id_comanda": c, "item_consumo": "Café",
                                         "valor_unitario": "6.00"}).status_code == 409


def test_saida_unica(client, grupo):
    c = grupo["ana"]
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "saida",
                                         "origem_evento": "sensor"}).status_code == 201
    assert client.post("/eventos", json={"id_comanda": c, "tipo_evento": "saida"}).status_code == 409


# ------------------------------------------------------------------ satisfação: cartão e brinde
CARTAO_OK = {"nota_comida": 5, "nota_ambiente": 2, "nota_atendimento": 4, "recomendaria": "talvez"}


@pytest.fixture(scope="module")
def cartoes(client):
    r = client.post("/cartoes/lote", json={"quantidade": 6, "lote": "TESTE"})
    assert r.status_code == 201
    return r.json()["codigos"]


def test_avaliacao_gera_cupom_de_brinde(client, grupo, cartoes):
    r = client.post("/avaliacoes", json={"codigo_cartao": cartoes[0], "id_comanda": grupo["ana"],
                                         **CARTAO_OK, "comentario": "Comida ótima, mas a mesa estava suja e a fila enorme"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["origem_registro"] == "caixa" and a["sentimento"] == "negativo"
    cupom = a["cupom"]
    assert cupom["status"] == "ativo" and cupom["descricao_brinde"] == "Café expresso"
    assert cupom["codigo_cupom"].startswith("B") and len(cupom["codigo_cupom"]) == 11


def test_comanda_aberta_tambem_pode_avaliar(client, grupo, cartoes):
    r = client.post("/avaliacoes", json={"codigo_cartao": cartoes[1], "id_comanda": grupo["beto"], **CARTAO_OK})
    assert r.status_code == 201


def test_cartao_reutilizado_ou_falso(client, cartoes):
    nova = client.post("/comandas").json()["id_comanda_aleatoria"]
    assert client.post("/avaliacoes", json={"codigo_cartao": cartoes[0], "id_comanda": nova,
                                            **CARTAO_OK}).status_code == 409
    assert client.post("/avaliacoes", json={"codigo_cartao": "CFALSO12345", "id_comanda": nova,
                                            **CARTAO_OK}).status_code == 404
    assert client.get(f"/cartoes/{cartoes[0]}").json()["utilizado"] is True


def test_segunda_avaliacao_da_comanda_409(client, grupo, cartoes):
    r = client.post("/avaliacoes", json={"codigo_cartao": cartoes[2], "id_comanda": grupo["ana"], **CARTAO_OK})
    assert r.status_code == 409


def test_nota_fora_da_escala_0_a_5_422(client, grupo, cartoes):
    r = client.post("/avaliacoes", json={"codigo_cartao": cartoes[2], "id_comanda": grupo["beto"],
                                         **{**CARTAO_OK, "nota_comida": 6}})
    assert r.status_code == 422
    r = client.post("/avaliacoes", json={"codigo_cartao": cartoes[2], "id_comanda": grupo["beto"],
                                         **{**CARTAO_OK, "recomendaria": "talvez sim"}})
    assert r.status_code == 422


def test_fechamento_devolve_cupom_para_a_nota(client, grupo):
    r = client.post(f"/comandas/{grupo['beto']}/fechar")
    assert r.status_code == 200 and r.json()["cupom_brinde"]["descricao_brinde"] == "Café expresso"


def test_resgate_do_cupom_na_proxima_visita(client, grupo):
    codigo = client.get(f"/avaliacoes/{grupo['ana']}").json()["cupom"]["codigo_cupom"]
    # mesma comanda (já paga) não pode
    assert client.post(f"/cupons/{codigo}/resgatar", json={"id_comanda": grupo["ana"]}).status_code == 409
    volta = client.post("/comandas").json()["id_comanda_aleatoria"]
    r = client.post(f"/cupons/{codigo}/resgatar", json={"id_comanda": volta})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resgatado"
    assert float(r.json()["item_na_comanda"]["valor_unitario"]) == 0
    # não resgata duas vezes
    outra = client.post("/comandas").json()["id_comanda_aleatoria"]
    assert client.post(f"/cupons/{codigo}/resgatar", json={"id_comanda": outra}).status_code == 409


def test_cupom_vencido_409(client, grupo):
    from sqlalchemy import text
    from app import database
    codigo = client.get(f"/avaliacoes/{grupo['beto']}").json()["cupom"]["codigo_cupom"]
    with database.get_engine().begin() as conn:
        conn.execute(text("UPDATE cupom_brinde SET data_validade = CURDATE() - INTERVAL 1 DAY "
                          "WHERE codigo_cupom = :c"), {"c": codigo})
    assert client.get(f"/cupons/{codigo}").json()["status"] == "vencido"
    volta = client.post("/comandas").json()["id_comanda_aleatoria"]
    r = client.post(f"/cupons/{codigo}/resgatar", json={"id_comanda": volta})
    assert r.status_code == 409 and "vencido" in r.json()["detail"]


def test_leitura_otica_do_cartao(client, cartoes, tmp_path):
    cv2 = pytest.importorskip("cv2")
    from tests.cartao_sintetico import desenhar_cartao
    cmd = client.post("/comandas").json()["id_comanda_aleatoria"]
    img = desenhar_cartao(tmp_path / "ok.png", {"nota_comida": 4, "nota_ambiente": 3,
                                                "nota_atendimento": 5, "recomendaria": "sim"})
    with open(img, "rb") as f:
        r = client.post("/avaliacoes/leitura-otica", data={"codigo_cartao": cartoes[3], "id_comanda": cmd},
                        files={"foto": ("cartao.png", f, "image/png")})
    assert r.status_code == 201, r.text
    a = r.json()
    assert (a["nota_comida"], a["nota_ambiente"], a["nota_atendimento"], a["recomendaria"]) == (4, 3, 5, "sim")
    assert a["origem_registro"] == "leitura_otica" and float(a["confianca_leitura"]) >= 0.8


def test_leitura_otica_ambigua_volta_para_o_caixa(client, cartoes, tmp_path):
    pytest.importorskip("cv2")
    from tests.cartao_sintetico import desenhar_cartao
    cmd = client.post("/comandas").json()["id_comanda_aleatoria"]
    img = desenhar_cartao(tmp_path / "ruim.png", {"nota_comida": [2, 4], "nota_ambiente": None,
                                                  "nota_atendimento": 5, "recomendaria": "sim"})
    with open(img, "rb") as f:
        r = client.post("/avaliacoes/leitura-otica", data={"codigo_cartao": cartoes[4], "id_comanda": cmd},
                        files={"foto": ("cartao.png", f, "image/png")})
    assert r.status_code == 422
    situacoes = {l["campo"]: l["situacao"] for l in r.json()["detail"]["linhas"]}
    assert situacoes == {"nota_comida": "ambigua", "nota_ambiente": "em_branco"}
    assert client.get(f"/cartoes/{cartoes[4]}").json()["utilizado"] is False


# ------------------------------------------------------------------ ciclo da mesa
def test_ciclo_completo_da_mesa(client, grupo):
    # o garçom marca a mesa como desocupada quando o grupo sai
    estados = [client.post("/mesas/1/avancar", json={"id_garcom": 3}).json()["ciclo_atual"]["status_mesa"]
               for _ in range(3)]
    assert estados == ["desocupada", "limpeza", "pronta"]
    ciclo = client.get("/mesas/1").json()["ciclo_atual"]
    assert ciclo["id_garcom_limpeza"] == 3 and ciclo["delta_tempo_liberacao"] is not None
    assert client.post("/mesas/1/avancar").status_code == 409   # nada a avançar


def test_mesa_suja_recusa_novo_grupo(client):
    client.post("/mesas/2/avancar")                              # grupo saiu: desocupada
    r = client.post("/mesas/2/ocupar", json={"qtd_pessoas": 2})
    assert r.status_code == 409 and "limpeza" in r.json()["detail"]


# ------------------------------------------------------------------ sobras e produção
def test_sobra_com_percentual(client, grupo):
    pid = client.get(f"/comandas/{grupo['ana']}").json()["pesagens"][0]["id_pesagem"]
    r = client.post("/sobras", json={"id_pesagem": pid, "peso_sobra_gramas": 80,
                                     "itens": [{"rotulo": "salada_folhas", "percentual": 75},
                                               {"rotulo": "arroz_branco", "percentual": 25}]})
    assert r.status_code == 201, r.text
    s = r.json()
    assert [i["peso_gramas"] for i in s["itens"]] == [60, 20]
    assert client.post("/sobras", json={"id_pesagem": pid, "peso_sobra_gramas": 10}).status_code == 409


def test_sobra_maior_que_prato_409(client, grupo):
    pid = client.get(f"/comandas/{grupo['beto']}").json()["pesagens"][0]["id_pesagem"]
    assert client.post("/sobras", json={"id_pesagem": pid, "peso_sobra_gramas": 9999}).status_code == 409


def test_producao_upsert_e_validacao(client):
    base = {"data_producao": "2026-11-20", "rotulo": "abobrinha", "peso_produzido_gramas": 5000,
            "peso_descartado_gramas": 1500}
    assert client.post("/producao", json=base).status_code == 200
    r = client.post("/producao", json={**base, "peso_descartado_gramas": 1200})
    assert r.json()["peso_descartado_gramas"] == 1200
    assert client.post("/producao", json={**base, "peso_descartado_gramas": 6000}).status_code == 422


# ------------------------------------------------------------------ cadastros
def test_custo_novo_nao_altera_historico(client, grupo):
    antes = client.get(f"/comandas/{grupo['ana']}").json()["crc"]
    assert client.patch("/ingredientes/file_mignon", json={"custo_kg": "95.00"}).status_code == 200
    depois = client.get(f"/comandas/{grupo['ana']}").json()["crc"]
    assert antes == depois


def test_cadastros(client):
    assert client.post("/garcons", json={"nome": "Carla Dias"}).status_code == 201
    assert client.post("/ingredientes", json={"nome_ingrediente": "Camarão", "rotulo_ia": "camarao",
                                              "categoria": "frutos_mar", "custo_kg": "92.00"}).status_code == 201
    assert client.post("/ingredientes", json={"nome_ingrediente": "Camarão 2", "rotulo_ia": "camarao",
                                              "categoria": "frutos_mar", "custo_kg": "1"}).status_code == 409
    assert client.post("/mesas", json={"numero_mesa": 4, "capacidade": 2}).json()["capacidade"] == 2


# ------------------------------------------------------------------ KPIs
def test_catalogo_e_todas_as_views_respondem(client):
    catalogo = client.get("/kpis").json()
    assert len(catalogo) == 14
    for k in catalogo:
        r = client.get(f"/kpis/{k['nome']}")
        assert r.status_code == 200, (k["nome"], r.text)


def test_kpi_custo_comanda_reflete_a_jornada(client, grupo):
    dados = client.get("/kpis/custo-comanda").json()["dados"]
    ana = next(d for d in dados if d["id_comanda"] == grupo["ana"])
    assert float(ana["crc"]) > 0 and ana["delta_tempo_uso"] is not None


def test_kpi_filtro_por_data_e_inexistente(client):
    r = client.get("/kpis/resumo-diario", params={"data_inicio": "2000-01-01", "data_fim": "2000-01-02"})
    assert r.json()["total"] == 0
    assert client.get("/kpis/vw_comanda; DROP TABLE comanda").status_code == 404
