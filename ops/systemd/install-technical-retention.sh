#!/usr/bin/env bash
set -euo pipefail
retention_ops=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ "$EUID" -ne 0 ]]; then
  exec sudo -n /bin/bash "$retention_ops/install-technical-retention.sh"
fi
install -m 0644 "$retention_ops/vera-technical-retention.service" /etc/systemd/system/vera-technical-retention.service
install -m 0644 "$retention_ops/vera-technical-retention.timer" /etc/systemd/system/vera-technical-retention.timer
systemctl daemon-reload
systemctl enable --now vera-technical-retention.timer
systemctl start vera-technical-retention.service
systemctl is-enabled vera-technical-retention.timer
systemctl is-active vera-technical-retention.timer
systemctl show vera-technical-retention.service -p Result -p ExecMainStatus
systemctl list-timers vera-technical-retention.timer --no-pager
