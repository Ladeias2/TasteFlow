-- =====================================================================
-- TasteFlow — 01. Modelo base (MySQL 8.0+)
-- Tabelas originais do sistema de comandas eletrônicas.
-- Estrutura mantida conforme definida pela equipe.
-- =====================================================================

SET NAMES utf8mb4;

-- 1. Tabela de Garçons
CREATE TABLE garcom (
    id_garcom INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    ativo BOOLEAN DEFAULT TRUE
);

-- 2. Tabela de Comandas
-- Cada cliente recebe uma comanda individual na entrada (id aleatório
-- impresso em QR Code). delta_tempo_uso mede o tempo entre a geração
-- da comanda e o pagamento.
CREATE TABLE comanda (
    id_comanda_aleatoria VARCHAR(50) PRIMARY KEY,
    data_hora_gerado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_hora_pago DATETIME NULL,
    delta_tempo_uso TIME GENERATED ALWAYS AS (TIMEDIFF(data_hora_pago, data_hora_gerado)) VIRTUAL,
    valor_total_comanda DECIMAL(10, 2) NOT NULL DEFAULT 0.00
);

-- 3. Tabela de Pesagem de Pratos (Kilo)
CREATE TABLE pratos_kilo (
    id_pesagem INT AUTO_INCREMENT PRIMARY KEY,
    id_comanda VARCHAR(50) NOT NULL,
    peso_gramas INT NOT NULL,
    preco_kg_aplicado DECIMAL(10, 2) NOT NULL, -- Ex: 79.90
    valor_prato DECIMAL(10, 2) GENERATED ALWAYS AS (ROUND((peso_gramas / 1000.0) * preco_kg_aplicado, 2)) STORED,
    datahora_pesou DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sequencia_peso INT NOT NULL,

    FOREIGN KEY (id_comanda) REFERENCES comanda(id_comanda_aleatoria) ON DELETE CASCADE
);

-- 4. Tabela de Pedidos na Mesa
CREATE TABLE pedidos_mesa (
    id_pedido INT AUTO_INCREMENT PRIMARY KEY,
    id_comanda VARCHAR(50) NOT NULL,
    id_garcom INT NULL,
    item_consumo VARCHAR(150) NOT NULL,
    quantidade INT NOT NULL DEFAULT 1,
    valor_unitario DECIMAL(10, 2) NOT NULL,
    data_hora_pedido DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (id_comanda) REFERENCES comanda(id_comanda_aleatoria) ON DELETE CASCADE,
    FOREIGN KEY (id_garcom) REFERENCES garcom(id_garcom) ON DELETE SET NULL
);

-- Fechamento de comanda (consulta original da equipe).
-- Encapsulada na procedure sp_fechar_comanda em 03_procedures_triggers.sql.
--
-- UPDATE comanda c
-- SET
--     data_hora_pago = CURRENT_TIMESTAMP,
--     valor_total_comanda = (
--         COALESCE((SELECT SUM(valor_prato) FROM pratos_kilo WHERE id_comanda = c.id_comanda_aleatoria), 0) +
--         COALESCE((SELECT SUM(quantidade * valor_unitario) FROM pedidos_mesa WHERE id_comanda = c.id_comanda_aleatoria), 0)
--     )
-- WHERE c.id_comanda_aleatoria = 'CODIGO_DA_COMANDA';
