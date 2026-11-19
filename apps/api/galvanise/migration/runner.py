"""Resolve operator-owned replay adapters and run a tracked Git snapshot without networking."""

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import tarfile
import time
from contextlib import suppress
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4

from galvanise.config import settings
from galvanise.services.ingestion import extract, redact

GUEST = Path(__file__).with_name("guest.py")
SECRETS = re.compile(
    r"(?:^|/)(?:(?:\.aws|\.ssh|\.git)(?:/|$)|(?:\.env(?:\..*)?|\.npmrc|\.netrc|\.gitconfig|credentials(?:\.[^/]+)?|[^/]+\.(?:pem|key|p12|pfx))$)",
    re.IGNORECASE,
)
REVISION = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
MAX_OUTPUT = 2_000_000


class SetupGap(ValueError):
    pass


def operator_config(project_id):
    if not settings.workflow_migration_config:
        return {}
    try:
        path = Path(settings.workflow_migration_config).resolve(strict=True)
        config = json.loads(path.read_text())
        entry = config["projects"].get(project_id, {})
        if not isinstance(entry, dict) or not isinstance(
            entry.get("targets", {}), dict
        ):
            raise TypeError
        return entry
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SetupGap(
            "The operator migration registry must be a readable JSON object keyed by project ID."
        ) from exc


def command(args, *, env=None, timeout=15, cwd=None, data=None):
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            input=data,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupGap(
            f"{args[0]} is unavailable or exceeded its execution limit."
        ) from exc
    if proc.returncode:
        process_failure(args, proc.returncode, proc.stderr)
    return proc.stdout


def process_failure(args, status, error):
    stderr = error.decode(errors="replace").casefold()
    if Path(args[0]).name == "docker":
        if "mount" in stderr or "bind source path" in stderr:
            raise SetupGap(
                "Docker cannot mount the replay inputs. Configure WORKFLOW_MIGRATION_SCRATCH on a Docker-shared directory."
            )
        if "daemon" in stderr or "docker api" in stderr:
            raise SetupGap(
                "Start the Docker daemon and grant the API worker access to it."
            )
        if (
            "no such image" in stderr
            or "not found" in stderr
            and args[1:3] == ["image", "inspect"]
        ):
            raise SetupGap(
                "The configured replay image is missing from the local Docker engine."
            )
    raise SetupGap(
        f"{args[0]} exited with status {status}. Check operator configuration."
    )


def docker_output(args):
    expires = time.monotonic() + 85
    output, errors = bytearray(), bytearray()
    try:
        with subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ) as proc:
            try:
                with selectors.DefaultSelector() as streams:
                    streams.register(proc.stdout, selectors.EVENT_READ, output)
                    streams.register(proc.stderr, selectors.EVENT_READ, errors)
                    while streams.get_map():
                        remaining = expires - time.monotonic()
                        if remaining <= 0:
                            raise SetupGap(
                                "The disposable replay container exceeded its 85 second time limit."
                            )
                        for stream, _ in streams.select(remaining):
                            content = os.read(stream.fd, 65_536)
                            if not content:
                                streams.unregister(stream.fileobj)
                            elif stream.data is output or len(errors) < 8_192:
                                stream.data.extend(content)
                            if len(output) > MAX_OUTPUT:
                                raise SetupGap(
                                    "Replay observations exceeded the 2 MB capture limit."
                                )
                status = proc.wait(timeout=max(0, expires - time.monotonic()))
                if status:
                    process_failure(args, status, errors)
            finally:
                if proc.poll() is None:
                    proc.kill()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupGap(
            "Docker is unavailable or the replay container exceeded its time limit."
        ) from exc
    return output


def git(repo, *args, timeout=15, dates=None):
    return command(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
        env={
            "PATH": os.defpath + ":/opt/homebrew/bin",
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "file",
            **(dates or {}),
        },
        timeout=timeout,
    )


def digest(content):
    return hashlib.sha256(content).hexdigest()


def get_variant(project_id, variant, target=None):
    config = operator_config(project_id)
    if variant == "legacy":
        raw = config.get("legacy")
    else:
        raw = config.get("targets", {}).get(target)
    label = "legacy" if variant == "legacy" else f"target {target}"
    if not isinstance(raw, dict):
        raise SetupGap(f"Register a {label} replay adapter for project {project_id}.")
    try:
        repo = Path(raw["repo"]).expanduser().resolve(strict=True)
        hooks = Path(raw["hooks"]).expanduser().resolve(strict=True)
        image = raw["image"]
        if not repo.is_dir() or not hooks.is_file() or not image:
            raise ValueError
        entries = raw["entries"]
        if not isinstance(entries, dict) or not entries:
            raise ValueError
        if any(
            not isinstance(entry, dict)
            or (
                not isinstance(entry.get("argv"), list) or not entry["argv"]
                if "argv" in entry
                else not {"path", "method", "port"} <= entry.keys()
            )
            for entry in entries.values()
        ):
            raise ValueError
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise SetupGap(
            f"The {label} adapter needs a local Git repository, a hooks file, an image and logical entry points."
        ) from exc
    ref = raw.get("ref", "")
    if not isinstance(ref, str) or not ref or ref.startswith("-"):
        raise SetupGap(f"Set the {label} adapter's Git ref.")
    if variant == "legacy" and not REVISION.fullmatch(ref):
        raise SetupGap(
            "Pin the legacy adapter ref to the full Git commit ID represented by the source snapshot."
        )
    revision = git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
    raw_image = command(["docker", "image", "inspect", image, "--format", "{{json .}}"])
    image_info = json.loads(raw_image)
    image_id = image_info["Id"]
    image_env = (image_info.get("Config") or {}).get("Env") or []
    credentials = re.compile(
        r"(?i)(?:password|password_file|passwd|secret|token|api_key|credentials)"
    )
    if any(
        credentials.search(item.split("=", 1)[0]) and item.split("=", 1)[-1]
        for item in image_env
    ):
        raise SetupGap("Remove credential environment variables from the runner image.")
    guest_config = {
        "entries": entries,
        "replies": raw.get("replies", {}),
        "sqlite": raw.get("sqlite", False),
        "redis": raw.get("redis", False),
        "capture_http": raw.get("capture_http", False),
    }
    return {
        **raw,
        "repo": repo,
        "hooks": hooks,
        "commit": revision,
        "image_id": image_id,
        "tree": git(repo, "rev-parse", revision + "^{tree}").decode().strip(),
        "protocol": guest_config,
        "fingerprint": digest(
            json.dumps(
                [
                    image_id,
                    guest_config,
                    digest(hooks.read_bytes()),
                    digest(GUEST.read_bytes()),
                ],
                sort_keys=True,
            ).encode()
        ),
    }


def scenario_setup(adapter, scenarios):
    missing = set()
    for scenario in scenarios:
        for step in scenario["steps"]:
            if step["input"] not in adapter["protocol"]["entries"]:
                missing.add(
                    f"{scenario['name']}: register logical input {step['input']!r}."
                )
    if missing:
        raise SetupGap(" ".join(sorted(missing)))


def checkout(repo, commit, work, patch=None):
    archive = work.parent / "source.tar"
    git(repo, "archive", "--format=tar", "--output=" + str(archive), commit, timeout=45)
    work.mkdir()
    with tarfile.open(archive) as tar:
        members = []
        total = 0
        for member in tar:
            if member.issym() or member.islnk() or SECRETS.search(member.name):
                continue
            total += member.size
            if total > 100_000_000:
                raise SetupGap("The tracked source snapshot exceeds 100 MB.")
            members.append(member)
        tar.extractall(work, members=members, filter="data")
    if patch:
        try:
            command(
                ["git", "apply", "--whitespace=nowarn", "-"],
                cwd=work,
                env={
                    "PATH": os.defpath + ":/opt/homebrew/bin",
                    "HOME": "/nonexistent",
                    "GIT_CEILING_DIRECTORIES": str(work.parent),
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                },
                data=patch.encode(),
            )
        except SetupGap as exc:
            raise SetupGap(
                "The replacement patch does not apply to the configured target revision."
            ) from exc
    for root, dirs, files in os.walk(work):
        for path in [*dirs, *files]:
            item = Path(root) / path
            if item.is_symlink() or SECRETS.search(item.relative_to(work).as_posix()):
                raise SetupGap(
                    "Remove symlinks and credential files from the replay checkout."
                )
    archive.unlink()


def capture(adapter, scenario, patch=None):
    scenario_setup(adapter, [scenario])
    docker = shutil.which("docker")
    if docker is None:
        raise SetupGap("Install Docker on the migration worker.")
    # Docker Desktop and Colima generally share the home directory on macOS.
    scratch = settings.workflow_migration_scratch or (
        str(Path.home()) if sys.platform == "darwin" else None
    )
    with TemporaryDirectory(prefix="galvanise-replay-", dir=scratch) as temp:
        work = Path(temp)
        source = work / "source"
        checkout(adapter["repo"], adapter["commit"], source, patch)
        hooks = work / "hooks.py"
        hooks.write_bytes(adapter["hooks"].read_bytes())
        protocol = work / "input.json"
        protocol.write_text(
            json.dumps({"config": adapter["protocol"], "scenario": scenario})
        )
        name = "galvanise-replay-" + uuid4().hex
        args = [
            docker,
            "run",
            "--pull=never",
            "--rm",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--pids-limit=128",
            "--memory=1g",
            "--cpus=2",
            "--log-driver=none",
            "--tmpfs",
            "/state:rw,nosuid,nodev,mode=1777,size=256m",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,mode=1777,size=128m",
        ]
        for host, guest in [
            (source, "/source"),
            (hooks, "/hooks.py"),
            (protocol, "/input.json"),
            (GUEST, "/guest.py"),
        ]:
            args += ["--mount", f"type=bind,source={host},target={guest},readonly"]
        args += ["--entrypoint", "python3", adapter["image_id"], "-I", "/guest.py"]
        # The image is operator-owned. No host or API environment is copied into the guest.
        try:
            output = docker_output(args)
        finally:
            with suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run(
                    [docker, "rm", "-f", name],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
        try:
            outcome = json.loads(output)
        except (ValueError, UnicodeError) as exc:
            raise SetupGap(
                "Replay adapter did not return valid JSON observations."
            ) from exc
        if "gap" in outcome:
            raise SetupGap(redact(outcome["gap"]))
        # Preserve primitive types and order. Hooks must operate on synthetic fixture data.
        return outcome["observation"]


def bind_sources(adapter, manifest, writes):
    """Verify that the execution commit contains selected immutable repository source blobs."""
    if not writes:
        raise SetupGap("Select at least one source-backed legacy write before replay.")
    sources = {item["id"]: item for item in manifest}
    selected = {item["location"].get("source_id") for item in writes}
    if None in selected or selected - sources.keys():
        raise SetupGap(
            "Refresh the migration source selection to resolve its frozen source files."
        )
    archive_uploads = {sources[key].get("upload_id") for key in selected} - {None}
    to_verify = [
        item
        for item in manifest
        if item["id"] in selected
        or (
            item.get("upload_id") in archive_uploads
            and item.get("kind") == "code"
            and item.get("status") == "analyzed"
        )
    ]
    for row in to_verify:
        path = row["path"]
        prefix = adapter.get("source_prefix", "").strip("/")
        local = path
        if prefix and row.get("archive"):
            prefix_path = PurePosixPath(prefix)
            try:
                local = PurePosixPath(path).relative_to(prefix_path).as_posix()
            except ValueError as exc:
                raise SetupGap(
                    "The archive source is outside the configured source_prefix: "
                    + path
                ) from exc
        try:
            name = adapter["commit"] + ":" + local
            if row.get("git_blob"):
                actual = (
                    git(adapter["repo"], "rev-parse", "--verify", name).decode().strip()
                )
                matches = actual == row["git_blob"]
            else:
                actual = extract(git(adapter["repo"], "show", name), path)
                matches = digest(actual.encode()) == row["content_hash"]
        except (SetupGap, KeyError, UnicodeError, ValueError) as exc:
            raise SetupGap(
                "Cannot verify frozen source against the configured legacy Git commit: "
                + path
            ) from exc
        if not matches:
            raise SetupGap(
                "The configured legacy Git revision differs from selected source "
                + path
                + "."
            )
        if row.get("git_tree") and adapter["tree"] != row["git_tree"]:
            raise SetupGap(
                "The configured legacy Git tree differs from the saved source snapshot."
            )
