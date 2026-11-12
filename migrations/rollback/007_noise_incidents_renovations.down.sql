ALTER TABLE notification_deliveries DROP CONSTRAINT IF EXISTS notification_deliveries_kind_check;
ALTER TABLE notification_deliveries
    ADD CONSTRAINT notification_deliveries_kind_check
    CHECK (kind IN ('alert', 'invite', 'test'));
ALTER TABLE alert_events DROP COLUMN IF EXISTS stage;
DROP TABLE IF EXISTS fines;
DROP TABLE IF EXISTS noise_incidents;
DROP TABLE IF EXISTS renovation_requests;
