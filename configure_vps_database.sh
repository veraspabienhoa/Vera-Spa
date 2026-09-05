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
api_marker='vera_web_v2_api_v38:app'
api_pattern='[v]era_web_v2_api_v38:app'
validation_stage=initialization

test "$(git -C "$script_dir" rev-parse HEAD)" = "$deploy_sha"

if [[ -z "$db_pass" ]]; then
  echo "DATABASE CONFIG FAILED: empty database password" >&2
  exit 2
fi

pid=$(pgrep -n -f "$api_pattern" || true)
if [[ -z "$pid" ]]; then
  echo "DATABASE CONFIG FAILED: running Web V2 API process was not found" >&2
  exit 1
fi
system_unit=$(sed -n 's#.*system\.slice/\([^/]*\.service\).*#\1#p' "/proc/$pid/cgroup" | head -n 1)
user_unit=""
if [[ -z "$system_unit" ]]; then
  user_unit=$(awk -F/ '{ for (i=NF; i>=1; i--) if ($i ~ /\.service$/ && $i !~ /^user@/) { print $i; exit } }' "/proc/$pid/cgroup")
fi
service_unit=${system_unit:-$user_unit}
if [[ -n "$service_unit" && ! "$service_unit" =~ ^[A-Za-z0-9_.@:-]+\.service$ ]]; then
  echo "DATABASE CONFIG FAILED: unsafe API systemd unit name" >&2
  exit 1
fi
if [[ -n "$system_unit" ]]; then
  service_scope=system
  service_ctl=(systemctl)
elif [[ -n "$user_unit" ]]; then
  service_scope=user
  service_ctl=(systemctl --user)
else
  service_scope=process
  service_ctl=()
fi
echo "DATABASE CONFIG: API runtime scope=$service_scope unit=${service_unit:-none}"
protect_home=""
environment_files=""
if [[ -n "$service_unit" ]]; then
  if environment_files=$("${service_ctl[@]}" show "$service_unit" --property=EnvironmentFiles --value 2>/dev/null); then
    echo "DATABASE CONFIG: API EnvironmentFiles=${environment_files:-none}"
  else
    echo "DATABASE CONFIG: API EnvironmentFiles=unavailable"
  fi
  service_user=$("${service_ctl[@]}" show "$service_unit" --property=User --value 2>/dev/null || true)
  protect_home=$("${service_ctl[@]}" show "$service_unit" --property=ProtectHome --value 2>/dev/null || true)
  echo "DATABASE CONFIG: API unit user=${service_user:-default} protect_home=${protect_home:-unknown}"
fi
deploy_uid=$(id -u)
api_uid=$(stat -c '%u' "/proc/$pid" 2>/dev/null || true)
if [[ -z "$api_uid" || "$api_uid" != "$deploy_uid" ]]; then
  echo "DATABASE CONFIG FAILED: API and deployment account ownership do not match" >&2
  exit 1
fi
if [[ "$service_scope" == system && "$protect_home" =~ ^(yes|true|tmpfs)$ ]]; then
  echo "DATABASE CONFIG FAILED: API system service cannot read its private home configuration" >&2
  exit 1
fi

runtime_home=$(getent passwd "$(id -u)" | awk -F: 'NR == 1 { print $6 }')
if [[ -z "$runtime_home" || "$runtime_home" != /* ]]; then
  echo "DATABASE CONFIG FAILED: could not resolve the deployment account home" >&2
  exit 1
fi
environment_dir=$runtime_home/.config/vera-spa
environment_path=$environment_dir/web-v2-api.env
staged_environment_path=$environment_dir/.web-v2-api.env.$$
auth_marker_path=$environment_dir/web-v2-local-auth.enabled
staged_auth_marker_path=$environment_dir/.web-v2-local-auth.enabled.$$
work_dir=$(mktemp -d)
had_environment_file=0
had_auth_marker=0
configuration_changed=none
restart_attempted=0

cleanup() {
  rm -f -- "$staged_environment_path" "$staged_auth_marker_path"
  rm -rf -- "$work_dir"
}

install_environment_file() {
  install -m 600 "$1" "$staged_environment_path"
  mv -f -- "$staged_environment_path" "$environment_path"
}

install_auth_marker() {
  install -m 600 "$1" "$staged_auth_marker_path"
  mv -f -- "$staged_auth_marker_path" "$auth_marker_path"
}

rollback() {
  local exit_code=$?
  local rollback_failed=0
  local rollback_ready=0
  if [[ "$exit_code" == 0 ]]; then
    exit_code=1
  fi
  trap - ERR HUP INT TERM
  echo "DATABASE CONFIG: validation failed at stage=$validation_stage; restoring previous API environment" >&2
  if [[ "$configuration_changed" == marker ]]; then
    if [[ "$had_auth_marker" == 1 ]]; then
      if ! install_auth_marker "$work_dir/auth-marker.previous"; then
        echo "DATABASE CONFIG ROLLBACK FAILED: could not restore local Auth marker" >&2
        rollback_failed=1
      fi
    elif ! rm -f -- "$auth_marker_path"; then
      echo "DATABASE CONFIG ROLLBACK FAILED: could not remove local Auth marker" >&2
      rollback_failed=1
    fi
    if [[ "$had_environment_file" == 1 ]]; then
      if ! install_environment_file "$work_dir/environment.previous"; then
        echo "DATABASE CONFIG ROLLBACK FAILED: could not restore private fallback environment" >&2
        rollback_failed=1
      fi
    elif ! rm -f -- "$environment_path"; then
      echo "DATABASE CONFIG ROLLBACK FAILED: could not remove private fallback environment" >&2
      rollback_failed=1
    fi
  fi
  if [[ "$restart_attempted" == 1 ]]; then
    if ! /opt/vera-spa/deploy.sh "$deploy_sha"; then
      echo "DATABASE CONFIG ROLLBACK FAILED: API restart did not complete" >&2
      rollback_failed=1
    else
      for _ in {1..15}; do
        if curl --fail --silent --connect-timeout 2 --max-time 5 \
          http://127.0.0.1:8000/v2/auth/health >/dev/null 2>&1; then
          rollback_ready=1
          break
        fi
        sleep 2
      done
      if [[ "$rollback_ready" == 0 ]]; then
        echo "DATABASE CONFIG ROLLBACK FAILED: restored API did not become healthy" >&2
        rollback_failed=1
      fi
    fi
  fi
  cleanup
  if [[ "$rollback_failed" == 1 ]]; then
    echo "DATABASE CONFIG ROLLBACK FAILED: manual recovery is required" >&2
  fi
  exit "$exit_code"
}

trap rollback ERR HUP INT TERM
trap cleanup EXIT

mkdir -p -- "$environment_dir"
chmod 700 "$environment_dir"
if [[ -e "$environment_path" || -L "$environment_path" ]]; then
  if [[ ! -f "$environment_path" || -L "$environment_path" ]]; then
    echo "DATABASE CONFIG FAILED: unsafe private fallback environment path" >&2
    exit 1
  fi
  cp -- "$environment_path" "$work_dir/environment.previous"
  had_environment_file=1
fi
if [[ -e "$auth_marker_path" || -L "$auth_marker_path" ]]; then
  if [[ ! -f "$auth_marker_path" || -L "$auth_marker_path" ]]; then
    echo "DATABASE CONFIG FAILED: unsafe local Auth marker path" >&2
    exit 1
  fi
  auth_marker_uid=$(stat -c '%u' "$auth_marker_path" 2>/dev/null || true)
  auth_marker_mode=$(stat -c '%a' "$auth_marker_path" 2>/dev/null || true)
  if [[ "$auth_marker_uid" != "$deploy_uid" \
    || "$auth_marker_mode" != 600 \
    || ! -r "$auth_marker_path" ]] \
    || ! cmp -s -- "$auth_marker_path" <(printf 'postgres-local-v1\n'); then
    echo "DATABASE CONFIG FAILED: existing local Auth marker is invalid" >&2
    exit 1
  fi
  cp -- "$auth_marker_path" "$work_dir/auth-marker.previous"
  had_auth_marker=1
fi

# Phase 1: prove the existing PostgreSQL runtime store supports Auth CRUD before
# the API is switched away from Supabase Auth. A failure here leaves
# the currently running provider untouched and triggers the rollback handler.
validation_stage=preflight
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

# The local Auth probe and the live API must target the same database.  The
# service may intentionally use a different, more privileged database role, so
# compare endpoint identity only and never print credentials or values.
declare -A api_database_environment=()
api_provider_present=0
while IFS= read -r -d '' entry; do
  key=${entry%%=*}
  case "$key" in
    DB_HOST|DB_PORT|DB_NAME)
      api_database_environment["$key"]=${entry#*=}
      ;;
    VERA_AUTH_PROVIDER)
      api_provider_present=1
      api_provider_value=${entry#*=}
      ;;
  esac
done < "/proc/$pid/environ"
api_database_mismatches=()
[[ "${api_database_environment[DB_HOST]:-}" == "$db_host" ]] || api_database_mismatches+=(DB_HOST)
[[ "${api_database_environment[DB_PORT]:-5432}" == "$db_port" ]] || api_database_mismatches+=(DB_PORT)
[[ "${api_database_environment[DB_NAME]:-postgres}" == "$db_name" ]] || api_database_mismatches+=(DB_NAME)
if (( ${#api_database_mismatches[@]} > 0 )); then
  echo "DATABASE CONFIG FAILED: live API database endpoint mismatch: ${api_database_mismatches[*]}" >&2
  false
fi
echo "DATABASE CONFIG: live API database endpoint matches the verified target"
if [[ "$api_provider_present" == 1 ]]; then
  api_provider_normalized=${api_provider_value,,}
  if [[ ! "$api_provider_normalized" =~ ^[[:space:]]*(local|postgres|postgresql|vps)[[:space:]]*$ ]]; then
    echo "DATABASE CONFIG FAILED: explicit API Auth provider policy does not permit marker cutover" >&2
    false
  fi
  echo "DATABASE CONFIG: explicit API Auth provider already permits local Auth"
else
  echo "DATABASE CONFIG: API Auth provider is eligible for secure marker cutover"
fi

# The production system EnvironmentFile is root-managed.  Activate only Auth
# through a strict, non-secret marker owned by the API/deployment account; keep
# the service's already-working database credentials unchanged.  Removing the
# earlier full environment fallback also avoids changing unrelated data modes.
validation_stage=cutover
printf 'postgres-local-v1\n' > "$work_dir/web-v2-local-auth.enabled"
configuration_changed=marker
rm -f -- "$environment_path"
install_auth_marker "$work_dir/web-v2-local-auth.enabled"
echo "DATABASE CONFIG: secure PostgreSQL local Auth marker installed"

validation_stage=prestart
(
  trap - ERR
  unset VERA_AUTH_PROVIDER
  cd -- "$script_dir"
  timeout 45 /opt/vera-spa/.venv/bin/python - <<'PY'
import sys

try:
    from vera_web_v2_runtime_env import load_managed_runtime_environment
    from vera_web_v2_local_auth import local_auth_enabled
    loaded = load_managed_runtime_environment()
except Exception as exc:
    print(f"RUNTIME PRESTART FAILED: {type(exc).__name__}", file=sys.stderr)
    raise SystemExit(1)

if loaded:
    raise SystemExit("RUNTIME PRESTART FAILED: stale private database environment was loaded")
if not local_auth_enabled():
    raise SystemExit("RUNTIME PRESTART FAILED: secure local Auth marker is not active")
print("RUNTIME PRESTART: secure PostgreSQL local Auth marker verified")
PY
)

validation_stage=restart
restart_attempted=1
/opt/vera-spa/deploy.sh "$deploy_sha"
echo "DATABASE CONFIG: deploy completed; waiting for local Auth health"

# Phase 2: the API keeps its existing database settings and reads the non-secret
# provider marker. Verify the exact release and its live Auth endpoint.
validation_stage=health
test "$(git -C "$script_dir" rev-parse HEAD)" = "$deploy_sha"
new_pid=""
health_payload=$work_dir/auth-health.json
for _ in {1..30}; do
  while IFS= read -r candidate_pid; do
    [[ "$candidate_pid" =~ ^[1-9][0-9]*$ ]] || continue
    [[ -r "/proc/$candidate_pid/cmdline" ]] || continue
    candidate_command=$(tr '\0' ' ' < "/proc/$candidate_pid/cmdline" 2>/dev/null || true)
    [[ "$candidate_command" == *"$api_marker"* ]] || continue
    candidate_release_dir=$(readlink -f "/proc/$candidate_pid/cwd" 2>/dev/null || true)
    [[ -n "$candidate_release_dir" ]] || continue
    candidate_release_sha=$(git -C "$candidate_release_dir" rev-parse HEAD 2>/dev/null || true)
    [[ "$candidate_release_sha" == "$deploy_sha" ]] || continue
    if curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
      http://127.0.0.1:8000/v2/auth/health > "$health_payload" 2>/dev/null \
      && /opt/vera-spa/.venv/bin/python - "$health_payload" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
if payload.get("ok") is not True or payload.get("provider") != "postgres-local":
    raise SystemExit(1)
PY
    then
      new_pid=$candidate_pid
      break 2
    fi
  done < <(pgrep -f "$api_pattern" || true)
  sleep 2
done
if [[ -z "$new_pid" ]]; then
  if [[ -n "$service_unit" ]]; then
    active_state=$("${service_ctl[@]}" show "$service_unit" --property=ActiveState --value 2>/dev/null || true)
    sub_state=$("${service_ctl[@]}" show "$service_unit" --property=SubState --value 2>/dev/null || true)
    main_pid=$("${service_ctl[@]}" show "$service_unit" --property=MainPID --value 2>/dev/null || true)
    echo "DATABASE CONFIG: API unit state=${active_state:-unknown}/${sub_state:-unknown} main_pid=${main_pid:-unknown}" >&2
  fi
  echo "DATABASE CONFIG FAILED: requested release did not report PostgreSQL local Auth healthy" >&2
  false
fi
echo "DATABASE CONFIG: PostgreSQL local Auth health verified"

validation_stage=postflight
/opt/vera-spa/.venv/bin/python "$local_auth_migrator"

test -f "$data_checker"
/opt/vera-spa/.venv/bin/python "$data_checker"

trap - ERR HUP INT TERM
echo "DATABASE CONFIG: PostgreSQL SSL and local Auth cutover applied and verified"
