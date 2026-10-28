from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import Filtros, FiltrosCompras
from app.models import Importacion
from app.schemas import (
    ComparativoOut,
    CompraArticuloOut,
    CompraCategoriaRow,
    CompraMensualRow,
    CompraPrecioMensualRow,
    CompraPrecioProductoRow,
    CompraProveedorRow,
    ComprasKpisOut,
    ComprasMetaOut,
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
from app.services import consultas, consultas_compras
from app.utils.paginacion import construir_page

ENDPOINTS_FILE = Path(__file__).resolve().parent.parent / "data" / "api_endpoints.json"

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

_FILTROS_COMPRAS = {
    "fecha_desde": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
    "fecha_hasta": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
    "categoria": {
        "type": ["string", "null"],
        "description": "Categoría exacta; usa 'Sin categoría' para las vacías",
    },
    "proveedor": {"type": ["string", "null"], "description": "Contiene"},
    "descripcion": {
        "type": ["string", "null"],
        "description": "Descripción exacta del artículo",
    },
    "ambito": {
        "type": ["string", "null"],
        "enum": ["nacional", "internacional", None],
        "description": "Ámbito de la compra",
    },
    "fraccion": {"type": ["string", "null"], "description": "Fracción exacta"},
    "q": {
        "type": ["string", "null"],
        "description": "Busca en descripción, proveedor o fracción; no busca en categoría",
    },
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

_DIMENSIONES_COMPARATIVO_IMPORTACIONES = (
    "partida",
    "pais_origen",
    "importador",
    "exportador",
)
_DIMENSIONES_COMPARATIVO_COMPRAS = ("descripcion", "categoria", "proveedor")

_TABS_SUGERIDOS = {
    "importaciones": (
        "resumen",
        "importadores",
        "proveedores",
        "productos",
        "comparativo",
        "matriz",
        "operaciones",
        "preguntas",
    ),
    "compras": ("graficas", "precios", "comparativo", "tabla"),
}

_CLAVES_FILTROS_SUGERIDOS = {
    "importaciones": (
        "fecha_desde",
        "fecha_hasta",
        "aduana",
        "pais_origen",
        "partida",
        "importador",
        "exportador",
    ),
    "compras": (
        "fecha_desde",
        "fecha_hasta",
        "categoria",
        "proveedor",
        "descripcion",
        "ambito",
        "fraccion",
        "q",
    ),
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


def _texto(args: dict, clave: str) -> str | None:
    valor = args.get(clave)
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return None


def _filtros(args: dict) -> Filtros:
    return Filtros(
        fecha_desde=_fecha(args.get("fecha_desde")),
        fecha_hasta=_fecha(args.get("fecha_hasta")),
        aduana=_texto(args, "aduana"),
        pais_origen=_texto(args, "pais_origen"),
        partida=_texto(args, "partida"),
        importador=_texto(args, "importador"),
        exportador=_texto(args, "exportador"),
    )


def _filtros_compras(args: dict) -> FiltrosCompras:
    ambito = _texto(args, "ambito")
    if ambito not in ("nacional", "internacional"):
        ambito = None
    return FiltrosCompras(
        fecha_desde=_fecha(args.get("fecha_desde")),
        fecha_hasta=_fecha(args.get("fecha_hasta")),
        categoria=_texto(args, "categoria"),
        proveedor=_texto(args, "proveedor"),
        descripcion=_texto(args, "descripcion"),
        ambito=ambito,
        fraccion=_texto(args, "fraccion"),
        q=_texto(args, "q"),
    )


def _top(args: dict) -> int:
    try:
        valor = int(args.get("top") or settings.agente_top_default)
    except (TypeError, ValueError):
        valor = settings.agente_top_default
    return max(1, min(valor, settings.agente_top_max))


def _anio(args: dict) -> int | None:
    try:
        valor = int(args.get("anio"))
    except (TypeError, ValueError):
        return None
    return valor if 2000 <= valor <= 2100 else None


def _entero(args: dict, clave: str, default: int, minimo: int = 0, maximo: int = 10000) -> int:
    try:
        valor = int(args.get(clave))
    except (TypeError, ValueError):
        return default
    return max(minimo, min(valor, maximo))


def _opcion(args: dict, clave: str, opciones: tuple[str, ...], default: str) -> str:
    valor = _texto(args, clave)
    return valor if valor in opciones else default


def _order_by(args: dict) -> str:
    valor = args.get("order_by", "valor_usd")
    return valor if valor in ("valor_usd", "volumen_kg") else "valor_usd"


def _modelo(modelo, fila: dict) -> dict:
    return modelo.model_validate(dict(fila)).model_dump(mode="json")


def _modelos(modelo, filas: list[dict]) -> list[dict]:
    return [_modelo(modelo, fila) for fila in filas]


def _pagina(db: Session, stmt, modelo, page_size: int) -> dict:
    pagina = construir_page(db, stmt, modelo, 1, page_size)
    return {
        "items": [item.model_dump(mode="json") for item in pagina["items"]],
        "total": pagina["total"],
    }


@lru_cache(maxsize=1)
def _endpoints() -> dict:
    return json.loads(ENDPOINTS_FILE.read_text(encoding="utf-8"))


def _resumen_kpis(db: Session, args: dict) -> dict:
    return _modelo(KpisOut, consultas.kpis(db, _filtros(args)))


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
        return {"error": f"dimension inválida: {dimension}. Usa una del enum."}

    dim, modelo, extra = _DIMENSIONES[dimension]
    stmt = consultas.ranking(dim, filtros, orden, True, extra_where=extra)
    return _pagina(db, stmt, modelo, top)


def _serie_mensual(db: Session, args: dict) -> dict:
    stmt = consultas.ranking(
        consultas.DIM_MES, _filtros(args), order_by="mes", desc=False
    )
    return _pagina(db, stmt, MensualRow, _top(args))


def _buscar(db: Session, args: dict) -> dict:
    q = _texto(args, "q")
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


def _comparativo_importaciones(db: Session, args: dict) -> dict:
    data = consultas.comparativo(
        db,
        _filtros(args),
        dimension=_opcion(
            args,
            "dimension",
            _DIMENSIONES_COMPARATIVO_IMPORTACIONES,
            "partida",
        ),
        mes=_texto(args, "mes"),
        comparar=_texto(args, "comparar"),
        metrica=_opcion(args, "metrica", ("valor_usd", "volumen_kg"), "valor_usd"),
        order_by=_opcion(
            args,
            "order_by",
            ("delta_abs", "delta_pp", "valor_actual"),
            "delta_abs",
        ),
        top=_top(args),
        min_registros=_entero(args, "min_registros", 5),
    )
    if data is None:
        return {"encontrado": False, "items": [], "total_items": 0}
    return ComparativoOut.model_validate(data).model_dump(mode="json")


def _compras_kpis(db: Session, args: dict) -> dict:
    return _modelo(ComprasKpisOut, consultas_compras.kpis(db, _filtros_compras(args)))


def _compras_ranking(db: Session, args: dict) -> dict:
    dimension = _opcion(args, "dimension", ("categorias", "proveedores"), "proveedores")
    filtros = _filtros_compras(args)
    top = _top(args)
    if dimension == "categorias":
        filas = consultas_compras.categorias(db, filtros, top=top)
        return {"items": _modelos(CompraCategoriaRow, filas), "total": len(filas)}
    filas = consultas_compras.proveedores(db, filtros, top=top)
    return {"items": _modelos(CompraProveedorRow, filas), "total": len(filas)}


def _compras_mensual(db: Session, args: dict) -> dict:
    filas = consultas_compras.mensual(db, _filtros_compras(args))
    return {"items": _modelos(CompraMensualRow, filas), "total": len(filas)}


def _compras_precio_producto(db: Session, args: dict) -> dict:
    filtros = _filtros_compras(args)
    descripcion = _texto(args, "descripcion")
    q = _texto(args, "q")
    anio = _anio(args)
    top = _top(args)

    if descripcion:
        filtros_exactos = replace(filtros, q=None)
        filas = consultas_compras.precios(
            db, filtros_exactos, anio=anio, top=500
        )
        objetivo = descripcion.casefold()
        fila = next(
            (
                item
                for item in filas
                if str(item["descripcion"]).casefold() == objetivo
            ),
            None,
        )
        if fila is None:
            filtros_busqueda = replace(
                filtros,
                q=q or descripcion,
            )
            coincidencias = consultas_compras.precios(
                db, filtros_busqueda, anio=anio, top=top
            )
            return {
                "encontrado": False,
                "descripcion": descripcion,
                "items": _modelos(CompraPrecioProductoRow, coincidencias),
                "total": len(coincidencias),
            }
        mensual = consultas_compras.precios_mensual(
            db,
            filtros_exactos,
            descripcion=fila["descripcion"],
            anio=fila["anio"],
        )
        return {
            "encontrado": True,
            "producto": _modelo(CompraPrecioProductoRow, fila),
            "mensual": _modelos(CompraPrecioMensualRow, mensual),
            "unidad": "MXN por unidad capturada",
        }

    if q:
        filtros_busqueda = replace(filtros, q=q)
        filas = consultas_compras.precios(
            db, filtros_busqueda, anio=anio, top=top
        )
        return {
            "encontrado": bool(filas),
            "items": _modelos(CompraPrecioProductoRow, filas),
            "total": len(filas),
            "nota": "Si hay varias descripciones, pide al usuario que elija antes de concluir.",
        }

    return {"error": "Falta q (búsqueda) o descripcion (producto exacto)."}


def _compras_comparativo(db: Session, args: dict) -> dict:
    data = consultas_compras.comparativo(
        db,
        _filtros_compras(args),
        dimension=_opcion(
            args,
            "dimension",
            _DIMENSIONES_COMPARATIVO_COMPRAS,
            "descripcion",
        ),
        mes=_texto(args, "mes"),
        comparar=_texto(args, "comparar"),
        metrica=_opcion(
            args,
            "metrica",
            ("importe_mxn", "cantidad", "precio_promedio_mxn"),
            "importe_mxn",
        ),
        order_by=_opcion(
            args,
            "order_by",
            ("delta_abs", "delta_pp", "valor_actual"),
            "delta_abs",
        ),
        top=_top(args),
        min_registros=_entero(args, "min_registros", 3),
    )
    if data is None:
        return {"encontrado": False, "items": [], "total_items": 0}
    return ComparativoOut.model_validate(data).model_dump(mode="json")


def _compras_buscar(db: Session, args: dict) -> dict:
    q = _texto(args, "q")
    if not q:
        return {"error": "Falta q (texto a buscar)."}
    filtros = _filtros_compras(args)
    stmt = consultas_compras.listar_compras(filtros)
    return _pagina(db, stmt, CompraArticuloOut, _top(args))


def _compras_catalogo(db: Session, args: dict) -> dict:
    tipo = _texto(args, "tipo") or "todo"
    if tipo == "descripciones":
        filas = consultas_compras.precios(
            db,
            _filtros_compras(args),
            anio=_anio(args),
            top=_top(args),
        )
        return {
            "tipo": tipo,
            "items": _modelos(CompraPrecioProductoRow, filas),
            "total": len(filas),
        }
    data = ComprasMetaOut.model_validate(consultas_compras.meta(db))
    if tipo == "todo":
        return data.model_dump(mode="json")
    claves = {
        "categorias": "categorias",
        "proveedores": "proveedores",
        "fracciones": "fracciones",
        "anios": "anios",
        "ambitos": "ambitos",
    }
    if tipo not in claves:
        return {
            "error": "tipo debe ser categorias, proveedores, fracciones, anios, ambitos, descripciones o todo."
        }
    return {
        "tipo": tipo,
        "items": data.model_dump(mode="json")[claves[tipo]],
    }


def _pedir_aclaracion(db: Session, args: dict) -> dict:
    pregunta = _texto(args, "pregunta")
    if not pregunta:
        return {"error": "Falta pregunta de aclaración."}
    opciones = args.get("opciones") or []
    if isinstance(opciones, str):
        opciones = [opciones]
    if not isinstance(opciones, list):
        opciones = []
    return {
        "aclaracion": pregunta,
        "opciones": [str(opcion) for opcion in opciones[:10]],
    }


def _sugerir_filtros(db: Session, args: dict) -> dict:
    modulo = _texto(args, "modulo")
    if modulo not in ("importaciones", "compras"):
        return {"error": "modulo debe ser importaciones o compras."}

    tab = _texto(args, "tab")
    tabs = _TABS_SUGERIDOS[modulo]
    if tab not in tabs:
        tab = "graficas" if modulo == "compras" else "resumen"

    raw = args.get("filtros")
    if not isinstance(raw, dict):
        raw = {}

    claves = _CLAVES_FILTROS_SUGERIDOS[modulo]
    filtros = {
        clave: str(valor).strip()
        for clave, valor in raw.items()
        if clave in claves and valor is not None and str(valor).strip()
    }
    if not filtros:
        return {"error": "Falta al menos un filtro para sugerir."}

    return {"modulo": modulo, "tab": tab, "filtros": filtros}


def filtros_sugeridos_desde_llamadas(llamadas: list[dict]) -> dict | None:
    for llamada in reversed(llamadas):
        nombre = llamada.get("name")
        args = llamada.get("args")
        if not isinstance(nombre, str) or not isinstance(args, dict):
            continue
        if nombre == "sugerir_filtros":
            continue

        if nombre.startswith("compras_"):
            modulo = "compras"
            if nombre == "compras_buscar":
                tab = "tabla"
            elif nombre == "compras_precio_producto":
                tab = "precios"
            elif nombre == "compras_comparativo":
                tab = "comparativo"
            else:
                tab = "graficas"
        elif nombre.startswith("importaciones_"):
            modulo = "importaciones"
            if nombre == "importaciones_buscar":
                tab = "operaciones"
            elif nombre == "importaciones_comparativo":
                tab = "comparativo"
            elif nombre == "importaciones_ranking" and args.get("dimension") == "importadores":
                tab = "importadores"
            elif nombre == "importaciones_ranking" and args.get("dimension") == "proveedores":
                tab = "proveedores"
            elif nombre == "importaciones_ranking" and args.get("dimension") == "partidas":
                tab = "productos"
            else:
                tab = "resumen"
        else:
            continue

        claves = _CLAVES_FILTROS_SUGERIDOS[modulo]
        filtros = {
            clave: str(args[clave]).strip()
            for clave in claves
            if args.get(clave) is not None and str(args[clave]).strip()
        }
        if not filtros:
            continue
        return {"modulo": modulo, "tab": tab, "filtros": filtros}
    return None


def _capacidades(db: Session, args: dict) -> dict:
    catalogo = _endpoints()
    return {
        "modulos": ["importaciones", "compras"],
        "endpoints": catalogo["endpoints"],
        "nota": catalogo["nota"],
    }


TOOLS: dict[str, Tool] = {
    t.definition["function"]["name"]: t
    for t in [
        _tool(
            "importaciones_kpis",
            "Importaciones: totales del conjunto filtrado en USD y KG, operaciones, costo unitario y número de actores.",
            _resumen_kpis,
            dict(_FILTROS),
        ),
        _tool(
            "importaciones_ranking",
            "Importaciones: ranking agregado por dimensión. Devuelve valor_usd, volumen_kg, registros, costo_unit_ponderado, pct_total, pct_acumulado y porcentaje.",
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
                    "description": "Solo tipo_importacion: agrupa en Depósito fiscal e Importación definitiva",
                },
            },
            required=["dimension"],
        ),
        _tool(
            "importaciones_mensual",
            "Importaciones: serie mensual con valor_usd, volumen_kg, registros y costo_unit_ponderado.",
            _serie_mensual,
            dict(_FILTROS),
        ),
        _tool(
            "importaciones_comparativo",
            "Importaciones: compara dos meses por partida, país, importador o exportador. Los filtros de fecha se ignoran.",
            _comparativo_importaciones,
            {
                "dimension": {
                    "type": ["string", "null"],
                    "enum": ["partida", "pais_origen", "importador", "exportador", None],
                },
                "mes": {"type": ["string", "null"], "description": "YYYY-MM"},
                "comparar": {"type": ["string", "null"], "description": "YYYY-MM"},
                "metrica": {
                    "type": ["string", "null"],
                    "enum": ["valor_usd", "volumen_kg", None],
                },
                "order_by": {
                    "type": ["string", "null"],
                    "enum": ["delta_abs", "delta_pp", "valor_actual", None],
                },
                "min_registros": {"type": ["integer", "null"]},
                **_FILTROS,
                **_ORDEN,
            },
        ),
        _tool(
            "importaciones_buscar",
            "Importaciones: busca operaciones por texto en la descripción comercial. Requiere q.",
            _buscar,
            {**_FILTROS, "q": {"type": "string", "description": "Texto a buscar"}},
            required=["q"],
        ),
        _tool(
            "importaciones_catalogo",
            "Importaciones: catálogo de aduanas, países o partidas con descripción.",
            _catalogo,
            {
                "tipo": {
                    "type": "string",
                    "enum": ["aduanas", "paises", "partidas"],
                }
            },
            required=["tipo"],
        ),
        _tool(
            "compras_kpis",
            "Compras: importe total MXN, registros, proveedores, categorías, meses, nacional/internacional y cobertura.",
            _compras_kpis,
            dict(_FILTROS_COMPRAS),
        ),
        _tool(
            "compras_ranking",
            "Compras: ranking de categorías o proveedores por importe MXN, registros y participación.",
            _compras_ranking,
            {
                "dimension": {
                    "type": "string",
                    "enum": ["categorias", "proveedores"],
                },
                **_FILTROS_COMPRAS,
                **_ORDEN,
            },
            required=["dimension"],
        ),
        _tool(
            "compras_mensual",
            "Compras: serie mensual de importe MXN, nacional/internacional, registros y bandera de mes completo.",
            _compras_mensual,
            dict(_FILTROS_COMPRAS),
        ),
        _tool(
            "compras_precio_producto",
            "Compras: busca productos por q o calcula precio promedio anual y serie mensual de una descripción exacta. Todos los importes en MXN.",
            _compras_precio_producto,
            {
                **_FILTROS_COMPRAS,
                "descripcion": {
                    "type": ["string", "null"],
                    "description": "Descripción exacta del producto, tal como aparece en la base",
                },
                "anio": {"type": ["integer", "null"], "description": "Año 2000-2100"},
                "top": {
                    "type": ["integer", "null"],
                    "description": "Coincidencias a devolver (default 10, máximo 50)",
                },
            },
        ),
        _tool(
            "compras_comparativo",
            "Compras: compara dos meses por descripción, categoría o proveedor. Los filtros de fecha se ignoran.",
            _compras_comparativo,
            {
                "dimension": {
                    "type": ["string", "null"],
                    "enum": ["descripcion", "categoria", "proveedor", None],
                },
                "mes": {"type": ["string", "null"], "description": "YYYY-MM"},
                "comparar": {"type": ["string", "null"], "description": "YYYY-MM"},
                "metrica": {
                    "type": ["string", "null"],
                    "enum": ["importe_mxn", "cantidad", "precio_promedio_mxn", None],
                },
                "order_by": {
                    "type": ["string", "null"],
                    "enum": ["delta_abs", "delta_pp", "valor_actual", None],
                },
                "min_registros": {"type": ["integer", "null"]},
                **_FILTROS_COMPRAS,
                **_ORDEN,
            },
        ),
        _tool(
            "compras_buscar",
            "Compras: lista compras filtradas. q busca en descripción, proveedor o fracción. Requiere q.",
            _compras_buscar,
            {**_FILTROS_COMPRAS, "q": {"type": "string", "description": "Texto a buscar"}},
            required=["q"],
        ),
        _tool(
            "compras_catalogo",
            "Compras: catálogo de categorías, proveedores, fracciones válidas, años, ámbitos, descripciones o todo. Para descripciones acepta q y devuelve coincidencias.",
            _compras_catalogo,
            {
                "tipo": {
                    "type": "string",
                    "enum": [
                        "categorias",
                        "proveedores",
                        "fracciones",
                        "anios",
                        "ambitos",
                        "descripciones",
                        "todo",
                    ],
                },
                "q": {
                    "type": ["string", "null"],
                    "description": "Solo para descripciones: texto a buscar",
                },
                "anio": {"type": ["integer", "null"], "description": "Solo para descripciones"},
                "top": {
                    "type": ["integer", "null"],
                    "description": "Solo para descripciones (default 10, máximo 50)",
                },
            },
            required=["tipo"],
        ),
        _tool(
            "pedir_aclaracion",
            "Pide al usuario que aclare el módulo, producto, proveedor, período o alcance antes de consultar. Úsala solo cuando falte información imprescindible.",
            _pedir_aclaracion,
            {
                "pregunta": {
                    "type": "string",
                    "description": "Pregunta breve y concreta para el usuario",
                },
                "opciones": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Opciones sugeridas, máximo 10",
                },
            },
            required=["pregunta"],
        ),
        _tool(
            "sugerir_filtros",
            "Registra filtros para que el usuario pueda abrirlos en una vista de la interfaz. No navega ni aplica filtros; el frontend pedirá confirmación. Úsala cuando la respuesta permita ver los mismos datos en una pestaña.",
            _sugerir_filtros,
            {
                "modulo": {
                    "type": "string",
                    "enum": ["importaciones", "compras"],
                },
                "tab": {
                    "type": ["string", "null"],
                    "enum": [
                        "resumen",
                        "importadores",
                        "proveedores",
                        "productos",
                        "comparativo",
                        "matriz",
                        "operaciones",
                        "preguntas",
                        "graficas",
                        "precios",
                        "tabla",
                        None,
                    ],
                    "description": "Pestaña destino de la vista",
                },
                "filtros": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Filtros exactos que se aplicarían en la vista",
                },
            },
            required=["modulo", "filtros"],
        ),
        _tool(
            "capacidades",
            "Devuelve los módulos, endpoints de solo lectura y capacidades analíticas disponibles. Úsala para preguntas sobre qué puedes hacer o qué datos puedes consultar.",
            _capacidades,
            {},
        ),
    ]
}

TOOL_DEFINITIONS = [t.definition for t in TOOLS.values()]
