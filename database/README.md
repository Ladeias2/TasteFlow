# Banco de dados — TasteFlow

MySQL 8.0.16 ou superior. A explicação completa do modelo está nas Seções 7 a 9 e no Apêndice A da [documentação](../docs/DOCUMENTACAO.md).

| Arquivo | Conteúdo |
|---|---|
| `01_schema_base.sql` | Tabelas originais, sem alteração: `garcom`, `comanda`, `pratos_kilo`, `pedidos_mesa` |
| `02_schema_extensao.sql` | 13 tabelas novas: mesas, eventos, ingredientes, composição, cartões, avaliação, cupons, sobras e cubas |
| `03_procedures_triggers.sql` | `trg_ocupacao_unica`, `sp_fechar_comanda`, `sp_ocupar_mesa`, `sp_avancar_status_mesa`, `sp_resgatar_cupom` |
| `04_views_kpis.sql` | 14 views de indicadores (CRC, filas, ciclo da mesa, CSAT, retorno, FWI) |
| `05_seed.sql` | 14 dias de dados simulados (apaga e recria os dados) |

## Execução

```bash
mysql -u root -p -e "CREATE DATABASE restaurante CHARACTER SET utf8mb4;"
mysql -u root -p restaurante < 01_schema_base.sql
mysql -u root -p restaurante < 02_schema_extensao.sql
mysql -u root -p restaurante < 03_procedures_triggers.sql
mysql -u root -p restaurante < 04_views_kpis.sql
mysql -u root -p restaurante < 05_seed.sql
```

O arquivo 03 usa `DELIMITER` e precisa ser executado pelo cliente `mysql` ou pelo MySQL Workbench (opção *Execute script*).

## Consultas para as capturas de tela

```sql
SELECT * FROM vw_resumo_diario;                          -- cartões do dashboard
SELECT * FROM vw_rentabilidade_ingrediente;              -- % do peso × % do custo
SELECT * FROM vw_fluxo_por_hora ORDER BY dia_semana, hora; -- mapa de calor das filas
SELECT * FROM vw_mesas_agora;                            -- painel verde/amarelo/vermelho
SELECT * FROM vw_satisfacao_por_fila;                    -- fila × satisfação
SELECT * FROM vw_cupons_diario;                          -- brindes e taxa de retorno
SELECT * FROM vw_desperdicio_ingrediente;                -- Food Waste Index
```
