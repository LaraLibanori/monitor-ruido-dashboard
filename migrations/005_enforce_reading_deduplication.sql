-- Reaplica a deduplicação para bancos que foram criados antes da migration 004.
DELETE FROM noise_readings old
USING noise_readings newer
WHERE old.sensor_id = newer.sensor_id
  AND old.sequence = newer.sequence
  AND old.id > newer.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_readings_sensor_sequence
    ON noise_readings(sensor_id, sequence);
