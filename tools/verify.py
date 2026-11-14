#!/usr/bin/env python3
"""Run all dunder-hundmat verification suites against a Dunder compiler."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('--graphics', action='store_true')
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix='dunder-hundmat-verify-') as tmp:
        work = Path(tmp)
        subprocess.run([compiler, 'test', ROOT / 'dogfood/tests.ddr', '-o', work / 'dogfood-tests'], check=True)
        subprocess.run(['python3', ROOT / 'tools/test-tabell.py', compiler], check=True)
        gfx_cmd = ['python3', ROOT / 'tools/test-graphics.py', compiler]
        if args.graphics:
            gfx_cmd.append('--graphics')
        subprocess.run(gfx_cmd, check=True)
        subprocess.run([compiler, 'test', ROOT / 'http/src/tests.ddr', '-o', work / 'http-tests'], check=True)
        subprocess.run(['python3', ROOT / 'tools/test-http.py', compiler], check=True)
    print('PASS all dunder-hundmat suites')


if __name__ == '__main__':
    main()
