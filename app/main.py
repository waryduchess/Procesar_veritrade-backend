from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_module, require_permission
from app.config import settings
from app.routers import (
    agente,
    asistente,
    auth,
    compras,
    exportar,
    health,
    importaciones,
    meta,
    procesamiento,
    reportes,
)

app = FastAPI(title="API Veritrade", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCESO_COMPRAS = [
    Depends(require_module("compras")),
    Depends(require_permission("compras.ver")),
]
ACCESO_EXPORTAR = [
    *ACCESO_COMPRAS,
    Depends(require_permission("compras.exportar")),
]

app.include_router(health.router)
app.include_router(auth.router, dependencies=ACCESO_COMPRAS)
app.include_router(reportes.router, dependencies=ACCESO_COMPRAS)
app.include_router(importaciones.router, dependencies=ACCESO_COMPRAS)
app.include_router(meta.router, dependencies=ACCESO_COMPRAS)
app.include_router(compras.router, dependencies=ACCESO_COMPRAS)
app.include_router(exportar.router, dependencies=ACCESO_EXPORTAR)
app.include_router(procesamiento.router, dependencies=ACCESO_COMPRAS)
app.include_router(asistente.router, dependencies=ACCESO_COMPRAS)
app.include_router(agente.router, dependencies=ACCESO_COMPRAS)
