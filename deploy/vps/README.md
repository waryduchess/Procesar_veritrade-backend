# Prueba VPS: Veritrade con Nginx, API y MySQL

Stack de prueba para levantar la base de Veritrade, la API FastAPI y el frontend
detrás de Nginx. No modifica Apache ni la base nativa del host.

## Servicios

- `veritrade_db_vps`: MySQL 8, solo en `127.0.0.1:3307`.
- `veritrade_api_vps`: FastAPI, solo en `127.0.0.1:8001`.
- `veritrade_frontend_vps`: Nginx con la SPA en `/compras/` y proxy `/compras/api/`.
- Red compartida: `veritrade_vps_net`.
- Volúmenes: `veritrade_mysql_vps`, `veritrade_uploads_vps`, `veritrade_salida_vps`.

## Requisitos

- Docker y Docker Compose.
- El usuario de despliegue debe poder ejecutar Docker.
- El repo del frontend debe estar en `../consulta_veritrade_frontend` respecto al backend,
  o definir `FRONTEND_DIR`.
- Directorio de llaves JWT en `/root/horbis-jwt-keys` o la ruta de
  `JWT_KEYS_DIR`. Para la primera prueba `AUTH_ENABLED=false`; para SSO
  necesitas `compras-private.pem` en la suite y `compras-public.pem` en el API.

## Configuración

1. Copiar el ejemplo y ajustar contraseñas, URLs y llaves:

   ```bash
   cp .env.vps.example .env
   chmod 600 .env
   ```

2. Verificar que `MYSQL_URL` use el mismo usuario y contraseña que `MYSQL_USER` y
   `MYSQL_PASSWORD`, y el host `db`.

3. Crear el directorio `/root/horbis-jwt-keys`. Si vas a usar SSO, genera
   `compras-private.pem` y `compras-public.pem`; el API monta el directorio en
   `/run/secrets`.

4. En el repo del frontend, crear `.env` a partir de `.env.vps.example` si se
   quieren cambiar los valores por defecto.

## Levantar

```bash
./deploy/vps/levantar.sh up
```

El script crea la red, levanta la DB y la API, espera `/health` y luego levanta
el frontend.

URLs de prueba:

- API: `http://127.0.0.1:8001/health`
- Frontend: `http://127.0.0.1:8080/compras/`

## Cargar datos

Opción rápida: restaurar un dump de la base local.

```bash
./deploy/vps/levantar.sh db-restore /ruta/veritrade.sql
```

Opción con los loaders del repo:

```bash
./deploy/vps/levantar.sh load -- cargar_mysql.py --help
```

El servicio `loader` monta el repo completo en `/app`; los scripts no están en
la imagen de producción.

## Comandos

```bash
./deploy/vps/levantar.sh status
./deploy/vps/levantar.sh logs api
./deploy/vps/levantar.sh logs frontend
./deploy/vps/levantar.sh health
./deploy/vps/levantar.sh db-dump
./deploy/vps/levantar.sh down
./deploy/vps/levantar.sh destroy
```

`down` conserva los volúmenes. `destroy` los elimina y pide confirmación.

## Apache

No modificar Apache sin respaldar el vhost y revisar
`/root/horbis-proteger-apache-dev.sh` y `/usr/local/sbin/horbis-ops`.

Ejemplo para el vhost de `dev.horbismex.com`:

```apache
ProxyPreserveHost On
ProxyPass /compras/ http://127.0.0.1:8080/compras/
ProxyPassReverse /compras/ http://127.0.0.1:8080/compras/
```

Después:

```bash
apachectl configtest
```

Si el test pasa, recargar Apache de forma controlada.

## Integración con la suite PHP

El frontend y la suite deben quedar en el mismo origen:

- `HORBIS_COMPRAS_APP_URL=https://dev.horbismex.com/compras/`
- CORS del API: `https://dev.horbismex.com`
- `VITE_AUTH_CONTEXT_URL=/api/auth/context.php`
- `AUTH_ENABLED=true` en el API y llave pública JWT montada.
- Para la primera prueba del proxy sin SSO, deja `AUTH_ENABLED=false` y
  `VITE_AUTH_ENABLED=false`; valida la red y el proxy antes de exponerlo por Apache.

## Seguridad

- No publicar MySQL en `3306`.
- No exponer la API ni la DB a Internet.
- No subir `.env` ni llaves al repositorio.
- No reutilizar volúmenes entre dev y app.
