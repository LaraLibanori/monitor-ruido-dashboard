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

    def advance_incident(self, reading: dict, *, continuity_gap_seconds: int,
                         warning_seconds: int, fine_seconds: int) -> dict:
        """Atualiza a ocorrência contínua e retorna transições que precisam notificar."""
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext('incident:' || %s))",
                (reading["sensor_id"],),
            )
            cur.execute(
                """
                SELECT id, started_at, last_high_at, status, renovation_request_id
                FROM noise_incidents
                WHERE sensor_id = %s AND ended_at IS NULL
                FOR UPDATE
                """,
                (reading["sensor_id"],),
            )
            incident = cur.fetchone()
            at = reading["received_at"]
            if incident is None or (at - incident["last_high_at"]).total_seconds() > continuity_gap_seconds:
                if incident is not None:
                    cur.execute(
                        "UPDATE noise_incidents SET ended_at = %s WHERE id = %s",
                        (incident["last_high_at"], incident["id"]),
                    )
                cur.execute(
                    """
                    INSERT INTO noise_incidents (sensor_id, started_at, last_high_at)
                    VALUES (%s, %s, %s)
                    RETURNING id, started_at, last_high_at, status, renovation_request_id
                    """,
                    (reading["sensor_id"], at, at),
                )
                incident = cur.fetchone()
            else:
                cur.execute(
                    "UPDATE noise_incidents SET last_high_at = %s WHERE id = %s",
                    (at, incident["id"]),
                )
                incident = {**incident, "last_high_at": at}

            elapsed = (incident["last_high_at"] - incident["started_at"]).total_seconds()
            transition = None
            if incident["status"] == "active" and elapsed >= warning_seconds:
                transition = "warning"
                cur.execute(
                    "UPDATE noise_incidents SET status = 'warning' WHERE id = %s",
                    (incident["id"],),
                )
            elif incident["status"] == "warning" and elapsed >= fine_seconds:
                transition = "fine_candidate"
                cur.execute(
                    "UPDATE noise_incidents SET status = 'fine_candidate' WHERE id = %s",
                    (incident["id"],),
                )

            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM renovation_requests
                    WHERE sensor_id = %s AND status = 'approved'
                      AND starts_at <= %s AND ends_at >= %s
                ) AS approved
                """,
                (reading["sensor_id"], at, at),
            )
            exempt = cur.fetchone()["approved"]
            if exempt and incident["status"] != "exempt":
                cur.execute(
                    "UPDATE noise_incidents SET status = 'exempt' WHERE id = %s",
                    (incident["id"],),
                )
                transition = None
            elif not exempt and incident["status"] == "exempt":
                cur.execute(
                    """
                    UPDATE noise_incidents
                    SET status = 'active', started_at = %s, last_high_at = %s
                    WHERE id = %s
                    """,
                    (at, at, incident["id"]),
                )
                transition = None
            return {
                "incident_id": incident["id"],
                "transition": transition,
                "elapsed_seconds": elapsed,
                "exempt": exempt,
            }

    def create_incident_event(self, reading: dict, incident_id: int, stage: str) -> int:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO alert_events (sensor_id, reading_id, noise_level, rms, created_at, stage)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (reading["sensor_id"], reading["id"], reading["noise_level"],
                 reading["rms"], reading["received_at"], stage),
            )
            event_id = cur.fetchone()["id"]
            column = "warning_event_id" if stage == "warning" else "fine_event_id"
            cur.execute(
                f"UPDATE noise_incidents SET {column} = %s WHERE id = %s",
                (event_id, incident_id),
            )
            return event_id

    def list_user_deliveries(self, user_id: int, limit: int = 100) -> list[dict]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT d.id, d.alert_event_id, d.kind, d.channel, d.status, d.provider,
                       d.detail, d.created_at, d.user_id,
                       e.sensor_id, e.stage, e.noise_level, e.rms
                FROM notification_deliveries d
                LEFT JOIN alert_events e ON e.id = d.alert_event_id
                WHERE d.user_id = %s
                ORDER BY d.id DESC
                LIMIT %s
                """,
                (user_id, min(max(limit, 1), 200)),
            )
            return [dict(row) for row in cur.fetchall()]

    def create_renovation_request(self, user_id: int, sensor_id: str, starts_at,
                                  ends_at, description: str) -> dict:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO renovation_requests
                    (user_id, sensor_id, starts_at, ends_at, description)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, user_id, sensor_id, starts_at, ends_at, description,
                          status, created_at
                """,
                (user_id, sensor_id, starts_at, ends_at, description),
            )
            return dict(cur.fetchone())

    def list_renovation_requests(self, *, user_id: int | None = None) -> list[dict]:
        with self.db.transaction() as cur:
            params = []
            sql = """
                SELECT r.id, r.user_id, u.name AS user_name, r.sensor_id,
                       r.starts_at, r.ends_at, r.description, r.status,
                       r.reviewed_by, r.reviewed_at, r.created_at
                FROM renovation_requests r
                JOIN users u ON u.id = r.user_id
            """
            if user_id is not None:
                sql += " WHERE r.user_id = %s"
                params.append(user_id)
            sql += " ORDER BY r.created_at DESC LIMIT 200"
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def review_renovation_request(self, request_id: int, reviewer_id: int, status: str) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE renovation_requests
                SET status = %s, reviewed_by = %s, reviewed_at = NOW()
                WHERE id = %s
                RETURNING id, user_id, sensor_id, starts_at, ends_at, description,
                          status, reviewed_by, reviewed_at, created_at
                """,
                (status, reviewer_id, request_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_fine_candidate(self, incident_id: int, user_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO fines (incident_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (incident_id, user_id) DO NOTHING
                """,
                (incident_id, user_id),
            )

    def list_fines(self) -> list[dict]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT f.id, f.incident_id, f.user_id, u.name AS user_name,
                       f.amount, f.due_date, f.status, f.notes, f.created_at,
                       i.sensor_id, i.started_at, i.last_high_at
                FROM fines f
                JOIN users u ON u.id = f.user_id
                JOIN noise_incidents i ON i.id = f.incident_id
                ORDER BY f.id DESC
                LIMIT 200
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def review_fine(self, fine_id: int, reviewer_id: int, status: str,
                    amount=None, due_date=None, notes: str | None = None) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE fines
                SET status = %s, amount = COALESCE(%s, amount),
                    due_date = COALESCE(%s, due_date),
                    notes = COALESCE(%s, notes),
                    approved_by = CASE WHEN %s = 'approved' THEN %s ELSE approved_by END,
                    approved_at = CASE WHEN %s = 'approved' THEN NOW() ELSE approved_at END
                WHERE id = %s
                RETURNING id, incident_id, user_id, amount, due_date, status,
                          approved_by, approved_at, notes, created_at
                """,
                (status, amount, due_date, notes, status, reviewer_id, status, fine_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

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
            SELECT e.id, e.sensor_id, e.noise_level, e.rms, e.stage, e.created_at,
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
