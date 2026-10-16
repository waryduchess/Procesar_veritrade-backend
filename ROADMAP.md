
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

- [ ] `app/config.py` con pydantic-settings (MYSQL_URL, API_PORT, etc.)
- [ ] `app/database.py` con engine, SessionLocal, get_db
- [ ] `app/main.py` mínimo con FastAPI, CORS, /health
- [ ] Correr: `uvicorn app.main:app --reload`
- [ ] Verificar: http://localhost:8000/docs

### Fase 2 — Modelos y schemas (0.5 día)

- [ ] `app/models.py`: tabla `importaciones` + vistas `v_*`
- [ ] `app/schemas.py`: un schema Pydantic por cada vista
- [ ] Schemas de request para filtros comunes
- [ ] Schemas de respuesta paginada genéricos

### Fase 3 — Endpoints de reportes (1 día)

Todos son GET, sin estado.

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

| Método | Endpoint                       | Descripción                         |
|--------|--------------------------------|-------------------------------------|
| GET    | /importaciones                 | Listado paginado                    |
| GET    | /importaciones/{id}            | Detalle de un registro              |
| GET    | /importaciones/buscar?q=...    | Búsqueda en descripción comercial   |

### Fase 5 — Procesamiento (1 día)

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

---

## Contrato de endpoint (ejemplo)

### GET /reportes/importadores

Query:
