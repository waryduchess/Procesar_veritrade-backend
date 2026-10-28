from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
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
    ComparativoOut,
    ImportadorRow,
    KpisOut,
    MatrizOut,
    MensualRow,
    Page,
    PaisOrigenRow,
    PartidaRow,
    ProveedorPaisRow,
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
        consultas.DIM_PROVEEDOR,
        filtros,
        orden.order_by,
        orden.desc,
        extra_where=consultas.SOLO_EXPORTADOR,
    )
    return construir_page(db, stmt, ProveedorRow, pag.page, pag.page_size)


@router.get("/proveedores-por-pais", response_model=Page[ProveedorPaisRow])
def reporte_proveedores_por_pais(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    pag: Paginacion = Depends(get_paginacion),
    orden: Orden = Depends(get_orden),
) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_PROVEEDOR_PAIS,
        filtros,
        orden.order_by,
        orden.desc,
        extra_where=consultas.SOLO_EXPORTADOR,
    )
    return construir_page(db, stmt, ProveedorPaisRow, pag.page, pag.page_size)


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
    solo_principales: bool = Query(
        False, description="Agrupa en Depósito fiscal e Importación definitiva"
    ),
) -> dict:
    stmt = consultas.tipo_importacion_ranking(
        filtros, orden.order_by, orden.desc, solo_principales=solo_principales
    )
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


DimensionComparativo = Literal["partida", "pais_origen", "importador", "exportador"]
MetricaAnalisis = Literal["valor_usd", "volumen_kg"]
OrdenComparativo = Literal["delta_abs", "delta_pp", "valor_actual"]
ColumnaMatriz = Literal["pais_origen", "exportador"]


@router.get("/comparativo", response_model=ComparativoOut)
def reporte_comparativo(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    dimension: DimensionComparativo = Query(
        "partida", description="Dimensión a comparar"
    ),
    mes: Annotated[
        str | None,
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mes YYYY-MM"),
    ] = None,
    comparar: Annotated[
        str | None,
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mes a comparar YYYY-MM"),
    ] = None,
    metrica: MetricaAnalisis = Query("valor_usd", description="Métrica comparada"),
    order_by: OrdenComparativo = Query(
        "delta_abs", description="Criterio de orden del top"
    ),
    top: int = Query(20, ge=1, le=200),
    min_registros: int = Query(5, ge=0, le=10000),
) -> dict:
    data = consultas.comparativo(
        db,
        filtros,
        dimension=dimension,
        mes=mes,
        comparar=comparar,
        metrica=metrica,
        order_by=order_by,
        top=top,
        min_registros=min_registros,
    )
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="No hay datos para el mes o los filtros seleccionados.",
        )
    return data


@router.get("/matriz", response_model=MatrizOut)
def reporte_matriz(
    db: Session = Depends(get_db),
    filtros: Filtros = Depends(get_filtros),
    columna: ColumnaMatriz = Query(
        "pais_origen", description="Dimensión de las columnas"
    ),
    metrica: MetricaAnalisis = Query("valor_usd", description="Métrica de la matriz"),
    top_filas: int = Query(20, ge=1, le=50),
    top_columnas: int = Query(10, ge=1, le=50),
    min_registros: int = Query(3, ge=0, le=10000),
) -> dict:
    return consultas.matriz(
        db,
        filtros,
        columna=columna,
        metrica=metrica,
        top_filas=top_filas,
        top_columnas=top_columnas,
        min_registros=min_registros,
    )
