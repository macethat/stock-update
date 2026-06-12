import pandas as pd
import urllib.request
import json
import base64
import time
import os
import sys
from datetime import datetime

RUTA = os.path.dirname(os.path.abspath(__file__)) + "/"
WC_URL = "https://suplementospanama.net"
CONSUMER_KEY = "ck_5fa7935bad5d098c833a7e3f022e6b4ab1a70e0e"
CONSUMER_SECRET = "cs_3f5441046f1d1d064a9edbc8c04c5e4d69b2a4fa"
DELAY_SECONDS = 0.05
STOCK_LIMIT = 6


def auth_header():
    token = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": "Stock-Sync/1.0"
    }


def api_url(endpoint):
    return f"{WC_URL}/wp-json/wc/v3/{endpoint}"


def api_update(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers=auth_header(),
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.read() else str(e)
    except urllib.error.URLError as e:
        return 0, {"message": str(e.reason)}


def cargar_datos():
    delimitador = ","
    with open(RUTA + "ListaInvFisic.csv", "r", encoding="ISO-8859-1") as f:
        if ";" in f.readline():
            delimitador = ";"

    df_inv = pd.read_csv(
        RUTA + "ListaInvFisic.csv", delimiter=delimitador,
        encoding="ISO-8859-1", dtype={"Codigo": str}
    )
    df_wc = pd.read_csv(
        RUTA + "wc-product-export-30-5-2026-1780118888233.csv",
        dtype={"SKU": str, "Superior": str}
    )

    df_inv["Codigo"] = df_inv["Codigo"].str.strip()
    df_wc["SKU"] = df_wc["SKU"].str.strip()
    df_wc["Inventario"] = pd.to_numeric(df_wc["Inventario"], errors="coerce").fillna(0).astype(int)
    df_wc["Superior"] = df_wc["Superior"].str.replace("id:", "", regex=False)
    df_wc["Superior"] = pd.to_numeric(df_wc["Superior"], errors="coerce").fillna(0).astype(int)

    return df_inv, df_wc


def preparar_actualizaciones(df_inv, df_wc):
    codigos_inv = set(df_inv["Codigo"].dropna().unique())
    skus_wc = set(df_wc["SKU"].dropna().unique())
    skus_wc = {s for s in skus_wc if s != "" and s != "nan"}
    coinciden = codigos_inv & skus_wc

    wc_con_sku = df_wc[
        df_wc["SKU"].notna() & (df_wc["SKU"] != "") & (df_wc["SKU"] != "nan")
    ].copy()

    updates = []

    # Productos que coinciden: actualizar stock desde inventario
    for _, wc_row in wc_con_sku.iterrows():
        sku = wc_row["SKU"]
        if sku in coinciden:
            inv_row = df_inv[df_inv["Codigo"] == sku].iloc[0]
            new_stock = int(inv_row["Cant.Total"])
            new_status = "outofstock" if new_stock <= STOCK_LIMIT else "instock"
            updates.append({
                "id": int(wc_row["ID"]),
                "parent_id": int(wc_row["Superior"]),
                "tipo": wc_row["Tipo"],
                "sku": sku,
                "nombre": inv_row["Nombre"],
                "old_stock": int(wc_row["Inventario"]),
                "new_stock": new_stock,
                "new_status": new_status,
                "motivo": "actualizacion_inventario"
            })

    # Productos solo en WC (sin match en inventario): aplicar regla stock <= 6
    solo_wc_skus = skus_wc - codigos_inv
    for _, wc_row in wc_con_sku.iterrows():
        sku = wc_row["SKU"]
        if sku in solo_wc_skus:
            current_stock = int(wc_row["Inventario"])
            current_status_known = False
            if current_stock <= STOCK_LIMIT:
                new_status = "outofstock"
                updates.append({
                    "id": int(wc_row["ID"]),
                    "parent_id": int(wc_row["Superior"]),
                    "tipo": wc_row["Tipo"],
                    "sku": sku,
                    "nombre": wc_row["Nombre"],
                    "old_stock": current_stock,
                    "new_stock": current_stock,
                    "new_status": new_status,
                    "motivo": "stock_bajo_sin_inventario"
                })

    return updates


def ejecutar(updates, dry_run=True, resume_from=0):
    ok = 0
    fail = 0
    skipped = 0

    print(f"\n{'='*70}")
    print(f"  {'SIMULACION (DRY RUN)' if dry_run else 'ACTUALIZACION EN VIVO'}")
    print(f"  Total de actualizaciones a procesar: {len(updates)}")
    if resume_from > 0:
        print(f"  Reanudando desde el producto #{resume_from + 1}")
    print(f"{'='*70}\n")

    for i, upd in enumerate(updates, 1):
        if i <= resume_from:
            continue
        if upd["tipo"] == "variation":
            endpoint = f"products/{upd['parent_id']}/variations/{upd['id']}"
        else:
            endpoint = f"products/{upd['id']}"

        url = api_url(endpoint)
        payload = {
            "stock_quantity": upd["new_stock"],
            "stock_status": upd["new_status"],
            "manage_stock": True
        }

        cambio = upd["new_stock"] - upd["old_stock"]
        signo = "+" if cambio > 0 else ""

        print(f"  [{i}/{len(updates)}] {upd['tipo']:<9} ID:{upd['id']:<6} "
              f"SKU:{upd['sku']:<15} "
              f"Stock: {upd['old_stock']:>4} -> {upd['new_stock']:>4} "
              f"({signo}{cambio}) "
              f"Status: {upd['new_status']:<10} "
              f"[{upd['motivo']}]")

        if not dry_run:
            needs_update = (cambio != 0) or (upd["new_stock"] <= STOCK_LIMIT)
            if not needs_update:
                skipped += 1
                print(f"    -> SIN CAMBIOS (omitido)")
            else:
                status, resp = api_update(url, payload)
                if status == 200:
                    ok += 1
                    print(f"    -> OK")
                else:
                    fail += 1
                    msg = resp.get("message", str(resp)) if isinstance(resp, dict) else str(resp)
                    print(f"    -> ERROR {status}: {msg[:120]}")
                time.sleep(DELAY_SECONDS)
        else:
            if cambio == 0 and upd["motivo"] == "actualizacion_inventario":
                skipped += 1

    print(f"\n{'='*70}")
    if dry_run:
        cambios_reales = sum(1 for u in updates if u["new_stock"] != u["old_stock"])
        solo_status = len(updates) - cambios_reales
        print(f"  RESUMEN DRY RUN:")
        print(f"  Total a procesar:       {len(updates)}")
        print(f"  Con cambio de stock:    {cambios_reales}")
        print(f"  Solo cambio de status:  {solo_status}")
    else:
        print(f"  RESULTADO:")
        print(f"  Exitosos:  {ok}")
        print(f"  Fallidos:  {fail}")
    print(f"{'='*70}\n")

    return ok, fail


def exportar_reporte(updates, dry_run=True):
    df = pd.DataFrame(updates)
    nombre = "reporte_dry_run.csv" if dry_run else "reporte_actualizacion.csv"
    df.to_csv(RUTA + nombre, index=False)
    print(f"  Reporte exportado: {nombre}")

    # Resumen por motivo
    print(f"\n  Resumen por motivo:")
    for motivo, grupo in df.groupby("motivo"):
        print(f"    {motivo}: {len(grupo)} productos")


def main():
    dry_run = "--live" not in sys.argv
    resume_from = 0
    for arg in sys.argv:
        if arg.startswith("--resume="):
            resume_from = int(arg.split("=")[1])

    print(f"Cargando datos...")
    df_inv, df_wc = cargar_datos()
    print(f"  Inventario fisico: {len(df_inv)} registros")
    print(f"  WooCommerce:       {len(df_wc)} registros")

    print(f"Preparando actualizaciones...")
    updates = preparar_actualizaciones(df_inv, df_wc)

    print(f"  Productos a actualizar por inventario: {sum(1 for u in updates if u['motivo'] == 'actualizacion_inventario')}")
    print(f"  Productos solo WC con stock <= {STOCK_LIMIT}: {sum(1 for u in updates if u['motivo'] == 'stock_bajo_sin_inventario')}")

    exportar_reporte(updates, dry_run=dry_run)
    ejecutar(updates, dry_run=dry_run, resume_from=resume_from)


if __name__ == "__main__":
    main()
