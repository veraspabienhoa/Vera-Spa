#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: configure_vps_database.sh DB_HOST DB_PORT DB_NAME DB_USER" >&2
  exit 2
fi

db_host=$1
db_port=$2
db_name=$3
db_user=$4
IFS= read -r db_pass

if [[ -z "$db_pass" ]]; then
  echo "DATABASE CONFIG FAILED: empty database password" >&2
  exit 2
fi

pid=$(pgrep -o -f "vera_web_v2_api_v38:app" || true)
if [[ -z "$pid" ]]; then
  echo "DATABASE CONFIG FAILED: running Web V2 API process was not found" >&2
  exit 1
fi

unit=$(sed -n 's#.*system.slice/\([^/]*\.service\).*#\1#p' "/proc/$pid/cgroup" | head -n 1)
if [[ -z "$unit" ]]; then
  echo "DATABASE CONFIG FAILED: API systemd service was not found" >&2
  exit 1
fi

env_dir=/etc/vera-spa
env_path=$env_dir/database.env
dropin_dir=/etc/systemd/system/$unit.d
dropin_path=$dropin_dir/vera-database.conf
work_dir=$(mktemp -d)
had_env=0
had_dropin=0

cleanup() {
  rm -rf -- "$work_dir"
}

rollback() {
  local exit_code=$?
  trap - ERR
  echo "DATABASE CONFIG: validation failed; restoring previous API configuration" >&2
  if [[ "$had_env" == 1 ]]; then
    sudo -n install -o root -g root -m 600 "$work_dir/database.env.previous" "$env_path"
  else
    sudo -n rm -f -- "$env_path"
  fi
  if [[ "$had_dropin" == 1 ]]; then
    sudo -n install -o root -g root -m 644 "$work_dir/dropin.previous" "$dropin_path"
  else
    sudo -n rm -f -- "$dropin_path"
  fi
  sudo -n systemctl daemon-reload
  sudo -n systemctl restart "$unit"
  cleanup
  exit "$exit_code"
}

trap rollback ERR
trap cleanup EXIT

if sudo -n test -f "$env_path"; then
  sudo -n cat "$env_path" > "$work_dir/database.env.previous"
  had_env=1
fi
if sudo -n test -f "$dropin_path"; then
  sudo -n cat "$dropin_path" > "$work_dir/dropin.previous"
  had_dropin=1
fi

systemd_quote() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  printf '"%s"' "$value"
}

{
  printf 'VERA_DB_ENABLED=1\n'
  printf 'VERA_DATA_BACKEND=postgres\n'
  printf 'DB_HOST=%s\n' "$(systemd_quote "$db_host")"
  printf 'DB_PORT=%s\n' "$(systemd_quote "$db_port")"
  printf 'DB_NAME=%s\n' "$(systemd_quote "$db_name")"
  printf 'DB_USER=%s\n' "$(systemd_quote "$db_user")"
  printf 'DB_PASS=%s\n' "$(systemd_quote "$db_pass")"
  printf 'DB_SSLMODE=require\n'
  printf 'DB_CONNECT_TIMEOUT=10\n'
} > "$work_dir/database.env"

{
  printf '[Service]\n'
  printf 'EnvironmentFile=%s\n' "$env_path"
} > "$work_dir/vera-database.conf"

sudo -n install -d -o root -g root -m 700 "$env_dir"
sudo -n install -d -o root -g root -m 755 "$dropin_dir"
sudo -n install -o root -g root -m 600 "$work_dir/database.env" "$env_path"
sudo -n install -o root -g root -m 644 "$work_dir/vera-database.conf" "$dropin_path"
sudo -n systemctl daemon-reload
sudo -n systemctl restart "$unit"

for _ in {1..20}; do
  if sudo -n systemctl is-active --quiet "$unit"; then
    break
  fi
  sleep 1
done
sudo -n systemctl is-active --quiet "$unit"

checker=$(find /opt/vera-spa -maxdepth 4 -name vera_vps_data_check.py -type f -print -quit)
test -n "$checker"
/opt/vera-spa/.venv/bin/python "$checker"

trap - ERR
echo "DATABASE CONFIG: PostgreSQL SSL configuration applied to $unit"
