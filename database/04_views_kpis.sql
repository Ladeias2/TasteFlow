-- =====================================================================
-- TasteFlow — 04. Views de indicadores (MySQL 8.0+)
-- Camada semântica consumida pelo dashboard (Power BI / aplicação web).
-- Convenção: tempos em minutos (decimal), valores em R$.
-- =====================================================================

SET NAMES utf8mb4;

-- =====================================================================
-- [MIX / CUSTO]
-- =====================================================================

-- Índice de Custo do Cliente (ICC) por pesagem:
-- ICC = Σ (peso do prato × percentual do item × custo/kg do item)
CREATE OR REPLACE VIEW vw_custo_pesagem AS
SELECT
    pk.id_pesagem,
    pk.id_comanda,
    pk.sequencia_peso,
    pk.datahora_pesou,
    pk.peso_gramas,
    pk.valor_prato                                                         AS receita,
    ROUND(SUM(pk.peso_gramas * cp.percentual / 100 / 1000 * cp.custo_kg_aplicado), 2) AS icc,
    ROUND(SUM(CASE WHEN i.categoria IN ('carne', 'frutos_mar') THEN cp.percentual ELSE 0 END), 1)
                                                                           AS pct_proteina
FROM pratos_kilo pk
JOIN composicao_prato cp ON cp.id_pesagem = pk.id_pesagem
JOIN ingrediente i       ON i.id_ingrediente = cp.id_ingrediente
GROUP BY pk.id_pesagem;

-- Custo Real por Cliente (CRC): a comanda é individual, então cada
-- linha representa um cliente.
CREATE OR REPLACE VIEW vw_custo_comanda AS
SELECT
    c.id_comanda_aleatoria                                    AS id_comanda,
    DATE(c.data_hora_gerado)                                  AS data,
    HOUR(c.data_hora_gerado)                                  AS hora,
    c.delta_tempo_uso,
    SUM(cp.peso_gramas)                                       AS peso_total_gramas,
    SUM(cp.receita)                                           AS receita_buffet,
    COALESCE(pm.receita_mesa, 0)                              AS receita_mesa,
    c.valor_total_comanda,
    SUM(cp.icc)                                               AS crc,
    SUM(cp.receita) - SUM(cp.icc)                             AS margem_buffet,
    ROUND(100 * (SUM(cp.receita) - SUM(cp.icc)) / NULLIF(SUM(cp.receita), 0), 1) AS margem_buffet_pct,
    ROUND(SUM(cp.icc) / NULLIF(SUM(cp.peso_gramas), 0) * 1000, 2)               AS custo_medio_kg,
    ROUND(SUM(cp.pct_proteina * cp.peso_gramas) / NULLIF(SUM(cp.peso_gramas), 0), 1) AS pct_proteina
FROM comanda c
JOIN vw_custo_pesagem cp ON cp.id_comanda = c.id_comanda_aleatoria
LEFT JOIN (SELECT id_comanda, SUM(quantidade * valor_unitario) AS receita_mesa
           FROM pedidos_mesa GROUP BY id_comanda) pm
       ON pm.id_comanda = c.id_comanda_aleatoria
GROUP BY c.id_comanda_aleatoria, pm.receita_mesa;

-- Rentabilidade por ingrediente: participação no peso servido × no custo
CREATE OR REPLACE VIEW vw_rentabilidade_ingrediente AS
WITH consumo AS (
    SELECT i.id_ingrediente, i.nome_ingrediente, i.categoria, i.custo_kg,
           SUM(pk.peso_gramas * cp.percentual / 100)                                AS consumido_g,
           SUM(pk.peso_gramas * cp.percentual / 100 / 1000 * cp.custo_kg_aplicado)  AS custo_total,
           SUM(pk.peso_gramas * cp.percentual / 100 / 1000 * pk.preco_kg_aplicado)  AS receita_atribuida
    FROM composicao_prato cp
    JOIN pratos_kilo pk ON pk.id_pesagem = cp.id_pesagem
    JOIN ingrediente i  ON i.id_ingrediente = cp.id_ingrediente
    GROUP BY i.id_ingrediente
)
SELECT nome_ingrediente, categoria, custo_kg,
       ROUND(consumido_g / 1000, 1)                              AS consumido_kg,
       ROUND(custo_total, 2)                                     AS custo_total,
       ROUND(receita_atribuida - custo_total, 2)                 AS margem_atribuida,
       ROUND(100 * consumido_g / SUM(consumido_g) OVER (), 1)    AS pct_do_peso,
       ROUND(100 * custo_total / SUM(custo_total) OVER (), 1)    AS pct_do_custo
FROM consumo
ORDER BY custo_total DESC;

-- =====================================================================
-- [FLUXO]
-- =====================================================================

-- Tempos de cada etapa por comanda (minutos)
CREATE OR REPLACE VIEW vw_tempos_comanda AS
SELECT
    c.id_comanda_aleatoria                                                          AS id_comanda,
    c.data_hora_gerado                                                              AS entrada,
    DATE(c.data_hora_gerado)                                                        AS data,
    HOUR(c.data_hora_gerado)                                                        AS hora,
    ROUND(TIMESTAMPDIFF(SECOND, c.data_hora_gerado, p.primeira_pesagem) / 60, 1)    AS min_fila_buffet,
    ROUND(TIMESTAMPDIFF(SECOND, e.churr_chegada, e.churr_atendido) / 60, 1)         AS min_fila_churrasqueira,
    ROUND(TIMESTAMPDIFF(SECOND, e.chamado_garcom,
          (SELECT MIN(pm.data_hora_pedido) FROM pedidos_mesa pm
            WHERE pm.id_comanda = c.id_comanda_aleatoria
              AND pm.id_garcom IS NOT NULL
              AND pm.data_hora_pedido >= e.chamado_garcom)) / 60, 1)                AS min_espera_garcom,
    (SELECT pm.id_garcom FROM pedidos_mesa pm
      WHERE pm.id_comanda = c.id_comanda_aleatoria
        AND pm.id_garcom IS NOT NULL
        AND pm.data_hora_pedido >= e.chamado_garcom
      ORDER BY pm.data_hora_pedido LIMIT 1)                                         AS id_garcom_atendimento,
    ROUND(TIMESTAMPDIFF(SECOND, c.data_hora_gerado, c.data_hora_pago) / 60, 1)      AS min_ate_pagamento,
    ROUND(TIMESTAMPDIFF(SECOND, c.data_hora_gerado, e.saida) / 60, 1)               AS min_permanencia
FROM comanda c
LEFT JOIN (SELECT id_comanda, MIN(datahora_pesou) AS primeira_pesagem
           FROM pratos_kilo GROUP BY id_comanda) p
       ON p.id_comanda = c.id_comanda_aleatoria
LEFT JOIN (SELECT id_comanda,
                  MIN(CASE WHEN tipo_evento = 'chegada_churrasqueira'  THEN data_hora_evento END) AS churr_chegada,
                  MIN(CASE WHEN tipo_evento = 'atendido_churrasqueira' THEN data_hora_evento END) AS churr_atendido,
                  MIN(CASE WHEN tipo_evento = 'chamado_garcom'         THEN data_hora_evento END) AS chamado_garcom,
                  MIN(CASE WHEN tipo_evento = 'saida'                  THEN data_hora_evento END) AS saida
           FROM evento_comanda GROUP BY id_comanda) e
       ON e.id_comanda = c.id_comanda_aleatoria;

-- Mapa de calor de gargalos: dia da semana × hora
CREATE OR REPLACE VIEW vw_fluxo_por_hora AS
SELECT DAYOFWEEK(entrada)                        AS dia_semana,   -- 1 = domingo
       hora,
       COUNT(*)                                  AS clientes,
       ROUND(AVG(min_fila_buffet), 1)            AS fila_buffet_media,
       ROUND(AVG(min_fila_churrasqueira), 1)     AS fila_churrasqueira_media,
       ROUND(AVG(min_espera_garcom), 1)          AS espera_garcom_media,
       ROUND(AVG(min_permanencia), 1)            AS permanencia_media,
       CASE WHEN AVG(min_fila_buffet) > 10 OR AVG(min_fila_churrasqueira) > 6
            THEN 'critico' ELSE 'normal' END     AS situacao
FROM vw_tempos_comanda
GROUP BY DAYOFWEEK(entrada), hora;

-- Desempenho dos garçons
CREATE OR REPLACE VIEW vw_desempenho_garcom AS
SELECT g.id_garcom, g.nome,
       COALESCE(p.pedidos, 0)                              AS pedidos_registrados,
       COALESCE(p.faturamento_mesa, 0)                     AS faturamento_mesa,
       COUNT(t.id_comanda)                                 AS chamados_atendidos,
       ROUND(AVG(t.min_espera_garcom), 1)                  AS espera_media_min,
       ROUND(AVG(a.nota_atendimento), 1)                   AS nota_atendimento_media,
       ROUND(100 * SUM(a.nota_atendimento >= 4)
             / NULLIF(COUNT(a.id_avaliacao), 0), 1)        AS csat_atendimento
FROM garcom g
JOIN (SELECT id_garcom, COUNT(*) AS pedidos, SUM(quantidade * valor_unitario) AS faturamento_mesa
      FROM pedidos_mesa GROUP BY id_garcom) p ON p.id_garcom = g.id_garcom   -- só quem atende mesas
LEFT JOIN vw_tempos_comanda t ON t.id_garcom_atendimento = g.id_garcom
LEFT JOIN avaliacao a         ON a.id_comanda = t.id_comanda
WHERE g.ativo
GROUP BY g.id_garcom, p.pedidos, p.faturamento_mesa;

-- =====================================================================
-- [MESAS]
-- =====================================================================

-- Ciclos concluídos (minutos)
CREATE OR REPLACE VIEW vw_ciclo_mesa AS
SELECT o.id_ocupacao, o.id_mesa, m.numero_mesa, o.qtd_pessoas, o.id_garcom_limpeza,
       DATE(o.data_hora_ocupada)                                                           AS data,
       o.data_hora_ocupada, o.data_hora_desocupada, o.data_hora_inicio_limpeza, o.data_hora_fim_limpeza,
       ROUND(TIMESTAMPDIFF(SECOND, o.data_hora_ocupada,        o.data_hora_desocupada)     / 60, 1) AS min_permanencia,
       ROUND(TIMESTAMPDIFF(SECOND, o.data_hora_desocupada,     o.data_hora_inicio_limpeza) / 60, 1) AS min_espera_limpeza,
       ROUND(TIMESTAMPDIFF(SECOND, o.data_hora_inicio_limpeza, o.data_hora_fim_limpeza)    / 60, 1) AS min_limpeza,
       ROUND(TIMESTAMPDIFF(SECOND, o.data_hora_desocupada,     o.data_hora_fim_limpeza)    / 60, 1) AS min_liberacao
FROM ocupacao_mesa o
JOIN mesa m ON m.id_mesa = o.id_mesa
WHERE o.status_mesa = 'pronta';

-- KPIs diários das mesas
CREATE OR REPLACE VIEW vw_mesa_kpis_diario AS
SELECT data,
       COUNT(*)                                                         AS ciclos,
       ROUND(COUNT(*) / (SELECT COUNT(*) FROM mesa WHERE ativo), 2)     AS giro_por_mesa,
       ROUND(AVG(min_permanencia), 1)                                   AS permanencia_media,
       ROUND(AVG(min_espera_limpeza), 1)                                AS espera_limpeza_media,
       ROUND(AVG(min_limpeza), 1)                                       AS limpeza_media,
       ROUND(AVG(min_liberacao), 1)                                     AS liberacao_media,
       SUM(min_espera_limpeza > 5)                                      AS ciclos_mesa_parada_5min
FROM vw_ciclo_mesa
GROUP BY data;

-- Painel em tempo real: verde (livre/pronta), amarelo (desocupada/limpeza), vermelho (ocupada)
CREATE OR REPLACE VIEW vw_mesas_agora AS
WITH ultima AS (
    SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.id_mesa ORDER BY o.data_hora_ocupada DESC) AS rn
    FROM ocupacao_mesa o
)
SELECT m.id_mesa, m.numero_mesa, m.capacidade,
       CASE WHEN u.status_mesa IS NULL OR u.status_mesa = 'pronta' THEN 'livre'
            ELSE u.status_mesa END                                          AS status_atual,
       CASE WHEN u.status_mesa = 'ocupada'                    THEN 'vermelho'
            WHEN u.status_mesa IN ('desocupada', 'limpeza')   THEN 'amarelo'
            ELSE 'verde' END                                                AS cor,
       u.qtd_pessoas,
       CASE u.status_mesa
            WHEN 'ocupada'    THEN u.data_hora_ocupada
            WHEN 'desocupada' THEN u.data_hora_desocupada
            WHEN 'limpeza'    THEN u.data_hora_inicio_limpeza
            ELSE u.data_hora_fim_limpeza END                                AS desde,
       (u.status_mesa = 'desocupada'
        AND u.data_hora_desocupada < NOW() - INTERVAL 5 MINUTE)            AS alerta_limpeza
FROM mesa m
LEFT JOIN ultima u ON u.id_mesa = m.id_mesa AND u.rn = 1
WHERE m.ativo;

-- =====================================================================
-- [SATISFAÇÃO]  Cartão raspadinha, escala 0 (insatisfeito) a 5 (satisfeito)
--   CSAT da dimensão        = % de notas 4 ou 5
--   CSAT geral              = % de notas 4 ou 5 nas três dimensões
--   Índice de recomendação  = % "sim" − % "não"   (de −100 a +100)
--   Taxa de resposta        = cartões devolvidos / clientes do dia
-- =====================================================================
CREATE OR REPLACE VIEW vw_satisfacao_diaria AS
SELECT DATE(a.data_hora_avaliacao)                                                AS data,
       COUNT(*)                                                                   AS respostas,
       ROUND(100 * COUNT(*) / MAX(c.clientes), 1)                                 AS taxa_resposta_pct,
       ROUND(100 * (SUM(a.nota_comida >= 4) + SUM(a.nota_ambiente >= 4)
                    + SUM(a.nota_atendimento >= 4)) / (3 * COUNT(*)), 1)          AS csat_geral,
       ROUND(100 * SUM(a.nota_comida      >= 4) / COUNT(*), 1)                    AS csat_comida,
       ROUND(100 * SUM(a.nota_ambiente    >= 4) / COUNT(*), 1)                    AS csat_ambiente,
       ROUND(100 * SUM(a.nota_atendimento >= 4) / COUNT(*), 1)                    AS csat_atendimento,
       ROUND(AVG(a.nota_comida), 2)                                               AS media_comida,
       ROUND(AVG(a.nota_ambiente), 2)                                             AS media_ambiente,
       ROUND(AVG(a.nota_atendimento), 2)                                          AS media_atendimento,
       ROUND(100 * (SUM(a.recomendaria = 'sim') - SUM(a.recomendaria = 'nao')) / COUNT(*), 1)
                                                                                  AS indice_recomendacao,
       SUM(a.sentimento = 'negativo')                                             AS comentarios_negativos,
       ROUND(100 * SUM(a.origem_registro = 'leitura_otica') / COUNT(*), 1)        AS pct_leitura_otica
FROM avaliacao a
LEFT JOIN (SELECT DATE(data_hora_gerado) AS dia, COUNT(*) AS clientes
           FROM comanda GROUP BY DATE(data_hora_gerado)) c
       ON c.dia = DATE(a.data_hora_avaliacao)
GROUP BY DATE(a.data_hora_avaliacao);

-- Relação entre tempo de fila e satisfação
CREATE OR REPLACE VIEW vw_satisfacao_por_fila AS
SELECT CASE WHEN t.min_fila_buffet < 5  THEN '1. até 5 min'
            WHEN t.min_fila_buffet < 10 THEN '2. 5 a 10 min'
            WHEN t.min_fila_buffet < 15 THEN '3. 10 a 15 min'
            ELSE '4. 15 min ou mais' END                                          AS faixa_fila,
       COUNT(*)                                                                   AS respostas,
       ROUND(100 * (SUM(a.nota_comida >= 4) + SUM(a.nota_ambiente >= 4)
                    + SUM(a.nota_atendimento >= 4)) / (3 * COUNT(*)), 1)          AS csat_geral,
       ROUND(100 * SUM(a.nota_ambiente >= 4) / COUNT(*), 1)                       AS csat_ambiente,
       ROUND(100 * (SUM(a.recomendaria = 'sim') - SUM(a.recomendaria = 'nao')) / COUNT(*), 1)
                                                                                  AS indice_recomendacao
FROM avaliacao a
JOIN vw_tempos_comanda t ON t.id_comanda = a.id_comanda
GROUP BY faixa_fila
ORDER BY faixa_fila;

-- Cupons de brinde: custo do incentivo e taxa de retorno dos clientes
CREATE OR REPLACE VIEW vw_cupons_diario AS
SELECT DATE(data_hora_emissao)                                                    AS data_emissao,
       COUNT(*)                                                                   AS emitidos,
       SUM(id_comanda_resgate IS NOT NULL)                                        AS resgatados,
       SUM(id_comanda_resgate IS NULL AND data_validade <  CURDATE())             AS vencidos,
       SUM(id_comanda_resgate IS NULL AND data_validade >= CURDATE())             AS ativos,
       ROUND(100 * SUM(id_comanda_resgate IS NOT NULL) / COUNT(*), 1)             AS taxa_retorno_pct,
       COALESCE(SUM(CASE WHEN id_comanda_resgate IS NOT NULL THEN custo_brinde END), 0)
                                                                                  AS custo_brindes,
       ROUND(AVG(DATEDIFF(data_hora_resgate, data_hora_emissao)), 1)              AS dias_ate_retorno
FROM cupom_brinde
GROUP BY DATE(data_hora_emissao);

-- =====================================================================
-- [SOBRAS]  Food Waste Index = (sobra no prato + descarte da cuba) / produzido
-- =====================================================================
CREATE OR REPLACE VIEW vw_desperdicio_ingrediente AS
WITH prod AS (
    SELECT id_ingrediente, SUM(peso_produzido_gramas) AS produzido, SUM(peso_descartado_gramas) AS descarte_cuba
    FROM producao_cuba GROUP BY id_ingrediente
), prato AS (
    SELECT id_ingrediente, SUM(peso_gramas) AS sobra_prato
    FROM composicao_sobra GROUP BY id_ingrediente
)
SELECT i.nome_ingrediente, i.categoria,
       ROUND(pr.produzido / 1000, 1)                                                      AS produzido_kg,
       ROUND(COALESCE(s.sobra_prato, 0) / 1000, 2)                                        AS sobra_prato_kg,
       ROUND(pr.descarte_cuba / 1000, 2)                                                  AS descarte_cuba_kg,
       ROUND(100 * (COALESCE(s.sobra_prato, 0) + pr.descarte_cuba) / NULLIF(pr.produzido, 0), 1) AS food_waste_index_pct,
       ROUND((COALESCE(s.sobra_prato, 0) + pr.descarte_cuba) / 1000 * i.custo_kg, 2)      AS custo_desperdicio
FROM prod pr
JOIN ingrediente i ON i.id_ingrediente = pr.id_ingrediente
LEFT JOIN prato s  ON s.id_ingrediente = pr.id_ingrediente
ORDER BY food_waste_index_pct DESC;

-- =====================================================================
-- Resumo executivo diário
-- =====================================================================
CREATE OR REPLACE VIEW vw_resumo_diario AS
SELECT c.data,
       COUNT(*)                                                  AS clientes,
       SUM(c.receita_buffet)                                     AS receita_buffet,
       SUM(c.receita_mesa)                                       AS receita_mesa,
       SUM(c.crc)                                                AS custo_buffet,
       ROUND(100 * SUM(c.margem_buffet) / SUM(c.receita_buffet), 1) AS margem_buffet_pct,
       ROUND(AVG(c.crc), 2)                                      AS crc_medio,
       (SELECT ROUND(AVG(t.min_fila_buffet), 1) FROM vw_tempos_comanda t WHERE t.data = c.data) AS fila_buffet_media,
       m.liberacao_media                                         AS liberacao_mesa_media,
       m.giro_por_mesa,
       n.taxa_resposta_pct,
       n.csat_geral
FROM vw_custo_comanda c
LEFT JOIN vw_mesa_kpis_diario m  ON m.data = c.data
LEFT JOIN vw_satisfacao_diaria n ON n.data = c.data
GROUP BY c.data, m.liberacao_media, m.giro_por_mesa, n.taxa_resposta_pct, n.csat_geral
ORDER BY c.data;
