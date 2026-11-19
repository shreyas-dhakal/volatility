"""Dependency-free replay entry point. Runs entirely inside a disposable container."""

import contextlib
import importlib.util
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 256_000


def values(entry):
    return {item["name"]: json.loads(item["json_value"]) for item in entry["values"]}


def payload(raw):
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        return raw.decode("utf-8", errors="replace")


def receiver(events, replies):
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                self.send_error(413)
                events.append(
                    {
                        "error": "Request body exceeded the receiver limit or used unsupported streaming"
                    }
                )
                return
            raw = self.rfile.read(size)
            events.append(
                {
                    "method": self.command,
                    "destination": self.headers["Host"] + self.path,
                    "payload": payload(raw) if raw else None,
                }
            )
            reply = replies.get(
                self.command + " " + self.path, {"status": 200, "body": {}}
            )
            self.send_response(reply["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply["body"]).encode())

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = (
            handle_request
        )

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", 18765), Handler)


def local_environment(state):
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(state),
        "TMPDIR": str(state),
        "GALVANISE_REPLAY_DB": str(state / "replay.sqlite3"),
        "GALVANISE_REPLAY_RECEIVER": "http://127.0.0.1:18765",
        "GALVANISE_REPLAY_REDIS": "redis://127.0.0.1:16379/0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def load_hooks():
    spec = importlib.util.spec_from_file_location("migration_hooks", "/hooks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def database(env, targets):
    def identifier(name):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(
                "SQLite observation needs simple table and field identifiers"
            )
        return '"' + name + '"'

    path = Path(env["GALVANISE_REPLAY_DB"])
    if not path.is_file():
        raise ValueError(
            "The app did not create the configured disposable SQLite database"
        )
    with contextlib.closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        result = {}
        for target in targets:
            fields = target["fields"]
            query = "SELECT " + (",".join(map(identifier, fields)) if fields else "*")
            rows = db.execute(
                query + " FROM " + identifier(target["target"]) + " LIMIT 1001"
            )
            data = [dict(row) for row in rows]
            if len(data) > 1000:
                raise ValueError("SQLite observation exceeded 1000 rows")
            result[target["target"]] = sorted(
                data, key=lambda row: json.dumps(row, sort_keys=True)
            )
        return result


class RedisObserver:
    """Observe actual enqueue commands even when a worker consumes every message."""

    def __init__(self):
        self.events = []
        self.ready = threading.Event()
        self.barrier = threading.Event()
        self.error = False

    def monitor(self):
        try:
            with socket.create_connection(("127.0.0.1", 16379), timeout=2) as conn:
                conn.settimeout(None)
                conn.sendall(b"*1\r\n$7\r\nMONITOR\r\n")
                with conn.makefile("r") as lines:
                    if lines.readline().strip() != "+OK":
                        raise RuntimeError("Redis MONITOR failed")
                    self.ready.set()
                    for line in lines:
                        args = shlex.split(line.partition("] ")[2])
                        if not args:
                            continue
                        command, *parts = args
                        command = command.casefold()
                        if command == "echo" and parts == [
                            "galvanise-observer-barrier"
                        ]:
                            self.barrier.set()
                        if (
                            command
                            in {"publish", "lpush", "rpush", "xadd", "lpushx", "rpushx"}
                            and len(parts) >= 2
                        ):
                            entries = [parts[1:]] if command == "xadd" else parts[1:]
                            self.events.extend(
                                {
                                    "command": command,
                                    "destination": parts[0],
                                    "payload": item,
                                }
                                for item in entries
                            )
        except (OSError, ValueError, RuntimeError):
            self.error = True
            self.ready.set()

    def capture(self, targets):
        self.barrier.clear()
        with socket.create_connection(("127.0.0.1", 16379), timeout=2) as conn:
            conn.sendall(b"*2\r\n$4\r\nECHO\r\n$26\r\ngalvanise-observer-barrier\r\n")
        if not self.barrier.wait(2) or self.error:
            raise ValueError("Redis queue observer lost its connection")
        destinations = {row["target"] for row in targets}
        requests = [
            item
            for item in self.events
            if not destinations or item["destination"] in destinations
        ]
        return {"count": len(requests), "requests": requests}


def select_observations(scenario, kind):
    return [row for row in scenario["observe"] if row["kind"] == kind]


def invoke(entry, data, env):
    if "argv" in entry:
        proc = subprocess.run(
            entry["argv"],
            input=json.dumps(data).encode(),
            capture_output=True,
            check=False,
            timeout=25,
            env=env,
        )
        if len(proc.stdout) > MAX_BODY:
            raise ValueError("Command response exceeded the capture limit")
        return {"status": proc.returncode, "body": payload(proc.stdout)}
    path = entry["path"]
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("HTTP adapter path must be relative to the local app")
    method = entry["method"].upper()
    body = json.dumps(data).encode()
    if method in ("GET", "HEAD"):
        query = urllib.parse.urlencode(data, doseq=True)
        if query:
            path += ("&" if "?" in path else "?") + query
        body = None
    request = urllib.request.Request(
        f"http://127.0.0.1:{entry['port']}{path}",
        method=method,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=25)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError("HTTP response exceeded the capture limit")
        return {"status": response.status, "body": payload(raw)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run(config, scenario):
    os.chdir("/source")
    state = Path("/state")
    env = local_environment(state)
    os.environ.clear()
    os.environ.update(env)
    hooks = load_hooks()
    outbound = []
    sink = receiver(outbound, config["replies"])
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    queue = None
    if config["redis"]:
        subprocess.Popen(
            [
                "redis-server",
                "--port",
                "16379",
                "--bind",
                "127.0.0.1",
                "--appendonly",
                "no",
                "--save",
                "",
            ],
            stdout=sys.stderr,
            env=env,
        )
        for attempt in range(30):
            try:
                with socket.create_connection(("127.0.0.1", 16379), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise ValueError("Disposable Redis did not start")
        queue = RedisObserver()
        threading.Thread(target=queue.monitor, daemon=True).start()
        if not queue.ready.wait(2) or queue.error:
            raise ValueError("Redis MONITOR did not start")
    if hasattr(hooks, "reset"):
        hooks.reset(env)
    for fixture in scenario["seed"]:
        hooks.seed(fixture["fixture"], values(fixture), env)
    if hasattr(hooks, "start"):
        hooks.start(env)
    rows = select_observations(scenario, "database")

    def observe_db():
        if not rows:
            return {}
        if hasattr(hooks, "observe_db"):
            return hooks.observe_db(rows, env)
        return database(env, rows) if config["sqlite"] else None

    queue_targets = select_observations(scenario, "messages")
    job_targets = select_observations(scenario, "jobs")
    has_messages = queue_targets or queue or hasattr(hooks, "observe_messages")
    has_jobs = job_targets or hasattr(hooks, "observe_jobs")

    def messages():
        if hasattr(hooks, "observe_messages"):
            return hooks.observe_messages(queue_targets, env)
        return queue.capture(queue_targets) if queue else None

    def jobs():
        return (
            hooks.observe_jobs(job_targets, env)
            if hasattr(hooks, "observe_jobs")
            else None
        )

    result = {"initial": observe_db(), "steps": []}
    if has_messages:
        result["initial_messages"] = messages()
    if has_jobs:
        result["initial_jobs"] = jobs()
    if queue:
        queue.events.clear()
    outbound.clear()
    for step in scenario["steps"]:
        entry = config["entries"][step["input"]]
        data = values(step)
        response = (
            hooks.invoke(step["input"], entry, data, env)
            if hasattr(hooks, "invoke")
            else invoke(entry, data, env)
        )
        drained = hooks.drain(env) if hasattr(hooks, "drain") else None
        observed = {
            "response": response,
            "database": observe_db() if rows else {},
            "http": {"count": len(outbound), "requests": list(outbound)}
            if config["capture_http"]
            else None,
        }
        if any("error" in event for event in outbound):
            raise ValueError("An outbound request could not be fully captured")
        if has_messages:
            observed["messages"] = messages()
        if has_jobs:
            observed["jobs"] = jobs()
        if job_targets or hasattr(hooks, "drain"):
            observed["drain"] = drained
        result["steps"].append(observed)
    return result


if __name__ == "__main__":
    try:
        args = json.loads(Path("/input.json").read_text())
        # Hook subprocess output goes to stderr, leaving a single JSON value on stdout.
        with contextlib.redirect_stdout(sys.stderr):
            result = run(args["config"], args["scenario"])
        print(json.dumps({"observation": result}, allow_nan=False))
    except Exception as exc:  # noqa: BLE001 - project hooks use arbitrary libraries
        print(json.dumps({"gap": f"{type(exc).__name__}: {exc}"[:750]}))
