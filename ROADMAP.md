
# Roadmap — API Veritrade

API de análisis de importaciones Veritrade México.
Stack: FastAPI + SQLAlchemy + MySQL + Docker.

---

## Stack

| Componente       | Librería              | Razón                                    |
|------------------|-----------------------|------------------------------------------|
| Framework        | FastAPI               | Async, tipado, docs automáticas          |
| Servidor         | Uvicorn               | Estándar para FastAPI                    |
| ORM              | SQLAlchemy 2.x        | Ya usado en cargar_mysql.py              |
| Validación       | Pydantic v2           | Viene con FastAPI                        |
| DB driver        | PyMySQL               | Ya usado en el proyecto                  |
| Upload archivos  | python-multipart      | Requerido para UploadFile                |
| Excel            | openpyxl / xlsxwriter | Ya usados en procesar_veritrade.py       |
| Config           | pydantic-settings     | Lee variables desde .env                 |
| Logs             | loguru                | Opcional, logs limpios                   |

---

## Estructura del proyecto
├── app/
│ ├── init.py
│ ├── main.py # FastAPI app, routers, CORS
│ ├── config.py # Settings con pydantic-settings
│ ├── database.py # Engine, SessionLocal, get_db
│ ├── models.py # SQLAlchemy models (tabla + vistas)
│ ├── schemas.py # Pydantic schemas
│ ├── dependencies.py # Deps comunes (paginación, filtros)
│ ├── routers/
│ │ ├── init.py
│ │ ├── health.py
│ │ ├── importaciones.py
│ │ ├── reportes.py
│ │ └── procesamiento.py
│ ├── services/
│ │ ├── init.py
│ │ ├── procesar.py
│ │ ├── cargar.py
│ │ └── consultas.py
│ └── utils/
│ ├── paginacion.py
│ └── exportacion.py
├── scripts/
│ └── procesar_veritrade.py # script actual
├── init/
│ └── 01_schema.sql
├── docker-compose.yml
├── requirements.txt
├── .env
└── .gitignore


---

## Tests (Bruno)

Colección en `tests/bruno/`:
- `bruno.json` — definición de colección
- `environments/local.bru` — `baseUrl=http://localhost:8000`
- `health.bru` — 4 tests sobre GET /health

Correr: `cd tests/bruno && npx @usebruno/cli run --env local`
(Abrir la carpeta `tests/bruno` en la app Bruno.)

---

## Fases

### Fase 1 — Cimientos (0.5 día)

- [x] `app/config.py` con pydantic-settings (MYSQL_URL, API_PORT, etc.)
- [x] `app/database.py` con engine, SessionLocal, get_db
- [x] `app/main.py` mínimo con FastAPI, CORS, /health
- [x] Correr: `uvicorn app.main:app --reload`
- [x] Verificar: http://localhost:8000/docs

### Fase 2 — Modelos y schemas (0.5 día)

- [x] `app/models.py`: tabla `importaciones` + vistas `v_*`
- [x] `app/schemas.py`: un schema Pydantic por cada vista
- [x] Schemas de request para filtros comunes
- [x] Schemas de respuesta paginada genéricos

### Fase 3 — Endpoints de reportes (1 día)

Todos son GET, sin estado. **Completada** (agregación dinámica sobre `importaciones`
para soportar filtros; `app/services/consultas.py` + `app/routers/reportes.py`).
Tests Bruno en `tests/bruno/reportes/`.

| Método | Endpoint                            | Descripción                              |
|--------|-------------------------------------|------------------------------------------|
| GET    | /reportes/importadores              | Ranking con valor, kg, costo, %          |
| GET    | /reportes/importadores-cancun       | Filtrado a Cancún                        |
| GET    | /reportes/proveedores               | Ranking de exportadores                  |
| GET    | /reportes/paises-origen             | Distribución por país                    |
| GET    | /reportes/tipo-importacion          | Definitiva vs depósito fiscal            |
| GET    | /reportes/partidas                  | Fracciones arancelarias                  |
| GET    | /reportes/mensual                   | Serie temporal                           |
| GET    | /reportes/kpis                      | Totales globales                         |

Query params comunes:
- `fecha_desde`, `fecha_hasta`
- `aduana`, `pais_origen`, `partida`, `importador`, `exportador`
- `top` (default 10)
- `order_by` (valor_usd | volumen_kg)
- `page`, `page_size`

### Fase 4 — Datos crudos (0.5 día)

Completada (`app/routers/importaciones.py` + `listar_importaciones` en `consultas.py`).

| Método | Endpoint                       | Descripción                         |
|--------|--------------------------------|-------------------------------------|
| GET    | /importaciones                 | Listado paginado                    |
| GET    | /importaciones/{id}            | Detalle de un registro              |
| GET    | /importaciones/buscar?q=...    | Búsqueda en descripción comercial   |

### Fase 5 — Procesamiento (1 día)

Completada (`app/services/{procesar,cargar,jobs}.py`, `app/routers/procesamiento.py`).
Jobs síncronos en memoria (sin Redis/Celery).

| Método | Endpoint                       | Descripción                              |
|--------|--------------------------------|------------------------------------------|
| POST   | /procesamiento/upload          | Sube Excel y procesa                     |
| POST   | /procesamiento/cargar          | Carga Excel procesado a MySQL            |
| GET    | /procesamiento/status/{job_id} | Estado de un job                         |
| GET    | /procesamiento/historial       | Últimos jobs ejecutados                  |

Estrategia:
- **Síncrono** al inicio (archivos hasta ~50 MB).
- **Asíncrono** después, con BackgroundTasks o Celery + Redis.

### Fase 6 — Extras (1-2 días)

Completada (`app/routers/{meta,exportar}.py`, `app/utils/exportacion.py`). Formatos xlsx y csv.

| Método | Endpoint                                | Descripción                       |
|--------|-----------------------------------------|-----------------------------------|
| GET    | /exportar/importadores?formato=xlsx     | Descarga Excel del ranking        |
| GET    | /exportar/proveedores?formato=csv       | Descarga CSV                      |
| GET    | /exportar/importaciones?formato=xlsx    | Descarga registros filtrados      |
| GET    | /meta/aduanas                           | Valores únicos de aduana          |
| GET    | /meta/partidas                          | Catálogo de fracciones            |
| GET    | /meta/paises                            | Catálogo de países                |

Los `/meta/*` alimentan los dropdowns del frontend.

### Fase 7 — Producción (1-2 días)

- [ ] Background jobs (Celery + Redis, o RQ)
- [ ] Autenticación JWT (OAuth2 de FastAPI)
- [ ] Dockerizar la API (servicio `api` en docker-compose)
- [ ] Nginx como reverse proxy
- [ ] Rate limiting (slowapi)
- [ ] Logs estructurados (loguru + JSON)
- [ ] Health checks y métricas

### Fase 8 — Capa de consulta y mejoras de datos (demo, sin IA)

Completada (`app/services/asistente.py`, `app/routers/asistente.py`, `app/data/preguntas.json`).
Sin LLM (no hay recurso/API key): glosario de preguntas precargadas + matching
determinista por palabras clave.

**Necesidades del usuario (fuente del glosario)**
- Quién importa a México y a Cancún
- Costos unitarios (USD/kg)
- Volúmenes (kg)
- Proveedores de origen: ordenados de mayor a menor y con su % del total
- Importadores (ranking)
- Tipo de importación: depósito fiscal vs importación definitiva
- Catálogo de fracciones arancelarias
- Nota: Veritrade limita la búsqueda externa a 10 artículos por consulta

**Mejoras de datos**
- [x] `costo_unit_ponderado` en `/reportes/paises-origen` y `/reportes/tipo-importacion` (ya se calcula en `ranking`, solo falta exponerlo en el schema)
- [x] `pct_acumulado` (Pareto) en rankings de importadores, proveedores, países, tipo y partidas
- [x] `porcentaje` (porcentaje que representa cada fila sobre el total del conjunto filtrado; sin acumulado). Con el filtro `partida` da el % de peso de cada importador/proveedor/país sobre el total de ese producto
- [x] `GET /reportes/proveedores-por-pais` (dimensión `exportador × país_origen`)
- [x] `GET /reportes/tipo-importacion?solo_principales=true` (colapsa a Depósito fiscal e Importación definitiva)

**Capa de consulta (glosario + reglas)**
- [x] `app/data/preguntas.json` — glosario (fuente de verdad): `{id, categoria, pregunta, endpoint, params, palabras_clave, descripcion}`
- [x] `GET /preguntas` — glosario agrupado por categoría (`?categoria=`) para los "chips" del frontend
- [x] `POST /consulta` `{pregunta, params?}` — normaliza, puntúa por `palabras_clave`, ejecuta el endpoint y devuelve **resumen determinista + datos**; si no hay match, responde `sin_coincidencia` con las preguntas disponibles
- [x] `app/services/asistente.py` (`detectar`, `ejecutar`, plantillas de resumen) y `app/routers/asistente.py`
- [x] Schemas `PreguntaOut`, `ConsultaIn`, `ConsultaOut`

Ejemplo de resumen (ranking):
> Top 10 de importadores: **MAYA SEA FOODS** lidera con 33.1M USD (9.2%). El top 10 concentra el 62.4% del valor analizado.

Preparado para IA futura: el dispatcher de ejecución se reutiliza para enchufar un
LLM (tool-calling) cuando exista API key, sin reescribir la capa de datos.

**Tests:** `tests/bruno/asistente/` + ampliación de reportes (`pct_acumulado`, `solo_principales`).

### Fase 9 — Agente LLM con tools (Groq)

Completada (`app/services/agente.py`, `app/services/tools.py`, `app/services/llm.py`,
`app/routers/agente.py`, `app/data/esquema.json`). Se mantiene `POST /consulta`
(reglas) separado como capa determinista.

- [x] `POST /agente/consulta` `{pregunta}` — stateless, sin streaming
- [x] 5 tools sobre `consultas.py`: `resumen_kpis`, `ranking(dimension)`, `serie_mensual`, `buscar_operaciones`, `catalogo`
- [x] `ranking` unifica importadores, importadores_cancun, proveedores, proveedores_por_pais, paises_origen, partidas y tipo_importacion
- [x] Grounding: sin tool-call → `No tengo ese dato en la base de datos.`; `datos_usados` para auditoría
- [x] Saludos/agradecimientos: respuesta cordial sin tools (detección de saludo puro + regla 13 del prompt)
- [x] Diccionario de datos (`app/data/esquema.json`) inyectado al system prompt
- [x] Manejo de `429`/`413` del tier gratuito (8000 TPM) con respuesta clara
- [x] Schemas `AgenteIn`, `ToolCallOut`, `AgenteOut`; `groq` en `requirements.txt`

**Tests:** `tests/bruno/agente/` (consulta con tools y fuera de tema).

---

## Contrato de endpoint (ejemplo)

### GET /reportes/importadores

Query:
