-- pointed_road_data の期間検索を高速化するインデックス。
-- DB は他システムと共有しているため、適用は DB 管理者と調整のうえで行うこと。
-- 適用:   sqlite3 database.db < scripts/create_indexes.sql
-- 取り消し: DROP INDEX IF EXISTS idx_pointed_road_data_get_at;
CREATE INDEX IF NOT EXISTS idx_pointed_road_data_get_at ON pointed_road_data(get_at);
