-- =====================================================================
-- TasteFlow — 05. Dados simulados (MySQL 8.0+)
-- 14 dias de almoço, 20 mesas. Regras da simulação:
--   * pico de fila entre 12h e 13h, mais forte no fim de semana;
--   * cada cliente recebe uma comanda individual;
--   * carnes nobres têm custo/kg muito superior às guarnições;
--   * a satisfação cai à medida que a fila aumenta;
--   * legumes e saladas sobram mais nos pratos e nas cubas.
-- Os valores mudam a cada execução (RAND()).
-- =====================================================================

SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE composicao_sobra; TRUNCATE sobra_prato; TRUNCATE producao_cuba;
TRUNCATE cupom_brinde; TRUNCATE avaliacao; TRUNCATE cartao_pesquisa; TRUNCATE composicao_prato; TRUNCATE foto_prato;
TRUNCATE evento_comanda; TRUNCATE ocupacao_comanda; TRUNCATE ocupacao_mesa;
TRUNCATE pedidos_mesa; TRUNCATE pratos_kilo; TRUNCATE comanda;
TRUNCATE ingrediente; TRUNCATE mesa; TRUNCATE garcom;
SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO garcom (nome) VALUES
  ('Ana Souza'), ('Bruno Lima'), ('Carla Dias'), ('Diego Alves'),
  ('Elisa Rocha'), ('Fábio Nunes');

INSERT INTO mesa (numero_mesa, capacidade)
WITH RECURSIVE n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n WHERE i < 20)
SELECT i, CASE WHEN i % 5 = 0 THEN 6 WHEN i % 3 = 0 THEN 2 ELSE 4 END
FROM n;

INSERT INTO ingrediente (nome_ingrediente, rotulo_ia, categoria, estacao, custo_kg) VALUES
  ('Arroz branco',     'arroz_branco',   'guarnicao',  'buffet',         6.50),
  ('Arroz integral',   'arroz_integral', 'guarnicao',  'buffet',         8.90),
  ('Feijão',           'feijao',         'guarnicao',  'buffet',         9.20),
  ('Farofa',           'farofa',         'guarnicao',  'buffet',        11.00),
  ('Batata frita',     'batata_frita',   'guarnicao',  'buffet',        15.00),
  ('Salada de folhas', 'salada_folhas',  'salada',     'buffet',        12.00),
  ('Tomate',           'tomate',         'salada',     'buffet',         9.50),
  ('Abobrinha',        'abobrinha',      'legume',     'buffet',         8.00),
  ('Couve-flor',       'couve_flor',     'legume',     'buffet',        13.00),
  ('Macarrão',         'macarrao',       'massa',      'buffet',        10.50),
  ('Lasanha',          'lasanha',        'massa',      'buffet',        24.00),
  ('Frango grelhado',  'frango',         'carne',      'buffet',        21.00),
  ('Strogonoff',       'strogonoff',     'carne',      'buffet',        32.00),
  ('Linguiça',         'linguica',       'carne',      'churrasqueira', 27.00),
  ('Alcatra',          'alcatra',        'carne',      'churrasqueira', 48.00),
  ('Picanha',          'picanha',        'carne',      'churrasqueira', 72.00),
  ('Filé mignon',      'file_mignon',    'carne',      'churrasqueira', 78.00),
  ('Camarão',          'camarao',        'frutos_mar', 'buffet',        92.00),
  ('Pudim',            'pudim',          'sobremesa',  'buffet',        18.00);

DROP PROCEDURE IF EXISTS sp_gerar_dados_simulados;
DELIMITER //
CREATE PROCEDURE sp_gerar_dados_simulados(IN p_dias INT)
BEGIN
    DECLARE v_dia INT DEFAULT p_dias;
    DECLARE v_data DATE;
    DECLARE v_fds BOOLEAN;
    DECLARE v_mesa INT;
    DECLARE v_cap INT;
    DECLARE v_t DATETIME;
    DECLARE v_pico DECIMAL(4,2);
    DECLARE v_pessoas INT;
    DECLARE v_p INT;
    DECLARE v_ocup INT;
    DECLARE v_cmd VARCHAR(50);
    DECLARE v_gerado DATETIME;
    DECLARE v_pesou DATETIME;
    DECLARE v_sentado DATETIME;
    DECLARE v_pago DATETIME;
    DECLARE v_saida DATETIME;
    DECLARE v_ultima_saida DATETIME;
    DECLARE v_limp DATETIME;
    DECLARE v_pronta DATETIME;
    DECLARE v_churr DATETIME;
    DECLARE v_garcom INT;
    DECLARE v_preco DECIMAL(10,2);

    WHILE v_dia >= 1 DO
        SET v_data = CURDATE() - INTERVAL v_dia DAY;
        SET v_fds  = DAYOFWEEK(v_data) IN (1, 7);
        SET v_preco = IF(v_fds, 99.90, 89.90);
        SET v_mesa = 1;

        WHILE v_mesa <= 20 DO
            SELECT capacidade INTO v_cap FROM mesa WHERE id_mesa = v_mesa;
            SET v_t = TIMESTAMP(v_data, '11:00:00') + INTERVAL FLOOR(RAND() * 2700) SECOND;

            WHILE v_t < TIMESTAMP(v_data, '14:30:00') DO
                SET v_pico = CASE HOUR(v_t) WHEN 12 THEN 1.0 WHEN 13 THEN 0.5 ELSE 0.1 END
                             * IF(v_fds, 1.4, 1.0);
                SET v_pessoas = LEAST(v_cap, 1 + FLOOR(RAND() * v_cap));
                SET v_garcom  = 1 + FLOOR(RAND() * 4);
                -- o grupo senta depois que o primeiro se serve
                SET v_sentado = v_t + INTERVAL ROUND((3 + RAND() * 4 + v_pico * (5 + RAND() * 8)) * 60) SECOND;
                SET v_ultima_saida = v_sentado;

                INSERT INTO ocupacao_mesa (id_mesa, qtd_pessoas, data_hora_ocupada, id_garcom_abertura)
                VALUES (v_mesa, v_pessoas, v_sentado, v_garcom);
                SET v_ocup = LAST_INSERT_ID();

                SET v_p = 1;
                WHILE v_p <= v_pessoas DO
                    SET v_cmd    = CONCAT('CMD-', UPPER(LEFT(MD5(CONCAT(RAND(), v_ocup, v_p)), 12)));
                    SET v_gerado = v_t + INTERVAL FLOOR(RAND() * 60) SECOND;
                    SET v_pesou  = v_gerado + INTERVAL ROUND((2 + RAND() * 4 + v_pico * (5 + RAND() * 8)) * 60) SECOND;
                    SET v_pago   = GREATEST(v_pesou, v_sentado) + INTERVAL ROUND((30 + RAND() * 35) * 60) SECOND;
                    SET v_saida  = v_pago + INTERVAL ROUND((1 + RAND() * 4) * 60) SECOND;
                    SET v_ultima_saida = GREATEST(v_ultima_saida, v_saida);

                    INSERT INTO comanda (id_comanda_aleatoria, data_hora_gerado, data_hora_pago)
                    VALUES (v_cmd, v_gerado, v_pago);
                    INSERT INTO ocupacao_comanda VALUES (v_ocup, v_cmd);

                    INSERT INTO pratos_kilo (id_comanda, peso_gramas, preco_kg_aplicado, datahora_pesou, sequencia_peso)
                    VALUES (v_cmd, 300 + FLOOR(RAND() * 600), v_preco, v_pesou, 1);
                    IF RAND() < 0.18 THEN   -- repetiu o prato
                        INSERT INTO pratos_kilo (id_comanda, peso_gramas, preco_kg_aplicado, datahora_pesou, sequencia_peso)
                        VALUES (v_cmd, 150 + FLOOR(RAND() * 300), v_preco, v_pesou + INTERVAL 25 MINUTE, 2);
                    END IF;

                    IF RAND() < 0.75 THEN   -- foi à churrasqueira
                        SET v_churr = v_pesou + INTERVAL ROUND((6 + RAND() * 10) * 60) SECOND;
                        INSERT INTO evento_comanda (id_comanda, tipo_evento, data_hora_evento, origem_evento) VALUES
                          (v_cmd, 'chegada_churrasqueira', v_churr, 'leitor'),
                          (v_cmd, 'atendido_churrasqueira',
                           v_churr + INTERVAL ROUND((1 + RAND() * 2 + v_pico * (2 + RAND() * 5)) * 60) SECOND, 'leitor');
                    END IF;

                    IF RAND() < 0.55 THEN   -- chamou o garçom e fez pedido
                        INSERT INTO evento_comanda (id_comanda, tipo_evento, data_hora_evento, origem_evento)
                        VALUES (v_cmd, 'chamado_garcom', v_pesou + INTERVAL 10 MINUTE, 'botao');
                        INSERT INTO pedidos_mesa (id_comanda, id_garcom, item_consumo, quantidade, valor_unitario, data_hora_pedido)
                        SELECT v_cmd, v_garcom, item, 1 + (RAND() < 0.2), preco,
                               v_pesou + INTERVAL 10 MINUTE
                                       + INTERVAL ROUND((1 + RAND() * 3 + v_pico * RAND() * 6) * 60) SECOND
                        FROM (SELECT ELT(k, 'Refrigerante lata', 'Suco natural', 'Água mineral',
                                            'Cerveja long neck', 'Café expresso') AS item,
                                     ELT(k, 7.50, 9.90, 5.00, 12.90, 6.00) AS preco
                              FROM (SELECT 1 + FLOOR(RAND() * 5) AS k) r) x;
                    END IF;

                    INSERT INTO evento_comanda (id_comanda, tipo_evento, data_hora_evento, origem_evento)
                    VALUES (v_cmd, 'saida', v_saida, 'sensor');

                    SET v_p = v_p + 1;
                END WHILE;

                -- encerra o ciclo da mesa
                SET v_limp   = v_ultima_saida + INTERVAL ROUND((0.5 + RAND() * 6 + v_pico * RAND() * 4) * 60) SECOND;
                SET v_pronta = v_limp + INTERVAL ROUND((2.5 + RAND() * 4) * 60) SECOND;
                UPDATE ocupacao_mesa
                   SET data_hora_desocupada = v_ultima_saida,
                       data_hora_inicio_limpeza = v_limp,
                       data_hora_fim_limpeza = v_pronta,
                       id_garcom_limpeza = 5 + FLOOR(RAND() * 2)
                 WHERE id_ocupacao = v_ocup;

                SET v_t = v_pronta + INTERVAL ROUND(RAND() * (20 - 15 * LEAST(v_pico, 1)) * 60) SECOND;
            END WHILE;
            SET v_mesa = v_mesa + 1;
        END WHILE;
        SET v_dia = v_dia - 1;
    END WHILE;
END //
DELIMITER ;

CALL sp_gerar_dados_simulados(14);
DROP PROCEDURE sp_gerar_dados_simulados;

-- Fechamento: mesma regra de sp_fechar_comanda, aplicada em lote
UPDATE comanda c
SET valor_total_comanda =
    COALESCE((SELECT SUM(valor_prato) FROM pratos_kilo WHERE id_comanda = c.id_comanda_aleatoria), 0) +
    COALESCE((SELECT SUM(quantidade * valor_unitario) FROM pedidos_mesa WHERE id_comanda = c.id_comanda_aleatoria), 0);

-- ---------------------------------------------------------------------
-- Visão computacional (simulada): foto e composição de cada prato
-- ---------------------------------------------------------------------
INSERT INTO foto_prato (id_pesagem, url_foto, versao_modelo, data_hora_captura)
SELECT id_pesagem, CONCAT('storage/pratos/', id_pesagem, '.jpg'), 'yolov8n-pratos-v1', datahora_pesou
FROM pratos_kilo;

DROP TEMPORARY TABLE IF EXISTS tmp_perfil;
CREATE TEMPORARY TABLE tmp_perfil (rotulo VARCHAR(50), prob DECIMAL(4,2), peso DECIMAL(4,2));
INSERT INTO tmp_perfil VALUES
  ('arroz_branco', .75, 3.0), ('arroz_integral', .12, 2.5), ('feijao', .60, 2.0),
  ('farofa', .30, 0.6), ('batata_frita', .35, 1.5), ('salada_folhas', .55, 1.2),
  ('tomate', .40, 0.6), ('abobrinha', .15, 0.8), ('couve_flor', .15, 0.8),
  ('macarrao', .25, 2.0), ('lasanha', .15, 2.5), ('frango', .35, 2.0),
  ('strogonoff', .25, 2.0), ('linguica', .40, 1.0), ('alcatra', .40, 2.0),
  ('picanha', .30, 2.2), ('file_mignon', .22, 2.2), ('camarao', .08, 1.5), ('pudim', .10, 0.8);

DROP TEMPORARY TABLE IF EXISTS tmp_sorteio;
CREATE TEMPORARY TABLE tmp_sorteio AS
SELECT pk.id_pesagem, i.id_ingrediente, i.custo_kg, pf.peso * (0.4 + RAND()) AS w
FROM pratos_kilo pk
CROSS JOIN ingrediente i
JOIN tmp_perfil pf ON pf.rotulo = i.rotulo_ia
WHERE RAND() < pf.prob;

INSERT INTO composicao_prato (id_pesagem, id_ingrediente, percentual, custo_kg_aplicado, confianca_ia, origem_classificacao)
SELECT id_pesagem, id_ingrediente,
       GREATEST(0.01, ROUND(100 * w / SUM(w) OVER (PARTITION BY id_pesagem), 2)),
       custo_kg, ROUND(0.72 + RAND() * 0.27, 3), 'ia'
FROM tmp_sorteio;

-- pratos em que nada foi sorteado: arroz + feijão (classificação manual)
INSERT INTO composicao_prato (id_pesagem, id_ingrediente, percentual, custo_kg_aplicado, confianca_ia, origem_classificacao)
SELECT pk.id_pesagem, i.id_ingrediente, IF(i.rotulo_ia = 'arroz_branco', 60, 40), i.custo_kg, NULL, 'manual'
FROM pratos_kilo pk
JOIN ingrediente i ON i.rotulo_ia IN ('arroz_branco', 'feijao')
WHERE NOT EXISTS (SELECT 1 FROM composicao_prato cp WHERE cp.id_pesagem = pk.id_pesagem);

-- >>> SATISFACAO ------------------------------------------------------
-- Cartões raspadinha (~65% devolvem: o brinde garantido estimula a
-- resposta). Escala 0–5; fila longa reduz principalmente o ambiente e a
-- recomendação. Todo cartão gera um cupom de café válido por 7 dias.
-- ---------------------------------------------------------------------
DROP TEMPORARY TABLE IF EXISTS tmp_resp;
CREATE TEMPORARY TABLE tmp_resp AS
SELECT t.id_comanda, c.data_hora_pago, t.min_fila_buffet AS fila,
       CONCAT('C', UPPER(LEFT(MD5(CONCAT('cartao', t.id_comanda, RAND())), 10))) AS codigo_cartao,
       RAND() AS r1, RAND() AS r2, RAND() AS r3, RAND() AS r4, RAND() AS rc, RAND() AS ro,
       1 + FLOOR(RAND() * 4) AS k
FROM vw_tempos_comanda t
JOIN comanda c ON c.id_comanda_aleatoria = t.id_comanda
WHERE c.data_hora_pago IS NOT NULL AND RAND() < 0.65;

-- Lotes impressos (um por dia), incluindo cartões que não voltaram
INSERT INTO cartao_pesquisa (codigo_cartao, lote, data_hora_impressao)
SELECT codigo_cartao, CONCAT('L', DATE_FORMAT(data_hora_pago, '%Y%m%d')),
       TIMESTAMP(DATE(data_hora_pago), '08:00:00')
FROM tmp_resp;
INSERT INTO cartao_pesquisa (codigo_cartao, lote, data_hora_impressao)
SELECT CONCAT('C', UPPER(LEFT(MD5(CONCAT('extra', id_comanda, RAND())), 10))),
       CONCAT('L', DATE_FORMAT(data_hora_pago, '%Y%m%d')),
       TIMESTAMP(DATE(data_hora_pago), '08:00:00')
FROM tmp_resp WHERE RAND() < 0.55;

INSERT INTO avaliacao (codigo_cartao, id_comanda, nota_comida, nota_ambiente, nota_atendimento,
                       recomendaria, comentario, origem_registro, confianca_leitura, data_hora_avaliacao)
SELECT codigo_cartao, id_comanda,
       LEAST(5, GREATEST(0, ROUND(5.6 - r2 * 2.6))),
       LEAST(5, GREATEST(0, ROUND(5.6 - fila * 0.10 - r3 * 2.2))),
       LEAST(5, GREATEST(0, ROUND(5.7 - fila * 0.07 - r4 * 2.4))),
       CASE WHEN ROUND(11.3 - fila * 0.18 - r1 * 3.0) >= 9 THEN 'sim'
            WHEN ROUND(11.3 - fila * 0.18 - r1 * 3.0) >= 7 THEN 'talvez' ELSE 'nao' END,
       CASE WHEN rc >= 0.15 THEN NULL
            WHEN ROUND(11.3 - fila * 0.18 - r1 * 3.0) >= 9
                 THEN ELT(k, 'Comida ótima, voltarei!', 'Picanha no ponto certo',
                             'Ótimo atendimento', 'Ambiente agradável e limpo')
            WHEN ROUND(11.3 - fila * 0.18 - r1 * 3.0) >= 7
                 THEN ELT(LEAST(k, 3), 'Bom, mas a fila estava grande',
                             'Comida boa, preço alto', 'Ok, nada de especial')
            ELSE ELT(k, 'Carne fria', 'Fila enorme na churrasqueira',
                        'Mesa suja quando sentei', 'Demorou para ser atendido')
       END,
       IF(ro < 0.75, 'leitura_otica', 'caixa'),
       IF(ro < 0.75, ROUND(0.88 + RAND() * 0.11, 3), NULL),
       data_hora_pago - INTERVAL 20 SECOND
FROM tmp_resp;

-- Sentimento provisório (regra simples); a API classifica os novos comentários
UPDATE avaliacao
SET sentimento = CASE recomendaria WHEN 'sim' THEN 'positivo' WHEN 'talvez' THEN 'neutro' ELSE 'negativo' END,
    score_sentimento = CASE recomendaria WHEN 'sim' THEN 0.8 WHEN 'talvez' THEN 0.0 ELSE -0.7 END
WHERE comentario IS NOT NULL;

-- Um cupom por avaliação: café expresso grátis por 7 dias
INSERT INTO cupom_brinde (codigo_cupom, id_avaliacao, descricao_brinde, custo_brinde,
                          data_hora_emissao, data_validade)
SELECT CONCAT('B', UPPER(LEFT(MD5(CONCAT('cupom', id_avaliacao, RAND())), 10))),
       id_avaliacao, 'Café expresso', 1.50, data_hora_avaliacao,
       DATE(data_hora_avaliacao) + INTERVAL 7 DAY
FROM avaliacao;

-- Resgates (~38% dos cupons): o cliente volta em outra data dentro da
-- validade e o brinde entra na comanda como item de valor zero
DROP PROCEDURE IF EXISTS sp_simular_resgates;
DELIMITER //
CREATE PROCEDURE sp_simular_resgates()
BEGIN
    DECLARE v_fim BOOLEAN DEFAULT FALSE;
    DECLARE v_cupom VARCHAR(12);
    DECLARE v_emissao DATETIME;
    DECLARE v_validade DATE;
    DECLARE v_descricao VARCHAR(80);
    DECLARE v_cmd VARCHAR(50);
    DECLARE v_pago DATETIME;
    DECLARE cur CURSOR FOR
        SELECT codigo_cupom, data_hora_emissao, data_validade, descricao_brinde
        FROM cupom_brinde WHERE RAND() < 0.38 ORDER BY data_hora_emissao;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fim = TRUE;

    OPEN cur;
    laco: LOOP
        FETCH cur INTO v_cupom, v_emissao, v_validade, v_descricao;
        IF v_fim THEN LEAVE laco; END IF;
        SET v_cmd = NULL;
        SELECT c.id_comanda_aleatoria, c.data_hora_pago INTO v_cmd, v_pago
        FROM comanda c
        WHERE DATE(c.data_hora_gerado) >  DATE(v_emissao)
          AND DATE(c.data_hora_gerado) <= v_validade
          AND c.data_hora_pago IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM cupom_brinde x WHERE x.id_comanda_resgate = c.id_comanda_aleatoria)
        ORDER BY RAND() LIMIT 1;
        IF v_cmd IS NOT NULL THEN
            UPDATE cupom_brinde
               SET id_comanda_resgate = v_cmd, data_hora_resgate = v_pago - INTERVAL 1 MINUTE
             WHERE codigo_cupom = v_cupom;
            INSERT INTO pedidos_mesa (id_comanda, id_garcom, item_consumo, quantidade, valor_unitario, data_hora_pedido)
            VALUES (v_cmd, NULL, CONCAT('Brinde (cupom ', v_cupom, '): ', v_descricao), 1, 0.00,
                    v_pago - INTERVAL 1 MINUTE);
        END IF;
    END LOOP;
    CLOSE cur;
END //
DELIMITER ;
CALL sp_simular_resgates();
DROP PROCEDURE sp_simular_resgates;
-- <<< SATISFACAO ------------------------------------------------------

-- ---------------------------------------------------------------------
-- Sobras nos pratos (~55% das pesagens) e composição da sobra
-- ---------------------------------------------------------------------
INSERT INTO sobra_prato (id_pesagem, peso_sobra_gramas, url_foto, data_hora_descarte)
SELECT id_pesagem, 10 + FLOOR(RAND() * 110), CONCAT('storage/sobras/', id_pesagem, '.jpg'),
       datahora_pesou + INTERVAL 45 MINUTE
FROM pratos_kilo
WHERE RAND() < 0.55;

DROP TEMPORARY TABLE IF EXISTS tmp_pesos_sobra;
CREATE TEMPORARY TABLE tmp_pesos_sobra AS
SELECT s.id_sobra, s.peso_sobra_gramas, cp.id_ingrediente,
       cp.percentual * CASE i.categoria WHEN 'legume' THEN 4 WHEN 'salada' THEN 2.5
                                        WHEN 'guarnicao' THEN 1.2 ELSE 0.6 END * (0.3 + RAND()) AS w
FROM sobra_prato s
JOIN composicao_prato cp ON cp.id_pesagem = s.id_pesagem
JOIN ingrediente i       ON i.id_ingrediente = cp.id_ingrediente;

INSERT INTO composicao_sobra (id_sobra, id_ingrediente, peso_gramas, confianca_ia)
SELECT id_sobra, id_ingrediente,
       ROUND(peso_sobra_gramas * w / SUM(w) OVER (PARTITION BY id_sobra)),
       ROUND(0.70 + RAND() * 0.25, 3)
FROM tmp_pesos_sobra;

-- ---------------------------------------------------------------------
-- Produção das cubas: consumo do dia + margem de segurança
-- ---------------------------------------------------------------------
INSERT INTO producao_cuba (data_producao, turno, id_ingrediente, peso_produzido_gramas, peso_descartado_gramas)
SELECT data, 'almoco', id_ingrediente, ROUND(consumido * (1 + extra)), ROUND(consumido * extra)
FROM (
    SELECT DATE(pk.datahora_pesou) AS data, cp.id_ingrediente,
           SUM(pk.peso_gramas * cp.percentual / 100) AS consumido,
           CASE MAX(i.categoria) WHEN 'legume'     THEN 0.25 + RAND() * 0.20
                                 WHEN 'salada'     THEN 0.15 + RAND() * 0.10
                                 WHEN 'carne'      THEN 0.03 + RAND() * 0.05
                                 WHEN 'frutos_mar' THEN 0.02 + RAND() * 0.03
                                 ELSE 0.08 + RAND() * 0.10 END AS extra
    FROM pratos_kilo pk
    JOIN composicao_prato cp ON cp.id_pesagem = pk.id_pesagem
    JOIN ingrediente i       ON i.id_ingrediente = cp.id_ingrediente
    GROUP BY DATE(pk.datahora_pesou), cp.id_ingrediente
) x;

-- ---------------------------------------------------------------------
-- Estado "ao vivo" para o painel de mesas (ciclos em aberto agora)
-- ---------------------------------------------------------------------
INSERT INTO ocupacao_mesa (id_mesa, qtd_pessoas, data_hora_ocupada, data_hora_desocupada,
                           data_hora_inicio_limpeza, id_garcom_limpeza)
VALUES
  (1, 3, NOW() - INTERVAL 35 MINUTE, NULL, NULL, NULL),
  (2, 2, NOW() - INTERVAL 20 MINUTE, NULL, NULL, NULL),
  (4, 4, NOW() - INTERVAL 48 MINUTE, NULL, NULL, NULL),
  (5, 5, NOW() - INTERVAL 12 MINUTE, NULL, NULL, NULL),
  (7, 2, NOW() - INTERVAL 55 MINUTE, NOW() - INTERVAL 8 MINUTE, NULL, NULL),
  (8, 4, NOW() - INTERVAL 60 MINUTE, NOW() - INTERVAL 2 MINUTE, NULL, NULL),
  (10, 6, NOW() - INTERVAL 70 MINUTE, NOW() - INTERVAL 6 MINUTE, NOW() - INTERVAL 3 MINUTE, 5);
