"""Send only the reviewed fixed diagnostic over SSH stdin; no host installation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

MAX_PAYLOAD = 262144
MAX_OUTPUT = 65536


def payload(directory):
    sources = {}
    for name in ('phase_three_db_preflight', 'phase_three_host_preflight'):
        body = (directory / (name + '.py')).read_text(encoding='utf-8')
        compile(body, name, 'exec')
        sources[name] = body
    script = (
        'import sys, types\n'
        'sys.dont_write_bytecode = True\n'
        'module = types.ModuleType("phase_three_db_preflight")\n'
        'sys.modules[module.__name__] = module\n'
        'exec(compile(' + repr(sources['phase_three_db_preflight']) + ', "fixed_db_preflight", "exec"), module.__dict__)\n'
        'exec(compile(' + repr(sources['phase_three_host_preflight']) + ', "fixed_host_preflight", "exec"), {"__name__": "__main__"})\n'
    ).encode('utf-8')
    if len(script) > MAX_PAYLOAD:
        raise ValueError('fixed payload exceeds limit')
    return script


def ssh_arguments(expected_sha, env):
    if not re.fullmatch(r'[0-9a-f]{40}', expected_sha):
        raise ValueError('invalid expected SHA')
    user, host = env.get('VPS_USER', ''), env.get('VPS_HOST', '')
    # argv is never a shell string; exclude options/control characters anyway.
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.-]{0,63}', user):
        raise ValueError('invalid SSH account')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}', host):
        raise ValueError('invalid SSH host')
    directory = Path(env['RUNNER_TEMP']) / 'vera-preflight-ssh'
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=10',
            '-o', 'ServerAliveCountMax=2', '-o', 'LogLevel=ERROR', '-o', 'IdentitiesOnly=yes',
            '-o', 'UserKnownHostsFile=' + str(directory / 'known_hosts'),
            '-i', str(directory / 'id_ed25519'), user + '@' + host,
            'timeout 125 /opt/vera-spa/.venv/bin/python -I -B - ' + expected_sha]


def bounded_exchange(arguments, source, *, timeout=140):
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    output = bytearray()
    offset = 0
    deadline = time.monotonic() + timeout
    try:
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdin, selectors.EVENT_WRITE, 'input')
            selector.register(process.stdout, selectors.EVENT_READ, 'output')
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('diagnostic timed out')
                for key, _ in selector.select(min(remaining, 0.2)):
                    if key.data == 'input':
                        written = os.write(key.fd, source[offset:offset + 16384])
                        offset += written
                        if offset == len(source):
                            selector.unregister(key.fd)
                            process.stdin.close()
                    else:
                        chunk = os.read(key.fd, min(16384, MAX_OUTPUT + 1 - len(output)))
                        if not chunk:
                            selector.unregister(key.fd)
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT:
                            raise ValueError('diagnostic output exceeds limit')
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if code:
            raise ValueError('diagnostic unavailable')
        result = json.loads(output)
        if (not isinstance(result, dict) or result.get('read_only') is not True
                or result.get('activation_ready') is not False):
            raise ValueError('unexpected diagnostic response')
        return result
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha', required=True)
    args = parser.parse_args()
    try:
        result = bounded_exchange(ssh_arguments(args.expected_sha, os.environ), payload(Path(__file__).parent))
        if result.get('expected_main_sha') != args.expected_sha:
            raise ValueError('unexpected diagnostic revision')
        print('PHASE_THREE_PREFLIGHT=' + json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
        # Incomplete gates are an expected finding; command success is not readiness.
        return 0 if result.get('status') == 'observed' else 2
    except Exception:
        print('PHASE_THREE_PREFLIGHT={"status":"unknown_transport_or_response","read_only":true,"activation_ready":false}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
