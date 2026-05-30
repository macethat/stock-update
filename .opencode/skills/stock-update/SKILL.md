---
name: stock-update
description: Actualiza el inventario de WooCommerce desde un CSV de inventario fisico. Descarga el export de productos de WooCommerce via API, lo cruza con ListaInvFisic.csv, actualiza stock y stock_status (outofstock si <=6), y verifica el resultado.
---

## Proceso diario de actualizacion de stock

### 1. Preparacion
- El archivo `ListaInvFisic.csv` debe estar en la raiz del proyecto (`C:\suplementos\stock-suplementos\`)
- El script `daily_stock_update.py` hace todo automaticamente

### 2. Ejecucion
```powershell
cd C:\suplementos\stock-suplementos
python daily_stock_update.py          # dry-run (simulacion)
python daily_stock_update.py --live   # actualizacion en vivo
```

### 3. Que hace el script
1. Descarga el export de productos de WooCommerce via API REST
2. Crea una subcarpeta `update_DD-MM-YYYY/`
3. Copia los archivos fuente a la carpeta del dia
4. Cruza `Codigo` (inventario) con `SKU` (WooCommerce)
5. Para cada producto coincidente:
   - Actualiza `stock_quantity` al valor de `Cant.Total`
   - Si stock <= 6, establece `stock_status = "outofstock"`
   - Si stock > 6, establece `stock_status = "instock"`
6. Productos solo en WooCommerce con stock <= 6 tambien se marcan outofstock
7. En modo `--live`, aplica los cambios via API
8. Verifica que los cambios se aplicaron correctamente

### 4. Reglas de negocio
- **Stock <= 6 unidades** → `outofstock` (aplica a todos los productos, incluso sin cambio de cantidad)
- **Stock > 6 unidades** → `instock`
- Productos sin SKU en WooCommerce (camisetas, merch, etc.) se ignoran
- Productos solo en inventario fisico (sin SKU en WC) se reportan pero no se crean

### 5. Archivos generados
En la carpeta `update_DD-MM-YYYY/`:
- `ListaInvFisic.csv` — copia del inventario original
- `wc-product-export-*.csv` — export descargado de WooCommerce
- `reporte_preview.csv` — detalle de cada producto actualizado
- `verificacion.csv` — resultados de la verificacion post-actualizacion

### 6. API Credentials
- URL: https://suplementospanama.net
- Consumer Key y Consumer Secret configuradas en `daily_stock_update.py`
- Permisos: Lectura/Escritura en WooCommerce REST API
