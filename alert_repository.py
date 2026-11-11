# =============================================
# alert_repository.py - SQL dos alertas e entregas
# =============================================

from datetime import datetime

from database import Database


class AlertRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_reading(self, reading_id: int) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT r.id, r.sensor_id, r.rms, r.noise_level, r.is_silence_period, r.received_at,
                       s.location, s.active,
                       COALESCE(NULLIF(s.display_name, ''), s.location, s.sensor_id) AS house_name
                FROM noise_readings r
                JOIN sensors s USING (sensor_id)
                WHERE r.id = %s
                """,
                (reading_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_event_if_due(self, reading: dict, cooldown_minutes: float) -> int | None:
        """
        Cria o evento de alerta, a não ser que:
          - esta leitura já tenha gerado alerta (reenvio do ESP32 / processamento repetido), ou
          - o mesmo sensor tenha gerado alerta há menos de `cooldown_minutes`.
        O lock por sensor evita duas leituras simultâneas criarem dois alertas.
        """
        with self.db.transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('alert:' || %s))", (reading["sensor_id"],))
            cur.execute(
                """
                SELECT 1 FROM alert_events
                WHERE reading_id = %s
                   OR (sensor_id = %s
                       AND created_at > %s - make_interval(secs => %s))
                LIMIT 1
                """,
                (reading["id"], reading["sensor_id"], reading["received_at"], cooldown_minutes * 60),
            )
            if cur.fetchone():
                return None
            cur.execute(
                """
                INSERT INTO alert_events (sensor_id, reading_id, noise_level, rms, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (reading["sensor_id"], reading["id"], reading["noise_level"],
                 reading["rms"], reading["received_at"]),
            )
            return cur.fetchone()["id"]

    def add_delivery(self, *, alert_event_id: int | None, user_id: int | None, kind: str,
                     channel: str, status: str, provider: str, detail: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO notification_deliveries
                    (alert_event_id, user_id, kind, channel, status, provider, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (alert_event_id, user_id, kind, channel, status, provider, (detail or "")[:1000]),
            )

    def list_events(self, limit: int = 50, sensor_ids: set[str] | None = None) -> list[dict]:
        sql = """
            SELECT e.id, e.sensor_id, e.noise_level, e.rms, e.created_at,
                   COALESCE(NULLIF(s.display_name, ''), s.location, s.sensor_id) AS house_name,
                   COALESCE(
                       (SELECT json_agg(json_build_object(
                            'user_id', d.user_id, 'user_name', u.name, 'channel', d.channel,
                            'status', d.status, 'provider', d.provider, 'detail', d.detail,
                            'created_at', d.created_at) ORDER BY d.id)
                        FROM notification_deliveries d
                        LEFT JOIN users u ON u.id = d.user_id
                        WHERE d.alert_event_id = e.id),
                       '[]'::json
                   ) AS deliveries
            FROM alert_events e
            JOIN sensors s USING (sensor_id)
        """
        params: list = []
        if sensor_ids is not None:
            sql += " WHERE e.sensor_id = ANY(%s)"
            params.append(sorted(sensor_ids))
        sql += " ORDER BY e.id DESC LIMIT %s"
        params.append(limit)
        with self.db.transaction() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def list_deliveries(self, limit: int = 100) -> list[dict]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT d.id, d.alert_event_id, d.kind, d.channel, d.status, d.provider, d.detail,
                       d.created_at, d.user_id, u.name AS user_name
                FROM notification_deliveries d
                LEFT JOIN users u ON u.id = d.user_id
                ORDER BY d.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    def latest_event_at(self, sensor_id: str) -> datetime | None:
        with self.db.transaction() as cur:
            cur.execute("SELECT MAX(created_at) AS at FROM alert_events WHERE sensor_id = %s", (sensor_id,))
            return cur.fetchone()["at"]
