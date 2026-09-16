#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/vera-spa/backend.env"
if [[ ! -r "$ENV_FILE" ]]; then
  echo "watchdog environment file is not readable" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a

SECRET="${VERA_V2_PUSH_WEBHOOK_SECRET:-}"
if [[ -z "$SECRET" ]]; then
  echo "watchdog secret is missing" >&2
  exit 1
fi

RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$RESPONSE_FILE"' EXIT

HTTP_CODE="$(curl -sS --connect-timeout 3 --max-time 30 \
  -o "$RESPONSE_FILE" -w '%{http_code}' \
  -X POST \
  -H 'Content-Type: application/json' \
  -H "x-vera-push-webhook: ${SECRET}" \
  --data '{}' \
  http://127.0.0.1:8000/v2/live-tour/projection-queue/watchdog)"

cat "$RESPONSE_FILE"
printf '\n'

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "watchdog endpoint returned HTTP ${HTTP_CODE}" >&2
  exit 1
fi
