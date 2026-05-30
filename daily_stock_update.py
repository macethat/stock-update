import pandas as pd
import urllib.request
import json
import base64
import time
import os
import sys
import shutil
from datetime import datetime

# === CONFIGURACION ===
CARPETA_BASE = os.path.dirname(os.path.abspath(__file__))
WC_URL = "https://suplementospanama.net"
CONSUMER_KEY = "ck_5fa7935bad5d098c833a7e3f022e6b4ab1a70e0e"
CONSUMER_SECRET = "cs_3f5441046f1d1d064a9edbc8c04c5e4d69b2a4fa"
STOCK_LIMIT = 6
API_DELAY = 0.05


def auth_header():
    token = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": "Stock-Sync/1.0"
    }


def api_get(url):
    req = urllib.request.Request(url, headers=auth_header())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ERROR API: {e}")
        return []


def api_put(url, data):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers=auth_header(), method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.read() else str(e)
    except urllib.error.URLError as e:
        return 0, {"message": str(e.reason)}


def descargar_export_wc():
    print("Descargando productos desde WooCommerce...")
    productos = []
    page = 1
    while True:
        url = f"{WC_URL}/wp-json/wc/v3/products?per_page=100&page={page}"
        data = api_get(url)
        if not data:
            break
        for p in data:
            productos.append({
                "ID": p["id"],
                "Tipo": p.get("type", ""),
                "SKU": p.get("sku", ""),
                "Nombre": p.get("name", ""),
                "Inventario": p.get("stock_quantity", 0) if p.get("stock_quantity") is not None else 0,
                "Publicado": 1 if p.get("status") == "publish" else 0,
                "Precio normal": p.get("regular_price", ""),
                "Superior": ""
            })
            if p.get("type") == "variable":
                vurl = f"{WC_URL}/wp-json/wc/v3/products/{p['id']}/variations?per_page=100"
                for v in api_get(vurl):
                    productos.append({
                        "ID": v["id"],
                        "Tipo": "variation",
                        "SKU": v.get("sku", ""),
                        "Nombre": v.get("name", ""),
                        "Inventario": v.get("stock_quantity", 0) if v.get("stock_quantity") is not None else 0,
                        "Publicado": 1 if v.get("status") == "publish" else 0,
                        "Precio normal": v.get("regular_price", ""),
                        "Superior": f"id:{p['id']}"
                    })
        print(f"  Pagina {page}: {len(data)} productos")
        page += 1
        time.sleep(0.3)

    fecha = datetime.now().strftime("%d-%m-%Y")
    nombre = f"wc-product-export-{fecha}-{int(time.time())}.csv"
    ruta = os.path.join(CARPETA_BASE, "tmp_wc_export.csv")
    df = pd.DataFrame(productos)
    df.to_csv(ruta, index=False)
    print(f"  Export descargado: {len(productos)} productos")
    return ruta


def crear_carpeta_dia():
    fecha = datetime.now().strftime("%d-%m-%Y")
    carpeta = os.path.join(CARPETA_BASE, f"update_{fecha}")
    os.makedirs(carpeta, exist_ok=True)
    print(f"Carpeta creada: {carpeta}")
    return carpeta


def procesar(inv_csv, wc_csv, carpeta, dry_run=True):
    with open(inv_csv, "r", encoding="ISO-8859-1") as f:
        delim = ";" if ";" in f.readline() else ","

    df_inv = pd.read_csv(inv_csv, delimiter=delim, encoding="ISO-8859-1", dtype={"Codigo": str})
    df_wc = pd.read_csv(wc_csv, dtype={"SKU": str, "Superior": str})

    df_inv["Codigo"] = df_inv["Codigo"].str.strip()
    df_wc["SKU"] = df_wc["SKU"].str.strip()
    df_wc["Inventario"] = pd.to_numeric(df_wc["Inventario"], errors="coerce").fillna(0).astype(int)
    if "Superior" in df_wc.columns:
        df_wc["Superior"] = df_wc["Superior"].astype(str).str.replace("id:", "", regex=False)
        df_wc["Superior"] = pd.to_numeric(df_wc["Superior"], errors="coerce").fillna(0).astype(int)
    else:
        df_wc["Superior"] = 0

    cod_inv = set(df_inv["Codigo"].dropna().unique())
    sku_wc = set(df_wc["SKU"].dropna().unique())
    sku_wc = {s for s in sku_wc if s not in ("", "nan")}
    coinciden = cod_inv & sku_wc

    wc_sku = df_wc[df_wc["SKU"].notna() & ~df_wc["SKU"].isin(["", "nan"])].copy()
    updates = []
    for _, wc in wc_sku.iterrows():
        sku = wc["SKU"]
        if sku in coinciden:
            inv = df_inv[df_inv["Codigo"] == sku].iloc[0]
            ns = int(inv["Cant.Total"])
            updates.append({
                "id": int(wc["ID"]), "parent_id": int(wc["Superior"]),
                "tipo": wc.get("Tipo", "simple"), "sku": sku,
                "nombre": inv.get("Nombre", wc.get("Nombre", "")),
                "old_stock": int(wc["Inventario"]), "new_stock": ns,
                "new_status": "outofstock" if ns <= STOCK_LIMIT else "instock",
                "motivo": "inventario"
            })
        elif sku in (sku_wc - cod_inv):
            cs = int(wc["Inventario"])
            if cs <= STOCK_LIMIT:
                updates.append({
                    "id": int(wc["ID"]), "parent_id": int(wc["Superior"]),
                    "tipo": wc.get("Tipo", "simple"), "sku": sku,
                    "nombre": wc.get("Nombre", ""),
                    "old_stock": cs, "new_stock": cs,
                    "new_status": "outofstock", "motivo": "solo_wc_sin_stock"
                })

    # Reporte previo (que se va a hacer)
    reporte_df = pd.DataFrame(updates)
    reporte_df.to_csv(os.path.join(carpeta, "reporte_preview.csv"), index=False)

    ok = fail = skip = 0
    print(f"\n{'='*70}")
    print(f"  {'SIMULACION' if dry_run else 'ACTUALIZACION EN VIVO'}")
    print(f"  Total: {len(updates)} productos")
    print(f"{'='*70}")

    for i, u in enumerate(updates, 1):
        ep = f"products/{u['parent_id']}/variations/{u['id']}" if u["tipo"] == "variation" else f"products/{u['id']}"
        url = f"{WC_URL}/wp-json/wc/v3/{ep}"
        payload = {"stock_quantity": u["new_stock"], "stock_status": u["new_status"], "manage_stock": True}
        diff = u["new_stock"] - u["old_stock"]
        signo = "+" if diff > 0 else ""
        print(f"  [{i}/{len(updates)}] {u['tipo']:<9} ID:{u['id']:<6} SKU:{u['sku']:<15} {u['old_stock']:>4}->{u['new_stock']:>4} ({signo}{diff}) {u['new_status']:<10} [{u['motivo']}]")

        if not dry_run:
            needs = (diff != 0) or (u["new_stock"] <= STOCK_LIMIT)
            if not needs:
                skip += 1; print("    -> SIN CAMBIOS")
            else:
                st, resp = api_put(url, payload)
                if st == 200:
                    ok += 1; print("    -> OK")
                else:
                    fail += 1
                    msg = resp.get("message", str(resp))[:120] if isinstance(resp, dict) else str(resp)
                    print(f"    -> ERROR {st}: {msg}")
                time.sleep(API_DELAY)

    print(f"\n{'='*70}")
    if dry_run:
        cambios = sum(1 for u in updates if u["new_stock"] != u["old_stock"])
        print(f"  Con cambio stock: {cambios}  Solo status: {len(updates)-cambios}")
    else:
        print(f"  OK: {ok}  Fallidos: {fail}  Omitidos: {skip}")
    print(f"{'='*70}")
    return updates, ok, fail, skip


def verificar(carpeta, wc_csv, inv_csv):
    print("\n--- VERIFICACION ---")
    with open(inv_csv, "r", encoding="ISO-8859-1") as f:
        delim = ";" if ";" in f.readline() else ","
    df_inv = pd.read_csv(inv_csv, delimiter=delim, encoding="ISO-8859-1", dtype={"Codigo": str})
    df_inv["Codigo"] = df_inv["Codigo"].str.strip()
    df_wc = pd.read_csv(wc_csv, dtype={"SKU": str})
    df_wc["SKU"] = df_wc["SKU"].str.strip()
    df_wc["Inventario"] = pd.to_numeric(df_wc["Inventario"], errors="coerce").fillna(0).astype(int)

    m = df_inv.merge(df_wc, left_on="Codigo", right_on="SKU", how="inner", suffixes=("_i", "_w"))
    ok = (m["Cant.Total"] == m["Inventario"]).sum()
    bad = (~(m["Cant.Total"] == m["Inventario"])).sum()
    m.to_csv(os.path.join(carpeta, "verificacion.csv"), index=False)
    print(f"  Coinciden: {len(m)}  OK: {ok}  Discrepancias: {bad}")
    return bad == 0


def main():
    dry_run = "--live" not in sys.argv

    print("=== ACTUALIZACION DIARIA DE STOCK ===")
    print(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

    inv_csv = os.path.join(CARPETA_BASE, "ListaInvFisic.csv")
    if not os.path.exists(inv_csv):
        print(f"ERROR: No se encuentra {inv_csv}")
        print("Coloca el archivo ListaInvFisic.csv en la carpeta del proyecto.")
        return

    wc_export = descargar_export_wc()
    carpeta = crear_carpeta_dia()

    shutil.copy2(inv_csv, os.path.join(carpeta, "ListaInvFisic.csv"))
    wc_dest = os.path.join(carpeta, os.path.basename(wc_export))
    shutil.copy2(wc_export, wc_dest)
    os.remove(wc_export)

    updates, ok, fail, skip = procesar(inv_csv, wc_dest, carpeta, dry_run=dry_run)

    if not dry_run:
        # Reporte post-actualizacion
        df_result = pd.DataFrame(updates)
        df_result["aplicado"] = df_result.apply(
            lambda r: "si" if (r["new_stock"] != r["old_stock"] or r["new_stock"] <= STOCK_LIMIT) else "no_omitido",
            axis=1
        )
        df_result.to_csv(os.path.join(carpeta, "reporte_actualizacion.csv"), index=False)
        verificar(carpeta, wc_dest, inv_csv)

    print(f"\nArchivos en: {carpeta}")
    for f in os.listdir(carpeta):
        print(f"  - {f}")


if __name__ == "__main__":
    main()
