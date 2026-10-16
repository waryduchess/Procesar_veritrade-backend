# -*- coding: utf-8 -*-
"""
Procesa el Excel de Veritrade (México - Importaciones)
y genera un Excel limpio con hojas de análisis listas para cargar a MySQL.

Sin dependencia de matplotlib. Solo pandas + openpyxl + xlsxwriter.
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ------------------ CONFIGURACIÓN ------------------
ARCHIVO_ENTRADA = "Veritrade_IMPORTACIONES@HORBISMEX.COM_MXD_I_20261016125142.xlsx"
HOJA_ENTRADA    = "Veritrade"
FILA_ENCABEZADO = 5                 # fila 6 en Excel (0-indexed en pandas)

DIR_SALIDA      = Path("salida")
ARCHIVO_SALIDA  = DIR_SALIDA / "veritrade_limpio.xlsx"
DIR_SALIDA.mkdir(parents=True, exist_ok=True)


# ------------------ 1. CARGA ------------------
def cargar_veritrade(ruta: str, hoja: str, fila_header: int) -> pd.DataFrame:
    """Carga el Excel saltando las filas de metadatos."""
    df = pd.read_excel(ruta, sheet_name=hoja, header=fila_header)
    df.columns = [str(c).strip() for c in df.columns]

    # Quitar columnas sin nombre (vacías o residuales)
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    return df


# ------------------ 2. LIMPIEZA ------------------
def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza textos, tipos y valores centinela."""

    # Reemplazar centinelas por NaN
    df = df.replace({"_x0000_": np.nan, "N/D": np.nan, "": np.nan, "nan": np.nan})

    # Columnas de texto: strip y tratar cadenas "nan"
    cols_texto = df.select_dtypes(include=["object", "string"]).columns
    for col in cols_texto:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace({"nan": pd.NA, "None": pd.NA, "<NA>": pd.NA})

    # Fecha
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    # Numéricos
    for c in ["Qty 1", "Qty 2", "U$ Valor Tot", "U$ Valor Unit 1", "U$ Valor Unit 2"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Duplicados exactos
    df = df.drop_duplicates().reset_index(drop=True)
    return df


# ------------------ 3. COLUMNAS CALCULADAS ------------------
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
    """Agrega columnas calculadas usadas en los reportes."""

    # Tipo de importación
    df["TipoImportacion"] = df["Regimen"].apply(clasificar_regimen)

    # ¿Es Cancún?
    aduana = df.get("Aduana", pd.Series("", index=df.index)).fillna("").str.upper()
    estado = df.get("Estado Importador", pd.Series("", index=df.index)).fillna("").str.upper()
    df["EsCancun"] = np.where(
        aduana.str.contains("CANCUN", na=False) | estado.str.contains("QUINTANA ROO", na=False),
        "Sí", "No"
    )

    # Mes / Año
    if "Fecha" in df.columns:
        df["Mes"] = df["Fecha"].dt.to_period("M").astype("string")
        df["Año"] = df["Fecha"].dt.year.astype("Int64")

    # Costo unitario ponderado por registro (Valor / Kg)
    if {"U$ Valor Tot", "Qty 1"}.issubset(df.columns):
        df["CostoUnitarioKg"] = np.where(
            df["Qty 1"] > 0, df["U$ Valor Tot"] / df["Qty 1"], np.nan
        )

    # País origen normalizado
    if "País Origen" in df.columns:
        df["PaisOrigen"] = df["País Origen"].fillna("").str.upper().str.strip()
    else:
        df["PaisOrigen"] = ""

    return df


# ------------------ 4. TABLAS DE ANÁLISIS ------------------
def _costo_ponderado(valor: pd.Series, kg: pd.Series) -> float:
    total_kg = kg.sum()
    return valor.sum() / total_kg if total_kg else np.nan


def pivote_importadores(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("Importador", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Importador", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    total = g["Valor_USD"].sum()
    g["%_del_Total"] = (g["Valor_USD"] / total * 100).round(4) if total else 0
    return g.sort_values("Valor_USD", ascending=False).reset_index(drop=True)


def pivote_proveedores(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("Exportador", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Exportador", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    total = g["Valor_USD"].sum()
    g["%_del_Total"] = (g["Valor_USD"] / total * 100).round(4) if total else 0
    return g.sort_values("Valor_USD", ascending=False).reset_index(drop=True)


def pivote_paises(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("PaisOrigen", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("PaisOrigen", "size"),
    ).reset_index()
    total = g["Valor_USD"].sum()
    g["%_del_Total"] = (g["Valor_USD"] / total * 100).round(4) if total else 0
    return g.sort_values("Valor_USD", ascending=False).reset_index(drop=True)


def pivote_tipo_importacion(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("TipoImportacion", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("TipoImportacion", "size"),
    ).reset_index()
    total = g["Valor_USD"].sum()
    g["%_del_Total"] = (g["Valor_USD"] / total * 100).round(4) if total else 0
    return g.sort_values("Valor_USD", ascending=False).reset_index(drop=True)


def pivote_partidas(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["Partida Aduanera", "Descripcion de la Partida Aduanera"],
                   dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Partida Aduanera", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
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
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    return g.sort_values("Mes").reset_index(drop=True)


# ------------------ 5. EXPORTACIÓN ------------------
def exportar(df_limpio: pd.DataFrame, tablas: dict, ruta: Path) -> None:
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as writer:
        df_limpio.to_excel(writer, sheet_name="Datos_Limpios", index=False)
        for nombre, tabla in tablas.items():
            if tabla is None or tabla.empty:
                continue
            tabla.to_excel(writer, sheet_name=nombre[:31], index=False)


# ------------------ MAIN ------------------
def main():
    print("→ Cargando archivo…")
    df = cargar_veritrade(ARCHIVO_ENTRADA, HOJA_ENTRADA, FILA_ENCABEZADO)
    print(f"   Filas: {len(df):,}  Columnas: {df.shape[1]}")

    print("→ Limpiando…")
    df = limpiar(df)
    print(f"   Filas tras dedupe: {len(df):,}")

    print("→ Enriqueciendo…")
    df = enriquecer(df)

    print("→ Generando reportes…")
    tablas = {
        "Importadores":        pivote_importadores(df),
        "Importadores_Cancun": pivote_importadores(df[df["EsCancun"] == "Sí"]),
        "Proveedores":         pivote_proveedores(df),
        "Paises_Origen":       pivote_paises(df),
        "Tipo_Importacion":    pivote_tipo_importacion(df),
        "Partidas":            pivote_partidas(df),
        "Mensual":             pivote_mensual(df),
    }

    print("→ Exportando Excel…")
    exportar(df, tablas, ARCHIVO_SALIDA)

    print("\n✅ Proceso terminado.")
    print(f"   Archivo: {ARCHIVO_SALIDA}")

    print("\n   Hojas generadas:")
    for nombre, tabla in tablas.items():
        if tabla is not None and not tabla.empty:
            print(f"     · {nombre:<22} {len(tabla):>5} filas")


if __name__ == "__main__":
    main()