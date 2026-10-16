# -*- coding: utf-8 -*-
"""
Procesa el Excel de Veritrade (México - Importaciones)
y genera reportes de importadores, proveedores, costos y tipos de importación.
"""

import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# ------------------ CONFIGURACIÓN ------------------
ARCHIVO_ENTRADA = "Veritrade_IMPORTACIONES@HORBISMEX.COM_MXD_I_20261016125142.xlsx"
HOJA = "Veritrade"
FILA_ENCABEZADO = 5      # fila 6 en Excel (0-indexed en pandas)
DIR_SALIDA = Path("salida")
DIR_GRAFICAS = DIR_SALIDA / "graficas"
DIR_GRAFICAS.mkdir(parents=True, exist_ok=True)

# ------------------ 1. CARGA ------------------
def cargar_veritrade(ruta: str, hoja: str, fila_header: int) -> pd.DataFrame:
    df = pd.read_excel(ruta, sheet_name=hoja, header=fila_header)
    df.columns = [str(c).strip() for c in df.columns]
    # eliminar columnas sin nombre o totalmente vacías
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    return df


# ------------------ 2. LIMPIEZA ------------------
def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    # reemplazar tokens raros
    df = df.replace({"_x0000_": np.nan, "N/D": np.nan, "": np.nan})

    # normalizar textos
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": np.nan, "None": np.nan})

    # fecha
    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    # numéricos
    cols_num = [
        "Qty 1", "Qty 2",
        "U$ Valor Tot", "U$ Valor Unit 1", "U$ Valor Unit 2",
    ]
    for c in cols_num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # quitar duplicados exactos
    df = df.drop_duplicates()

    return df


# ------------------ 3. COLUMNAS CALCULADAS ------------------
def clasificar_regimen(txt: str) -> str:
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
    # Tipo de importación
    df["TipoImportacion"] = df["Regimen"].apply(clasificar_regimen)

    # ¿Es Cancún?
    aduana = df.get("Aduana", pd.Series("", index=df.index)).fillna("").str.upper()
    estado = df.get("Estado Importador", pd.Series("", index=df.index)).fillna("").str.upper()
    df["EsCancun"] = np.where(
        aduana.str.contains("CANCUN") | estado.str.contains("QUINTANA ROO"),
        "Sí", "No"
    )

    # Mes / Año
    if "Fecha" in df.columns:
        df["Mes"] = df["Fecha"].dt.to_period("M").astype(str)
        df["Año"] = df["Fecha"].dt.year

    # Costo unitario (cuidado: 0 evita división)
    if {"U$ Valor Tot", "Qty 1"}.issubset(df.columns):
        df["CostoUnitarioKg"] = np.where(
            df["Qty 1"] > 0, df["U$ Valor Tot"] / df["Qty 1"], np.nan
        )

    # Normalizar país origen
    if "País Origen" in df.columns:
        df["PaisOrigen"] = df["País Origen"].fillna("").str.upper().str.strip()

    return df


# ------------------ 4. REPORTES ------------------
def pivote_importadores(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("Importador", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Importador", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    g["%_del_Total"] = g["Valor_USD"] / g["Valor_USD"].sum() * 100
    return g.sort_values("Valor_USD", ascending=False)


def pivote_proveedores(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("Exportador", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Exportador", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    g["%_del_Total"] = g["Valor_USD"] / g["Valor_USD"].sum() * 100
    return g.sort_values("Valor_USD", ascending=False)


def pivote_paises(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("PaisOrigen", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("PaisOrigen", "size"),
    ).reset_index()
    g["%_del_Total"] = g["Valor_USD"] / g["Valor_USD"].sum() * 100
    return g.sort_values("Valor_USD", ascending=False)


def pivote_tipo_importacion(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("TipoImportacion", dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("TipoImportacion", "size"),
    ).reset_index()
    g["%_del_Total"] = g["Valor_USD"] / g["Valor_USD"].sum() * 100
    return g.sort_values("Valor_USD", ascending=False)


def pivote_partidas(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["Partida Aduanera", "Descripcion de la Partida Aduanera"],
                   dropna=False).agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Partida Aduanera", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    g["%_del_Total"] = g["Valor_USD"] / g["Valor_USD"].sum() * 100
    return g.sort_values("Valor_USD", ascending=False)


def pivote_mensual(df: pd.DataFrame) -> pd.DataFrame:
    if "Mes" not in df.columns:
        return pd.DataFrame()
    g = df.groupby("Mes").agg(
        Valor_USD=("U$ Valor Tot", "sum"),
        Volumen_KG=("Qty 1", "sum"),
        Registros=("Mes", "size"),
    ).reset_index()
    g["CostoUnit_Ponderado"] = np.where(g["Volumen_KG"] > 0,
                                        g["Valor_USD"] / g["Volumen_KG"], np.nan)
    return g.sort_values("Mes")


# ------------------ 5. GRÁFICAS ------------------
def barras_top(df, col_x, col_y, titulo, archivo, top=10, color="#1f77b4"):
    d = df.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(d[col_x], d[col_y], color=color)
    ax.set_title(titulo, fontsize=14, fontweight="bold")
    ax.set_xlabel(col_y)
    for i, v in enumerate(d[col_y]):
        ax.text(v, i, f" {v:,.0f}", va="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(DIR_GRAFICAS / archivo, dpi=150)
    plt.close()


def pastel(df, col_x, col_y, titulo, archivo):
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(df[col_y], labels=df[col_x], autopct="%1.1f%%", startangle=90)
    ax.set_title(titulo, fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(DIR_GRAFICAS / archivo, dpi=150)
    plt.close()


def linea_mensual(df, titulo, archivo):
    if df.empty:
        return
    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax1.plot(df["Mes"], df["Volumen_KG"], marker="o", color="#2ca02c", label="Volumen KG")
    ax1.set_ylabel("Volumen KG", color="#2ca02c")
    ax1.tick_params(axis="y", labelcolor="#2ca02c")
    ax2 = ax1.twinx()
    ax2.plot(df["Mes"], df["Valor_USD"], marker="s", color="#d62728", label="Valor USD")
    ax2.set_ylabel("Valor USD", color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    ax1.set_title(titulo, fontsize=14, fontweight="bold")
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(DIR_GRAFICAS / archivo, dpi=150)
    plt.close()


# ------------------ 6. EXPORTAR ------------------
def exportar(df_limpio, tablas: dict, ruta_salida: Path):
    with pd.ExcelWriter(ruta_salida, engine="xlsxwriter") as writer:
        df_limpio.to_excel(writer, sheet_name="Datos_Limpios", index=False)
        for nombre, tabla in tablas.items():
            if tabla is None or tabla.empty:
                continue
            tabla.to_excel(writer, sheet_name=nombre[:31], index=False)


# ------------------ MAIN ------------------
def main():
    print("→ Cargando archivo...")
    df = cargar_veritrade(ARCHIVO_ENTRADA, HOJA, FILA_ENCABEZADO)
    print(f"   Filas: {len(df):,}  Columnas: {df.shape[1]}")

    print("→ Limpiando...")
    df = limpiar(df)
    df = enriquecer(df)

    print("→ Generando reportes...")
    tablas = {
        "Importadores": pivote_importadores(df),
        "Importadores_Cancun": pivote_importadores(df[df["EsCancun"] == "Sí"]),
        "Proveedores": pivote_proveedores(df),
        "Paises_Origen": pivote_paises(df),
        "Tipo_Importacion": pivote_tipo_importacion(df),
        "Partidas": pivote_partidas(df),
        "Mensual": pivote_mensual(df),
    }

    print("→ Exportando Excel...")
    exportar(df, tablas, DIR_SALIDA / "veritrade_limpio.xlsx")

    print("→ Generando gráficas...")
    barras_top(tablas["Importadores"], "Importador", "Valor_USD",
               "Top 10 Importadores México (USD)", "top_importadores.png")
    barras_top(tablas["Importadores_Cancun"], "Importador", "Valor_USD",
               "Top 10 Importadores Cancún (USD)", "top_importadores_cancun.png",
               color="#ff7f0e")
    barras_top(tablas["Proveedores"], "Exportador", "Valor_USD",
               "Top 10 Proveedores (USD)", "top_proveedores.png",
               color="#2ca02c")
    pastel(tablas["Paises_Origen"].head(8), "PaisOrigen", "Valor_USD",
           "Distribución por País de Origen", "paises_origen.png")
    pastel(tablas["Tipo_Importacion"], "TipoImportacion", "Valor_USD",
           "Tipo de Importación", "tipo_importacion.png")
    linea_mensual(tablas["Mensual"], "Evolución mensual 2026",
                  "evolucion_mensual.png")

    print("\n✅ Proceso terminado.")
    print(f"   Excel:    {DIR_SALIDA / 'veritrade_limpio.xlsx'}")
    print(f"   Gráficas: {DIR_GRAFICAS}")


if __name__ == "__main__":
    main()