# PSK-WC-SYNC

Sincronización bidireccional entre **PSK Cloud** (Premium Soft) y **WooCommerce** para gestión de inventario, clientes y pedidos.

## Arquitectura

```
PSK Cloud API ──> daily_stock_update.py ──> WooCommerce (via SSH+WP-CLI)
       │                                          │
       └── Clientes, Pedidos, Stock               └── Pedidos web
```

- **Origen de datos**: API REST de PSK Cloud (`adm.premium-soft.com/Api/`)
- **Destino**: WooCommerce vía SSH + WP-CLI
- **Frecuencia**: Diaria (bajo demanda o programable vía Windows Task Scheduler)

## Procesos

### 1. Sincronización de Inventario (Implementado ✅)

Extrae stock total (suma de todos los almacenes) desde PSK Cloud y actualiza WooCommerce.

**Uso:**
```bash
# Dry-run (solo genera reportes)
python daily_stock_update.py --api

# Live (actualiza WooCommerce)
python daily_stock_update.py --live --api

# Con fecha forzada (si el inventario es del día anterior)
python daily_stock_update.py --live --api --fecha DD-MM-YYYY

# Sin flag --api usa ListaInvFisic.csv manual
python daily_stock_update.py --live
```

**Regla de negocio:**
- Stock > 6 → `instock`
- Stock ≤ 6 → `outofstock`

**Salida por corrida (carpeta `update_DD-MM-YYYY/`):**
- `ListaInvFisic.csv` — inventario extraído de la API
- `wc_export.json` — exportación de productos WooCommerce
- `comparativa_previa.csv` — comparación antes de actualizar
- `cambios.csv` — todos los cambios (stock + status)
- `cambios_stock.csv` — solo cambios de cantidad
- `reporte_actualizacion.csv` — resultado final
- `verificacion.txt` — discrepancias post-actualización

### 2. Gestión de Clientes (Pendiente 🔄)

Al recibir un pedido en WooCommerce, buscar al cliente en PSK Cloud por documento/email. Si no existe, crearlo vía `Clientes_GuardarRapido`.

**Endpoint:** `POST /Api/Clientes_GuardarRapido?pin=46558`

### 3. Pedidos y Descuento de Stock (Pendiente 🔄)

Crear pedidos en PSK Cloud desde WooCommerce con prioridad de almacén:
1. SP CANGREJO (id=1)
2. SP MEGAPOLIS (id=5)
3. Resto (sucursal con mayor stock)

**Endpoint:** `POST /Api/ProcesarDoc?pin=46558`

## Configuración

### Credenciales

| Variable | Descripción |
|---|---|
| PSK PIN | `46558` |
| PSK API Key | configurada en script |
| SSH Host | `ssh.suplementospanama.net:18765` |
| SSH User | `u1910-kbd9lgn9dh44` |
| WP Path | `~/www/suplementospanama.net/public_html` |

### Almacenes (id_almacen)

| ID | Nombre |
|---|---|
| 1 | SP CANGREJO |
| 5 | SP MEGAPOLIS |
| 6 | SP ATRIO COSTA DEL ESTE |
| 7 | POWER CLUB SAN FRANCISCO |
| 8 | POWER CLUB ALTOS DE PANAMA |
| 9 | SP BODEGA |
| 10 | SP METROMALL |
| 11 | BODEGA MEGAPOLIS |
| 12 | BODEGA ATRIO |

### Documentos

| Tipo | id_tipo_documento |
|---|---|
| Pedido web | 2 (origen_tipo=3) |
| Factura interna web | 35 |

### Usuarios / Vendedores

| Rol | ID | Nombre |
|---|---|---|
| Usuario pedidos web | 143 | VENTAS WEB |
| Vendedor pedidos web | 25 | VENTAS WEB |

## API PSK Cloud - Endpoints Utilizados

| Endpoint | Método | Uso |
|---|---|---|
| `/Api/Articulos` | GET | Listar productos con stock total |
| `/Api/Almacenes` | GET | Obtener lista de almacenes |
| `/Api/Existencias` | GET | Stock por artículo por almacén |
| `/Api/Tipo_documentos` | GET | Tipos de documento disponibles |
| `/Api/Clientes` | GET | Buscar clientes |
| `/Api/Clientes_GuardarRapido` | POST | Crear/actualizar cliente |
| `/Api/ProcesarDoc` | POST | Crear pedido (cabecera + líneas + cobros) |
| `/Api/Vendedores` | GET | Listar vendedores |
| `/Api/Usuarios` | GET | Listar usuarios del sistema |

## Notas Técnicas

- **Autenticación API**: Header `clave-api-business` (usar guiones `clave-api-business`, no guiones bajos)
- **WooCommerce**: Actualmente bloqueado por SG-CAPTCHA en API REST directa → se usa SSH+WP-CLI
- **Auto-commit**: Cada corrida `--live` genera commit + push automático al repo
- **Bug conocido (resuelto)**: `existencias` viene como `"258.00"` (string) → se convierte a `int(float())`
