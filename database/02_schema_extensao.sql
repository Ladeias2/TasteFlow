-- =====================================================================
-- TasteFlow — 02. Extensão do modelo (MySQL 8.0.16+)
-- Novas tabelas, no mesmo padrão de nomenclatura do modelo base,
-- que conectam as comandas aos cinco módulos da solução:
--
--   [Mesas]   mesa, ocupacao_mesa, ocupacao_comanda
--   [Fluxo]   evento_comanda
--   [Mix]     ingrediente, foto_prato, composicao_prato
--   [Satisf.] cartao_pesquisa, avaliacao, cupom_brinde
--   [Sobras]  sobra_prato, composicao_sobra, producao_cuba
--
-- As tabelas do modelo base (01) não são alteradas.
-- =====================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- [MESAS]
-- O ciclo da mesa é registrado apenas pela equipe, num tablet com o mapa
-- do salão; o cliente não precisa interagir com nada.
-- ---------------------------------------------------------------------

-- 5. Tabela de Mesas
CREATE TABLE mesa (
    id_mesa INT AUTO_INCREMENT PRIMARY KEY,
    numero_mesa INT NOT NULL UNIQUE,
    capacidade INT NOT NULL DEFAULT 4,
    ativo BOOLEAN DEFAULT TRUE,

    CHECK (capacidade > 0)
);

-- 6. Tabela de Ocupação de Mesa
-- Uma linha = um ciclo completo da mesa:
--   ocupada → desocupada → limpeza → pronta
-- O status atual e os tempos de cada etapa são colunas geradas,
-- no mesmo padrão de comanda.delta_tempo_uso.
CREATE TABLE ocupacao_mesa (
    id_ocupacao INT AUTO_INCREMENT PRIMARY KEY,
    id_mesa INT NOT NULL,
    qtd_pessoas INT NOT NULL DEFAULT 1,
    data_hora_ocupada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_hora_desocupada DATETIME NULL,
    data_hora_inicio_limpeza DATETIME NULL,
    data_hora_fim_limpeza DATETIME NULL,          -- mesa apta para o próximo grupo
    id_garcom_abertura INT NULL,                  -- quem registrou a chegada do grupo
    id_garcom_limpeza INT NULL,

    status_mesa VARCHAR(12) GENERATED ALWAYS AS (
        CASE
            WHEN data_hora_fim_limpeza    IS NOT NULL THEN 'pronta'
            WHEN data_hora_inicio_limpeza IS NOT NULL THEN 'limpeza'
            WHEN data_hora_desocupada     IS NOT NULL THEN 'desocupada'
            ELSE 'ocupada'
        END) VIRTUAL,
    delta_tempo_permanencia    TIME GENERATED ALWAYS AS (TIMEDIFF(data_hora_desocupada, data_hora_ocupada)) VIRTUAL,
    delta_tempo_espera_limpeza TIME GENERATED ALWAYS AS (TIMEDIFF(data_hora_inicio_limpeza, data_hora_desocupada)) VIRTUAL,
    delta_tempo_limpeza        TIME GENERATED ALWAYS AS (TIMEDIFF(data_hora_fim_limpeza, data_hora_inicio_limpeza)) VIRTUAL,
    delta_tempo_liberacao      TIME GENERATED ALWAYS AS (TIMEDIFF(data_hora_fim_limpeza, data_hora_desocupada)) VIRTUAL,

    FOREIGN KEY (id_mesa) REFERENCES mesa(id_mesa),
    FOREIGN KEY (id_garcom_abertura) REFERENCES garcom(id_garcom) ON DELETE SET NULL,
    FOREIGN KEY (id_garcom_limpeza) REFERENCES garcom(id_garcom) ON DELETE SET NULL,
    CHECK (qtd_pessoas > 0),
    CHECK (data_hora_desocupada     IS NULL OR data_hora_desocupada     >= data_hora_ocupada),
    CHECK (data_hora_inicio_limpeza IS NULL OR data_hora_inicio_limpeza >= data_hora_desocupada),
    CHECK (data_hora_fim_limpeza    IS NULL OR data_hora_fim_limpeza    >= data_hora_inicio_limpeza),
    INDEX idx_ocupacao_mesa_data (id_mesa, data_hora_ocupada)
);

-- 7. Tabela de Comandas por Ocupação (opcional)
-- As comandas são individuais; um grupo sentado na mesma mesa gera
-- várias comandas ligadas à mesma ocupação. O vínculo é feito pelo
-- garçom quando atende a mesa; nenhum indicador depende dele.
CREATE TABLE ocupacao_comanda (
    id_ocupacao INT NOT NULL,
    id_comanda VARCHAR(50) NOT NULL,

    PRIMARY KEY (id_ocupacao, id_comanda),
    FOREIGN KEY (id_ocupacao) REFERENCES ocupacao_mesa(id_ocupacao) ON DELETE CASCADE,
    FOREIGN KEY (id_comanda) REFERENCES comanda(id_comanda_aleatoria) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- [FLUXO]
-- Marcos já existentes no modelo base e reaproveitados:
--   entrada          = comanda.data_hora_gerado
--   fim da fila      = primeira pratos_kilo.datahora_pesou
--   atendimento      = primeiro pedidos_mesa.data_hora_pedido após o chamado
--   pagamento        = comanda.data_hora_pago
-- A tabela abaixo registra apenas os marcos que ainda não existiam.
-- ---------------------------------------------------------------------

-- 8. Tabela de Eventos da Comanda
CREATE TABLE evento_comanda (
    id_evento INT AUTO_INCREMENT PRIMARY KEY,
    id_comanda VARCHAR(50) NOT NULL,
    tipo_evento ENUM('chegada_churrasqueira',     -- entrou na fila da churrasqueira
                     'atendido_churrasqueira',    -- recebeu a carne
                     'chamado_garcom',            -- botão de chamada da mesa (campainha)
                     'saida') NOT NULL,           -- passou pela catraca/porta
    data_hora_evento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    origem_evento ENUM('comanda', 'leitor', 'sensor', 'botao', 'manual') NOT NULL DEFAULT 'comanda',
    id_garcom INT NULL,

    FOREIGN KEY (id_comanda) REFERENCES comanda(id_comanda_aleatoria) ON DELETE CASCADE,
    FOREIGN KEY (id_garcom) REFERENCES garcom(id_garcom) ON DELETE SET NULL,
    INDEX idx_evento_comanda_tipo (id_comanda, tipo_evento),
    INDEX idx_evento_data (data_hora_evento)
);

-- ---------------------------------------------------------------------
-- [MIX DO PRATO / CUSTO]
-- ---------------------------------------------------------------------

-- 9. Tabela de Ingredientes
CREATE TABLE ingrediente (
    id_ingrediente INT AUTO_INCREMENT PRIMARY KEY,
    nome_ingrediente VARCHAR(80) NOT NULL UNIQUE,
    rotulo_ia VARCHAR(50) NOT NULL UNIQUE,      -- classe devolvida pelo modelo de visão computacional
    categoria ENUM('guarnicao', 'salada', 'legume', 'massa', 'carne', 'frutos_mar', 'sobremesa') NOT NULL,
    estacao ENUM('buffet', 'churrasqueira') NOT NULL DEFAULT 'buffet',
    custo_kg DECIMAL(10, 2) NOT NULL,           -- custo de insumo + preparo por kg
    ativo BOOLEAN DEFAULT TRUE,

    CHECK (custo_kg >= 0)
);

-- 10. Tabela de Fotos do Prato (câmera acima da balança)
CREATE TABLE foto_prato (
    id_foto INT AUTO_INCREMENT PRIMARY KEY,
    id_pesagem INT NOT NULL,
    url_foto VARCHAR(255) NOT NULL,
    versao_modelo VARCHAR(30) NULL,             -- ex.: yolov8n-pratos-v1
    data_hora_captura DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (id_pesagem) REFERENCES pratos_kilo(id_pesagem) ON DELETE CASCADE
);

-- 11. Tabela de Composição do Prato (saída da IA)
-- A IA estima o percentual de cada item; os gramas vêm do peso real da balança.
CREATE TABLE composicao_prato (
    id_pesagem INT NOT NULL,
    id_ingrediente INT NOT NULL,
    percentual DECIMAL(5, 2) NOT NULL,
    custo_kg_aplicado DECIMAL(10, 2) NOT NULL,  -- custo congelado na data da pesagem
    confianca_ia DECIMAL(4, 3) NULL,
    origem_classificacao ENUM('ia', 'manual') NOT NULL DEFAULT 'ia',

    PRIMARY KEY (id_pesagem, id_ingrediente),
    FOREIGN KEY (id_pesagem) REFERENCES pratos_kilo(id_pesagem) ON DELETE CASCADE,
    FOREIGN KEY (id_ingrediente) REFERENCES ingrediente(id_ingrediente),
    CHECK (percentual > 0 AND percentual <= 100),
    CHECK (confianca_ia IS NULL OR confianca_ia BETWEEN 0 AND 1)
);

-- ---------------------------------------------------------------------
-- [SATISFAÇÃO]
-- Cartão de papel estilo raspadinha: o cliente raspa com o talher uma
-- bolinha por linha (0 = insatisfeito, 5 = satisfeito) e entrega no caixa.
-- Todo cartão preenchido ganha o mesmo brinde (sem sorteio: o benefício
-- não depende de sorte nem das respostas).
-- ---------------------------------------------------------------------

-- 12. Tabela de Cartões de Pesquisa
-- Cartões impressos em lotes, cada um com código único em código de barras.
-- Só cartões cadastrados geram brinde (evita cópias).
CREATE TABLE cartao_pesquisa (
    codigo_cartao VARCHAR(12) PRIMARY KEY,
    lote VARCHAR(20) NOT NULL,
    data_hora_impressao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_cartao_lote (lote)
);

-- 13. Tabela de Avaliações
CREATE TABLE avaliacao (
    id_avaliacao INT AUTO_INCREMENT PRIMARY KEY,
    codigo_cartao VARCHAR(12) NOT NULL UNIQUE,  -- um cartão vale uma vez
    id_comanda VARCHAR(50) NOT NULL UNIQUE,     -- uma avaliação por comanda
    nota_comida TINYINT NOT NULL,               -- 0 (insatisfeito) a 5 (satisfeito)
    nota_ambiente TINYINT NOT NULL,
    nota_atendimento TINYINT NOT NULL,
    recomendaria ENUM('sim', 'talvez', 'nao') NOT NULL,
    comentario TEXT NULL,                       -- linha opcional, digitada pelo caixa
    sentimento ENUM('positivo', 'neutro', 'negativo') NULL,
    score_sentimento DECIMAL(4, 3) NULL,        -- de -1 a 1
    origem_registro ENUM('caixa', 'leitura_otica') NOT NULL DEFAULT 'caixa',
    confianca_leitura DECIMAL(4, 3) NULL,       -- só para leitura óptica
    data_hora_avaliacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (codigo_cartao) REFERENCES cartao_pesquisa(codigo_cartao),
    FOREIGN KEY (id_comanda) REFERENCES comanda(id_comanda_aleatoria) ON DELETE CASCADE,
    CHECK (nota_comida      BETWEEN 0 AND 5),
    CHECK (nota_ambiente    BETWEEN 0 AND 5),
    CHECK (nota_atendimento BETWEEN 0 AND 5),
    CHECK (confianca_leitura IS NULL OR confianca_leitura BETWEEN 0 AND 1)
);

-- 14. Tabela de Cupons de Brinde
-- Emitido para toda avaliação; válido por 7 dias; resgatado numa visita
-- seguinte (o resgate entra como item de valor zero em pedidos_mesa).
CREATE TABLE cupom_brinde (
    codigo_cupom VARCHAR(12) PRIMARY KEY,
    id_avaliacao INT NOT NULL UNIQUE,
    descricao_brinde VARCHAR(80) NOT NULL,      -- ex.: Café expresso
    custo_brinde DECIMAL(10, 2) NOT NULL,       -- custo para o restaurante
    data_hora_emissao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_validade DATE NOT NULL,
    id_comanda_resgate VARCHAR(50) NULL UNIQUE, -- um cupom por visita
    data_hora_resgate DATETIME NULL,

    FOREIGN KEY (id_avaliacao) REFERENCES avaliacao(id_avaliacao) ON DELETE CASCADE,
    FOREIGN KEY (id_comanda_resgate) REFERENCES comanda(id_comanda_aleatoria),
    CHECK (custo_brinde >= 0),
    CHECK ((id_comanda_resgate IS NULL) = (data_hora_resgate IS NULL))
);

-- ---------------------------------------------------------------------
-- [SOBRAS]
-- ---------------------------------------------------------------------

-- 15. Tabela de Sobras do Prato (balança da estação de descarte)
CREATE TABLE sobra_prato (
    id_sobra INT AUTO_INCREMENT PRIMARY KEY,
    id_pesagem INT NOT NULL,
    peso_sobra_gramas INT NOT NULL,
    url_foto VARCHAR(255) NULL,
    data_hora_descarte DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (id_pesagem) REFERENCES pratos_kilo(id_pesagem) ON DELETE CASCADE,
    CHECK (peso_sobra_gramas >= 0)
);

-- 16. Tabela de Composição da Sobra (saída da IA)
CREATE TABLE composicao_sobra (
    id_sobra INT NOT NULL,
    id_ingrediente INT NOT NULL,
    peso_gramas INT NOT NULL,
    confianca_ia DECIMAL(4, 3) NULL,

    PRIMARY KEY (id_sobra, id_ingrediente),
    FOREIGN KEY (id_sobra) REFERENCES sobra_prato(id_sobra) ON DELETE CASCADE,
    FOREIGN KEY (id_ingrediente) REFERENCES ingrediente(id_ingrediente),
    CHECK (peso_gramas >= 0)
);

-- 17. Tabela de Produção das Cubas
-- Quanto foi produzido de cada item e quanto foi descartado da cuba
-- ao final do turno (nunca chegou ao prato do cliente).
CREATE TABLE producao_cuba (
    id_producao INT AUTO_INCREMENT PRIMARY KEY,
    data_producao DATE NOT NULL,
    turno ENUM('almoco', 'jantar') NOT NULL DEFAULT 'almoco',
    id_ingrediente INT NOT NULL,
    peso_produzido_gramas INT NOT NULL,
    peso_descartado_gramas INT NOT NULL DEFAULT 0,

    UNIQUE (data_producao, turno, id_ingrediente),
    FOREIGN KEY (id_ingrediente) REFERENCES ingrediente(id_ingrediente),
    CHECK (peso_produzido_gramas >= 0),
    CHECK (peso_descartado_gramas BETWEEN 0 AND peso_produzido_gramas)
);
