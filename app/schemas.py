from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

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


class MensajeHistorial(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=40000)
    modulo: Literal["importaciones", "compras", "mixto"] | None = None


class ConsultaRequest(BaseModel):
    pregunta: str = Field(min_length=1, max_length=2000)
    historial: list[MensajeHistorial] | None = Field(default=None, max_length=50)
    modulo: Literal["auto", "importaciones", "compras"] = "auto"
    modo: Literal["auto", "consulta", "informe"] = "auto"


class ToolCallOut(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class AgenteOut(BaseModel):
    respuesta: str
    tool_calls: list[ToolCallOut]
    datos_usados: list[Any]
    modo: Literal["consulta", "informe"] | None = None
    modulo: Literal["importaciones", "compras", "mixto"] | None = None


class PeriodoInfo(BaseModel):
    mes: str
    desde: date
    hasta: date
    completo: bool
    registros: int = 0


class ComparativoItem(BaseModel):
    clave: str
    etiqueta: str
    detalle: str | None = None
    valor_actual: float | None = None
    valor_previo: float | None = None
    delta_abs: float | None = None
    variacion_pct: float | None = None
    share_actual: float | None = None
    share_previo: float | None = None
    delta_pp: float | None = None
    registros_actual: int = 0
    registros_previo: int = 0
    estado: Literal["sube", "baja", "nuevo", "desaparece", "sin_cambio"]
    muestra_suficiente: bool


class ComparativoOut(BaseModel):
    periodo: PeriodoInfo
    periodo_anterior: PeriodoInfo
    periodos: list[PeriodoInfo]
    dimension: str
    metrica: str
    order_by: str
    min_registros: int
    total_actual: float | None = None
    total_previo: float | None = None
    items: list[ComparativoItem]
    total_items: int


class MatrizFila(BaseModel):
    clave: str
    etiqueta: str
    detalle: str | None = None
    total: float | None = None
    registros: int = 0
    es_otros: bool = False


class MatrizColumna(BaseModel):
    clave: str
    etiqueta: str
    detalle: str | None = None
    total: float | None = None
    registros: int = 0
    es_otros: bool = False


class MatrizCelda(BaseModel):
    fila: str
    columna: str
    valor: float | None = None
    valor_usd: float | None = None
    volumen_kg: float | None = None
    registros: int = 0
    share_fila: float | None = None
    muestra_suficiente: bool


class MatrizOut(BaseModel):
    columna: str
    metrica: str
    filas: list[MatrizFila]
    columnas: list[MatrizColumna]
    celdas: list[MatrizCelda]
    total: float | None = None
    total_registros: int = 0
    omitidos: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Compras por artículo
# ---------------------------------------------------------------------------


class CompraArticuloOut(ORMModel):
    id: int
    fecha: date
    categoria: str | None = None
    fraccion_arancelaria: str | None = None
    fraccion_valida: bool = False
    descripcion: str
    cantidad: float | None = None
    importe_mxn: float
    precio_unitario_mxn: float | None = None
    moneda: str = "MXN"
    proveedor: str
    ambito: Literal["nacional", "internacional"]
    anio: int
    mes: str
    archivo_origen: str | None = None
    fila_origen: int | None = None
    creado_en: datetime | None = None


class ComprasKpisOut(BaseModel):
    importe_total_mxn: float | None = None
    registros: int = 0
    proveedores: int = 0
    categorias: int = 0
    meses: int = 0
    importe_nacional_mxn: float | None = None
    importe_internacional_mxn: float | None = None
    pct_internacional: float | None = None
    fracciones_validas: int = 0
    fracciones_invalidas: int = 0
    sin_fraccion: int = 0
    fecha_min: date | None = None
    fecha_max: date | None = None


class CompraMensualRow(BaseModel):
    mes: str
    importe_mxn: float | None = None
    importe_nacional_mxn: float | None = None
    importe_internacional_mxn: float | None = None
    registros: int = 0
    pct_internacional: float | None = None
    completo: bool = True


class CompraCategoriaRow(BaseModel):
    categoria: str
    importe_mxn: float | None = None
    registros: int = 0
    proveedores: int = 0
    pct_importe: float | None = None
    pct_internacional: float | None = None


class CompraProveedorRow(BaseModel):
    proveedor: str
    ambito: Literal["nacional", "internacional"]
    importe_mxn: float | None = None
    registros: int = 0
    categorias: int = 0
    pct_importe: float | None = None


class CompraPrecioProductoRow(BaseModel):
    descripcion: str
    categoria: str | None = None
    anio: int
    importe_mxn: float
    cantidad: float
    precio_promedio_mxn: float | None = None
    registros: int = 0
    proveedores: int = 0
    meses: int = 0


class CompraPrecioMensualRow(BaseModel):
    mes: str
    importe_mxn: float
    cantidad: float
    precio_promedio_mxn: float | None = None
    registros: int = 0


class ComprasMetaOut(BaseModel):
    categorias: list[str] = Field(default_factory=list)
    proveedores: list[str] = Field(default_factory=list)
    fracciones: list[str] = Field(default_factory=list)
    anios: list[int] = Field(default_factory=list)
    ambitos: list[str] = Field(default_factory=lambda: ["nacional", "internacional"])
    fecha_min: date | None = None
    fecha_max: date | None = None
    total_registros: int = 0


class CompraAmbitoResumen(BaseModel):
    registros: int = 0
    importe_mxn: float = 0


class ComprasImportOut(BaseModel):
    archivo: str
    archivo_origen: str | None = None
    modo: Literal["reemplazar", "agregar"]
    filas_leidas: int
    filas_insertadas: int
    filas_totales_en_bd: int
    total_importe_mxn: float
    total_csv_mxn: float
    descuadre_mxn: float
    nacional: CompraAmbitoResumen
    internacional: CompraAmbitoResumen
    duplicados_exactos: int = 0
    filas_cero: int = 0
    fracciones_validas: int = 0
    fracciones_invalidas: int = 0
    sin_fraccion: int = 0
    fecha_min: date | None = None
    fecha_max: date | None = None
    copia: str | None = None
    copia_error: str | None = None
