"""Offline synthetic CPU comparison; excludes DB, network, rendering and production.

python scripts/benchmark_system_performance.py --baseline e734dd90 --samples 20
The baseline is read from local git; no network or real employee records.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
from time import perf_counter
import types
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vera_web_v2_department_payroll as current


def norm(value):
    value = unicodedata.normalize('NFD', str(value or '').strip().lower())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn').replace('đ', 'd')
    return re.sub(r'\s+', ' ', value).strip()


def measure(fn, samples):
    fn()
    results = []
    for _ in range(samples):
        started = perf_counter()
        fn()
        results.append((perf_counter() - started) * 1000)
    results.sort()
    return {'p50_ms': round(statistics.median(results), 3),
            'p95_ms': round(results[max(0, int(samples * .95) - 1)], 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='e734dd90')
    parser.add_argument('--samples', type=int, default=20)
    args = parser.parse_args()
    source = subprocess.check_output(['git', 'show', f'{args.baseline}:vera_web_v2_department_payroll.py'], cwd=ROOT, text=True)
    baseline = types.ModuleType('baseline_payroll')
    exec(compile(source, 'baseline_payroll.py', 'exec'), baseline.__dict__)
    definitions = {'locker': {'Ca 1': {'start': '09:30', 'end': '17:00'}, 'Ca 2': {'start': '17:00', 'end': '01:00'}}}
    cfg = current.DEFAULT_CONFIG['locker']
    for count in (15, 60, 200):
        names = [f'test_{i}' for i in range(count)]
        rows = [dict(employee_username=name, work_date=date(2026, 10, day),
                     schedule_department='locker', shift_code='Ca 1' if day % 2 else 'Ca 2')
                for name in names for day in range(1, 32)]
        def old():
            return [baseline._schedule_totals(rows, name, 'locker', definitions, cfg, norm) for name in names]
        def new():
            grouped = current._group_payroll_records(rows, 'employee_username', norm)
            return [current._schedule_totals(grouped[norm(name)], name, 'locker', definitions, cfg, norm) for name in names]
        assert old() == new(), 'Computed wages/hours differ'
        before, after = measure(old, args.samples), measure(new, args.samples)
        print(json.dumps({'baseline': args.baseline, 'employees': count, 'rows': len(rows),
                          'samples': args.samples, 'equal': True, 'before': before, 'after': after,
                          'p50_speedup': round(before['p50_ms'] / after['p50_ms'], 2)}), flush=True)


if __name__ == '__main__':
    main()
