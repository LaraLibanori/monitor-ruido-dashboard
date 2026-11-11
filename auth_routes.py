# =============================================
# auth_routes.py - Login, convites e área do usuário (/api/auth, /api/me)
# =============================================

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from alert_service import AlertService
from auth_deps import AuthDeps
from auth_service import AuthService, public_user


class LoginIn(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=256)


class AcceptInviteIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., max_length=256)


class MeUpdateIn(BaseModel):
    name: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=30)


class PasswordIn(BaseModel):
    current_password: str = Field(..., max_length=256)
    new_password: str = Field(..., max_length=256)


class PreferencesIn(BaseModel):
    email: bool | None = None
    push: bool | None = None


class DeviceIn(BaseModel):
    token: str = Field(..., max_length=4096)
    platform: Literal["android", "ios", "web"]


class DeviceDeleteIn(BaseModel):
    token: str = Field(..., max_length=4096)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def build_auth_router(auth: AuthService, alerts: AlertService, deps: AuthDeps) -> APIRouter:
    router = APIRouter(tags=["Acesso e usuário"])

    # ---------------- /api/auth ----------------

    @router.post("/api/auth/login", summary="Entrar com e-mail e senha")
    def login(body: LoginIn, request: Request):
        return auth.login(body.email, body.password, _client_ip(request))

    @router.post("/api/auth/logout", status_code=204, summary="Sair (revoga o token atual)")
    def logout(token: str | None = Depends(deps.bearer_token), _user=Depends(deps.current_user)):
        auth.logout(token)
        return Response(status_code=204)

    @router.get("/api/auth/me", summary="Quem está logado")
    def me(user: dict = Depends(deps.current_user)):
        data = public_user(user)
        data["session_expires_at"] = user["session_expires_at"]
        return data

    @router.get("/api/auth/invites/{token}", summary="Dados do convite (tela de ativação)")
    def invite_info(token: str):
        return auth.invite_info(token)

    @router.post("/api/auth/invites/accept", summary="Aceitar convite e criar senha")
    def accept_invite(body: AcceptInviteIn):
        return auth.accept_invite(body.token, body.password)

    # ---------------- /api/me ----------------

    @router.patch("/api/me", summary="Atualizar nome/telefone")
    def update_me(body: MeUpdateIn, user: dict = Depends(deps.current_user)):
        return auth.update_me(user, body.model_dump(exclude_unset=True))

    @router.post("/api/me/password", status_code=204, summary="Trocar senha (encerra as sessões)")
    def change_password(body: PasswordIn, user: dict = Depends(deps.current_user)):
        auth.change_password(user, body.current_password, body.new_password)
        return Response(status_code=204)

    @router.get("/api/me/preferences", summary="Minhas preferências de notificação")
    def get_preferences(user: dict = Depends(deps.current_user)):
        return public_user(user)["notifications"]

    @router.put("/api/me/preferences", summary="Ligar/desligar e-mail e push")
    def set_preferences(body: PreferencesIn, user: dict = Depends(deps.current_user)):
        return auth.set_preferences(user, email=body.email, push=body.push)

    @router.post("/api/me/devices", status_code=204, summary="Registrar token FCM do aparelho")
    def register_device(body: DeviceIn, user: dict = Depends(deps.current_user)):
        auth.register_device(user, body.token, body.platform)
        return Response(status_code=204)

    @router.post("/api/me/devices/remove", status_code=204, summary="Remover token do aparelho (logout)")
    def remove_device(body: DeviceDeleteIn, user: dict = Depends(deps.current_user)):
        auth.remove_device(user, body.token)
        return Response(status_code=204)

    @router.get("/api/me/alerts", summary="Alertas recentes das minhas casas")
    def my_alerts(limit: int = 30, user: dict = Depends(deps.current_user)):
        events = alerts.list_events(limit, auth.allowed_sensor_ids(user))
        for event in events:  # cada um vê só os próprios envios
            event["deliveries"] = [d for d in event["deliveries"] if d["user_id"] == user["id"]]
        return events

    @router.post("/api/me/notifications/test", summary="Enviar notificação de teste para mim")
    def test_me(user: dict = Depends(deps.current_user)):
        return {"providers": alerts.providers(), "results": alerts.send_test(user)}

    return router
