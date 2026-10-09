-- =============================================
-- 002_app_mobile.sql
-- Suporte ao aplicativo Android.
-- Aplicada automaticamente quando a API inicia.
-- =============================================

-- Nome amigável de cada sensor no app (ex.: "Casa 1", "Casa da Sueli").
-- Se ficar vazio, o app mostra "Casa 1", "Casa 2"... pela ordem dos sensores.
-- Para renomear:  UPDATE sensors SET display_name = 'Casa 1' WHERE sensor_id = 'sensor_ap1';
ALTER TABLE sensors ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Acelera "última leitura de cada sensor" e o histórico por sensor
CREATE INDEX IF NOT EXISTS idx_readings_sensor_time
    ON noise_readings (sensor_id, received_at DESC);
