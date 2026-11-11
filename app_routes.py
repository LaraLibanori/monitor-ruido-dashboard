# =============================================
# app_routes.py - Endpoints do aplicativo Android
# =============================================
# Só leitura. A rota só recebe o pedido e chama o serviço.
# Com login (token Bearer), o morador vê apenas as casas dele;
# o administrador vê todas. Sem login, as rotas continuam abertas
# para manter compatibilidade, a não ser que APP_REQUIRE_AUTH=true.
# =============================================

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app_service import AppService, HouseNotFound
from auth_service import AuthService


def build_router(service: AppService, app_user=None) -> APIRouter:
    router = APIRouter(prefix="/api/app", tags=["Aplicativo Android"])
    user_dep = Depends(app_user) if app_user else Depends(lambda: None)

    @router.get("/overview", summary="Tela inicial: silêncio + casas autorizadas")
    def overview(user: dict | None = user_dep):
        return service.overview(AuthService.allowed_sensor_ids(user))

    @router.get("/houses/{sensor_id}/history", summary="Tela da casa: resumo hora a hora")
    def history(
        sensor_id: str,
        day: str | None = Query(None, description="Dia no formato AAAA-MM-DD (padrão: hoje)"),
        user: dict | None = user_dep,
    ):
        try:
            parsed_day = date.fromisoformat(day) if day else None
        except ValueError:
            raise HTTPException(status_code=400, detail="Use a data no formato AAAA-MM-DD.")
        try:
            return service.history(sensor_id, parsed_day, AuthService.allowed_sensor_ids(user))
        except HouseNotFound:
            raise HTTPException(status_code=404, detail=f"Casa '{sensor_id}' não encontrada.")

    return router
