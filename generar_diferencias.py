import pandas as pd
import os
from datetime import datetime

RUTA_CARPETA = r"C:/suplementos/stock-suplementos/"
ARCHIVO_INVENTARIO = "ListaInvFisic.csv"
ARCHIVO_WOOCOMMERCE = "wc-product-export-29-5-2026-1780069665677.csv"


def detectar_delimitador(ruta_archivo):
    with open(ruta_archivo, 'r', encoding='ISO-8859-1', errors='ignore') as f:
        sample = f.readline()
        delimiters = {',': ',', ';': ';', '\t': '\t'}
        return max(delimiters, key=lambda d: sample.count(delimiters[d]))


def cargar_datos():
    delimitador = detectar_delimitador(RUTA_CARPETA + ARCHIVO_INVENTARIO)
    df_fisico = pd.read_csv(
        RUTA_CARPETA + ARCHIVO_INVENTARIO,
        delimiter=delimitador,
        encoding='ISO-8859-1',
        dtype={'Codigo': str}
    )
    df_wc = pd.read_csv(
        RUTA_CARPETA + ARCHIVO_WOOCOMMERCE,
        dtype={'SKU': str}
    )
    return df_fisico, df_wc


def limpiar_y_validar(df_fisico, df_wc):
    errores = []

    if not {'Codigo', 'Cant.Total'}.issubset(df_fisico.columns):
        errores.append("El archivo fisico debe tener los campos 'Codigo' y 'Cant.Total'.")
    if not {'SKU', 'Inventario', 'ID'}.issubset(df_wc.columns):
        errores.append("El archivo WooCommerce debe tener los campos 'SKU', 'Inventario' e 'ID'.")

    if errores:
        for e in errores:
            print(f"  ERROR: {e}")
        exit()

    df_fisico['Codigo'] = df_fisico['Codigo'].str.strip()
    df_wc['SKU'] = df_wc['SKU'].str.strip()
    df_wc['Inventario'] = pd.to_numeric(df_wc['Inventario'], errors='coerce').fillna(0).astype(int)

    return df_fisico, df_wc


def generar_reporte(df_fisico, df_wc):
    print("=" * 65)
    print(f"  REPORTE DE INVENTARIO - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 65)

    total_inventario = len(df_fisico)
    total_wc = len(df_wc)
    print(f"\n  Productos en inventario fisico: {total_inventario}")
    print(f"  Productos en WooCommerce:       {total_wc}")

    codigos_inv = set(df_fisico['Codigo'].dropna().unique())
    skus_wc = set(df_wc['SKU'].dropna().unique())
    skus_wc = {s for s in skus_wc if s != '' and s != 'nan'}

    coinciden = codigos_inv & skus_wc
    solo_inventario = codigos_inv - skus_wc
    solo_wc = skus_wc - codigos_inv

    print(f"\n  Coinciden (mismo codigo en ambos): {len(coinciden)}")
    print(f"  Solo en inventario fisico:          {len(solo_inventario)}")
    print(f"  Solo en WooCommerce:                {len(solo_wc)}")

    sin_sku_wc = df_wc[df_wc['SKU'].isna() | (df_wc['SKU'] == '') | (df_wc['SKU'] == 'nan')]
    print(f"  Productos WC sin SKU:               {len(sin_sku_wc)}")

    stock_desactivado = df_wc[df_wc['Inventario'] == 0]
    print(f"  Productos WC con stock desactivado:  {len(stock_desactivado)} (Inventario = 0)")

    if solo_inventario:
        print(f"\n  --- Productos SOLO en inventario (no estan en WC por SKU) ---")
        ejemplo_inv = df_fisico[df_fisico['Codigo'].isin(solo_inventario)].head(10)
        for _, row in ejemplo_inv.iterrows():
            print(f"    {row['Codigo']} - {row['Nombre']} (Cant.Total: {row['Cant.Total']})")
        if len(solo_inventario) > 10:
            print(f"    ... y {len(solo_inventario) - 10} mas")

    if solo_wc:
        print(f"\n  --- Productos SOLO en WooCommerce (no estan en inventario) ---")
        ejemplo_wc = df_wc[df_wc['SKU'].isin(solo_wc)].head(10)
        for _, row in ejemplo_wc.iterrows():
            print(f"    {row['SKU']} - {row['Nombre']} (Inventario: {row['Inventario']})")
        if len(solo_wc) > 10:
            print(f"    ... y {len(solo_wc) - 10} mas")

    if sin_sku_wc.head(5) is not None:
        print(f"\n  --- Ejemplos de productos WC sin SKU ---")
        for _, row in sin_sku_wc.head(5).iterrows():
            print(f"    ID:{row['ID']} - {row['Nombre']} (Inventario: {row['Inventario']})")

    return coinciden


def generar_actualizaciones(df_fisico, df_wc, coinciden):
    print(f"\n  --- Diferencias de stock (productos coincidentes) ---")

    inv_match = df_fisico[df_fisico['Codigo'].isin(coinciden)].copy()
    wc_match = df_wc[df_wc['SKU'].isin(coinciden)][['ID', 'SKU', 'Inventario', 'Nombre']].copy()

    inv_match['Codigo'] = inv_match['Codigo'].astype(str)
    wc_match['SKU'] = wc_match['SKU'].astype(str)

    merged = inv_match.merge(
        wc_match,
        left_on='Codigo',
        right_on='SKU',
        how='inner',
        suffixes=('_inv', '_wc')
    )

    merged['diferencia'] = merged['Cant.Total'] - merged['Inventario']

    merged['stock_status_nuevo'] = merged['Cant.Total'].apply(
        lambda x: "outofstock" if x == 0 else "instock"
    )

    cambios = merged[merged['diferencia'] != 0].copy()
    sin_cambios = merged[merged['diferencia'] == 0]

    print(f"  Productos sin cambios:           {len(sin_cambios)}")
    print(f"  Productos con cambios:           {len(cambios)}")

    if not cambios.empty:
        print(f"\n  Top 20 productos con mayor diferencia:")
        top_cambios = cambios.reindex(cambios['diferencia'].abs().sort_values(ascending=False).index).head(20)
        for _, row in top_cambios.iterrows():
            direccion = "+" if row['diferencia'] > 0 else ""
            print(f"    {row['Codigo']:>15} | {str(row.get('Nombre_inv', row.get('Nombre_wc', '')))[:40]:<40} | "
                  f"Inv: {int(row['Cant.Total']):>4} | WC: {int(row['Inventario']):>4} | "
                  f"Diff: {direccion}{int(row['diferencia'])}")

    output = cambios[['ID', 'SKU', 'Nombre_inv', 'Cant.Total', 'Inventario', 'diferencia', 'stock_status_nuevo']]
    output.columns = ['ID', 'SKU', 'Nombre', 'Stock_Nuevo', 'Stock_Actual_WC', 'Diferencia', 'stock_status']

    output_path = RUTA_CARPETA + "actualizacion_stock.csv"
    output.to_csv(output_path, index=False)
    print(f"\n  Archivo de actualizacion generado: {output_path}")
    print(f"  Registros a actualizar: {len(output)}")

    resumen_path = RUTA_CARPETA + "resumen_completo.csv"
    merged.to_csv(resumen_path, index=False)
    print(f"  Resumen completo generado: {resumen_path}")

    return output


def main():
    print("Cargando datos...")
    df_fisico, df_wc = cargar_datos()

    print("Limpiando y validando...")
    df_fisico, df_wc = limpiar_y_validar(df_fisico, df_wc)

    coinciden = generar_reporte(df_fisico, df_wc)

    actualizaciones = generar_actualizaciones(df_fisico, df_wc, coinciden)

    print(f"\n{'=' * 65}")
    print(f"  PROCESO COMPLETADO")
    print(f"  Archivos generados:")
    print(f"    - actualizacion_stock.csv  (solo productos con cambios)")
    print(f"    - resumen_completo.csv     (todos los productos cotejados)")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
