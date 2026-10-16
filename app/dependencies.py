from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal

from fastapi import Query


@dataclass
class Filtros:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    aduana: str | None = None
    pais_origen: str | None = None
    partida: str | None = None
    importador: str | None = None
    exportador: str | None = None


def get_filtros(
    fecha_desde: Annotated[date | None, Query(description="Fecha inicial (YYYY-MM-DD)")] = None,
    fecha_hasta: Annotated[date | None, Query(description="Fecha final (YYYY-MM-DD)")] = None,
    aduana: Annotated[str | None, Query(description="Aduana (contiene)")] = None,
    pais_origen: Annotated[str | None, Query(description="País de origen (contiene)")] = None,
    partida: Annotated[str | None, Query(description="Partida arancelaria (contiene)")] = None,
    importador: Annotated[str | None, Query(description="Importador (contiene)")] = None,
    exportador: Annotated[str | None, Query(description="Exportador (contiene)")] = None,
) -> Filtros:
    return Filtros(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        aduana=aduana,
        pais_origen=pais_origen,
        partida=partida,
        importador=importador,
        exportador=exportador,
    )


@dataclass
class Paginacion:
    page: int = 1
    page_size: int = 50


def get_paginacion(
    page: Annotated[int, Query(ge=1, description="Número de página")] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, description="Tamaño de página")] = 50,
    top: Annotated[
        int | None,
        Query(ge=1, le=500, description="Alias de page_size (devuelve la primera página)"),
    ] = None,
) -> Paginacion:
    if top is not None:
        return Paginacion(page=1, page_size=top)
    return Paginacion(page=page, page_size=page_size)


OrderBy = Literal["valor_usd", "volumen_kg", "mes"]


@dataclass
class Orden:
    order_by: OrderBy = "valor_usd"
    desc: bool = True


def get_orden(
    order_by: Annotated[OrderBy, Query(description="Campo de ordenamiento")] = "valor_usd",
    desc: Annotated[bool, Query(description="Orden descendente")] = True,
) -> Orden:
    return Orden(order_by=order_by, desc=desc)
