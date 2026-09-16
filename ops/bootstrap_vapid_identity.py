#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ENV_PATH = Path('/etc/vera-spa/backend.env')
SUBJECT = 'https://app.veraspa.vn/'
REQUIRED = (
    'VERA_V2_VAPID_PRIVATE_KEY',
    'VERA_V2_VAPID_PUBLIC_KEY',
    'VERA_V2_VAPID_SUBJECT',
)


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def existing_names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            names.add(line.split('=', 1)[0].strip())
    return names


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit('Run as root.')
    if not ENV_PATH.exists():
        raise SystemExit(f'Missing {ENV_PATH}')

    text = ENV_PATH.read_text()
    present = existing_names(text)
    found = [name for name in REQUIRED if name in present]
    if found:
        raise SystemExit('VAPID bootstrap refused: one or more VAPID variables already exist.')

    key = ec.generate_private_key(ec.SECP256R1())
    private_value = key.private_numbers().private_value.to_bytes(32, 'big')
    public_value = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = ENV_PATH.with_name(f'{ENV_PATH.name}.backup.vapid-{stamp}')
    shutil.copy2(ENV_PATH, backup)

    addition = (
        f'\nVERA_V2_VAPID_PRIVATE_KEY={b64url(private_value)}\n'
        f'VERA_V2_VAPID_PUBLIC_KEY={b64url(public_value)}\n'
        f'VERA_V2_VAPID_SUBJECT={SUBJECT}\n'
    )
    with ENV_PATH.open('a') as handle:
        handle.write(addition)
    os.chmod(ENV_PATH, 0o600)

    subprocess.run([
        'runuser', '-u', 'postgres', '--', 'psql', '-d', 'veraspa', '-v', 'ON_ERROR_STOP=1', '-c',
        "UPDATE public.vera_v2_push_subscription SET is_active=false, "
        "last_error='VAPID identity rotated; client re-registration required', "
        "updated_at=NOW() WHERE is_active=true;",
    ], check=True)

    print('VAPID_BOOTSTRAP=OK')
    print(f'BACKUP={backup}')
    print('OLD_ACTIVE_SUBSCRIPTIONS=DEACTIVATED')
    print('SECRET_VALUES=NOT_PRINTED')


if __name__ == '__main__':
    main()
