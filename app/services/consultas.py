from calendar import monthrange
from collections import defaultdict
from dataclasses import replace
from datetime import date
from typing import Mapping

from sqlalchemy import Select, case, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.dependencies import Filtros
from app.models import Importacion

DIM_IMPORTADOR = [Importacion.importador.label("importador")]
DIM_PROVEEDOR = [Importacion.exportador.label("exportador")]
DIM_PROVEEDOR_PAIS = [
    Importacion.exportador.label("exportador"),
    Importacion.pais_origen.label("pais_origen"),
]
DIM_PAIS = [Importacion.pais_origen.label("pais_origen")]
DIM_TIPO = [Importacion.tipo_importacion.label("tipo_importacion")]
DIM_PARTIDA = [
    Importacion.partida_arancelaria.label("partida_arancelaria"),
    Importacion.descripcion_partida.label("descripcion_partida"),
]
DIM_MES = [Importacion.mes.label("mes")]

TIPO_PRINCIPAL_WHERE = or_(
    Importacion.tipo_importacion.ilike("%DEPOSITO FISCAL%"),
    Importacion.tipo_importacion.ilike("%IMPORTACION DEFINITIVA%"),
)

SOLO_EXPORTADOR = Importacion.exportador.is_not(None)


def tipo_principales_expr():
    return case(
        (
            Importacion.tipo_importacion.ilike("%DEPOSITO FISCAL%"),
            "Depósito fiscal",
        ),
        (
            Importacion.tipo_importacion.ilike("%IMPORTACION DEFINITIVA%"),
            "Importación definitiva",
        ),
        else_="Otros",
    ).label("tipo_importacion")


def aplicar_filtros(stmt: Select, filtros: Filtros) -> Select:
    if filtros.fecha_desde is not None:
        stmt = stmt.where(Importacion.fecha >= filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        stmt = stmt.where(Importacion.fecha <= filtros.fecha_hasta)
    if filtros.aduana:
        stmt = stmt.where(Importacion.aduana.ilike(f"%{filtros.aduana}%"))
    if filtros.pais_origen:
        stmt = stmt.where(Importacion.pais_origen.ilike(f"%{filtros.pais_origen}%"))
    if filtros.partida:
        stmt = stmt.where(Importacion.partida_arancelaria.like(f"%{filtros.partida}%"))
    if filtros.importador:
        stmt = stmt.where(Importacion.importador.ilike(f"%{filtros.importador}%"))
    if filtros.exportador:
        stmt = stmt.where(Importacion.exportador.ilike(f"%{filtros.exportador}%"))
    return stmt


def ranking(
    dimension: list,
    filtros: Filtros,
    order_by: str = "valor_usd",
    desc: bool = True,
    extra_where=None,
) -> Select:
    valor = func.sum(Importacion.valor_total_usd)
    kg = func.sum(Importacion.qty1)
    total = func.sum(valor).over()
    total_kg = func.sum(kg).over()

    orden_col = {
        "valor_usd": valor,
        "volumen_kg": kg,
        "mes": Importacion.mes,
    }.get(order_by, valor)
    orden = orden_col.desc() if desc else orden_col.asc()
    acumulado = func.sum(valor).over(order_by=orden, rows=(None, 0))

    stmt = select(
        *dimension,
        valor.label("valor_usd"),
        kg.label("volumen_kg"),
        func.count().label("registros"),
        (valor / func.nullif(kg, 0)).label("costo_unit_ponderado"),
        (valor * 100.0 / func.nullif(total, 0)).label("pct_total"),
        (acumulado * 100.0 / func.nullif(total, 0)).label("pct_acumulado"),
        (kg * 100.0 / func.nullif(total_kg, 0)).label("porcentaje"),
    ).group_by(*dimension)

    stmt = aplicar_filtros(stmt, filtros)
    if extra_where is not None:
        stmt = stmt.where(extra_where)

    return stmt.order_by(orden)


def tipo_importacion_ranking(
    filtros: Filtros,
    order_by: str = "valor_usd",
    desc: bool = True,
    solo_principales: bool = False,
) -> Select:
    if solo_principales:
        return ranking(
            [tipo_principales_expr()],
            filtros,
            order_by=order_by,
            desc=desc,
            extra_where=TIPO_PRINCIPAL_WHERE,
        )
    return ranking(DIM_TIPO, filtros, order_by=order_by, desc=desc)


def kpis(db: Session, filtros: Filtros) -> Mapping:
    valor = func.sum(Importacion.valor_total_usd)
    kg = func.sum(Importacion.qty1)

    stmt = select(
        valor.label("valor_total_usd"),
        kg.label("volumen_total_kg"),
        func.count().label("registros"),
        (valor / func.nullif(kg, 0)).label("costo_unit_ponderado"),
        func.count(distinct(Importacion.importador)).label("importadores"),
        func.count(distinct(Importacion.exportador)).label("exportadores"),
        func.count(distinct(Importacion.partida_arancelaria)).label("partidas"),
        func.count(distinct(Importacion.pais_origen)).label("paises_origen"),
    )
    stmt = aplicar_filtros(stmt, filtros)
    return db.execute(stmt).mappings().one()


def listar_importaciones(
    filtros: Filtros,
    q: str | None = None,
    order_by: str = "fecha",
    desc: bool = True,
) -> Select:
    stmt = select(*Importacion.__table__.columns)
    stmt = aplicar_filtros(stmt, filtros)
    if q:
        stmt = stmt.where(Importacion.descripcion_comercial.ilike(f"%{q}%"))
    orden_col = getattr(Importacion, order_by, Importacion.fecha)
    return stmt.order_by(orden_col.desc() if desc else orden_col.asc())


def obtener_importacion(db: Session, importacion_id: int):
    return db.get(Importacion, importacion_id)


def valores_meta(db: Session, columna) -> list:
    stmt = (
        select(columna)
        .where(columna.is_not(None))
        .distinct()
        .order_by(columna)
    )
    return [fila[0] for fila in db.execute(stmt).all()]


def meta_partidas(db: Session) -> list[dict]:
    stmt = (
        select(Importacion.partida_arancelaria, Importacion.descripcion_partida)
        .where(Importacion.partida_arancelaria.is_not(None))
        .distinct()
        .order_by(Importacion.partida_arancelaria)
    )
    return [
        {"partida_arancelaria": p, "descripcion_partida": d}
        for p, d in db.execute(stmt).all()
    ]


# ---------------------------------------------------------------------------
# Análisis comparativo mensual y matriz producto × dimensión
# ---------------------------------------------------------------------------


def sin_filtros_fecha(filtros: Filtros) -> Filtros:
    """El comparativo y sus períodos usan meses, no el rango global de fechas."""
    return replace(filtros, fecha_desde=None, fecha_hasta=None)


def _parse_mes(mes: str) -> tuple[int, int]:
    anio, numero_mes = mes.split("-")
    return int(anio), int(numero_mes)


def _mes_anterior(mes: str) -> str:
    anio, numero_mes = _parse_mes(mes)
    if numero_mes == 1:
        return f"{anio - 1}-12"
    return f"{anio}-{numero_mes - 1:02d}"


def _periodo_vacio(mes: str) -> dict:
    anio, numero_mes = _parse_mes(mes)
    ultimo_dia = monthrange(anio, numero_mes)[1]
    return {
        "mes": mes,
        "desde": date(anio, numero_mes, 1),
        "hasta": date(anio, numero_mes, ultimo_dia),
        "completo": False,
        "registros": 0,
    }


def periodos(db: Session, filtros: Filtros) -> list[dict]:
    """Meses disponibles y si están completos según el rango de datos filtrado."""
    stmt = (
        select(
            Importacion.mes.label("mes"),
            func.min(Importacion.fecha).label("desde_datos"),
            func.max(Importacion.fecha).label("hasta_datos"),
            func.count().label("registros"),
        )
        .where(Importacion.mes.is_not(None))
        .group_by(Importacion.mes)
        .order_by(Importacion.mes)
    )
    stmt = aplicar_filtros(stmt, sin_filtros_fecha(filtros))
    filas = db.execute(stmt).mappings().all()
    if not filas:
        return []

    primer_mes = filas[0]["mes"]
    ultimo_mes = filas[-1]["mes"]
    salida = []
    for fila in filas:
        mes = fila["mes"]
        anio, numero_mes = _parse_mes(mes)
        primer_dia = date(anio, numero_mes, 1)
        ultimo_dia = date(anio, numero_mes, monthrange(anio, numero_mes)[1])
        desde_datos = fila["desde_datos"]
        hasta_datos = fila["hasta_datos"]
        completo = True
        if mes == primer_mes and desde_datos and desde_datos > primer_dia:
            completo = False
        if mes == ultimo_mes and hasta_datos and hasta_datos < ultimo_dia:
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


def _dimension_columna(dimension: str):
    columnas = {
        "partida": Importacion.partida_arancelaria,
        "pais_origen": Importacion.pais_origen,
        "importador": Importacion.importador,
        "exportador": Importacion.exportador,
    }
    try:
        return columnas[dimension]
    except KeyError as exc:
        raise ValueError(f"Dimensión no soportada: {dimension}") from exc


def _dimension_select(dimension: str):
    if dimension == "partida":
        return [
            Importacion.partida_arancelaria.label("clave"),
            func.max(Importacion.descripcion_partida).label("detalle"),
        ]
    return [_dimension_columna(dimension).label("clave")]


def _dimension_group(dimension: str):
    if dimension == "partida":
        return [Importacion.partida_arancelaria]
    return [_dimension_columna(dimension)]


def _metrica_columna(metrica: str):
    return Importacion.valor_total_usd if metrica == "valor_usd" else Importacion.qty1


def _agregar_periodo(
    db: Session,
    filtros: Filtros,
    dimension: str,
    metrica: str,
    mes: str,
) -> dict[str, dict]:
    valor = _metrica_columna(metrica)
    stmt = (
        select(
            *_dimension_select(dimension),
            func.sum(valor).label("valor"),
            func.sum(Importacion.valor_total_usd).label("valor_usd"),
            func.sum(Importacion.qty1).label("volumen_kg"),
            func.count().label("registros"),
        )
        .where(Importacion.mes == mes)
        .group_by(*_dimension_group(dimension))
    )
    stmt = aplicar_filtros(stmt, filtros)
    if dimension == "exportador":
        stmt = stmt.where(SOLO_EXPORTADOR)

    salida = {}
    for fila in db.execute(stmt).mappings().all():
        clave = fila["clave"] if fila["clave"] is not None else "Sin dato"
        salida[str(clave)] = {
            "clave": str(clave),
            "detalle": fila.get("detalle"),
            "valor": float(fila["valor"] or 0),
            "valor_usd": float(fila["valor_usd"] or 0),
            "volumen_kg": float(fila["volumen_kg"] or 0),
            "registros": int(fila["registros"] or 0),
        }
    return salida


def comparativo(
    db: Session,
    filtros: Filtros,
    dimension: str = "partida",
    mes: str | None = None,
    comparar: str | None = None,
    metrica: str = "valor_usd",
    order_by: str = "delta_abs",
    top: int = 20,
    min_registros: int = 5,
) -> dict | None:
    filtros = sin_filtros_fecha(filtros)
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
            return abs(item["valor_actual"] - item["valor_previo"])

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


def _agregado_matriz(
    db: Session,
    filtros: Filtros,
    columna: str,
) -> list[dict]:
    col = _dimension_columna(columna)
    stmt = (
        select(
            Importacion.partida_arancelaria.label("partida"),
            func.max(Importacion.descripcion_partida).label("descripcion"),
            col.label("columna"),
            func.sum(Importacion.valor_total_usd).label("valor_usd"),
            func.sum(Importacion.qty1).label("volumen_kg"),
            func.count().label("registros"),
        )
        .where(Importacion.partida_arancelaria.is_not(None))
        .where(col.is_not(None))
        .group_by(Importacion.partida_arancelaria, col)
    )
    stmt = aplicar_filtros(stmt, filtros)
    return [dict(fila) for fila in db.execute(stmt).mappings().all()]


def _contar_omitidos(db: Session, filtros: Filtros, columna: str) -> dict[str, int]:
    col = _dimension_columna(columna)
    stmt = (
        select(func.count())
        .select_from(Importacion)
        .where(col.is_(None))
    )
    stmt = aplicar_filtros(stmt, filtros)
    total = int(db.scalar(stmt) or 0)
    nombre = "sin_exportador" if columna == "exportador" else "sin_pais_origen"
    return {nombre: total} if total else {}



def matriz(
    db: Session,
    filtros: Filtros,
    columna: str = "pais_origen",
    metrica: str = "valor_usd",
    top_filas: int = 20,
    top_columnas: int = 10,
    min_registros: int = 3,
) -> dict:
    filas_agregadas = _agregado_matriz(db, filtros, columna)
    if not filas_agregadas:
        return {
            "columna": columna,
            "metrica": metrica,
            "filas": [],
            "columnas": [],
            "celdas": [],
            "total": 0.0,
            "total_registros": 0,
            "omitidos": _contar_omitidos(db, filtros, columna),
        }

    def inicial() -> dict:
        return {
            "valor": 0.0,
            "valor_usd": 0.0,
            "volumen_kg": 0.0,
            "registros": 0,
        }

    totales_fila = defaultdict(inicial)
    totales_columna = defaultdict(inicial)
    descripciones = {}
    celdas = defaultdict(inicial)

    for fila in filas_agregadas:
        partida = str(fila["partida"])
        columna_valor = str(fila["columna"])
        valor = (
            float(fila["valor_usd"] or 0)
            if metrica == "valor_usd"
            else float(fila["volumen_kg"] or 0)
        )
        registro = int(fila["registros"] or 0)
        descripciones[partida] = fila["descripcion"]

        for acumulados, clave in (
            (totales_fila, partida),
            (totales_columna, columna_valor),
            (celdas, (partida, columna_valor)),
        ):
            acumulados[clave]["valor"] += valor
            acumulados[clave]["valor_usd"] += float(fila["valor_usd"] or 0)
            acumulados[clave]["volumen_kg"] += float(fila["volumen_kg"] or 0)
            acumulados[clave]["registros"] += registro

    claves_filas = sorted(
        totales_fila, key=lambda clave: totales_fila[clave]["valor"], reverse=True
    )
    claves_columnas = sorted(
        totales_columna,
        key=lambda clave: totales_columna[clave]["valor"],
        reverse=True,
    )

    filas_top = claves_filas[:top_filas]
    columnas_top = claves_columnas[:top_columnas]
    hay_otros_filas = len(claves_filas) > len(filas_top)
    hay_otros_columnas = len(claves_columnas) > len(columnas_top)

    filas = []
    for clave in filas_top:
        total = totales_fila[clave]
        filas.append(
            {
                "clave": clave,
                "etiqueta": clave,
                "detalle": descripciones.get(clave),
                "total": total["valor"],
                "registros": total["registros"],
                "es_otros": False,
            }
        )
    if hay_otros_filas:
        restantes = [clave for clave in claves_filas if clave not in set(filas_top)]
        total = inicial()
        for clave in restantes:
            for campo in total:
                total[campo] += totales_fila[clave][campo]
        filas.append(
            {
                "clave": "__otros__",
                "etiqueta": "Otros",
                "detalle": f"{len(restantes)} partidas",
                "total": total["valor"],
                "registros": total["registros"],
                "es_otros": True,
            }
        )

    columnas = []
    for clave in columnas_top:
        total = totales_columna[clave]
        columnas.append(
            {
                "clave": clave,
                "etiqueta": clave,
                "detalle": None,
                "total": total["valor"],
                "registros": total["registros"],
                "es_otros": False,
            }
        )
    if hay_otros_columnas:
        restantes = [
            clave for clave in claves_columnas if clave not in set(columnas_top)
        ]
        total = inicial()
        for clave in restantes:
            for campo in total:
                total[campo] += totales_columna[clave][campo]
        columnas.append(
            {
                "clave": "__otros__",
                "etiqueta": "Otros",
                "detalle": f"{len(restantes)} orígenes",
                "total": total["valor"],
                "registros": total["registros"],
                "es_otros": True,
            }
        )

    conjunto_filas = set(filas_top)
    conjunto_columnas = set(columnas_top)
    celdas_agrupadas = defaultdict(inicial)
    for fila in filas_agregadas:
        partida = str(fila["partida"])
        columna_valor = str(fila["columna"])
        clave_fila = partida if partida in conjunto_filas else "__otros__"
        clave_columna = (
            columna_valor if columna_valor in conjunto_columnas else "__otros__"
        )
        if clave_fila == "__otros__" and not hay_otros_filas:
            continue
        if clave_columna == "__otros__" and not hay_otros_columnas:
            continue
        valor = (
            float(fila["valor_usd"] or 0)
            if metrica == "valor_usd"
            else float(fila["volumen_kg"] or 0)
        )
        registro = int(fila["registros"] or 0)
        acumulados = celdas_agrupadas[(clave_fila, clave_columna)]
        acumulados["valor"] += valor
        acumulados["valor_usd"] += float(fila["valor_usd"] or 0)
        acumulados["volumen_kg"] += float(fila["volumen_kg"] or 0)
        acumulados["registros"] += registro

    filas_por_clave = {fila["clave"]: fila for fila in filas}
    celdas_out = []
    for fila in filas:
        total_fila = filas_por_clave[fila["clave"]]["total"]
        for columna_item in columnas:
            acumulados = celdas_agrupadas.get(
                (fila["clave"], columna_item["clave"]), inicial()
            )
            celdas_out.append(
                {
                    "fila": fila["clave"],
                    "columna": columna_item["clave"],
                    "valor": acumulados["valor"],
                    "valor_usd": acumulados["valor_usd"],
                    "volumen_kg": acumulados["volumen_kg"],
                    "registros": acumulados["registros"],
                    "share_fila": (
                        acumulados["valor"] * 100.0 / total_fila
                        if total_fila > 0
                        else None
                    ),
                    "muestra_suficiente": (
                        acumulados["registros"] >= min_registros
                    ),
                }
            )

    total = sum(totales_fila[clave]["valor"] for clave in claves_filas)
    total_registros = sum(
        totales_fila[clave]["registros"] for clave in claves_filas
    )
    return {
        "columna": columna,
        "metrica": metrica,
        "filas": filas,
        "columnas": columnas,
        "celdas": celdas_out,
        "total": total,
        "total_registros": total_registros,
        "omitidos": _contar_omitidos(db, filtros, columna),
    }
