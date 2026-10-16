import csv
import io
from decimal import Decimal
from typing import Mapping

import pandas as pd

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MEDIA_TYPE = "text/csv"


def _normalizar(rows: list[Mapping]) -> list[dict]:
    normalizadas = []
    for row in rows:
        fila = {}
        for clave, valor in row.items():
            if isinstance(valor, Decimal):
                valor = float(valor)
            fila[clave] = valor
        normalizadas.append(fila)
    return normalizadas


def generar(rows: list[Mapping], formato: str) -> tuple[bytes, str]:
    filas = _normalizar(rows)

    if formato == "csv":
        buffer = io.StringIO()
        if filas:
            writer = csv.DictWriter(buffer, fieldnames=list(filas[0].keys()))
            writer.writeheader()
            writer.writerows(filas)
        return buffer.getvalue().encode("utf-8-sig"), CSV_MEDIA_TYPE

    buffer_bytes = io.BytesIO()
    with pd.ExcelWriter(buffer_bytes, engine="xlsxwriter") as writer:
        pd.DataFrame(filas).to_excel(writer, index=False, sheet_name="Datos")
    return buffer_bytes.getvalue(), XLSX_MEDIA_TYPE
