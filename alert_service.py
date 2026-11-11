# =============================================
# alert_service.py - Do barulho ao aviso
# =============================================
# Fluxo:
#   leitura salva -> é horário de silêncio? nível alto/muito alto?
#   -> sensor ativo? -> cria evento (sem duplicar) -> busca moradores
#   autorizados daquele sensor -> envia push e/ou e-mail conforme as
#   preferências -> registra o resultado de cada envio.
# Roda em segundo plano depois que a API já respondeu ao ESP32.
# =============================================

import logging
import os

from alert_repository import AlertRepository
from notifications import ConsoleEmailProvider, ConsolePushProvider
from silence_policy import policy
from user_repository import UserRepository

log = logging.getLogger("monitor.alerts")

ALERT_LEVELS = {"alto", "muito_alto"}
ALERT_COOLDOWN_MINUTES = float(os.getenv("ALERT_COOLDOWN_MINUTES", 15))
_LEVEL_LABEL = {"alto": "alto", "muito_alto": "muito alto"}


class AlertService:
    def __init__(self, alerts: AlertRepository, users: UserRepository,
                 email_provider=None, push_provider=None,
                 cooldown_minutes: float = ALERT_COOLDOWN_MINUTES):
        self.alerts = alerts
        self.users = users
        self.email = email_provider or ConsoleEmailProvider()
        self.push = push_provider or ConsolePushProvider()
        self.cooldown_minutes = cooldown_minutes

    def providers(self) -> dict:
        return {"email": self.email.name, "push": self.push.name}

    def record_delivery(self, *, user_id, kind, channel, status, provider, detail, alert_event_id=None):
        self.alerts.add_delivery(alert_event_id=alert_event_id, user_id=user_id, kind=kind,
                                 channel=channel, status=status, provider=provider, detail=detail)

    # ---------------------------------------------

    def process_reading(self, reading_id: int) -> int | None:
        """Retorna o id do evento criado, ou None se não era caso de alerta."""
        try:
            reading = self.alerts.get_reading(reading_id)
            if not reading or not reading["active"]:
                return None
            if not reading["is_silence_period"] or reading["noise_level"] not in ALERT_LEVELS:
                return None
            event_id = self.alerts.create_event_if_due(reading, self.cooldown_minutes)
            if event_id is None:
                return None
            self._notify(event_id, reading)
            return event_id
        except Exception:  # nunca derrubar o recebimento de leituras por causa de aviso
            log.exception("Falha ao processar alerta da leitura %s", reading_id)
            return None

    def _notify(self, event_id: int, reading: dict) -> None:
        local = policy.to_local(reading["received_at"])
        level = _LEVEL_LABEL.get(reading["noise_level"], reading["noise_level"])
        title = f"Barulho no horário de silêncio — {reading['house_name']}"
        body = (f"Nível {level} às {local:%H:%M} ({local:%d/%m}) em {reading['house_name']}. "
                "Abra o app para ver o histórico.")
        data = {"type": "noise_alert", "sensor_id": reading["sensor_id"], "event_id": event_id}
        for user in self.users.recipients_for_sensor(reading["sensor_id"]):
            self._deliver(user, title, body, data, kind="alert", event_id=event_id)

    def _deliver(self, user: dict, title: str, body: str, data: dict, *, kind: str,
                 event_id: int | None) -> list[dict]:
        results = []
        if user["push_enabled"]:
            tokens = self.users.list_device_tokens(user["id"])
            if tokens:
                result = self.push.send(tokens, title, body, data)
                for token in result.invalid_tokens:
                    self.users.delete_device_token(token)
                status, provider, detail = result.status, result.provider, result.detail
            else:
                status, provider, detail = "skipped", self.push.name, "Nenhum aparelho registrado no app."
            self.record_delivery(user_id=user["id"], kind=kind, channel="push", status=status,
                                 provider=provider, detail=detail, alert_event_id=event_id)
            results.append({"channel": "push", "status": status, "provider": provider, "detail": detail})
        if user["email_enabled"]:
            result = self.email.send(user["email"], title, body + "\n\n— Monitor de Ruído")
            self.record_delivery(user_id=user["id"], kind=kind, channel="email", status=result.status,
                                 provider=result.provider, detail=result.detail, alert_event_id=event_id)
            results.append({"channel": "email", "status": result.status,
                             "provider": result.provider, "detail": result.detail})
        return results

    def send_test(self, user: dict) -> list[dict]:
        """Envia uma notificação de teste pelos canais ligados do usuário."""
        title = "Teste — Monitor de Ruído"
        body = "Se você recebeu esta mensagem, as notificações estão funcionando."
        results = self._deliver(user, title, body, {"type": "test"}, kind="test", event_id=None)
        if not results:
            results.append({"channel": "-", "status": "skipped", "provider": "-",
                            "detail": "Todas as notificações deste usuário estão desligadas."})
        return results

    def list_events(self, limit: int = 50, sensor_ids: set[str] | None = None) -> list[dict]:
        return self.alerts.list_events(min(max(limit, 1), 200), sensor_ids)

    def list_deliveries(self, limit: int = 100) -> list[dict]:
        return self.alerts.list_deliveries(min(max(limit, 1), 500))
