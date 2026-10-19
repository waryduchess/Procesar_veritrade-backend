from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AgenteIn, AgenteOut
from app.services import agente, llm

router = APIRouter(prefix="/agente", tags=["agente"])


@router.post("/consulta", response_model=AgenteOut)
def consulta(payload: AgenteIn, db: Session = Depends(get_db)) -> dict:
    if not llm.disponible():
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY no está configurada en .env",
        )
    try:
        return agente.consultar(db, payload.pregunta)
    except agente.AgenteLimite as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except agente.AgenteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
