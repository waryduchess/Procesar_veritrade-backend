from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    agente,
    asistente,
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

app.include_router(health.router)
app.include_router(reportes.router)
app.include_router(importaciones.router)
app.include_router(meta.router)
app.include_router(compras.router)
app.include_router(exportar.router)
app.include_router(procesamiento.router)
app.include_router(asistente.router)
app.include_router(agente.router)
