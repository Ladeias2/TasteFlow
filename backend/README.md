# Back-end — API TasteFlow

API REST em **Python + FastAPI** que recebe os dados das estações de captura (balança + câmera, tablet do salão, leitores e sensores, cartão de satisfação) e expõe os indicadores do banco para o dashboard.

As regras críticas já estão no banco (trigger, procedures, colunas geradas e views). A API **valida, orquestra e traduz erros**, sem duplicar essas regras.

## Estrutura

```
backend/
├── app/
│   ├── main.py              aplicação, CORS e /saude
│   ├── config.py            variáveis de ambiente (.env)
│   ├── database.py          conexão MySQL (SQLAlchemy Core) e chamada de procedures
│   ├── errors.py            erros do MySQL → HTTP (409, 422...)
│   ├── schemas.py           contratos de entrada (Pydantic)
│   ├── routers/
│   │   ├── comandas.py      /comandas, /pedidos
│   │   ├── pesagens.py      /pesagens (Mix e Custo)
│   │   ├── eventos.py       /eventos (Fluxo)
│   │   ├── mesas.py         /mesas (mapa do salão operado pela equipe)
│   │   ├── avaliacoes.py    /avaliacoes, /cartoes, /cupons (Satisfação)
│   │   ├── sobras.py        /sobras, /producao (Sobras)
│   │   ├── cadastros.py     /garcons, /ingredientes
│   │   └── kpis.py          /kpis (14 indicadores)
│   └── services/
│       ├── regras.py        regras compartilhadas (comanda aberta/paga, composição, custo)
│       ├── visao.py         YOLOv8-seg: máscaras → percentual por alimento
│       ├── leitura_cartao.py leitura óptica do cartão raspadinha (OMR)
│       └── sentimento.py    análise de sentimento dos comentários
├── tests/                   60 testes (pytest) contra um MySQL real
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Como executar

**Opção 1: Docker (banco + API).** Na raiz do repositório:

```bash
docker compose up --build
```

O MySQL executa os scripts de `database/` (inclusive os dados simulados) na primeira inicialização. A API fica em http://localhost:8000/docs.

**Opção 2: local**, com o banco já criado pelos scripts de `database/`:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # ajuste usuário e senha do MySQL
uvicorn app.main:app --reload
```

Acesse **http://localhost:8000/docs** para a documentação interativa (Swagger), onde todos os endpoints podem ser testados.

## Endpoints

| Método | Rota | Quem chama | O que faz |
|---|---|---|---|
| POST | `/comandas` | Porta | Gera a comanda individual (código aleatório) |
| GET | `/comandas/{id}` | Cliente / caixa | Pesagens com custo, pedidos, eventos, mesa, tempos e CRC |
| POST | `/comandas/{id}/fechar` | Caixa | `sp_fechar_comanda`: soma pesagens e pedidos e grava o pagamento |
| POST | `/pedidos` | Garçom | Registra item pedido à mesa |
| POST | `/pesagens` | Balança + IA na borda | Grava a pesagem e a composição e devolve ICC e margem |
| POST | `/pesagens/foto` | Balança (só foto) | Inferência YOLOv8 no servidor (503 sem modelo configurado) |
| GET | `/pesagens/{id}` | Dashboard | Composição em gramas, custo e confiança |
| PUT | `/pesagens/{id}/composicao` | Funcionário | Correção manual quando a IA tem baixa confiança |
| POST | `/eventos` | Leitores / sensores | Churrasqueira, chamado do garçom e saída |
| GET | `/mesas` | Tablet / painel | Mapa do salão (verde, amarelo, vermelho) e alertas |
| POST | `/mesas` | Gestor | Cadastra mesa |
| GET | `/mesas/{numero}` | Tablet | Mesa e ciclo atual |
| POST | `/mesas/{numero}/ocupar` | Garçom | `sp_ocupar_mesa`: registra a chegada do grupo |
| POST | `/mesas/{numero}/comandas` | Garçom | Vincula uma comanda ao grupo (opcional) |
| POST | `/mesas/{numero}/avancar` | Funcionário | `sp_avancar_status_mesa`: desocupada → limpeza → pronta |
| POST | `/cartoes/lote` | Gestor | Gera os códigos de um lote de cartões para impressão |
| GET | `/cartoes/{codigo}` | Caixa | Verifica se o cartão existe e se já foi usado |
| POST | `/avaliacoes` | Caixa | Lança o cartão (notas 0–5 + recomendaria) e emite o cupom de brinde |
| POST | `/avaliacoes/leitura-otica` | Urna com câmera | Lê o cartão por foto (OMR); se houver dúvida, devolve 422 para o caixa |
| GET | `/avaliacoes/{id}` | Caixa | Avaliação e cupom de uma comanda |
| GET | `/cupons/{codigo}` | Caixa | Situação do cupom: ativo, resgatado ou vencido |
| POST | `/cupons/{codigo}/resgatar` | Caixa | `sp_resgatar_cupom`: brinde entra na comanda com valor zero |
| POST | `/sobras` | Estação de descarte | Sobra do prato e sua composição |
| POST | `/sobras/foto` | Estação de descarte | Inferência no servidor (503 sem modelo) |
| POST | `/producao` | Cozinha | Produção e descarte da cuba (atualiza se já existir) |
| GET/POST | `/garcons` | Gestor | Funcionários |
| GET/POST | `/ingredientes` | Gestor | Ingredientes, rótulo da IA e custo/kg |
| PATCH | `/ingredientes/{rotulo}` | Gestor | Novo custo, que vale só para pesagens futuras |
| GET | `/kpis` | Dashboard | Catálogo dos 14 indicadores |
| GET | `/kpis/{nome}` | Dashboard | Dados de uma view, com filtro `data_inicio` e `data_fim` |
| GET | `/saude` | Monitoramento | API e banco no ar |

## Regras validadas pela API

| Regra | Resposta |
|---|---|
| Pesagem, pedido, chamado ou churrasqueira em comanda **já paga** | 409 |
| Saída em comanda **não paga** | 409 |
| Segunda saída, segunda avaliação da comanda ou segunda sobra do mesmo prato | 409 |
| Cartão de satisfação não cadastrado (cópia ou falsificado) | 404 |
| Cartão já utilizado | 409 |
| Cupom já resgatado, vencido ou usado na mesma visita em que foi ganho | 409 |
| Atendimento na churrasqueira sem chegada pendente, ou entrar duas vezes na fila | 409 |
| Comanda vinculada a duas mesas ao mesmo tempo | 409 |
| Ocupar mesa ocupada ou aguardando limpeza (`sp_ocupar_mesa`) | 409 |
| Grupo maior que a capacidade da mesa (+2 cadeiras) | 409 |
| Nova ocupação com ciclo em aberto (`trg_ocupacao_unica`) | 409 |
| Rótulo da IA sem ingrediente ativo cadastrado | 422 (e nada é gravado) |
| Nota fora de 0 a 5, descarte maior que a produção, sobra maior que o prato | 422 / 409 |
| Leitura óptica com linha em branco ou duas bolinhas raspadas | 422 com diagnóstico; nada é gravado |
| Percentuais da IA que não somam 100 | Normalizados |
| Confiança média da IA abaixo de `CONFIANCA_MINIMA` | `revisao_necessaria: true` |

Cada requisição roda numa **transação única**: se qualquer passo falhar, nada é gravado.

## Exemplos

```bash
# 1. cliente entra
curl -X POST localhost:8000/comandas
# → {"id_comanda_aleatoria": "CMD-7F3A9C21B0D4", ...}

# 2. balança + IA registram o prato
curl -X POST localhost:8000/pesagens -H "Content-Type: application/json" -d '{
  "id_comanda": "CMD-7F3A9C21B0D4", "peso_gramas": 850, "preco_kg_aplicado": 89.90,
  "itens": [
    {"rotulo": "file_mignon",   "percentual": 50, "confianca": 0.88},
    {"rotulo": "arroz_branco",  "percentual": 20, "confianca": 0.94},
    {"rotulo": "salada_folhas", "percentual": 20, "confianca": 0.86},
    {"rotulo": "feijao",        "percentual": 10, "confianca": 0.91}]}'
# → valor_prato 76.42, icc 37.08, margem 39.34, composicao em gramas

# 3. garçom registra a chegada do grupo de 2 na mesa 3 (tablet)
curl -X POST localhost:8000/mesas/3/ocupar -H "Content-Type: application/json" \
     -d '{"qtd_pessoas": 2, "id_garcom": 1}'

# 4. no caixa: lança o cartão raspadinha e emite o cupom de brinde
curl -X POST localhost:8000/avaliacoes -H "Content-Type: application/json" -d '{
  "codigo_cartao": "C4F7A21B9E0", "id_comanda": "CMD-7F3A9C21B0D4",
  "nota_comida": 5, "nota_ambiente": 4, "nota_atendimento": 5, "recomendaria": "sim"}'
# → cupom {"codigo_cupom": "B19C0D7E2A4", "descricao_brinde": "Café expresso", "data_validade": ...}

# 5. paga (a resposta traz o cupom para imprimir na nota)
curl -X POST localhost:8000/comandas/CMD-7F3A9C21B0D4/fechar

# 6. funcionário toca na mesa três vezes: desocupada → limpeza → pronta
curl -X POST localhost:8000/mesas/3/avancar -H "Content-Type: application/json" -d '{"id_garcom": 5}'

# dias depois, o cliente volta e resgata o café
curl -X POST localhost:8000/cupons/B19C0D7E2A4/resgatar -H "Content-Type: application/json" \
     -d '{"id_comanda": "CMD-0A1B2C3D4E5F"}'

# 7. indicadores
curl "localhost:8000/kpis/resumo-diario?data_inicio=2026-11-20"
```

## Testes

```bash
cd backend
pytest
```

Os testes criam um banco `restaurante_teste` do zero com os scripts de `database/`, executam a jornada completa de um grupo (entrada, pesagem, mesa, churrasqueira, garçom, cartão de satisfação, pagamento, saída, limpeza, sobra, resgate do brinde) e todos os casos de erro, e apagam o banco ao final. A leitura óptica é testada com cartões sintéticos desenhados com OpenCV, incluindo linhas em branco e ambíguas; sem OpenCV instalado, esses dois testes são pulados. É preciso ter o cliente `mysql` no PATH e um usuário com permissão para criar bancos. Ajuste com as variáveis `TEST_DB_HOST`, `TEST_DB_USER` e `TEST_DB_PASSWORD`.

## Visão computacional

A API aceita dois modos:

1. **Inferência na borda (recomendado):** a estação da balança roda o modelo e envia a composição pronta em `POST /pesagens`.
2. **Inferência no servidor:** a estação envia só a foto em `POST /pesagens/foto`. Exige `pip install ultralytics` e `MODELO_VISAO_PATH` apontando para os pesos treinados. O repositório traz o modelo de demonstração em `ia/modelos/tasteflow-seg-demo.pt` (já configurado no `.env.example`). Sem o modelo, a rota responde 503.

O treino do modelo, a estação da balança e o caminho para o modelo de produção estão em [`ia/README.md`](../ia/README.md).

Nos dois casos, `services/visao.py` converte as máscaras de segmentação em percentual por alimento, e o banco calcula os gramas com o peso real da balança. As classes do modelo devem ter o mesmo nome de `ingrediente.rotulo_ia`.

## Cartão de satisfação e leitura óptica

O cartão tem quatro linhas de bolinhas cobertas por tinta raspável: comida, ambiente e atendimento (0 a 5) e "Recomendaria?" (sim, talvez, não). Cada cartão tem um código de barras gerado em `POST /cartoes/lote`, e só cartões cadastrados geram brinde.

`services/leitura_cartao.py` lê a foto tirada pela urna: mede a escuridão de cada bolinha nas posições do gabarito e escolhe a raspada em cada linha. Se uma linha estiver em branco ou tiver duas bolinhas raspadas com escuridão parecida, a leitura é recusada, e o caixa lança o cartão. As coordenadas de `GABARITO` devem seguir a arte impressa do cartão.

O brinde (padrão: café expresso, custo R$ 1,50, validade de 7 dias) é configurado no `.env`. Ele é o mesmo para todos e não depende das respostas. Assim não há sorteio, que exigiria autorização prévia (Lei 5.768/1971), e o cliente não tem motivo para inflar as notas.

## Sentimento

`services/sentimento.py` traz uma implementação de referência baseada em léxico do português, com tratamento de negação ("não estava boa" é negativo) e intensificadores. A interface `analisar(texto) -> (rotulo, score)` permite trocar por um modelo pré-treinado sem alterar a API.
