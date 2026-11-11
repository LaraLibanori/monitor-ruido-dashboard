# =============================================
# main.py - FastAPI + PostgreSQL
# =============================================
# Responsabilidades:
#   - Receber dados dos sensores via POST
#   - Rate limiting por sensor
#   - Delegar persistência ao módulo database.py
#   - Servir dashboard HTML e endpoints de leitura
#   - Informar o status da lei do silêncio (fonte única: silence_policy.py)
#   - Incluir as rotas do app Android (app_routes.py)
#   - Login, convites e área do usuário (auth_routes.py)
#   - Painel do administrador (admin_routes.py + templates/admin.html)
#   - Disparar alertas de barulho no horário de silêncio (alert_service.py)
#
# As rotas são "def" (e não "async def") porque o
# psycopg2 é síncrono: assim o FastAPI roda cada uma
# numa thread e o servidor não trava esperando o banco.
# =============================================

from fastapi import BackgroundTasks, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Literal
from contextlib import asynccontextmanager
from collections import defaultdict
import logging
import threading
import time
import os

from database import Database
from silence_policy import policy
from app_service import AppService
from app_routes import build_router
from user_repository import UserRepository
from alert_repository import AlertRepository
from notifications import build_email_provider, build_push_provider
from alert_service import AlertService
from auth_service import AuthService, ServiceError
from auth_deps import build_auth_deps
from auth_routes import build_auth_router
from admin_routes import build_admin_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ---------- CONFIGURAÇÕES ----------
RATE_LIMIT_MAX    = int(os.getenv("RATE_LIMIT_MAX", 100))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))

# Flutter Web uses a random localhost port during development. Keep the
# explicit origins for portless requests and use a restricted regex for the
# variable development ports; credentials are intentionally disabled.
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost,http://127.0.0.1",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

# ---------- RATE LIMITING ----------
# { sensor_id: (count, window_start_ts) }
_rate_store: dict[str, tuple[int, float]] = defaultdict(lambda: (0, time.time()))
_rate_lock = threading.Lock()  # rotas rodam em threads: evita contagem corrompida


def check_rate_limit(sensor_id: str) -> tuple[bool, int, int]:
    """Retorna (permitido, contagem_atual, segundos_restantes)"""
    with _rate_lock:
        return _check_rate_limit_unlocked(sensor_id)


def _check_rate_limit_unlocked(sensor_id: str) -> tuple[bool, int, int]:
    now = time.time()
    count, window_start = _rate_store[sensor_id]

    if now - window_start >= RATE_LIMIT_WINDOW:
        _rate_store[sensor_id] = (1, now)
        return True, 1, RATE_LIMIT_WINDOW

    if count >= RATE_LIMIT_MAX:
        remaining = int(RATE_LIMIT_WINDOW - (now - window_start))
        return False, count, remaining

    _rate_store[sensor_id] = (count + 1, window_start)
    return True, count + 1, int(RATE_LIMIT_WINDOW - (now - window_start))


# ---------- SERVIÇOS ----------
db = Database()
user_repo = UserRepository(db)
email_provider = build_email_provider()
push_provider = build_push_provider()
alert_service = AlertService(AlertRepository(db), user_repo, email_provider, push_provider)
auth_service = AuthService(user_repo, email_provider, alert_service)
auth_deps = build_auth_deps(auth_service)


# ---------- LIFESPAN ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando sistema...")
    db.connect()
    auth_service.load_silence_settings()
    print("📦 Banco de dados pronto!")
    print(f"✉️  E-mail: {email_provider.name} | 📱 Push: {push_provider.name}")
    if user_repo.count_users() == 0:
        print("👤 Nenhum usuário ainda. Crie o administrador: "
              "docker compose exec app python manage.py create-admin")
    yield
    db.disconnect()
    print("🛑 Conexão com banco encerrada.")


# ---------- APP ----------
app = FastAPI(
    title="Monitor de Ruído ESP32",
    description="Sistema IoT com ESP32 + FastAPI + PostgreSQL + Docker",
    version="6.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=False,  # o login usa token Bearer, não cookie
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization"],
)

templates = Jinja2Templates(directory="templates")


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


# Rotas do aplicativo (/api/app/...), login/usuário e administração
app.include_router(build_router(AppService(db), auth_deps.app_user))
app.include_router(build_auth_router(auth_service, alert_service, auth_deps))
app.include_router(build_admin_router(auth_service, alert_service, auth_deps))


# ---------- MODELOS ----------
class NoiseData(BaseModel):
    sensor_id: str = Field(..., min_length=1, max_length=100)
    location: str = Field(..., min_length=1, max_length=200)
    rms: float = Field(..., ge=0)
    noise_level: Literal['baixo', 'medio', 'alto', 'muito_alto']
    sequence: int = Field(..., ge=0)
    device_uptime_ms: int = Field(..., ge=0)


# ---------- ENDPOINTS ----------

@app.post("/api/noise", summary="Recebe leitura de um sensor")
def receive_noise(data: NoiseData, request: Request, background: BackgroundTasks):
    # Rate limit
    allowed, count, remaining = check_rate_limit(data.sensor_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "sensor_id": data.sensor_id,
                "count": count,
                "limit": RATE_LIMIT_MAX,
                "window_seconds": RATE_LIMIT_WINDOW,
                "retry_after_seconds": remaining,
            },
        )

    source_ip = request.client.host if request.client else "unknown"

    reading_id = db.save_reading(data, source_ip)

    # Alerta (se for o caso) depois da resposta: o ESP32 não espera o envio
    if data.noise_level in ("alto", "muito_alto"):
        background.add_task(alert_service.process_reading, reading_id)

    return {
        "status": "success",
        "reading_id": reading_id,
        "rate": {
            "count": count,
            "limit": RATE_LIMIT_MAX,
            "window_seconds": RATE_LIMIT_WINDOW,
        },
    }


@app.get("/api/readings", summary="Últimas 100 leituras")
def get_readings(limit: int = 100):
    return db.get_readings(limit=min(limit, 500))


@app.get("/api/sensors", summary="Lista sensores cadastrados")
def get_sensors():
    return db.get_sensors()


@app.get("/api/rate-status", summary="Status de rate limit por sensor")
def get_rate_status():
    now = time.time()
    result = {}
    with _rate_lock:
        snapshot = list(_rate_store.items())
    for sensor_id, (count, window_start) in snapshot:
        elapsed = now - window_start
        if elapsed < RATE_LIMIT_WINDOW:
            result[sensor_id] = {
                "count": count,
                "limit": RATE_LIMIT_MAX,
                "remaining_in_window": int(RATE_LIMIT_WINDOW - elapsed),
                "percent_used": round(count / RATE_LIMIT_MAX * 100, 1),
            }
    return result


@app.get("/api/silence-status", summary="Lei do silêncio está ativa agora?")
def get_silence_status():
    return policy.status()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    readings = db.get_readings(limit=30)
    return templates.TemplateResponse(
        "index.html", {"request": request, "readings": readings}
    )


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page(request: Request):
    return templates.TemplateResponse(
        "admin.html", {"request": request}, headers={"Cache-Control": "no-store"}
    )


@app.get("/convite", response_class=HTMLResponse, include_in_schema=False)
def invite_page(request: Request):
    # O token do convite está na URL: não vazar por Referer nem cache
    return templates.TemplateResponse(
        "convite.html", {"request": request},
        headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"},
    )


@app.get("/health", summary="Health check")
def health():
    total = db.count_readings()
    return {"status": "ok", "total_readings": total}