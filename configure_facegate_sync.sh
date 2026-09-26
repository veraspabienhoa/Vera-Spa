#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Production deploy and API run as the same unprivileged account. Install only
# that account's cron entry; do not require sudo or modify system services.
stage=preflight
work_dir=''
cleanup() { if [[ -n "$work_dir" ]]; then rm -rf -- "$work_dir"; fi; }
trap cleanup EXIT
trap 'printf "FACEGATE SCHEDULE FAILED: stage=%s. See the preceding diagnostic.\n" "$stage" >&2' ERR
fail() { printf 'FACEGATE SCHEDULE FAILED: %s\n' "$1" >&2; exit 1; }

base_dir=/opt/vera-spa
test -x "$base_dir/.venv/bin/python" || fail 'VPS Python is unavailable.'
test -f "$base_dir/current/vera_facegate_auto_sync.py" || fail 'FaceGate worker is missing from the deployed release.'
test -w "$base_dir" || fail 'Deployment account cannot write the archive lock/status directory.'
for file in .facegate-sync.lock .facegate-sync-last.log; do
  if [[ -e "$base_dir/$file" || -L "$base_dir/$file" ]]; then
    [[ -f "$base_dir/$file" && ! -L "$base_dir/$file" && -w "$base_dir/$file" ]] || fail 'Archive lock/status file is not writable by the deployment account.'
  fi
done
pid=$(pgrep -n -f '[v]era_web_v2_api_v38:app') || fail 'Running VERA API was not found.'
test "$(stat -c '%u' "/proc/$pid")" = "$(id -u)" || fail 'Run as the same account that owns the VERA API.'

# Keep a previously installed and active timer; never install a second scheduler.
if systemctl is-active --quiet vera-facegate-sync.timer 2>/dev/null; then
  printf '%s\n' 'FACEGATE SCHEDULE: existing timer active; attendance source unchanged.'
  exit 0
fi
command -v crontab >/dev/null || fail 'crontab is not installed on the VPS.'
command -v flock >/dev/null || fail 'flock is not installed on the VPS.'
if ! systemctl is-active --quiet cron.service 2>/dev/null && ! systemctl is-active --quiet crond.service 2>/dev/null; then
  fail 'The VPS cron service is not active; no cron entries were changed.'
fi

work_dir=$(mktemp -d)
exec 9>"$base_dir/.facegate-cron-install.lock"
flock -w 10 9 || fail 'Another schedule installer is running.'

read_cron() {
  local destination=$1 status=0
  LC_ALL=C crontab -l >"$destination" 2>"$work_dir/error" || status=$?
  if (( status != 0 )); then
    if (( status == 1 )) && grep -q '^no crontab for ' "$work_dir/error"; then
      : >"$destination"
    else
      fail 'Cannot read this account crontab; existing schedules were not replaced.'
    fi
  fi
}

stage=read_existing_schedule
read_cron "$work_dir/original"
marker='# VERA_FACEGATE_ARCHIVE_V1'
entry='* * * * * umask 077; cd /opt/vera-spa/current && /opt/vera-spa/.venv/bin/python vera_facegate_auto_sync.py > /opt/vera-spa/.facegate-sync-last.log 2>&1 # VERA_FACEGATE_ARCHIVE_V1'
# Preserve unrelated jobs and environment entries exactly. The worker's own
# nonblocking file lock also excludes the existing hourly GitHub fallback.
awk -v marker="$marker" 'length($0) < length(marker) || substr($0,length($0)-length(marker)+1) != marker {print}' "$work_dir/original" >"$work_dir/next"
printf '%s\n' "$entry" >>"$work_dir/next"
read_cron "$work_dir/recheck"
cmp -s "$work_dir/original" "$work_dir/recheck" || fail 'Crontab changed during preparation; retry without overwriting the newer schedule.'
stage=install_user_cron
if ! cmp -s "$work_dir/original" "$work_dir/next"; then
  crontab "$work_dir/next" 2>"$work_dir/error" || fail 'This account is not allowed to install a crontab; no privilege changes were attempted.'
fi
stage=verify_user_cron
read_cron "$work_dir/installed"
test "$(grep -Fxc -- "$entry" "$work_dir/installed")" = 1 || fail 'The installed FaceGate schedule could not be verified.'
printf '%s\n' 'FACEGATE SCHEDULE: user cron verified, every minute; attendance source unchanged.'
