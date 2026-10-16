# Procesar_veritrade-backend

Backend para procesar datos de importaciones de Veritrade (México): pipeline de limpieza Excel → MySQL y API FastAPI para reportes.

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
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

> Usa siempre `.venv/bin/python -m pip` (no `pip` a secas) para asegurar que instalas en el venv correcto.

### 2. Variables de entorno

El archivo `.env` está en `.gitignore`, así que créalo manualmente en la raíz:

```env
MYSQL_URL=mysql+pymysql://veritrade:veritrade123@localhost:3306/veritrade?charset=utf8mb4
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### 3. Levantar MySQL

```bash
docker compose up -d
```

Esto crea la base `veritrade`, el usuario `veritrade/veritrade123` y ejecuta `database/schema.sql`
(tabla `importaciones` + vistas `v_*`) en el primer arranque.

### 4. Correr la API

```bash
.venv/bin/uvicorn app.main:app --reload
```

- Documentación: http://localhost:8000/docs
- Health check: http://localhost:8000/health → `{"status":"ok","db":"ok"}`

## Pipeline de datos (opcional)

```bash
# 1. Limpia el Excel de Veritrade y genera salida/veritrade_limpio.xlsx
.venv/bin/python procesar_veritrade.py

# 2. Carga el Excel procesado a MySQL (trunca e inserta)
.venv/bin/python cargar_mysql.py
```

## Tests (Bruno)

La colección está en `tests/bruno/`.

```bash
cd tests/bruno
npx -y @usebruno/cli run --env local
```

> El CLI de Bruno debe ejecutarse **desde la raíz de la colección** (`tests/bruno`).
> También puedes abrir esa carpeta directamente en la app de Bruno.

## Endpoints

- `GET /health`
- `GET /reportes/{importadores,importadores-cancun,proveedores,proveedores-por-pais,paises-origen,tipo-importacion,partidas,mensual,kpis}`
- `GET /importaciones`, `/importaciones/{id}`, `/importaciones/buscar?q=`
- `GET /meta/{aduanas,paises,partidas}`
- `GET /exportar/{importadores,proveedores,importaciones}?formato=xlsx|csv`
- `GET /preguntas` (`?categoria=`) y `POST /consulta` — glosario de preguntas precargadas
- `POST /procesamiento/upload`, `POST /procesamiento/cargar`, `GET /procesamiento/status/{job_id}`, `GET /procesamiento/historial`

Query params comunes en reportes/importaciones: `fecha_desde`, `fecha_hasta`, `aduana`,
`pais_origen`, `partida`, `importador`, `exportador`, `page`, `page_size`, `top`,
`order_by` (`valor_usd` | `volumen_kg` | `mes`), `desc`.

`GET /reportes/tipo-importacion` acepta `solo_principales=true` para agrupar en
Depósito fiscal e Importación definitiva.

### Capa de consulta (sin IA)

`POST /consulta` recibe `{"pregunta": "...", "params": {...}}`, mapea el texto a una
pregunta del glosario (`app/data/preguntas.json`) por palabras clave y devuelve un
**resumen determinista + los datos** del endpoint correspondiente. Si no hay
coincidencia responde `encontrada: false` con sugerencias. No usa LLM.

```bash
curl -X POST localhost:8000/consulta -H 'Content-Type: application/json' \
  -d '{"pregunta":"cuales son los principales importadores"}'
```

## Estructura

```
app/                 # API FastAPI (config, database, models, schemas, routers, services, utils)
database/            # schema.sql (tabla + vistas)
tests/bruno/         # colección de pruebas Bruno
procesar_veritrade.py# limpieza del Excel (script standalone)
cargar_mysql.py      # carga a MySQL (script standalone)
docker-compose.yml   # MySQL 8
ROADMAP.md           # plan de fases del proyecto
```
