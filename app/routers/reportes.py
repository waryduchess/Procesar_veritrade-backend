from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    Filtros,
    Orden,
    Paginacion,
    get_filtros,
    get_orden,
    get_paginacion,
)
from app.models import Importacion
from app.schemas import (
    ImportadorRow,
    KpisOut,
    MensualRow,
    Page,
    PaisOrigenRow,
    PartidaRow,
    ProveedorRow,
    TipoImportacionRow,
)
from app.services import consultas
from app.utils.paginacion import construir_page

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("/importadores", response_model=Page[ImportadorRow])
def reporte_importadores(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_IMPORTADOR, filtros, orden.order_by, orden.desc
    )
    return construir_page(db, stmt, ImportadorRow, pag.page, pag.page_size)


@router.get("/importadores-cancun", response_model=Page[ImportadorRow])
def reporte_importadores_cancun(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_IMPORTADOR,
        filtros,
        orden.order_by,
        orden.desc,
        extra_where=Importacion.es_cancun == 1,
    )
    return construir_page(db, stmt, ImportadorRow, pag.page, pag.page_size)


@router.get("/proveedores", response_model=Page[ProveedorRow])
def reporte_proveedores(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_PROVEEDOR, filtros, orden.order_by, orden.desc
    )
    return construir_page(db, stmt, ProveedorRow, pag.page, pag.page_size)


@router.get("/paises-origen", response_model=Page[PaisOrigenRow])
def reporte_paises_origen(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(consultas.DIM_PAIS, filtros, orden.order_by, orden.desc)
    return construir_page(db, stmt, PaisOrigenRow, pag.page, pag.page_size)


@router.get("/tipo-importacion", response_model=Page[TipoImportacionRow])
def reporte_tipo_importacion(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(consultas.DIM_TIPO, filtros, orden.order_by, orden.desc)
    return construir_page(db, stmt, TipoImportacionRow, pag.page, pag.page_size)


@router.get("/partidas", response_model=Page[PartidaRow])
def reporte_partidas(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_PARTIDA, filtros, orden.order_by, orden.desc
    )
    return construir_page(db, stmt, PartidaRow, pag.page, pag.page_size)


@router.get("/mensual", response_model=Page[MensualRow])
def reporte_mensual(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_MES, filtros, order_by="mes", desc=False
    )
    return construir_page(db, stmt, MensualRow, pag.page, pag.page_size)


@router.get("/kpis", response_model=KpisOut)
def reporte_kpis(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
) -> KpisOut:
    return KpisOut.model_validate(dict(consultas.kpis(db, filtros)))
