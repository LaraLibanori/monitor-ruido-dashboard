# =============================================
# notifications.py - Envio de e-mail e push
# =============================================
# Provedores reais:
#   - E-mail: SMTP (qualquer provedor: Gmail, SendGrid, Mailgun, SES...)
#   - Push:   Firebase Cloud Messaging (API HTTP v1, conta de serviço)
# Provedores de desenvolvimento ("console"):
#   - não enviam nada; registram no log e devolvem status "simulated".
#   - são usados automaticamente quando faltam credenciais, para o
#     sistema nunca dizer que enviou algo que não enviou.
# =============================================

from dataclasses import dataclass, field
from email.message import EmailMessage
import json
import logging
import os
import smtplib
import ssl
import threading

log = logging.getLogger("monitor.notifications")


@dataclass
class DeliveryResult:
    status: str                 # sent | simulated | failed | skipped
    provider: str
    detail: str = ""
    invalid_tokens: list[str] = field(default_factory=list)


@dataclass
class OutboxItem:
    channel: str
    to: str | list[str]
    title: str
    body: str
    data: dict = field(default_factory=dict)


# ---------------- e-mail ----------------

class ConsoleEmailProvider:
    """Não envia: só registra. Útil sem credenciais e nos testes (outbox)."""
    name = "console-email"

    def __init__(self):
        self.outbox: list[OutboxItem] = []
        self._lock = threading.Lock()

    def send(self, to: str, subject: str, body: str) -> DeliveryResult:
        with self._lock:
            self.outbox.append(OutboxItem("email", to, subject, body))
        log.info("[e-mail simulado] para=%s assunto=%s", to, subject)
        return DeliveryResult("simulated", self.name, "SMTP não configurado: e-mail apenas registrado no log.")


class SmtpEmailProvider:
    name = "smtp"

    def __init__(self, *, host: str, port: int, user: str, password: str,
                 sender: str, use_ssl: bool, use_starttls: bool, timeout: float = 15):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.sender = sender
        self.use_ssl, self.use_starttls = use_ssl, use_starttls
        self.timeout = timeout

    def send(self, to: str, subject: str, body: str) -> DeliveryResult:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            context = ssl.create_default_context()
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with server:
                if self.use_starttls and not self.use_ssl:
                    server.starttls(context=context)
                if self.user:
                    server.login(self.user, self.password)
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("Falha no envio de e-mail para %s: %s", to, exc)
            return DeliveryResult("failed", self.name, f"{type(exc).__name__}: {exc}")
        return DeliveryResult("sent", self.name, "")


# ---------------- push ----------------

class ConsolePushProvider:
    name = "console-push"

    def __init__(self):
        self.outbox: list[OutboxItem] = []
        self._lock = threading.Lock()

    def send(self, tokens: list[str], title: str, body: str, data: dict | None = None) -> DeliveryResult:
        with self._lock:
            self.outbox.append(OutboxItem("push", list(tokens), title, body, data or {}))
        log.info("[push simulado] aparelhos=%d título=%s", len(tokens), title)
        return DeliveryResult("simulated", self.name, "FCM não configurado: push apenas registrado no log.")


class FcmPushProvider:
    """Firebase Cloud Messaging, API HTTP v1, autenticada com conta de serviço."""
    name = "fcm"
    _SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

    def __init__(self, credentials_path: str, project_id: str | None = None,
                 session=None, credentials=None):
        self.credentials_path = credentials_path
        if project_id is None:
            with open(credentials_path, encoding="utf-8") as fh:
                project_id = json.load(fh).get("project_id")
        if not project_id:
            raise ValueError("Não foi possível descobrir o project_id do Firebase.")
        self.project_id = project_id
        self._credentials = credentials
        self._session = session
        self._lock = threading.Lock()

    def _authorized_session(self):
        # Import tardio: só quem usa FCM precisa do google-auth instalado
        with self._lock:
            if self._session is None:
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account
                creds = self._credentials or service_account.Credentials.from_service_account_file(
                    self.credentials_path, scopes=[self._SCOPE]
                )
                self._session = AuthorizedSession(creds)
            return self._session

    def send(self, tokens: list[str], title: str, body: str, data: dict | None = None) -> DeliveryResult:
        if not tokens:
            return DeliveryResult("skipped", self.name, "Nenhum aparelho registrado.")
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        payload_data = {k: str(v) for k, v in (data or {}).items()}
        sent, errors, invalid = 0, [], []
        try:
            session = self._authorized_session()
        except Exception as exc:  # credencial inválida, arquivo ausente etc.
            log.warning("FCM indisponível: %s", exc)
            return DeliveryResult("failed", self.name, f"Credencial FCM: {type(exc).__name__}: {exc}")
        for token in tokens:
            message = {
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "data": payload_data,
                    "android": {"priority": "HIGH"},
                    "apns": {"headers": {"apns-priority": "10"}},
                }
            }
            try:
                response = session.post(url, json=message, timeout=15)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
            if response.status_code == 200:
                sent += 1
                continue
            text = response.text[:300]
            # Token que não existe mais: remover do banco
            if response.status_code == 404 or "UNREGISTERED" in text or (
                response.status_code == 400 and "registration token" in text.lower()
            ):
                invalid.append(token)
            errors.append(f"HTTP {response.status_code}: {text}")
        if sent:
            detail = f"{sent}/{len(tokens)} aparelho(s)." + (f" Erros: {'; '.join(errors)}" if errors else "")
            return DeliveryResult("sent", self.name, detail, invalid)
        return DeliveryResult("failed", self.name, "; ".join(errors) or "Falha desconhecida.", invalid)


# ---------------- fábrica ----------------

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


def build_email_provider():
    mode = os.getenv("EMAIL_PROVIDER", "auto").strip().lower()
    host = os.getenv("SMTP_HOST", "").strip()
    if mode == "console" or (mode == "auto" and not host):
        return ConsoleEmailProvider()
    if not host:
        raise ValueError("EMAIL_PROVIDER=smtp exige SMTP_HOST.")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    return SmtpEmailProvider(
        host=host,
        port=port,
        user=user,
        password=os.getenv("SMTP_PASSWORD", ""),
        sender=os.getenv("SMTP_FROM", "") or user or "monitor-ruido@localhost",
        use_ssl=_env_bool("SMTP_USE_SSL", port == 465),
        use_starttls=_env_bool("SMTP_STARTTLS", port != 465),
    )


def build_push_provider():
    mode = os.getenv("PUSH_PROVIDER", "auto").strip().lower()
    path = os.getenv("FCM_CREDENTIALS_PATH", "").strip()
    if mode == "console" or (mode == "auto" and not path):
        return ConsolePushProvider()
    if not path or not os.path.isfile(path):
        log.warning("FCM_CREDENTIALS_PATH ausente ou arquivo inexistente (%r): push em modo simulado.", path)
        return ConsolePushProvider()
    return FcmPushProvider(path, project_id=os.getenv("FCM_PROJECT_ID") or None)
