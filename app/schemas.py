from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ImportadorRow(ORMModel):
    importador: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    pct_total: float | None = None
    pct_acumulado: float | None = None
    porcentaje: float | None = None


class ProveedorRow(ORMModel):
    exportador: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    pct_total: float | None = None
    pct_acumulado: float | None = None
    porcentaje: float | None = None


class ProveedorPaisRow(ORMModel):
    exportador: str | None = None
    pais_origen: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    pct_total: float | None = None
    pct_acumulado: float | None = None
    porcentaje: float | None = None


class PaisOrigenRow(ORMModel):
    pais_origen: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    pct_total: float | None = None
    pct_acumulado: float | None = None
    porcentaje: float | None = None


class TipoImportacionRow(ORMModel):
    tipo_importacion: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    pct_total: float | None = None
    pct_acumulado: float | None = None
    porcentaje: float | None = None


class PartidaRow(ORMModel):
    partida_arancelaria: str | None = None
    descripcion_partida: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    pct_total: float | None = None
    pct_acumulado: float | None = None
    porcentaje: float | None = None


class MensualRow(ORMModel):
    mes: str | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None


class KpisOut(ORMModel):
    valor_total_usd: float | None = None
    volumen_total_kg: float | None = None
    registros: int = 0
    costo_unit_ponderado: float | None = None
    importadores: int = 0
    exportadores: int = 0
    partidas: int = 0
    paises_origen: int = 0


class ImportacionOut(ORMModel):
    id: int
    partida_arancelaria: str
    descripcion_partida: str | None = None
    aduana: str | None = None
    dua: str | None = None
    numero_serie: str | None = None
    fecha: date | None = None
    codigo_tributario: str | None = None
    importador: str | None = None
    ciudad_importador: str | None = None
    direccion_importador: str | None = None
    estado_importador: str | None = None
    exportador: str | None = None
    ciudad_exportador: str | None = None
    direccion_exportador: str | None = None
    qty1: float | None = None
    und1: str | None = None
    qty2: float | None = None
    und2: str | None = None
    valor_total_usd: float | None = None
    valor_unit1_usd: float | None = None
    valor_unit2_usd: float | None = None
    pais_origen: str | None = None
    pais_compra: str | None = None
    via: str | None = None
    descripcion_comercial: str | None = None
    regimen: str | None = None
    tipo_importacion: str | None = None
    es_cancun: int | None = None
    costo_unitario_kg: float | None = None
    anio: int | None = None
    mes: str | None = None
    creado_en: datetime | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class PartidaMeta(ORMModel):
    partida_arancelaria: str
    descripcion_partida: str | None = None


class CargarIn(BaseModel):
    ruta: str | None = None


class JobOut(ORMModel):
    id: int
    tipo: str
    estado: str
    mensaje: str | None = None
    detalle: dict | None = None
    creado_en: datetime
    terminado_en: datetime | None = None


class PreguntaOut(ORMModel):
    id: str
    categoria: str
    pregunta: str
    endpoint: str
    params: dict = Field(default_factory=dict)
    descripcion: str | None = None


class ConsultaIn(BaseModel):
    pregunta: str
    params: dict | None = None


class ConsultaOut(BaseModel):
    encontrada: bool
    pregunta: str | None = None
    id: str | None = None
    categoria: str | None = None
    endpoint: str | None = None
    params: dict | None = None
    resumen: str
    datos: Any | None = None
    sugerencias: list[str] | None = None
