from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ConsultaIn, ConsultaOut, PreguntaOut
from app.services import asistente

router = APIRouter(tags=["asistente"])


@router.get("/preguntas", response_model=list[PreguntaOut])
def listar_preguntas(
    categoria: str | None = Query(None, description="Filtra por categoría"),
) -> list[PreguntaOut]:
    return asistente.listar(categoria)


@router.post("/consulta", response_model=ConsultaOut)
def consulta(payload: ConsultaIn, db: Session = Depends(get_db)) -> dict:
    return asistente.responder(payload.pregunta, db, payload.params)
