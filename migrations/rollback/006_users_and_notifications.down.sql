-- =============================================
-- Reverte 006_users_and_notifications.sql
-- NÃO é aplicado automaticamente. Para reverter:
--   docker compose exec -T db psql -U noiseuser -d noisedb \
--     < migrations/rollback/006_users_and_notifications.down.sql
-- Apaga usuários, convites, alertas e auditoria. As leituras e os
-- sensores continuam intactos.
-- =============================================

BEGIN;

DROP TABLE IF EXISTS app_settings;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS notification_deliveries;
DROP TABLE IF EXISTS alert_events;
DROP TABLE IF EXISTS device_tokens;
DROP TABLE IF EXISTS notification_preferences;
DROP TABLE IF EXISTS user_sensors;
DROP TABLE IF EXISTS user_invites;
DROP TABLE IF EXISTS user_sessions;
DROP TABLE IF EXISTS users;

DELETE FROM schema_migrations WHERE name = '006_users_and_notifications.sql';

COMMIT;
