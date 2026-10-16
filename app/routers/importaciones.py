from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Filtros, Paginacion, get_filtros, get_paginacion
from app.schemas import ImportacionOut, Page
from app.services import consultas
from app.utils.paginacion import construir_page

router = APIRouter(prefix="/importaciones", tags=["importaciones"])


@router.get("", response_model=Page[ImportacionOut])
def listar_importaciones(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
) -> dict:
    stmt = consultas.listar_importaciones(filtros)
    return construir_page(db, stmt, ImportacionOut, pag.page, pag.page_size)


@router.get("/buscar", response_model=Page[ImportacionOut])
def buscar_importaciones(
    q: str = Query(min_length=1, description="Texto a buscar en la descripción comercial"),
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
) -> dict:
    stmt = consultas.listar_importaciones(filtros, q=q)
    return construir_page(db, stmt, ImportacionOut, pag.page, pag.page_size)


@router.get("/{importacion_id}", response_model=ImportacionOut)
def detalle_importacion(
    importacion_id: int,
    db: Session = Depends(get_db),
) -> ImportacionOut:
    obj = consultas.obtener_importacion(db, importacion_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Importación no encontrada")
    return obj
