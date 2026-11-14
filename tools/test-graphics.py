#!/usr/bin/env python3
"""Verify Metal, Vulkan and WebGPU graphics dogfood targets."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAC = platform.system() == 'Darwin'
LINUX_TARGETS = {
    'arm64-linux': (183, '/lib/ld-linux-aarch64.so.1'),
    'x86_64-linux': (62, '/lib64/ld-linux-x86-64.so.2'),
}


def command(args, *, cwd, status=0, env=None):
    result = subprocess.run(
        args,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )
    accepted = result.returncode > 0 if status is None else result.returncode == status
    if not accepted:
        raise RuntimeError(f'{args}: exit {result.returncode}\n{result.stdout}{result.stderr}')
    if 'VUID-' in result.stderr or 'Validation Error' in result.stderr:
        raise RuntimeError(result.stderr)
    return result


def check_elf(image, machine, interpreter):
    assert image[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', image, 18)[0] == machine
    table, = struct.unpack_from('<Q', image, 32)
    stride, count = struct.unpack_from('<HH', image, 54)
    segments = [struct.unpack_from('<IIQQQQQQ', image, table + i * stride) for i in range(count)]
    loaders = [image[offset:offset + size] for kind, _, offset, _, _, size, _, _ in segments if kind == 3]
    assert loaders == [interpreter.encode() + b'\0']


def check_webgpu(build, work):
    wasm_out = work / 'webgpu.wasm'
    build(ROOT / 'dogfood/webgpu/main.ddr', wasm_out, '--target', 'wasm32')
    script = """
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const mod = new WebAssembly.Module(readFileSync(process.argv[2]));
let draws = 0;
let instance;
instance = new WebAssembly.Instance(mod, {
  webgpu: {
    draw(surface, p, count) {
      assert.equal(surface, 1);
      assert.equal(count, 3);
      const expected = [
        0, 0.72, 0, 1, 1, 0.69, 0.28, 1,
        -0.72, -0.62, 0, 1, 0.16, 0.87, 0.74, 1,
        0.72, -0.62, 0, 1, 0.40, 0.47, 1, 1,
      ].map(Math.fround);
      const actual = [...new Float32Array(instance.exports.memory.buffer, p, expected.length)];
      assert.deepEqual(actual, expected);
      draws++;
    }
  }
});
instance.exports.main();
assert.equal(draws, 1);
"""
    checker = work / 'check_webgpu.mjs'
    checker.write_text(script)
    command(['node', checker, wasm_out], cwd=work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('--graphics', action='store_true', help='execute native Metal or Vulkan/SDL graphics')
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='dunder-hundmat-gfx-') as tmp:
        work = Path(tmp)

        def build(source, output, *flags, status=0):
            return command(
                [compiler, 'build', source, '-o', output, *flags],
                cwd=work,
                env={'PATH': '/no-external-tools'},
                status=status,
            )

        triangle = ROOT / 'dogfood/vulkan/triangle.ddr'
        metal = ROOT / 'dogfood/metal/triangle.ddr'
        for source, target in [(triangle, 'arm64-macos'), (metal, 'arm64-linux')]:
            rejection = build(source, work / 'unexpected', '--target', target, status=None)
            assert 'requires the selected native platform' in rejection.stderr
            assert not (work / 'unexpected').exists()

        for target, (machine, interpreter) in LINUX_TARGETS.items():
            path = work / target
            build(triangle, path, '--target', target)
            image = path.read_bytes()
            check_elf(image, machine, interpreter)
            build(triangle, path, '--target', target)
            assert image == path.read_bytes()

        mac_triangle = work / 'Triangle.app'
        build(metal, mac_triangle, '--target', 'arm64-macos', '--app')
        plist = plistlib.loads((mac_triangle / 'Contents/Info.plist').read_bytes())
        assert plist['CFBundleExecutable'] == 'Triangle'
        assert (mac_triangle / 'Contents/MacOS/Triangle').is_file()

        check_webgpu(build, work)
        print('PASS graphics: Vulkan ELF cross-builds, Metal .app bundle, and WebGPU Wasm module')

        if args.graphics:
            if MAC:
                command(['/usr/bin/codesign', '--verify', '--strict', mac_triangle], cwd=work)
                programs = [(mac_triangle / 'Contents/MacOS/Triangle', ['--frames', '3'], 'triangle frames=3')]
                for name, run_args, expected in [
                    ('main', ['--frames', '3'], 'atlas frames=3'),
                    ('lifecycle', [], 'lifecycle cycles=3'),
                    ('events', [], 'native event sequence ok'),
                ]:
                    out = work / name
                    build(ROOT / f'dogfood/metal/{name}.ddr', out)
                    programs.append((out, run_args, expected))
                for binary, run_args, expected in programs:
                    assert command([binary, *run_args], cwd=work, env={'MTL_DEBUG_LAYER': '1'}).stdout.strip() == expected
                print('PASS live AppKit/Metal graphics execution')
            else:
                for name, run_args, expected in [
                    ('triangle', ['--headless', '--frames', '3'], 'triangle frames=3'),
                    ('main', ['--headless', '--frames', '3'], 'atlas frames=3'),
                    ('lifecycle', [], 'lifecycle cycles=3'),
                    ('pixels', [], 'pixels ok'),
                    ('events', [], 'SDL surface and events ok'),
                ]:
                    out = work / name
                    build(ROOT / f'dogfood/vulkan/{name}.ddr', out)
                    env = {'SDL_VIDEODRIVER': 'dummy'} if name == 'events' else {}
                    result = command([out, *run_args], cwd=work, env=env)
                    assert result.stdout.splitlines()[-1] == expected, result.stdout
                print('PASS live Vulkan graphics execution')


if __name__ == '__main__':
    main()
