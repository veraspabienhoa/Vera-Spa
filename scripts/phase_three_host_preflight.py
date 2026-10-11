"""Fixed read-only host inventory. Executed in memory, never imports the app.

Only allowlisted flags/counts leave this process. A stable observation is not a
maintenance lock, proof of session affinity, or permission to activate anything.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import shlex
import signal
import stat
import subprocess
import time

BASE = Path('/opt/vera-spa')
# The application release was reviewed separately from this diagnostic-only PR.
AUDITED_RELEASE_SHA = '02ef3641edf1dfaf12ab048c725df03c4397af3e'
MAX_FILE = 65536
MAX_COMMAND = 131072
MAX_PROCESSES = 4096
PROCESS_MARKERS = {
    'api': 'vera_web_v2_api_v38:app',
    'worker': 'vera_web_v2_worker:app',
    'facegate': 'vera_facegate_auto_sync.py',
    'timesoft': 'timesoft_sync_job.py',
    'daily_ops': 'vera_daily_ops_job.py',
    'retention': 'vera_technical_retention.py',
    'storage_maintenance': 'vera_live_tour_maintenance.py',
    'number_maintenance': 'vera_live_tour_bill_numbers.py',
}
NUMERIC_KEYS = {
    'DB_POOL_SIZE', 'DB_MAX_OVERFLOW', 'DB_POOL_TIMEOUT', 'DB_POOL_RECYCLE',
    'DB_CONNECT_TIMEOUT', 'DB_BACKGROUND_POOL_SIZE', 'DB_BACKGROUND_MAX_OVERFLOW',
    'DB_AUTH_POOL_SIZE', 'DB_AUTH_POOL_TIMEOUT', 'DB_STATEMENT_TIMEOUT_MS',
    'DB_LOCK_TIMEOUT_MS', 'DB_IDLE_IN_TRANSACTION_TIMEOUT_MS',
    'DB_CONNECTION_BUDGET', 'DB_API_POOL_INSTANCES', 'DB_BACKGROUND_POOL_INSTANCES',
    'DB_DEDICATED_CONNECTIONS', 'DB_EXTERNAL_CONNECTION_RESERVE',
}
BUDGET_KEYS = {
    'DB_CONNECTION_BUDGET', 'DB_API_POOL_INSTANCES', 'DB_BACKGROUND_POOL_INSTANCES',
    'DB_DEDICATED_CONNECTIONS', 'DB_EXTERNAL_CONNECTION_RESERVE',
}
DB_KEYS = {'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASS', 'DB_SSLMODE'}
MODE_VALUES = {
    'VERA_SERVICE_ROLE': {'combined', 'api', 'worker'},
    'VERA_WORKER_DB_MODE': {'unknown', 'direct', 'session', 'transaction'},
    'VERA_LIVE_TOUR_RELATIONAL_MODE': {'off', 'shadow', 'verify', 'active'},
}
ENV_KEYS = NUMERIC_KEYS | DB_KEYS | set(MODE_VALUES) | {
    'VERA_DB_ENABLED', 'VERA_DATA_BACKEND', 'VERA_AUTH_PROVIDER',
}
FIXED_UNITS = {
    'api': 'vera-api.service', 'worker': 'vera-worker.service',
    'facegate_timer': 'vera-facegate-sync.timer',
    'retention_timer': 'vera-technical-retention.timer',
    'watchdog_timer': 'vera-live-tour-queue-watchdog.timer',
    'cron': 'cron.service', 'crond': 'crond.service',
}


class Unavailable(Exception):
    """Intentionally has no untrusted error body."""


class Deadline(BaseException):
    """Bypass best-effort catches while still cleaning up child processes."""


def deadline_expired(_signal, _frame):
    raise Deadline()


def read_bytes(path, maximum=MAX_FILE, *, private=False):
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Unavailable()
        if private and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise Unavailable()
        chunks = []
        size = 0
        while size <= maximum:
            chunk = os.read(fd, min(16384, maximum + 1 - size))
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)
            size += len(chunk)
        raise Unavailable()
    finally:
        os.close(fd)


def command(argv, timeout=3, maximum=MAX_COMMAND):
    """Bound memory/time; discard stderr, never invoke a shell or print output."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, start_new_session=True,
                               env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'})
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Unavailable()
                for key, _ in selector.select(min(remaining, 0.2)):
                    chunk = os.read(key.fd, min(16384, maximum + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fd)
                        continue
                    output.extend(chunk)
                    if len(output) > maximum:
                        raise Unavailable()
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        return code, bytes(output).decode('utf-8', 'strict')
    except Exception:
        raise Unavailable() from None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        process.stdout.close()


def revision(path):
    code, output = command(['git', '-c', 'core.fsmonitor=false', '-C', str(path), 'rev-parse', 'HEAD'])
    if code != 0 or not re.fullmatch(r'[0-9a-f]{40}\n?', output):
        raise Unavailable()
    return output.strip()


def parse_environment(content):
    result = {}
    for line in content.decode('utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, raw = line.partition('=')
        key = key.strip()
        if not separator or key not in ENV_KEYS:
            continue
        if key in result:
            raise Unavailable()
        parser = shlex.shlex(raw.strip(), posix=True)
        parser.whitespace_split = True
        parser.commenters = ''
        parts = list(parser)
        if len(parts) != 1 or any(c in parts[0] for c in ('\0', '\r', '\n')):
            raise Unavailable()
        result[key] = parts[0]
    return result


def managed_configuration(home):
    result = {'available': False, 'valid': False, 'mode_override': False}
    env, fingerprints = {}, []
    runtime = home / '.config/vera-spa/web-v2-api.env'
    mode = home / '.config/vera-spa/live-tour-storage.env'
    try:
        data = read_bytes(runtime, private=True)
    except FileNotFoundError:
        pass
    else:
        result['available'] = True
        parsed = parse_environment(data)
        required = DB_KEYS | {'DB_CONNECT_TIMEOUT', 'VERA_DB_ENABLED', 'VERA_DATA_BACKEND', 'VERA_AUTH_PROVIDER'}
        if not required <= parsed.keys():
            raise Unavailable()
        if (parsed['VERA_DB_ENABLED'].lower() != '1' or parsed['VERA_DATA_BACKEND'].lower() != 'postgres'
                or parsed['VERA_AUTH_PROVIDER'].lower() != 'local' or parsed['DB_SSLMODE'].lower() != 'require'):
            raise Unavailable()
        env.update(parsed)
        fingerprints.append((str(runtime), hashlib.sha256(data).hexdigest(), runtime.stat().st_mtime_ns))
        result['valid'] = True
    try:
        data = read_bytes(mode, private=True)
    except FileNotFoundError:
        pass
    else:
        lines = [line.strip() for line in data.decode('utf-8').splitlines() if line.strip() and not line.lstrip().startswith('#')]
        if len(lines) != 1 or lines[0].partition('=')[0].strip() != 'VERA_LIVE_TOUR_RELATIONAL_MODE':
            raise Unavailable()
        parsed = parse_environment(data)
        if parsed.get('VERA_LIVE_TOUR_RELATIONAL_MODE') not in MODE_VALUES['VERA_LIVE_TOUR_RELATIONAL_MODE']:
            raise Unavailable()
        env.update(parsed)
        fingerprints.append((str(mode), hashlib.sha256(data).hexdigest(), mode.stat().st_mtime_ns))
        result['mode_override'] = True
    return result, env, tuple(fingerprints)


def initial_environment(proc):
    result = {}
    for entry in read_bytes(proc / 'environ').split(b'\0'):
        key, separator, value = entry.partition(b'=')
        name = key.decode('utf-8', 'replace')
        if separator and name in ENV_KEYS:
            result[name] = value.decode('utf-8', 'strict')
    return result


def effective_environment(initial, managed, category='api'):
    if category == 'worker' and 'VERA_SERVICE_ROLE' not in initial:
        # Worker entrypoint sets this before the managed loader runs.
        initial = {**initial, 'VERA_SERVICE_ROLE': 'worker'}
    result = {**initial, **managed}
    for key in ('VERA_SERVICE_ROLE', 'VERA_WORKER_DB_MODE'):
        if key in initial:
            result[key] = initial[key]
    return result


def numeric(value, minimum=0, maximum=1000000):
    try:
        if not re.fullmatch(r'[0-9]{1,' + str(len(str(maximum))) + '}', str(value)):
            return None
        number = int(value)
        return number if minimum <= number <= maximum else None
    except (TypeError, ValueError):
        return None


def pool_summary(env, category='api'):
    fields = {key: numeric(env[key]) for key in sorted(NUMERIC_KEYS & env.keys())}
    result = {'configured': fields, 'invalid_numeric_fields': sum(v is None for v in fields.values()),
              'budget_status': 'undeclared'}
    for key, allowed in MODE_VALUES.items():
        default = {'VERA_SERVICE_ROLE': 'worker' if category == 'worker' else 'combined', 'VERA_WORKER_DB_MODE': 'unknown',
                   'VERA_LIVE_TOUR_RELATIONAL_MODE': 'shadow'}[key]
        result[key] = env.get(key, default) if env.get(key, default) in allowed else 'invalid'
    if BUDGET_KEYS & env.keys():
        if not BUDGET_KEYS <= env.keys() or any(fields.get(key) is None for key in BUDGET_KEYS):
            result['budget_status'] = 'invalid_or_partial'
        else:
            values = {**{'DB_POOL_SIZE': 2, 'DB_MAX_OVERFLOW': 0, 'DB_AUTH_POOL_SIZE': 2}, **fields}
            background = fields.get('DB_BACKGROUND_POOL_SIZE', fields.get('DB_POOL_SIZE', 8))
            overflow = fields.get('DB_BACKGROUND_MAX_OVERFLOW', fields.get('DB_MAX_OVERFLOW', 12))
            if None not in (values['DB_POOL_SIZE'], values['DB_MAX_OVERFLOW'], values['DB_AUTH_POOL_SIZE'], background, overflow):
                demand = (values['DB_API_POOL_INSTANCES'] * (values['DB_POOL_SIZE'] + values['DB_MAX_OVERFLOW'] + max(1, min(4, values['DB_AUTH_POOL_SIZE'])))
                          + values['DB_BACKGROUND_POOL_INSTANCES'] * (background + overflow)
                          + values['DB_DEDICATED_CONNECTIONS'] + values['DB_EXTERNAL_CONNECTION_RESERVE'])
                result['declared_demand'] = demand
                result['budget_status'] = 'within_declaration' if demand <= values['DB_CONNECTION_BUDGET'] else 'exceeded'
    result['declaration_matches_actual_fleet'] = 'unverified'
    result['runtime_bounds_validated'] = False
    result['configuration_source'] = 'current_managed_file_plus_initial_process_environment'
    result['live_engine_configuration'] = 'unverified'
    if result['budget_status'] == 'within_declaration':
        result['budget_status'] = 'arithmetic_only_within_declaration'
    if BUDGET_KEYS <= fields.keys() and all(fields[k] is not None for k in BUDGET_KEYS):
        if fields['DB_API_POOL_INSTANCES'] + fields['DB_BACKGROUND_POOL_INSTANCES'] < 1:
            result['budget_status'] = 'invalid_or_partial'
    result['session_affinity'] = 'unverified_requires_provider_configuration'
    return result


def process_inventory(managed, proc_root=Path('/proc')):
    records, errors = [], 0
    dirs = sorted((p for p in proc_root.iterdir() if p.name.isdigit()), key=lambda p: int(p.name))
    if len(dirs) > MAX_PROCESSES:
        raise Unavailable()
    for proc in dirs:
        try:
            raw = read_bytes(proc / 'cmdline')
            tokens = raw.decode('utf-8', 'replace').split('\0')
            category = next((k for k, marker in PROCESS_MARKERS.items() if marker in tokens or (marker.endswith('.py') and any(Path(token).name == marker for token in tokens))), None)
            if category is None:
                continue
            owned = proc.stat().st_uid == os.getuid()
            cwd = (proc / 'cwd').resolve(strict=True)
            info = read_bytes(proc / 'stat').decode().rsplit(')', 1)[1].split()
            initial = initial_environment(proc) if owned else {}
            environment = effective_environment(initial, managed, category) if owned else {}
            code_sha = revision(cwd)
            cgroup = read_bytes(proc / 'cgroup').decode('utf-8')
            match = re.search(r'/system\.slice/([A-Za-z0-9_.@-]{1,120}\.service)(?:/|$)', cgroup, re.M)
            records.append({'category': category, 'owned': owned, 'pid': int(proc.name),
                            'start_ticks': int(info[19]), 'cwd': str(cwd), 'sha': code_sha,
                            'unit': match[1] if match else None, 'env': environment,
                            'initial_digest': hashlib.sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest()})
        except (FileNotFoundError, ProcessLookupError):
            continue
        except Exception:
            errors += 1
    return records, errors


def unit_summary(unit):
    properties = 'LoadState,ActiveState,SubState,MainPID,TasksCurrent,MemoryCurrent,TimeoutStopUSec,KillMode'
    code, output = command(['systemctl', 'show', unit, '--no-pager', '--property=' + properties])
    if code:
        return {'status': 'unknown'}
    values = dict(line.partition('=')[::2] for line in output.splitlines() if '=' in line)
    return {'status': 'observed', 'loaded': values.get('LoadState') == 'loaded',
            'active': values.get('ActiveState') == 'active',
            'running': values.get('SubState') == 'running', 'main_process_present': numeric(values.get('MainPID')) not in (None, 0),
            'tasks': numeric(values.get('TasksCurrent')), 'memory_bytes': numeric(values.get('MemoryCurrent'), maximum=10**15),
            'kill_mode': values.get('KillMode') if values.get('KillMode') in {'control-group', 'mixed', 'process', 'none'} else 'unknown',
            'shutdown_grace_at_least_30_seconds': duration_at_least_30(values.get('TimeoutStopUSec', ''))}


def duration_at_least_30(value):
    # systemctl formats these as human durations; unknown formats never pass.
    if re.fullmatch(r'[0-9]+s', value):
        return int(value[:-1]) >= 30
    if re.fullmatch(r'[0-9]+min(?: [0-9]+s)?', value):
        return int(value.split('min')[0]) >= 1
    return None


def schedule_summary():
    result = {'coverage': 'current_user_and_readable_system_files_only', 'other_user_crons': 'unknown',
              'known_entries': {key: 0 for key in PROCESS_MARKERS}, 'unclassified_vera_entries': 0,
              'read_sources': 0, 'unreadable_sources': 0}
    sources = []
    try:
        code, content = command(['crontab', '-l'], maximum=MAX_FILE)
        if code == 0:
            sources.append(content)
        else:
            result['unreadable_sources'] += 1
    except Exception:
        result['unreadable_sources'] += 1
    paths = [Path('/etc/crontab')]
    try:
        entries = list(Path('/etc/cron.d').iterdir())
        if len(entries) > 64:
            raise Unavailable()
        paths.extend(entries)
    except Exception:
        result['unreadable_sources'] += 1
    for path in paths:
        try:
            sources.append(read_bytes(path).decode('utf-8'))
        except Exception:
            result['unreadable_sources'] += 1
    for content in sources:
        result['read_sources'] += 1
        for line in content.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            # Do not count command-like text in comments as a recognized schedule.
            command_part = line.partition('#')[0]
            found = [key for key, marker in PROCESS_MARKERS.items() if marker in command_part]
            for key in found:
                result['known_entries'][key] += 1
            if not found and re.search(r'vera|timesoft|facegate', command_part, re.I):
                result['unclassified_vera_entries'] += 1
    result['entry_matches_are_hints_not_execution_proof'] = True
    return result


def deploy_summary():
    data = read_bytes(BASE / 'deploy.sh', maximum=262144)
    body = '\n'.join(line for line in data.decode('utf-8').splitlines() if not line.lstrip().startswith('#'))
    return {'sha256': hashlib.sha256(data).hexdigest(),
            'flock_token_present': bool(re.search(r'\bflock\b', body)),
            'api_service_token_present': 'vera-api.service' in body,
            'worker_entrypoint_token_present': 'vera_web_v2_worker' in body,
            'worker_service_token_present': 'vera-worker.service' in body,
            'current_symlink_token_present': '/current' in body or 'current=' in body,
            'shutdown_wait_token_present': bool(re.search(r'\b(wait|TimeoutStopSec)\b', body)),
            'locking_and_lifecycle_verified': False,
            'reason': 'static_tokens_only_host_script_not_executed'}


def host_capacity():
    memory = {}
    for line in read_bytes(Path('/proc/meminfo')).decode().splitlines():
        key, _, raw = line.partition(':')
        if key in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            match = re.fullmatch(r'\s*([0-9]{1,15}) kB', raw)
            memory[key + '_kib'] = int(match[1]) if match else None
    return {'cpu_logical': os.cpu_count(), 'memory': memory,
            'load_milli': [round(value * 1000) for value in os.getloadavg()],
            'concurrent_user_capacity': 'unmeasured'}


def snapshot(records, errors, config_fingerprint):
    current = (BASE / 'current').resolve(strict=True)
    metadata = (BASE / 'current').lstat()
    return (str(current), revision(current), metadata.st_ino, metadata.st_mtime_ns,
            hashlib.sha256(read_bytes(BASE / 'deploy.sh', 262144)).hexdigest(), config_fingerprint,
            errors, tuple((r['category'], r['pid'], r['start_ticks'], r['cwd'], r['sha'], r['initial_digest']) for r in records))


def run(expected_sha):
    result = {'format_version': 1, 'read_only': True, 'activation_authorized': False,
              'activation_ready': False, 'expected_main_sha': expected_sha,
              'audited_application_sha': AUDITED_RELEASE_SHA,
              'session_affinity': 'unverified_requires_provider_configuration',
              'all_writers_inventory_complete': False,
              'maintenance_window_minutes': 'not_established_by_read_only_inspection'}
    if not re.fullmatch('[0-9a-f]{40}', expected_sha):
        return {**result, 'status': 'invalid_expected_sha'}
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    try:
        config_status, managed, fingerprint = managed_configuration(home)
        records, errors = process_inventory(managed)
        before = snapshot(records, errors, fingerprint)
        api = [r for r in records if r['category'] == 'api']
        app = [r for r in records if r['category'] in {'api', 'worker'}]
        release_match = bool(api) and all(r['sha'] == AUDITED_RELEASE_SHA for r in app) and before[1] == AUDITED_RELEASE_SHA
        result['release'] = {'current_sha': before[1], 'all_application_processes_match_audited_release': release_match,
                             'observed_process_revisions': sorted({r['sha'] for r in app}),
                             'inventory_errors': errors}
        result['process_counts'] = dict(Counter(r['category'] for r in records))
        result['process_inventory_scope'] = 'recognized_command_tokens_only_descendants_and_external_hosts_unverified'
        result['managed_configuration'] = {**config_status, 'same_as_loaded_by_live_processes': 'unverified'}
        result['process_configurations'] = [dict(category=r['category'], owned=r['owned'], **pool_summary(r['env'], r['category'])) for r in app[:32]]
        result['host'] = host_capacity()
        result['deploy_script'] = deploy_summary()
        result['schedules'] = schedule_summary()
        units = dict(FIXED_UNITS)
        for index, unit in enumerate(sorted({r['unit'] for r in records if r['unit']})):
            units['observed_process_unit_' + str(index)] = unit
        result['services'] = {}
        for label, unit in list(units.items())[:24]:
            try:
                result['services'][label] = unit_summary(unit)
            except Exception:
                result['services'][label] = {'status': 'unknown'}
        targets = {tuple(sorted((k, r['env'].get(k, '')) for k in DB_KEYS)) for r in app if r['owned']}
        result['database'] = {'status': 'not_inspected_unverified_release_or_configuration'}
        if release_match and errors == 0 and len(targets) == 1 and all(r['owned'] for r in app):
            from sqlalchemy.engine import URL
            from phase_three_db_preflight import inspect_database
            env = app[0]['env']
            if all(env.get(k) for k in ('DB_HOST', 'DB_USER', 'DB_PASS')):
                sslmode = env.get('DB_SSLMODE', 'require')
                if sslmode not in {'require', 'verify-ca', 'verify-full'}:
                    raise Unavailable()
                url = URL.create('postgresql+psycopg', host=env['DB_HOST'], port=int(env.get('DB_PORT', '5432')),
                                 username=env['DB_USER'], password=env['DB_PASS'], database=env.get('DB_NAME', 'postgres'),
                                 query={'sslmode': sslmode})
                result['database'] = inspect_database(url)
        _, managed_after, fingerprint_after = managed_configuration(home)
        records_after, errors_after = process_inventory(managed_after)
        after = snapshot(records_after, errors_after, fingerprint_after)
        stable = before == after
        result['observation_stable'] = stable
        result['exclusive_deployment_lock_held'] = False
        if not stable:
            # Discard database findings: they cannot be assigned to a stable release.
            result['database'] = {'status': 'unknown_runtime_changed_during_observation'}
        result['status'] = ('target_release_moved' if not release_match else
                            'observed' if stable and errors == 0 else 'inconclusive')
    except Exception:
        result['status'] = 'unknown_host_inspection_failed'
        result['database'] = {'status': 'not_established'}
    return result


def main():
    import sys
    try:
        signal.signal(signal.SIGALRM, deadline_expired)
        signal.alarm(110)
        result = run(sys.argv[1] if len(sys.argv) == 2 else '')
        payload = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(payload.encode()) > 65536:
            raise Unavailable()
        print(payload)
    except (Exception, Deadline):
        print('{"status":"unknown_preflight_failed","read_only":true,"activation_ready":false}')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
