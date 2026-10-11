-- Remove duplicatas antigas, preservando a primeira leitura de cada sequência.
DELETE FROM noise_readings old
USING noise_readings newer
WHERE old.sensor_id = newer.sensor_id
  AND old.sequence = newer.sequence
  AND old.id > newer.id;

-- Impede que retries do ESP32 gravem a mesma sequência mais de uma vez.
CREATE UNIQUE INDEX IF NOT EXISTS uq_readings_sensor_sequence
    ON noise_readings(sensor_id, sequence);
