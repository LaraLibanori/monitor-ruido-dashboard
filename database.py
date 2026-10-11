# =============================================
# database.py - Camada de acesso ao banco
# =============================================
# Toda interação com o PostgreSQL fica aqui.
# main.py não sabe nada sobre SQL.
# Os métodos são síncronos de propósito: o psycopg2
# bloqueia enquanto espera o banco, então o FastAPI
# executa as rotas "def" em threads separadas.
# =============================================

from datetime import datetime, timezone
from pathlib import Path
import os
from urllib.parse import urlparse
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from silence_policy import policy


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://noiseuser:noisepass@localhost:5432/noisedb",
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://noiseuser:noisepass@localhost:5432/noisedb",
)

# Mantém o fallback funcional mesmo quando o arquivo .env não existe.
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://noiseuser:noisepass@localhost:5432/noisedb"

# Fallback final para instalações sem arquivo .env.
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://noiseuser:noisepass@localhost:5432/noisedb"

_configured_url = os.getenv("DATABASE_URL")
_parsed_url = urlparse(_configured_url or "")
if not (
    _parsed_url.scheme in {"postgresql", "postgres"}
    and _parsed_url.hostname
    and _parsed_url.username
    and _parsed_url.password
):
    DATABASE_URL = "postgresql://noiseuser:noisepass@localhost:5432/noisedb"

_pool: ThreadedConnectionPool | None = None

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Ordem de gravidade dos níveis (usada para achar o "pior" nível de uma hora)
_LEVEL_ORDER_SQL = """
    CASE noise_level
        WHEN 'baixo' THEN 0 WHEN 'medio' THEN 1
        WHEN 'alto'  THEN 2 ELSE 3
    END
"""

# Sensores ativos numerados, com nome amigável ("Casa 1", "Casa 2"...)
_HOUSES_CTE = """
    houses AS (
        SELECT
            s.sensor_id,
            s.location,
            COALESCE(NULLIF(s.display_name, ''),
                     'Casa ' || ROW_NUMBER() OVER (ORDER BY s.sensor_id)) AS display_name,
            ROW_NUMBER() OVER (ORDER BY s.sensor_id) AS position
        FROM sensors s
        WHERE s.active
    )
"""


class Database:
    """Repositório de leituras de ruído."""

    def connect(self):
        global _pool
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
        print(f"🔌 Pool de conexões criado: {DATABASE_URL.split('@')[-1]}")
        self._run_migrations()

    def _run_migrations(self):
        """Aplica, uma única vez, cada arquivo de migrations/ (em ordem alfabética)."""
        conn = self._get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            name       TEXT PRIMARY KEY,
                            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cur.execute("SELECT name FROM schema_migrations")
                    applied = {row[0] for row in cur.fetchall()}

            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in applied:
                    continue
                with conn:  # cada migração é uma transação: ou aplica tudo, ou nada
                    with conn.cursor() as cur:
                        cur.execute(path.read_text(encoding="utf-8"))
                        cur.execute(
                            "INSERT INTO schema_migrations (name) VALUES (%s)",
                            (path.name,),
                        )
                print(f"🧱 Migração aplicada: {path.name}")
        finally:
            self._put_conn(conn)

    def disconnect(self):
        if _pool:
            _pool.closeall()

    def _get_conn(self):
        return _pool.getconn()

    def _put_conn(self, conn):
        _pool.putconn(conn)

    # --------------------------------------------------

    def save_reading(self, data, source_ip: str) -> int:
        """Persiste uma leitura e garante que o sensor exista."""
        now        = datetime.now(tz=timezone.utc)
        # Hora no fuso do condomínio (antes usava o relógio do container, que é UTC)
        local_hour = policy.to_local(now).hour
        silence    = policy.is_silence(now)

        conn = self._get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id
                        FROM noise_readings
                        WHERE sensor_id = %s AND sequence = %s
                        """,
                        (data.sensor_id, data.sequence),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        return existing[0]

                    # Upsert do sensor (cria se não existir)
                    cur.execute(
                        """
                        INSERT INTO sensors (sensor_id, location)
                        VALUES (%s, %s)
                        ON CONFLICT (sensor_id) DO UPDATE
                            SET location = EXCLUDED.location
                        """,
                        (data.sensor_id, data.location),
                    )

                    # Insere leitura
                    cur.execute(
                        """
                        INSERT INTO noise_readings
                            (sensor_id, rms, noise_level, sequence,
                             device_uptime_ms, source_ip, received_at,
                             capture_hour, is_silence_period)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sensor_id, sequence) DO NOTHING
                        RETURNING id
                        """,
                        (
                            data.sensor_id,
                            data.rms,
                            data.noise_level,
                            data.sequence,
                            data.device_uptime_ms,
                            source_ip,
                            now,
                            local_hour,
                            silence,
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute(
                            """
                            SELECT id
                            FROM noise_readings
                            WHERE sensor_id = %s AND sequence = %s
                            """,
                            (data.sensor_id, data.sequence),
                        )
                        row = cur.fetchone()
                    return row[0]
        finally:
            self._put_conn(conn)

    def get_readings(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        r.id,
                        r.sensor_id,
                        s.location,
                        r.rms,
                        r.noise_level,
                        r.sequence,
                        r.device_uptime_ms,
                        r.source_ip,
                        to_char(r.received_at AT TIME ZONE %s,
                                'YYYY-MM-DD HH24:MI:SS') AS received_at,
                        r.capture_hour,
                        r.is_silence_period
                    FROM noise_readings r
                    JOIN sensors s USING (sensor_id)
                    ORDER BY r.id DESC
                    LIMIT %s
                    """,
                    (policy.tz_name, limit),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def get_sensors(self) -> list[dict]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        s.sensor_id,
                        s.location,
                        s.description,
                        s.active,
                        COUNT(r.id)           AS total_readings,
                        MAX(r.received_at)    AS last_reading_at
                    FROM sensors s
                    LEFT JOIN noise_readings r USING (sensor_id)
                    GROUP BY s.sensor_id, s.location, s.description, s.active
                    ORDER BY s.sensor_id
                    """
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def count_readings(self) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM noise_readings")
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)

    # --------------------------------------------------
    # Consultas do aplicativo Android
    # --------------------------------------------------

    def get_houses_overview(self, day_start_utc: datetime) -> list[dict]:
        """Cada casa com sua última leitura e o resumo do dia."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    WITH {_HOUSES_CTE},
                    today AS (
                        SELECT
                            sensor_id,
                            COUNT(*) AS readings,
                            COUNT(*) FILTER (
                                WHERE is_silence_period
                                  AND noise_level IN ('alto', 'muito_alto')
                            ) AS loud_in_silence
                        FROM noise_readings
                        WHERE received_at >= %s
                        GROUP BY sensor_id
                    )
                    SELECT
                        h.sensor_id,
                        h.location,
                        h.display_name,
                        last.rms,
                        last.noise_level,
                        last.is_silence_period,
                        EXTRACT(EPOCH FROM (NOW() - last.received_at))::INT AS seconds_since_last,
                        COALESCE(t.readings, 0)        AS today_readings,
                        COALESCE(t.loud_in_silence, 0) AS today_loud_in_silence
                    FROM houses h
                    LEFT JOIN LATERAL (
                        SELECT r.rms, r.noise_level, r.is_silence_period, r.received_at
                        FROM noise_readings r
                        WHERE r.sensor_id = h.sensor_id
                        ORDER BY r.received_at DESC
                        LIMIT 1
                    ) last ON TRUE
                    LEFT JOIN today t ON t.sensor_id = h.sensor_id
                    ORDER BY h.position
                    """,
                    (day_start_utc,),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def get_house(self, sensor_id: str) -> dict | None:
        """Dados de uma casa (nome amigável incluso) ou None se não existir."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    WITH {_HOUSES_CTE}
                    SELECT sensor_id, location, display_name
                    FROM houses WHERE sensor_id = %s
                    """,
                    (sensor_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put_conn(conn)

    def get_hourly_history(
        self, sensor_id: str, start_utc: datetime, end_utc: datetime, tz_name: str
    ) -> list[dict]:
        """Resumo hora a hora (no fuso do condomínio) de um sensor num intervalo."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        EXTRACT(HOUR FROM received_at AT TIME ZONE %s)::INT AS hour,
                        COUNT(*)                   AS readings,
                        AVG(rms)::REAL             AS avg_rms,
                        MAX(rms)                   AS max_rms,
                        MAX({_LEVEL_ORDER_SQL})    AS worst_level_order,
                        COUNT(*) FILTER (
                            WHERE noise_level IN ('alto', 'muito_alto')
                        ) AS loud,
                        COUNT(*) FILTER (
                            WHERE is_silence_period
                              AND noise_level IN ('alto', 'muito_alto')
                        ) AS loud_in_silence
                    FROM noise_readings
                    WHERE sensor_id = %s
                      AND received_at >= %s
                      AND received_at <  %s
                    GROUP BY 1
                    ORDER BY 1
                    """,
                    (tz_name, sensor_id, start_utc, end_utc),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._put_conn(conn)
