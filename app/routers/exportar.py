from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Filtros, Orden, get_filtros, get_orden
from app.services import consultas
from app.utils import exportacion

Formato = Literal["xlsx", "csv"]

router = APIRouter(prefix="/exportar", tags=["exportar"])


def _respuesta(rows, formato: str, nombre: str) -> Response:
    contenido, media_type = exportacion.generar(rows, formato)
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}.{formato}"'},
    )


@router.get("/importadores")
def exportar_importadores(
    formato: Formato = "xlsx",
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    orden: Orden = Depends(get_orden),
) -> Response:
    stmt = consultas.ranking(
        consultas.DIM_IMPORTADOR, filtros, orden.order_by, orden.desc
    )
    rows = db.execute(stmt).mappings().all()
    return _respuesta(rows, formato, "importadores")


@router.get("/proveedores")
def exportar_proveedores(
    formato: Formato = "xlsx",
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    orden: Orden = Depends(get_orden),
) -> Response:
    stmt = consultas.ranking(
        consultas.DIM_PROVEEDOR,
        filtros,
        orden.order_by,
        orden.desc,
        extra_where=consultas.SOLO_EXPORTADOR,
    )
    rows = db.execute(stmt).mappings().all()
    return _respuesta(rows, formato, "proveedores")


@router.get("/importaciones")
def exportar_importaciones(
    formato: Formato = "xlsx",
    q: str | None = None,
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
) -> Response:
    stmt = consultas.listar_importaciones(filtros, q=q)
    rows = db.execute(stmt).mappings().all()
    return _respuesta(rows, formato, "importaciones")
