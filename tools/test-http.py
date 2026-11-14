#!/usr/bin/env python3
"""Integration, protocol, concurrency, traversal, and throughput tests for dunder-http."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def read_http_response(sock):
    buf = bytearray()
    while b'\r\n\r\n' not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            raise RuntimeError(f'EOF before end of headers: {bytes(buf)!r}')
        buf.extend(chunk)
    hdr_end = buf.index(b'\r\n\r\n')
    head_bytes = bytes(buf[:hdr_end])
    rest = bytearray(buf[hdr_end + 4:])
    lines = head_bytes.split(b'\r\n')
    status_line = lines[0].decode('ascii')
    status_code = int(status_line.split(' ', 2)[1])
    headers = {}
    for line in lines[1:]:
        k, v = line.split(b':', 1)
        headers[k.decode('ascii').lower()] = v.decode('ascii').strip()
    clen = int(headers.get('content-length', '0'))
    return status_code, headers, rest, clen


def recv_exact_with_buf(sock, rest, count):
    while len(rest) < count:
        chunk = sock.recv(65536)
        if not chunk:
            raise RuntimeError(f'EOF reading body ({len(rest)}/{count})')
        rest.extend(chunk)
    body = bytes(rest[:count])
    del rest[:count]
    return body


def read_pipelined_responses(sock, count, is_head=False):
    buf = bytearray()
    responses = []
    for _ in range(count):
        while b'\r\n\r\n' not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError('EOF waiting for pipelined header')
            buf.extend(chunk)
        hdr_end = buf.index(b'\r\n\r\n')
        head_bytes = bytes(buf[:hdr_end])
        del buf[:hdr_end + 4]
        lines = head_bytes.split(b'\r\n')
        status = int(lines[0].decode('ascii').split(' ', 2)[1])
        headers = {}
        for line in lines[1:]:
            k, v = line.split(b':', 1)
            headers[k.decode('ascii').lower()] = v.decode('ascii').strip()
        clen = 0 if is_head else int(headers.get('content-length', '0'))
        while len(buf) < clen:
            chunk = sock.recv(65536)
            if not chunk:
                raise RuntimeError('EOF waiting for pipelined body')
            buf.extend(chunk)
        body = bytes(buf[:clen])
        del buf[:clen]
        responses.append((status, headers, body))
    assert len(buf) == 0, f'unexpected trailing bytes: {bytes(buf)!r}'
    return responses


def launch_server(binary, work_dir, doc_root, extra_args):
    proc = subprocess.Popen(
        [str(binary), '--host', '127.0.0.1', '--port', '0', '--dir', str(doc_root), *extra_args],
        cwd=work_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    if not line.startswith('LISTENING '):
        stderr = proc.stderr.read() if proc.stderr else ''
        proc.kill()
        raise RuntimeError(f'server failed to announce LISTENING: {line!r} stderr={stderr!r}')
    port = int(line.split(' ', 1)[1])
    return proc, port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    compiler = parser.parse_args().compiler.resolve(strict=True)

    http_dir = ROOT / 'http'
    with tempfile.TemporaryDirectory(prefix='dunder-http-test-') as tmp:
        work = Path(tmp)
        binary = work / 'dunder-http'
        subprocess.run([compiler, 'build', http_dir / 'src/main.ddr', '-o', binary],
                       cwd=http_dir, check=True, timeout=60)

        doc_root = work / 'www'
        (doc_root / 'sub').mkdir(parents=True)
        (doc_root / 'index.html').write_text('<!doctype html><h1>Dunder HTTP</h1>\n')
        (doc_root / 'sub/hello.txt').write_text('hej från statisk fil\n')
        secret = work / 'secret.txt'
        secret.write_text('TOP_SECRET_MUST_NEVER_ESCAPE')

        rng = random.Random(20261114)
        large_bytes = bytes(rng.getrandbits(8) for _ in range(512 * 1024))
        large_sha = hashlib.sha256(large_bytes).hexdigest()
        (doc_root / 'large.bin').write_bytes(large_bytes)

        proc, port = launch_server(binary, work, doc_root, ['--idle-ms', '5000'])
        try:
            # 1. GET & HEAD /healthz + POST /echo binary + static files + large.bin
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            conn.request('GET', '/healthz')
            r = conn.getresponse()
            assert r.status == 200 and r.read() == b'ok\n'

            conn.request('HEAD', '/healthz')
            r = conn.getresponse()
            assert r.status == 200 and r.getheader('Content-Length') == '3' and r.read() == b''

            payload = bytes(range(256)) + b'\r\n\r\nPOST /fake HTTP/1.1\r\n\r\n'
            conn.request('POST', '/echo', body=payload, headers={'Content-Type': 'application/x-test'})
            r = conn.getresponse()
            assert r.status == 200 and r.getheader('Content-Type') == 'application/x-test' and r.read() == payload

            conn.request('GET', '/')
            r = conn.getresponse()
            assert r.status == 200 and b'text/html' in r.getheader('Content-Type', '').encode() and b'Dunder HTTP' in r.read()

            conn.request('GET', '/sub/hello.txt')
            r = conn.getresponse()
            assert r.status == 200 and r.read() == 'hej från statisk fil\n'.encode('utf-8')

            conn.request('GET', '/large.bin')
            r = conn.getresponse()
            got_large = r.read()
            assert r.status == 200 and hashlib.sha256(got_large).hexdigest() == large_sha

            conn.request('GET', '/stats')
            r = conn.getresponse()
            stats_json = json.loads(r.read().decode('utf-8'))
            assert stats_json['requests'] >= 7 and stats_json['active_connections'] >= 1
            conn.close()

            # 2. Raw-socket traversal rejection (no client normalization)
            for bad_path in ['/../secret.txt', '/sub/../../secret.txt', '//etc/passwd', '/sub/']:
                with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
                    s.sendall(f'GET {bad_path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'.encode())
                    code, _, rest, clen = read_http_response(s)
                    body = recv_exact_with_buf(s, rest, clen)
                    assert code in (400, 404), (bad_path, code)
                    assert b'TOP_SECRET' not in body

            # 3. Single-connection keep-alive (10 sequential) + 4x HTTP pipelining + Connection: close
            with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                for _ in range(10):
                    s.sendall(b'GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n')
                    code, _, rest, clen = read_http_response(s)
                    assert code == 200 and recv_exact_with_buf(s, rest, clen) == b'ok\n'

                pipe = b''.join([
                    b'GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n',
                    b'POST /echo HTTP/1.1\r\nHost: localhost\r\nContent-Length: 4\r\n\r\nabcd',
                    b'GET /sub/hello.txt HTTP/1.1\r\nHost: localhost\r\n\r\n',
                    b'GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n',
                ])
                s.sendall(pipe)
                resps = read_pipelined_responses(s, 4)
                assert [r[0] for r in resps] == [200, 200, 200, 200]
                assert resps[0][2] == b'ok\n'
                assert resps[1][2] == b'abcd'
                assert resps[2][2] == 'hej från statisk fil\n'.encode('utf-8')
                assert resps[3][1].get('connection') == 'close'
                assert s.recv(16) == b''

            # 4. Fragmented delivery across separate poll ticks + error status codes
            with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
                s.sendall(b'POST /ech')
                time.sleep(0.01)
                s.sendall(b'o HTTP/1.1\r\nContent-Length: 5\r\n\r\nhe')
                time.sleep(0.01)
                s.sendall(b'llo')
                code, _, rest, clen = read_http_response(s)
                assert code == 200 and recv_exact_with_buf(s, rest, clen) == b'hello'

            for req_bytes, expected_code in [
                (b'BAD\r\n\r\n', 400),
                (b'FOOBAR / HTTP/1.1\r\n\r\n', 501),
                (b'POST /echo HTTP/1.1\r\nContent-Length: 100000\r\n\r\n', 413),
                (b'POST /echo HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n', 501),
            ]:
                with socket.create_connection(('127.0.0.1', port), timeout=5) as s:
                    s.sendall(req_bytes)
                    code, _, _, _ = read_http_response(s)
                    assert code == expected_code, (req_bytes, code, expected_code)

            # 5. Concurrent keep-alive throughput benchmark: 16 clients x 100 requests = 1600 requests
            workers = 16
            reqs_per_worker = 100

            def worker(_idx):
                latencies = []
                with socket.create_connection(('127.0.0.1', port), timeout=10) as s:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    for r_idx in range(reqs_per_worker):
                        t0 = time.perf_counter_ns()
                        if r_idx % 2 == 0:
                            s.sendall(b'GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n')
                            code, _, rest, clen = read_http_response(s)
                            body = recv_exact_with_buf(s, rest, clen)
                            assert code == 200 and body == b'ok\n'
                        else:
                            s.sendall(b'GET /sub/hello.txt HTTP/1.1\r\nHost: localhost\r\n\r\n')
                            code, _, rest, clen = read_http_response(s)
                            body = recv_exact_with_buf(s, rest, clen)
                            assert code == 200 and body.endswith(b'fil\n')
                        latencies.append((time.perf_counter_ns() - t0) / 1_000_000)
                return latencies

            t_start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                all_latencies = [lat for sub in pool.map(worker, range(workers)) for lat in sub]
            elapsed = time.perf_counter() - t_start
            total_reqs = workers * reqs_per_worker
            rps = total_reqs / elapsed
            med_ms = statistics.median(all_latencies)
            p95_ms = sorted(all_latencies)[int(len(all_latencies) * 0.95)]
            print(f'PASS concurrency & throughput: {total_reqs} reqs across {workers} workers in {elapsed:.3f}s ({rps:.0f} req/s, median={med_ms:.3f}ms, p95={p95_ms:.3f}ms)')
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        # 6. Idle timeout disconnect test
        proc_idle, idle_port = launch_server(binary, work, doc_root, ['--idle-ms', '250'])
        try:
            with socket.create_connection(('127.0.0.1', idle_port), timeout=3) as s:
                s.settimeout(2.0)
                assert s.recv(16) == b''
        finally:
            proc_idle.terminate()
            proc_idle.wait(timeout=5)
        print('PASS dunder-http: HTTP/1.1 methods, static SHA-256, traversal confinement, keep-alive, pipelining, errors, concurrency, and idle timeout')


if __name__ == '__main__':
    main()
