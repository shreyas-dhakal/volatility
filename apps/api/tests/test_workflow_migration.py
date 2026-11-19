from galvanise.migration.compare import compare


def observation(count, *, value="created", available=True):
    return {
        "steps": [
            {
                "response": {"status": 200},
                "database": {"orders": [{"state": value}]},
                "http": {
                    "count": count,
                    "requests": [{"destination": "/billing"}] * count,
                }
                if available
                else None,
            }
        ],
        "initial": {},
    }


def test_duplicate_outbound_requests_fail_even_with_identical_response_and_database():
    result = compare(observation(1), observation(2))
    assert result["status"] == "different"
    assert result["first"]["path"] == "/steps/0/http/count"
    assert result["first"]["legacy"] == 1
    assert result["first"]["replacement"] == 2


def test_missing_observer_is_unknown_even_if_both_sides_are_missing():
    data = observation(0, available=False)
    assert compare(data, data)["status"] == "unknown"


def test_id_rule_preserves_aliasing_between_database_and_request():
    old = {"initial": {}, "steps": [{"response": {"id": "old"}, "http": {"id": "old"}}]}
    new = {
        "initial": {},
        "steps": [{"response": {"id": "new"}, "http": {"id": "mismatch"}}],
    }
    rules = [
        {"path": "/steps/0/response/id", "kind": "id", "reason": "Generated order ID"},
        {"path": "/steps/0/http/id", "kind": "id", "reason": "Same generated order ID"},
    ]
    assert compare(old, new, rules)["status"] == "different"
    new["steps"][0]["http"]["id"] = "new"
    assert compare(old, new, rules)["status"] == "match"


def test_real_replay_preserves_response_and_database_but_detects_duplicate_request(
    tmp_path,
    monkeypatch,
):
    import os
    import subprocess

    import pytest

    from galvanise.migration import runner

    image = os.environ.get("GALVANISE_TEST_REPLAY_IMAGE")
    if not image:
        pytest.skip("Set GALVANISE_TEST_REPLAY_IMAGE to a local Python Docker image")
    use_redis = os.environ.get("GALVANISE_TEST_REPLAY_REDIS") == "1"
    repo = tmp_path / "repo"
    repo.mkdir()
    hooks = tmp_path / "hooks.py"
    hooks.write_text(
        """
import sqlite3

def reset(env):
    with sqlite3.connect(env["GALVANISE_REPLAY_DB"]) as db:
        db.execute("create table orders (number int, state text)")

def seed(fixture, data, env):
    assert fixture == "order"
    with sqlite3.connect(env["GALVANISE_REPLAY_DB"]) as db:
        db.execute("insert into orders values (?, 'pending')", (data["number"],))
"""
    )
    service = repo / "purchase.py"
    source = """
import json, os, sqlite3, sys, urllib.request
data = json.load(sys.stdin)
with sqlite3.connect(os.environ["GALVANISE_REPLAY_DB"]) as db:
    db.execute("update orders set state='paid' where number=?", (data["number"],))
for _ in range(1):
    with urllib.request.urlopen(os.environ["GALVANISE_REPLAY_RECEIVER"] + "/billing",
                                data=json.dumps(data).encode()) as reply:
        assert reply.status == 200
print(json.dumps({"state": "paid"}))
"""
    if use_redis:
        source += """
import subprocess
subprocess.run(["redis-cli", "-p", "16379", "RPUSH", "billing-jobs", json.dumps(data)],
               check=True, stdout=subprocess.DEVNULL)
"""
        with hooks.open("a") as hook_file:
            hook_file.write("""
import subprocess

def drain(env):
    payload = subprocess.check_output(["redis-cli", "-p", "16379", "LPOP", "billing-jobs"])
    return {"consumed": 1 if payload.strip() else 0}

def observe_jobs(targets, env):
    pending = subprocess.check_output(["redis-cli", "-p", "16379", "LLEN", "billing-jobs"])
    return {"pending": int(pending)}
""")
    service.write_text(source)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "purchase.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "Legacy test fixture",
        ],
        check=True,
    )
    commit = runner.git(repo, "rev-parse", "HEAD").decode().strip()
    service.write_text(source.replace("range(1)", "range(2)"))
    patch = runner.git(repo, "diff").decode()
    image_id = (
        runner.command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        .decode()
        .strip()
    )
    adapter = {
        "repo": repo,
        "hooks": hooks,
        "commit": commit,
        "image_id": image_id,
        "protocol": {
            "entries": {"purchase": {"argv": ["python3", "purchase.py"]}},
            "sqlite": True,
            "redis": use_redis,
            "capture_http": True,
            "replies": {},
        },
    }
    data = [{"name": "number", "json_value": "9"}]
    scenario = {
        "name": "purchase",
        "seed": [{"fixture": "order", "values": data}],
        "steps": [{"input": "purchase", "values": data}],
        "observe": [
            {"kind": "database", "target": "orders", "fields": ["number", "state"]}
        ],
    }
    if use_redis:
        scenario["observe"] += [
            {"kind": "messages", "target": "billing-jobs", "fields": []},
            {"kind": "jobs", "target": "billing-jobs", "fields": []},
        ]
    legacy = runner.capture(adapter, scenario)
    if use_redis:
        assert legacy["initial_messages"] == {"count": 0, "requests": []}
        assert legacy["steps"][0]["messages"] == {
            "count": 1,
            "requests": [
                {
                    "command": "rpush",
                    "destination": "billing-jobs",
                    "payload": '{"number": 9}',
                }
            ],
        }
        assert legacy["steps"][0]["drain"] == {"consumed": 1}
        assert legacy["steps"][0]["jobs"] == {"pending": 0}
    assert compare(legacy, runner.capture(adapter, scenario))["status"] == "match"
    replacement = runner.capture(adapter, scenario, patch)
    assert legacy["initial"] == replacement["initial"]
    assert legacy["steps"][0]["database"] == replacement["steps"][0]["database"]
    assert legacy["steps"][0]["response"] == replacement["steps"][0]["response"]
    assert (
        replacement["steps"][0]["http"]["requests"]
        == [
            {
                "method": "POST",
                "destination": "127.0.0.1:18765/billing",
                "payload": {"number": 9},
            }
        ]
        * 2
    )
    assert compare(legacy, replacement)["first"] == {
        "path": "/steps/0/http/count",
        "legacy": 1,
        "replacement": 2,
    }

    runner.git(repo, "add", "purchase.py")
    runner.git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "Replacement test fixture",
    )
    verify_persisted_workflow(
        monkeypatch, tmp_path, repo, hooks, image, commit, source, scenario, use_redis
    )


def verify_persisted_workflow(
    monkeypatch, tmp_path, repo, hooks, image, commit, source, scenario, use_redis
):
    import asyncio
    import json

    from auth_helpers import authenticate_as
    from fastapi.testclient import TestClient

    from galvanise.config import settings
    from galvanise.database import Base, SessionLocal, engine
    from galvanise.design_engine.sources import store
    from galvanise.main import app
    from galvanise.migration import jobs, replay, runner
    from galvanise.models import DesignChunk, DesignRevision, Project

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        owner = authenticate_as(client, "docker-replay@example.test")
        with SessionLocal() as db:
            project = Project(user_id=owner.id, name="Replay", system_type="existing")
            db.add(project)
            db.flush()
            source_id = store(
                db,
                project.id,
                "legacy/purchase.py",
                {"kind": "code", "path": "purchase.py", "archive": "legacy.zip"},
                [({}, source)],
            )
            db.flush()
            chunk = db.query(DesignChunk).filter_by(source_id=source_id).one()
            revision = DesignRevision(
                project_id=project.id,
                source_ids=[source_id],
                diff_json={},
                snapshot_json={
                    "use_cases": [
                        {
                            "id": "purchase",
                            "name": "Purchase",
                            "basis": "observed",
                            "evidence": [
                                {"chunk_id": chunk.id, "excerpt": "update orders"}
                            ],
                        }
                    ]
                },
            )
            db.add(revision)
            db.commit()
        configuration = tmp_path / "registry.json"
        legacy_adapter = {
            "repo": str(repo),
            "ref": commit,
            "hooks": str(hooks),
            "image": image,
            "entries": {"purchase": {"argv": ["python3", "purchase.py"]}},
            "sqlite": True,
            "redis": use_redis,
            "capture_http": True,
        }
        configuration.write_text(
            json.dumps(
                {
                    "projects": {
                        project.id: {
                            "legacy": legacy_adapter,
                            "targets": {"local": {**legacy_adapter, "ref": "HEAD"}},
                        }
                    }
                }
            )
        )
        monkeypatch.setattr(settings, "workflow_migration_config", str(configuration))
        path = f"/api/projects/{project.id}/workflow-migrations/{revision.id}/purchase"
        source_response = client.get(path + "/sources").json()
        write = next(
            item for item in source_response["writes"] if item.get("field") == "state"
        )
        assert (
            client.put(
                path + "/selection", json={"query": "", "selected": [write["id"]]}
            ).status_code
            == 200
        )
        suite = {
            "scenarios": [
                {**scenario, "category": "normal", "evidence_ids": [chunk.id]}
            ]
        }
        assert client.put(path + "/scenarios", json=suite).status_code == 200
        queued = client.post(
            path + "/jobs",
            json={"action": "baseline", "request_id": "fixture-baseline"},
        )
        assert queued.status_code == 202
        asyncio.run(jobs.execute(*jobs.claim()))
        job_id = queued.json()["id"]
        capture = client.get(path + "/jobs/" + job_id).json()
        assert capture["status"] == "completed", capture
        assert capture["result"]["source_commit"] == commit
        assert capture["result"]["captures"][0]["stability"]["status"] == "match"
        approve = client.post(path + "/baseline", json={"capture_id": job_id})
        assert approve.status_code == 200, approve.text
        assert client.put(path + "/scenarios", json=suite).status_code == 409
        baseline = client.get(path + "/baseline/export").json()
        assert asyncio.run(replay.replay(baseline))[0]["status"] == "match"
        queued = client.post(
            path + "/jobs",
            json={
                "action": "compare",
                "request_id": "fixture-compare",
                "replacement": {"target": "local"},
            },
        )
        assert queued.status_code == 202, queued.text
        asyncio.run(jobs.execute(*jobs.claim()))
        target_job = queued.json()["id"]
        result = client.get(path + "/jobs/" + target_job).json()
        assert result["status"] == "completed", result
        assert (
            result["result"]["comparisons"][0]["first"]["path"] == "/steps/0/http/count"
        )
        bundle = client.get(path + "/jobs/" + target_job + "/replay").json()
        assert asyncio.run(replay.replay(bundle))[0]["status"] == "different"
        reduced = asyncio.run(replay.replay(bundle, "purchase", smallest=True))[0]
        assert reduced["first"]["path"] == "/steps/0/http/count"
        assert runner.get_variant(project.id, "legacy")["commit"] == commit


def test_business_mapping_aligns_only_database_fields_and_preserves_http():
    from galvanise.migration.compare import replacement_scenario, safe_mapping

    mappings = [
        {
            "legacy": "/database/orders/state",
            "replacement": "/database/orders/payment_state",
            "reason": "The replacement uses a qualified column name.",
        }
    ]
    assert safe_mapping(mappings[0]["legacy"], mappings[0]["replacement"])
    old = observation(1)
    new = observation(1)
    new["steps"][0]["database"]["orders"] = [{"payment_state": "created"}]
    assert compare(old, new, mappings=mappings)["status"] == "match"
    assert compare(old, new)["status"] == "different"
    scenario = {
        "observe": [{"kind": "database", "target": "orders", "fields": ["state"]}]
    }
    assert replacement_scenario(scenario, mappings)["observe"][0]["fields"] == [
        "payment_state"
    ]
    new["steps"][0]["http"]["count"] = 2
    assert (
        compare(old, new, mappings=mappings)["first"]["path"] == "/steps/0/http/count"
    )
    assert not safe_mapping("/steps/0/http/count", "/steps/0/http/total")


def test_migration_retains_actionable_not_run_job_and_authorizes_every_lookup(
    monkeypatch,
):
    import asyncio

    from auth_helpers import authenticate_as
    from fastapi.testclient import TestClient

    from galvanise.config import settings
    from galvanise.database import Base, SessionLocal, engine
    from galvanise.design_engine.sources import store
    from galvanise.main import app
    from galvanise.migration import jobs
    from galvanise.models import DesignChunk, DesignRevision, Project

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "workflow_migration_config", "")
    with TestClient(app) as client:
        owner = authenticate_as(client, "migration-owner@example.test")
        with SessionLocal() as db:
            project = Project(
                user_id=owner.id, name="Migration", system_type="existing"
            )
            db.add(project)
            db.flush()
            source_id = store(
                db,
                project.id,
                "legacy/checkout.sql",
                {"kind": "code", "path": "checkout.sql"},
                [
                    (
                        {},
                        "BEGIN;\nUPDATE orders SET payment_state = 'paid' WHERE id = 1;\nCOMMIT;",
                    )
                ],
            )
            trigger_id = store(
                db,
                project.id,
                "legacy/trigger.sql",
                {"kind": "code", "path": "trigger.sql"},
                [
                    (
                        {},
                        "CREATE TRIGGER after_purchase\nAFTER UPDATE ON orders\nFOR EACH ROW\nBEGIN\nCOMMIT;",
                    )
                ],
            )
            db.flush()
            chunk = db.query(DesignChunk).filter_by(source_id=source_id).one()
            revision = DesignRevision(
                project_id=project.id,
                source_ids=[source_id, trigger_id],
                diff_json={},
                snapshot_json={
                    "use_cases": [
                        {
                            "id": "purchase",
                            "name": "Purchase orders",
                            "basis": "observed",
                            "evidence": [
                                {"chunk_id": chunk.id, "excerpt": "UPDATE orders"}
                            ],
                        }
                    ]
                },
            )
            db.add(revision)
            db.commit()
        path = f"/api/projects/{project.id}/workflow-migrations/{revision.id}/purchase"
        assert client.get(path).json()["scenarios"] == []
        candidates = client.get(path + "/sources", params={"query": "orders"}).json()[
            "writes"
        ]
        write = next(row for row in candidates if row["field"] == "payment_state")
        assert write["transaction_evidence"]
        selection = client.put(
            path + "/selection", json={"query": "orders", "selected": [write["id"]]}
        )
        assert selection.status_code == 200
        assert any(
            row["kind"] == "scheduler / trigger" for row in selection.json()["reverse"]
        )
        request = {"action": "generate", "request_id": "generate-one"}
        queued = client.post(path + "/jobs", json=request)
        assert queued.status_code == 202
        job_id = queued.json()["id"]
        assert client.post(path + "/jobs", json=request).json()["id"] == job_id
        asyncio.run(jobs.execute(*jobs.claim()))
        job = client.get(path + "/jobs/" + job_id).json()
        assert job["status"] == "not_run"
        assert "OPENAI_API_KEY" in job["error"]
        assert client.get(path).json()["jobs"][0]["id"] == job_id
        authenticate_as(client, "other-migration-user@example.test")
        assert client.get(path).status_code == 404
        assert client.get(path + "/jobs/" + job_id).status_code == 404
