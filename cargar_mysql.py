# -*- coding: utf-8 -*-
"""
Lee veritrade_limpio.xlsx (hoja Datos_Limpios) y lo inserta en MySQL.
Por defecto reemplaza la tabla; usa --agregar para conservar lo existente.
"""

import argparse
from pathlib import Path

from app.database import engine
from app.services import cargar

ARCHIVO = Path("salida/veritrade_limpio.xlsx")
HOJA = "Datos_Limpios"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", type=Path, default=ARCHIVO)
    parser.add_argument("--hoja", default=HOJA)
    parser.add_argument(
        "--agregar",
        action="store_true",
        help="Conserva los datos actuales en vez de reemplazar la tabla",
    )
    args = parser.parse_args()

    if not args.archivo.exists():
        raise SystemExit(f"No existe el archivo: {args.archivo}")

    print(f"→ Leyendo {args.archivo}…")
    detalle = cargar.cargar(
        args.archivo,
        engine,
        hoja=args.hoja,
        reemplazar=not args.agregar,
    )
    print(f"   Filas insertadas: {detalle['filas_insertadas']:,}")
    print(f"✅ Listo. Filas en MySQL: {detalle['filas_totales_en_bd']:,}")
    if detalle.get("copia"):
        print(f"   Copia guardada: {detalle['copia']}")
    if detalle.get("copia_error"):
        print(f"   Aviso: no se pudo guardar la copia: {detalle['copia_error']}")


if __name__ == "__main__":
    main()
