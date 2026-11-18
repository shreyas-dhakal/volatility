"""Launcher regression: do not bind Next to a different origin than WEB_URL."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "galvanise_dev", Path(__file__).parents[3] / "scripts/dev.py"
)
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


def test_next_binds_to_web_url_hostname_instead_of_hardcoded_ipv4(monkeypatch):
    calls = []

    class Child:
        pid = 999999
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def setsockopt(self, *args):
            pass

        def bind(self, *args):
            pass

    monkeypatch.setattr(dev.socket, "socket", Probe)
    monkeypatch.setenv("WEB_URL", "http://localhost:3091")
    monkeypatch.setattr(dev.shutil, "which", lambda _: "/synthetic/tool")
    monkeypatch.setattr(dev, "run", lambda *a, **kw: None)
    monkeypatch.setattr(
        dev.subprocess, "Popen", lambda args, **kw: calls.append(args) or Child()
    )
    monkeypatch.setattr(dev.signal, "signal", lambda *a: None)
    monkeypatch.setattr(dev, "env_value", lambda name, default: "http://localhost:3091")
    monkeypatch.setattr(dev.Path, "exists", lambda _: True)
    monkeypatch.setattr("sys.argv", ["dev.py", "--skip-db", "--api-port", "18091"])
    import pytest

    with pytest.raises(SystemExit):
        dev.main()
    command = next(c for c in calls if c[0] == "npm")
    assert command[command.index("--hostname") + 1] == "localhost"
