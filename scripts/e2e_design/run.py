"""Run browser acceptance H from an integrated Git checkout."""

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
APP_FILES = (
    "apps/web",
    "apps/api/galvanise",
    "apps/api/alembic",
    "apps/api/alembic.ini",
    "apps/api/tests/parking_model.py",
    "src",
    "astryx-themes.js",
    "package.json",
    "package-lock.json",
)


def stage(root, tmp):
    # Copy tracked sources only. The app cannot read the developer's .env or .next.
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", *APP_FILES], cwd=root
    )
    for entry in paths.split(b"\0"):
        if not entry:
            continue
        name = Path(os.fsdecode(entry))
        if name.name.startswith(".env"):
            continue
        target = tmp / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    modules = Path(os.environ.get("E2E_NODE_MODULES", root / "node_modules")).resolve(
        strict=True
    )
    (tmp / "node_modules").symlink_to(modules, target_is_directory=True)
    # This one-shot server cannot reuse a persistent webpack cache after teardown.
    with (tmp / "apps/web/next.config.js").open("a") as config:
        config.write("""
const appWebpack = module.exports.webpack;
module.exports.webpack = (config, options) => {
  const result = appWebpack ? appWebpack(config, options) : config;
  result.cache = false;
  return result;
};
""")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def server(args, cwd, env, origin):
    process = subprocess.Popen(args, cwd=cwd, env=env, start_new_session=True)
    try:
        deadline = time.monotonic() + 100
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with urlopen(origin + "/api/health", timeout=3) as response:
                    if json.load(response)["status"] == "ok":
                        break
            except (URLError, TimeoutError):
                time.sleep(0.25)
        else:
            raise RuntimeError(
                f"Server at {origin} failed readiness (exit={process.poll()})"
            )
        yield
    finally:
        if process.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def run(root, tmp):
    stage(root, tmp)
    api, web = tmp / "apps/api", tmp / "apps/web"
    sys.path.insert(0, str(api / "tests"))
    from parking_model import CORRECTION_TEXT, PARKING_POLICY, PARKING_TEXT

    fixture = tmp / "parking.md"
    fixture.write_text(PARKING_TEXT)
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    api_origin = f"http://127.0.0.1:{api_port}"
    web_origin = f"http://127.0.0.1:{web_port}"
    env = {
        k: os.environ[k] for k in ("HOME", "PATH", "TMPDIR", "LANG") if k in os.environ
    }
    env.update(
        APP_ENV="development",
        AUTH_MODE="legacy",
        AUTH_SECRET=secrets.token_hex(32),
        DATABASE_URL=f"sqlite:///{tmp / 'acceptance.db'}",
        AUTO_CREATE_TABLES="false",
        OPENAI_API_KEY="fixture-only",
        OPENAI_BASE_URL=api_origin + "/unused-provider",
        WEB_URL=web_origin,
        API_URL=api_origin,
        NEXT_TELEMETRY_DISABLED="1",
        PYTHONPATH=os.pathsep.join(map(str, [api, api / "tests", HERE])),
        PYTHONDONTWRITEBYTECODE="1",
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api,
        env=env,
        check=True,
    )
    uvicorn = [
        sys.executable,
        "-m",
        "uvicorn",
        "fixture_api:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
        "--no-access-log",
    ]
    next_cli = tmp / "node_modules/next/dist/bin/next"
    next_dev = [
        "node",
        next_cli,
        "dev",
        "--webpack",
        "-H",
        "127.0.0.1",
        "-p",
        str(web_port),
    ]
    with server(uvicorn, api, env, api_origin), server(next_dev, web, env, web_origin):
        browser_env = env | {
            k: os.environ[k]
            for k in ("E2E_PLAYWRIGHT", "E2E_BROWSER", "PLAYWRIGHT_BROWSERS_PATH")
            if k in os.environ
        }
        browser_env["NODE_PATH"] = str(tmp / "node_modules")
        scenario = [
            "node",
            HERE / "acceptance.cjs",
            web_origin,
            fixture,
            PARKING_POLICY,
            CORRECTION_TEXT,
        ]
        subprocess.run(scenario, cwd=tmp, env=browser_env, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-root", type=Path, default=HERE.parents[1], help="Integrated Git checkout"
    )
    root = parser.parse_args().app_root.resolve()
    with tempfile.TemporaryDirectory(prefix="galvanise-browser-") as folder:
        run(root, Path(folder))
