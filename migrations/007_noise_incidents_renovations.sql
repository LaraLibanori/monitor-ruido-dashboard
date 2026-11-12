-- Ocorrências contínuas, autorizações de reforma e candidatos a multa.

CREATE TABLE IF NOT EXISTS renovation_requests (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sensor_id   TEXT NOT NULL REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    starts_at   TIMESTAMPTZ NOT NULL,
    ends_at     TIMESTAMPTZ NOT NULL,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS idx_renovation_sensor_time
    ON renovation_requests (sensor_id, starts_at, ends_at);

CREATE TABLE IF NOT EXISTS noise_incidents (
    id                 SERIAL PRIMARY KEY,
    sensor_id          TEXT NOT NULL REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    started_at         TIMESTAMPTZ NOT NULL,
    last_high_at       TIMESTAMPTZ NOT NULL,
    ended_at           TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'warning', 'fine_candidate', 'exempt')),
    warning_event_id   INTEGER REFERENCES alert_events(id) ON DELETE SET NULL,
    fine_event_id      INTEGER REFERENCES alert_events(id) ON DELETE SET NULL,
    renovation_request_id INTEGER REFERENCES renovation_requests(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_noise_incidents_sensor_time
    ON noise_incidents (sensor_id, started_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_noise_incident
    ON noise_incidents (sensor_id) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS fines (
    id           SERIAL PRIMARY KEY,
    incident_id  INTEGER NOT NULL REFERENCES noise_incidents(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount       NUMERIC(12, 2),
    due_date     DATE,
    status       TEXT NOT NULL DEFAULT 'proposed'
                 CHECK (status IN ('proposed', 'approved', 'cancelled', 'paid')),
    approved_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approved_at  TIMESTAMPTZ,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fines_incident_user ON fines (incident_id, user_id);

ALTER TABLE alert_events
    ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'warning';
ALTER TABLE notification_deliveries
    DROP CONSTRAINT IF EXISTS notification_deliveries_kind_check;
ALTER TABLE notification_deliveries
    ADD CONSTRAINT notification_deliveries_kind_check
    CHECK (kind IN ('alert', 'warning', 'fine_candidate', 'invite', 'test'));
