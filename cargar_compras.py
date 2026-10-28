# -*- coding: utf-8 -*-
"""
Carga el CSV de compras por artículo en MySQL.
Por defecto reemplaza la tabla; usa --agregar para conservar lo existente.
"""

import argparse
from pathlib import Path

from app.database import engine
from app.services import compras

ARCHIVO = compras.ARCHIVO_DEFECTO


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", type=Path, default=ARCHIVO)
    parser.add_argument(
        "--agregar",
        action="store_true",
        help="Conserva los datos actuales en vez de reemplazar la tabla",
    )
    args = parser.parse_args()

    if not args.archivo.exists():
        raise SystemExit(f"No existe el archivo: {args.archivo}")

    print(f"→ Leyendo {args.archivo}…")
    detalle = compras.cargar(
        args.archivo,
        engine,
        reemplazar=not args.agregar,
        archivo_origen=args.archivo.name,
    )
    print(f"   Filas insertadas: {detalle['filas_insertadas']:,}")
    print(f"   Importe cargado: ${detalle['total_importe_mxn']:,.2f} MXN")
    print(
        "   Nacional: "
        f"{detalle['nacional']['registros']:,} filas / "
        f"${detalle['nacional']['importe_mxn']:,.2f}"
    )
    print(
        "   Internacional: "
        f"{detalle['internacional']['registros']:,} filas / "
        f"${detalle['internacional']['importe_mxn']:,.2f}"
    )
    print(f"   Duplicados exactos conservados: {detalle['duplicados_exactos']:,}")
    print(f"✅ Listo. Filas en MySQL: {detalle['filas_totales_en_bd']:,}")
    if detalle.get("copia"):
        print(f"   Copia guardada: {detalle['copia']}")
    if detalle.get("copia_error"):
        print(f"   Aviso: no se pudo guardar la copia: {detalle['copia_error']}")


if __name__ == "__main__":
    main()
