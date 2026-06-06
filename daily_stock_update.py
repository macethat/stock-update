import pandas as pd
import json
import os
import sys
import subprocess
import shutil
from datetime import datetime

CARPETA_BASE = os.path.dirname(os.path.abspath(__file__))
STOCK_LIMIT = 6

SSH_KEY = os.path.join(CARPETA_BASE, "ssh-key-nopass")
SSH_USER = "u1910-kbd9lgn9dh44"
SSH_HOST = "ssh.suplementospanama.net"
SSH_PORT = "18765"
WP_PATH = "~/www/suplementospanama.net/public_html"

PSK_PIN = "46558"
PSK_API_KEY = "BQxQrt5/FwARtlVUwT0GFw=="
PSK_API_HOST = "adm.premium-soft.com"

def ssh_run(cmd):
    full = (
        f'ssh -o StrictHostKeyChecking=no -i "{SSH_KEY}" -p {SSH_PORT} '
        f'{SSH_USER}@{SSH_HOST} '
        f'"export TERM=xterm-256color; {cmd}"'
    )
    r = subprocess.run(full, shell=True, capture_output=True, timeout=120)
    stdout = r.stdout.decode('utf-8', errors='replace').strip()
    stderr = r.stderr.decode('utf-8', errors='replace').strip()
    if r.returncode != 0 and stderr:
        if not any(x in stderr for x in ['Warning:', 'Permanently added']):
            print(f"  SSH WARN: {stderr[:200]}")
    return stdout

def get_wc_export_via_ssh(suffix=""):
    print("Exportando productos via SSH/WP-CLI...")
    out = ssh_run(
        f'cd {WP_PATH} && wp --user=Suplementos eval-file ~/wc_export_ssh.php 2>/dev/null'
    )
    local = os.path.join(CARPETA_BASE, f"tmp_wc_export{suffix}.json")
    with open(local, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f"  Exportados: {len(json.loads(out))} productos")
    return local

def fetch_from_psk_api(suffix=""):
    import http.client
    print("Extrayendo inventario desde PSK Cloud API...")
    conn = http.client.HTTPSConnection(PSK_API_HOST)
    conn.request('GET', f'/Api/Articulos?pin={PSK_PIN}&pagina=0&cant_pagina=99999',
                 headers={'clave-api-business': PSK_API_KEY})
    r = conn.getresponse()
    if r.status != 200:
        print(f"ERROR: API respondio con status {r.status}")
        sys.exit(1)
    data = json.loads(r.read().decode())
    if not isinstance(data, list):
        print(f"ERROR: Respuesta inesperada de API: {data}")
        sys.exit(1)
    rows = []
    for a in data:
        cod = a.get('codigo', '')
        nom = a.get('nombre', '')
        ext = a.get('existencias', '0')
        try:
            ext = int(float(ext))
        except:
            ext = 0
        rows.append({"Codigo": cod, "Nombre": nom, "Cant.Total": ext})
    df = pd.DataFrame(rows)
    df["Codigo"] = df["Codigo"].str.strip()
    print(f"  Extraidos {len(df)} articulos desde PSK Cloud API")
    return df

def main():
    dry_run = "--live" not in sys.argv
    use_api = "--api" in sys.argv
    fecha_arg = None
    for i, a in enumerate(sys.argv):
        if a == "--fecha" and i+1 < len(sys.argv):
            fecha_arg = sys.argv[i+1]
            sys.argv.pop(i+1); sys.argv.pop(i)
            break
    if use_api:
        for i, a in enumerate(sys.argv):
            if a == "--api":
                sys.argv.pop(i)
                break
    print("=== ACTUALIZACION DIARIA DE STOCK ===")
    print(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

    inv_csv = os.path.join(CARPETA_BASE, "ListaInvFisic.csv")

    if use_api:
        fec = datetime.strptime(fecha_arg, "%d-%m-%Y") if fecha_arg else datetime.now()
        carpeta = os.path.join(CARPETA_BASE, f"update_{fec.strftime('%d-%m-%Y')}")
        os.makedirs(carpeta, exist_ok=True)
        df_inv = fetch_from_psk_api()
        df_inv.to_csv(os.path.join(carpeta, "ListaInvFisic.csv"), index=False)
    else:
        if not os.path.exists(inv_csv):
            print(f"ERROR: No se encuentra {inv_csv}")
            print("Coloca el archivo ListaInvFisic.csv en la carpeta del proyecto.")
            return
        if fecha_arg:
            fec = datetime.strptime(fecha_arg, "%d-%m-%Y")
        else:
            fec = datetime.fromtimestamp(os.path.getmtime(inv_csv))
        carpeta = os.path.join(CARPETA_BASE, f"update_{fec.strftime('%d-%m-%Y')}")
        os.makedirs(carpeta, exist_ok=True)
        shutil.copy2(inv_csv, os.path.join(carpeta, "ListaInvFisic.csv"))
        with open(inv_csv, "r", encoding="ISO-8859-1") as f:
            delim = ";" if ";" in f.readline() else ","
        df_inv = pd.read_csv(inv_csv, delimiter=delim, encoding="ISO-8859-1", dtype={"Codigo": str})
        df_inv["Codigo"] = df_inv["Codigo"].str.strip()

    wc_json = get_wc_export_via_ssh(suffix="_1")
    wc_path = os.path.join(carpeta, "wc_export.json")
    shutil.copy2(wc_json, wc_path)

    with open(wc_json, encoding='utf-8') as f:
        wc_products = json.load(f)

    wc_by_sku = {}
    for p in wc_products:
        sku = p["sku"].strip() if p["sku"] else ""
        if sku:
            wc_by_sku[sku] = p

    cod_inv = set(df_inv["Codigo"].dropna().unique())
    sku_wc = set(wc_by_sku.keys())
    coinciden = cod_inv & sku_wc

    # === COMPARATIVA PREVIA ===
    rows_comp = []
    for sku in coinciden:
        wc_p = wc_by_sku[sku]
        inv_row = df_inv[df_inv["Codigo"] == sku].iloc[0]
        old_s = wc_p["stock_qty"] if wc_p["stock_qty"] is not None else 0
        try:
            ns = int(inv_row["Cant.Total"])
        except:
            continue
        ns_status = "outofstock" if ns <= STOCK_LIMIT else "instock"
        diff = ns - old_s
        rows_comp.append({
            "sku": sku, "nombre": inv_row.get("Nombre", wc_p.get("name", "")),
            "tipo": wc_p["type"], "wc_stock": old_s, "wc_status": wc_p["stock_st"],
            "inv_stock": ns, "nuevo_status": ns_status, "diferencia": diff,
            "cambiara": "SI" if (diff != 0 or wc_p["stock_st"] != ns_status) else "no"
        })
    for sku in (sku_wc - cod_inv):
        wc_p = wc_by_sku[sku]
        old_s = wc_p["stock_qty"] if wc_p["stock_qty"] is not None else 0
        if old_s <= STOCK_LIMIT:
            rows_comp.append({
                "sku": sku, "nombre": wc_p.get("name", ""),
                "tipo": wc_p["type"], "wc_stock": old_s, "wc_status": wc_p["stock_st"],
                "inv_stock": "(solo WC)", "nuevo_status": "outofstock", "diferencia": "-",
                "cambiara": "SI"
            })
    comp_df = pd.DataFrame(rows_comp)
    comp_df.to_csv(os.path.join(carpeta, "comparativa_previa.csv"), index=False)
    cambiaran = sum(1 for r in rows_comp if r["cambiara"] == "SI")
    print(f"  Comparativa previa: {len(rows_comp)} productos ({cambiaran} cambiaran)")

    updates = []
    for sku in coinciden:
        wc_p = wc_by_sku[sku]
        inv_row = df_inv[df_inv["Codigo"] == sku].iloc[0]
        old_stock = wc_p["stock_qty"] if wc_p["stock_qty"] is not None else 0
        try:
            ns = int(inv_row["Cant.Total"])
        except:
            continue
        updates.append({
            "id": wc_p["id"], "parent": wc_p["parent"],
            "tipo": wc_p["type"], "sku": sku,
            "nombre": inv_row.get("Nombre", wc_p.get("name", "")),
            "old_stock": old_stock, "new_stock": ns,
            "new_status": "outofstock" if ns <= STOCK_LIMIT else "instock",
            "old_status": wc_p["stock_st"],
            "manage": wc_p["manage"],
        })

    for sku in (sku_wc - cod_inv):
        wc_p = wc_by_sku[sku]
        cs = wc_p["stock_qty"] if wc_p["stock_qty"] is not None else 0
        if cs <= STOCK_LIMIT:
            updates.append({
                "id": wc_p["id"], "parent": wc_p["parent"],
                "tipo": wc_p["type"], "sku": sku,
                "nombre": wc_p.get("name", ""),
                "old_stock": cs, "new_stock": cs,
                "new_status": "outofstock",
                "old_status": wc_p["stock_st"],
                "manage": wc_p["manage"],
            })

    df_prev = pd.DataFrame(updates)
    df_prev.to_csv(os.path.join(carpeta, "reporte_preview.csv"), index=False)
    print(f"\n{'='*70}")
    print(f"  {'SIMULACION' if dry_run else 'ACTUALIZACION EN VIVO (SSH)'}")
    print(f"  Total a procesar: {len(updates)} productos")
    print(f"  Coincidencias: {len(coinciden)} | Solo WC (low stock): {len(updates)-len(coinciden)}")
    print(f"{'='*70}")

    commands = []
    for u in updates:
        diff = u["new_stock"] - u["old_stock"]
        signo = "+" if diff > 0 else ""
        needs_update = (diff != 0) or (u["new_status"] != u["old_status"])

        print(f"  {u['tipo']:<9} ID:{u['id']:<6} SKU:{u['sku']:<15} "
              f"{u['old_stock']:>4}->{u['new_stock']:>4} ({signo}{diff}) "
              f"{u['new_status']:<10}", end="")

        if not needs_update:
            print(" -> SIN CAMBIOS")
            continue

        in_stock = "true" if u["new_status"] == "instock" else "false"
        if u["tipo"] == "variation":
            wp_cmd = f"wp --user=Suplementos wc product_variation update {u['parent']} {u['id']}"
        else:
            wp_cmd = f"wp --user=Suplementos wc product update {u['id']}"
        wp_cmd += f" --stock_quantity={u['new_stock']} --in_stock={in_stock}"
        if not u["manage"] or u["manage"] == "parent":
            wp_cmd += " --manage_stock=true"
        commands.append(f"cd {WP_PATH} && {wp_cmd}")

        if dry_run:
            print(f" -> {'outofstock' if u['new_stock'] <= STOCK_LIMIT else 'instock'} (dry)")
        else:
            print(" -> pendiente")

    # CSV de cambios (solo productos con modificacion real)
    cambios_df = pd.DataFrame([u for u in updates if u["new_stock"] != u["old_stock"] or u["new_status"] != u["old_status"]])
    if not cambios_df.empty:
        cambios_df["tipo_cambio"] = cambios_df.apply(
            lambda r: "solo_status" if r["new_stock"] == r["old_stock"] else "stock+/-", axis=1)
        cambios_df.to_csv(os.path.join(carpeta, "cambios.csv"), index=False)
        cambios_stock = cambios_df[cambios_df["new_stock"] != cambios_df["old_stock"]]
        if not cambios_stock.empty:
            cambios_stock.to_csv(os.path.join(carpeta, "cambios_stock.csv"), index=False)
            print(f"  Cambios reales guardados: {len(cambios_df)} en cambios.csv ({len(cambios_stock)} con cambio de stock en cambios_stock.csv)")

    if dry_run:
        cambios = sum(1 for u in updates if u["new_stock"] != u["old_stock"])
        print(f"\n  Con cambio stock: {cambios}  Solo status: {len(updates)-cambios}")
        print(f"  Comandos WP-CLI generados: {len(commands)}")
    else:
        print(f"\n  Ejecutando {len(commands)} comandos vía SSH...")
        ok = fail = 0
        batch_size = 20
        for b in range(0, len(commands), batch_size):
            batch = commands[b:b+batch_size]
            batch_cmd = "; ".join(batch)
            out = ssh_run(batch_cmd)
            for i, cmd in enumerate(batch, b+1):
                sys.stdout.write(f"\r  [{i}/{len(commands)}] ")
                sys.stdout.flush()
            succ = out.count("Success:")
            errs = out.count("Error:")
            ok += succ
            fail += errs
            sys.stdout.write(f"  OK: +{succ}  Err: +{errs}\n")
            sys.stdout.flush()

        print(f"\n  OK: {ok}  Fallidos: {fail}")

        print("\n--- VERIFICACION ---", flush=True)
        wc_json2 = get_wc_export_via_ssh(suffix="_2")
        with open(wc_json2, encoding='utf-8') as f:
            wc2 = json.load(f)
        wc2_by_sku = {}
        for p in wc2:
            sku = p["sku"].strip() if p["sku"] else ""
            if sku:
                wc2_by_sku[sku] = p

        disc = 0
        for u in updates:
            wc2_p = wc2_by_sku.get(u["sku"])
            if not wc2_p:
                continue
            actual = wc2_p["stock_qty"] if wc2_p["stock_qty"] is not None else 0
            if actual != u["new_stock"]:
                disc += 1
                print(f"  DISCREPANCIA: {u['sku']} esperado={u['new_stock']} actual={actual}")

        if disc == 0:
            print("  Todas las actualizaciones verificadas correctamente.")
        else:
            print(f"  {disc} discrepancias encontradas.")

        df_result = pd.DataFrame(updates)
        if not df_result.empty:
            df_result["aplicado"] = df_result.apply(
                lambda r: "si" if (r["new_stock"] != r["old_stock"] or r["new_stock"] <= STOCK_LIMIT) else "no_omitido",
                axis=1
            )
        df_result.to_csv(os.path.join(carpeta, "reporte_actualizacion.csv"), index=False)
        with open(os.path.join(carpeta, "verificacion.txt"), "w") as f:
            f.write(f"Discrepancias: {disc}\n")
            f.write(f"OK: {ok}  Fallidos: {fail}\n")
        os.remove(wc_json2)

    os.remove(wc_json)
    print(f"\nArchivos en: {carpeta}")
    for f in sorted(os.listdir(carpeta)):
        print(f"  - {f}")

if __name__ == "__main__":
    main()
