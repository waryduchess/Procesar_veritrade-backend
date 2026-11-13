from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer(auto_error=False)

MODULO_COMPRAS = "compras"
PERMISOS_COMPRAS = frozenset(
    {"compras.ver", "compras.importar", "compras.exportar"}
)


@dataclass(frozen=True, slots=True)
class AuthContext:
    sub: str
    empresa_id: int
    empresa_clave: str
    roles: tuple[str, ...]
    legacy_role: str | None
    modules: frozenset[str]
    permissions: frozenset[str]
    jti: str


def _error_401(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _error_403(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def _texto(valor: object) -> str:
    return str(valor).strip() if valor is not None else ""


def _conjunto(valor: object) -> frozenset[str]:
    if isinstance(valor, str):
        texto = valor.strip()
        return frozenset({texto}) if texto else frozenset()
    if isinstance(valor, (list, tuple, set, frozenset)):
        return frozenset(
            texto
            for item in valor
            if (texto := _texto(item))
        )
    return frozenset()


def _tupla(valor: object) -> tuple[str, ...]:
    if isinstance(valor, str):
        texto = valor.strip()
        return (texto,) if texto else ()
    if isinstance(valor, (list, tuple, set, frozenset)):
        return tuple(texto for item in valor if (texto := _texto(item)))
    return ()


@lru_cache(maxsize=1)
def _load_public_key() -> str:
    if settings.jwt_public_key.strip():
        return settings.jwt_public_key.replace("\\n", "\n")

    ruta = settings.jwt_public_key_path.strip()
    if not ruta:
        raise RuntimeError(
            "Configura JWT_PUBLIC_KEY o JWT_PUBLIC_KEY_PATH para validar tokens."
        )

    return Path(ruta).read_text(encoding="utf-8")


def _contexto_local() -> AuthContext:
    return AuthContext(
        sub="local-dev",
        empresa_id=settings.empresa_id or 1,
        empresa_clave=settings.empresa_clave or "local",
        roles=("admin",),
        legacy_role="admin",
        modules=frozenset({MODULO_COMPRAS}),
        permissions=PERMISOS_COMPRAS,
        jti="local-dev",
    )


def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthContext:
    if not settings.auth_enabled:
        return _contexto_local()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _error_401("Token de acceso requerido.")

    token = credentials.credentials.strip()
    if not token:
        raise _error_401("Token de acceso requerido.")

    try:
        clave_publica = _load_public_key()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="La autenticación JWT no está configurada.",
        ) from exc

    try:
        payload = jwt.decode(
            token,
            clave_publica,
            algorithms=["RS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=settings.jwt_leeway_seconds,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub", "jti"],
            },
        )
    except jwt.PyJWTError as exc:
        raise _error_401("Token inválido o expirado.") from exc

    sub = _texto(payload.get("sub"))
    jti = _texto(payload.get("jti"))
    if not sub or not jti:
        raise _error_401("Token inválido: faltan claims obligatorios.")

    try:
        empresa_id = int(payload.get("empresa_id", 0))
    except (TypeError, ValueError) as exc:
        raise _error_401("Token inválido: empresa_id no es numérico.") from exc

    empresa_clave = _texto(payload.get("empresa_clave"))

    if settings.empresa_id > 0 and empresa_id != settings.empresa_id:
        raise _error_403("La empresa del token no coincide con la configurada.")

    if settings.empresa_clave and empresa_clave != settings.empresa_clave:
        raise _error_403("La empresa del token no coincide con la configurada.")

    legacy_role = payload.get("legacy_role")
    return AuthContext(
        sub=sub,
        empresa_id=empresa_id,
        empresa_clave=empresa_clave,
        roles=_tupla(payload.get("roles")),
        legacy_role=legacy_role if isinstance(legacy_role, str) else None,
        modules=_conjunto(payload.get("modules")),
        permissions=_conjunto(payload.get("permissions")),
        jti=jti,
    )


def require_module(module: str):
    def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if module not in ctx.modules:
            raise _error_403(f"El módulo {module} no está autorizado.")
        return ctx

    return dependency


def require_permission(permission: str):
    def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if permission not in ctx.permissions:
            raise _error_403(f"El permiso {permission} no está autorizado.")
        return ctx

    return dependency
