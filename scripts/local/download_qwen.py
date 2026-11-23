"""Fetch official Ollama artifacts through the current HTTPS proxy, verify every SHA256."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import os
import time
import urllib.request
import requests
import threading

MODEL = 'qwen3.5'
TAG = '9b'
REGISTRY = 'https://registry.ollama.ai'
STORE = Path.home() / '.ollama/models'
STAGING = Path.home() / '.cache/travel-agent-qwen35'
WORKERS = 16
PART_BYTES = 8 * 1024 * 1024
TIMEOUT = 120
THREAD_LOCAL = threading.local()

STAGING.mkdir(parents=True, exist_ok=True)
BLOBS = STORE / 'blobs'
BLOBS.mkdir(parents=True, exist_ok=True)
base = f'{REGISTRY}/v2/library/{MODEL}'
with urllib.request.urlopen(f'{base}/manifests/{TAG}', timeout=30) as r:
    manifest_bytes = r.read()
manifest = json.loads(manifest_bytes)
layers = manifest['layers'] + [manifest['config']]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return 'sha256:' + h.hexdigest()

def fetch_part(item, start):
    if not hasattr(THREAD_LOCAL, 'session'):
        THREAD_LOCAL.session = requests.Session()
    end = min(item['size'], start + PART_BYTES) - 1
    part = STAGING / f"{item['digest'].replace(':', '-')}.{start}.part"
    if part.exists() and part.stat().st_size == end - start + 1:
        return part
    url = f"{base}/blobs/{item['digest']}?download_part={start}"
    for attempt in range(12):
        try:
            offset = part.stat().st_size if part.exists() else 0
            if offset == end - start + 1:
                return part
            current = start + offset
            headers = {'Range': f'bytes={current}-{end}', 'Cache-Control': 'no-cache'}
            with THREAD_LOCAL.session.get(url + f'&offset={offset}', headers=headers, timeout=TIMEOUT, stream=True) as response:
                expected = f"bytes {current}-{end}/{item['size']}"
                if response.status_code != 206 or response.headers.get('Content-Range') != expected:
                    raise RuntimeError('Unexpected ranged response')
                with part.open('ab') as f:
                    for b in response.iter_content(1024 * 1024):
                        if b:
                            f.write(b)
            if part.stat().st_size != end - start + 1:
                raise RuntimeError('Incomplete range')
            return part
        except Exception:
            if attempt == 11:
                raise
            time.sleep(2)

for item in layers:
    target = BLOBS / item['digest'].replace(':', '-')
    if target.exists() and target.stat().st_size == item['size'] and digest(target) == item['digest']:
        print('Already verified:', item['mediaType'], flush=True)
        continue
    print('Downloading:', item['mediaType'], round(item['size']/1e9, 2), 'GB', flush=True)
    if item['size'] < PART_BYTES:
        with urllib.request.urlopen(f"{base}/blobs/{item['digest']}", timeout=TIMEOUT) as r:
            data = r.read()
        tmp = STAGING / (item['digest'].replace(':','-') + '.assembled')
        tmp.write_bytes(data)
    else:
        starts = list(range(0, item['size'], PART_BYTES))
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_part, item, start): start for start in starts}
            complete = 0
            last_report = 0
            for future in concurrent.futures.as_completed(futures):
                path = future.result()
                complete += path.stat().st_size
                if time.monotonic() - last_report > 20 or complete == item['size']:
                    print('Progress:', round(100 * complete/item['size'],1), '%', flush=True)
                    last_report = time.monotonic()
        tmp = STAGING / (item['digest'].replace(':','-') + '.assembled')
        with tmp.open('wb') as dest:
            for start in starts:
                path = STAGING / f"{item['digest'].replace(':', '-')}.{start}.part"
                with path.open('rb') as src:
                    while b := src.read(8 * 1024 * 1024):
                        dest.write(b)
    if tmp.stat().st_size != item['size'] or digest(tmp) != item['digest']:
        raise RuntimeError('Official SHA256 verification failed')
    os.replace(tmp, target)
    for part in STAGING.glob(item['digest'].replace(':','-') + '.*.part'):
        part.unlink()
    print('SHA256 verified:', item['mediaType'], flush=True)

target = STORE / 'manifests/registry.ollama.ai/library' / MODEL / TAG
target.parent.mkdir(parents=True, exist_ok=True)
tmp = target.with_suffix('.download')
tmp.write_bytes(manifest_bytes)
os.replace(tmp, target)
print('Official model manifest installed; all artifacts verified.', flush=True)
