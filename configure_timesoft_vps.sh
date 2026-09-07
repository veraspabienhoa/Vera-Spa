#!/usr/bin/env bash
set -Eeuo pipefail

: "${TIMESOFT_USERNAME:?TIMESOFT_USERNAME is required}"
: "${TIMESOFT_PASSWORD:?TIMESOFT_PASSWORD is required}"
: "${VPS_USER:?VPS_USER is required}"
: "${VPS_HOST:?VPS_HOST is required}"

SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_ed25519}"
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT
umask 077

python - "$TMP_FILE" <<'PY'
import json
import os
import sys
from pathlib import Path
path = Path(sys.argv[1])
payload = {
    "username": os.environ["TIMESOFT_USERNAME"],
    "password": os.environ["TIMESOFT_PASSWORD"],
}
path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
path.chmod(0o600)
PY

scp -i "$SSH_KEY_PATH" "$TMP_FILE" "${VPS_USER}@${VPS_HOST}:/opt/vera-spa/timesoft-credentials.json.new"
ssh -i "$SSH_KEY_PATH" "${VPS_USER}@${VPS_HOST}" \
  'set -e; chmod 600 /opt/vera-spa/timesoft-credentials.json.new; mv -f /opt/vera-spa/timesoft-credentials.json.new /opt/vera-spa/timesoft-credentials.json; test "$(stat -c %a /opt/vera-spa/timesoft-credentials.json)" = 600'

echo "TIMESOFT CREDENTIAL FILE: installed privately on VPS"
