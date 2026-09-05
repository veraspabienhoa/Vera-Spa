#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 5 ]]; then
  echo "Usage: configure_vps_database.sh DEPLOY_SHA DB_HOST DB_PORT DB_NAME DB_USER" >&2
  exit 2
fi

deploy_sha=$1
db_host=$2
db_port=$3
db_name=$4
db_user=$5
IFS= read -r db_pass
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
local_auth_migrator=$script_dir/vera_web_v2_local_auth.py
data_checker=$script_dir/vera_vps_data_check.py

test "$(git -C "$script_dir" rev-parse HEAD)" = "$deploy_sha"

if [[ -z "$db_pass" ]]; then
  echo "DATABASE CONFIG FAILED: empty database password" >&2
  exit 2
fi

pid=$(pgrep -n -f "vera_web_v2_api_v38:app" || true)
if [[ -z "$pid" ]]; then
  echo "DATABASE CONFIG FAILED: running Web V2 API process was not found" >&2
  exit 1
fi

readonly -a db_keys=(
  VERA_DB_ENABLED VERA_DATA_BACKEND DB_HOST DB_PORT DB_NAME DB_USER DB_PASS
  DB_SSLMODE DB_CONNECT_TIMEOUT VERA_AUTH_PROVIDER
)
declare -A previous_values=()
declare -A previous_present=()

while IFS= read -r -d '' entry; do
  key=${entry%%=*}
  for wanted in "${db_keys[@]}"; do
    if [[ "$key" == "$wanted" ]]; then
      previous_values["$key"]=${entry#*=}
      previous_present["$key"]=1
      break
    fi
  done
done < "/proc/$pid/environ"

environment_dir=$HOME/.config/environment.d
environment_path=$environment_dir/50-vera-database.conf
work_dir=$(mktemp -d)
had_environment_file=0

cleanup() {
  rm -rf -- "$work_dir"
}

restore_previous_exports() {
  local key
  for key in "${db_keys[@]}"; do
    if [[ "${previous_present[$key]:-0}" == 1 ]]; then
      printf -v "$key" '%s' "${previous_values[$key]}"
      export "$key"
    else
      unset "$key"
    fi
  done
}

rollback() {
  local exit_code=$?
  if [[ "$exit_code" == 0 ]]; then
    exit_code=1
  fi
  trap - ERR HUP INT TERM
  echo "DATABASE CONFIG: validation failed; restoring previous API environment" >&2
  if [[ "$had_environment_file" == 1 ]]; then
    install -m 600 "$work_dir/environment.previous" "$environment_path"
  else
    rm -f -- "$environment_path"
  fi
  restore_previous_exports
  systemctl --user unset-environment "${db_keys[@]}" >/dev/null 2>&1 || true
  systemctl --user import-environment "${db_keys[@]}" >/dev/null 2>&1 || true
  /opt/vera-spa/deploy.sh "$deploy_sha" || true
  cleanup
  exit "$exit_code"
}

trap rollback ERR HUP INT TERM
trap cleanup EXIT

mkdir -p -- "$environment_dir"
chmod 700 "$environment_dir"
if [[ -f "$environment_path" ]]; then
  cp -- "$environment_path" "$work_dir/environment.previous"
  had_environment_file=1
fi

systemd_quote() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  printf '"%s"' "$value"
}

# Phase 1: prove the existing PostgreSQL runtime store supports Auth CRUD before
# the service manager is switched away from Supabase Auth. A failure here leaves
# the currently running provider untouched and triggers the rollback handler.
test -f "$local_auth_migrator"
export VERA_DB_ENABLED=1
export VERA_DATA_BACKEND=postgres
export DB_HOST="$db_host"
export DB_PORT="$db_port"
export DB_NAME="$db_name"
export DB_USER="$db_user"
export DB_PASS="$db_pass"
export DB_SSLMODE=require
export DB_CONNECT_TIMEOUT=10
/opt/vera-spa/.venv/bin/python "$local_auth_migrator"

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
  printf 'VERA_AUTH_PROVIDER=local\n'
} > "$work_dir/50-vera-database.conf"
install -m 600 "$work_dir/50-vera-database.conf" "$environment_path"

export VERA_AUTH_PROVIDER=local
systemctl --user import-environment "${db_keys[@]}" >/dev/null 2>&1 || true

/opt/vera-spa/deploy.sh "$deploy_sha"

# Phase 2: verify the restarted API inherited the cutover flag, then recheck
# the Auth store through the exact code shipped in this release.
test "$(git -C "$script_dir" rev-parse HEAD)" = "$deploy_sha"
new_pid=$(pgrep -n -f "vera_web_v2_api_v38:app" || true)
test -n "$new_pid"
declare -A new_environment=()
while IFS= read -r -d '' entry; do
  key=${entry%%=*}
  new_environment["$key"]=${entry#*=}
done < "/proc/$new_pid/environ"
[[ "${new_environment[DB_HOST]:-}" == "$db_host" ]]
[[ "${new_environment[DB_PORT]:-}" == "$db_port" ]]
[[ "${new_environment[DB_NAME]:-}" == "$db_name" ]]
[[ "${new_environment[DB_USER]:-}" == "$db_user" ]]
[[ "${new_environment[DB_PASS]:-}" == "$db_pass" ]]
[[ "${new_environment[DB_SSLMODE]:-}" == "require" ]]
[[ "${new_environment[VERA_AUTH_PROVIDER]:-}" == "local" ]]
/opt/vera-spa/.venv/bin/python "$local_auth_migrator"

test -f "$data_checker"
/opt/vera-spa/.venv/bin/python "$data_checker"

trap - ERR HUP INT TERM
echo "DATABASE CONFIG: PostgreSQL SSL and local Auth environment applied and verified"
