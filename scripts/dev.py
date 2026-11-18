#!/usr/bin/env python3
"""Start the PostgreSQL-backed development workspace and stop owned processes cleanly."""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def env_value(name: str, default: str) -> str:
    if os.getenv(name):
        return os.environ[name]
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip().startswith(name + '='):
            return line.split('=', 1)[1].strip().strip('"').strip("'") or default
    return default


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port', type=int, default=int(os.getenv('GALVANISE_API_PORT', '8000')))
    parser.add_argument('--skip-db', action='store_true', help='Use an already configured PostgreSQL server')
    args = parser.parse_args()
    for tool in ('uv', 'npm', 'docker'):
        if tool == 'docker' and args.skip_db:
            continue
        if not shutil.which(tool):
            raise SystemExit(f'Install {tool} before starting Galvanise. See README.md.')
    config = ROOT / '.env'
    if not config.exists():
        content = (ROOT / '.env.example').read_text()
        content = '\n'.join(content.splitlines()) + '\n'
        config.write_text(content)
        config.chmod(0o600)
        print('Created .env. Configure Clerk, OpenAI, and GitHub there to enable them.', flush=True)
    web_url = env_value('WEB_URL', 'http://localhost:3000')
    address = urlparse(web_url)
    if address.hostname not in ('localhost', '127.0.0.1') or address.scheme != 'http':
        raise SystemExit('Local development requires WEB_URL=http://localhost:<port> in .env.')
    web_port = address.port or 80
    for port in (args.api_port, web_port):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise SystemExit(f'Port {port} is occupied. Change WEB_URL and GITHUB_CALLBACK_URL in .env or use --api-port.')
    if not args.skip_db:
        run(['docker', 'compose', 'up', '-d', '--wait', 'db'])
    if not (ROOT / 'node_modules' / 'next').exists():
        run(['npm', 'ci'])
    api = ROOT / 'apps' / 'api'
    run(['uv', 'sync'], api)
    run(['uv', 'run', 'alembic', 'upgrade', 'head'], api)
    children: list[subprocess.Popen] = []
    def stop(_signum=None, _frame=None):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen(['uv', 'run', 'uvicorn', 'galvanise.main:app', '--host', '127.0.0.1',
                                          '--port', str(args.api_port)], cwd=api, start_new_session=True))
        web_env = {**os.environ, 'API_URL': f'http://127.0.0.1:{args.api_port}'}
        children.append(subprocess.Popen(['npm', 'run', 'dev', '--workspace', '@galvanise/web', '--',
                                          '--hostname', address.hostname, '--port', str(web_port)],
                                         cwd=ROOT, env=web_env, start_new_session=True))
        print(f'\nGalvanise: {web_url}\nAPI docs: http://127.0.0.1:{args.api_port}/docs\nCtrl-C stops these app processes; PostgreSQL data stays in Docker.\n', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        failed = next(child for child in children if child.poll() is not None)
        raise SystemExit(f'An application process exited with code {failed.returncode}; inspect its output above.')
    except KeyboardInterrupt:
        print('\nStopping Galvanise app processes…', flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == '__main__':
    main()
