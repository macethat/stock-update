# Proceso de Actualización Diaria de Stock - WooCommerce

## Visión General

Proceso automatizado que sincroniza el inventario físico (CSV del sistema de inventario de la empresa) con los productos de WooCommerce, actualizando cantidades y estados de stock diariamente.

---

## Fases del Proceso

### Fase 1: Preparación
- El usuario coloca `ListaInvFisic.csv` (exportado del sistema de inventario) en la raiz del proyecto
- El script `daily_stock_update.py` descarga automaticamente el export de productos de WooCommerce via API REST

### Fase 2: Matching
- Se cruza el campo `Codigo` del CSV de inventario con `SKU` de WooCommerce
- Se identifican:
  - Productos que coinciden en ambos sistemas (se actualizan)
  - Productos solo en inventario (se reportan, no se crean)
  - Productos solo en WooCommerce (se aplica regla de stock bajo)
  - Productos sin SKU en WooCommerce (se ignoran)

### Fase 3: Preparacion de actualizaciones
Para cada producto coincidente se calcula:
- Nuevo stock = `Cant.Total` del inventario fisico
- Nuevo estado = `outofstock` si stock <= 6, `instock` si stock > 6

### Fase 4: Ejecucion
- **Dry-run** (por defecto): solo simula, no hace cambios
- **Live** (`--live`): aplica los cambios via API REST a WooCommerce
- Cada producto se actualiza via `PUT` al endpoint correspondiente:
  - Simples: `/wp-json/wc/v3/products/{id}`
  - Variaciones: `/wp-json/wc/v3/products/{parent}/variations/{id}`

### Fase 5: Verificacion
- Post-actualizacion, se compara el stock final en WooCommerce contra el inventario fuente
- Se genera un archivo `verificacion.csv` con el detalle

---

## Reglas de Negocio

| Condicion | Stock | Status |
|---|---|---|
| Cant.Total > 6 | Cant.Total | instock |
| Cant.Total <= 6 | Cant.Total | outofstock |
| Solo en WC con stock <= 6 | Sin cambios | outofstock |
| Solo en WC con stock > 6 | Sin cambios | Sin cambios |

---

## Scripts del Proyecto

### `daily_stock_update.py` (PRINCIPAL)
Script unificado que ejecuta todo el proceso automaticamente.

**Uso:**
```powershell
python daily_stock_update.py              # Simulacion (dry-run)
python daily_stock_update.py --live        # Actualizacion en vivo
```

**Funciones:**
- `descargar_export_wc()` — descarga todos los productos y variaciones via API REST
- `crear_carpeta_dia()` — crea `update_DD-MM-YYYY/`
- `procesar()` — cruza los datos, prepara y ejecuta las actualizaciones
- `verificar()` — compara stock final contra inventario fuente

---

### `generar_diferencias.py` (ANALISIS)
Script standalone para analizar diferencias entre inventario fisico y WooCommerce.
Genera reportes de matching sin aplicar cambios.

**Archivos generados:**
- `actualizacion_stock.csv` — solo productos con cambios
- `resumen_completo.csv` — todos los productos cotejados
- `solo_en_inventario_fisico.csv` — productos que no existen en WooCommerce
- `solo_en_woocommerce.csv` — productos en WC que no estan en inventario

---

## Archivos Generados por el Proceso

### En la raiz del proyecto
| Archivo | Origen | Proposito |
|---|---|---|
| `ListaInvFisic.csv` | Sistema de inventario | Fuente de verdad del stock fisico |
| `daily_stock_update.py` | Script | Proceso diario automatizado |

### En `update_DD-MM-YYYY/`
| Archivo | Cuando se genera | Contenido |
|---|---|---|
| `ListaInvFisic.csv` | Fase 1 (copia) | Copia del inventario original del dia |
| `wc-product-export-*.csv` | Fase 1 | Export descargado de WooCommerce |
| `reporte_preview.csv` | Fase 3 | Plan de actualizacion (antes de ejecutar) |
| `reporte_actualizacion.csv` | Fase 4 (solo live) | Registro de lo que se actualizo |
| `verificacion.csv` | Fase 5 (solo live) | Comparacion post-actualizacion |

### Columnas de `reporte_preview.csv` y `reporte_actualizacion.csv`
| Columna | Descripcion |
|---|---|
| `id` | ID del producto en WooCommerce |
| `parent_id` | ID del producto padre (0 si es simple) |
| `tipo` | `simple` o `variation` |
| `sku` | Codigo SKU / Codigo de barras |
| `nombre` | Nombre del producto |
| `old_stock` | Stock anterior en WooCommerce |
| `new_stock` | Nuevo stock (desde inventario) |
| `new_status` | `instock` o `outofstock` |
| `motivo` | `inventario` o `solo_wc_sin_stock` |
| `aplicado` | `si` o `no_omitido` (solo en reporte post) |

---

## Estructura del Proyecto

```
C:\suplementos\stock-suplementos\
│
├── ListaInvFisic.csv              # Inventario fisico actual
├── daily_stock_update.py          # Script principal automatizado
├── generar_diferencias.py         # Script de analisis
│
├── .opencode/
│   └── skills/
│       └── stock-update/
│           └── SKILL.md           # Skill de OpenCode
│
├── docs/
│   └── proceso_actualizacion_diaria.md  # Esta documentacion
│
├── update_30-05-2026/             # Carpeta de la corrida del dia
│   ├── ListaInvFisic.csv
│   ├── wc-product-export-*.csv
│   ├── reporte_preview.csv
│   ├── reporte_actualizacion.csv  # (solo si se ejecuto --live)
│   ├── verificacion.csv           # (solo si se ejecuto --live)
│   └── *.py, *.csv               # Scripts auxiliares de la corrida
│
└── update_*.*/                    # Carpetas de corridas anteriores
```

---

## WooCommerce API

**Endpoint base:** `https://suplementospanama.net/wp-json/wc/v3/`

**Autenticacion:** Basic Auth (Consumer Key + Consumer Secret)

**Metodos usados:**
- `GET /products?per_page=100&page=N` — listar productos (con paginacion)
- `GET /products/{id}/variations` — listar variaciones de un producto variable
- `PUT /products/{id}` — actualizar producto simple
- `PUT /products/{parent}/variations/{id}` — actualizar variacion

**Payload de actualizacion:**
```json
{
  "stock_quantity": <nuevo_stock>,
  "stock_status": "instock" | "outofstock",
  "manage_stock": true
}
```

---

## OpenCode Skill

El skill `stock-update` esta definido en `.opencode/skills/stock-update/SKILL.md`.

### Ubicacion de los skills en OpenCode

OpenCode busca skills en estas rutas (por orden de prioridad):

| Ruta | Alcance |
|---|---|
| `.opencode/skills/<name>/SKILL.md` | Proyecto actual |
| `~/.config/opencode/skills/<name>/SKILL.md` | Global (todos los proyectos) |
| `.claude/skills/<name>/SKILL.md` | Compatibilidad Claude |
| `~/.claude/skills/<name>/SKILL.md` | Compatibilidad Claude global |

### Como se invoca un skill

1. **Automaticamente:** cuando trabajas en este proyecto, OpenCode detecta el skill y lo ofrece como opcion disponible
2. **Manual:** usando el comando `skill` dentro de OpenCode, el agente decide si cargarlo segun el contexto
3. **Desde un agente:** cualquier agente de OpenCode puede cargar el skill invocando la herramienta `skill`

### Requisitos
- OpenCode debe estar ejecutandose en la carpeta del proyecto (`C:\suplementos\stock-suplementos\`)
- El skill aparece listado en la descripcion de la herramienta `skill` como disponible
- Los permisos del skill se configuran en `opencode.json` si es necesario
