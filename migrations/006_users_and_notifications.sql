-- =============================================
-- 006_users_and_notifications.sql
-- Usuários (administrador e morador), sessões, convites,
-- vínculo morador <-> sensor, preferências de notificação,
-- dispositivos para push, eventos de alerta, entregas,
-- auditoria e configurações editáveis pelo administrador.
--
-- Aplicada automaticamente quando a API inicia.
-- Reverter: migrations/rollback/006_users_and_notifications.down.sql
-- =============================================

CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    name                TEXT        NOT NULL CHECK (length(trim(name)) > 0),
    email               TEXT        NOT NULL,
    phone               TEXT,
    role                TEXT        NOT NULL CHECK (role IN ('admin', 'morador')),
    password_hash       TEXT,                      -- NULL = convite ainda não aceito
    active              BOOLEAN     NOT NULL DEFAULT TRUE,
    contact_verified_at TIMESTAMPTZ,               -- preenchido ao aceitar o convite
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- E-mail único sem diferenciar maiúsculas/minúsculas
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (lower(email));

-- Sessões: guardamos só o hash do token, nunca o token em si
CREATE TABLE IF NOT EXISTS user_sessions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions (user_id);

-- Convites com expiração (também só o hash do token)
CREATE TABLE IF NOT EXISTS user_invites (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT        NOT NULL UNIQUE,
    channel      TEXT        NOT NULL CHECK (channel IN ('email', 'phone')),
    created_by   INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    accepted_at  TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_invites_user ON user_invites (user_id);

-- Quais casas/sensores cada usuário pode ver e de quais recebe alerta
CREATE TABLE IF NOT EXISTS user_sensors (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sensor_id  TEXT    NOT NULL REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, sensor_id)
);
CREATE INDEX IF NOT EXISTS idx_user_sensors_sensor ON user_sensors (sensor_id);

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    push_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tokens FCM dos aparelhos (um usuário pode ter vários aparelhos)
CREATE TABLE IF NOT EXISTS device_tokens (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token        TEXT        NOT NULL UNIQUE,
    platform     TEXT        NOT NULL CHECK (platform IN ('android', 'ios', 'web')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens (user_id);

-- Um evento por "barulho alto no horário de silêncio".
-- reading_id único impede alerta duplicado para a mesma leitura;
-- o intervalo mínimo entre eventos do mesmo sensor é aplicado pelo backend.
CREATE TABLE IF NOT EXISTS alert_events (
    id          SERIAL PRIMARY KEY,
    sensor_id   TEXT        NOT NULL REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    reading_id  INTEGER     NOT NULL UNIQUE REFERENCES noise_readings(id) ON DELETE CASCADE,
    noise_level TEXT        NOT NULL,
    rms         REAL        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alert_events_sensor_time ON alert_events (sensor_id, created_at DESC);

-- Resultado de cada tentativa de envio (inclusive falhas e simulações)
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id             SERIAL PRIMARY KEY,
    alert_event_id INTEGER     REFERENCES alert_events(id) ON DELETE CASCADE,  -- NULL = teste/convite
    user_id        INTEGER     REFERENCES users(id) ON DELETE CASCADE,
    kind           TEXT        NOT NULL CHECK (kind IN ('alert', 'invite', 'test')),
    channel        TEXT        NOT NULL CHECK (channel IN ('email', 'push')),
    status         TEXT        NOT NULL CHECK (status IN ('sent', 'simulated', 'failed', 'skipped')),
    provider       TEXT        NOT NULL,
    detail         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deliveries_event ON notification_deliveries (alert_event_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_time  ON notification_deliveries (created_at DESC);

-- Auditoria das ações administrativas e de acesso
CREATE TABLE IF NOT EXISTS audit_log (
    id            SERIAL PRIMARY KEY,
    actor_user_id INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    action        TEXT        NOT NULL,
    target        TEXT,
    details       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log (created_at DESC);

-- Configurações editáveis no painel (ex.: horário de silêncio)
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      JSONB       NOT NULL,
    updated_by INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
