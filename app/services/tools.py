from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import Filtros
from app.models import Importacion
from app.schemas import (
    ImportacionOut,
    ImportadorRow,
    KpisOut,
    MensualRow,
    PaisOrigenRow,
    PartidaMeta,
    PartidaRow,
    ProveedorPaisRow,
    ProveedorRow,
    TipoImportacionRow,
)
from app.services import consultas
from app.utils.paginacion import construir_page

_FILTROS = {
    "fecha_desde": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
    "fecha_hasta": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
    "aduana": {"type": ["string", "null"], "description": "Contiene"},
    "pais_origen": {"type": ["string", "null"], "description": "Contiene"},
    "partida": {
        "type": ["string", "null"],
        "description": "Fracción/producto. El porcentaje se calcula sobre el total de ese producto.",
    },
    "importador": {"type": ["string", "null"], "description": "Contiene"},
    "exportador": {"type": ["string", "null"], "description": "Contiene"},
}

_ORDEN = {
    "order_by": {
        "type": ["string", "null"],
        "enum": ["valor_usd", "volumen_kg", None],
        "description": "Métrica de orden (default valor_usd)",
    },
    "top": {
        "type": ["integer", "null"],
        "description": "Filas a devolver (default 10, máximo 50)",
    },
}

_DIMENSIONES = {
    "importadores": (consultas.DIM_IMPORTADOR, ImportadorRow, None),
    "importadores_cancun": (
        consultas.DIM_IMPORTADOR,
        ImportadorRow,
        Importacion.es_cancun == 1,
    ),
    "proveedores": (consultas.DIM_PROVEEDOR, ProveedorRow, consultas.SOLO_EXPORTADOR),
    "proveedores_por_pais": (
        consultas.DIM_PROVEEDOR_PAIS,
        ProveedorPaisRow,
        consultas.SOLO_EXPORTADOR,
    ),
    "paises_origen": (consultas.DIM_PAIS, PaisOrigenRow, None),
    "partidas": (consultas.DIM_PARTIDA, PartidaRow, None),
}


@dataclass(frozen=True)
class Tool:
    definition: dict
    handler: Callable[[Session, dict], Any]


def _tool(
    name: str,
    description: str,
    handler: Callable[[Session, dict], Any],
    properties: dict,
    required: list[str] | None = None,
) -> Tool:
    return Tool(
        definition={
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                },
            },
        },
        handler=handler,
    )


def _fecha(valor) -> date | None:
    if isinstance(valor, str) and valor:
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return None
    return None


def _filtros(args: dict) -> Filtros:
    return Filtros(
        fecha_desde=_fecha(args.get("fecha_desde")),
        fecha_hasta=_fecha(args.get("fecha_hasta")),
        aduana=args.get("aduana"),
        pais_origen=args.get("pais_origen"),
        partida=args.get("partida"),
        importador=args.get("importador"),
        exportador=args.get("exportador"),
    )


def _top(args: dict) -> int:
    try:
        valor = int(args.get("top") or settings.agente_top_default)
    except (TypeError, ValueError):
        valor = settings.agente_top_default
    return max(1, min(valor, settings.agente_top_max))


def _order_by(args: dict) -> str:
    valor = args.get("order_by", "valor_usd")
    return valor if valor in ("valor_usd", "volumen_kg") else "valor_usd"


def _pagina(db: Session, stmt, modelo, page_size: int) -> dict:
    pagina = construir_page(db, stmt, modelo, 1, page_size)
    return {
        "items": [item.model_dump(mode="json") for item in pagina["items"]],
        "total": pagina["total"],
    }


def _resumen_kpis(db: Session, args: dict) -> dict:
    datos = KpisOut.model_validate(dict(consultas.kpis(db, _filtros(args))))
    return datos.model_dump(mode="json")


def _ranking(db: Session, args: dict) -> dict:
    dimension = args.get("dimension")
    filtros = _filtros(args)
    orden = _order_by(args)
    top = _top(args)

    if dimension == "tipo_importacion":
        stmt = consultas.tipo_importacion_ranking(
            filtros,
            orden,
            True,
            solo_principales=bool(args.get("solo_principales", False)),
        )
        return _pagina(db, stmt, TipoImportacionRow, top)

    if dimension not in _DIMENSIONES:
        return {
            "error": f"dimension inválida: {dimension}. Usa una del enum."
        }

    dim, modelo, extra = _DIMENSIONES[dimension]
    stmt = consultas.ranking(dim, filtros, orden, True, extra_where=extra)
    return _pagina(db, stmt, modelo, top)


def _serie_mensual(db: Session, args: dict) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_MES, _filtros(args), order_by="mes", desc=False
    )
    return _pagina(db, stmt, MensualRow, _top(args))


def _buscar(db: Session, args: dict) -> dict:
    q = (args.get("q") or "").strip()
    if not q:
        return {"error": "Falta q (texto a buscar)."}
    stmt = consultas.listar_importaciones(_filtros(args), q=q)
    return _pagina(db, stmt, ImportacionOut, _top(args))


def _catalogo(db: Session, args: dict) -> dict:
    tipo = args.get("tipo")
    if tipo == "aduanas":
        return {"items": consultas.valores_meta(db, Importacion.aduana)}
    if tipo == "paises":
        return {"items": consultas.valores_meta(db, Importacion.pais_origen)}
    if tipo == "partidas":
        return {
            "items": [
                PartidaMeta.model_validate(f).model_dump(mode="json")
                for f in consultas.meta_partidas(db)
            ]
        }
    return {"error": "tipo debe ser aduanas, paises o partidas."}


TOOLS: dict[str, Tool] = {
    t.definition["function"]["name"]: t
    for t in [
        _tool(
            "resumen_kpis",
            "Totales del conjunto filtrado: valor USD, volumen KG, operaciones, costo unitario, nº de importadores/exportadores/partidas/países.",
            _resumen_kpis,
            dict(_FILTROS),
        ),
        _tool(
            "ranking",
            "Ranking agregado. Devuelve items con valor_usd, volumen_kg, registros, costo_unit_ponderado, pct_total (% valor), pct_acumulado (Pareto valor) y porcentaje (% volumen). Elige la dimension.",
            _ranking,
            {
                "dimension": {
                    "type": "string",
                    "enum": [
                        "importadores",
                        "importadores_cancun",
                        "proveedores",
                        "proveedores_por_pais",
                        "paises_origen",
                        "partidas",
                        "tipo_importacion",
                    ],
                },
                **_FILTROS,
                **_ORDEN,
                "solo_principales": {
                    "type": ["boolean", "null"],
                    "description": "Solo para tipo_importacion: agrupa en Depósito fiscal e Importación definitiva",
                },
            },
            required=["dimension"],
        ),
        _tool(
            "serie_mensual",
            "Serie mensual (mes YYYY-MM) con valor_usd, volumen_kg, registros y costo_unit_ponderado.",
            _serie_mensual,
            dict(_FILTROS),
        ),
        _tool(
            "buscar_operaciones",
            "Busca operaciones por texto en la descripción comercial. Requiere q.",
            _buscar,
            {**_FILTROS, "q": {"type": "string", "description": "Texto a buscar"}},
            required=["q"],
        ),
        _tool(
            "catalogo",
            "Catálogo de aduanas, países o partidas.",
            _catalogo,
            {
                "tipo": {
                    "type": "string",
                    "enum": ["aduanas", "paises", "partidas"],
                }
            },
            required=["tipo"],
        ),
    ]
}

TOOL_DEFINITIONS = [t.definition for t in TOOLS.values()]
