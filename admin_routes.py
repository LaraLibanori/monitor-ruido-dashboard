# =============================================
# admin_routes.py - Painel do administrador (/api/admin)
# =============================================
# Todas as rotas exigem usuário com papel "admin".
# =============================================

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from alert_service import AlertService
from auth_deps import AuthDeps, public_base_url
from auth_service import AuthService, ServiceError, public_user
from silence_policy import policy


class NotificationsIn(BaseModel):
    email: bool | None = None
    push: bool | None = None


class UserCreateIn(BaseModel):
    name: str = Field(..., max_length=120)
    email: str = Field(..., max_length=254)
    phone: str | None = Field(None, max_length=30)
    role: Literal["admin", "morador"] = "morador"
    sensor_ids: list[str] = Field(default_factory=list, max_length=100)
    notifications: NotificationsIn = Field(default_factory=lambda: NotificationsIn(email=True, push=True))
    invite_channel: Literal["email", "phone"] = "email"


class UserUpdateIn(BaseModel):
    name: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=30)
    role: Literal["admin", "morador"] | None = None
    active: bool | None = None
    sensor_ids: list[str] | None = Field(None, max_length=100)
    notifications: NotificationsIn | None = None


class InviteIn(BaseModel):
    channel: Literal["email", "phone"] = "email"


class SensorCreateIn(BaseModel):
    sensor_id: str = Field(..., max_length=100)
    location: str = Field(..., max_length=200)
    display_name: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=500)


class SensorUpdateIn(BaseModel):
    location: str | None = Field(None, max_length=200)
    display_name: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=500)
    active: bool | None = None


class SilenceIn(BaseModel):
    weekday_start: str = Field(..., max_length=5, examples=["22:00"])
    weekend_start: str = Field(..., max_length=5, examples=["15:00"])
    end: str = Field(..., max_length=5, examples=["09:00"])


class RenovationReviewIn(BaseModel):
    status: Literal["approved", "rejected", "cancelled"]


class FineReviewIn(BaseModel):
    status: Literal["approved", "cancelled", "paid"]
    amount: float | None = Field(None, ge=0)
    due_date: date | None = None
    notes: str | None = Field(None, max_length=1000)


def build_admin_router(auth: AuthService, alerts: AlertService, deps: AuthDeps) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["Administração"])
    admin = Depends(deps.admin_user)

    # ---------------- usuários ----------------

    @router.get("/users", summary="Listar administradores e moradores")
    def list_users(role: Literal["admin", "morador"] | None = None, _=admin):
        return auth.list_users(role)

    @router.post("/users", status_code=201, summary="Cadastrar morador/admin e enviar convite")
    def create_user(body: UserCreateIn, request: Request, actor: dict = admin):
        notifications = body.notifications
        return auth.create_user(
            actor,
            name=body.name, email=body.email, phone=body.phone, role=body.role,
            sensor_ids=body.sensor_ids,
            email_enabled=notifications.email if notifications.email is not None else True,
            push_enabled=notifications.push if notifications.push is not None else True,
            invite_channel=body.invite_channel,
            base_url=public_base_url(request),
        )

    @router.get("/users/{user_id}", summary="Detalhes de um usuário")
    def get_user(user_id: int, _=admin):
        return public_user(auth.get_user(user_id))

    @router.patch("/users/{user_id}", summary="Editar, ativar/desativar, associar casas")
    def update_user(user_id: int, body: UserUpdateIn, actor: dict = admin):
        changes = body.model_dump(exclude_unset=True)
        if "notifications" in changes and changes["notifications"] is not None:
            changes["notifications"] = {k: v for k, v in changes["notifications"].items() if v is not None}
        for key in ("name", "email", "role", "active"):
            if key in changes and changes[key] is None:
                raise ServiceError(422, f"O campo '{key}' não pode ser vazio.")
        return auth.update_user(actor, user_id, changes)

    @router.post("/users/{user_id}/invite", summary="Gerar novo convite (o anterior deixa de valer)")
    def resend_invite(user_id: int, body: InviteIn, request: Request, actor: dict = admin):
        return auth.resend_invite(actor, user_id, body.channel, public_base_url(request))

    @router.post("/users/{user_id}/notifications/test", summary="Enviar notificação de teste")
    def test_notification(user_id: int, actor: dict = admin):
        user = auth.get_user(user_id)
        results = alerts.send_test(user)
        auth.users.add_audit(actor["id"], "notificacao_teste", user["email"], {"results": results})
        return {"providers": alerts.providers(), "results": results}

    # ---------------- sensores / casas ----------------

    @router.get("/sensors", summary="Sensores/casas com moradores vinculados")
    def list_sensors(_=admin):
        return auth.list_sensors()

    @router.post("/sensors", status_code=201, summary="Cadastrar sensor/casa")
    def create_sensor(body: SensorCreateIn, actor: dict = admin):
        return auth.create_sensor(actor, **body.model_dump())

    @router.patch("/sensors/{sensor_id}", summary="Editar sensor/casa")
    def update_sensor(sensor_id: str, body: SensorUpdateIn, actor: dict = admin):
        changes = body.model_dump(exclude_unset=True)
        if "active" in changes and changes["active"] is None:
            raise ServiceError(422, "O campo 'active' não pode ser vazio.")
        return auth.update_sensor(actor, sensor_id, changes)

    @router.get("/sensors/{sensor_id}/recipients", summary="Quem recebe alertas desta casa")
    def recipients(sensor_id: str, _=admin):
        return auth.recipients(sensor_id)

    # ---------------- silêncio, alertas, auditoria ----------------

    @router.get("/settings/silence", summary="Horário de silêncio atual")
    def get_silence(_=admin):
        return policy.rules()

    @router.put("/settings/silence", summary="Alterar horário de silêncio")
    def put_silence(body: SilenceIn, actor: dict = admin):
        return auth.update_silence(actor, **body.model_dump())

    @router.get("/alerts", summary="Alertas recentes e resultado de cada envio")
    def list_alerts(limit: int = 50, _=admin):
        return alerts.list_events(limit)

    @router.get("/deliveries", summary="Últimos envios (alertas, convites e testes)")
    def list_deliveries(limit: int = 100, _=admin):
        return alerts.list_deliveries(limit)

    @router.get("/notifications/status", summary="Provedores de e-mail e push em uso")
    def notification_status(_=admin):
        providers = alerts.providers()
        return {
            "email": providers["email"],
            "push": providers["push"],
            "email_real": providers["email"] == "smtp",
            "push_real": providers["push"] == "fcm",
            "warning_seconds": alerts.warning_seconds,
            "fine_seconds": alerts.fine_seconds,
            "continuity_gap_seconds": alerts.continuity_gap_seconds,
        }

    @router.get("/audit", summary="Auditoria de ações")
    def audit(limit: int = 100, _=admin):
        return auth.audit(limit)

    @router.get("/renovations", summary="Solicitações de reforma")
    def list_renovations(_=admin):
        return alerts.list_renovation_requests()

    @router.patch("/renovations/{request_id}", summary="Aprovar ou rejeitar reforma")
    def review_renovation(request_id: int, body: RenovationReviewIn, actor: dict = admin):
        result = alerts.review_renovation_request(request_id, actor["id"], body.status)
        if result is None:
            raise ServiceError(404, "Solicitação de reforma não encontrada.")
        auth.users.add_audit(actor["id"], "reforma_revisada", str(request_id),
                             {"status": body.status})
        return result

    @router.get("/fines", summary="Candidatas e registros de multa")
    def list_fines(_=admin):
        return alerts.list_fines()

    @router.patch("/fines/{fine_id}", summary="Aprovar, cancelar ou registrar multa paga")
    def review_fine(fine_id: int, body: FineReviewIn, actor: dict = admin):
        result = alerts.review_fine(
            fine_id, actor["id"], body.status, body.amount, body.due_date, body.notes
        )
        if result is None:
            raise ServiceError(404, "Registro de multa não encontrado.")
        auth.users.add_audit(actor["id"], "multa_revisada", str(fine_id),
                             {"status": body.status, "amount": body.amount})
        return result

    return router
