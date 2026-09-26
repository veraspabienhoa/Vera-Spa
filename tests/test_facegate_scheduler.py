"""Execute the actual installer with isolated, unprivileged VPS command doubles."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


COMMAND = r'''
import json, os, pathlib, sys
root = pathlib.Path(os.environ['FACEGATE_TEST_ROOT'])
flags = json.loads((root/'flags.json').read_text())
name = pathlib.Path(sys.argv[0]).name
with (root/'calls').open('a') as log: log.write(name+' '+('read' if sys.argv[1:]==['-l'] else 'other')+'\n')
if name == 'id': print('1001')
elif name == 'stat': print('1002' if flags.get('wrong_owner') else '1001')
elif name == 'pgrep':
    if flags.get('no_api'): sys.exit(1)
    print('123')
elif name == 'systemctl':
    assert sys.argv[1:3] == ['is-active', '--quiet'], 'Installer must not modify services'
    if sys.argv[-1]=='vera-facegate-sync.timer': sys.exit(0 if flags.get('timer_active') else 3)
    sys.exit(3 if flags.get('cron_inactive') else 0)
elif name == 'crontab':
    table=root/'crontab'
    if sys.argv[1:]==['-l']:
        if flags.get('read_denied'):
            print('account is not allowed to use crontab',file=sys.stderr); sys.exit(1)
        if flags.get('race'):
            counter=root/'reads'; n=int(counter.read_text())+1 if counter.exists() else 1; counter.write_text(str(n))
            if n==2: table.write_text(table.read_text()+'15 4 * * * concurrent-job\n')
        if not table.exists():
            print('no crontab for synthetic-account',file=sys.stderr); sys.exit(1)
        sys.stdout.write(table.read_text())
    else:
        if flags.get('write_denied'): sys.exit(1)
        assert len(sys.argv)==2, 'No editing another account cron'
        table.write_text(pathlib.Path(sys.argv[1]).read_text())
        with (root/'writes').open('a') as log: log.write('write\n')
else:
    raise AssertionError('Unexpected or privileged command: '+name)
'''


class FaceGateSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root/'spa'
        (self.base/'.venv/bin').mkdir(parents=True)
        (self.base/'current').mkdir()
        python = self.base/'.venv/bin/python'
        python.write_text('#!/bin/sh\nexit 0\n'); python.chmod(0o700)
        (self.base/'current/vera_facegate_auto_sync.py').write_text('# Worker existence only\n')
        self.bin = self.root/'bin'; self.bin.mkdir()
        for name in ('id', 'stat', 'pgrep', 'systemctl', 'crontab', 'sudo'):
            script = self.bin/name
            script.write_text(f'#!{sys.executable}\n'+COMMAND); script.chmod(0o700)
        self.installer = self.root/'install.sh'
        original = Path(__file__).resolve().parents[1]/'configure_facegate_sync.sh'
        self.installer.write_text(original.read_text().replace('/opt/vera-spa', str(self.base)))
        (self.root/'flags.json').write_text('{}')
        self.original = 'MAILTO=""\n# unrelated\n15 1 * * * backup-command # PRIVATE_JOB_SENTINEL\n'
        (self.root/'crontab').write_text(self.original)

    def run_installer(self, **flags):
        (self.root/'flags.json').write_text(json.dumps(flags))
        result = subprocess.run(['bash', str(self.installer)], text=True, capture_output=True, timeout=15,
            env={**os.environ, 'PATH': str(self.bin)+os.pathsep+os.environ['PATH'], 'FACEGATE_TEST_ROOT': str(self.root)})
        self.assertNotIn('PRIVATE_JOB_SENTINEL', result.stdout+result.stderr)
        self.assertNotIn('sudo ', (self.root/'calls').read_text())
        return result

    def test_non_root_install_preserves_jobs_and_repeated_install_is_unchanged(self):
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stderr)
        table = (self.root/'crontab').read_text()
        self.assertTrue(table.startswith(self.original))
        self.assertEqual(table.count('# VERA_FACEGATE_ARCHIVE_V1'), 1)
        self.assertIn('every minute', first.stdout)
        second = self.run_installer()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.root/'crontab').read_text(), table)
        self.assertEqual((self.root/'writes').read_text(), 'write\n')

    def test_empty_crontab_is_supported(self):
        (self.root/'crontab').unlink()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root/'crontab').read_text().count('# VERA_FACEGATE_ARCHIVE_V1'), 1)

    def test_denied_read_does_not_replace_existing_jobs(self):
        result = self.run_installer(read_denied=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot read', result.stderr)
        self.assertEqual((self.root/'crontab').read_text(), self.original)
        self.assertFalse((self.root/'writes').exists())

    def test_denied_write_is_reported_without_changing_privileges(self):
        result = self.run_installer(write_denied=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not allowed to install', result.stderr)
        self.assertEqual((self.root/'crontab').read_text(), self.original)

    def test_detected_concurrent_cron_edit_is_preserved(self):
        result = self.run_installer(race=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed during preparation', result.stderr)
        self.assertIn('concurrent-job', (self.root/'crontab').read_text())
        self.assertFalse((self.root/'writes').exists())

    def test_inactive_cron_does_not_claim_schedule_success(self):
        result = self.run_installer(cron_inactive=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cron service is not active', result.stderr)
        self.assertFalse((self.root/'writes').exists())

    def test_api_owner_must_match_current_deployment_account(self):
        result = self.run_installer(wrong_owner=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('same account', result.stderr)
        self.assertFalse((self.root/'writes').exists())

    def test_existing_active_timer_is_not_duplicated(self):
        result = self.run_installer(timer_active=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('existing timer active', result.stdout)
        self.assertFalse((self.root/'writes').exists())

    def test_managed_duplicate_entries_converge_to_one_without_losing_other_jobs(self):
        (self.root/'crontab').write_text(self.original + '*/2 * * * * old-worker # VERA_FACEGATE_ARCHIVE_V1\n'*2)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = (self.root/'crontab').read_text()
        self.assertTrue(installed.startswith(self.original))
        self.assertEqual(installed.count('# VERA_FACEGATE_ARCHIVE_V1'), 1)
