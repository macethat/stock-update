import urllib.request
import base64
import json
import pandas as pd
import time
import os

RUTA = os.path.dirname(os.path.abspath(__file__)) + "/"
WC_URL = "https://suplementospanama.net"
CONSUMER_KEY = "ck_5fa7935bad5d098c833a7e3f022e6b4ab1a70e0e"
CONSUMER_SECRET = "cs_3f5441046f1d1d064a9edbc8c04c5e4d69b2a4fa"


def api_get(url):
    token = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {token}",
            "User-Agent": "Stock-Sync/1.0"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def obtener_productos_wc():
    productos = []
    page = 1
    while True:
        url = f"{WC_URL}/wp-json/wc/v3/products?per_page=100&page={page}"
        data = api_get(url)
        if not data:
            break
        for p in data:
            sku = p.get("sku", "")
            stock = p.get("stock_quantity")
            productos.append({
                "id": p["id"],
                "sku": str(sku).strip() if sku else "",
                "stock": stock if stock is not None else 0,
                "status": p.get("stock_status", ""),
                "nombre": p.get("name", ""),
                "tipo": p.get("type", "")
            })
            # Variations
            if p.get("type") == "variable":
                var_url = f"{WC_URL}/wp-json/wc/v3/products/{p['id']}/variations?per_page=100"
                vars_data = api_get(var_url)
                for v in vars_data:
                    v_sku = v.get("sku", "")
                    v_stock = v.get("stock_quantity")
                    productos.append({
                        "id": v["id"],
                        "sku": str(v_sku).strip() if v_sku else "",
                        "stock": v_stock if v_stock is not None else 0,
                        "status": v.get("stock_status", ""),
                        "nombre": v.get("name", ""),
                        "tipo": "variation"
                    })
        print(f"  Pagina {page}: {len(data)} productos + variaciones")
        page += 1
        time.sleep(0.3)
    return pd.DataFrame(productos)


def main():
    print("Descargando productos desde WooCommerce...")
    df_wc = obtener_productos_wc()
    print(f"Total productos + variaciones descargados: {len(df_wc)}")
    print(f"  Con SKU: {df_wc['sku'].str.len().gt(0).sum()}")
    print(f"  Sin SKU: {(df_wc['sku'] == '').sum()}")

    print("\nLeyendo archivo fuente del inventario...")
    delimitador = ","
    with open(RUTA + "ListaInvFisic.csv", "r", encoding="ISO-8859-1") as f:
        if ";" in f.readline():
            delimitador = ";"
    df_inv = pd.read_csv(
        RUTA + "ListaInvFisic.csv",
        delimiter=delimitador,
        encoding="ISO-8859-1",
        dtype={"Codigo": str}
    )
    df_inv["Codigo"] = df_inv["Codigo"].str.strip()

    print(f"  Productos en inventario: {len(df_inv)}")

    # Comparar
    wc_con_sku = df_wc[df_wc["sku"] != ""].copy()
    merged = df_inv.merge(
        wc_con_sku,
        left_on="Codigo",
        right_on="sku",
        how="inner",
        suffixes=("_inv", "_wc")
    )

    merged["coincide"] = merged["Cant.Total"] == merged["stock"]
    ok = merged["coincide"].sum()
    mal = (~merged["coincide"]).sum()

    print(f"\n=== VERIFICACION ===")
    print(f"Productos cotejados: {len(merged)}")
    print(f"  Coinciden stock:   {ok}")
    print(f"  NO coinciden:      {mal}")

    if mal > 0:
        errores = merged[~merged["coincide"]].copy()
        errores["diff"] = errores["Cant.Total"] - errores["stock"]
        print(f"\nTop 15 discrepancias:")
        top = errores.reindex(errores["diff"].abs().sort_values(ascending=False).index).head(15)
        for _, r in top.iterrows():
            print(f"  SKU:{r['Codigo']:<15} "
                  f"Esperado:{int(r['Cant.Total']):>5} "
                  f"Real WC:{int(r['stock']):>5} "
                  f"Diff:{int(r['diff']):>5}")

    # Productos solo en inventario (no en WC)
    codigos_wc = set(wc_con_sku["sku"].unique())
    solo_inv = set(df_inv["Codigo"].unique()) - codigos_wc
    if solo_inv:
        print(f"\nProductos en inventario pero NO en WC: {len(solo_inv)}")

    # Productos solo en WC (no en inventario)
    codigos_inv = set(df_inv["Codigo"].unique())
    solo_wc = codigos_wc - codigos_inv
    if solo_wc:
        print(f"Productos en WC pero NO en inventario: {len(solo_wc)}")

    # Guardar resultados
    merged.to_csv(RUTA + "verificacion_completa.csv", index=False)
    print(f"\nReporte guardado: verificacion_completa.csv")


if __name__ == "__main__":
    main()
