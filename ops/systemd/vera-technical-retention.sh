#!/usr/bin/env bash
set -euo pipefail

# Follow the running release, including after rollback; never use a stale checkout.
retention_pid=$(pgrep -n -f '[v]era_web_v2_api_v38:app') || exit 0
retention_release=$(readlink -f "/proc/${retention_pid}/cwd")
test -n "$retention_release"
cd "$retention_release"
# An older release cannot honor the interval. Do not fall back to ungated cleanup.
if ! /opt/vera-spa/.venv/bin/python vera_technical_retention.py --help | grep -q -- '--scheduled'; then
  echo '{"skipped":"deployed_release_has_no_cleanup_schedule"}'
  exit 0
fi
exec timeout 30 /opt/vera-spa/.venv/bin/python vera_technical_retention.py --apply --scheduled
