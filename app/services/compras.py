from __future__ import annotations

import csv
import json
import re
import shutil
import unicodedata
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from app.models import CompraArticulo

BASE_DIR = Path(__file__).resolve().parents[2]
ARCHIVO_DEFECTO = BASE_DIR / "ComprasporartículoBD707.csv"
DIR_COPIAS = BASE_DIR / "uploads" / "compras"
ARCHIVO_PROVEEDORES = BASE_DIR / "app" / "data" / "proveedores_internacionales.json"
MONEDA = "MXN"

COLUMNAS_CSV = [
    "Fecha",
    "Categoría",
    "Fraccion Arancelaria",
    "Descripción (ventas)",
    "Cantidad",
    "Importe (bruto)",
    "Precio unitario",
    "Proveedor",
]

COLUMNAS_TABLA = [
    "fecha",
    "categoria",
    "fraccion_arancelaria",
    "fraccion_valida",
    "descripcion",
    "cantidad",
    "importe_mxn",
    "precio_unitario_mxn",
    "moneda",
    "proveedor",
    "ambito",
    "anio",
    "mes",
    "archivo_origen",
    "fila_origen",
]

PROVEEDORES_INTERNACIONALES_DEFECTO = {
    "IMPORTACIONES ESPECIALIZADAS ANGELION",
    "DISTRIBUIDORA VALBI",
}

_SUFIJO_SA = re.compile(
    r"\s+(?:S\s*A\s+DE\s+C\s*V|S\s+DE\s+R\s*L\s+DE\s+C\s*V|SAPI\s+DE\s+C\s*V)$"
)


def _normalizar_espacios(valor: str | None) -> str:
    if valor is None:
        return ""
    return re.sub(r"\s+", " ", str(valor).replace("\t", " ")).strip()


def _clave_proveedor(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[.,]", " ", texto.upper())
    texto = _normalizar_espacios(texto)
    return _SUFIJO_SA.sub("", texto).strip()


def _cargar_proveedores_internacionales() -> set[str]:
    if not ARCHIVO_PROVEEDORES.exists():
        return set(PROVEEDORES_INTERNACIONALES_DEFECTO)
    try:
        data = json.loads(ARCHIVO_PROVEEDORES.read_text(encoding="utf-8"))
        valores = data.get("proveedores", [])
        claves = {_clave_proveedor(str(valor)) for valor in valores if str(valor).strip()}
        return claves or set(PROVEEDORES_INTERNACIONALES_DEFECTO)
    except (OSError, ValueError, TypeError):
        return set(PROVEEDORES_INTERNACIONALES_DEFECTO)


def _decimal(valor: str | None) -> Decimal | None:
    texto = _normalizar_espacios(valor)
    if not texto:
        return None
    texto = texto.replace("$", "").replace(",", "").replace(" ", "")
    if texto.startswith("(") and texto.endswith(")"):
        texto = f"-{texto[1:-1]}"
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico inválido: {valor!r}") from exc


def _fecha(valor: str | None) -> date:
    texto = _normalizar_espacios(valor)
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: {valor!r}")


def _fraccion_valida(valor: str | None) -> bool:
    if not valor:
        return False
    digitos = re.sub(r"[^0-9]", "", valor)
    return len(digitos) >= 4


def _leer_filas(ruta: Path) -> list[list[str]]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with ruta.open("r", encoding=encoding, newline="") as archivo:
                return [fila for fila in csv.reader(archivo)]
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer el archivo: codificación no reconocida.")


def leer_csv(ruta: Path) -> dict:
    filas = _leer_filas(ruta)
    if not filas:
        raise ValueError("El archivo CSV está vacío.")

    indice_header = None
    for indice, fila in enumerate(filas):
        encabezados = [_normalizar_espacios(celda) for celda in fila]
        if (
            encabezados
            and encabezados[0].casefold() == "fecha"
            and "proveedor" in {campo.casefold() for campo in encabezados}
        ):
            indice_header = indice
            break
    if indice_header is None:
        raise ValueError(
            "No se encontró el encabezado de compras. Se esperaba una fila con Fecha y Proveedor."
        )

    encabezados = [_normalizar_espacios(celda) for celda in filas[indice_header]]
    mapa = {nombre: posicion for posicion, nombre in enumerate(encabezados)}
    faltantes = [columna for columna in COLUMNAS_CSV if columna not in mapa]
    if faltantes:
        raise ValueError(
            "Faltan columnas obligatorias en el CSV: " + ", ".join(faltantes)
        )

    proveedores_internacionales = _cargar_proveedores_internacionales()
    registros: list[dict] = []
    total_declarado: Decimal | None = None
    duplicados: Counter[tuple] = Counter()
    filas_cero = 0
    fracciones_validas = 0
    fracciones_invalidas = 0
    sin_fraccion = 0

    for posicion, fila in enumerate(filas[indice_header + 1 :], start=indice_header + 2):
        if not any(_normalizar_espacios(celda) for celda in fila):
            continue

        def valor(columna: str) -> str | None:
            indice = mapa[columna]
            if indice >= len(fila):
                return None
            texto = _normalizar_espacios(fila[indice])
            return texto or None

        fecha_texto = valor("Fecha")
        if fecha_texto and fecha_texto.casefold() == "total":
            total_declarado = _decimal(valor("Importe (bruto)"))
            continue

        try:
            fecha = _fecha(fecha_texto)
            cantidad = _decimal(valor("Cantidad"))
            importe = _decimal(valor("Importe (bruto)"))
            precio = _decimal(valor("Precio unitario"))
            descripcion = valor("Descripción (ventas)")
            proveedor = valor("Proveedor")

            if importe is None:
                raise ValueError("El importe es obligatorio.")
            if not descripcion:
                raise ValueError("La descripción es obligatoria.")
            if not proveedor:
                raise ValueError("El proveedor es obligatorio.")
        except ValueError as exc:
            raise ValueError(f"Fila {posicion}: {exc}") from exc

        categoria = valor("Categoría")
        fraccion = valor("Fraccion Arancelaria")
        valida = _fraccion_valida(fraccion)
        if valida:
            fracciones_validas += 1
        elif fraccion:
            fracciones_invalidas += 1
        else:
            sin_fraccion += 1
        if (cantidad is None or cantidad == 0) and importe == 0:
            filas_cero += 1

        ambito = (
            "internacional"
            if _clave_proveedor(proveedor) in proveedores_internacionales
            else "nacional"
        )
        registro = {
            "fecha": fecha,
            "categoria": categoria,
            "fraccion_arancelaria": fraccion,
            "fraccion_valida": valida,
            "descripcion": descripcion,
            "cantidad": float(cantidad) if cantidad is not None else None,
            "importe_mxn": float(importe),
            "precio_unitario_mxn": float(precio) if precio is not None else None,
            "moneda": MONEDA,
            "proveedor": proveedor,
            "ambito": ambito,
            "anio": fecha.year,
            "mes": f"{fecha.year}-{fecha.month:02d}",
            "archivo_origen": ruta.name,
            "fila_origen": posicion,
        }
        registros.append(registro)
        duplicados[
            (
                fecha,
                categoria,
                fraccion,
                descripcion,
                cantidad,
                importe,
                precio,
                proveedor,
            )
        ] += 1

    if not registros:
        raise ValueError("El CSV no contiene registros de compras.")

    total_calculado = sum(Decimal(str(fila["importe_mxn"])) for fila in registros)
    if total_declarado is not None:
        descuadre = total_calculado - total_declarado
        if abs(descuadre) > Decimal("0.01"):
            raise ValueError(
                "El total del CSV no coincide con la suma de sus filas: "
                f"declarado {total_declarado:,.2f} vs calculado {total_calculado:,.2f}."
            )
    else:
        total_declarado = total_calculado

    return {
        "filas": registros,
        "total_calculado": total_calculado,
        "total_declarado": total_declarado,
        "duplicados_exactos": sum(
            cantidad - 1 for cantidad in duplicados.values() if cantidad > 1
        ),
        "filas_cero": filas_cero,
        "fracciones_validas": fracciones_validas,
        "fracciones_invalidas": fracciones_invalidas,
        "sin_fraccion": sin_fraccion,
        "fecha_min": min(fila["fecha"] for fila in registros),
        "fecha_max": max(fila["fecha"] for fila in registros),
    }


def _guardar_copia(ruta: Path, modo: str) -> Path:
    DIR_COPIAS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = DIR_COPIAS / f"compras_{timestamp}_{modo}_{ruta.name}"
    shutil.copy2(ruta, destino)
    return destino


def _resumen_ambitos(engine: Engine) -> dict[str, dict[str, float | int]]:
    stmt = (
        select(
            CompraArticulo.ambito,
            func.count().label("registros"),
            func.coalesce(func.sum(CompraArticulo.importe_mxn), 0).label("importe"),
        )
        .group_by(CompraArticulo.ambito)
    )
    with engine.connect() as conn:
        filas = conn.execute(stmt).mappings().all()
    resumen = {
        "nacional": {"registros": 0, "importe_mxn": 0.0},
        "internacional": {"registros": 0, "importe_mxn": 0.0},
    }
    for fila in filas:
        resumen[str(fila["ambito"])] = {
            "registros": int(fila["registros"] or 0),
            "importe_mxn": float(fila["importe"] or 0),
        }
    return resumen


def cargar(
    ruta: Path | str,
    engine: Engine,
    reemplazar: bool = True,
    guardar_copia: bool = True,
    archivo_origen: str | None = None,
) -> dict:
    ruta = Path(ruta)
    datos = leer_csv(ruta)
    filas = datos["filas"]
    for fila in filas:
        if archivo_origen:
            fila["archivo_origen"] = archivo_origen

    CompraArticulo.__table__.create(bind=engine, checkfirst=True)

    df = pd.DataFrame(filas, columns=COLUMNAS_TABLA)
    with engine.begin() as conn:
        if reemplazar:
            conn.execute(CompraArticulo.__table__.delete())
        df.to_sql(
            CompraArticulo.__tablename__,
            conn,
            if_exists="append",
            index=False,
            chunksize=500,
            method="multi",
        )

    with engine.connect() as conn:
        total_bd = conn.execute(
            select(func.count()).select_from(CompraArticulo)
        ).scalar_one()

    resumen = _resumen_ambitos(engine)
    modo = "reemplazar" if reemplazar else "agregar"
    detalle = {
        "archivo": str(ruta),
        "archivo_origen": archivo_origen or ruta.name,
        "modo": modo,
        "filas_leidas": len(filas),
        "filas_insertadas": len(filas),
        "filas_totales_en_bd": int(total_bd or 0),
        "total_importe_mxn": float(datos["total_calculado"]),
        "total_csv_mxn": float(datos["total_declarado"]),
        "descuadre_mxn": float(datos["total_calculado"] - datos["total_declarado"]),
        "nacional": resumen["nacional"],
        "internacional": resumen["internacional"],
        "duplicados_exactos": int(datos["duplicados_exactos"]),
        "filas_cero": int(datos["filas_cero"]),
        "fracciones_validas": int(datos["fracciones_validas"]),
        "fracciones_invalidas": int(datos["fracciones_invalidas"]),
        "sin_fraccion": int(datos["sin_fraccion"]),
        "fecha_min": datos["fecha_min"],
        "fecha_max": datos["fecha_max"],
    }

    if guardar_copia:
        try:
            detalle["copia"] = str(_guardar_copia(ruta, modo))
        except OSError as exc:
            detalle["copia_error"] = str(exc)

    return detalle
