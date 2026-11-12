# =============================================
# user_repository.py - SQL de usuários, sessões, convites,
# preferências, aparelhos, sensores (admin), auditoria e configurações
# =============================================
# Só SQL aqui. Regras de negócio ficam em auth_service.py.
# =============================================

from datetime import datetime
import json

import psycopg2
import psycopg2.errors

from database import Database


class DuplicateEmail(Exception):
    pass


class DuplicateSensor(Exception):
    pass


class UnknownSensor(Exception):
    def __init__(self, sensor_ids):
        super().__init__(", ".join(sorted(sensor_ids)))
        self.sensor_ids = sorted(sensor_ids)


_USER_COLUMNS = """
    u.id, u.name, u.email, u.phone, u.role, u.active,
    (u.password_hash IS NOT NULL) AS has_password,
    u.contact_verified_at, u.created_at, u.updated_at
"""

_USER_DETAIL_SQL = f"""
    SELECT
        {_USER_COLUMNS},
        COALESCE(
            (SELECT array_agg(us.sensor_id ORDER BY us.sensor_id)
             FROM user_sensors us WHERE us.user_id = u.id),
            ARRAY[]::TEXT[]
        ) AS sensor_ids,
        COALESCE(p.email_enabled, TRUE) AS email_enabled,
        COALESCE(p.push_enabled, TRUE)  AS push_enabled,
        (SELECT COUNT(*) FROM device_tokens d WHERE d.user_id = u.id)::INT AS devices,
        (SELECT MAX(i.expires_at) FROM user_invites i
          WHERE i.user_id = u.id AND i.accepted_at IS NULL AND i.revoked_at IS NULL
        ) AS invite_expires_at
    FROM users u
    LEFT JOIN notification_preferences p ON p.user_id = u.id
"""


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---------------- usuários ----------------

    def count_users(self) -> int:
        with self.db.transaction() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users")
            return cur.fetchone()["n"]

    def create_user(self, *, name: str, email: str, phone: str | None, role: str,
                    password_hash: str | None = None, verified: bool = False) -> int:
        try:
            with self.db.transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO users (name, email, phone, role, password_hash, contact_verified_at)
                    VALUES (%s, %s, %s, %s, %s, CASE WHEN %s THEN NOW() END)
                    RETURNING id
                    """,
                    (name, email, phone, role, password_hash, verified),
                )
                user_id = cur.fetchone()["id"]
                cur.execute(
                    "INSERT INTO notification_preferences (user_id) VALUES (%s)", (user_id,)
                )
                return user_id
        except psycopg2.errors.UniqueViolation as exc:
            raise DuplicateEmail(email) from exc

    def get_user(self, user_id: int) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute(_USER_DETAIL_SQL + " WHERE u.id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_login_row(self, email: str) -> dict | None:
        """Linha com o hash da senha (uso exclusivo do login)."""
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT id, password_hash, active, role FROM users WHERE lower(email) = lower(%s)",
                (email,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_password_hash(self, user_id: int) -> str | None:
        with self.db.transaction() as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return row["password_hash"] if row else None

    def list_users(self, role: str | None = None) -> list[dict]:
        sql = _USER_DETAIL_SQL
        params: tuple = ()
        if role:
            sql += " WHERE u.role = %s"
            params = (role,)
        sql += " ORDER BY u.active DESC, lower(u.name)"
        with self.db.transaction() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def update_user(self, user_id: int, fields: dict) -> None:
        allowed = {"name", "email", "phone", "role", "active"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        assignments = ", ".join(f"{column} = %s" for column in fields)
        try:
            with self.db.transaction() as cur:
                cur.execute(
                    f"UPDATE users SET {assignments}, updated_at = NOW() WHERE id = %s",
                    (*fields.values(), user_id),
                )
        except psycopg2.errors.UniqueViolation as exc:
            raise DuplicateEmail(fields.get("email")) from exc

    def set_password(self, user_id: int, password_hash: str, *, verify_contact: bool) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s,
                    contact_verified_at = CASE WHEN %s THEN COALESCE(contact_verified_at, NOW())
                                               ELSE contact_verified_at END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (password_hash, verify_contact, user_id),
            )

    def missing_sensors(self, sensor_ids: list[str]) -> list[str]:
        wanted = sorted(set(sensor_ids))
        if not wanted:
            return []
        with self.db.transaction() as cur:
            cur.execute("SELECT sensor_id FROM sensors WHERE sensor_id = ANY(%s)", (wanted,))
            found = {r["sensor_id"] for r in cur.fetchall()}
        return [s for s in wanted if s not in found]

    def set_user_sensors(self, user_id: int, sensor_ids: list[str]) -> None:
        wanted = sorted(set(sensor_ids))
        with self.db.transaction() as cur:
            if wanted:
                cur.execute(
                    "SELECT sensor_id FROM sensors WHERE sensor_id = ANY(%s)", (wanted,)
                )
                found = {r["sensor_id"] for r in cur.fetchall()}
                missing = set(wanted) - found
                if missing:
                    raise UnknownSensor(missing)
            cur.execute("DELETE FROM user_sensors WHERE user_id = %s", (user_id,))
            for sensor_id in wanted:
                cur.execute(
                    "INSERT INTO user_sensors (user_id, sensor_id) VALUES (%s, %s)",
                    (user_id, sensor_id),
                )

    # ---------------- sessões ----------------

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, token_hash, expires_at),
            )
            # Limpeza oportunista de sessões vencidas do mesmo usuário
            cur.execute(
                "DELETE FROM user_sessions WHERE user_id = %s AND expires_at < NOW() - INTERVAL '7 days'",
                (user_id,),
            )

    def get_session(self, token_hash: str) -> dict | None:
        """Sessão válida (não expirada, não revogada) de usuário ativo."""
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT s.user_id, s.expires_at
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > NOW()
                  AND u.active
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def revoke_session(self, token_hash: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE user_sessions SET revoked_at = NOW() WHERE token_hash = %s AND revoked_at IS NULL",
                (token_hash,),
            )

    def revoke_user_sessions(self, user_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL",
                (user_id,),
            )

    # ---------------- convites ----------------

    def create_invite(self, *, user_id: int, token_hash: str, channel: str,
                      created_by: int | None, expires_at: datetime) -> None:
        with self.db.transaction() as cur:
            # Só o convite mais recente vale
            cur.execute(
                """
                UPDATE user_invites SET revoked_at = NOW()
                WHERE user_id = %s AND accepted_at IS NULL AND revoked_at IS NULL
                """,
                (user_id,),
            )
            cur.execute(
                """
                INSERT INTO user_invites (user_id, token_hash, channel, created_by, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, token_hash, channel, created_by, expires_at),
            )

    def get_invite(self, token_hash: str) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT i.id, i.user_id, i.channel, i.expires_at, i.accepted_at, i.revoked_at,
                       (i.expires_at <= NOW()) AS expired,
                       u.name, u.email, u.phone, u.role, u.active
                FROM user_invites i
                JOIN users u ON u.id = i.user_id
                WHERE i.token_hash = %s
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def accept_invite(self, invite_id: int, user_id: int, password_hash: str) -> bool:
        """Marca o convite como aceito e define a senha. False se outro pedido aceitou antes."""
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE user_invites SET accepted_at = NOW()
                WHERE id = %s AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > NOW()
                RETURNING id
                """,
                (invite_id,),
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s,
                    contact_verified_at = COALESCE(contact_verified_at, NOW()),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (password_hash, user_id),
            )
            return True

    # ---------------- preferências e aparelhos ----------------

    def set_preferences(self, user_id: int, *, email_enabled: bool | None = None,
                        push_enabled: bool | None = None) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO notification_preferences (user_id, email_enabled, push_enabled)
                VALUES (%s, COALESCE(%s, TRUE), COALESCE(%s, TRUE))
                ON CONFLICT (user_id) DO UPDATE SET
                    email_enabled = COALESCE(%s, notification_preferences.email_enabled),
                    push_enabled  = COALESCE(%s, notification_preferences.push_enabled),
                    updated_at    = NOW()
                """,
                (user_id, email_enabled, push_enabled, email_enabled, push_enabled),
            )

    def upsert_device(self, user_id: int, token: str, platform: str) -> None:
        with self.db.transaction() as cur:
            # O mesmo aparelho pode trocar de usuário (logout/login): o token passa para o novo dono
            cur.execute(
                """
                INSERT INTO device_tokens (user_id, token, platform)
                VALUES (%s, %s, %s)
                ON CONFLICT (token) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    platform = EXCLUDED.platform,
                    last_seen_at = NOW()
                """,
                (user_id, token, platform),
            )

    def delete_device(self, user_id: int, token: str) -> bool:
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM device_tokens WHERE user_id = %s AND token = %s", (user_id, token)
            )
            return cur.rowcount > 0

    def delete_device_token(self, token: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM device_tokens WHERE token = %s", (token,))

    def list_device_tokens(self, user_id: int) -> list[str]:
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT token FROM device_tokens WHERE user_id = %s ORDER BY last_seen_at DESC",
                (user_id,),
            )
            return [r["token"] for r in cur.fetchall()]

    # ---------------- sensores (administração) ----------------

    def list_sensors(self) -> list[dict]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT
                    s.sensor_id, s.location, s.display_name, s.description, s.active, s.created_at,
                    (SELECT MAX(r.received_at) FROM noise_readings r
                      WHERE r.sensor_id = s.sensor_id) AS last_reading_at,
                    COALESCE(
                        (SELECT array_agg(u.name ORDER BY u.name)
                         FROM user_sensors us JOIN users u ON u.id = us.user_id
                         WHERE us.sensor_id = s.sensor_id AND u.active),
                        ARRAY[]::TEXT[]
                    ) AS residents
                FROM sensors s
                ORDER BY s.sensor_id
                """
            )
            return [dict(r) for r in cur.fetchall()]

    def get_sensor(self, sensor_id: str) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT sensor_id, location, display_name, description, active FROM sensors WHERE sensor_id = %s",
                (sensor_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_sensor(self, *, sensor_id: str, location: str, display_name: str | None,
                      description: str | None) -> None:
        try:
            with self.db.transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO sensors (sensor_id, location, display_name, description)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (sensor_id, location, display_name, description),
                )
        except psycopg2.errors.UniqueViolation as exc:
            raise DuplicateSensor(sensor_id) from exc

    def update_sensor(self, sensor_id: str, fields: dict) -> bool:
        allowed = {"location", "display_name", "description", "active"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return self.get_sensor(sensor_id) is not None
        assignments = ", ".join(f"{column} = %s" for column in fields)
        with self.db.transaction() as cur:
            cur.execute(
                f"UPDATE sensors SET {assignments} WHERE sensor_id = %s",
                (*fields.values(), sensor_id),
            )
            return cur.rowcount > 0

    def recipients_for_sensor(self, sensor_id: str) -> list[dict]:
        """Quem recebe alertas desse sensor: ativo, com convite aceito e algum canal ligado."""
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT u.id, u.name, u.email, u.phone, u.role,
                       COALESCE(p.email_enabled, TRUE) AS email_enabled,
                       COALESCE(p.push_enabled, TRUE)  AS push_enabled,
                       (SELECT COUNT(*) FROM device_tokens d WHERE d.user_id = u.id)::INT AS devices
                FROM user_sensors us
                JOIN users u ON u.id = us.user_id
                LEFT JOIN notification_preferences p ON p.user_id = u.id
                WHERE us.sensor_id = %s
                  AND u.active
                  AND u.password_hash IS NOT NULL
                  AND (COALESCE(p.email_enabled, TRUE) OR COALESCE(p.push_enabled, TRUE))
                ORDER BY lower(u.name)
                """,
                (sensor_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------------- auditoria ----------------

    def add_audit(self, actor_user_id: int | None, action: str, target: str | None = None,
                  details: dict | None = None) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO audit_log (actor_user_id, action, target, details) VALUES (%s, %s, %s, %s)",
                (actor_user_id, action, target, json.dumps(details or {}, default=str)),
            )

    def list_audit(self, limit: int = 100) -> list[dict]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT a.id, a.action, a.target, a.details, a.created_at,
                       a.actor_user_id, u.name AS actor_name
                FROM audit_log a
                LEFT JOIN users u ON u.id = a.actor_user_id
                ORDER BY a.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------------- configurações ----------------

    def get_setting(self, key: str) -> dict | None:
        with self.db.transaction() as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: dict, updated_by: int | None) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO app_settings (key, value, updated_by) VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = NOW()
                """,
                (key, json.dumps(value), updated_by),
            )
