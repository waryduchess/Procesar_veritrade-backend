from __future__ import annotations

import json
import unicodedata
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

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
    PreguntaOut,
    ProveedorPaisRow,
    ProveedorRow,
    TipoImportacionRow,
)
from app.services import consultas
from app.utils.paginacion import construir_page

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "preguntas.json"

_METRICAS = {
    "valor_usd",
    "volumen_kg",
    "registros",
    "costo_unit_ponderado",
    "pct_total",
    "pct_acumulado",
    "porcentaje",
}

_RANKINGS = {
    "/reportes/importadores": (consultas.DIM_IMPORTADOR, ImportadorRow, None),
    "/reportes/importadores-cancun": (
        consultas.DIM_IMPORTADOR,
        ImportadorRow,
        Importacion.es_cancun == 1,
    ),
    "/reportes/proveedores": (
        consultas.DIM_PROVEEDOR,
        ProveedorRow,
        consultas.SOLO_EXPORTADOR,
    ),
    "/reportes/proveedores-por-pais": (
        consultas.DIM_PROVEEDOR_PAIS,
        ProveedorPaisRow,
        consultas.SOLO_EXPORTADOR,
    ),
    "/reportes/paises-origen": (consultas.DIM_PAIS, PaisOrigenRow, None),
    "/reportes/partidas": (consultas.DIM_PARTIDA, PartidaRow, None),
}


def cargar_preguntas() -> tuple[dict, ...]:
    return tuple(json.loads(DATA_FILE.read_text(encoding="utf-8")))


def _normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def listar(categoria: str | None = None) -> list[PreguntaOut]:
    preguntas = cargar_preguntas()
    if categoria:
        objetivo = _normalizar(categoria)
        preguntas = [p for p in preguntas if _normalizar(p["categoria"]) == objetivo]
    return [PreguntaOut(**p) for p in preguntas]


def detectar(texto: str) -> dict | None:
    normalizado = _normalizar(texto)
    mejor = None
    mejor_score = 0
    for entrada in cargar_preguntas():
        puntaje = sum(
            len(_normalizar(kw))
            for kw in entrada["palabras_clave"]
            if _normalizar(kw) in normalizado
        )
        if puntaje > mejor_score:
            mejor, mejor_score = entrada, puntaje
    return mejor


def responder(texto: str, db: Session, params_override: dict | None = None) -> dict:
    pregunta = detectar(texto)
    if pregunta is None:
        return {
            "encontrada": False,
            "resumen": (
                "No encontré una pregunta que coincida con el glosario. "
                "Prueba con una de las sugerencias."
            ),
            "sugerencias": [p["pregunta"] for p in cargar_preguntas()],
        }

    resumen, datos = ejecutar(pregunta, db, params_override)
    return {
        "encontrada": True,
        "pregunta": pregunta["pregunta"],
        "id": pregunta["id"],
        "categoria": pregunta["categoria"],
        "endpoint": pregunta["endpoint"],
        "params": {**pregunta.get("params", {}), **(params_override or {})},
        "resumen": resumen,
        "datos": datos,
    }


def ejecutar(
    pregunta: dict, db: Session, params_override: dict | None = None
) -> tuple[str, dict | None]:
    params = {**pregunta.get("params", {}), **(params_override or {})}
    for requerido in pregunta.get("requiere", []):
        if not params.get(requerido):
            return f"Falta indicar el parámetro '{requerido}'.", None

    filtros = _filtros(params)
    endpoint = pregunta["endpoint"]

    if endpoint in _RANKINGS:
        dimension, modelo, extra = _RANKINGS[endpoint]
        stmt = consultas.ranking(
            dimension, filtros, _order_by(params), _desc(params), extra_where=extra
        )
        datos = _page_dict(db, stmt, modelo, _page(params), _page_size(params))
        return _resumen_ranking(pregunta, datos, _order_by(params)), datos

    if pregunta["endpoint"] == "/reportes/mensual":
        stmt = consultas.ranking(consultas.DIM_MES, filtros, order_by="mes", desc=False)
        datos = _page_dict(db, stmt, MensualRow, 1, _page_size(params))
        return _resumen_mensual(datos), datos

    if pregunta["endpoint"] == "/reportes/tipo-importacion":
        stmt = consultas.tipo_importacion_ranking(
            filtros,
            _order_by(params),
            _desc(params),
            solo_principales=bool(params.get("solo_principales", False)),
        )
        datos = _page_dict(db, stmt, TipoImportacionRow, _page(params), _page_size(params))
        return _resumen_ranking(pregunta, datos, _order_by(params)), datos

    if pregunta["endpoint"] == "/reportes/kpis":
        datos = KpisOut.model_validate(dict(consultas.kpis(db, filtros))).model_dump(
            mode="json"
        )
        return _resumen_kpis(datos), datos

    if pregunta["endpoint"] == "/meta/partidas":
        filas = consultas.meta_partidas(db)
        datos = [PartidaMeta.model_validate(f).model_dump(mode="json") for f in filas]
        return f"El catálogo tiene {len(datos)} fracciones arancelarias.", {
            "items": datos,
            "total": len(datos),
        }

    if pregunta["endpoint"] == "/meta/paises":
        valores = consultas.valores_meta(db, Importacion.pais_origen)
        return f"Hay {len(valores)} países de origen registrados.", {
            "items": valores,
            "total": len(valores),
        }

    if pregunta["endpoint"] == "/meta/aduanas":
        valores = consultas.valores_meta(db, Importacion.aduana)
        return f"Hay {len(valores)} aduanas registradas.", {
            "items": valores,
            "total": len(valores),
        }

    if pregunta["endpoint"] == "/importaciones/buscar":
        q = params.get("q")
        stmt = consultas.listar_importaciones(filtros, q=q)
        datos = _page_dict(db, stmt, ImportacionOut, _page(params), _page_size(params))
        return (
            f'Se encontraron {datos['total']} operaciones que contienen "{q}" '
            f"en la descripción comercial.",
            datos,
        )

    return "Pregunta no implementada.", None


def _filtros(params: dict) -> Filtros:
    return Filtros(
        fecha_desde=_fecha(params.get("fecha_desde")),
        fecha_hasta=_fecha(params.get("fecha_hasta")),
        aduana=params.get("aduana"),
        pais_origen=params.get("pais_origen"),
        partida=params.get("partida"),
        importador=params.get("importador"),
        exportador=params.get("exportador"),
    )


def _fecha(valor) -> date | None:
    if isinstance(valor, str) and valor:
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return None
    return None


def _order_by(params: dict) -> str:
    valor = params.get("order_by", "valor_usd")
    return valor if valor in ("valor_usd", "volumen_kg", "mes") else "valor_usd"


def _desc(params: dict) -> bool:
    return bool(params.get("desc", True))


def _page(params: dict) -> int:
    try:
        return max(1, int(params.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def _page_size(params: dict) -> int:
    valor = params.get("top") or params.get("page_size") or 10
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        valor = 10
    return max(1, min(valor, 500))


def _page_dict(db: Session, stmt, modelo, page: int, page_size: int) -> dict:
    pagina = construir_page(db, stmt, modelo, page, page_size)
    return {
        **pagina,
        "items": [item.model_dump(mode="json") for item in pagina["items"]],
    }


def _fmt_usd(valor) -> str:
    if valor is None:
        return "N/D"
    valor = float(valor)
    if abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.1f}M"
    if abs(valor) >= 1_000:
        return f"{valor / 1_000:.1f}K"
    return f"{valor:,.2f}"


def _dim_legible(item: dict) -> str:
    partes = [str(v) for k, v in item.items() if k not in _METRICAS and v]
    texto = " / ".join(partes) if partes else "el primer lugar"
    return texto if len(texto) <= 70 else texto[:67] + "..."


def _resumen_ranking(pregunta: dict, datos: dict, order_by: str = "valor_usd") -> str:
    items = datos["items"]
    if not items:
        return "No hay datos para estos filtros."
    primero = items[0]
    if order_by == "volumen_kg":
        metrica = f"{_fmt_usd(primero.get('volumen_kg'))} kg"
        pct = primero.get("porcentaje")
        etiqueta = "del volumen"
        acumulado = None
    else:
        metrica = f"{_fmt_usd(primero.get('valor_usd'))} USD"
        pct = primero.get("pct_total")
        etiqueta = "del valor"
        acumulado = items[-1].get("pct_acumulado")
    resumen = f"{pregunta['categoria']}: {_dim_legible(primero)} lidera con {metrica}"
    if pct is not None:
        resumen += f" ({pct:.1f}% {etiqueta})"
    resumen += f". Mostrando {len(items)} de {datos['total']}."
    if acumulado is not None:
        resumen += f" Este top concentra el {acumulado:.1f}% {etiqueta}."
    return resumen


def _resumen_mensual(datos: dict) -> str:
    items = datos.get("items", [])
    if not items:
        return "No hay datos para estos filtros."
    total = sum(float(i.get("valor_usd") or 0) for i in items)
    return (
        f"Serie mensual de {len(items)} periodos, de {items[0].get('mes')} a "
        f"{items[-1].get('mes')}. Valor acumulado: {_fmt_usd(total)} USD."
    )


def _resumen_kpis(datos: dict) -> str:
    return (
        f"Valor total importado: {_fmt_usd(datos.get('valor_total_usd'))} USD. "
        f"Volumen: {_fmt_usd(datos.get('volumen_total_kg'))} kg. "
        f"Costo unitario ponderado: {_fmt_usd(datos.get('costo_unit_ponderado'))} USD/kg. "
        f"Importadores: {datos.get('importadores')}, "
        f"exportadores: {datos.get('exportadores')}, "
        f"partidas: {datos.get('partidas')}, "
        f"países de origen: {datos.get('paises_origen')}."
    )
