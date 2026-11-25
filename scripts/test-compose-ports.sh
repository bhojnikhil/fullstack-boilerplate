#!/usr/bin/env bash
set -euo pipefail

check_ports() {
    docker compose -f docker-compose.yml config --format json |
        jq -e --arg postgres "$1" --arg api "$2" --arg web "$3" --arg ui "$4" --arg smtp "$5" '
            def bound($host_port; $container_port):
                .host_ip == "127.0.0.1"
                    and .published == $host_port and .target == $container_port;
            (.services.postgres.ports | length == 1 and (.[0] | bound($postgres; 5432))) and
            (.services.api.ports | length == 1 and (.[0] | bound($api; 8000))) and
            (.services.web.ports | length == 1 and (.[0] | bound($web; 3000))) and
            (.services.mailpit.ports | length == 2
                and (.[0] | bound($ui; 8025)) and (.[1] | bound($smtp; 1025)))
        ' >/dev/null
}

POSTGRES_PORT= API_PORT= WEB_PORT= MAILPIT_UI_PORT= MAILPIT_SMTP_PORT= \
    check_ports 5432 8000 3000 8025 1025
POSTGRES_PORT=25432 API_PORT=28000 WEB_PORT=23000 MAILPIT_UI_PORT=28025 MAILPIT_SMTP_PORT=21025 \
    check_ports 25432 28000 23000 28025 21025

echo "Compose API, web, Postgres and Mailpit port mappings are loopback-only"
