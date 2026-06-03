---
name: stock-update
description: Actualiza el inventario de WooCommerce desde un CSV de inventario fisico via SSH+WP-CLI. Cruza ListaInvFisic.csv con el export de WooCommerce, genera comparativa previa, actualiza stock y stock_status (outofstock si <=6), y verifica.
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
1. Exporta todos los productos de WooCommerce via SSH + WP-CLI (PHP script en servidor)
2. Crea una subcarpeta `update_DD-MM-YYYY/`
3. Copia los archivos fuente a la carpeta del dia
4. Genera `comparativa_previa.csv` con:
   - stock y status actual (WC) vs inventario fisico
   - diferencia de unidades
   - nuevo status segun regla (outofstock si <= 6)
   - columna "cambiara" (SI/no)
5. Cruza `Codigo` (inventario) con `SKU` (WooCommerce)
6. Para cada producto coincidente:
   - Actualiza `stock_quantity` al valor de `Cant.Total`
   - Si stock <= 6, establece `stock_status = "outofstock"`
   - Si stock > 6, establece `stock_status = "instock"`
7. Productos solo en WooCommerce con stock <= 6 tambien se marcan outofstock
8. En modo `--live`, aplica los cambios via SSH (WP-CLI `wc product update` / `wc product_variation update`)
9. Re-exporta y verifica que los cambios se aplicaron correctamente

### 4. Reglas de negocio
- **Stock <= 6 unidades** → `outofstock` (aplica a todos los productos, incluso sin cambio de cantidad)
- **Stock > 6 unidades** → `instock`
- Productos sin SKU en WooCommerce (camisetas, merch, etc.) se ignoran
- Productos solo en inventario fisico (sin SKU en WC) se reportan pero no se crean

### 5. Archivos generados
En la carpeta `update_DD-MM-YYYY/`:
- `ListaInvFisic.csv` — copia del inventario original
- `wc_export.json` — export de WooCommerce via WP-CLI
- `comparativa_previa.csv` — comparacion pre-actualizacion (WC vs inventario)
- `reporte_preview.csv` — detalle de cada producto a actualizar
- `cambios.csv` — solo productos con cambio real (stock o status)
- `reporte_actualizacion.csv` — resultado post-actualizacion (solo --live)
- `verificacion.txt` — resultado de la verificacion (solo --live)

### 6. Conexion (SSH + WP-CLI)
- Host: `ssh.suplementospanama.net:18765`
- Usuario: `u1910-kbd9lgn9dh44`
- Llave sin contraseña: `ssh-key-nopass`
- WP-CLI version 2.12.0 en servidor
- PHP script `~/wc_export_ssh.php` para exportar productos
