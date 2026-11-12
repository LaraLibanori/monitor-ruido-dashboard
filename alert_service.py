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
NOISE_CONTINUITY_GAP_SECONDS = int(os.getenv("NOISE_CONTINUITY_GAP_SECONDS", 15))
NOISE_WARNING_SECONDS = int(os.getenv("NOISE_WARNING_SECONDS", 120))
NOISE_FINE_SECONDS = int(os.getenv("NOISE_FINE_SECONDS", 300))
_LEVEL_LABEL = {"alto": "alto", "muito_alto": "muito alto"}


class AlertService:
    def __init__(self, alerts: AlertRepository, users: UserRepository,
                 email_provider=None, push_provider=None,
                 continuity_gap_seconds: int = NOISE_CONTINUITY_GAP_SECONDS,
                 warning_seconds: int = NOISE_WARNING_SECONDS,
                 fine_seconds: int = NOISE_FINE_SECONDS):
        self.alerts = alerts
        self.users = users
        self.email = email_provider or ConsoleEmailProvider()
        self.push = push_provider or ConsolePushProvider()
        self.continuity_gap_seconds = continuity_gap_seconds
        self.warning_seconds = warning_seconds
        self.fine_seconds = fine_seconds

    def providers(self) -> dict:
        return {"email": self.email.name, "push": self.push.name}

    def record_delivery(self, *, user_id, kind, channel, status, provider, detail, alert_event_id=None):
        self.alerts.add_delivery(alert_event_id=alert_event_id, user_id=user_id, kind=kind,
                                 channel=channel, status=status, provider=provider, detail=detail)

    # ---------------------------------------------

    def process_reading(self, reading_id: int) -> int | None:
        """Atualiza a ocorrência contínua e notifica apenas nas transições."""
        try:
            reading = self.alerts.get_reading(reading_id)
            if not reading or not reading["active"]:
                return None
            if not reading["is_silence_period"] or reading["noise_level"] not in ALERT_LEVELS:
                return None
            state = self.alerts.advance_incident(
                reading,
                continuity_gap_seconds=self.continuity_gap_seconds,
                warning_seconds=self.warning_seconds,
                fine_seconds=self.fine_seconds,
            )
            stage = state["transition"]
            if not stage:
                return None
            event_id = self.alerts.create_incident_event(reading, state["incident_id"], stage)
            self._notify(event_id, reading, stage, state["elapsed_seconds"], state["incident_id"])
            return event_id
        except Exception:  # nunca derrubar o recebimento de leituras por causa de aviso
            log.exception("Falha ao processar alerta da leitura %s", reading_id)
            return None

    def _notify(self, event_id: int, reading: dict, stage: str,
                elapsed_seconds: float, incident_id: int) -> None:
        local = policy.to_local(reading["received_at"])
        level = _LEVEL_LABEL.get(reading["noise_level"], reading["noise_level"])
        minutes = round(elapsed_seconds / 60)
        if stage == "fine_candidate":
            title = f"Ocorrência para análise de multa — {reading['house_name']}"
            body = (f"Ruído {level} contínuo por {minutes} minutos às {local:%H:%M} "
                    f"({local:%d/%m}) em {reading['house_name']}. A multa depende de aprovação.")
        else:
            title = f"Advertência de ruído — {reading['house_name']}"
            body = (f"Nível {level} contínuo por {minutes} minutos às {local:%H:%M} "
                    f"({local:%d/%m}) em {reading['house_name']}. Abra o app para acompanhar.")
        data = {"type": "noise_alert", "stage": stage,
                "sensor_id": reading["sensor_id"], "event_id": event_id}
        for user in self.users.recipients_for_sensor(reading["sensor_id"]):
            if stage == "fine_candidate":
                self.alerts.create_fine_candidate(incident_id, user["id"])
            delivery_kind = "alert" if stage == "warning" else "fine_candidate"
            self._deliver(user, title, body, data, kind=delivery_kind, event_id=event_id)

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

    def list_user_deliveries(self, user_id: int, limit: int = 100) -> list[dict]:
        return self.alerts.list_user_deliveries(user_id, limit)

    def create_renovation_request(self, user_id: int, sensor_id: str, starts_at,
                                  ends_at, description: str) -> dict:
        return self.alerts.create_renovation_request(
            user_id, sensor_id, starts_at, ends_at, description
        )

    def list_renovation_requests(self, user_id: int | None = None) -> list[dict]:
        return self.alerts.list_renovation_requests(user_id=user_id)

    def review_renovation_request(self, request_id: int, reviewer_id: int, status: str):
        return self.alerts.review_renovation_request(request_id, reviewer_id, status)

    def list_fines(self) -> list[dict]:
        return self.alerts.list_fines()

    def review_fine(self, fine_id: int, reviewer_id: int, status: str,
                    amount=None, due_date=None, notes: str | None = None):
        return self.alerts.review_fine(fine_id, reviewer_id, status, amount, due_date, notes)
