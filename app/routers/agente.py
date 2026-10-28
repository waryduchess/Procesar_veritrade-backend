from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AgenteOut, ConsultaRequest
from app.services import agente, llm

router = APIRouter(prefix="/agente", tags=["agente"])


@router.post("/consulta", response_model=AgenteOut)
def consulta(payload: ConsultaRequest, db: Session = Depends(get_db)) -> dict:
    if not llm.disponible():
        raise HTTPException(
            status_code=503,
            detail=f"{llm.variable_api_key()} no está configurada en .env",
        )
    historial = [m.model_dump() for m in payload.historial] if payload.historial else None
    try:
        return agente.consultar(
            db,
            payload.pregunta,
            historial,
            modulo=payload.modulo,
            modo=payload.modo,
        )
    except agente.AgenteLimite as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except agente.AgenteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
