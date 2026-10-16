from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

ARCHIVO_DEFECTO = Path("salida/veritrade_limpio.xlsx")
HOJA = "Datos_Limpios"

MAPEO = {
    "Partida Aduanera": "partida_arancelaria",
    "Descripcion de la Partida Aduanera": "descripcion_partida",
    "Aduana": "aduana",
    "DUA": "dua",
    "NroSerie": "numero_serie",
    "Fecha": "fecha",
    "Cod. Tributario": "codigo_tributario",
    "Importador": "importador",
    "Ciudad Importador": "ciudad_importador",
    "Dirección Importador": "direccion_importador",
    "Estado Importador": "estado_importador",
    "Exportador": "exportador",
    "Ciudad del Exportador": "ciudad_exportador",
    "Dirección del Exportador": "direccion_exportador",
    "Qty 1": "qty1",
    "Und 1": "und1",
    "Qty 2": "qty2",
    "Und 2": "und2",
    "U$ Valor Tot": "valor_total_usd",
    "U$ Valor Unit 1": "valor_unit1_usd",
    "U$ Valor Unit 2": "valor_unit2_usd",
    "País Origen": "pais_origen",
    "Pais de Compra": "pais_compra",
    "Via": "via",
    "Descripción Comercial": "descripcion_comercial",
    "Regimen": "regimen",
    "TipoImportacion": "tipo_importacion",
    "EsCancun": "es_cancun",
    "CostoUnitarioKg": "costo_unitario_kg",
    "Mes": "mes",
    "Año": "anio",
}


def cargar_dataframe(ruta=ARCHIVO_DEFECTO, hoja: str = HOJA) -> pd.DataFrame:
    df = pd.read_excel(ruta, sheet_name=hoja)
    df = df.rename(columns=MAPEO)

    columnas_sql = [c for c in MAPEO.values() if c in df.columns]
    df = df[columnas_sql]

    df["es_cancun"] = df["es_cancun"].map({"Sí": 1, "No": 0}).fillna(0).astype(int)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df["mes"] = df["mes"].astype(str)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")

    return df.where(pd.notna(df), None)


def cargar(ruta, engine: Engine, hoja: str = HOJA) -> dict:
    df = cargar_dataframe(ruta, hoja)

    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0;"))
        conn.execute(text("TRUNCATE TABLE importaciones;"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1;"))

    df.to_sql(
        "importaciones",
        engine,
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi",
    )

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM importaciones")).scalar()

    return {"filas_insertadas": len(df), "filas_totales_en_bd": total}
