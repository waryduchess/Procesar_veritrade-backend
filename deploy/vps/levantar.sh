#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$(cd "$BACKEND_DIR/.." && pwd)/consulta_veritrade_frontend}"
BACKEND_COMPOSE="$BACKEND_DIR/docker-compose.vps.yml"
FRONTEND_COMPOSE="$FRONTEND_DIR/docker-compose.vps.yml"

API_PORT="${API_PORT:-8001}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
VERITRADE_NETWORK="${VERITRADE_NETWORK:-veritrade_vps_net}"
JWT_KEYS_DIR="${JWT_KEYS_DIR:-/root/horbis-jwt-keys}"
AUTH_ENABLED="${AUTH_ENABLED:-false}"

log() {
    printf '[veritrade-vps] %s\n' "$*"
}

fail() {
    printf '[veritrade-vps] ERROR: %s\n' "$*" >&2
    exit 1
}

read_env_file() {
    local file="$1"
    local key="$2"
    local fallback="$3"
    local value=""

    if [ -f "$file" ]; then
        value="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r')"
    fi

    printf '%s' "${value:-$fallback}"
}

require() {
    command -v docker >/dev/null 2>&1 || fail "Docker no está instalado."
    docker compose version >/dev/null 2>&1 || fail "docker compose no está disponible."
    docker info >/dev/null 2>&1 || fail "Tu usuario no puede usar Docker. Agrega codex-deploy al grupo docker o ejecuta con sudo."
    command -v curl >/dev/null 2>&1 || fail "curl no está instalado."

    [ -f "$BACKEND_DIR/.env" ] || fail "Falta $BACKEND_DIR/.env. Copia .env.vps.example y ajusta los valores."
    [ -d "$FRONTEND_DIR" ] || fail "No existe FRONTEND_DIR=$FRONTEND_DIR."
    [ -f "$FRONTEND_COMPOSE" ] || fail "Falta $FRONTEND_COMPOSE."

    API_PORT="$(read_env_file "$BACKEND_DIR/.env" API_PORT "$API_PORT")"
    MYSQL_PORT="$(read_env_file "$BACKEND_DIR/.env" MYSQL_PORT "$MYSQL_PORT")"
    FRONTEND_PORT="$(read_env_file "$FRONTEND_DIR/.env" FRONTEND_PORT "$FRONTEND_PORT")"
    VERITRADE_NETWORK="$(read_env_file "$BACKEND_DIR/.env" VERITRADE_NETWORK "$VERITRADE_NETWORK")"
    JWT_KEYS_DIR="$(read_env_file "$BACKEND_DIR/.env" JWT_KEYS_DIR "$JWT_KEYS_DIR")"
    AUTH_ENABLED="$(read_env_file "$BACKEND_DIR/.env" AUTH_ENABLED "$AUTH_ENABLED")"

    [ -d "$JWT_KEYS_DIR" ] || fail "Falta el directorio de llaves JWT: $JWT_KEYS_DIR"
    if [ "$AUTH_ENABLED" = "true" ] && [ ! -f "$JWT_KEYS_DIR/compras-public.pem" ]; then
        fail "AUTH_ENABLED=true pero falta $JWT_KEYS_DIR/compras-public.pem"
    fi

    export API_PORT MYSQL_PORT FRONTEND_PORT VERITRADE_NETWORK JWT_KEYS_DIR AUTH_ENABLED
}

network_up() {
    if ! docker network inspect "$VERITRADE_NETWORK" >/dev/null 2>&1; then
        log "Creando red $VERITRADE_NETWORK"
        docker network create "$VERITRADE_NETWORK" >/dev/null
    fi
}

wait_api() {
    log "Esperando API en http://127.0.0.1:${API_PORT}/health ..."
    for _ in $(seq 1 60); do
        if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
            log "API lista."
            return 0
        fi
        sleep 2
    done
    fail "La API no respondió en 120s. Revisa: $0 logs api"
}

show_urls() {
    log "API:      http://127.0.0.1:${API_PORT}/health"
    log "Frontend: http://127.0.0.1:${FRONTEND_PORT}/compras/"
    log "DB:       127.0.0.1:${MYSQL_PORT}"
    log "Red:      ${VERITRADE_NETWORK}"
}

up() {
    require
    network_up

    log "Levantando DB y API..."
    docker compose -f "$BACKEND_COMPOSE" up -d --build db api
    wait_api

    log "Levantando frontend..."
    docker compose -f "$FRONTEND_COMPOSE" up -d --build frontend

    log "Stack arriba."
    show_urls
}

down() {
    require
    log "Bajando frontend..."
    docker compose -f "$FRONTEND_COMPOSE" down || true
    log "Bajando DB y API..."
    docker compose -f "$BACKEND_COMPOSE" down || true
    log "Contenedores detenidos. Los volúmenes se conservan."
}

destroy() {
    require
    log "ADVERTENCIA: se eliminarán contenedores y volúmenes de la prueba."
    read -r -p "Escribe BORRAR para continuar: " confirm
    [ "$confirm" = "BORRAR" ] || fail "Cancelado."
    docker compose -f "$FRONTEND_COMPOSE" down -v || true
    docker compose -f "$BACKEND_COMPOSE" down -v || true
    log "Stack y volúmenes eliminados."
}

status() {
    require
    docker ps -a --filter "name=veritrade_" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
}

logs() {
    require
    local service="${1:-}"
    case "$service" in
        frontend) docker compose -f "$FRONTEND_COMPOSE" logs -f frontend ;;
        db|api|loader) docker compose -f "$BACKEND_COMPOSE" logs -f "$service" ;;
        "") docker compose -f "$BACKEND_COMPOSE" logs -f ;;
        *) fail "Servicio desconocido: $service (usa db, api, frontend)" ;;
    esac
}

health() {
    require
    log "API:"
    curl -fsS "http://127.0.0.1:${API_PORT}/health" || fail "La API no responde."
    printf '\n'
    log "Frontend:"
    curl -fsS -I "http://127.0.0.1:${FRONTEND_PORT}/compras/" | head -1 || fail "El frontend no responde."
}

db_dump() {
    require
    local file="${1:-$BACKEND_DIR/backups/veritrade_vps_$(date +%Y%m%d_%H%M%S).sql}"
    mkdir -p "$(dirname "$file")"
    log "Exportando base de datos a $file ..."
    docker compose -f "$BACKEND_COMPOSE" exec -T db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --databases "$MYSQL_DATABASE"' > "$file"
    log "Respaldo listo."
}

db_restore() {
    require
    local file="${1:-}"
    [ -n "$file" ] && [ -f "$file" ] || fail "Uso: $0 db-restore /ruta/al/respaldo.sql"
    log "Restaurando $file ..."
    docker compose -f "$BACKEND_COMPOSE" exec -T db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < "$file"
    log "Restauración terminada."
}

load_tools() {
    require
    log "Ejecutando loader. Pasa el script y sus argumentos después de '--'."
    if [ "$#" -eq 0 ]; then
        fail "Uso: $0 load -- cargar_mysql.py [argumentos]"
    fi
    docker compose -f "$BACKEND_COMPOSE" --profile tools run --rm loader "$@"
}

case "${1:-up}" in
    up) up ;;
    down) down ;;
    destroy) destroy ;;
    restart) down; up ;;
    status) status ;;
    logs) shift || true; logs "$@" ;;
    health) health ;;
    db-dump) shift || true; db_dump "$@" ;;
    db-restore) shift || true; db_restore "$@" ;;
    load)
        shift || true
        if [ "${1:-}" = "--" ]; then shift; fi
        load_tools "$@"
        ;;
    *)
        echo "Uso: $0 {up|down|destroy|restart|status|logs [db|api|frontend]|health|db-dump [archivo]|db-restore archivo|load -- script args}"
        exit 1
        ;;
esac
