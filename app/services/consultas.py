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
