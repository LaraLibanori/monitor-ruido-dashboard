# =============================================
# app_routes.py - Endpoints do aplicativo Android
# =============================================
# Só leitura: o app nunca escreve nada no sistema.
# A rota só recebe o pedido e chama o serviço.
# =============================================

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app_service import AppService, HouseNotFound


def build_router(service: AppService) -> APIRouter:
    router = APIRouter(prefix="/api/app", tags=["Aplicativo Android"])

    @router.get("/overview", summary="Tela inicial: silêncio + todas as casas")
    def overview():
        return service.overview()

    @router.get("/houses/{sensor_id}/history", summary="Tela da casa: resumo hora a hora")
    def history(
        sensor_id: str,
        day: str | None = Query(None, description="Dia no formato AAAA-MM-DD (padrão: hoje)"),
    ):
        try:
            parsed_day = date.fromisoformat(day) if day else None
        except ValueError:
            raise HTTPException(status_code=400, detail="Use a data no formato AAAA-MM-DD.")
        try:
            return service.history(sensor_id, parsed_day)
        except HouseNotFound:
            raise HTTPException(status_code=404, detail=f"Casa '{sensor_id}' não encontrada.")

    return router
