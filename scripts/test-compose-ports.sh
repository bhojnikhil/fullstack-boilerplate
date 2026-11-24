#!/usr/bin/env bash
set -euo pipefail

check_ports() {
    docker compose -f docker-compose.yml config --format json |
        jq -e --arg postgres "$1" --arg api "$2" '
            def bound($host_port; $container_port):
                length == 1 and .[0].host_ip == "127.0.0.1"
                    and .[0].published == $host_port and .[0].target == $container_port;
            (.services.postgres.ports | bound($postgres; 5432)) and
            (.services.api.ports | bound($api; 8000))
        ' >/dev/null
}

POSTGRES_PORT= API_PORT= check_ports 5432 8000
POSTGRES_PORT=25432 API_PORT=28000 check_ports 25432 28000

echo "Compose API and Postgres port mappings are loopback-only"
