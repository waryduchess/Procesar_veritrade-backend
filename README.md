# Procesar_veritrade-backend

Backend para procesar datos de importaciones y compras por artículo de Veritrade (México): pipeline de limpieza Excel/CSV → MySQL y API FastAPI para reportes.

> Proyecto de prueba/demo. **Sin autenticación ni medidas de seguridad.**

## Requisitos

- Python 3.14
- Docker + Docker Compose
- Node.js (opcional, para los tests con Bruno)

## Puesta en marcha

### 1. Clonar y crear el entorno virtual

```bash
git clone <url-del-repo> Procesar_veritrade-backend
cd Procesar_veritrade-backend
cp .env.example .env   # luego pon tu DEEPSEEK_API_KEY
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

> Usa siempre `.venv/bin/python -m pip` (no `pip` a secas) para asegurar que instalas en el venv correcto.

### 2. Variables de entorno

El archivo `.env` está en `.gitignore`, así que créalo a partir de `.env.example`:

```env
MYSQL_URL=mysql+pymysql://veritrade:veritrade123@localhost:3307/veritrade?charset=utf8mb4
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=tu_api_key_de_deepseek
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_THINKING=false

# Agente (0 en tokens = sin límite impuesto por la app)
AGENTE_MAX_TOOL_CALLS=12
AGENTE_MAX_TOKENS=0
AGENTE_INFORME_MAX_TOKENS=0
AGENTE_TIMEOUT=120
AGENTE_HISTORIAL_MENSAJES=12
AGENTE_HISTORIAL_CHARS=12000
```

### 3. Levantar MySQL

```bash
docker compose up -d
```

Esto crea la base `veritrade`, el usuario `veritrade/veritrade123` y ejecuta `database/schema.sql`
(tablas `importaciones` y `compras_articulos` + vistas `v_*`) en el primer arranque.

> MySQL se expone en el puerto **3307** para no chocar con otros proyectos que usen 3306.
> Si cambias el puerto en `docker-compose.yml`, ajusta `MYSQL_URL` en `.env`.

### 4. Correr la API

```bash
.venv/bin/uvicorn app.main:app --reload
```

- Documentación: http://localhost:8000/docs
- Health check: http://localhost:8000/health → `{"status":"ok","db":"ok"}`

### 5. Desplegar la API en el VPS con Docker

El compose de producción solo levanta la API. **MySQL debe existir por separado**
(servicio administrado o contenedor externo); no se incluye en este compose.

```bash
cp .env.production.example .env
# Edita MYSQL_URL con el host, usuario, contraseña y base reales.
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

La API queda publicada únicamente en `127.0.0.1:${API_PORT:-8000}`. No abras el
puerto 8000 al público: la API aún no tiene autenticación. El frontend/proxy futuro
debe entrar por la red Docker `veritrade_net` usando `veritrade_api:8000`, y publicar
solo `80/443` con TLS.

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
curl http://127.0.0.1:8000/health
```

- El contenedor corre como usuario no root y usa un solo worker porque los jobs de
  procesamiento viven en memoria.
- El healthcheck consulta `/health` y exige `"db": "ok"`.
- `uploads/` y `salida/` se guardan en los volúmenes `veritrade_uploads` y
  `veritrade_salida`.
- Para actualizar: `git pull`, rebuild y `up -d`.

Respaldo de los volúmenes:

```bash
mkdir -p backups
docker run --rm -v veritrade_uploads:/data -v "$PWD/backups":/backup alpine tar czf /backup/uploads.tar.gz -C /data .
docker run --rm -v veritrade_salida:/data -v "$PWD/backups":/backup alpine tar czf /backup/salida.tar.gz -C /data .
```

## Pipeline de datos (opcional)

```bash
# 1. Limpia el Excel de Veritrade y genera salida/veritrade_limpio.xlsx
.venv/bin/python procesar_veritrade.py

# 2. Reemplaza la tabla con el Excel procesado
.venv/bin/python cargar_mysql.py

# 2b. Agrega otro Excel sin borrar lo ya cargado
.venv/bin/python cargar_mysql.py --agregar
```

> Para un segundo Excel: procésalo (sobrescribe `salida/veritrade_limpio.xlsx`) y
> cárgalo con `--agregar` o `POST /procesamiento/cargar?modo=agregar`.
>
> Cada carga exitosa guarda una copia del Excel limpio en `salida/historial/` con
> timestamp y modo. La copia se puede desactivar con `guardar_copia=False` al usar
> el servicio desde código.

## Compras por artículo (CSV)

El módulo de compras usa `ComprasporartículoBD707.csv` (UTF-8, encabezado en la
fila 7). Carga inicial o reemplazo:

```bash
.venv/bin/python cargar_compras.py
```

- Por defecto **reemplaza** `compras_articulos`; usa `--agregar` para conservar lo existente.
- También se puede cargar desde la interfaz con `POST /compras/importar`
  (`modo=reemplazar|agregar`, archivo `.csv`, límite 20 MB).
- Clasifica nacional/internacional según `app/data/proveedores_internacionales.json`
  (alias normalizados; el CSV omite sufijos como `SA DE CV`).
- Conserva duplicados exactos y valida el total contra la fila `Total` del CSV.
- `fraccion_valida` solo es `true` cuando la fracción tiene formato válido; los
  valores vacíos se cuentan como `sin_fraccion`.

## Tests (Bruno)

La colección está en `tests/bruno/`. El módulo de compras está en `tests/bruno/compras/`.

```bash
cd tests/bruno
npx -y @usebruno/cli run --env local
```

> El CLI de Bruno debe ejecutarse **desde la raíz de la colección** (`tests/bruno`).
> También puedes abrir esa carpeta directamente en la app de Bruno.

## Endpoints

- `GET /health`
- `GET /reportes/{importadores,importadores-cancun,proveedores,proveedores-por-pais,paises-origen,tipo-importacion,partidas,mensual,kpis,comparativo,matriz}`
- `GET /importaciones`, `/importaciones/{id}`, `/importaciones/buscar?q=`
- `GET /meta/{aduanas,paises,partidas}`
- `GET /compras/{kpis,mensual,categorias,proveedores,meta,articulos,exportar}`
- `GET /compras/precios`, `/compras/precios/mensual`, `/compras/comparativo` — analítica de precios y comparativo mensual
- `POST /compras/importar` (`?modo=agregar|reemplazar`) — carga CSV de compras
- `GET /exportar/{importadores,proveedores,importaciones}?formato=xlsx|csv`
- `GET /preguntas` (`?categoria=`) y `POST /consulta` — glosario de preguntas precargadas (reglas, sin IA)
- `POST /agente/consulta` — agente LLM + tools (DeepSeek/Groq) que responde solo con datos de la BD
- `POST /procesamiento/upload`, `POST /procesamiento/upload-lote`, `POST /procesamiento/cargar` (`?modo=agregar|reemplazar`), `GET /procesamiento/status/{job_id}`, `GET /procesamiento/historial`

`POST /procesamiento/upload` recibe un archivo; `POST /procesamiento/upload-lote`
recibe varios (`archivos`) y genera un único `salida/veritrade_limpio.xlsx`
combinado, sin tocar MySQL. Después se llama a `POST /procesamiento/cargar` una sola
vez.

`POST /procesamiento/cargar` usa `modo=reemplazar` por defecto: elimina los registros
actuales e inserta los del Excel dentro de una transacción. Con `modo=agregar` inserta
el Excel procesado sin borrar los registros existentes.

Query params comunes en reportes/importaciones: `fecha_desde`, `fecha_hasta`, `aduana`,
`pais_origen`, `partida`, `importador`, `exportador`, `page`, `page_size`, `top`,
`order_by` (`valor_usd` | `volumen_kg` | `mes`), `desc`.

`/compras/*` acepta `fecha_desde`, `fecha_hasta`, `categoria`, `proveedor`,
`descripcion` (descripción exacta), `ambito` (`nacional` | `internacional`),
`fraccion`, `q` (descripción/proveedor/fracción), `page`, `page_size`, `top`,
`order_by` (`fecha` | `importe_mxn` | `precio_unitario_mxn` | `cantidad` |
`proveedor`) y `desc`. Todos los importes se expresan en **MXN**.
`GET /compras/exportar` acepta `formato=xlsx|csv`.

`GET /compras/precios` calcula el precio promedio anual ponderado por cantidad
(`importe_mxn / cantidad`), agrupado por descripción exacta; acepta `anio` y `top`.
`GET /compras/precios/mensual` requiere `descripcion` y acepta `anio` para devolver
la serie mensual ponderada del producto.

`GET /compras/comparativo` compara dos meses calendario (`mes` y `comparar`,
formato `YYYY-MM`; por defecto el último mes completo contra el anterior) por
`dimension=descripcion|categoria|proveedor` y
`metrica=importe_mxn|cantidad|precio_promedio_mxn`; acepta `order_by=delta_abs|delta_pp|valor_actual`,
`top` y `min_registros`. Los filtros de fecha global se ignoran. Para precios no se
calcula participación y `share_*`/`delta_pp` quedan nulos.

`GET /reportes/tipo-importacion` acepta `solo_principales=true` para agrupar en
Depósito fiscal e Importación definitiva.

`GET /reportes/comparativo` compara dos meses calendario (`mes` y `comparar`,
formato `YYYY-MM`; por defecto el último mes completo contra el anterior) por
`dimension=partida|pais_origen|importador|exportador` y
`metrica=valor_usd|volumen_kg`. Devuelve valor actual/previo, variación porcentual,
participación por mes, cambio en puntos porcentuales, registros, estado (`sube`,
`baja`, `nuevo`, `desaparece`, `sin_cambio`) y lista de períodos con bandera
`completo`. Los filtros de fecha global se ignoran; el período se elige con
`mes`/`comparar`.

`GET /reportes/matriz` devuelve una matriz de partidas ×
`columna=pais_origen|exportador`, con `metrica=valor_usd|volumen_kg`,
`top_filas`, `top_columnas` y `min_registros`. Incluye celdas con valor, volumen,
registros, participación dentro de la fila y marca de muestra suficiente; las filas
y columnas fuera del top se agrupan en `Otros`. En proveedores se excluyen las
operaciones sin exportador y se reportan en `omitidos.sin_exportador`.

Los rankings incluyen `pct_total`/`pct_acumulado` (valor USD) y `porcentaje`
(peso kg). El porcentaje se calcula sobre el total del conjunto filtrado, así que
filtrando por `partida` obtienes el peso de cada actor sobre el total importado de
ese producto:

```bash
# % de peso de cada importador sobre el total del producto 304610100
curl "localhost:8000/reportes/importadores?partida=304610100&order_by=volumen_kg&top=10"
```

### Capa de consulta (sin IA)

`POST /consulta` recibe `{"pregunta": "...", "params": {...}}`, mapea el texto a una
pregunta del glosario (`app/data/preguntas.json`) por palabras clave y devuelve un
**resumen determinista + los datos** del endpoint correspondiente. Si no hay
coincidencia responde `encontrada: false` con sugerencias. No usa LLM.

```bash
curl -X POST localhost:8000/consulta -H 'Content-Type: application/json' \
  -d '{"pregunta":"cuales son los principales importadores"}'
```

### Agente (LLM + tools)

`POST /agente/consulta` responde en lenguaje natural usando **solo** resultados de
la base de datos. El proveedor es configurable con `LLM_PROVIDER` (`deepseek` por
defecto con `deepseek-flash`; o `groq`).

Request:

```json
{
  "pregunta": "Hazme un informe de compras de camarón en 2026",
  "historial": [],
  "modulo": "auto",
  "modo": "auto"
}
```

- `modulo`: `auto`, `importaciones` o `compras`. Si es ambiguo, el agente pide aclaración.
- `modo`: `auto`, `consulta` o `informe`. `auto` detecta informes, análisis y recomendaciones.
- `historial`: máximo 50 mensajes; cada mensaje acepta hasta 40,000 caracteres. El servidor usa los últimos 12, resume las respuestas del asistente y limita el contexto efectivo a ~12,000 caracteres.
- Las respuestas largas no se reenvían completas al modelo: se conserva un resumen con encabezados, hallazgos y limitaciones.
- Response: `respuesta`, `tool_calls`, `datos_usados`, `modo`, `modulo` y
  `filtros_sugeridos`.
- `filtros_sugeridos` contiene módulo, filtros validados contra catálogos y pestaña
  sugerida, para que el frontend aplique la consulta en la vista correspondiente.
  Ejemplo: `{"modulo":"compras","filtros":{"categoria":"AVES"},"tab":"graficas"}`.
  Para aduanas usa el valor canónico, por ejemplo `CANCUN- QUINTANA ROO`.

**Contexto de la IA**

- `app/data/esquema.json`: diccionario de Importaciones.
- `app/data/esquema_compras.json`: diccionario de Compras.
- `app/data/api_endpoints.json`: catálogo de endpoints de solo lectura y su tool.
- `app/data/playbooks.json`: guías para producto, proveedor, categoría, país,
  precios, comparativo, recomendación e informe.

**Tools (15)**

- Importaciones: `importaciones_kpis`, `importaciones_ranking`,
  `importaciones_mensual`, `importaciones_comparativo`, `importaciones_buscar`,
  `importaciones_catalogo`.
- Compras: `compras_kpis`, `compras_ranking`, `compras_mensual`,
  `compras_precio_producto`, `compras_comparativo`, `compras_buscar`,
  `compras_catalogo`.
- Control: `pedir_aclaracion` y `capacidades`.

Las tools ejecutan internamente `app/services/consultas.py` y
`app/services/consultas_compras.py`; no hacen peticiones HTTP contra la propia API.

**Comportamiento**

- Si no hay datos, responde `No tengo ese dato en la base de datos.`
- Si el módulo, producto o proveedor es ambiguo, pide aclaración.
- Los informes se entregan en Markdown dentro del chat.
- Las recomendaciones incluyen hallazgo, evidencia y limitación.
- No hay pronósticos, noticias ni conocimiento externo.
- No se mezclan USD de Importaciones con MXN de Compras.
- No se suman cantidades de Compras porque mezclan kg y piezas.

**Límites de consumo**

- La app **no impone un límite de tokens de salida** por defecto:
  `AGENTE_MAX_TOKENS=0` y `AGENTE_INFORME_MAX_TOKENS=0` omiten `max_tokens` y dejan
  que el proveedor use su máximo. Puedes fijar un valor positivo si necesitas
  controlar costo o latencia.
- `AGENTE_MAX_TOOL_CALLS=12` y `AGENTE_TIMEOUT=120`.
- `AGENTE_HISTORIAL_RESUMEN_CHARS=2000` controla el resumen de cada respuesta del
  asistente enviado como historial.
- Los límites de saldo, tasa, contexto y tokens/día de la cuenta de DeepSeek/Groq
  son externos a la app y no se pueden eliminar desde este código.
- Sin saldo en DeepSeek, el endpoint responde `402`; con rate limit, `429`.

```bash
curl -X POST localhost:8000/agente/consulta -H 'Content-Type: application/json' \
  -d '{"pregunta":"¿Cuál es el valor y volumen total importado?","modulo":"importaciones"}'
```

Para un seguimiento, envía los turnos previos:

```bash
curl -X POST localhost:8000/agente/consulta -H 'Content-Type: application/json' \
  -d '{"pregunta":"¿Y qué proveedores les venden?","modulo":"importaciones","historial":[
    {"role":"user","content":"¿Quiénes son los top 3 importadores de la partida 304610100?"},
    {"role":"assistant","content":"...","modulo":"importaciones"}
  ]}'
```

> **DeepSeek (default):** el costo y los límites dependen de tu cuenta y saldo;
> `deepseek-flash` es la opción económica. Sin saldo, el endpoint responde `402`.
>
> **Groq (fallback, plan gratis):** 8000 tokens/minuto (TPM) y 200.000
> tokens/día (TPD) **por modelo**. El `openai/gpt-oss-120b` se agota rápido; para
> desarrollo usa `GROQ_MODEL=openai/gpt-oss-20b`. Cada desarrollador debe usar su
> propia `GROQ_API_KEY`. Si se agota la cuota, el endpoint responde `429` con el
> modelo, el tipo de límite (TPM/TPD) y el tiempo de reintento.
>
> Los tests de `tests/bruno/agente/` hacen varias llamadas al LLM. Con Groq 120b
> pueden fallar por TPM aunque el saludo funcione por separado.

## Estructura

```
app/                 # API FastAPI (config, database, models, schemas, routers, services, utils)
app/data/esquema.json              # diccionario de datos de Importaciones para el agente
app/data/esquema_compras.json      # diccionario de datos de Compras para el agente
app/data/api_endpoints.json        # endpoints de solo lectura disponibles para el agente
app/data/playbooks.json            # guías de análisis, informes y recomendaciones
app/data/proveedores_internacionales.json  # proveedores clasificados como internacionales
database/            # schema.sql (tabla + vistas)
salida/              # Excel procesado y copias en salida/historial/ (ignorado)
uploads/             # Excel originales de cada carga (ignorado)
tests/bruno/         # colección de pruebas Bruno
procesar_veritrade.py# limpieza del Excel (script standalone)
cargar_mysql.py      # carga a MySQL (script standalone)
cargar_compras.py    # carga el CSV de compras a MySQL (script standalone)
docker-compose.yml   # MySQL 8 para desarrollo local
docker-compose.prod.yml # API para VPS (MySQL externo)
Dockerfile           # imagen de la API
.env.production.example # plantilla de variables para VPS
ROADMAP.md           # plan de fases del proyecto
```
