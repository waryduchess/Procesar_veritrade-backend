from pathlib import Path

import numpy as np
import pandas as pd

HOJA_DEFECTO = "Veritrade"
FILA_ENCABEZADO_DEFECTO = 5


def cargar_excel(
    ruta: str, hoja: str = HOJA_DEFECTO, fila_header: int = FILA_ENCABEZADO_DEFECTO
) -> pd.DataFrame:
    df = pd.read_excel(ruta, sheet_name=hoja, header=fila_header)
    df.columns = [str(c).strip() for c in df.columns]
    return df.loc[:, ~df.columns.str.match(r"^Unnamed")]


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.replace({"_x0000_": None, "N/D": None, "": None, "nan": None})

    cols_texto = df.select_dtypes(include=["object", "string"]).columns
    for col in cols_texto:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "<NA>": None})

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    for c in ["Qty 1", "Qty 2", "U$ Valor Tot", "U$ Valor Unit 1", "U$ Valor Unit 2"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.drop_duplicates().reset_index(drop=True)


def clasificar_regimen(txt) -> str:
    if not isinstance(txt, str):
        return "Otro"
    t = txt.upper()
    if "EXTRACCION DE DEPOSITO FISCAL" in t:
        return "Extracción depósito fiscal"
    if "DEPOSITO FISCAL" in t:
        return "Depósito fiscal"
    if "REEXPEDICION" in t:
        return "Reexpedición"
    if "IMPORTACION DEFINITIVA" in t and "FRANJA" in t:
        return "Importación definitiva franja"
    if "IMPORTACION DEFINITIVA" in t:
        return "Importación definitiva"
    return "Otro"


def enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    df["TipoImportacion"] = df["Regimen"].apply(clasificar_regimen)

    aduana = df.get("Aduana", pd.Series("", index=df.index)).fillna("").str.upper()
    estado = df.get("Estado Importador", pd.Series("", index=df.index)).fillna("").str.upper()
    df["EsCancun"] = [
        "Sí" if ("CANCUN" in a or "QUINTANA ROO" in e) else "No"
        for a, e in zip(aduana, estado)
    ]

    if "Fecha" in df.columns:
        df["Mes"] = df["Fecha"].dt.to_period("M").astype("string")
        df["Año"] = df["Fecha"].dt.year.astype("Int64")

    if {"U$ Valor Tot", "Qty 1"}.issubset(df.columns):
        df["CostoUnitarioKg"] = df.apply(
            lambda r: r["U$ Valor Tot"] / r["Qty 1"]
            if pd.notna(r["Qty 1"]) and r["Qty 1"] > 0
            else None,
            axis=1,
        )

    if "País Origen" in df.columns:
        df["PaisOrigen"] = df["País Origen"].fillna("").str.upper().str.strip()
    else:
        df["PaisOrigen"] = ""

    return df


def pivote_por(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    g = df.groupby(columna, dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=(columna, "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = g.apply(
        lambda r: r["Valor_USD"] / r["Volumen_KG"]
        if r["Volumen_KG"] and r["Volumen_KG"] > 0
        else None,
        axis=1,
    )
    total = g["Valor_USD"].sum()
    g["%_del_Total"] = (g["Valor_USD"] / total * 100).round(4) if total else 0
    return g.sort_values("Valor_USD", ascending=False).reset_index(drop=True)


def pivote_partidas(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(
        ["Partida Aduanera", "Descripcion de la Partida Aduanera"], dropna=False
    ).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Partida Aduanera", "size"),
    ).reset_index()
    total = g["Valor_USD"].sum()
    g["%_del_Total"] = (g["Valor_USD"] / total * 100).round(4) if total else 0
    return g.sort_values("Valor_USD", ascending=False).reset_index(drop=True)


def pivote_mensual(df: pd.DataFrame) -> pd.DataFrame:
    if "Mes" not in df.columns or df["Mes"].isna().all():
        return pd.DataFrame()
    g = df.groupby("Mes", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Mes", "size"),
    ).reset_index()
    return g.sort_values("Mes").reset_index(drop=True)


def generar_tablas(df: pd.DataFrame) -> dict:
    return {
        "Importadores": pivote_por(df, "Importador"),
        "Importadores_Cancun": pivote_por(df[df["EsCancun"] == "Sí"], "Importador"),
        "Proveedores": pivote_por(df, "Exportador"),
        "Paises_Origen": pivote_por(df, "PaisOrigen"),
        "Tipo_Importacion": pivote_por(df, "TipoImportacion"),
        "Partidas": pivote_partidas(df),
        "Mensual": pivote_mensual(df),
    }


def exportar(df_limpio: pd.DataFrame, tablas: dict, ruta) -> None:
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as writer:
        df_limpio.to_excel(writer, sheet_name="Datos_Limpios", index=False)
        for nombre, tabla in tablas.items():
            if tabla is None or tabla.empty:
                continue
            tabla.to_excel(writer, sheet_name=nombre[:31], index=False)


def procesar(
    ruta_entrada,
    ruta_salida,
    hoja: str = HOJA_DEFECTO,
    fila_header: int = FILA_ENCABEZADO_DEFECTO,
) -> dict:
    df = cargar_excel(ruta_entrada, hoja, fila_header)
    filas_entrada = len(df)

    df = limpiar(df)
    df = enriquecer(df)
    tablas = generar_tablas(df)
    exportar(df, tablas, ruta_salida)

    return {
        "filas_entrada": filas_entrada,
        "filas_limpias": len(df),
        "columnas": int(df.shape[1]),
        "archivo_salida": str(ruta_salida),
        "tablas": {k: len(v) for k, v in tablas.items() if v is not None and not v.empty},
    }
