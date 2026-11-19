"""Replay a downloaded, approved workflow artifact with the local operator registry."""

import argparse
import asyncio
import json
from pathlib import Path

from galvanise.migration import runner
from galvanise.migration.compare import compare, replacement_scenario, rules_for
from galvanise.migration.jobs import compare_target
from galvanise.migration.schemas import Suite


async def replay(bundle, scenario_name=None, *, recapture=False, smallest=False):
    if bundle.get("format") != "galvanise-workflow-replay/v1":
        raise runner.SetupGap("Expected a Galvanise workflow replay v1 export.")
    Suite.model_validate({"scenarios": bundle["scenarios"]})
    artifact = dict(bundle)
    if scenario_name:
        scenarios = [s for s in artifact["scenarios"] if s["name"] == scenario_name]
        if not scenarios:
            raise runner.SetupGap("The named scenario is not in this export.")
        artifact["scenarios"] = scenarios
    replacement = artifact.get("replacement")
    if replacement and not recapture:
        adapter = runner.get_variant(
            artifact["project_id"], "target", replacement["target"]
        )
        if (adapter["commit"], adapter["fingerprint"]) != (
            replacement["target_commit"],
            replacement["target_adapter"],
        ):
            raise runner.SetupGap(
                "The target Git ref, image, hooks or protocol differ from the replay export."
            )
        if smallest:
            if not scenario_name:
                raise runner.SetupGap(
                    "Choose a scenario when replaying the smallest recorded reproduction."
                )
            case = next(
                (
                    s
                    for s in replacement.get("reproductions", [])
                    if s["name"] == scenario_name
                ),
                None,
            )
            if not case:
                raise runner.SetupGap(
                    "This report does not contain a verified reduced reproduction."
                )
            observed = await asyncio.to_thread(
                runner.capture,
                adapter,
                replacement_scenario(case["scenario"], replacement["mappings"]),
                replacement["patch"],
            )
            return [
                {
                    "name": scenario_name,
                    **compare(
                        case["legacy"],
                        observed,
                        rules_for(artifact["rules"], scenario_name),
                        replacement["mappings"],
                    ),
                    "legacy": case["legacy"],
                    "replacement": observed,
                }
            ]
        return await compare_target(
            adapter,
            artifact,
            replacement["mappings"],
            replacement["patch"],
            minimize=False,
        )
    adapter = runner.get_variant(artifact["project_id"], "legacy")
    if (adapter["commit"], adapter["fingerprint"]) != (
        artifact["source_commit"],
        artifact["adapter_fingerprint"],
    ):
        raise runner.SetupGap(
            "The legacy Git ref, image, hooks or protocol differ from the replay export."
        )
    old = {item["name"]: item["first"] for item in artifact["captures"]}
    rows = []
    for scenario in artifact["scenarios"]:
        current = await asyncio.to_thread(runner.capture, adapter, scenario)
        rows.append(
            {
                "name": scenario["name"],
                **compare(
                    old[scenario["name"]],
                    current,
                    rules_for(artifact["rules"], scenario["name"]),
                ),
                "legacy": old[scenario["name"]],
                "replayed": current,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--scenario")
    parser.add_argument(
        "--legacy", action="store_true", help="Replay the approved legacy commit"
    )
    parser.add_argument(
        "--smallest", action="store_true", help="Replay the recorded reduced scenario"
    )
    args = parser.parse_args()
    try:
        bundle = json.loads(args.artifact.read_text())
        rows = asyncio.run(
            replay(bundle, args.scenario, recapture=args.legacy, smallest=args.smallest)
        )
    except (runner.SetupGap, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "not_run", "setup": str(exc)}))
        return 2
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    if any(row["status"] == "different" for row in rows):
        return 1
    return 2 if any(row["status"] != "match" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
