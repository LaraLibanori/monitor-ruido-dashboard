# =============================================
# security.py - Senhas e tokens
# =============================================
# - Senhas: scrypt (biblioteca padrão do Python), com sal aleatório.
# - Tokens de sessão/convite: aleatórios; no banco guardamos só um
#   HMAC-SHA256 do token (com SECRET_KEY). Quem lê o banco não
#   consegue usar os tokens.
# =============================================

import base64
import hashlib
import hmac
import logging
import os
import secrets

log = logging.getLogger("monitor.security")

MIN_PASSWORD_LENGTH = 8

# Custo do scrypt. Os testes podem reduzir via variável de ambiente.
_SCRYPT_N = int(os.getenv("PASSWORD_SCRYPT_N", 2**14))
_SCRYPT_R = 8
_SCRYPT_P = 1

_secret = os.getenv("SECRET_KEY", "")
if not _secret:
    # Sem SECRET_KEY o sistema funciona, mas as sessões caem a cada reinício.
    _secret = secrets.token_urlsafe(48)
    log.warning(
        "SECRET_KEY não definida: usando chave temporária. "
        "Defina SECRET_KEY no .env para manter as sessões após reiniciar."
    )
_SECRET_BYTES = _secret.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(password) > 256:
        raise ValueError("A senha pode ter no máximo 256 caracteres.")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not isinstance(password, str):
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    """Token aleatório para sessão ou convite (vai só para o usuário)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """O que fica salvo no banco no lugar do token."""
    return hmac.new(_SECRET_BYTES, token.encode("utf-8"), hashlib.sha256).hexdigest()
