# =============================================
# auth_service.py - Regras de acesso, usuários e administração
# =============================================
# - Login com sessão expirável (token Bearer).
# - Papéis: "admin" (gerencia tudo) e "morador" (vê só as casas dele).
# - Morador entra por convite: o administrador cadastra, o sistema gera
#   um link com validade; ao aceitar, o morador define a senha e o contato
#   fica confirmado.
# - Toda ação administrativa vai para a auditoria.
# Não tem HTTP aqui (as rotas traduzem ServiceError em resposta).
# =============================================

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
import re
import threading
import time

import security
from notifications import ConsoleEmailProvider
from silence_policy import policy
from user_repository import DuplicateEmail, DuplicateSensor, UnknownSensor, UserRepository

SESSION_TTL_HOURS = float(os.getenv("SESSION_TTL_HOURS", 12))
INVITE_TTL_HOURS = float(os.getenv("INVITE_TTL_HOURS", 72))
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", 5))
LOGIN_LOCK_SECONDS = int(os.getenv("LOGIN_LOCK_SECONDS", 15 * 60))
LOGIN_IP_MAX_FAILURES = int(os.getenv("LOGIN_IP_MAX_FAILURES", LOGIN_MAX_FAILURES))
LOGIN_MAX_TRACKED_KEYS = int(os.getenv("LOGIN_MAX_TRACKED_KEYS", 10_000))

ROLES = ("admin", "morador")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SENSOR_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SILENCE_SETTING_KEY = "silence_policy"


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise ServiceError(422, "Informe um e-mail válido.")
    return email


def normalize_phone(phone: str | None) -> str | None:
    if phone is None or not str(phone).strip():
        return None
    raw = str(phone).strip()
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 15:
        raise ServiceError(422, "Telefone inválido: use DDD + número (ex.: 11 91234-5678).")
    return ("+" if raw.startswith("+") else "") + digits


def normalize_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > 120:
        raise ServiceError(422, "Informe um nome com até 120 caracteres.")
    return name


def public_user(user: dict) -> dict:
    """O que pode sair na API sobre um usuário (sem hash de senha)."""
    status = "ativo" if user["active"] and user["has_password"] else (
        "convite_pendente" if user["active"] else "inativo"
    )
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "phone": user["phone"],
        "role": user["role"],
        "active": user["active"],
        "status": status,
        "contact_verified": user["contact_verified_at"] is not None,
        "sensor_ids": list(user["sensor_ids"]),
        "notifications": {"email": user["email_enabled"], "push": user["push_enabled"]},
        "devices": user["devices"],
        "invite_expires_at": user["invite_expires_at"],
        "created_at": user["created_at"],
    }


class _LoginThrottle:
    """Bloqueia tentativas de senha por credencial e por endereço IP."""

    def __init__(self, max_tracked_keys: int = LOGIN_MAX_TRACKED_KEYS):
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._ip_failures: dict[str, list[float]] = defaultdict(list)
        self._max_tracked_keys = max(1, max_tracked_keys)
        self._lock = threading.Lock()

    @staticmethod
    def _recent(failures: dict[str, list[float]], key: str, now: float) -> list[float]:
        values = failures.get(key)
        if not values:
            return []
        recent = [t for t in values if now - t < LOGIN_LOCK_SECONDS]
        if recent:
            failures[key] = recent
        else:
            failures.pop(key, None)
        return recent

    def _prune(self, now: float) -> None:
        for failures in (self._failures, self._ip_failures):
            for key in list(failures):
                self._recent(failures, key, now)
            while len(failures) > self._max_tracked_keys:
                oldest = min(failures, key=lambda item: failures[item][0])
                failures.pop(oldest, None)

    def check(self, key: str, client_ip: str) -> None:
        with self._lock:
            now = time.time()
            self._prune(now)
            if (
                len(self._recent(self._failures, key, now)) >= LOGIN_MAX_FAILURES
                or len(self._recent(self._ip_failures, client_ip, now)) >= LOGIN_IP_MAX_FAILURES
            ):
                raise ServiceError(429, "Muitas tentativas. Aguarde alguns minutos e tente de novo.")

    def fail(self, key: str, client_ip: str) -> None:
        with self._lock:
            now = time.time()
            self._prune(now)
            self._failures.setdefault(key, []).append(now)
            self._ip_failures.setdefault(client_ip, []).append(now)
            self._prune(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class AuthService:
    def __init__(self, users: UserRepository, email_provider=None, alerts=None):
        self.users = users
        self.email = email_provider or ConsoleEmailProvider()
        self.alerts = alerts  # AlertService (registro de entregas de convite)
        self._throttle = _LoginThrottle()

    # ---------------- sessão ----------------

    def login(self, email: str, password: str, client_ip: str = "?") -> dict:
        email = (email or "").strip().lower()
        key = f"{client_ip}|{email}"
        self._throttle.check(key, client_ip)
        row = self.users.get_login_row(email) if email else None
        ok = bool(row) and row["active"] and security.verify_password(password or "", row["password_hash"])
        if not ok:
            self._throttle.fail(key, client_ip)
            self.users.add_audit(row["id"] if row else None, "login_falhou", email, {"ip": client_ip})
            raise ServiceError(401, "E-mail ou senha incorretos.")
        self._throttle.reset(key)
        session = self._new_session(row["id"])
        self.users.add_audit(row["id"], "login", email, {"ip": client_ip})
        return session

    def _new_session(self, user_id: int) -> dict:
        token = security.new_token()
        expires_at = _now() + timedelta(hours=SESSION_TTL_HOURS)
        self.users.create_session(user_id, security.hash_token(token), expires_at)
        return {
            "token": token,
            "token_type": "bearer",
            "expires_at": expires_at,
            "user": public_user(self.users.get_user(user_id)),
        }

    def logout(self, token: str) -> None:
        self.users.revoke_session(security.hash_token(token))

    def authenticate(self, token: str) -> dict | None:
        """Usuário dono do token, ou None se o token for inválido/expirado."""
        if not token:
            return None
        session = self.users.get_session(security.hash_token(token))
        if not session:
            return None
        user = self.users.get_user(session["user_id"])
        if not user or not user["active"]:
            return None
        user["session_expires_at"] = session["expires_at"]
        return user

    # ---------------- primeiro administrador (CLI) ----------------

    def create_admin(self, *, name: str, email: str, password: str, phone: str | None = None) -> dict:
        try:
            password_hash = security.hash_password(password)
        except ValueError as exc:
            raise ServiceError(422, str(exc)) from exc
        try:
            user_id = self.users.create_user(
                name=normalize_name(name), email=normalize_email(email),
                phone=normalize_phone(phone), role="admin",
                password_hash=password_hash, verified=True,
            )
        except DuplicateEmail:
            raise ServiceError(409, "Já existe um usuário com esse e-mail.") from None
        self.users.add_audit(None, "admin_criado_cli", email, {"user_id": user_id})
        return public_user(self.users.get_user(user_id))

    # ---------------- convites ----------------

    def _issue_invite(self, actor: dict | None, user: dict, channel: str, base_url: str) -> dict:
        if channel not in ("email", "phone"):
            raise ServiceError(422, "Canal do convite deve ser 'email' ou 'phone'.")
        if channel == "phone" and not user["phone"]:
            raise ServiceError(422, "Cadastre um telefone para convidar por telefone.")
        token = security.new_token()
        expires_at = _now() + timedelta(hours=INVITE_TTL_HOURS)
        self.users.create_invite(
            user_id=user["id"], token_hash=security.hash_token(token), channel=channel,
            created_by=actor["id"] if actor else None, expires_at=expires_at,
        )
        url = f"{base_url.rstrip('/')}/convite?token={token}"
        expires_local = policy.to_local(expires_at).strftime("%d/%m/%Y %H:%M")
        if channel == "email":
            result = self.email.send(
                user["email"],
                "Convite: Monitor de Ruído",
                f"Olá, {user['name']}!\n\n"
                "Você foi convidado(a) para acompanhar o Monitor de Ruído do condomínio.\n"
                f"Para criar sua senha e ativar o acesso, abra o link abaixo até {expires_local}:\n\n"
                f"{url}\n\n"
                "Se você não esperava este convite, ignore esta mensagem.",
            )
            delivery = {"channel": "email", "status": result.status, "provider": result.provider,
                        "detail": result.detail}
        else:
            # Sem provedor de SMS/WhatsApp: o administrador compartilha o link.
            delivery = {"channel": "phone", "status": "skipped", "provider": "manual",
                        "detail": "Envio por SMS/WhatsApp não configurado: compartilhe o link manualmente."}
        if self.alerts and delivery["channel"] == "email":
            self.alerts.record_delivery(
                user_id=user["id"], kind="invite", channel="email",
                status=delivery["status"], provider=delivery["provider"], detail=delivery["detail"],
            )
        self.users.add_audit(
            actor["id"] if actor else None, "convite_emitido", user["email"],
            {"user_id": user["id"], "channel": channel, "delivery": delivery["status"]},
        )
        return {"invite_url": url, "expires_at": expires_at, "delivery": delivery}

    def invite_info(self, token: str) -> dict:
        invite = self._valid_invite(token)
        return {
            "name": invite["name"], "email": invite["email"], "role": invite["role"],
            "channel": invite["channel"], "expires_at": invite["expires_at"],
        }

    def _valid_invite(self, token: str) -> dict:
        invite = self.users.get_invite(security.hash_token(token or ""))
        if not invite or invite["revoked_at"] is not None:
            raise ServiceError(404, "Convite inválido ou substituído por um mais novo.")
        if invite["accepted_at"] is not None:
            raise ServiceError(409, "Este convite já foi usado. Entre com seu e-mail e senha.")
        if invite["expired"]:
            raise ServiceError(410, "Convite expirado. Peça um novo ao administrador.")
        if not invite["active"]:
            raise ServiceError(403, "Este acesso foi desativado pelo administrador.")
        return invite

    def accept_invite(self, token: str, password: str) -> dict:
        invite = self._valid_invite(token)
        try:
            password_hash = security.hash_password(password)
        except ValueError as exc:
            raise ServiceError(422, str(exc)) from exc
        if not self.users.accept_invite(invite["id"], invite["user_id"], password_hash):
            raise ServiceError(409, "Este convite já foi usado. Entre com seu e-mail e senha.")
        self.users.add_audit(invite["user_id"], "convite_aceito", invite["email"],
                             {"channel": invite["channel"]})
        return self._new_session(invite["user_id"])

    # ---------------- usuários (admin) ----------------

    def list_users(self, role: str | None = None) -> list[dict]:
        if role and role not in ROLES:
            raise ServiceError(422, "Papel inválido.")
        return [public_user(u) for u in self.users.list_users(role)]

    def get_user(self, user_id: int) -> dict:
        user = self.users.get_user(user_id)
        if not user:
            raise ServiceError(404, "Usuário não encontrado.")
        return user

    def create_user(self, actor: dict, *, name: str, email: str, phone: str | None, role: str,
                    sensor_ids: list[str], email_enabled: bool, push_enabled: bool,
                    invite_channel: str, base_url: str) -> dict:
        if role not in ROLES:
            raise ServiceError(422, "Papel deve ser 'admin' ou 'morador'.")
        name, email, phone = normalize_name(name), normalize_email(email), normalize_phone(phone)
        if invite_channel == "phone" and not phone:
            raise ServiceError(422, "Cadastre um telefone para convidar por telefone.")
        missing = self.users.missing_sensors(sensor_ids)
        if missing:
            raise ServiceError(422, f"Sensor(es) inexistente(s): {', '.join(missing)}.")
        try:
            user_id = self.users.create_user(name=name, email=email, phone=phone, role=role)
        except DuplicateEmail:
            raise ServiceError(409, "Já existe um usuário com esse e-mail.") from None
        self.users.set_user_sensors(user_id, sensor_ids)
        self.users.set_preferences(user_id, email_enabled=email_enabled, push_enabled=push_enabled)
        self.users.add_audit(actor["id"], "usuario_criado", email,
                             {"user_id": user_id, "role": role, "sensor_ids": sorted(set(sensor_ids))})
        user = self.users.get_user(user_id)
        invite = self._issue_invite(actor, user, invite_channel, base_url)
        return {"user": public_user(self.users.get_user(user_id)), "invite": invite}

    def update_user(self, actor: dict, user_id: int, changes: dict) -> dict:
        user = self.get_user(user_id)
        fields: dict = {}
        if "name" in changes:
            fields["name"] = normalize_name(changes["name"])
        if "email" in changes:
            fields["email"] = normalize_email(changes["email"])
        if "phone" in changes:
            fields["phone"] = normalize_phone(changes["phone"])
        if "role" in changes:
            if changes["role"] not in ROLES:
                raise ServiceError(422, "Papel deve ser 'admin' ou 'morador'.")
            fields["role"] = changes["role"]
        if "active" in changes:
            fields["active"] = bool(changes["active"])
        if user_id == actor["id"] and (fields.get("active") is False or fields.get("role") == "morador"):
            raise ServiceError(409, "Você não pode desativar nem rebaixar a própria conta.")
        try:
            self.users.update_user(user_id, fields)
        except DuplicateEmail:
            raise ServiceError(409, "Já existe um usuário com esse e-mail.") from None
        if "sensor_ids" in changes:
            try:
                self.users.set_user_sensors(user_id, changes["sensor_ids"] or [])
            except UnknownSensor as exc:
                raise ServiceError(422, f"Sensor(es) inexistente(s): {', '.join(exc.sensor_ids)}.") from None
        prefs = changes.get("notifications") or {}
        if prefs:
            self.users.set_preferences(user_id, email_enabled=prefs.get("email"),
                                       push_enabled=prefs.get("push"))
        if fields.get("active") is False or ("email" in fields and fields["email"] != user["email"]):
            self.users.revoke_user_sessions(user_id)
        self.users.add_audit(actor["id"], "usuario_alterado", user["email"],
                             {"user_id": user_id, "changes": changes})
        return public_user(self.users.get_user(user_id))

    def resend_invite(self, actor: dict, user_id: int, channel: str, base_url: str) -> dict:
        user = self.get_user(user_id)
        if not user["active"]:
            raise ServiceError(409, "Reative o usuário antes de enviar um novo convite.")
        if user["has_password"]:
            raise ServiceError(409, "Este usuário já ativou o acesso.")
        return self._issue_invite(actor, user, channel, base_url)

    # ---------------- o próprio usuário ----------------

    def update_me(self, user: dict, changes: dict) -> dict:
        fields: dict = {}
        if "name" in changes:
            fields["name"] = normalize_name(changes["name"])
        if "phone" in changes:
            fields["phone"] = normalize_phone(changes["phone"])
        self.users.update_user(user["id"], fields)
        if fields:
            self.users.add_audit(user["id"], "perfil_alterado", user["email"], {"fields": sorted(fields)})
        return public_user(self.users.get_user(user["id"]))

    def change_password(self, user: dict, current: str, new: str) -> None:
        if not security.verify_password(current or "", self.users.get_password_hash(user["id"])):
            raise ServiceError(401, "Senha atual incorreta.")
        try:
            password_hash = security.hash_password(new)
        except ValueError as exc:
            raise ServiceError(422, str(exc)) from exc
        self.users.set_password(user["id"], password_hash, verify_contact=False)
        self.users.revoke_user_sessions(user["id"])
        self.users.add_audit(user["id"], "senha_alterada", user["email"])

    def set_preferences(self, user: dict, *, email: bool | None, push: bool | None) -> dict:
        self.users.set_preferences(user["id"], email_enabled=email, push_enabled=push)
        self.users.add_audit(user["id"], "preferencias_alteradas", user["email"],
                             {"email": email, "push": push})
        return public_user(self.users.get_user(user["id"]))["notifications"]

    def register_device(self, user: dict, token: str, platform: str) -> None:
        token = (token or "").strip()
        if not 20 <= len(token) <= 4096:
            raise ServiceError(422, "Token do aparelho inválido.")
        if platform not in ("android", "ios", "web"):
            raise ServiceError(422, "Plataforma deve ser android, ios ou web.")
        self.users.upsert_device(user["id"], token, platform)

    def remove_device(self, user: dict, token: str) -> None:
        if not self.users.delete_device(user["id"], (token or "").strip()):
            raise ServiceError(404, "Aparelho não encontrado.")

    @staticmethod
    def allowed_sensor_ids(user: dict | None) -> set[str] | None:
        """None = pode ver tudo (admin ou acesso público configurado)."""
        if user is None or user["role"] == "admin":
            return None
        return set(user["sensor_ids"])

    # ---------------- sensores (admin) ----------------

    def list_sensors(self) -> list[dict]:
        return self.users.list_sensors()

    def create_sensor(self, actor: dict, *, sensor_id: str, location: str,
                      display_name: str | None, description: str | None) -> dict:
        sensor_id = (sensor_id or "").strip()
        if not _SENSOR_ID_RE.match(sensor_id):
            raise ServiceError(422, "Identificador do sensor: letras, números, '_', '-' ou '.' (até 100).")
        location = (location or "").strip()
        if not location or len(location) > 200:
            raise ServiceError(422, "Informe o local do sensor (até 200 caracteres).")
        try:
            self.users.create_sensor(
                sensor_id=sensor_id, location=location,
                display_name=(display_name or "").strip() or None,
                description=(description or "").strip() or None,
            )
        except DuplicateSensor:
            raise ServiceError(409, "Já existe um sensor com esse identificador.") from None
        self.users.add_audit(actor["id"], "sensor_criado", sensor_id, {"location": location})
        return self.users.get_sensor(sensor_id)

    def update_sensor(self, actor: dict, sensor_id: str, changes: dict) -> dict:
        fields = {}
        for key in ("location", "display_name", "description"):
            if key in changes:
                value = (changes[key] or "").strip()
                if key == "location" and not value:
                    raise ServiceError(422, "O local do sensor não pode ficar vazio.")
                fields[key] = value or None
        if "active" in changes:
            fields["active"] = bool(changes["active"])
        if not self.users.update_sensor(sensor_id, fields):
            raise ServiceError(404, "Sensor não encontrado.")
        self.users.add_audit(actor["id"], "sensor_alterado", sensor_id, {"changes": changes})
        return self.users.get_sensor(sensor_id)

    def recipients(self, sensor_id: str) -> list[dict]:
        if not self.users.get_sensor(sensor_id):
            raise ServiceError(404, "Sensor não encontrado.")
        return self.users.recipients_for_sensor(sensor_id)

    # ---------------- horário de silêncio ----------------

    def load_silence_settings(self) -> None:
        """Na inicialização: o que o administrador salvou vale mais que o .env."""
        saved = self.users.get_setting(SILENCE_SETTING_KEY)
        if saved:
            try:
                policy.update(**{k: saved[k] for k in ("weekday_start", "weekend_start", "end")})
            except (KeyError, ValueError):
                pass

    def update_silence(self, actor: dict, *, weekday_start: str, weekend_start: str, end: str) -> dict:
        previous = policy.rules()
        try:
            policy.update(weekday_start=weekday_start, weekend_start=weekend_start, end=end)
        except ValueError as exc:
            raise ServiceError(422, str(exc)) from exc
        rules = policy.rules()
        self.users.set_setting(SILENCE_SETTING_KEY, rules, actor["id"])
        self.users.add_audit(actor["id"], "silencio_alterado", None, {"antes": previous, "depois": rules})
        return rules

    def audit(self, limit: int) -> list[dict]:
        return self.users.list_audit(min(max(limit, 1), 500))
