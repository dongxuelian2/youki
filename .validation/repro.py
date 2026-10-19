"""Run issue #3818's complete OCI fixture in a disposable Linux mount namespace."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--phase', choices=['before', 'after'], required=True)
args = parser.parse_args()
runtime = str(args.runtime.resolve())
base = Path('results') / f'repro-{args.phase}'
base.mkdir(parents=True, exist_ok=True)
cases = [([], set()), (['sync'], {'sync'}), (['dirsync'], {'dirsync'}),
         (['sync', 'dirsync'], {'sync', 'dirsync'}), (['sync', 'async'], set()),
         (['async', 'sync'], {'sync'}), (['sync', 'async', 'dirsync'], {'dirsync'}),
         (['sync', 'dirsync', 'youki-unsupported-option'], None)]
for index, (options, expected) in enumerate(cases):
    bundle = (base / str(index)).resolve()
    (bundle / 'rootfs/dev').mkdir(parents=True)
    shutil.copyfile(shutil.which('busybox'), bundle / 'rootfs/busybox')
    (bundle / 'rootfs/busybox').chmod(0o755)
    config = {
        'ociVersion': '1.3.0', 'root': {'path': 'rootfs'},
        'process': {'terminal': False, 'user': {'uid': 0, 'gid': 0},
                    'args': ['/busybox', 'sh', '-c', "/busybox grep ' /stack ' /proc/self/mountinfo; exec /busybox sleep 300"],
                    'env': ['PATH=/'], 'cwd': '/'},
        'linux': {'namespaces': [{'type': 'mount'}, {'type': 'pid'}]},
        'mounts': [{'destination': '/proc', 'type': 'proc', 'source': 'proc'},
                   {'destination': '/stack', 'type': 'tmpfs', 'source': 'tmpfs',
                    'options': ['size=1m', 'mode=777', *options]}]}
    (bundle / 'config.json').write_text(json.dumps(config))
    cmd = [runtime, '--root', str(bundle / 'state')]
    container = f'repro-youki-{index}'
    try:
        with (bundle / 'process.log').open('w') as output, (bundle / 'create.stderr').open('w') as error:
            created = subprocess.run(cmd + ['create', '--bundle', str(bundle), container], stdout=output, stderr=error)
        print(f'{args.phase} {options}: create={created.returncode}', flush=True)
        print((bundle / 'create.stderr').read_text(), flush=True)
        if expected is None:
            assert created.returncode != 0, 'unsupported filesystem option unexpectedly accepted'
            continue
        assert created.returncode == 0, 'container creation failed before mountinfo could be checked'
        subprocess.run(cmd + ['state', container], check=True)
        subprocess.run(cmd + ['start', container], check=True)
        subprocess.run(cmd + ['state', container], check=True)
        for _ in range(50):
            lines = (bundle / 'process.log').read_text().splitlines()
            if any(' /stack ' in line for line in lines):
                break
            time.sleep(0.1)
        line = next(line for line in lines if ' /stack ' in line)
        print(line, flush=True)
        super_options = set(line.split(' - ', 1)[1].split()[2].split(','))
        actual = super_options & {'sync', 'dirsync'}
        wanted = expected if args.phase == 'after' else set()
        assert actual == wanted, f'{options}: expected {wanted}, got {actual}'
    finally:
        subprocess.run(cmd + ['delete', '--force', container], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print(f'{args.phase}: all 8 OCI cases matched the expected observations', flush=True)
