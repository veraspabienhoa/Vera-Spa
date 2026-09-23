"""Explicit VPS maintenance; never invoked by deploy or API startup.

Use the matching deployed release, as the API owner. A dedicated NullPool
connection holds BOTH session fences until runtime verification (or recovery)
finishes. Private pg_dump backups remain on the VPS. No business mutations are
submitted to production as a health test.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import vera_live_tour_cutover as cutover
import vera_live_tour_relational as relational
import vera_live_tour_resource_store as resources
from vera_web_v2_runtime_env import (
    LIVE_TOUR_MODE_RELATIVE_PATH, RUNTIME_ENV_KEYS, _read_private_file,
    load_managed_runtime_environment,
)
from vera_vps_data_check import _database_url

MODE_KEY = 'VERA_LIVE_TOUR_RELATIONAL_MODE'
LEGACY_FENCE = 'vera:v2:live_tour:state'
RELEASE = Path(__file__).resolve().parent


class MaintenanceError(RuntimeError):
    """Only operator-safe messages explicitly authored by this module."""


def command(args, *, timeout=30, env=None):
    # Never propagate subprocess stderr: pg_dump/systemctl may include secrets.
    result = subprocess.run(args, capture_output=True, timeout=timeout, env=env)
    if result.returncode:
        raise MaintenanceError('maintenance subprocess failed')
    return result.stdout.decode('utf-8', 'strict').strip()


def api_processes():
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if b'vera_web_v2_api_v38:app' not in args:
                continue
            if proc.stat().st_uid != os.getuid():
                raise MaintenanceError('API and maintenance owners differ')
            found.append((proc, (proc / 'cwd').resolve(strict=True), (proc / 'cgroup').read_text()))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return found


class Service:
    def __init__(self, sha):
        self.sha = sha
        processes = api_processes()
        if not processes:
            raise MaintenanceError('running API not found')
        units = set()
        for _, release, cgroup in processes:
            if release != RELEASE:
                raise MaintenanceError('multiple or different API releases found')
            match = re.search(r'system\.slice/([A-Za-z0-9_.@:-]+\.service)(?:/|$)', cgroup, re.M)
            if match:
                units.add(('system', match.group(1)))
            else:
                names = re.findall(r'/([A-Za-z0-9_.@:-]+\.service)(?=/|$)', cgroup, re.M)
                names = [name for name in names if not name.startswith('user@')]
                if not names:
                    raise MaintenanceError('API must run in a dedicated systemd unit')
                units.add(('user', names[-1]))
        if len(units) != 1:
            raise MaintenanceError('more than one API systemd unit found')
        self.scope, self.unit = units.pop()
        self.ctl = [shutil.which('systemctl') or '/usr/bin/systemctl']
        if self.scope == 'user':
            self.ctl.append('--user')
        if command(self.ctl + ['show', self.unit, '-p', 'KillMode', '--value']) != 'control-group':
            raise MaintenanceError('API unit must stop its complete control group')
        self.control = self.ctl
        self.verify_release()

    def authorize(self):
        if self.scope == 'system' and os.getuid() != 0:
            for action in ('stop', 'start'):
                try:
                    command(['sudo', '-n', '-l', *self.ctl, action, self.unit])
                except MaintenanceError:
                    raise MaintenanceError(
                        'noninteractive sudo authorization check failed for '
                        + shlex.join([*self.ctl, action, self.unit])
                        + '; ask the VPS administrator to verify this exact service permission'
                    ) from None
            self.control = ['sudo', '-n', *self.ctl]

    def verify_release(self):
        if command(['git', '-C', str(RELEASE), 'rev-parse', 'HEAD']) != self.sha:
            raise MaintenanceError('deployed SHA does not match requested SHA')
        if command(['git', '-C', str(RELEASE), 'status', '--porcelain', '--untracked-files=no']):
            raise MaintenanceError('deployed source has tracked changes')
        for _, release, _ in api_processes():
            if release != RELEASE:
                raise MaintenanceError('API release changed during maintenance')

    def stop(self):
        command([*self.control, 'stop', self.unit], timeout=90)
        if api_processes():
            raise MaintenanceError('API writers remain after service stop')
        if command(self.ctl + ['show', self.unit, '-p', 'ActiveState', '--value']) not in {'inactive', 'failed'}:
            raise MaintenanceError('API service did not stop')

    def start(self):
        command([*self.control, 'start', self.unit], timeout=90)


def health(expected_mode=None, attempts=1):
    for attempt in range(attempts):
        try:
            payloads = []
            for endpoint in ('auth/health', 'health'):
                with urllib.request.urlopen('http://127.0.0.1:8000/v2/' + endpoint, timeout=5) as response:
                    payloads.append(json.load(response))
            auth, business = payloads
            mode = business.get('live_tour_relational_mode')
            ready = business.get('live_tour_storage_ready')
            if (auth.get('ok') is True and auth.get('provider') == 'postgres-local'
                    and business.get('ok') is True and mode in {'off', 'shadow', 'verify', 'active'}
                    and isinstance(ready, bool) and ready == (mode == 'active')
                    and (expected_mode is None or mode == expected_mode)):
                return mode
        except (OSError, ValueError):
            pass
        if attempt + 1 < attempts:
            time.sleep(2)
    raise MaintenanceError('API Auth/business/storage health verification failed')


def write_private(path, content):
    fd, temp = tempfile.mkstemp(prefix='.maintenance-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def mode_configuration(content, mode):
    lines = [line for line in content.splitlines() if line.partition('=')[0].strip() != MODE_KEY]
    return '\n'.join(lines) + '\n' + MODE_KEY + '=' + shlex.quote(mode) + '\n'


def runtime_settings():
    """Read exact validated API processes; never trust the invoking SSH shell."""
    if load_managed_runtime_environment():
        return {key: os.environ[key] for key in RUNTIME_ENV_KEYS if key in os.environ}
    candidates = []
    for proc, _, _ in api_processes():
        values = {}
        for entry in (proc / 'environ').read_bytes().split(b'\0'):
            key, sep, value = entry.partition(b'=')
            name = key.decode('utf-8', 'strict')
            if sep and name in RUNTIME_ENV_KEYS:
                values[name] = value.decode('utf-8', 'strict')
        candidates.append(values)
    if not candidates or any(values != candidates[0] for values in candidates):
        raise MaintenanceError('API processes have missing or inconsistent runtime settings')
    values = candidates[0]
    # These are the shared API engine defaults, not the SSH environment.
    defaults = {'DB_PORT': '5432', 'DB_NAME': 'postgres',
                'DB_SSLMODE': 'require', 'DB_CONNECT_TIMEOUT': '10'}
    values = {**defaults, **values}
    _database_url(values)  # require host/user/password without logging values
    if values['DB_SSLMODE'] not in {'require', 'verify-ca', 'verify-full'}:
        raise MaintenanceError('API runtime requires supported verified TLS settings')
    if not 1 <= int(values['DB_PORT']) <= 65535 or not 3 <= int(values['DB_CONNECT_TIMEOUT']) <= 120:
        raise MaintenanceError('API database numeric settings are invalid')
    return values


def restore_mode_configuration(path, original):
    if original is not None:
        write_private(path, original)
    else:
        path.unlink(missing_ok=True)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def activation_preflight(service):
    """Read-only capability checks; never stop services or change sudo policy."""
    errors = []
    try:
        service.authorize()
    except MaintenanceError as exc:
        errors.append(str(exc))
    for binary in ('pg_dump', 'pg_restore'):
        if not shutil.which(binary):
            errors.append('required PostgreSQL client not found: ' + binary)
    if os.environ.get('DB_PORT') == '6543':
        errors.append('use a direct or session-pooled database connection for maintenance')
    return {'ok': not errors, 'service': service.unit, 'scope': service.scope, 'errors': errors}


def acquire_fences(conn):
    # Session locks survive cutover commit and also exclude writers in the new
    # API while health is checked. Closing this dedicated connection releases both.
    conn.execute(text("SET lock_timeout='5s'"))
    conn.execute(text("SET statement_timeout='120s'"))
    conn.execute(text('SELECT pg_advisory_lock(hashtext(:key))'), {'key': LEGACY_FENCE})
    conn.execute(text('SELECT pg_advisory_lock(hashtextextended(:key,0))'), {'key': resources.FENCE})
    conn.commit()
    conn.info['maintenance_pid'] = conn.execute(text('SELECT pg_backend_pid()')).scalar_one()
    conn.commit()


def verify_fences(conn):
    pid = conn.execute(text('SELECT pg_backend_pid()')).scalar_one()
    if pid != conn.info['maintenance_pid']:
        raise MaintenanceError('maintenance requires a dedicated database session')
    count = conn.execute(text("SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory' AND mode='ExclusiveLock' AND granted")).scalar_one()
    if count < 2:
        raise MaintenanceError('maintenance fence ownership lost')
    conn.commit()


def snapshot(conn, active):
    if active:
        state, revision, _ = resources.read(conn)
    else:
        row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='live_tour' AND setting_key='state'")).mappings().first()
        if not row or not isinstance(row['value_json'], dict):
            raise MaintenanceError('Live Tour board is not initialized')
        state, revision = row['value_json'], row['revision']
    return {'state': state, 'revision': int(revision)}


def backup(directory, state):
    # Same SSL settings as the API; password only in child environment, not argv.
    pg_env = os.environ.copy()
    for pg_key, db_key in {'PGHOST': 'DB_HOST', 'PGPORT': 'DB_PORT', 'PGDATABASE': 'DB_NAME',
                           'PGUSER': 'DB_USER', 'PGPASSWORD': 'DB_PASS', 'PGSSLMODE': 'DB_SSLMODE',
                           'PGCONNECT_TIMEOUT': 'DB_CONNECT_TIMEOUT'}.items():
        pg_env[pg_key] = os.environ[db_key]
    archive = directory / 'database.dump'
    command(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(archive)],
            timeout=300, env=pg_env)
    archive.chmod(0o600)
    command(['pg_restore', '--list', str(archive)], timeout=30)
    if archive.stat().st_size == 0:
        raise MaintenanceError('database backup is empty')
    write_private(directory / 'live-tour.json', relational._json(state))


def migrate(conn, rollback):
    verify_fences(conn)
    with conn.begin():
        cutover.run(conn, rollback=rollback)
        result = snapshot(conn, not rollback)
        if relational.resource_ready(conn) != (not rollback):
            raise MaintenanceError('cutover readiness verification failed')
        # Load canonical board through production reader; require every collection.
        if any(not isinstance(result['state'].get(name), list) for name in relational.RESOURCE_COLLECTIONS):
            raise MaintenanceError('canonical collection verification failed')
    return result


def transition(conn, service, path, original, old_mode, new_mode, directory):
    """Caller has stopped writers, completed backup, and holds session fences."""
    changed = False
    starting = False
    try:
        result = migrate(conn, rollback=new_mode != 'active')
        changed = True
        write_private(directory / 'phase.json', json.dumps({'phase': 'database_committed', 'mode': new_mode}))
        write_private(path, mode_configuration(original or '', new_mode))
        os.environ[MODE_KEY] = new_mode
        starting = True  # start may succeed even if systemctl's response fails
        service.start()
        health(new_mode, attempts=20)
        service.verify_release()
        if not api_processes():
            raise MaintenanceError('API process missing after restart')
        verify_fences(conn)
        write_private(directory / 'phase.json', json.dumps({'phase': 'verified', 'mode': new_mode}))
        return {'ok': True, 'mode': new_mode, 'revision': result['revision']}
    except BaseException:
        # If the DB connection was lost, commit/fence ownership is uncertain.
        # Never restart a potentially mismatched writer in that situation.
        try:
            if starting:
                service.stop()
            if conn.invalidated or conn.closed:
                raise MaintenanceError('database fence ownership lost; manual recovery required')
            conn.rollback()
            if changed:
                migrate(conn, rollback=old_mode != 'active')
            restore_mode_configuration(path, original)
            os.environ[MODE_KEY] = old_mode
            service.start()
            health(old_mode, attempts=20)
            service.verify_release()
            write_private(directory / 'phase.json', json.dumps({'phase': 'recovered', 'mode': old_mode}))
        except BaseException:
            # Best effort stop, never hide that automatic recovery failed.
            try:
                service.stop()
            except BaseException:
                pass
            raise MaintenanceError('automatic recovery incomplete; check private phase file and service before restarting') from None
        raise MaintenanceError('activation failed; previous mode and current data restored') from None


def _run(action, sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('exact release SHA required')
    service = Service(sha)
    old_mode = health()
    settings = runtime_settings()
    os.environ.update(settings)
    engine = create_engine(_database_url(settings), poolclass=NullPool,
                           connect_args={'sslmode': settings['DB_SSLMODE'],
                                         'connect_timeout': int(settings['DB_CONNECT_TIMEOUT'])})
    os.environ[MODE_KEY] = old_mode
    with engine.connect() as conn:
        ready = relational.resource_ready(conn)
        if ready != (old_mode == 'active'):
            raise MaintenanceError('API mode and database authority disagree')
        conn.rollback()
        if action == 'status':
            return {'ok': True, 'mode': old_mode, 'resource_ready': ready, 'changed': False,
                    'activation_preflight': activation_preflight(service)}
        if (action == 'activate' and ready) or (action == 'rollback' and not ready):
            return {'ok': True, 'mode': old_mode, 'resource_ready': ready, 'changed': False}
        preflight = activation_preflight(service)
        if not preflight['ok']:
            raise MaintenanceError('activation preflight failed before stopping writers: ' + '; '.join(preflight['errors']))
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        path = home / LIVE_TOUR_MODE_RELATIVE_PATH
        try:
            original = _read_private_file(path)
        except FileNotFoundError:
            original = None
        directory = home / '.local/state/vera-spa/live-tour-backups' / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid4().hex[:8])
        directory.mkdir(parents=True, mode=0o700)
        directory.chmod(0o700)
        if original is not None:
            write_private(directory / 'storage.env.before', original)
        write_private(directory / 'manifest.json', json.dumps({'mode': old_mode, 'sha': sha, 'unit': service.unit, 'scope': service.scope, 'mode_override_existed': original is not None}))
        write_private(directory / 'phase.json', json.dumps({'phase': 'preflight', 'mode': old_mode}))
        print('LIVE TOUR MAINTENANCE: preflight passed; stopping API and embedded projection workers', flush=True)
        try:
            service.stop()
            acquire_fences(conn)
            before = snapshot(conn, ready)
            conn.commit()
            backup(directory, before)
        except BaseException:
            # No cutover/config writes yet. A stopped healthy service can recover.
            conn.rollback()
            service.start()
            health(old_mode, attempts=20)
            raise MaintenanceError('preparation failed; no cutover applied') from None
        print('LIVE TOUR MAINTENANCE: private database backup verified; switching storage', flush=True)
        result = transition(conn, service, path, original, old_mode,
                            'active' if action == 'activate' else 'shadow', directory)
        # Release locks explicitly; NullPool also closes the physical connection.
        conn.execute(text('SELECT pg_advisory_unlock_all()'))
        conn.commit()
        return result


def run(action, sha):
    # Also exclude manual SSH invocations, independently of GitHub concurrency.
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    lock_path = home / '.config/vera-spa/live-tour-maintenance.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run(action, sha)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', choices=['status', 'activate', 'rollback'], required=True)
    parser.add_argument('--sha', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    def interrupted(_signum, _frame):
        raise InterruptedError('maintenance interrupted')
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        print(json.dumps(run(args.action, args.sha), sort_keys=True))
    except BaseException as exc:
        # Exception messages/tracebacks may contain database parameters or PII.
        reason = str(exc) if isinstance(exc, MaintenanceError) else type(exc).__name__
        print(f'LIVE TOUR MAINTENANCE FAILED: {reason}; inspect private phase.json on VPS. Do not change the mode flag manually.', flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
