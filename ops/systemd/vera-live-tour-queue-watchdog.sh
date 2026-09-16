#!/usr/bin/env bash
set -euo pipefail

SECRET="$(runuser -u postgres -- psql -d veraspa -Atqc "SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='vera_v2_push_webhook_secret' LIMIT 1;")"
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
