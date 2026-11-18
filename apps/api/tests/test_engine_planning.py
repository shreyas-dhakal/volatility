from copy import deepcopy

import pytest

from galvanise.design_engine.planning import plan


def person(id="p", **kwargs):
    return {"id": id, "availability": 1, "skills": ["engineering"], **kwargs}


def activity(id, effort, predecessors=(), **kwargs):
    return {
        "id": id,
        "deliverable": f"Deliver {id}",
        "predecessors": list(predecessors),
        "effort": {"likely": effort},
        "skills": ["engineering"],
        **kwargs,
    }


@pytest.fixture
def planning_inputs():
    return {
        "start_date": "2026-11-20",  # Friday
        "activities": [
            activity("a", 2),
            activity("b", 2),
            activity("join", 1, ["a", "b"]),
        ],
        "rosters": [
            {"id": "solo", "people": [person()]},
            {"id": "pair", "people": [person("q"), person()]},
            {"id": "unqualified", "people": [person(skills=["design"])]},
        ],
    }


def test_acceptance_schedules(planning_inputs):
    result = plan({}, planning_inputs)
    solo, pair, unqualified = result["runs"]
    assert solo["status"] == pair["status"] == "scheduled"
    assert solo["critical_path_days"] == pair["critical_path_days"] == 3
    assert solo["critical_path"] == pair["critical_path"] == ["a", "join"]
    assert solo["makespan_days"] == 5
    assert pair["makespan_days"] == 3
    assert solo["start_date"] == pair["start_date"] == "2026-11-20"
    assert solo["finish_date"] == "2026-11-26"
    assert pair["finish_date"] == "2026-11-24"
    assert solo["total_cost"] is pair["total_cost"] is None
    assert all(a["cost"] is None for a in solo["assignments"])
    assert [a["person_id"] for a in pair["assignments"]] == ["p", "q", "p"]
    assert [w["code"] for w in solo["warnings"]] == ["single_person_coverage"] * 3
    assert unqualified["status"] == "infeasible"
    assert unqualified["blockers"][0]["activity_id"] == "a"
    assert unqualified["blockers"][0]["skills"] == ["engineering"]
    assert unqualified["finish_date"] is None
    fixture = deepcopy(planning_inputs)
    fixture["activities"].reverse()
    fixture["rosters"][1]["people"].reverse()
    assert plan({}, fixture) == result


def test_generated_work_uses_contracts_for_parallel_implementation():
    evidence = [{"chunk_id": "chunk-1", "excerpt": "Charges vary"}]
    snapshot = {
        "components": [
            {"id": "a", "name": "Invoices", "owns": [], "use_case_ids": ["invoice"]},
            {"id": "b", "name": "Tax", "owns": ["v"], "evidence": evidence},
        ],
        "contracts": [
            {
                "id": "k",
                "name": "Tax calculation",
                "owner_id": "b",
                "operations": [{"id": "tax"}],
                "evidence": evidence,
            }
        ],
        "dependencies": [
            {
                "id": "d",
                "caller_id": "a",
                "callee_id": "b",
                "operation_id": "tax",
                "reason": "Calculate invoice tax",
            }
        ],
        "use_cases": [{"id": "invoice", "name": "Issue an invoice"}],
        "walkthroughs": [
            {"use_case_id": "invoice", "steps": [{"caller_id": "a", "callee_id": "b"}]}
        ],
    }
    result = plan(snapshot, {})
    activities = {a["id"]: a for a in result["activities"]}
    assert set(activities) == {
        "component:a",
        "component:b",
        "contract:k",
        "integration:d",
        "validation:invoice",
    }
    assert (
        activities["component:a"]["predecessors"]
        == activities["component:b"]["predecessors"]
        == ["contract:k"]
    )
    assert activities["contract:k"]["sources"] == evidence
    assert activities["component:b"]["related_ids"] == ["b", "v"]
    assert activities["integration:d"]["predecessors"] == ["component:a", "component:b"]
    assert activities["validation:invoice"]["predecessors"] == [
        "component:a",
        "component:b",
        "integration:d",
    ]
    assert activities["component:b"]["effort"]["likely"] is None
    assert result["runs"] == []
    assert {
        "activities.component:b.skills",
        "activities.component:b.effort.likely",
        "start_date",
        "rosters",
    } <= {m["path"] for m in result["missing_inputs"]}
    assert plan(snapshot, {"activities": result["activities"]}) == result


def test_fractional_capacity_cost_and_nonpreemptive_window():
    inputs = {
        "start_date": "2026-11-20",
        "activities": [activity("a", 2.25)],
        "rosters": [
            {
                "id": "team",
                "people": [
                    person(
                        availability=0.75,
                        daily_rate=200,
                        commitments=[
                            {"start": "2026-11-23", "end": "2026-11-23"},
                            {
                                "start": "2026-11-24",
                                "end": "2026-11-25",
                                "fraction": 0.25,
                            },
                        ],
                    )
                ],
            },
        ],
    }
    run = plan({}, inputs)["runs"][0]
    assert (run["start_date"], run["finish_date"], run["makespan_days"]) == (
        "2026-11-24",
        "2026-11-27",
        6,
    )
    assert run["assignments"][0]["cost"] == run["total_cost"] == 450
    assert run["critical_path_days"] == 3
    inputs["rosters"][0]["people"][0]["available_until"] = "2026-11-26"
    run = plan({}, inputs)["runs"][0]
    assert run["status"] == "infeasible"
    assert "continuous available slot" in run["blockers"][0]["reason"]


def test_longest_remaining_path_first_scenario_comparison_and_missing_fields():
    inputs = {
        "activities": [
            activity("low", 1),
            activity("mid", 1),
            activity("next", 1, ["mid"]),
            activity("end", 1, ["next"]),
        ],
        "start_date": "2026-11-22",  # Sunday
        "rosters": [{"id": "current", "people": [person(daily_rate=0)]}],
    }
    for a in inputs["activities"]:
        a["effort"] = {"optimistic": 0.5, "likely": 1, "pessimistic": 2}
    result = plan({}, inputs)
    assert [r["makespan_days"] for r in result["runs"]] == [4, 4, 8]
    run = result["runs"][1]
    assert run["start_date"] == "2026-11-23"
    assert [a["activity_id"] for a in run["assignments"]] == [
        "mid",
        "next",
        "end",
        "low",
    ]
    assert run["total_cost"] == 0
    assert run["warnings"][0]["code"] == "long_dependency_chain"
    assert all(w["code"] == "unconfirmed_estimate" for w in result["warnings"])
    inputs["activities"][0]["effort"]["optimistic"] = None
    inputs["rosters"].append({"id": "unknown", "people": [{"id": "new"}]})
    result = plan({}, inputs)
    assert [r["status"] for r in result["runs"]] == [
        "missing_inputs",
        "scheduled",
        "scheduled",
        "missing_inputs",
        "missing_inputs",
        "missing_inputs",
    ]
    assert result["runs"][-1]["critical_path_days"] == 6
    assert {
        "rosters.unknown.people.new.availability",
        "rosters.unknown.people.new.skills",
        "activities.low.effort.optimistic",
    } == {m["path"] for m in result["missing_inputs"]}


def test_ready_successor_reconsidered_before_future_reservations():
    inputs = {
        "activities": [
            activity("a", 1, skills=["x"]),
            activity("b", 1, skills=["y"]),
            activity("c", 2, ["a"], skills=["y"]),
        ],
        "start_date": "2026-11-23",
        "rosters": [
            {
                "id": "team",
                "people": [
                    person("x", skills=["x"]),
                    person("y", skills=["y"], available_from="2026-11-25"),
                ],
            }
        ],
    }
    run = plan({}, inputs)["runs"][0]
    assert [a["activity_id"] for a in run["assignments"]] == ["a", "c", "b"]


@pytest.mark.parametrize(
    "changes,match",
    [
        ([activity("a", 1, ["a"])], "cycle"),
        ([activity("a", 1, ["absent"])], "unknown predecessor"),
        ([activity("a", 1), activity("a", 1)], "Duplicate activity"),
        ([activity("a", -1)], "greater than 0"),
        ([activity("a", True)], "valid number"),
    ],
)
def test_reject_invalid_graph(changes, match):
    with pytest.raises(ValueError, match=match):
        plan({}, {"activities": changes})
