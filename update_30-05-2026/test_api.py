import urllib.request
import base64
import json

url = "https://suplementospanama.net/wp-json/wc/v3/products/81"
auth = base64.b64encode(b"ck_5fa7935bad5d098c833a7e3f022e6b4ab1a70e0e:cs_3f5441046f1d1d064a9edbc8c04c5e4d69b2a4fa").decode()

req = urllib.request.Request(
    url,
    headers={
        "Authorization": f"Basic {auth}",
        "User-Agent": "Stock-Sync/1.0"
    }
)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
        print(f"OK: Producto ID {data['id']} - SKU: {data['sku']} - Stock: {data.get('stock_quantity', 'N/A')}")
except Exception as e:
    print(f"ERROR: {e}")
