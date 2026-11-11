# =============================================
# Testes de integração: API real + PostgreSQL real.
# Cada execução recria o banco <nome>_test do zero (init.sql + migrações).
#   TEST_DATABASE_URL=postgresql://usuario:senha@localhost:5432/noisedb_test pytest
# =============================================

import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import parse_qs

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # templates/ e migrations/ são relativos à raiz

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://noiseuser:noisepass@localhost:5432/noisedb_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "chave-somente-para-testes")
os.environ.setdefault("PASSWORD_SCRYPT_N", "1024")  # hash rápido nos testes
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["PUSH_PROVIDER"] = "console"
os.environ["APP_REQUIRE_AUTH"] = "false"
os.environ.setdefault("LOGIN_MAX_FAILURES", "5")


def _recreate_database():
    parsed = urlparse(TEST_DATABASE_URL)
    name = parsed.path.lstrip("/")
    admin_url = parsed._replace(path="/postgres").geturl()
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{name}"')
    conn.close()
    conn = psycopg2.connect(TEST_DATABASE_URL)
    with conn, conn.cursor() as cur:
        cur.execute((ROOT / "init.sql").read_text(encoding="utf-8"))
    conn.close()


_recreate_database()

import main  # noqa: E402  (precisa das variáveis acima)
from fastapi.testclient import TestClient  # noqa: E402
from notifications import ConsoleEmailProvider, ConsolePushProvider  # noqa: E402
from silence_policy import policy  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as test_client:  # roda o lifespan (conexão + migrações)
        yield test_client


@pytest.fixture(autouse=True)
def clean_state(client):
    """Banco e serviços limpos antes de cada teste."""
    with main.db.transaction() as cur:
        cur.execute(
            """
            TRUNCATE users, user_sessions, user_invites, user_sensors,
                     notification_preferences, device_tokens, alert_events,
                     notification_deliveries, audit_log, app_settings,
                     noise_readings RESTART IDENTITY CASCADE
            """
        )
        cur.execute("DELETE FROM sensors WHERE sensor_id NOT IN ('sensor_ap1','sensor_ap2','sensor_ap3','sensor_ap4')")
        cur.execute("UPDATE sensors SET active = TRUE, display_name = NULL")
    email, push = ConsoleEmailProvider(), ConsolePushProvider()
    main.alert_service.email = email
    main.alert_service.push = push
    main.auth_service.email = email
    main.auth_service._throttle._failures.clear()
    main._rate_store.clear()
    policy.update(weekday_start="22:00", weekend_start="15:00", end="09:00")
    yield


@pytest.fixture
def outbox():
    return {"email": main.alert_service.email.outbox, "push": main.alert_service.push.outbox}


@pytest.fixture
def always_silence():
    """Todo instante vira horário de silêncio."""
    policy.update(weekday_start="00:00", weekend_start="00:00", end="00:00")


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(client):
    main.auth_service.create_admin(name="Síndica", email="admin@exemplo.com", password="senha-admin-1")
    response = client.post("/api/auth/login", json={"email": "admin@exemplo.com", "password": "senha-admin-1"})
    assert response.status_code == 200, response.text
    data = response.json()
    return {"user": data["user"], "headers": auth_header(data["token"])}


def invite_token(invite: dict) -> str:
    return parse_qs(urlparse(invite["invite_url"]).query)["token"][0]


@pytest.fixture
def make_resident(client, admin):
    """Cadastra morador, aceita o convite e devolve {user, headers, token}."""
    def _make(email="ana@exemplo.com", sensor_ids=("sensor_ap1",), name="Ana Souza",
              notifications=None, accept=True, password="senha-morador-1"):
        body = {"name": name, "email": email, "sensor_ids": list(sensor_ids)}
        if notifications is not None:
            body["notifications"] = notifications
        created = client.post("/api/admin/users", json=body, headers=admin["headers"])
        assert created.status_code == 201, created.text
        data = created.json()
        result = {"user": data["user"], "invite": data["invite"]}
        if accept:
            accepted = client.post(
                "/api/auth/invites/accept",
                json={"token": invite_token(data["invite"]), "password": password},
            )
            assert accepted.status_code == 200, accepted.text
            result["user"] = accepted.json()["user"]
            result["headers"] = auth_header(accepted.json()["token"])
        return result
    return _make


def post_reading(client, sensor_id="sensor_ap1", level="alto", sequence=1, rms=21000.0):
    return client.post("/api/noise", json={
        "sensor_id": sensor_id, "location": sensor_id.replace("sensor_", "").upper(),
        "rms": rms, "noise_level": level, "sequence": sequence, "device_uptime_ms": 1000 + sequence,
    })
