from __future__ import annotations

from calendar import monthrange
from dataclasses import replace
from datetime import date
from typing import Mapping

from sqlalchemy import Select, case, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.dependencies import FiltrosCompras
from app.models import CompraArticulo

CATEGORIA_SIN_DATO = "Sin categoría"

IMPORTE = CompraArticulo.importe_mxn
AMBITO_INTERNACIONAL = CompraArticulo.ambito == "internacional"
AMBITO_NACIONAL = CompraArticulo.ambito == "nacional"


def aplicar_filtros(stmt: Select, filtros: FiltrosCompras) -> Select:
    if filtros.fecha_desde is not None:
        stmt = stmt.where(CompraArticulo.fecha >= filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        stmt = stmt.where(CompraArticulo.fecha <= filtros.fecha_hasta)
    if filtros.categoria:
        if filtros.categoria == CATEGORIA_SIN_DATO:
            stmt = stmt.where(CompraArticulo.categoria.is_(None))
        else:
            stmt = stmt.where(CompraArticulo.categoria == filtros.categoria)
    if filtros.proveedor:
        stmt = stmt.where(
            CompraArticulo.proveedor.ilike(f"%{filtros.proveedor}%")
        )
    if filtros.descripcion:
        stmt = stmt.where(CompraArticulo.descripcion == filtros.descripcion)
    if filtros.ambito:
        stmt = stmt.where(CompraArticulo.ambito == filtros.ambito)
    if filtros.fraccion:
        stmt = stmt.where(CompraArticulo.fraccion_arancelaria == filtros.fraccion)
    if filtros.q:
        patron = f"%{filtros.q}%"
        stmt = stmt.where(
            or_(
                CompraArticulo.descripcion.ilike(patron),
                CompraArticulo.proveedor.ilike(patron),
                CompraArticulo.fraccion_arancelaria.ilike(patron),
            )
        )
    return stmt


def kpis(db: Session, filtros: FiltrosCompras) -> Mapping:
    total = func.sum(IMPORTE)
    nacional = func.coalesce(
        func.sum(case((AMBITO_NACIONAL, IMPORTE), else_=0)), 0
    )
    internacional = func.coalesce(
        func.sum(case((AMBITO_INTERNACIONAL, IMPORTE), else_=0)), 0
    )
    stmt = select(
        total.label("importe_total_mxn"),
        func.count().label("registros"),
        func.count(distinct(CompraArticulo.proveedor)).label("proveedores"),
        func.count(
            distinct(func.coalesce(CompraArticulo.categoria, CATEGORIA_SIN_DATO))
        ).label("categorias"),
        func.count(distinct(CompraArticulo.mes)).label("meses"),
        nacional.label("importe_nacional_mxn"),
        internacional.label("importe_internacional_mxn"),
        func.coalesce(
            func.sum(case((CompraArticulo.fraccion_valida.is_(True), 1), else_=0)), 0
        ).label("fracciones_validas"),
        func.coalesce(
            func.sum(
                case(
                    (
                        CompraArticulo.fraccion_arancelaria.is_not(None)
                        & (func.trim(CompraArticulo.fraccion_arancelaria) != "")
                        & CompraArticulo.fraccion_valida.is_(False),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("fracciones_invalidas"),
        func.coalesce(
            func.sum(
                case(
                    (
                        CompraArticulo.fraccion_arancelaria.is_(None)
                        | (func.trim(CompraArticulo.fraccion_arancelaria) == ""),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("sin_fraccion"),
        func.min(CompraArticulo.fecha).label("fecha_min"),
        func.max(CompraArticulo.fecha).label("fecha_max"),
    )
    stmt = aplicar_filtros(stmt, filtros)
    fila = db.execute(stmt).mappings().one()
    data = dict(fila)
    importe_total = float(data["importe_total_mxn"] or 0)
    importe_internacional = float(data["importe_internacional_mxn"] or 0)
    data["pct_internacional"] = (
        importe_internacional * 100.0 / importe_total if importe_total else None
    )
    return data


def mensual(db: Session, filtros: FiltrosCompras) -> list[dict]:
    nacional = func.coalesce(
        func.sum(case((AMBITO_NACIONAL, IMPORTE), else_=0)), 0
    )
    internacional = func.coalesce(
        func.sum(case((AMBITO_INTERNACIONAL, IMPORTE), else_=0)), 0
    )
    stmt = (
        select(
            CompraArticulo.mes.label("mes"),
            func.sum(IMPORTE).label("importe_mxn"),
            nacional.label("importe_nacional_mxn"),
            internacional.label("importe_internacional_mxn"),
            func.count().label("registros"),
            func.min(CompraArticulo.fecha).label("fecha_min"),
            func.max(CompraArticulo.fecha).label("fecha_max"),
        )
        .group_by(CompraArticulo.mes)
        .order_by(CompraArticulo.mes)
    )
    stmt = aplicar_filtros(stmt, filtros)
    filas = db.execute(stmt).mappings().all()
    if not filas:
        return []

    primer_mes = str(filas[0]["mes"])
    ultimo_mes = str(filas[-1]["mes"])
    salida = []
    for fila in filas:
        mes = str(fila["mes"])
        importe = float(fila["importe_mxn"] or 0)
        importe_int = float(fila["importe_internacional_mxn"] or 0)
        anio, numero_mes = (int(parte) for parte in mes.split("-"))
        primer_dia = date(anio, numero_mes, 1)
        ultimo_dia = date(anio, numero_mes, monthrange(anio, numero_mes)[1])
        fecha_min = fila["fecha_min"]
        fecha_max = fila["fecha_max"]
        completo = True
        if mes == primer_mes and fecha_min and fecha_min > primer_dia:
            completo = False
        if mes == ultimo_mes and fecha_max and fecha_max < ultimo_dia:
            completo = False
        salida.append(
            {
                "mes": mes,
                "importe_mxn": importe,
                "importe_nacional_mxn": float(fila["importe_nacional_mxn"] or 0),
                "importe_internacional_mxn": importe_int,
                "registros": int(fila["registros"] or 0),
                "pct_internacional": (importe_int * 100.0 / importe) if importe else None,
                "completo": completo,
            }
        )
    return salida


def categorias(
    db: Session, filtros: FiltrosCompras, top: int = 20
) -> list[dict]:
    categoria = func.coalesce(
        CompraArticulo.categoria, CATEGORIA_SIN_DATO
    ).label("categoria")
    importe = func.sum(IMPORTE)
    total = func.sum(importe).over()
    internacional = func.coalesce(
        func.sum(case((AMBITO_INTERNACIONAL, IMPORTE), else_=0)), 0
    )
    stmt = (
        select(
            categoria,
            importe.label("importe_mxn"),
            func.count().label("registros"),
            func.count(distinct(CompraArticulo.proveedor)).label("proveedores"),
            (importe * 100.0 / func.nullif(total, 0)).label("pct_importe"),
            (internacional * 100.0 / func.nullif(importe, 0)).label(
                "pct_internacional"
            ),
        )
        .group_by(categoria)
        .order_by(importe.desc())
        .limit(top)
    )
    stmt = aplicar_filtros(stmt, filtros)
    return [dict(fila) for fila in db.execute(stmt).mappings().all()]


def proveedores(
    db: Session, filtros: FiltrosCompras, top: int = 20
) -> list[dict]:
    importe = func.sum(IMPORTE)
    total = func.sum(importe).over()
    stmt = (
        select(
            CompraArticulo.proveedor.label("proveedor"),
            CompraArticulo.ambito.label("ambito"),
            importe.label("importe_mxn"),
            func.count().label("registros"),
            func.count(
                distinct(func.coalesce(CompraArticulo.categoria, CATEGORIA_SIN_DATO))
            ).label("categorias"),
            (importe * 100.0 / func.nullif(total, 0)).label("pct_importe"),
        )
        .group_by(CompraArticulo.proveedor, CompraArticulo.ambito)
        .order_by(importe.desc())
        .limit(top)
    )
    stmt = aplicar_filtros(stmt, filtros)
    return [dict(fila) for fila in db.execute(stmt).mappings().all()]


def listar_compras(
    filtros: FiltrosCompras,
    order_by: str = "fecha",
    desc: bool = True,
) -> Select:
    stmt = select(*CompraArticulo.__table__.columns)
    stmt = aplicar_filtros(stmt, filtros)
    columnas = {
        "fecha": CompraArticulo.fecha,
        "importe_mxn": CompraArticulo.importe_mxn,
        "precio_unitario_mxn": CompraArticulo.precio_unitario_mxn,
        "cantidad": CompraArticulo.cantidad,
        "proveedor": CompraArticulo.proveedor,
    }
    orden = columnas.get(order_by, CompraArticulo.fecha)
    orden = orden.desc() if desc else orden.asc()
    return stmt.order_by(orden, CompraArticulo.id.desc())


def _anio_actual(db: Session, filtros: FiltrosCompras) -> int | None:
    stmt = select(func.max(CompraArticulo.anio))
    stmt = aplicar_filtros(stmt, filtros)
    return db.scalar(stmt)


def precios(
    db: Session,
    filtros: FiltrosCompras,
    anio: int | None = None,
    top: int = 100,
) -> list[dict]:
    if anio is None:
        anio = _anio_actual(db, filtros)
    if anio is None:
        return []

    importe = func.sum(IMPORTE)
    cantidad = func.sum(CompraArticulo.cantidad)
    stmt = (
        select(
            CompraArticulo.descripcion.label("descripcion"),
            func.max(CompraArticulo.categoria).label("categoria"),
            CompraArticulo.anio.label("anio"),
            importe.label("importe_mxn"),
            cantidad.label("cantidad"),
            func.count().label("registros"),
            func.count(distinct(CompraArticulo.proveedor)).label("proveedores"),
            func.count(distinct(CompraArticulo.mes)).label("meses"),
        )
        .where(CompraArticulo.anio == anio)
        .where(CompraArticulo.cantidad.is_not(None))
        .where(CompraArticulo.cantidad > 0)
        .group_by(CompraArticulo.descripcion, CompraArticulo.anio)
        .order_by(importe.desc())
        .limit(top)
    )
    stmt = aplicar_filtros(stmt, filtros)
    salida = []
    for fila in db.execute(stmt).mappings().all():
        importe_mxn = float(fila["importe_mxn"] or 0)
        cantidad_total = float(fila["cantidad"] or 0)
        salida.append(
            {
                "descripcion": fila["descripcion"],
                "categoria": fila["categoria"],
                "anio": int(fila["anio"]),
                "importe_mxn": importe_mxn,
                "cantidad": cantidad_total,
                "precio_promedio_mxn": (
                    importe_mxn / cantidad_total if cantidad_total > 0 else None
                ),
                "registros": int(fila["registros"] or 0),
                "proveedores": int(fila["proveedores"] or 0),
                "meses": int(fila["meses"] or 0),
            }
        )
    return salida


def precios_mensual(
    db: Session,
    filtros: FiltrosCompras,
    descripcion: str,
    anio: int | None = None,
) -> list[dict]:
    if anio is None:
        stmt_anio = select(func.max(CompraArticulo.anio)).where(
            CompraArticulo.descripcion == descripcion
        )
        stmt_anio = aplicar_filtros(stmt_anio, filtros)
        anio = db.scalar(stmt_anio)
    if anio is None:
        return []

    importe = func.sum(IMPORTE)
    cantidad = func.sum(CompraArticulo.cantidad)
    stmt = (
        select(
            CompraArticulo.mes.label("mes"),
            importe.label("importe_mxn"),
            cantidad.label("cantidad"),
            func.count().label("registros"),
        )
        .where(CompraArticulo.descripcion == descripcion)
        .where(CompraArticulo.anio == anio)
        .where(CompraArticulo.cantidad.is_not(None))
        .where(CompraArticulo.cantidad > 0)
        .group_by(CompraArticulo.mes)
        .order_by(CompraArticulo.mes)
    )
    stmt = aplicar_filtros(stmt, filtros)
    salida = []
    for fila in db.execute(stmt).mappings().all():
        importe_mxn = float(fila["importe_mxn"] or 0)
        cantidad_total = float(fila["cantidad"] or 0)
        salida.append(
            {
                "mes": str(fila["mes"]),
                "importe_mxn": importe_mxn,
                "cantidad": cantidad_total,
                "precio_promedio_mxn": (
                    importe_mxn / cantidad_total if cantidad_total > 0 else None
                ),
                "registros": int(fila["registros"] or 0),
            }
        )
    return salida


def _sin_filtros_fecha(filtros: FiltrosCompras) -> FiltrosCompras:
    return replace(filtros, fecha_desde=None, fecha_hasta=None)


def _mes_anterior(mes: str) -> str:
    anio, numero = (int(parte) for parte in mes.split("-"))
    if numero == 1:
        return f"{anio - 1}-12"
    return f"{anio}-{numero - 1:02d}"


def _periodo_vacio(mes: str) -> dict:
    anio, numero = (int(parte) for parte in mes.split("-"))
    return {
        "mes": mes,
        "desde": date(anio, numero, 1),
        "hasta": date(anio, numero, monthrange(anio, numero)[1]),
        "completo": False,
        "registros": 0,
    }


def periodos(db: Session, filtros: FiltrosCompras) -> list[dict]:
    stmt = (
        select(
            CompraArticulo.mes.label("mes"),
            func.min(CompraArticulo.fecha).label("fecha_min"),
            func.max(CompraArticulo.fecha).label("fecha_max"),
            func.count().label("registros"),
        )
        .group_by(CompraArticulo.mes)
        .order_by(CompraArticulo.mes)
    )
    stmt = aplicar_filtros(stmt, filtros)
    filas = db.execute(stmt).mappings().all()
    if not filas:
        return []

    primer_mes = str(filas[0]["mes"])
    ultimo_mes = str(filas[-1]["mes"])
    salida = []
    for fila in filas:
        mes = str(fila["mes"])
        anio, numero_mes = (int(parte) for parte in mes.split("-"))
        primer_dia = date(anio, numero_mes, 1)
        ultimo_dia = date(anio, numero_mes, monthrange(anio, numero_mes)[1])
        fecha_min = fila["fecha_min"]
        fecha_max = fila["fecha_max"]
        completo = True
        if mes == primer_mes and fecha_min and fecha_min > primer_dia:
            completo = False
        if mes == ultimo_mes and fecha_max and fecha_max < ultimo_dia:
            completo = False
        salida.append(
            {
                "mes": mes,
                "desde": primer_dia,
                "hasta": ultimo_dia,
                "completo": completo,
                "registros": int(fila["registros"] or 0),
            }
        )
    return salida


def _agregar_periodo(
    db: Session,
    filtros: FiltrosCompras,
    dimension: str,
    metrica: str,
    mes: str,
) -> dict[str, dict]:
    columnas = {
        "descripcion": CompraArticulo.descripcion,
        "categoria": func.coalesce(
            CompraArticulo.categoria, CATEGORIA_SIN_DATO
        ),
        "proveedor": CompraArticulo.proveedor,
    }
    columna = columnas[dimension]
    detalle = (
        func.max(CompraArticulo.categoria)
        if dimension == "descripcion"
        else func.max(CompraArticulo.ambito)
        if dimension == "proveedor"
        else None
    )
    importe = func.sum(IMPORTE)
    cantidad = func.sum(CompraArticulo.cantidad)
    seleccion = [
        columna.label("clave"),
        importe.label("importe_mxn"),
        cantidad.label("cantidad"),
        func.count().label("registros"),
    ]
    if detalle is not None:
        seleccion.append(detalle.label("detalle"))
    stmt = (
        select(*seleccion)
        .where(CompraArticulo.mes == mes)
        .group_by(columna)
    )
    if metrica == "precio_promedio_mxn":
        stmt = stmt.where(
            CompraArticulo.cantidad.is_not(None),
            CompraArticulo.cantidad > 0,
        )
    stmt = aplicar_filtros(stmt, filtros)
    resultado = {}
    for fila in db.execute(stmt).mappings().all():
        importe_mxn = float(fila["importe_mxn"] or 0)
        cantidad_total = float(fila["cantidad"] or 0)
        if metrica == "cantidad":
            valor = cantidad_total
        elif metrica == "precio_promedio_mxn":
            valor = importe_mxn / cantidad_total if cantidad_total > 0 else 0.0
        else:
            valor = importe_mxn
        if valor == 0:
            continue
        resultado[str(fila["clave"])] = {
            "valor": valor,
            "importe_mxn": importe_mxn,
            "cantidad": cantidad_total,
            "registros": int(fila["registros"] or 0),
            "detalle": fila.get("detalle"),
        }
    return resultado


def comparativo(
    db: Session,
    filtros: FiltrosCompras,
    dimension: str = "descripcion",
    mes: str | None = None,
    comparar: str | None = None,
    metrica: str = "importe_mxn",
    order_by: str = "delta_abs",
    top: int = 20,
    min_registros: int = 3,
) -> dict | None:
    filtros = _sin_filtros_fecha(filtros)
    periodos_disponibles = periodos(db, filtros)
    if not periodos_disponibles:
        return None

    por_mes = {periodo["mes"]: periodo for periodo in periodos_disponibles}
    if mes is None:
        completos = [periodo for periodo in periodos_disponibles if periodo["completo"]]
        periodo_actual = (completos or periodos_disponibles)[-1]
    else:
        periodo_actual = por_mes.get(mes)
        if periodo_actual is None:
            return None

    if comparar is None:
        comparar = _mes_anterior(periodo_actual["mes"])
    periodo_anterior = por_mes.get(comparar) or _periodo_vacio(comparar)

    actual = _agregar_periodo(
        db, filtros, dimension, metrica, periodo_actual["mes"]
    )
    previo = _agregar_periodo(
        db, filtros, dimension, metrica, periodo_anterior["mes"]
    )

    if metrica == "precio_promedio_mxn":
        importe_actual = sum(fila["importe_mxn"] for fila in actual.values())
        cantidad_actual = sum(fila["cantidad"] for fila in actual.values())
        importe_previo = sum(fila["importe_mxn"] for fila in previo.values())
        cantidad_previa = sum(fila["cantidad"] for fila in previo.values())
        total_actual = (
            importe_actual / cantidad_actual if cantidad_actual > 0 else 0.0
        )
        total_previo = (
            importe_previo / cantidad_previa if cantidad_previa > 0 else 0.0
        )
    else:
        total_actual = sum(fila["valor"] for fila in actual.values())
        total_previo = sum(fila["valor"] for fila in previo.values())

    claves = set(actual) | set(previo)
    items = []
    for clave in claves:
        fila_actual = actual.get(clave, {})
        fila_previa = previo.get(clave, {})
        valor_actual = float(fila_actual.get("valor") or 0)
        valor_previo = float(fila_previa.get("valor") or 0)
        if valor_actual == 0 and valor_previo == 0:
            continue

        if valor_previo <= 0:
            variacion_pct = None if valor_actual > 0 else 0.0
            estado = "nuevo" if valor_actual > 0 else "sin_cambio"
        else:
            variacion_pct = (valor_actual - valor_previo) * 100.0 / valor_previo
            if valor_actual <= 0:
                estado = "desaparece"
            elif abs(variacion_pct) < 1e-9:
                estado = "sin_cambio"
            elif variacion_pct > 0:
                estado = "sube"
            else:
                estado = "baja"

        share_actual = None
        share_previo = None
        delta_pp = None
        if metrica != "precio_promedio_mxn":
            share_actual = (
                valor_actual * 100.0 / total_actual if total_actual > 0 else None
            )
            share_previo = (
                valor_previo * 100.0 / total_previo if total_previo > 0 else None
            )
            delta_pp = (
                share_actual - share_previo
                if share_actual is not None and share_previo is not None
                else None
            )
        registros_actual = int(fila_actual.get("registros") or 0)
        registros_previo = int(fila_previa.get("registros") or 0)

        items.append(
            {
                "clave": clave,
                "etiqueta": clave,
                "detalle": fila_actual.get("detalle")
                or fila_previa.get("detalle"),
                "valor_actual": valor_actual,
                "valor_previo": valor_previo,
                "delta_abs": valor_actual - valor_previo,
                "variacion_pct": variacion_pct,
                "share_actual": share_actual,
                "share_previo": share_previo,
                "delta_pp": delta_pp,
                "registros_actual": registros_actual,
                "registros_previo": registros_previo,
                "estado": estado,
                "muestra_suficiente": (
                    registros_actual >= min_registros
                    and registros_previo >= min_registros
                ),
            }
        )

    if order_by == "delta_pp":
        def orden(item):
            return abs(item["delta_pp"] or 0)
    elif order_by == "valor_actual":
        def orden(item):
            return item["valor_actual"]
    else:
        def orden(item):
            return abs(item["delta_abs"])

    items.sort(key=orden, reverse=True)
    total_items = len(items)
    items = items[:top]

    return {
        "periodo": periodo_actual,
        "periodo_anterior": periodo_anterior,
        "periodos": periodos_disponibles,
        "dimension": dimension,
        "metrica": metrica,
        "order_by": order_by,
        "min_registros": min_registros,
        "total_actual": total_actual,
        "total_previo": total_previo,
        "items": items,
        "total_items": total_items,
    }


def meta(db: Session) -> dict:
    categorias_bd = [
        fila[0]
        for fila in db.execute(
            select(CompraArticulo.categoria)
            .where(CompraArticulo.categoria.is_not(None))
            .distinct()
            .order_by(CompraArticulo.categoria)
        ).all()
    ]
    hay_sin_categoria = db.scalar(
        select(func.count())
        .select_from(CompraArticulo)
        .where(CompraArticulo.categoria.is_(None))
    )
    if hay_sin_categoria:
        categorias_bd.append(CATEGORIA_SIN_DATO)

    proveedores_bd = [
        fila[0]
        for fila in db.execute(
            select(CompraArticulo.proveedor)
            .distinct()
            .order_by(CompraArticulo.proveedor)
        ).all()
    ]
    descripciones = [
        fila[0]
        for fila in db.execute(
            select(CompraArticulo.descripcion)
            .where(func.trim(CompraArticulo.descripcion) != "")
            .distinct()
            .order_by(CompraArticulo.descripcion)
        ).all()
    ]
    fracciones = [
        fila[0]
        for fila in db.execute(
            select(CompraArticulo.fraccion_arancelaria)
            .where(CompraArticulo.fraccion_valida.is_(True))
            .distinct()
            .order_by(CompraArticulo.fraccion_arancelaria)
        ).all()
    ]
    anios = [
        int(fila[0])
        for fila in db.execute(
            select(CompraArticulo.anio)
            .distinct()
            .order_by(CompraArticulo.anio.desc())
        ).all()
    ]
    fechas = db.execute(
        select(
            func.min(CompraArticulo.fecha).label("fecha_min"),
            func.max(CompraArticulo.fecha).label("fecha_max"),
            func.count().label("total"),
        )
    ).mappings().one()
    return {
        "categorias": categorias_bd,
        "proveedores": proveedores_bd,
        "descripciones": descripciones,
        "fracciones": fracciones,
        "anios": anios,
        "ambitos": ["nacional", "internacional"],
        "fecha_min": fechas["fecha_min"],
        "fecha_max": fechas["fecha_max"],
        "total_registros": int(fechas["total"] or 0),
    }
