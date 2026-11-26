-- =====================================================================
-- TasteFlow — 03. Regras de negócio (MySQL 8.0+)
-- Triggers e procedures chamadas pelo backend (FastAPI).
-- Execute pelo cliente mysql (usa DELIMITER).
-- =====================================================================

SET NAMES utf8mb4;

DROP TRIGGER IF EXISTS trg_ocupacao_unica;
DROP PROCEDURE IF EXISTS sp_fechar_comanda;
DROP PROCEDURE IF EXISTS sp_ocupar_mesa;
DROP PROCEDURE IF EXISTS sp_avancar_status_mesa;
DROP PROCEDURE IF EXISTS sp_resgatar_cupom;

DELIMITER //

-- ---------------------------------------------------------------------
-- Uma mesa não pode iniciar um novo ciclo enquanto o anterior não
-- estiver concluído (limpeza finalizada).
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_ocupacao_unica
BEFORE INSERT ON ocupacao_mesa
FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM ocupacao_mesa
               WHERE id_mesa = NEW.id_mesa
                 AND data_hora_fim_limpeza IS NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Mesa possui um ciclo em aberto (ocupada, desocupada ou em limpeza).';
    END IF;
END //

-- ---------------------------------------------------------------------
-- sp_fechar_comanda: consulta de fechamento original da equipe,
-- parametrizada.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_fechar_comanda(IN p_id_comanda VARCHAR(50))
BEGIN
    UPDATE comanda c
    SET
        data_hora_pago = CURRENT_TIMESTAMP,
        valor_total_comanda = (
            COALESCE((SELECT SUM(valor_prato) FROM pratos_kilo WHERE id_comanda = c.id_comanda_aleatoria), 0) +
            COALESCE((SELECT SUM(quantidade * valor_unitario) FROM pedidos_mesa WHERE id_comanda = c.id_comanda_aleatoria), 0)
        )
    WHERE c.id_comanda_aleatoria = p_id_comanda;
END //

-- ---------------------------------------------------------------------
-- sp_ocupar_mesa: o garçom toca na mesa (tablet) quando o grupo senta.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_ocupar_mesa(IN p_numero_mesa INT, IN p_qtd_pessoas INT, IN p_id_garcom INT)
BEGIN
    DECLARE v_id_mesa INT;
    DECLARE v_status VARCHAR(12);

    SELECT id_mesa INTO v_id_mesa FROM mesa WHERE numero_mesa = p_numero_mesa AND ativo;
    IF v_id_mesa IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Mesa inexistente ou inativa.';
    END IF;

    SELECT status_mesa INTO v_status
    FROM ocupacao_mesa
    WHERE id_mesa = v_id_mesa
    ORDER BY data_hora_ocupada DESC, id_ocupacao DESC
    LIMIT 1;

    IF v_status IS NOT NULL AND v_status <> 'pronta' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Mesa não está livre (ocupada ou aguardando limpeza).';
    END IF;

    INSERT INTO ocupacao_mesa (id_mesa, qtd_pessoas, id_garcom_abertura)
    VALUES (v_id_mesa, p_qtd_pessoas, p_id_garcom);

    SELECT LAST_INSERT_ID() AS id_ocupacao;
END //

-- ---------------------------------------------------------------------
-- sp_avancar_status_mesa: cada toque do funcionário avança uma etapa:
--   ocupada → desocupada → limpeza → pronta
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_avancar_status_mesa(IN p_numero_mesa INT, IN p_id_garcom INT)
BEGIN
    DECLARE v_id_ocupacao INT;
    DECLARE v_status VARCHAR(12);

    SELECT o.id_ocupacao, o.status_mesa INTO v_id_ocupacao, v_status
    FROM ocupacao_mesa o
    JOIN mesa m ON m.id_mesa = o.id_mesa
    WHERE m.numero_mesa = p_numero_mesa
    ORDER BY o.data_hora_ocupada DESC, o.id_ocupacao DESC
    LIMIT 1;

    CASE v_status
        WHEN 'ocupada' THEN
            UPDATE ocupacao_mesa SET data_hora_desocupada = NOW() WHERE id_ocupacao = v_id_ocupacao;
        WHEN 'desocupada' THEN
            UPDATE ocupacao_mesa SET data_hora_inicio_limpeza = NOW(), id_garcom_limpeza = p_id_garcom
            WHERE id_ocupacao = v_id_ocupacao;
        WHEN 'limpeza' THEN
            UPDATE ocupacao_mesa SET data_hora_fim_limpeza = NOW() WHERE id_ocupacao = v_id_ocupacao;
        ELSE
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Mesa já está livre; não há ciclo em aberto.';
    END CASE;

    SELECT id_ocupacao, status_mesa FROM ocupacao_mesa WHERE id_ocupacao = v_id_ocupacao;
END //

-- ---------------------------------------------------------------------
-- sp_resgatar_cupom: o cliente volta e apresenta o cupom no caixa.
-- O brinde entra na comanda como item de valor zero, assim o fechamento
-- original (sp_fechar_comanda) continua correto sem alteração.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_resgatar_cupom(IN p_codigo_cupom VARCHAR(12), IN p_id_comanda VARCHAR(50))
BEGIN
    DECLARE v_validade DATE;
    DECLARE v_resgate VARCHAR(50);
    DECLARE v_descricao VARCHAR(80);
    DECLARE v_comanda_origem VARCHAR(50);
    DECLARE v_pago DATETIME;
    DECLARE v_existe INT DEFAULT 0;

    SELECT COUNT(*) INTO v_existe FROM cupom_brinde WHERE codigo_cupom = p_codigo_cupom;
    IF v_existe = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cupom inexistente.';
    END IF;

    SELECT cb.data_validade, cb.id_comanda_resgate, cb.descricao_brinde, a.id_comanda
      INTO v_validade, v_resgate, v_descricao, v_comanda_origem
    FROM cupom_brinde cb JOIN avaliacao a ON a.id_avaliacao = cb.id_avaliacao
    WHERE cb.codigo_cupom = p_codigo_cupom;

    IF v_resgate IS NOT NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cupom já resgatado.';
    END IF;
    IF v_validade < CURDATE() THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cupom vencido.';
    END IF;
    IF v_comanda_origem = p_id_comanda THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'O cupom vale para uma próxima visita.';
    END IF;

    SELECT data_hora_pago INTO v_pago FROM comanda WHERE id_comanda_aleatoria = p_id_comanda;
    IF v_pago IS NOT NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Comanda já foi paga.';
    END IF;

    UPDATE cupom_brinde
       SET id_comanda_resgate = p_id_comanda, data_hora_resgate = NOW()
     WHERE codigo_cupom = p_codigo_cupom;

    INSERT INTO pedidos_mesa (id_comanda, id_garcom, item_consumo, quantidade, valor_unitario)
    VALUES (p_id_comanda, NULL, CONCAT('Brinde (cupom ', p_codigo_cupom, '): ', v_descricao), 1, 0.00);
END //

DELIMITER ;
