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
```

### 3. Levantar MySQL

```bash
docker compose up -d
```

Esto crea la base `veritrade`, el usuario `veritrade/veritrade123` y ejecuta `database/schema.sql`
(tabla `importaciones` + vistas `v_*`) en el primer arranque.

> MySQL se expone en el puerto **3307** para no chocar con otros proyectos que usen 3306.
> Si cambias el puerto en `docker-compose.yml`, ajusta `MYSQL_URL` en `.env`.

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
- `GET /preguntas` (`?categoria=`) y `POST /consulta` — glosario de preguntas precargadas (reglas, sin IA)
- `POST /agente/consulta` — agente LLM + tools (DeepSeek/Groq) que responde solo con datos de la BD
- `POST /procesamiento/upload`, `POST /procesamiento/cargar`, `GET /procesamiento/status/{job_id}`, `GET /procesamiento/historial`

Query params comunes en reportes/importaciones: `fecha_desde`, `fecha_hasta`, `aduana`,
`pais_origen`, `partida`, `importador`, `exportador`, `page`, `page_size`, `top`,
`order_by` (`valor_usd` | `volumen_kg` | `mes`), `desc`.

`GET /reportes/tipo-importacion` acepta `solo_principales=true` para agrupar en
Depósito fiscal e Importación definitiva.

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

`POST /agente/consulta` recibe `{"pregunta": "...", "historial": [...]}` (historial opcional) y responde en lenguaje natural
usando **solo** resultados de la base de datos. El proveedor es configurable con
`LLM_PROVIDER` (`deepseek` por defecto con `deepseek-flash`; o `groq`). El modelo
elige entre 5 tools que ejecutan internamente `app/services/consultas.py`:
`resumen_kpis`, `ranking(dimension=...)`, `serie_mensual`, `buscar_operaciones` y
`catalogo`.

- **Memoria conversacional**: acepta `historial` (máx. 50 mensajes; usa los últimos 10) para preguntas de seguimiento. El servidor no guarda sesiones: el cliente envía el contexto en cada request.
- **Proveedor**: `deepseek` (default, thinking desactivado) o `groq`; cambiar
  `LLM_PROVIDER` o las API keys requiere reiniciar el backend.
- **Sin SQL libre**: el modelo solo puede llamar tools acotadas.
- **Anti-alucinación**: si no llama ninguna tool, responde
  `No tengo ese dato en la base de datos.` y no inventa.
- **Saludos/agradecimientos**: responde cordialmente en 1-2 líneas sin consultar
  la BD (no llama tools).
- Devuelve `respuesta`, `tool_calls` y `datos_usados` (auditoría de cada tool y su resultado).

```bash
curl -X POST localhost:8000/agente/consulta -H 'Content-Type: application/json' \
  -d '{"pregunta":"¿Cuál es el valor y volumen total importado?"}'
```

Para una pregunta de seguimiento, envía los turnos previos:

```bash
curl -X POST localhost:8000/agente/consulta -H 'Content-Type: application/json' \
  -d '{"pregunta":"¿Y qué proveedores les venden?","historial":[
    {"role":"user","content":"¿Quiénes son los top 3 importadores de la partida 304610100?"},
    {"role":"assistant","content":"..."}
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
database/            # schema.sql (tabla + vistas)
tests/bruno/         # colección de pruebas Bruno
procesar_veritrade.py# limpieza del Excel (script standalone)
cargar_mysql.py      # carga a MySQL (script standalone)
docker-compose.yml   # MySQL 8
ROADMAP.md           # plan de fases del proyecto
```
