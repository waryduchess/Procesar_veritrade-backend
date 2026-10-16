from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Importacion
from app.schemas import PartidaMeta
from app.services import consultas

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/aduanas", response_model=list[str])
def aduanas(db: Session = Depends(get_db)) -> list[str]:
    return consultas.valores_meta(db, Importacion.aduana)


@router.get("/paises", response_model=list[str])
def paises(db: Session = Depends(get_db)) -> list[str]:
    return consultas.valores_meta(db, Importacion.pais_origen)


@router.get("/partidas", response_model=list[PartidaMeta])
def partidas(db: Session = Depends(get_db)) -> list[dict]:
    return consultas.meta_partidas(db)
