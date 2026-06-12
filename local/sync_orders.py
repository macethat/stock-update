import json
import os
import sys
import subprocess
from datetime import datetime

CARPETA_BASE = os.path.dirname(os.path.abspath(__file__))

SSH_KEY = os.path.join(CARPETA_BASE, "ssh-key-nopass")
SSH_USER = "u1910-kbd9lgn9dh44"
SSH_HOST = "ssh.suplementospanama.net"
SSH_PORT = "18765"
WP_PATH = "~/www/suplementospanama.net/public_html"

PSK_PIN = "46558"
PSK_API_KEY = "BQxQrt5/FwARtlVUwT0GFw=="
PSK_API_HOST = "adm.premium-soft.com"

WAREHOUSE_PRIORITY = [
    (9, 6),    # SP BODEGA
    (1, 1),    # SP CANGREJO
    (5, 2),    # SP MEGAPOLIS
    (6, 3),    # SP ATRIO COSTA DEL ESTE
    (7, 5),    # POWER CLUB SAN FRANCISCO
    (8, 4),    # POWER CLUB ALTOS DE PANAMA
    (10, 7),   # SP METROMALL
    (11, 2),   # BODEGA MEGAPOLIS
    (12, 3),   # BODEGA ATRIO
]

ID_USUARIO = 143
ID_VENDEDOR = 25
ID_TIPO_DOCUMENTO = 2
ID_AGENCIA_DEFAULT = 6
ID_UNIDAD_DEFAULT = 79


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


def psk_api(method, path, body=None):
    import http.client
    conn = http.client.HTTPSConnection(PSK_API_HOST)
    headers = {'clave-api-business': PSK_API_KEY}
    if body:
        headers['Content-Type'] = 'application/json'
        conn.request(method, path, json.dumps(body), headers=headers)
    else:
        conn.request(method, path, headers=headers)
    r = conn.getresponse()
    raw = r.read().decode()
    try:
        return r.status, json.loads(raw)
    except:
        return r.status, raw


def get_articulos_map():
    print("  Obteniendo catalogo de PSK Cloud...")
    status, data = psk_api('GET', f'/Api/Articulos?pin={PSK_PIN}&pagina=0&cant_pagina=99999')
    if status != 200 or not isinstance(data, list):
        print(f"  ERROR: API Articulos respondio {status}")
        return {}
    m = {}
    for a in data:
        cod = a.get('codigo', '').strip()
        if cod:
            imp = a.get('impuestos', [])
            if imp:
                imp_clean = [{
                    'id_tipo_impuesto': i['id_tipo_impuesto'],
                    'prc_impuesto': i['prc_impuesto'],
                    'monto_impuesto': i.get('monto_impuesto', '0.0000000'),
                } for i in imp]
            else:
                imp_clean = [{
                    'id_tipo_impuesto': '1',
                    'prc_impuesto': '0.0000000',
                    'monto_impuesto': '0.0000000',
                }]
            m[cod] = {
                'id_articulo': a.get('id_articulo'),
                'nombre': a.get('nombre', ''),
                'id_unidad': a.get('id_unidad', ID_UNIDAD_DEFAULT),
                'impuestos': imp_clean,
            }
    print(f"  {len(m)} articulos cargados")
    return m


def get_wc_orders():
    print("  Obteniendo pedidos nuevos de WooCommerce...")
    raw = ssh_run(
        f'cd {WP_PATH} && wp wc order list --status=processing,pending '
        f'--field=id --format=json 2>/dev/null'
    )
    if not raw or raw == '[]':
        print("  No hay pedidos nuevos")
        return []
    try:
        ids = json.loads(raw)
    except:
        print(f"  ERROR parseando lista de ordenes: {raw[:100]}")
        return []
    print(f"  {len(ids)} pedidos encontrados")
    orders = []
    for oid in ids:
        details = ssh_run(
            f'cd {WP_PATH} && wp wc order get {oid} --format=json 2>/dev/null'
        )
        if not details:
            continue
        try:
            orders.append(json.loads(details))
        except:
            print(f"  ERROR parseando orden {oid}")
    return orders


def get_existencias_por_articulo(id_articulo):
    status, data = psk_api('GET', f'/Api/Existencias?pin={PSK_PIN}&id_articulo={id_articulo}&todos=1')
    if status != 200 or not isinstance(data, list):
        return {}
    stocks = {}
    for e in data:
        aid = int(e.get('id_almacen', 0))
        try:
            stocks[aid] = int(float(e.get('existencia', '0')))
        except:
            stocks[aid] = 0
    return stocks


def choose_warehouse_for_order(items, articulos):
    for alm, ag in WAREHOUSE_PRIORITY:
        all_have_stock = True
        for sku, qty in items:
            art = articulos.get(sku)
            if not art:
                all_have_stock = False
                break
            stocks = get_existencias_por_articulo(art['id_articulo'])
            if stocks.get(alm, 0) <= 0:
                all_have_stock = False
                break
        if all_have_stock:
            return alm, ag
    return WAREHOUSE_PRIORITY[0]


def check_client_exists(email, doc_id):
    params = f'pin={PSK_PIN}'
    if doc_id:
        params += f'&doc_identificacion={doc_id}'
    if email:
        params += f'&email={email}'
    status, data = psk_api('GET', f'/Api/Clientes?{params}')
    if status == 200 and isinstance(data, list) and len(data) > 0:
        return data[0]
    return None


def create_client(doc_id, nombre, email, telefono, direccion):
    payload = {
        'doc_identificacion': doc_id,
        'nombre': nombre,
        'email': email,
        'telefono': telefono,
        'direccion': direccion,
    }
    print(f"    Creando cliente: {nombre} ({doc_id})...")
    status, data = psk_api('POST', f'/Api/Clientes_GuardarRapido?pin={PSK_PIN}', payload)
    if status not in (200, 201):
        print(f"    ERROR creando cliente: status={status}")
        return None
    found = check_client_exists(email, doc_id)
    if found:
        print(f"    Cliente OK: id_cliente={found.get('id_cliente')}")
        return found
    print(f"    WARN: No se pudo recuperar id_cliente")
    return None


def create_order_in_psk(pedido_data):
    print(f"    Creando pedido en PSK Cloud...")
    status, data = psk_api('POST', f'/Api/ProcesarDoc?pin={PSK_PIN}', pedido_data)
    if status in (200, 201):
        if isinstance(data, dict) and data.get('status') == 0:
            print(f"    ERROR PSK: {data.get('msj', 'desconocido')}")
            return None
        print(f"    Pedido creado OK: {str(data)[:200]}")
        return data
    print(f"    ERROR creando pedido: status={status} data={str(data)[:200]}")
    return None


def process_order(wc_order, articulos):
    oid = wc_order.get('id')
    print(f"\n  --- Procesando orden WC #{oid} ---")

    billing = wc_order.get('billing', {})
    first_name = billing.get('first_name', '')
    last_name = billing.get('last_name', '')
    nombre = f"{first_name} {last_name}".strip()
    if not nombre:
        nombre = billing.get('email', 'Cliente Web')
    email = billing.get('email', '')
    phone = billing.get('phone', '')
    address_1 = billing.get('address_1', '')
    address_2 = billing.get('address_2', '')
    city = billing.get('city', '')
    direccion = f"{address_1} {address_2}, {city}".strip().strip(',')

    meta = {m.get('key'): m.get('value') for m in wc_order.get('meta_data', [])}
    doc_id = meta.get('_doc_identificacion', '')

    client = check_client_exists(email, doc_id)
    if not client:
        client = create_client(doc_id, nombre, email, phone, direccion)
        if not client:
            print(f"  ERROR: No se pudo crear/obtener cliente para orden #{oid}")
            return False

    print(f"    Cliente: {nombre} (id_cliente={client.get('id_cliente', '?')})")

    wc_items = wc_order.get('line_items', [])
    order_items = []
    opermv = []

    for item in wc_items:
        sku = item.get('sku', '').strip()
        qty = int(item.get('quantity', 1))
        price = float(item.get('price', 0))
        name = item.get('name', '')

        if not sku:
            print(f"    SKIP: {name} - sin SKU")
            continue
        art = articulos.get(sku)
        if not art:
            print(f"    SKIP: {sku} ({name}) - no encontrado en PSK Cloud")
            continue

        order_items.append((sku, qty))
        linea = {
            'id_articulo': art['id_articulo'],
            'nombre_articulo': art['nombre'],
            'precio_unitario': f"{price:.2f}",
            'monto_descuento': '0',
            'prc_descuento': '0',
            'cantidad': f"{qty}.0",
            'id_unidad': art.get('id_unidad', str(ID_UNIDAD_DEFAULT)),
            'seriales': None,
            'id_lote_vencimiento': None,
            'notas': '',
            'mostrado_en_comanda': 0.0,
            'integrados': None,
        }
        linea['impuestos'] = art['impuestos']
        opermv.append(linea)
        print(f"    Linea: {sku} x{qty} @ ${price:.2f}")

    if not opermv:
        print(f"  ERROR: No hay lineas procesables para orden #{oid}")
        return False

    id_almacen, id_agencia = choose_warehouse_for_order(order_items, articulos)
    print(f"    Almacen seleccionado: {id_almacen} (agencia {id_agencia})")

    now = datetime.now()
    pedido = {
        'operti': {
            'id_operti': '',
            'registrar_contabilidad': '0',
            'id_operti_devol': '',
            'id_tipo_documento': str(ID_TIPO_DOCUMENTO),
            'fecha_emision': now.strftime('%Y-%m-%d'),
            'hora_emision': now.strftime('%H:%M'),
            'id_almacen': str(id_almacen),
            'id_cliente': client.get('id_cliente'),
            'nombre_cliente': nombre,
            'id_vendedor': str(ID_VENDEDOR),
            'id_agencia': str(id_agencia),
            'id_usuario': str(ID_USUARIO),
            'notas': f"Orden WooCommerce #{oid}",
            'notas_internas': None,
            'id_mesa': None,
            'retenciones': [],
            'id_tipo_recargo': None,
            'prc_recargo': None,
            'monto_recargo': None,
            'motivo_recargo': None,
            'id_tipo_recargo_propina': None,
            'prc_recargo_propina': None,
            'monto_recargo_propina': None,
            'motivo_recargo_propina': None,
            'fechaVence': None,
        },
        'opermv': opermv,
    }

    result = create_order_in_psk(pedido)
    if result:
        psk_id = result.get('id', str(result))
        cmd = (
            f"cd {WP_PATH} && wp wc order update {oid} "
            f"--meta_data='[{{\"key\":\"_psk_order_id\",\"value\":\"{psk_id}\"}},"
            f"{{\"key\":\"_psk_sync_status\",\"value\":\"success\"}}]' 2>/dev/null"
        )
        ssh_run(cmd)
        print(f"  Orden #{oid} sincronizada OK -> PSK #{psk_id}")
        return True
    else:
        cmd = (
            f"cd {WP_PATH} && wp wc order update {oid} "
            f"--meta_data='[{{\"key\":\"_psk_sync_status\",\"value\":\"failed\"}}]' 2>/dev/null"
        )
        ssh_run(cmd)
        return False


def main():
    dry_run = "--live" not in sys.argv
    if not dry_run:
        for i, a in enumerate(sys.argv):
            if a == "--live":
                sys.argv.pop(i)
                break

    print("=== SINCRONIZACION DE PEDIDOS ===")
    print(f"Ejecucion: {'SIMULACION (dry-run)' if dry_run else 'EN VIVO'}")
    print(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

    if dry_run:
        orders = get_wc_orders()
        print(f"\nPedidos pendientes: {len(orders)}")
        for o in orders:
            oid = o.get('id')
            billing = o.get('billing', {})
            total = o.get('total')
            items = o.get('line_items', [])
            meta = {m.get('key'): m.get('value') for m in o.get('meta_data', [])}
            doc_id = meta.get('_doc_identificacion', '')
            print(f"  #{oid}: {billing.get('first_name', '')} {billing.get('last_name', '')} "
                  f"- ${total} ({len(items)} items) doc_id={doc_id}")
        print("\n(dry-run: no se realizaron cambios)")
        return

    articulos = get_articulos_map()
    if not articulos:
        print("ERROR: No se pudo cargar catalogo de PSK Cloud")
        return

    orders = get_wc_orders()
    print(f"\nPedidos a procesar: {len(orders)}")

    ok = fail = 0
    for wc_order in orders:
        if process_order(wc_order, articulos):
            ok += 1
        else:
            fail += 1

    print(f"\n{'='*50}")
    print(f"Resultado: {ok} OK, {fail} fallidos")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
