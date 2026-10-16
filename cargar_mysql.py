# -*- coding: utf-8 -*-
"""
Lee veritrade_limpio.xlsx (hoja Datos_Limpios) y lo inserta en MySQL.
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from pathlib import Path

# --- Config ---
MYSQL_URL = "mysql+pymysql://veritrade:veritrade123@localhost:3306/veritrade?charset=utf8mb4"
ARCHIVO = Path("salida/veritrade_limpio.xlsx")
HOJA = "Datos_Limpios"

# Mapeo: columna Excel -> columna SQL
MAPEO = {
    "Partida Aduanera":                    "partida_arancelaria",
    "Descripcion de la Partida Aduanera":  "descripcion_partida",
    "Aduana":                              "aduana",
    "DUA":                                 "dua",
    "NroSerie":                            "numero_serie",
    "Fecha":                               "fecha",
    "Cod. Tributario":                     "codigo_tributario",
    "Importador":                          "importador",
    "Ciudad Importador":                   "ciudad_importador",
    "Dirección Importador":                "direccion_importador",
    "Estado Importador":                   "estado_importador",
    "Exportador":                          "exportador",
    "Ciudad del Exportador":               "ciudad_exportador",
    "Dirección del Exportador":            "direccion_exportador",
    "Qty 1":                               "qty1",
    "Und 1":                               "und1",
    "Qty 2":                               "qty2",
    "Und 2":                               "und2",
    "U$ Valor Tot":                        "valor_total_usd",
    "U$ Valor Unit 1":                     "valor_unit1_usd",
    "U$ Valor Unit 2":                     "valor_unit2_usd",
    "País Origen":                         "pais_origen",
    "Pais de Compra":                      "pais_compra",
    "Via":                                 "via",
    "Descripción Comercial":               "descripcion_comercial",
    "Regimen":                             "regimen",
    "TipoImportacion":                     "tipo_importacion",
    "EsCancun":                            "es_cancun",
    "CostoUnitarioKg":                     "costo_unitario_kg",
    "Mes":                                 "mes",
    "Año":                                 "anio",
}


def cargar() -> pd.DataFrame:
    df = pd.read_excel(ARCHIVO, sheet_name=HOJA)
    df = df.rename(columns=MAPEO)

    # Solo columnas que existen en el destino
    columnas_sql = [c for c in MAPEO.values() if c in df.columns]
    df = df[columnas_sql]

    # Normalizaciones finales
    df["es_cancun"] = df["es_cancun"].map({"Sí": 1, "No": 0}).fillna(0).astype(int)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df["mes"] = df["mes"].astype(str)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")

    # NaN -> None para que MySQL inserte NULL
    df = df.where(pd.notna(df), None)

    return df


def main():
    print("→ Leyendo Excel…")
    df = cargar()
    print(f"   Filas a insertar: {len(df):,}")

    engine = create_engine(MYSQL_URL, pool_pre_ping=True)

    print("→ Truncando tabla importaciones…")
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0;"))
        conn.execute(text("TRUNCATE TABLE importaciones;"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1;"))

    print("→ Insertando…")
    df.to_sql(
        "importaciones",
        engine,
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi",
    )

    # Verificación
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM importaciones")).scalar()
    print(f"✅ Listo. Filas en MySQL: {total:,}")


if __name__ == "__main__":
    main()