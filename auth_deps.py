# =============================================
# auth_deps.py - Dependências FastAPI de autenticação
# =============================================
# Uso nas rotas:
#   user = Depends(deps.current_user)   -> qualquer usuário logado
#   user = Depends(deps.admin_user)     -> só administrador
#   user = Depends(deps.app_user)       -> rotas do app (login opcional,
#                                          obrigatório se APP_REQUIRE_AUTH=true)
# =============================================

from dataclasses import dataclass
import os

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_service import AuthService


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "")
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


APP_REQUIRE_AUTH = _env_bool("APP_REQUIRE_AUTH", False)

_bearer = HTTPBearer(auto_error=False, description="Token recebido em /api/auth/login")


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=401, detail=message, headers={"WWW-Authenticate": "Bearer"})


@dataclass
class AuthDeps:
    optional_user: object
    current_user: object
    admin_user: object
    app_user: object
    bearer_token: object


def build_auth_deps(auth: AuthService, require_auth_for_app: bool | None = None) -> AuthDeps:
    def bearer_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str | None:
        if creds is None or creds.scheme.lower() != "bearer":
            return None
        return creds.credentials

    def optional_user(token: str | None = Depends(bearer_token)) -> dict | None:
        if token is None:
            return None
        user = auth.authenticate(token)
        if user is None:
            raise _unauthorized("Sessão inválida ou expirada. Entre novamente.")
        return user

    def current_user(user: dict | None = Depends(optional_user)) -> dict:
        if user is None:
            raise _unauthorized("Faça login para continuar.")
        return user

    def admin_user(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")
        return user

    def app_user(request: Request, user: dict | None = Depends(optional_user)) -> dict | None:
        required = APP_REQUIRE_AUTH if require_auth_for_app is None else require_auth_for_app
        if user is None and required:
            raise _unauthorized("Faça login no aplicativo para ver as casas.")
        return user

    return AuthDeps(optional_user, current_user, admin_user, app_user, bearer_token)


def public_base_url(request: Request) -> str:
    """Endereço usado nos links de convite."""
    configured = os.getenv("PUBLIC_BASE_URL", "").strip()
    return configured or str(request.base_url)
