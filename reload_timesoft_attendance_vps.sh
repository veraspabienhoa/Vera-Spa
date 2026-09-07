#!/usr/bin/env bash
set -euo pipefail

pid="$(pgrep -n -f '[v]era_web_v2_api_v38:app')"
release_dir="$(readlink -f "/proc/${pid}/cwd")"
python_bin="/opt/vera-spa/.venv/bin/python"

test -f "${release_dir}/reload_timesoft_attendance_dates.py"

"${python_bin}" - "${pid}" "${release_dir}" <<'PY'
import os
import sys

pid = sys.argv[1]
release_dir = sys.argv[2]
with open(f"/proc/{pid}/environ", "rb") as fh:
    items = fh.read().split(b"\0")
env = {}
for item in items:
    if b"=" not in item:
        continue
    key, value = item.split(b"=", 1)
    env[key.decode("utf-8", "ignore")] = value.decode("utf-8", "ignore")
env["TIMESOFT_SYNC_DAYS"] = "2"
os.chdir(release_dir)
python_bin = "/opt/vera-spa/.venv/bin/python"
os.execve(python_bin, [python_bin, "reload_timesoft_attendance_dates.py"], env)
PY
