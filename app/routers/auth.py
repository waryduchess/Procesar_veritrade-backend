from fastapi import APIRouter, Depends

from app.auth import AuthContext, get_auth_context

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    return {
        "sub": ctx.sub,
        "empresa_id": ctx.empresa_id,
        "empresa_clave": ctx.empresa_clave,
        "roles": list(ctx.roles),
        "legacy_role": ctx.legacy_role,
        "modules": sorted(ctx.modules),
        "permissions": sorted(ctx.permissions),
        "jti": ctx.jti,
    }
