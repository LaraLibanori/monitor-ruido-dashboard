from datetime import datetime, timezone
import json

import pytest

import security
from notifications import (
    ConsoleEmailProvider, ConsolePushProvider, FcmPushProvider, SmtpEmailProvider,
    build_email_provider, build_push_provider,
)
from silence_policy import SilencePolicy, _parse_hhmm


def test_hash_de_senha():
    stored = security.hash_password("uma-senha-boa")
    assert security.verify_password("uma-senha-boa", stored)
    assert not security.verify_password("outra-senha", stored)
    assert not security.verify_password("uma-senha-boa", None)
    assert not security.verify_password("uma-senha-boa", "lixo")
    assert security.hash_password("uma-senha-boa") != stored  # sal aleatório
    with pytest.raises(ValueError):
        security.hash_password("curta")


def test_tokens():
    a, b = security.new_token(), security.new_token()
    assert a != b and len(a) >= 40
    assert security.hash_token(a) == security.hash_token(a) != security.hash_token(b)


def test_parse_horario():
    assert _parse_hhmm("9:05").hour == 9
    for bad in ("25:00", "aa:bb", "2200", "22:0", ""):
        with pytest.raises(ValueError):
            _parse_hhmm(bad)


def test_politica_de_silencio_e_update():
    policy = SilencePolicy.from_env()
    policy.update(weekday_start="22:00", weekend_start="15:00", end="09:00")
    tz = policy.tz
    wednesday_23h = datetime(2026, 11, 11, 23, 0, tzinfo=tz)
    wednesday_12h = datetime(2026, 11, 11, 12, 0, tzinfo=tz)
    saturday_16h = datetime(2026, 11, 14, 16, 0, tzinfo=tz)
    assert policy.is_silence(wednesday_23h)
    assert not policy.is_silence(wednesday_12h)
    assert policy.is_silence(saturday_16h)
    policy.update(weekday_start="11:00", weekend_start="15:00", end="09:00")
    assert policy.is_silence(wednesday_12h)
    assert policy.rules()["weekday_start"] == "11:00"


def test_fabricas_sem_credenciais_usam_simulacao(monkeypatch):
    for name in ("EMAIL_PROVIDER", "PUSH_PROVIDER", "SMTP_HOST", "FCM_CREDENTIALS_PATH"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(build_email_provider(), ConsoleEmailProvider)
    assert isinstance(build_push_provider(), ConsolePushProvider)
    monkeypatch.setenv("FCM_CREDENTIALS_PATH", "/nao/existe.json")
    assert isinstance(build_push_provider(), ConsolePushProvider)
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    smtp = build_email_provider()
    assert isinstance(smtp, SmtpEmailProvider) and smtp.use_ssl and not smtp.use_starttls


def test_smtp_envia_e_registra_falha(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            sent["tls"] = True

        def login(self, user, password):
            if password != "certa":
                import smtplib
                raise smtplib.SMTPAuthenticationError(535, b"bad")
            sent["login"] = user

        def send_message(self, message):
            sent["to"] = message["To"]

    monkeypatch.setattr("notifications.smtplib.SMTP", FakeSMTP)
    provider = SmtpEmailProvider(host="smtp.x", port=587, user="u", password="certa",
                                 sender="no-reply@x", use_ssl=False, use_starttls=True)
    assert provider.send("ana@x.com", "Assunto", "Corpo").status == "sent"
    assert sent == {"server": ("smtp.x", 587), "tls": True, "login": "u", "to": "ana@x.com"}
    provider.password = "errada"
    failed = provider.send("ana@x.com", "Assunto", "Corpo")
    assert failed.status == "failed" and "SMTPAuthenticationError" in failed.detail


def test_fcm_monta_mensagem_v1_e_detecta_token_invalido(tmp_path):
    credentials = tmp_path / "firebase.json"
    credentials.write_text(json.dumps({"project_id": "monitor-ruido-teste"}))

    class Response:
        def __init__(self, status, text=""):
            self.status_code, self.text = status, text

    class Session:
        def __init__(self):
            self.calls = []

        def post(self, url, json, timeout):
            self.calls.append((url, json))
            token = json["message"]["token"]
            if token == "valido":
                return Response(200)
            return Response(404, '{"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}')

    session = Session()
    provider = FcmPushProvider(str(credentials), session=session)
    result = provider.send(["valido", "antigo"], "Título", "Corpo", {"sensor_id": "sensor_ap1", "n": 3})
    assert result.status == "sent" and result.invalid_tokens == ["antigo"]
    url, payload = session.calls[0]
    assert url == "https://fcm.googleapis.com/v1/projects/monitor-ruido-teste/messages:send"
    assert payload["message"]["notification"] == {"title": "Título", "body": "Corpo"}
    assert payload["message"]["data"] == {"sensor_id": "sensor_ap1", "n": "3"}  # FCM exige strings
    assert provider.send([], "t", "b").status == "skipped"


def test_console_nunca_diz_que_enviou():
    assert ConsoleEmailProvider().send("a@b.com", "s", "b").status == "simulated"
    assert ConsolePushProvider().send(["t"], "s", "b").status == "simulated"
    assert datetime.now(timezone.utc)  # sanity
