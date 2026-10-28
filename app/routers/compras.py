from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.dependencies import (
    FiltrosCompras,
    OrdenComprasParams,
    Paginacion,
    get_filtros_compras,
    get_orden_compras,
    get_paginacion,
)
from app.schemas import (
    ComparativoOut,
    CompraArticuloOut,
    CompraCategoriaRow,
    CompraMensualRow,
    CompraPrecioMensualRow,
    CompraPrecioProductoRow,
    CompraProveedorRow,
    ComprasImportOut,
    ComprasKpisOut,
    ComprasMetaOut,
    Page,
)
from app.services import compras as compras_service
from app.services import consultas_compras
from app.utils import exportacion
from app.utils.paginacion import construir_page

router = APIRouter(prefix="/compras", tags=["compras"])

Formato = Literal["xlsx", "csv"]
ModoCarga = Literal["reemplazar", "agregar"]
DimensionComparativo = Literal["descripcion", "categoria", "proveedor"]
MetricaComparativo = Literal["importe_mxn", "cantidad", "precio_promedio_mxn"]
OrdenComparativo = Literal["delta_abs", "delta_pp", "valor_actual"]


@router.get("/kpis", response_model=ComprasKpisOut)
def compras_kpis(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
) -> dict:
    return dict(consultas_compras.kpis(db, filtros))


@router.get("/precios", response_model=list[CompraPrecioProductoRow])
def compras_precios(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    anio: int | None = Query(None, ge=2000, le=2100),
    top: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return consultas_compras.precios(db, filtros, anio=anio, top=top)


@router.get("/precios/mensual", response_model=list[CompraPrecioMensualRow])
def compras_precios_mensual(
    descripcion: Annotated[str, Query(min_length=1, max_length=500)],
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    anio: int | None = Query(None, ge=2000, le=2100),
) -> list[dict]:
    return consultas_compras.precios_mensual(
        db, filtros, descripcion=descripcion, anio=anio
    )


@router.get("/comparativo", response_model=ComparativoOut)
def compras_comparativo(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    dimension: DimensionComparativo = Query(
        "descripcion", description="Dimensión a comparar"
    ),
    mes: Annotated[
        str | None,
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mes YYYY-MM"),
    ] = None,
    comparar: Annotated[
        str | None,
        Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mes a comparar YYYY-MM"),
    ] = None,
    metrica: MetricaComparativo = Query(
        "importe_mxn", description="Métrica comparada"
    ),
    order_by: OrdenComparativo = Query(
        "delta_abs", description="Criterio de orden del top"
    ),
    top: int = Query(20, ge=1, le=200),
    min_registros: int = Query(3, ge=0, le=10000),
) -> dict:
    data = consultas_compras.comparativo(
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


@router.get("/mensual", response_model=list[CompraMensualRow])
def compras_mensual(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
) -> list[dict]:
    return consultas_compras.mensual(db, filtros)


@router.get("/categorias", response_model=list[CompraCategoriaRow])
def compras_categorias(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    top: int = Query(20, ge=1, le=500),
) -> list[dict]:
    return consultas_compras.categorias(db, filtros, top=top)


@router.get("/proveedores", response_model=list[CompraProveedorRow])
def compras_proveedores(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    top: int = Query(15, ge=1, le=500),
) -> list[dict]:
    return consultas_compras.proveedores(db, filtros, top=top)


@router.get("/meta", response_model=ComprasMetaOut)
def compras_meta(db: Session = Depends(get_db)) -> dict:
    return consultas_compras.meta(db)


@router.get("/articulos", response_model=Page[CompraArticuloOut])
def compras_articulos(
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    pag: Paginacion = Depends(get_paginacion),
    orden: OrdenComprasParams = Depends(get_orden_compras),
) -> dict:
    stmt = consultas_compras.listar_compras(
        filtros, order_by=orden.order_by, desc=orden.desc
    )
    return construir_page(db, stmt, CompraArticuloOut, pag.page, pag.page_size)


@router.get("/exportar")
def compras_exportar(
    formato: Formato = "xlsx",
    db: Session = Depends(get_db),
    filtros: FiltrosCompras = Depends(get_filtros_compras),
    orden: OrdenComprasParams = Depends(get_orden_compras),
) -> Response:
    stmt = consultas_compras.listar_compras(
        filtros, order_by=orden.order_by, desc=orden.desc
    )
    rows = db.execute(stmt).mappings().all()
    contenido, media_type = exportacion.generar(rows, formato)
    return Response(
        content=contenido,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="compras.{formato}"'
        },
    )


@router.post("/importar", response_model=ComprasImportOut)
async def compras_importar(
    archivo: UploadFile = File(...),
    modo: ModoCarga = Query("reemplazar"),
) -> dict:
    nombre_original = archivo.filename or "compras.csv"
    if Path(nombre_original).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=422, detail="El archivo debe tener extensión .csv."
        )

    contenido = await archivo.read()
    await archivo.close()
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo CSV está vacío.")
    if len(contenido) > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail="El archivo supera el límite de 20 MB."
        )

    compras_service.DIR_COPIAS.mkdir(parents=True, exist_ok=True)
    nombre_seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(nombre_original).name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = compras_service.DIR_COPIAS / f"{timestamp}_{nombre_seguro}"
    destino.write_bytes(contenido)

    try:
        detalle = compras_service.cargar(
            destino,
            engine,
            reemplazar=modo == "reemplazar",
            guardar_copia=False,
            archivo_origen=nombre_original,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    detalle["copia"] = str(destino)
    return detalle
