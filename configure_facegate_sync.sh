#!/usr/bin/env bash
set -euo pipefail
# Run from the exact deployed release, after runtime/schema checks. No secrets
# or employee records are copied into the systemd unit or its journal.
test "$(id -u)" = 0
test -x /opt/vera-spa/.venv/bin/python
test -f /opt/vera-spa/current/vera_facegate_auto_sync.py
cat > /etc/systemd/system/vera-facegate-sync.service <<'UNIT'
[Unit]
Description=VERA FaceGate evidence archive
After=network-online.target vera-api.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/vera-spa/current
ExecStart=/opt/vera-spa/.venv/bin/python vera_facegate_auto_sync.py
TimeoutStartSec=440
UMask=0077
Nice=10
UNIT
cat > /etc/systemd/system/vera-facegate-sync.timer <<'UNIT'
[Unit]
Description=Archive FaceGate evidence after each completed sync

[Timer]
OnBootSec=45s
OnUnitInactiveSec=60s
AccuracySec=5s
Unit=vera-facegate-sync.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now vera-facegate-sync.timer
systemctl is-active --quiet vera-facegate-sync.timer
printf '%s\n' 'FaceGate archive timer active; attendance source unchanged.'
