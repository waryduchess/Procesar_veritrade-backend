from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Importacion(Base):
    __tablename__ = "importaciones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    partida_arancelaria: Mapped[str] = mapped_column(String(20))
    descripcion_partida: Mapped[str | None] = mapped_column(String(500))
    aduana: Mapped[str | None] = mapped_column(String(120))
    dua: Mapped[str | None] = mapped_column(String(50))
    numero_serie: Mapped[str | None] = mapped_column(String(20))
    fecha: Mapped[date | None]
    codigo_tributario: Mapped[str | None] = mapped_column(String(20))

    importador: Mapped[str | None] = mapped_column(String(255))
    ciudad_importador: Mapped[str | None] = mapped_column(String(120))
    direccion_importador: Mapped[str | None] = mapped_column(String(500))
    estado_importador: Mapped[str | None] = mapped_column(String(120))

    exportador: Mapped[str | None] = mapped_column(String(255))
    ciudad_exportador: Mapped[str | None] = mapped_column(String(120))
    direccion_exportador: Mapped[str | None] = mapped_column(String(500))

    qty1: Mapped[Decimal | None]
    und1: Mapped[str | None] = mapped_column(String(20))
    qty2: Mapped[Decimal | None]
    und2: Mapped[str | None] = mapped_column(String(20))
    valor_total_usd: Mapped[Decimal | None]
    valor_unit1_usd: Mapped[Decimal | None]
    valor_unit2_usd: Mapped[Decimal | None]

    pais_origen: Mapped[str | None] = mapped_column(String(120))
    pais_compra: Mapped[str | None] = mapped_column(String(120))
    via: Mapped[str | None] = mapped_column(String(60))
    descripcion_comercial: Mapped[str | None] = mapped_column(Text)
    regimen: Mapped[str | None] = mapped_column(Text)

    tipo_importacion: Mapped[str | None] = mapped_column(String(60))
    es_cancun: Mapped[int | None] = mapped_column(SmallInteger, default=0)
    costo_unitario_kg: Mapped[Decimal | None]
    anio: Mapped[int | None] = mapped_column(SmallInteger)
    mes: Mapped[str | None] = mapped_column(String(7))

    creado_en: Mapped[datetime | None] = mapped_column(DateTime)


class CompraArticulo(Base):
    __tablename__ = "compras_articulos"
    __table_args__ = (
        CheckConstraint(
            "ambito IN ('nacional', 'internacional')",
            name="ck_compras_ambito",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    fecha: Mapped[date] = mapped_column(Date, index=True)
    categoria: Mapped[str | None] = mapped_column(String(120), index=True)
    fraccion_arancelaria: Mapped[str | None] = mapped_column(String(30), index=True)
    fraccion_valida: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    descripcion: Mapped[str] = mapped_column(String(500))

    cantidad: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    importe_mxn: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    precio_unitario_mxn: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    moneda: Mapped[str] = mapped_column(String(3), default="MXN")

    proveedor: Mapped[str] = mapped_column(String(255), index=True)
    ambito: Mapped[str] = mapped_column(String(20), index=True)

    anio: Mapped[int] = mapped_column(SmallInteger, index=True)
    mes: Mapped[str] = mapped_column(String(7), index=True)

    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    fila_origen: Mapped[int | None]
    creado_en: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )


vista_metadata = MetaData()

v_importadores = Table(
    "v_importadores",
    vista_metadata,
    Column("importador", String(255), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("costo_unit_ponderado", Numeric(18, 6)),
    Column("pct_total", Numeric(20, 6)),
)

v_importadores_cancun = Table(
    "v_importadores_cancun",
    vista_metadata,
    Column("importador", String(255), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("costo_unit_ponderado", Numeric(18, 6)),
    Column("pct_total", Numeric(20, 6)),
)

v_proveedores = Table(
    "v_proveedores",
    vista_metadata,
    Column("exportador", String(255), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("costo_unit_ponderado", Numeric(18, 6)),
    Column("pct_total", Numeric(20, 6)),
)

v_paises_origen = Table(
    "v_paises_origen",
    vista_metadata,
    Column("pais_origen", String(120), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("pct_total", Numeric(20, 6)),
)

v_tipo_importacion = Table(
    "v_tipo_importacion",
    vista_metadata,
    Column("tipo_importacion", String(60), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("pct_total", Numeric(20, 6)),
)

v_partidas = Table(
    "v_partidas",
    vista_metadata,
    Column("partida_arancelaria", String(20), primary_key=True),
    Column("descripcion_partida", String(500), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("costo_unit_ponderado", Numeric(18, 6)),
    Column("pct_total", Numeric(20, 6)),
)

v_mensual = Table(
    "v_mensual",
    vista_metadata,
    Column("mes", String(7), primary_key=True),
    Column("valor_usd", Numeric(18, 2)),
    Column("volumen_kg", Numeric(18, 3)),
    Column("registros", BigInteger),
    Column("costo_unit_ponderado", Numeric(18, 6)),
)


class ImportadorVista(Base):
    __table__ = v_importadores


class ImportadorCancunVista(Base):
    __table__ = v_importadores_cancun


class ProveedorVista(Base):
    __table__ = v_proveedores


class PaisOrigenVista(Base):
    __table__ = v_paises_origen


class TipoImportacionVista(Base):
    __table__ = v_tipo_importacion


class PartidaVista(Base):
    __table__ = v_partidas


class MensualVista(Base):
    __table__ = v_mensual
